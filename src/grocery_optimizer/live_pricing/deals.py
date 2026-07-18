from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_verified_deals(
    *,
    snapshot_path: str | Path = "config/live_pricing/snapshots/latest.json",
    postal_code: str = "",
    category: str = "",
    chain: str = "",
    query: str = "",
    sale_only: bool = True,
    sort_by: Literal["price", "unit_price", "savings", "ending_soon"] = "savings",
    limit: int = 60,
) -> dict[str, Any]:
    path = Path(snapshot_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "deals": [],
            "count": 0,
            "generated_at_utc": "",
            "coverage": [],
            "detail": "Verified deal snapshot is unavailable.",
        }

    now = datetime.now(UTC)
    normalized_postal = postal_code.upper().replace(" ", "")
    category_filter = category.strip().lower()
    chain_filter = chain.strip().lower()
    query_filter = query.strip().lower()
    rows = payload.get("quotes", []) if int(payload.get("schema_version", 0) or 0) >= 2 else []
    deals: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("source_type") not in {"flyer_aggregator", "retailer_ecommerce"}:
            continue
        row_postal = str(row.get("postal_code", "")).upper().replace(" ", "")
        if normalized_postal and row_postal != normalized_postal:
            continue
        if category_filter and str(row.get("item_category", "")).lower() != category_filter:
            continue
        if chain_filter and chain_filter not in str(row.get("store_chain", "")).lower():
            continue
        haystack = f"{row.get('item_name', '')} {row.get('product_name', '')}".lower()
        if query_filter and query_filter not in haystack:
            continue
        valid_from = _parse_datetime(row.get("valid_from_utc"))
        valid_to = _parse_datetime(row.get("valid_to_utc"))
        if (valid_from and now < valid_from) or (valid_to and now > valid_to):
            continue
        regular_price = float(row.get("regular_price", 0.0) or 0.0)
        unit_price = float(row.get("unit_price", 0.0) or 0.0)
        savings_amount = round(max(0.0, regular_price - unit_price), 2)
        is_sale = bool(row.get("on_sale")) or savings_amount > 0
        if sale_only and not is_sale:
            continue
        deals.append(
            {
                **row,
                "unit_price": round(unit_price, 2),
                "savings_amount": savings_amount,
                "savings_percent": round((savings_amount / regular_price) * 100, 1) if regular_price else 0.0,
                "days_remaining": max(0, (valid_to.date() - now.date()).days) if valid_to else None,
                "verified_current": True,
            }
        )

    sort_keys = {
        "price": lambda row: (float(row["unit_price"]), -float(row["savings_amount"])),
        "unit_price": lambda row: (
            float(row.get("normalized_unit_price", row["unit_price"])),
            str(row.get("normalized_unit_basis", "package")),
        ),
        "savings": lambda row: (-float(row["savings_amount"]), float(row["unit_price"])),
        "ending_soon": lambda row: (
            int(row["days_remaining"]) if row["days_remaining"] is not None else 999,
            -float(row["savings_amount"]),
        ),
    }
    deals.sort(key=sort_keys[sort_by])
    configured = payload.get("diagnostics", {}).get("configured_chains", [])
    active_chains = {str(row.get("store_chain", "")).lower() for row in deals}
    coverage = [
        {
            "chain": configured_chain,
            "status": "current_matches" if str(configured_chain).lower() in active_chains else "no_current_matches",
        }
        for configured_chain in configured
    ] if isinstance(configured, list) else []
    return {
        "deals": deals[: max(1, min(limit, 200))],
        "count": len(deals),
        "generated_at_utc": str(payload.get("generated_at_utc", "")),
        "coverage": coverage,
        "source": str(payload.get("source", "")),
        "detail": "Current verified sales" if deals else "No current verified deals matched these filters.",
    }
