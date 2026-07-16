from __future__ import annotations

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false
import json
import re
from http.client import RemoteDisconnected
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _to_float(value: Any) -> float | None:
    try:
        return round(float(str(value).replace(",", "")), 4)
    except (TypeError, ValueError):
        return None


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


def _http_json(url: str, timeout_seconds: int = 10) -> Any:
    req = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": "grocery-optimizer/0.3",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8", errors="ignore")
            return json.loads(payload)
    except HTTPError as error:
        _close_http_error(error)
        return None
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError, RemoteDisconnected, ConnectionError):
        return None


def _extract_path(payload: Any, path: str) -> Any:
    if not path:
        return None
    current = payload
    for token in path.split("."):
        if isinstance(current, list):
            current_list = cast(list[Any], current)
            try:
                idx = int(token)
            except ValueError:
                return None
            if idx < 0 or idx >= len(current_list):
                return None
            current = current_list[idx]
        elif isinstance(current, dict):
            current_dict = cast(dict[str, Any], current)
            if token not in current_dict:
                return None
            current = current_dict[token]
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# Deal-text parsing
# ---------------------------------------------------------------------------

def _parse_deal_unit_price(value: Any) -> float | None:
    if not isinstance(value, str):
        return None

    text = value.strip().lower()
    if not text:
        return None

    # Example: 2/$5 or 2 / $5.00
    two_part = re.search(r"(\d+)\s*/\s*\$?\s*(\d+(?:\.\d{1,2})?)", text)
    if two_part:
        qty = _to_float(two_part.group(1))
        total = _to_float(two_part.group(2))
        if qty and total and qty > 0:
            return round(total / qty, 4)

    # Example: 2 for $5 or buy 3 for $10
    for_match = re.search(r"(\d+)\s*(?:for)\s*\$?\s*(\d+(?:\.\d{1,2})?)", text)
    if for_match:
        qty = _to_float(for_match.group(1))
        total = _to_float(for_match.group(2))
        if qty and total and qty > 0:
            return round(total / qty, 4)

    # Example: $1.99/lb, 2.49 ea, $3.25 each
    unit_match = re.search(
        r"\$?\s*(\d+(?:\.\d{1,2})?)\s*(?:/\s*|\s+)(ea|each|lb|kg|oz|g|ct|count|pack)",
        text,
    )
    if unit_match:
        return _to_float(unit_match.group(1))

    # Fallback: first explicit money-like number.
    money_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
    if money_match:
        return _to_float(money_match.group(1))

    # Last resort numeric parse if string itself is a number.
    return _to_float(text)


# Public alias used by the rest of the package and tests.
parse_deal_text = _parse_deal_unit_price


# ---------------------------------------------------------------------------
# Flipp / partner-feed extraction helpers
# ---------------------------------------------------------------------------

def _product_matches_store(product: dict[str, Any], store_chain_lower: str) -> bool:
    if not store_chain_lower:
        return True
    stores = str(product.get("stores", "")).lower()
    if store_chain_lower in stores:
        return True
    tags = product.get("stores_tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and store_chain_lower in tag.lower():
                return True
    return False


def _extract_partner_price(product: dict[str, Any]) -> float | None:
    # Common direct field in partner datasets.
    direct = _to_float(product.get("price"))
    if direct is not None and direct > 0:
        return direct

    # Some datasets expose list of prices.
    prices_obj = product.get("prices")
    if isinstance(prices_obj, list):
        for item in prices_obj:
            if isinstance(item, dict):
                candidate = _to_float(item.get("price"))
                if candidate is not None and candidate > 0:
                    return candidate
            else:
                candidate = _to_float(item)
                if candidate is not None and candidate > 0:
                    return candidate

    return None


def _extract_flipp_price(
    *,
    payload: Any,
    item_name: str,
    store_chain: str,
    fallback_price_path: str,
) -> float | None:
    item_tokens = _tokenize_for_match(item_name)
    store_tokens = _tokenize_for_match(store_chain)

    best_score = -1
    best_price: float | None = None
    minimum_score = 7

    for candidate in _iter_flipp_candidate_records(payload):
        score = 0
        if _record_matches_tokens(candidate, store_tokens):
            score += 4
        if _record_matches_tokens(candidate, item_tokens):
            score += 5

        price = _extract_price_from_record(candidate)
        if price is not None and price > 0:
            score += 3
        else:
            continue

        if score > best_score:
            best_score = score
            best_price = price

    if best_price is not None and best_score >= minimum_score:
        return best_price

    # Fallback to configured path only when no sufficiently matched candidate was found.
    configured = _to_float(_extract_path(payload, fallback_price_path))
    if configured is not None and configured > 0:
        return configured
    return None


def _extract_flipp_currency(payload: Any, fallback_currency_path: str) -> str | None:
    configured_currency = _extract_path(payload, fallback_currency_path)
    if isinstance(configured_currency, str) and configured_currency.strip():
        return configured_currency.strip().upper()

    for candidate in _iter_flipp_candidate_records(payload):
        for key in ("currency", "currency_code", "price_currency"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()

    return None


def _iter_flipp_candidate_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    # Common top-level containers across Flipp partner feeds and wrappers.
    for path in (
        "results",
        "data",
        "deals",
        "items",
        "offers",
        "flyers",
        "response.results",
        "response.data",
    ):
        value = _extract_path(payload, path)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
        elif isinstance(value, dict):
            records.append(value)

    # Fallback recursive walk in case the shape differs.
    if not records:
        records.extend(_collect_dicts_recursive(payload, max_nodes=500))

    # Deduplicate by object identity while preserving order.
    unique: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for record in records:
        oid = id(record)
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        unique.append(record)
    return unique


def _collect_dicts_recursive(value: Any, max_nodes: int) -> list[dict[str, Any]]:
    stack: list[Any] = [value]
    output: list[dict[str, Any]] = []
    visited = 0
    while stack and visited < max_nodes:
        current = stack.pop()
        visited += 1
        if isinstance(current, dict):
            output.append(current)
            for inner in current.values():
                stack.append(inner)
        elif isinstance(current, list):
            for inner in current:
                stack.append(inner)
    return output


def _tokenize_for_match(text: str) -> set[str]:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return {p for p in parts if len(p) >= 3}


def _record_matches_tokens(record: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return False
    corpus = _record_text_corpus(record)
    return any(token in corpus for token in tokens)


def _record_text_corpus(record: dict[str, Any]) -> str:
    fragments: list[str] = []
    for key in (
        "name",
        "title",
        "description",
        "merchant",
        "merchant_name",
        "retailer",
        "retailer_name",
        "brand",
        "product_name",
        "flyer_name",
        "deal_text",
        "price_text",
    ):
        value = record.get(key)
        if isinstance(value, str):
            fragments.append(value.lower())
    return " | ".join(fragments)


def _extract_price_from_record(record: dict[str, Any]) -> float | None:
    # Direct numeric candidates first.
    for key in (
        "price",
        "sale_price",
        "current_price",
        "unit_price",
        "value",
        "amount",
        "final_price",
    ):
        candidate = _to_float(record.get(key))
        if candidate is not None and candidate > 0:
            return candidate

    # Nested price objects are common in wrapped feeds.
    for key in ("price", "pricing", "sale"):
        nested = record.get(key)
        if isinstance(nested, dict):
            for nested_key in ("amount", "value", "current", "regular", "sale"):
                candidate = _to_float(nested.get(nested_key))
                if candidate is not None and candidate > 0:
                    return candidate

    # Parse promotional text formats like 2/$5, 3 for $10, $1.99/lb, 2.49 ea.
    for key in (
        "deal_text",
        "price_text",
        "description",
        "subtitle",
        "name",
        "title",
    ):
        value = record.get(key)
        parsed = _parse_deal_unit_price(value)
        if parsed is not None and parsed > 0:
            return parsed

    # Some feeds emit promo strings in arrays.
    for key in ("badges", "promotions", "labels", "highlights"):
        value = record.get(key)
        if isinstance(value, list):
            for element in value:
                parsed = _parse_deal_unit_price(element)
                if parsed is not None and parsed > 0:
                    return parsed

    return None
