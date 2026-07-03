from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import combinations
from typing import Any, cast

from ..data_io import load_items_from_json
from ..geo_discovery import discover_food_places, geocode_address, geocode_postal_code
from ..live_pricing import build_store_live_pricing_snapshot, get_live_price_history, get_live_pricing_engine
from ..location import apply_location_pricing, list_available_locations, load_location_profile
from ..optimizer import OptimizationWeights, optimize_grocery_list
from ..price_prediction import predict_price_drops
from ..retailer_research import summarize_retailer_research
from ..stores import (
    Store,
    find_nearby_stores,
    find_nearby_stores_from_coordinates,
    get_price_tier_multiplier,
    load_postal_codes,
    load_stores,
    optimize_route,
    optimize_route_from_coordinates,
)
from .schemas import OptimizeRequest


def _shelf_life_metrics(selected_items: list[Any]) -> dict[str, float | int]:
    if not selected_items:
        return {
            "total_units": 0,
            "average_shelf_life_days": 0.0,
            "shortest_shelf_life_days": 0,
            "longest_shelf_life_days": 0,
        }

    total_units = sum(item.quantity for item in selected_items)
    weighted_shelf_life = sum(item.shelf_life_days * item.quantity for item in selected_items)
    return {
        "total_units": total_units,
        "average_shelf_life_days": round(weighted_shelf_life / total_units, 1),
        "shortest_shelf_life_days": min(item.shelf_life_days for item in selected_items),
        "longest_shelf_life_days": max(item.shelf_life_days for item in selected_items),
    }


def _build_plan_insights(
    *,
    selected_items: list[Any],
    budget: float,
    total_cost: float,
    store_comparison: list[dict[str, Any]],
    route_info: dict[str, Any] | None,
    currency: str,
) -> dict[str, Any]:
    category_totals: dict[str, dict[str, Any]] = {}
    for item in selected_items:
        category = str(getattr(item, "category", "other") or "other")
        bucket = category_totals.setdefault(category, {"category": category, "cost": 0.0, "items": 0, "units": 0})
        bucket["cost"] = round(float(bucket["cost"]) + float(getattr(item, "total_cost", 0.0)), 2)
        bucket["items"] = int(bucket["items"]) + 1
        bucket["units"] = int(bucket["units"]) + int(getattr(item, "quantity", 0))

    sorted_categories = sorted(category_totals.values(), key=lambda row: (-float(row["cost"]), str(row["category"])))
    budget_used_percent = round((total_cost / budget) * 100, 1) if budget > 0 else 0.0
    best_store = min(store_comparison, key=lambda store: float(store.get("estimated_total", 0.0)), default=None)
    highest_store = max(store_comparison, key=lambda store: float(store.get("estimated_total", 0.0)), default=None)
    estimated_store_savings = 0.0
    if best_store and highest_store:
        estimated_store_savings = round(
            float(highest_store.get("estimated_total", 0.0)) - float(best_store.get("estimated_total", 0.0)),
            2,
        )

    next_actions: list[str] = []
    if budget_used_percent < 70:
        next_actions.append("Budget has room left; consider adding shelf-stable staples or higher-protein items.")
    elif budget_used_percent > 95:
        next_actions.append("Plan is close to budget; review premium stores or non-essential items before shopping.")
    else:
        next_actions.append("Budget usage is balanced for the selected item count.")

    if best_store:
        next_actions.append(f"Start price checks with {best_store.get('name', 'the lowest estimated store')}.")
    if route_info and route_info.get("total_distance_km") is not None:
        next_actions.append(f"Use the suggested route to keep travel near {route_info.get('total_distance_km')} km.")
    if route_info and float(route_info.get("net_route_savings", 0.0) or 0.0) > 0:
        next_actions.append(
            f"Split items by store only when you want the estimated {currency} {route_info.get('net_route_savings')} net route savings."
        )
    if sorted_categories:
        next_actions.append(f"Most spending is in {sorted_categories[0]['category']}; adjust that category first for savings.")

    return {
        "budget_used_percent": budget_used_percent,
        "category_breakdown": sorted_categories,
        "best_store": best_store,
        "estimated_store_savings": estimated_store_savings,
        "route_distance_km": route_info.get("total_distance_km") if route_info else None,
        "multi_store_item_savings": route_info.get("multi_store_item_savings", 0.0) if route_info else 0.0,
        "estimated_travel_cost": route_info.get("estimated_travel_cost", 0.0) if route_info else 0.0,
        "net_route_savings": route_info.get("net_route_savings", 0.0) if route_info else 0.0,
        "currency": currency,
        "next_actions": next_actions,
    }


def _resolve_origin(
    request: OptimizeRequest,
    postal_codes: dict[str, Any],
    profile: Any,
    all_stores: list[Any],
) -> tuple[dict[str, Any] | None, list[tuple[Any, float]]]:
    """Resolve the user's origin from postal code or address and find nearby stores.

    Tries, in order: local postal-code lookup, geocoded postal code, postal-prefix
    centroid fallback, and finally address geocoding.

    Returns ``(origin_dict, nearby_list)``.
    """
    normalized_postal = request.postal_code.upper().replace(" ", "") if request.postal_code else ""
    normalized_address = request.address.strip()
    origin: dict[str, Any] | None = None
    nearby: list[tuple[Any, float]] = []

    if request.postal_code:
        nearby = find_nearby_stores(
            request.postal_code, all_stores, postal_codes, max_distance_km=20.0
        )
        pc_info = postal_codes.get(normalized_postal)
        if pc_info:
            origin = {
                "postal_code": pc_info.postal_code,
                "display_name": f"{pc_info.city}, {pc_info.province_state}",
                "latitude": pc_info.latitude,
                "longitude": pc_info.longitude,
                "origin_type": "postal_code",
            }
        elif normalized_postal:
            # Fallback: geocode postal code not present in local sample set.
            geo = geocode_postal_code(normalized_postal)
            if geo:
                origin = {
                    "postal_code": normalized_postal,
                    "display_name": geo.display_name,
                    "latitude": geo.latitude,
                    "longitude": geo.longitude,
                    "origin_type": "postal_code_geocoded",
                }
                nearby = find_nearby_stores_from_coordinates(
                    geo.latitude,
                    geo.longitude,
                    all_stores,
                    max_distance_km=20.0,
                )

        # Offline fallback: infer origin from local postal prefix cluster.
        if not nearby and normalized_postal and len(normalized_postal) >= 3:
            prefix = normalized_postal[:3]
            prefix_matches = [info for code, info in postal_codes.items() if code.startswith(prefix)]
            if prefix_matches:
                avg_lat = sum(info.latitude for info in prefix_matches) / len(prefix_matches)
                avg_lon = sum(info.longitude for info in prefix_matches) / len(prefix_matches)
                sample = prefix_matches[0]
                origin = {
                    "postal_code": normalized_postal,
                    "display_name": f"{sample.city}, {sample.province_state} (postal-prefix fallback)",
                    "latitude": round(avg_lat, 6),
                    "longitude": round(avg_lon, 6),
                    "origin_type": "postal_prefix_fallback",
                }
                nearby = find_nearby_stores_from_coordinates(
                    avg_lat,
                    avg_lon,
                    all_stores,
                    max_distance_km=20.0,
                )

        # Last fallback: if postal flow failed but address is present, use address geocode.
        if not nearby and normalized_address:
            geo_country_hint = "Canada" if profile.currency == "CAD" else "USA"
            geo = geocode_address(normalized_address, country_hint=geo_country_hint)
            if geo:
                origin = {
                    "postal_code": normalized_postal,
                    "display_name": geo.display_name,
                    "latitude": geo.latitude,
                    "longitude": geo.longitude,
                    "origin_type": "address_fallback",
                }
                nearby = find_nearby_stores_from_coordinates(
                    geo.latitude,
                    geo.longitude,
                    all_stores,
                    max_distance_km=20.0,
                )
    else:
        # Address-only path.
        geo_country_hint = "Canada" if profile.currency == "CAD" else "USA"
        geo = geocode_address(normalized_address, country_hint=geo_country_hint)
        if geo:
            origin = {
                "postal_code": "",
                "display_name": geo.display_name,
                "latitude": geo.latitude,
                "longitude": geo.longitude,
                "origin_type": "address",
            }
            nearby = find_nearby_stores_from_coordinates(
                geo.latitude,
                geo.longitude,
                all_stores,
                max_distance_km=20.0,
            )

    return origin, nearby


def _apply_auto_discovery(
    request: OptimizeRequest,
    nearby: list[tuple[Any, float]],
    normalized_postal: str,
) -> list[tuple[Any, float]]:
    """Merge Overpass auto-discovered stores into the nearby list.

    Only runs when the ``GROCERY_ENABLE_AUTO_DISCOVERY`` env var is ``"true"``
    and a postal code is provided.  Duplicate stores (same name + distance) are
    skipped.  Returns the updated *nearby* list.
    """
    auto_discovery_enabled = os.getenv("GROCERY_ENABLE_AUTO_DISCOVERY", "true").lower() == "true"
    auto_scan: dict[str, Any] = (
        discover_food_places(request.postal_code, radius_km=12.0)
        if request.postal_code and auto_discovery_enabled
        else {"stores": []}
    )
    scan_stores = auto_scan.get("stores", [])

    if not scan_stores:
        return nearby

    seen_keys = {
        (store.name.lower(), round(distance, 1))
        for store, distance in nearby
    }
    for s in scan_stores[:30]:
        if not isinstance(s, dict):
            continue
        s_dict = cast(dict[str, Any], s)
        name = str(s_dict.get("name", "Food Store"))
        discovered_store = Store(
            store_id=str(s_dict.get("store_id", "scan-unknown")),
            name=name,
            chain=str(s_dict.get("chain", name)),
            address=str(s_dict.get("address", "Address unavailable")),
            postal_code=normalized_postal,
            latitude=float(s_dict.get("latitude", 0.0)),
            longitude=float(s_dict.get("longitude", 0.0)),
            price_tier=str(s_dict.get("price_tier", "mid")),
            quality_rating=float(s_dict.get("quality_rating", 3.5)),
            location_id=str(s_dict.get("location_id", "auto-discovered")),
        )
        dist = float(s_dict.get("distance_km", 0.0))
        key = (discovered_store.name.lower(), round(dist, 1))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        nearby.append((discovered_store, dist))

    return nearby


def _prioritize_stores(
    nearby: list[tuple[Any, float]],
    profile: Any,
    max_candidate_stores: int,
) -> list[tuple[Any, float]]:
    """Sort nearby stores: preferred chains first, then by distance.

    The result is limited to *max_candidate_stores* entries.
    """
    preferred_chains = {chain.lower() for chain in profile.stores}

    def _is_preferred(store_obj: Any) -> bool:
        chain = str(getattr(store_obj, "chain", "")).lower()
        name = str(getattr(store_obj, "name", "")).lower()
        if chain in preferred_chains:
            return True
        return any(pref in name for pref in preferred_chains)

    nearby_sorted = sorted(nearby, key=lambda item: item[1])
    preferred = [entry for entry in nearby_sorted if _is_preferred(entry[0])]
    others = [entry for entry in nearby_sorted if not _is_preferred(entry[0])]
    return (preferred + others)[:max_candidate_stores]


def _select_deal_route_stores(
    *,
    nearby: list[tuple[Any, float]],
    store_comparison: list[dict[str, Any]],
    item_quotes: list[dict[str, Any]],
    max_stops: int = 3,
) -> tuple[list[Any], dict[str, Any]]:
    """Choose route stops by true per-item multi-store savings.

    Each candidate store set is scored by assigning every item to the cheapest
    quote available inside that set, then subtracting a simple travel-cost
    estimate for additional stops. This avoids sending users to every store and
    avoids adding a stop unless item-level savings justify it.
    """
    if not nearby or not store_comparison:
        return [], {
            "selection_reason": "No nearby store estimates were available.",
            "deal_savings_by_store": {},
            "item_assignments": [],
        }

    nearby_by_id = {str(store.store_id): (store, distance) for store, distance in nearby}
    comparison_by_id = {str(store.get("store_id", "")): store for store in store_comparison}
    sorted_comparison = sorted(
        [store for store in store_comparison if str(store.get("store_id", "")) in nearby_by_id],
        key=lambda store: (float(store.get("estimated_total", 0.0)), float(store.get("distance_km", 999.0))),
    )
    if not sorted_comparison:
        return [], {
            "selection_reason": "Nearby stores could not be matched to estimates.",
            "deal_savings_by_store": {},
            "item_assignments": [],
        }

    best = sorted_comparison[0]
    best_id = str(best.get("store_id", ""))
    best_total = float(best.get("estimated_total", 0.0))
    quotes_by_item: dict[str, list[dict[str, Any]]] = {}
    for quote in item_quotes:
        item_name = str(quote.get("item_name", "")).strip().lower()
        store_id = str(quote.get("store_id", ""))
        if item_name and store_id in nearby_by_id:
            quotes_by_item.setdefault(item_name, []).append(quote)

    candidate_ids = [str(store.get("store_id", "")) for store in sorted_comparison[: min(len(sorted_comparison), 8)]]
    if not quotes_by_item or best_id not in candidate_ids:
        return [nearby_by_id[best_id][0]], {
            "selection_reason": "Best-value single-store route",
            "best_value_store_id": best_id,
            "best_value_store_name": best.get("name", ""),
            "skipped_store_count": max(0, len(sorted_comparison) - 1),
            "deal_savings_by_store": {},
            "item_assignments": [],
            "single_store_baseline_total": round(best_total, 2),
            "multi_store_total": round(best_total, 2),
            "multi_store_item_savings": 0.0,
            "estimated_travel_cost": 0.0,
            "net_route_savings": 0.0,
        }

    baseline_quotes: dict[str, dict[str, Any]] = {}
    for item_key, quotes in quotes_by_item.items():
        baseline_quote = next((quote for quote in quotes if str(quote.get("store_id", "")) == best_id), None)
        if baseline_quote is not None:
            baseline_quotes[item_key] = baseline_quote

    if len(baseline_quotes) != len(quotes_by_item):
        return [nearby_by_id[best_id][0]], {
            "selection_reason": "Best-value single-store route",
            "best_value_store_id": best_id,
            "best_value_store_name": best.get("name", ""),
            "skipped_store_count": max(0, len(sorted_comparison) - 1),
            "deal_savings_by_store": {},
            "item_assignments": [],
            "single_store_baseline_total": round(best_total, 2),
            "multi_store_total": round(best_total, 2),
            "multi_store_item_savings": 0.0,
            "estimated_travel_cost": 0.0,
            "net_route_savings": 0.0,
        }

    baseline_total = round(sum(float(quote.get("line_total", 0.0)) for quote in baseline_quotes.values()), 2)
    travel_cost_per_km = float(os.getenv("GROCERY_ROUTE_COST_PER_KM", "0.70"))
    savings_threshold = float(os.getenv("GROCERY_ROUTE_MIN_NET_SAVINGS", "1.50"))
    baseline_distance = float(nearby_by_id.get(best_id, (None, 0.0))[1])

    def _score_combo(combo_ids: tuple[str, ...]) -> dict[str, Any] | None:
        combo_set = set(combo_ids)
        assignments: list[dict[str, Any]] = []
        shopping_total = 0.0
        gross_savings = 0.0
        deal_savings_by_store: dict[str, float] = {}

        for item_key, quotes in quotes_by_item.items():
            available_quotes = [quote for quote in quotes if str(quote.get("store_id", "")) in combo_set]
            if not available_quotes:
                return None
            selected_quote = min(available_quotes, key=lambda quote: float(quote.get("line_total", 0.0)))
            baseline_quote = baseline_quotes[item_key]
            selected_store_id = str(selected_quote.get("store_id", ""))
            selected_line_total = float(selected_quote.get("line_total", 0.0))
            baseline_line_total = float(baseline_quote.get("line_total", 0.0))
            line_savings = max(0.0, baseline_line_total - selected_line_total)
            shopping_total += selected_line_total
            gross_savings += line_savings
            deal_savings_by_store[selected_store_id] = round(
                deal_savings_by_store.get(selected_store_id, 0.0) + line_savings,
                2,
            )
            assignments.append(
                {
                    "item_name": selected_quote.get("item_name", item_key),
                    "quantity": selected_quote.get("quantity", 1),
                    "store_id": selected_store_id,
                    "store_name": selected_quote.get("store_name", comparison_by_id.get(selected_store_id, {}).get("name", "")),
                    "unit_price": selected_quote.get("unit_price"),
                    "line_total": round(selected_line_total, 2),
                    "baseline_store_id": best_id,
                    "baseline_store_name": best.get("name", ""),
                    "baseline_line_total": round(baseline_line_total, 2),
                    "gross_savings": round(line_savings, 2),
                    "provider_id": selected_quote.get("provider_id", ""),
                    "pricing_source": selected_quote.get("pricing_source", ""),
                }
            )

        total_candidate_distance = sum(float(nearby_by_id[store_id][1]) for store_id in combo_ids)
        extra_distance = max(0.0, total_candidate_distance - baseline_distance)
        estimated_travel_cost = round(extra_distance * travel_cost_per_km, 2)
        net_savings = round(gross_savings - estimated_travel_cost, 2)
        return {
            "store_ids": combo_ids,
            "item_assignments": assignments,
            "deal_savings_by_store": deal_savings_by_store,
            "single_store_baseline_total": round(baseline_total, 2),
            "multi_store_total": round(shopping_total, 2),
            "multi_store_item_savings": round(gross_savings, 2),
            "estimated_travel_cost": estimated_travel_cost,
            "net_route_savings": net_savings,
        }

    best_plan = _score_combo((best_id,))
    for stop_count in range(1, min(max_stops, len(candidate_ids)) + 1):
        for combo in combinations(candidate_ids, stop_count):
            scored = _score_combo(combo)
            if scored is None:
                continue
            if best_plan is None or (
                float(scored["net_route_savings"]),
                float(scored["multi_store_item_savings"]),
                -len(scored["store_ids"]),
            ) > (
                float(best_plan["net_route_savings"]),
                float(best_plan["multi_store_item_savings"]),
                -len(best_plan["store_ids"]),
            ):
                best_plan = scored

    if best_plan is None or (
        len(best_plan["store_ids"]) > 1 and float(best_plan["net_route_savings"]) < savings_threshold
    ):
        best_plan = _score_combo((best_id,))

    selected_ids = set(best_plan["store_ids"]) if best_plan else {best_id}
    deal_savings_by_store = cast(dict[str, float], best_plan.get("deal_savings_by_store", {}) if best_plan else {})
    selected_stores = [
        nearby_by_id[store_id][0]
        for store_id in sorted(
            selected_ids,
            key=lambda sid: (
                0 if sid == best_id else 1,
                -deal_savings_by_store.get(sid, 0.0),
                float(comparison_by_id.get(sid, {}).get("estimated_total", 999999.0)),
            ),
        )
    ]

    reason = "Best-value single-store route"
    if len(selected_stores) > 1 and best_plan:
        reason = (
            "Per-item deal route: "
            f"{best_plan['multi_store_item_savings']:.2f} item savings, "
            f"{best_plan['estimated_travel_cost']:.2f} estimated travel cost"
        )

    return selected_stores, {
        "selection_reason": reason,
        "best_value_store_id": best_id,
        "best_value_store_name": best.get("name", ""),
        "skipped_store_count": max(0, len(sorted_comparison) - len(selected_stores)),
        "deal_savings_by_store": deal_savings_by_store,
        "item_assignments": best_plan.get("item_assignments", []) if best_plan else [],
        "single_store_baseline_total": best_plan.get("single_store_baseline_total", round(best_total, 2)) if best_plan else round(best_total, 2),
        "multi_store_total": best_plan.get("multi_store_total", round(best_total, 2)) if best_plan else round(best_total, 2),
        "multi_store_item_savings": best_plan.get("multi_store_item_savings", 0.0) if best_plan else 0.0,
        "estimated_travel_cost": best_plan.get("estimated_travel_cost", 0.0) if best_plan else 0.0,
        "net_route_savings": best_plan.get("net_route_savings", 0.0) if best_plan else 0.0,
    }


def _build_store_data(
    nearby: list[tuple[Any, float]],
    result: Any,
    profile: Any,
    normalized_postal: str,
    origin: dict[str, Any] | None,
    *,
    postal_codes: dict[str, Any] | None = None,
    normalized_address: str = "",
    use_live_pricing: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any], str]:
    """Build the store-comparison payload, nearby-stores list, route info, and pricing metadata.

    Returns ``(nearby_stores, store_comparison, route_info, pricing_meta, missing_reason)``.
    """
    nearby_stores: list[dict[str, Any]] = []
    route_info: dict[str, Any] | None = None
    missing_reason = ""

    # Determine why store data is missing (if applicable).
    if not nearby:
        if normalized_postal and postal_codes and normalized_postal not in postal_codes and not normalized_address:
            missing_reason = "Postal code not found in local sample set and area scan returned no stores."
        elif normalized_address:
            missing_reason = "Address could not be routed to nearby stores within 20 km."
        else:
            missing_reason = "No nearby stores found within 20 km."

    store_inputs: list[dict[str, Any]] = []
    for store, distance in nearby:
        store_info = {
            "store_id": store.store_id,
            "name": store.name,
            "chain": store.chain,
            "address": store.address,
            "distance_km": distance,
            "latitude": store.latitude,
            "longitude": store.longitude,
            "price_tier": store.price_tier,
            "quality_rating": store.quality_rating,
        }
        nearby_stores.append(store_info)
        store_inputs.append(store_info)

    country = "US" if profile.currency == "USD" else "CA"
    store_comparison, pricing_meta = build_store_live_pricing_snapshot(
        stores=store_inputs,
        selected_items=result.selected_items,
        postal_code=normalized_postal,
        country=country,
        currency=profile.currency,
        fallback_multiplier_resolver=get_price_tier_multiplier,
        use_live_providers=use_live_pricing,
    )

    # Generate a compact, deal-aware route instead of sending users to every nearby store.
    if nearby and origin:
        stores_to_route, route_selection = _select_deal_route_stores(
            nearby=nearby,
            store_comparison=store_comparison,
            item_quotes=list(pricing_meta.get("item_quotes", [])),
        )
        if origin.get("origin_type") in {"address", "address_fallback", "postal_code_geocoded", "postal_prefix_fallback"}:
            route = optimize_route_from_coordinates(
                stores_to_route,
                float(origin.get("latitude", 0.0)),
                float(origin.get("longitude", 0.0)),
            )
        else:
            pc_info = postal_codes.get(normalized_postal) if postal_codes else None
            route = optimize_route(stores_to_route, pc_info) if pc_info else []

        assignments = [
            cast(dict[str, Any], row)
            for row in route_selection.get("item_assignments", [])
            if isinstance(row, dict)
        ]
        assignments_by_store: dict[str, list[dict[str, Any]]] = {}
        for assignment in assignments:
            assignments_by_store.setdefault(str(assignment.get("store_id", "")), []).append(assignment)

        route_info = {
            "origin": origin,
            "stops": [
                {
                    "order": order,
                    "store_id": store.store_id,
                    "name": store.name,
                    "latitude": store.latitude,
                    "longitude": store.longitude,
                    "distance_from_previous_km": dist,
                    "estimated_total": next(
                        (
                            comparison.get("estimated_total")
                            for comparison in store_comparison
                            if str(comparison.get("store_id", "")) == str(store.store_id)
                        ),
                        None,
                    ),
                    "deal_savings": route_selection.get("deal_savings_by_store", {}).get(str(store.store_id), 0.0),
                    "assigned_item_count": len(assignments_by_store.get(str(store.store_id), [])),
                    "assigned_spend": round(
                        sum(float(row.get("line_total", 0.0)) for row in assignments_by_store.get(str(store.store_id), [])),
                        2,
                    ),
                    "assigned_items": [
                        {
                            "item_name": row.get("item_name", ""),
                            "quantity": row.get("quantity", 1),
                            "line_total": row.get("line_total", 0.0),
                            "gross_savings": row.get("gross_savings", 0.0),
                        }
                        for row in assignments_by_store.get(str(store.store_id), [])
                    ],
                }
                for store, dist, order in route
            ],
            "total_distance_km": round(sum(dist for _, dist, _ in route), 2),
            "selection_reason": route_selection.get("selection_reason", ""),
            "best_value_store_id": route_selection.get("best_value_store_id", ""),
            "best_value_store_name": route_selection.get("best_value_store_name", ""),
            "skipped_store_count": route_selection.get("skipped_store_count", 0),
            "item_assignments": assignments,
            "single_store_baseline_total": route_selection.get("single_store_baseline_total", 0.0),
            "multi_store_total": route_selection.get("multi_store_total", 0.0),
            "multi_store_item_savings": route_selection.get("multi_store_item_savings", 0.0),
            "estimated_travel_cost": route_selection.get("estimated_travel_cost", 0.0),
            "net_route_savings": route_selection.get("net_route_savings", 0.0),
        }

    return nearby_stores, store_comparison, route_info, pricing_meta, missing_reason


def optimize_from_request(request: OptimizeRequest) -> dict[str, Any]:
    # 1. Load and price items.
    profile = load_location_profile(request.location)
    items = load_items_from_json(request.catalog_path)
    priced_items = apply_location_pricing(items, profile)

    # 2. Apply preferences.
    likes = [item.lower() for item in request.likes]
    dislikes = [item.lower() for item in request.dislikes]
    health_goals = [item.lower() for item in request.health_goals]

    if dislikes:
        priced_items = [
            item
            for item in priced_items
            if not any(token in item.name.lower() or token in item.category.lower() for token in dislikes)
        ]

    goal_required: set[str] = set(request.required_categories)
    if any("protein" in goal or "muscle" in goal or "strength" in goal for goal in health_goals):
        goal_required.add("protein")
    if any("heart" in goal or "low sodium" in goal or "fiber" in goal for goal in health_goals):
        goal_required.add("produce")

    like_required = {
        item.category
        for item in priced_items
        if any(token in item.name.lower() or token in item.category.lower() for token in likes)
    }
    required_categories = goal_required | like_required

    # 3. Run optimization AND geo-resolution in parallel.
    #    The optimizer only needs items/budget; geo needs postal/address.
    #    Running them concurrently saves 10-40s of sequential HTTP waits.
    all_stores = load_stores()
    postal_codes = load_postal_codes()
    normalized_postal = request.postal_code.upper().replace(" ", "") if request.postal_code else ""
    normalized_address = request.address.strip()

    def _run_optimization():
        return optimize_grocery_list(
            items=priced_items,
            budget=request.budget,
            max_items=request.max_items,
            required_categories=required_categories,
            required_item_names=set(request.must_have_items),
            excluded_categories=set(request.excluded_categories),
            strategy=request.strategy,
            weights=OptimizationWeights(
                nutrition_weight=request.nutrition_weight,
                shelf_life_weight=request.shelf_life_weight,
                cost_weight=request.cost_weight,
            ),
            target_spend_ratio=0.92,
        )

    def _run_geo():
        if not (request.postal_code or normalized_address):
            return None, []
        origin, nearby = _resolve_origin(request, postal_codes, profile, all_stores)
        nearby = _apply_auto_discovery(request, nearby, normalized_postal)
        nearby = _prioritize_stores(nearby, profile, max_candidate_stores=50)
        return origin, nearby

    with ThreadPoolExecutor(max_workers=2) as pool:
        opt_future = pool.submit(_run_optimization)
        geo_future = pool.submit(_run_geo)
        result = opt_future.result()
        origin, nearby = geo_future.result()

    shelf_life = _shelf_life_metrics(result.selected_items)

    # 4. Build store data and route (depends on both optimization + geo results).
    if request.postal_code or normalized_address:
        nearby_stores, store_comparison, route_info, pricing_meta, missing_reason = _build_store_data(
            nearby, result, profile, normalized_postal, origin,
            postal_codes=postal_codes,
            normalized_address=normalized_address,
            use_live_pricing=request.include_live_pricing,
        )
    else:
        nearby_stores = []
        store_comparison = []
        route_info = None
        pricing_meta = {}
        missing_reason = "Enter a postal code or street address to show nearby stores, live price estimates, and route."

    # 6. Assemble and return response.
    pricing_timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    engine = get_live_pricing_engine()
    provider_health = engine.provider_health()
    providers_live = list(pricing_meta.get("providers_with_live_quotes", []))
    retailer_research = summarize_retailer_research(profile.location_id)
    avg_confidence = round(
        sum(float(store.get("confidence_score", 0.0)) for store in store_comparison) / len(store_comparison),
        2,
    ) if store_comparison else 0.0
    insights = _build_plan_insights(
        selected_items=result.selected_items,
        budget=request.budget,
        total_cost=result.total_cost,
        store_comparison=store_comparison,
        route_info=route_info,
        currency=profile.currency,
    )
    price_forecast = predict_price_drops(
        get_live_price_history(normalized_postal, limit=1000) if normalized_postal else []
    )
    route_assignments = [
        cast(dict[str, Any], row)
        for row in (route_info or {}).get("item_assignments", [])
        if isinstance(row, dict)
    ]
    assignment_by_item = {
        str(row.get("item_name", "")).strip().lower(): row
        for row in route_assignments
    }

    return {
        "location": {
            "location_id": profile.location_id,
            "display_name": profile.display_name,
            "currency": profile.currency,
            "postal_code": request.postal_code,
            "address": request.address,
        },
        "summary": {
            "strategy": result.strategy,
            "total_cost": result.total_cost,
            "budget_remaining": result.budget_remaining,
            "total_nutrition_score": result.total_nutrition_score,
            "total_shelf_life_days": result.total_shelf_life_days,
            "total_utility_score": result.total_utility_score,
            "total_units": shelf_life["total_units"],
            "average_shelf_life_days": shelf_life["average_shelf_life_days"],
            "shortest_shelf_life_days": shelf_life["shortest_shelf_life_days"],
            "longest_shelf_life_days": shelf_life["longest_shelf_life_days"],
        },
        "items": [
            {
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "quantity": item.quantity,
                "total_cost": item.total_cost,
                "nutrition_score": item.nutrition_score,
                "shelf_life_days": item.shelf_life_days,
                "recommended_store": assignment_by_item.get(item.name.lower(), {}).get("store_name", ""),
                "recommended_store_id": assignment_by_item.get(item.name.lower(), {}).get("store_id", ""),
                "store_line_total": assignment_by_item.get(item.name.lower(), {}).get("line_total", item.total_cost),
                "store_savings": assignment_by_item.get(item.name.lower(), {}).get("gross_savings", 0.0),
            }
            for item in result.selected_items
        ],
        "stores": {
            "nearby": nearby_stores,
            "comparison": store_comparison,
            "data_source": "Instant store-tier estimates; use Refresh prices for live provider checks"
            if not request.include_live_pricing
            else "Third-party live feeds when available, with store-tier fallback estimates",
            "pricing_mode": "instant_estimate"
            if not request.include_live_pricing
            else "third_party_live_with_fallback",
            "last_updated_utc": pricing_meta.get("last_updated_utc", pricing_timestamp),
            "refresh_interval_seconds": 60,
            "available": len(store_comparison) > 0,
            "missing_reason": missing_reason,
            "provider_health": provider_health,
            "providers_with_live_quotes": providers_live,
            "average_confidence": avg_confidence,
            "live_quote_coverage_percent": pricing_meta.get("live_coverage_percent", 0.0),
            "live_quotes": pricing_meta.get("live_quotes", 0),
            "total_quote_attempts": pricing_meta.get("total_quote_attempts", 0),
            "item_quotes": pricing_meta.get("item_quotes", []),
            "alerts": pricing_meta.get("alerts", []),
            "auto_discovery_used": any(str(s.get("store_id", "")).startswith("scan-") for s in nearby_stores),
            "retailer_research": retailer_research,
        },
        "route": route_info,
        "price_forecast": price_forecast,
        "insights": insights,
    }


def get_locations() -> list[str]:
    return list_available_locations()
