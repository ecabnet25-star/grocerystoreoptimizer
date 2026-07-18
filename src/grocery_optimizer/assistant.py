from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_PROTEIN_TOKENS = ("chicken", "tofu", "tuna", "bean", "lentil", "egg", "yogurt")
_BASE_TOKENS = ("rice", "quinoa", "pasta", "tortilla", "bread", "oat", "potato")
_PRODUCE_TOKENS = (
    "romaine",
    "spinach",
    "broccoli",
    "carrot",
    "apple",
    "banana",
    "tomato",
    "onion",
    "berries",
    "vegetable",
)


def _close_http_error(error: HTTPError) -> None:
    try:
        error.close()
    except Exception:
        response_body = getattr(error, "fp", None)
        if response_body and hasattr(response_body, "close"):
            response_body.close()


def _item_names(plan_items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("name", "")).strip() for item in plan_items if str(item.get("name", "")).strip()]


def _find(items: list[str], tokens: tuple[str, ...], limit: int = 2) -> list[str]:
    return [item for item in items if any(token in item.lower() for token in tokens)][:limit]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _safe_extras(dislikes: list[str], language: str) -> list[str]:
    options = ["huile de cuisson", "sel", "poivre"] if language == "fr" else ["cooking oil", "salt", "pepper"]
    lowered = [value.lower() for value in dislikes]
    return [option for option in options if not any(token in option.lower() for token in lowered)]


def _build_structured_recipes(
    items: list[str],
    dislikes: list[str],
    user_message: str,
    language: str,
) -> list[dict[str, Any]]:
    proteins = _find(items, _PROTEIN_TOKENS)
    bases = _find(items, _BASE_TOKENS)
    produce = _find(items, _PRODUCE_TOKENS, limit=3)
    extras = _safe_extras(dislikes, language)
    recipes: list[dict[str, Any]] = []

    bowl_items = _unique([*(proteins[:1] or items[:1]), *bases[:1], *produce[:2]])
    if bowl_items:
        if language == "fr":
            recipes.append(
                {
                    "name": "Bol repas express",
                    "cook_time_minutes": 20,
                    "ingredients_from_plan": bowl_items,
                    "extras_needed": extras,
                    "steps": [
                        f"Cuire {bases[0]} selon l'emballage." if bases else f"Preparer {bowl_items[0]} comme base.",
                        f"Cuire {proteins[0]} jusqu'a cuisson complete." if proteins else "Chauffer les ingredients principaux.",
                        f"Ajouter {', '.join(produce[:2])}; assaisonner et servir." if produce else "Assaisonner, assembler et servir.",
                    ],
                }
            )
        else:
            recipes.append(
                {
                    "name": "Quick grocery bowl",
                    "cook_time_minutes": 20,
                    "ingredients_from_plan": bowl_items,
                    "extras_needed": extras,
                    "steps": [
                        f"Cook {bases[0]} according to its package." if bases else f"Prepare {bowl_items[0]} as the base.",
                        f"Cook {proteins[0]} until safely done." if proteins else "Warm the main ingredients.",
                        f"Add {', '.join(produce[:2])}; season and serve." if produce else "Season, assemble, and serve.",
                    ],
                }
            )

    breakfast_tokens = ("egg", "oat", "yogurt", "bread", "apple", "banana", "berries")
    breakfast_items = _find(items, breakfast_tokens, limit=4)
    remaining = [item for item in items if item not in bowl_items]
    second_items = breakfast_items if len(breakfast_items) >= 2 else remaining[:4]
    if second_items:
        is_breakfast = len(breakfast_items) >= 2
        if language == "fr":
            recipes.append(
                {
                    "name": "Dejeuner nourrissant" if is_breakfast else "Poelee vide-frigo",
                    "cook_time_minutes": 10 if is_breakfast else 25,
                    "ingredients_from_plan": second_items,
                    "extras_needed": extras[:2],
                    "steps": [
                        f"Preparer {second_items[0]} dans un bol ou une poele.",
                        f"Ajouter {', '.join(second_items[1:3])}." if len(second_items) > 1 else "Assaisonner legerement.",
                        "Cuire jusqu'a la texture desiree, puis servir.",
                    ],
                }
            )
        else:
            recipes.append(
                {
                    "name": "Filling breakfast" if is_breakfast else "Use-it-up skillet",
                    "cook_time_minutes": 10 if is_breakfast else 25,
                    "ingredients_from_plan": second_items,
                    "extras_needed": extras[:2],
                    "steps": [
                        f"Prepare {second_items[0]} in a bowl or skillet.",
                        f"Add {', '.join(second_items[1:3])}." if len(second_items) > 1 else "Season lightly.",
                        "Cook to the desired texture, then serve.",
                    ],
                }
            )

    requested_fast = any(token in user_message.lower() for token in ("fast", "quick", "rapide", "vite"))
    return recipes[:1] if requested_fast else recipes[:2]


def _intent_tip(user_message: str, language: str) -> str:
    message = user_message.lower()
    if any(token in message for token in ("prep", "schedule", "horaire")):
        return (
            "Cuisez les cereales et les proteines en lot; gardez les garnitures separees."
            if language == "fr"
            else "Batch cook grains and proteins; keep toppings separate."
        )
    if any(token in message for token in ("spoil", "fresh", "perime", "frais")):
        return (
            "Utilisez d'abord les legumes-feuilles et les petits fruits."
            if language == "fr"
            else "Use leafy greens and berries first."
        )
    return "Commencez par les aliments les plus perissables." if language == "fr" else "Start with the most perishable items."


def _build_ollama_prompt(
    *,
    user_message: str,
    item_names: list[str],
    dislikes: list[str],
    language: str,
) -> str:
    output_language = "French" if language == "fr" else "English"
    return (
        f"Reply in {output_language}. You are The Chef. Give at most two concise recipes using only these cart ingredients: "
        f"{', '.join(item_names[:24])}. Avoid: {', '.join(dislikes[:10]) or 'none'}. "
        f"Request: {user_message or 'meal ideas'}. Include name, time, extras, and three numbered steps. No greeting."
    )


def _ollama_generate_response(prompt: str) -> tuple[str | None, str]:
    base_url = os.getenv("GROCERY_ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("GROCERY_ASSISTANT_OLLAMA_MODEL", "llama3.2:3b")
    timeout = int(os.getenv("GROCERY_ASSISTANT_OLLAMA_TIMEOUT_SECONDS", "8"))
    request = Request(
        url=f"{base_url}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.35, "num_predict": 180},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="ignore"))
    except HTTPError as error:
        _close_http_error(error)
        return None, model
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None, model
    text = str(parsed.get("response", "")).strip()
    return (text or None), model


def build_meal_assistant_response(
    *,
    user_message: str,
    plan_items: list[dict[str, Any]],
    likes: list[str],
    dislikes: list[str],
    health_goals: list[str],
    language: str = "en",
) -> dict[str, Any]:
    del likes, health_goals
    selected_language = "fr" if language == "fr" else "en"
    item_names = _item_names(plan_items)
    normalized_dislikes = [value.strip().lower() for value in dislikes if value.strip()]
    recipes = _build_structured_recipes(item_names, normalized_dislikes, user_message, selected_language)
    plan_tip = _intent_tip(user_message, selected_language)
    summary = (
        f"{len(recipes)} recette{'s' if len(recipes) != 1 else ''} prete{'s' if len(recipes) != 1 else ''}. {plan_tip}"
        if selected_language == "fr"
        else f"{len(recipes)} recipe{'s' if len(recipes) != 1 else ''} ready. {plan_tip}"
    )

    assistant_mode = os.getenv("GROCERY_ASSISTANT_MODE", "rules").strip().lower()
    llm_text: str | None = None
    model = ""
    # Rules are the production path: deterministic, structured, and immediate.
    # Ollama is opt-in for operators who explicitly accept its extra latency.
    if assistant_mode == "ollama":
        llm_text, model = _ollama_generate_response(
            _build_ollama_prompt(
                user_message=user_message,
                item_names=item_names,
                dislikes=normalized_dislikes,
                language=selected_language,
            )
        )
    response = llm_text or summary
    suggestions = [
        {
            "title": recipe["name"],
            "instructions": " ".join(recipe["steps"]),
            "uses": ", ".join(recipe["ingredients_from_plan"]),
        }
        for recipe in recipes
    ]
    return {
        "response": response,
        "recipes": recipes,
        "suggestions": suggestions,
        "goal_tips": [],
        "plan_tip": plan_tip,
        "assistant_mode": assistant_mode,
        "response_source": "ollama" if llm_text else "rule_fallback",
        "model": model,
        "language": selected_language,
    }
