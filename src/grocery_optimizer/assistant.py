from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MEAL_PATTERNS = [
    (["rice", "beans", "broccoli"], "Protein rice bowl", "Cook rice, saute broccoli, and top with seasoned beans."),
    (["eggs", "bread"], "Savory egg toast", "Toast bread and top with scrambled eggs plus a crunchy side."),
    (["yogurt", "berries"], "Berry yogurt bowl", "Mix yogurt with berries for breakfast or a fast snack."),
    (["chicken", "broccoli", "rice"], "Chicken and greens plate", "Roast chicken, steam broccoli, and serve over rice."),
    (["oats", "yogurt"], "Overnight oat cup", "Mix oats and yogurt, chill overnight, then top with fruit."),
    (["pasta", "tomato"], "Pantry pasta", "Simmer tomato sauce and toss with pasta plus any greens."),
]


HEALTH_GUIDANCE = {
    "muscle": "Add high-protein options and include a protein source in each meal.",
    "weight": "Favor produce, lean proteins, and high-fiber staples.",
    "heart": "Keep sodium low and prioritize produce, whole grains, and healthy fats.",
    "energy": "Combine complex carbs with protein to stabilize energy through the day.",
}

CHEF_INTENTS = {
    "fast": "Keep the first meal to 20 minutes or less by using the quickest-cooking protein and a simple bowl or toast format.",
    "dinner": "Build dinners around one protein, one vegetable, and one filling base so the plan feels complete.",
    "prep": "Batch cook the grains or starch first, portion proteins second, and keep sauces or fresh toppings separate.",
    "schedule": "Use fresh produce early in the week, then rely on pantry staples and sturdier proteins later.",
    "spoil": "Cook tender greens, berries, and fresh herbs first; save grains, canned goods, and frozen items for later.",
    "fresh": "Prioritize the shortest shelf-life produce in the first two meals.",
    "breakfast": "Use oats, yogurt, eggs, fruit, or bread first for low-effort breakfasts.",
    "lunch": "Turn leftovers into bowls, wraps, or salads so lunch does not require a full second recipe.",
}


def _close_http_error(error: HTTPError) -> None:
    try:
        error.close()
        return
    except Exception:
        pass

    response_body = getattr(error, "fp", None)
    if response_body and hasattr(response_body, "close"):
        try:
            response_body.close()
        except Exception:
            pass


def _normalize(tokens: list[str]) -> list[str]:
    return [token.strip().lower() for token in tokens if token and token.strip()]


def _extract_item_names(plan_items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in plan_items:
        name = str(item.get("name", "")).strip()
        if name:
            names.append(name.lower())
    return names


def _goal_tips(health_goals: list[str]) -> list[str]:
    tips: list[str] = []
    for goal in health_goals:
        for key, tip in HEALTH_GUIDANCE.items():
            if key in goal.lower() and tip not in tips:
                tips.append(tip)
    return tips


def _intent_tip(user_message: str) -> str:
    msg = user_message.lower()
    for keyword, tip in CHEF_INTENTS.items():
        if keyword in msg:
            return tip
    return "Start with the most perishable items, then stretch pantry staples across multiple meals."


def _build_fallback_suggestions(item_names: list[str], dislikes: list[str]) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for required_tokens, title, instructions in MEAL_PATTERNS:
        if all(any(token in item for item in item_names) for token in required_tokens):
            if any(dislike in title.lower() for dislike in dislikes):
                continue
            suggestions.append(
                {
                    "title": title,
                    "instructions": instructions,
                    "uses": ", ".join(required_tokens),
                }
            )

    if not suggestions and item_names:
        top_items = ", ".join(item_names[:4])
        suggestions.append(
            {
                "title": "Flexible skillet meal",
                "instructions": "Build a simple skillet or bowl meal around your top ingredients.",
                "uses": top_items,
            }
        )

    return suggestions


def _build_ollama_prompt(
    *,
    user_message: str,
    item_names: list[str],
    likes: list[str],
    dislikes: list[str],
    health_goals: list[str],
) -> str:
    items_text = ", ".join(item_names[:24]) if item_names else "No items"
    likes_text = ", ".join(likes[:10]) if likes else "None"
    dislikes_text = ", ".join(dislikes[:10]) if dislikes else "None"
    goals_text = ", ".join(health_goals[:10]) if health_goals else "None"
    user_text = user_message.strip() or "Give me meal ideas for this grocery list."

    return (
        "You are The Chef, a practical, upbeat grocery meal-planning helper inside a grocery planner app. "
        "Return direct, concise guidance and exactly 3 meal ideas grounded in the provided groceries. "
        "Respect dislikes and health goals. Avoid ingredients the user dislikes.\n\n"
        f"Groceries: {items_text}\n"
        f"Likes: {likes_text}\n"
        f"Dislikes: {dislikes_text}\n"
        f"Health goals: {goals_text}\n"
        f"User request: {user_text}\n\n"
        "Format:\n"
        "Use at most 90 words total. No introduction, repetition, or filler.\n"
        "1) Start with one sentence beginning 'Chef:'\n"
        "2) Give exactly 3 bullet meals; each bullet must name the meal and key groceries.\n"
        "3) End with one prep tip under 12 words."
    )


def _ollama_generate_response(prompt: str) -> tuple[str | None, str]:
    base_url = os.getenv("GROCERY_ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("GROCERY_ASSISTANT_OLLAMA_MODEL", "llama3.2:3b")
    timeout = int(os.getenv("GROCERY_ASSISTANT_OLLAMA_TIMEOUT_SECONDS", "12"))

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.6,
            "num_predict": 180,
        },
    }

    req = Request(
        url=f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
    except HTTPError as error:
        _close_http_error(error)
        return None, model
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None, model

    text = str(parsed.get("response", "")).strip()
    if not text:
        return None, model
    return text, model


def build_meal_assistant_response(
    *,
    user_message: str,
    plan_items: list[dict[str, Any]],
    likes: list[str],
    dislikes: list[str],
    health_goals: list[str],
) -> dict[str, Any]:
    msg = user_message.strip()
    normalized_likes = _normalize(likes)
    normalized_dislikes = _normalize(dislikes)
    normalized_goals = _normalize(health_goals)
    item_names = _extract_item_names(plan_items)

    suggestions = _build_fallback_suggestions(item_names, normalized_dislikes)

    preference_line = ""
    if normalized_likes:
        preference_line += f" Prioritizing: {', '.join(normalized_likes[:4])}."
    if normalized_dislikes:
        preference_line += f" Avoiding: {', '.join(normalized_dislikes[:4])}."

    goal_tips = _goal_tips(normalized_goals)
    intent_tip = _intent_tip(msg)
    fallback_response = (
        "Chef: these ideas use your current cart."
        + preference_line
        + (f" Goal tip: {goal_tips[0]}" if goal_tips else "")
        + f" Plan tip: {intent_tip}"
    )

    assistant_mode = os.getenv("GROCERY_ASSISTANT_MODE", "hybrid").strip().lower()
    llm_text: str | None = None
    llm_model = ""

    if assistant_mode in {"hybrid", "ollama"}:
        llm_prompt = _build_ollama_prompt(
            user_message=msg,
            item_names=item_names,
            likes=normalized_likes,
            dislikes=normalized_dislikes,
            health_goals=normalized_goals,
        )
        llm_text, llm_model = _ollama_generate_response(llm_prompt)

    response = llm_text if llm_text else fallback_response
    response_source = "ollama" if llm_text else "rule_fallback"

    return {
        "response": response,
        "suggestions": suggestions[:4],
        "goal_tips": goal_tips,
        "plan_tip": intent_tip,
        "assistant_mode": assistant_mode,
        "response_source": response_source,
        "model": llm_model,
    }
