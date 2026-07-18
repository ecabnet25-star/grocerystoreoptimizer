from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..unit_pricing import normalized_unit_price, parse_package_size

DEFAULT_FLIPP_SEARCH_URL = "https://cdn-gateflipp.flippback.com/bf/flipp/items/search"
_TOKEN_STOPWORDS = {"and", "or", "ou", "the", "fresh", "product", "produit", "your", "market"}
_NON_MATCHING_PHRASES = {"nature valley"}
_NON_GROCERY_TERMS = {
    "bird",
    "birdhouse",
    "candle",
    "cleaner",
    "conditioner",
    "cooker",
    "costume",
    "decor",
    "deodorant",
    "detergent",
    "feeder",
    "house",
    "litter",
    "lotion",
    "ornament",
    "serum",
    "shampoo",
    "shirt",
    "slime",
    "slimygloop",
    "soap",
    "sock",
    "toy",
}
_DERIVATIVE_TERMS = {
    "baby",
    "bar",
    "becel",
    "blend",
    "brochette",
    "bread",
    "breaded",
    "canola",
    "candy",
    "cereal",
    "chip",
    "chocolate",
    "cider",
    "coconut",
    "condensed",
    "cooked",
    "cookie",
    "cracker",
    "deli",
    "diced",
    "dijon",
    "dijonnaise",
    "dried",
    "drink",
    "ice",
    "juice",
    "loaf",
    "margarine",
    "marinated",
    "meal",
    "pam",
    "paratha",
    "pie",
    "pizza",
    "prepared",
    "puree",
    "reese",
    "roast",
    "roasted",
    "salad",
    "sardine",
    "sauce",
    "seasoned",
    "shish",
    "skewer",
    "slice",
    "smoked",
    "smoothie",
    "soup",
    "spray",
    "spread",
    "stuffed",
    "taouk",
    "vegetable",
}


def _plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _tokens(value: str) -> set[str]:
    output: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", _plain_text(value)):
        if len(token) < 2 or token in _TOKEN_STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        output.add(token)
    return output


def item_match_score(query: str, candidate: str) -> float:
    candidate_text = _plain_text(candidate)
    if any(phrase in candidate_text for phrase in _NON_MATCHING_PHRASES):
        return 0.0
    requested = _tokens(query)
    available = _tokens(candidate)
    if not requested or not available:
        return 0.0
    if available & _NON_GROCERY_TERMS:
        return 0.0
    overlap = len(requested & available)
    coverage = overlap / len(requested)
    precision = overlap / len(available)
    score = (coverage * 0.8) + (precision * 0.2)
    derivative_count = len((available - requested) & _DERIVATIVE_TERMS)
    if derivative_count:
        score -= min(0.45, derivative_count * 0.25)
    return round(max(0.0, score), 4)


def chain_matches(requested_chain: str, candidate_chain: str) -> bool:
    requested = _tokens(requested_chain)
    candidate = _tokens(candidate_chain)
    if not requested or not candidate:
        return False
    aliases = {
        "superc": {"super", "c"},
        "pa": {"supermarche", "pa"},
    }
    requested_plain = re.sub(r"[^a-z0-9]", "", _plain_text(requested_chain))
    candidate_plain = re.sub(r"[^a-z0-9]", "", _plain_text(candidate_chain))
    requested = aliases.get(requested_plain, requested)
    candidate = aliases.get(candidate_plain, candidate)
    return requested == candidate or requested.issubset(candidate) or candidate.issubset(requested)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _offer_quantity(pre_price_text: Any) -> int:
    text = str(pre_price_text or "").strip()
    match = re.search(r"\b(\d+)\s*(?:/|for\b)", text, flags=re.IGNORECASE)
    return max(1, int(match.group(1))) if match else 1


def _price_basis(post_price_text: Any) -> tuple[float | None, str, str]:
    text = str(post_price_text or "").strip()
    normalized = re.sub(r"\s+", "", text.lower())
    if normalized.startswith(("/lb", "lb")):
        return 1.0, "lb", "per lb"
    if normalized.startswith(("/kg", "kg")):
        return 1.0, "kg", "per kg"
    return None, "package", ""


def flipp_search_url(
    *,
    item_name: str,
    postal_code: str,
    locale: str = "en-ca",
    base_url: str = DEFAULT_FLIPP_SEARCH_URL,
) -> str:
    return f"{base_url}?{urlencode({'locale': locale, 'postal_code': postal_code, 'sid': '', 'q': item_name})}"


def fetch_flipp_search(
    *,
    item_name: str,
    postal_code: str,
    locale: str = "en-ca",
    base_url: str = DEFAULT_FLIPP_SEARCH_URL,
    timeout_seconds: int = 8,
) -> tuple[dict[str, Any], str]:
    url = flipp_search_url(item_name=item_name, postal_code=postal_code, locale=locale, base_url=base_url)
    request = Request(
        url=url,
        headers={"Accept": "application/json", "User-Agent": "unibite.click/0.4 (current flyer lookup)"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    return (payload if isinstance(payload, dict) else {}), url


def parse_flipp_quotes(
    payload: dict[str, Any],
    *,
    requested_item: str,
    requested_chain: str = "",
    item_category: str = "other",
    source_url: str = "",
    now: datetime | None = None,
    include_ecommerce: bool = True,
) -> list[dict[str, Any]]:
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    candidates: list[tuple[str, dict[str, Any]]] = []
    flyer_rows = payload.get("items", [])
    if isinstance(flyer_rows, list):
        candidates.extend(("flyer", row) for row in flyer_rows if isinstance(row, dict))
    ecommerce_rows = payload.get("ecom_items", [])
    if include_ecommerce and isinstance(ecommerce_rows, list):
        candidates.extend(("ecommerce", row) for row in ecommerce_rows if isinstance(row, dict))

    quotes: list[dict[str, Any]] = []
    for source_type, row in candidates:
        product_name = str(row.get("name") or "").strip()
        chain = str(row.get("merchant_name") or row.get("merchant") or "").strip()
        score = item_match_score(requested_item, product_name)
        if not product_name or not chain or score < 0.72:
            continue
        if requested_chain and not chain_matches(requested_chain, chain):
            continue

        try:
            offer_price = float(row.get("current_price"))
        except (TypeError, ValueError):
            continue
        if offer_price <= 0:
            continue

        valid_from = _parse_datetime(row.get("valid_from"))
        valid_to = _parse_datetime(row.get("valid_to"))
        if source_type == "flyer" and (
            (valid_from and current_time < valid_from) or (valid_to and current_time > valid_to)
        ):
            continue

        offer_quantity = _offer_quantity(row.get("pre_price_text"))
        effective_price = round(offer_price / offer_quantity, 2)
        try:
            original = float(row.get("original_price")) / offer_quantity
        except (TypeError, ValueError):
            original = None
        package_size, package_unit, package_label = parse_package_size(product_name)
        if item_category == "produce" and package_size is not None and package_unit in {"ml", "l"}:
            continue
        basis_size, basis_unit, basis_label = _price_basis(row.get("post_price_text"))
        if basis_size is not None:
            package_size, package_unit, package_label = basis_size, basis_unit, basis_label
        normalized_price, normalized_basis = normalized_unit_price(effective_price, package_size, package_unit)
        quotes.append(
            {
                "item_name": requested_item,
                "item_category": item_category,
                "product_name": product_name,
                "store_chain": chain,
                "currency": "CAD",
                "unit_price": effective_price,
                "regular_price": round(original, 2) if original and original > 0 else None,
                "offer_price": round(offer_price, 2),
                "offer_quantity": offer_quantity,
                "package_size": package_size,
                "package_unit": package_unit,
                "package_label": package_label,
                "normalized_unit_price": normalized_price,
                "normalized_unit_basis": normalized_basis,
                "on_sale": source_type == "flyer" or bool(original and original > effective_price),
                "valid_from_utc": valid_from.isoformat().replace("+00:00", "Z") if valid_from else "",
                "valid_to_utc": valid_to.isoformat().replace("+00:00", "Z") if valid_to else "",
                "source_type": "flyer_aggregator" if source_type == "flyer" else "retailer_ecommerce",
                "source_url": source_url,
                "source_item_id": str(row.get("flyer_item_id") or row.get("item_id") or row.get("id") or ""),
                "image_url": str(row.get("clean_image_url") or row.get("image_url") or ""),
                "price_basis_text": str(row.get("post_price_text") or ""),
                "confidence": round((0.84 if source_type == "flyer" else 0.76) + (score * 0.1), 4),
                "match_score": score,
                "fetched_at_utc": current_time.isoformat().replace("+00:00", "Z"),
            }
        )

    quotes.sort(
        key=lambda quote: (
            -float(quote["match_score"]),
            0 if quote["source_type"] == "flyer_aggregator" else 1,
            float(quote["unit_price"]),
        )
    )
    return quotes
