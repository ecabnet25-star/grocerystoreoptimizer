from __future__ import annotations

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha1
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .stores import calculate_distance_km, load_postal_codes, load_stores


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float
    display_name: str
    country_code: str


# In-memory cache for Nominatim geocode results to avoid repeated HTTP calls.
_geocode_cache: dict[str, GeoPoint | None] = {}

# In-memory cache for Overpass store discovery results (keyed by postal+radius).
_discovery_cache: dict[str, dict[str, Any]] = {}

_OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter?data=",
    "https://overpass.private.coffee/api/interpreter?data=",
)

_GROCERY_SHOP_TYPES = {"supermarket", "grocery", "greengrocer", "health_food", "wholesale"}
_GROCERY_DEPARTMENT_STORE_NAMES = ("walmart", "giant tiger", "tigre géant")


def _is_grocery_location(name: str, tags: dict[str, Any]) -> bool:
    shop_types = {part.strip() for part in str(tags.get("shop", "")).lower().split(";") if part.strip()}
    if shop_types & _GROCERY_SHOP_TYPES:
        return True
    normalized_name = name.lower()
    if "department_store" in shop_types and any(chain in normalized_name for chain in _GROCERY_DEPARTMENT_STORE_NAMES):
        return True
    return str(tags.get("amenity", "")).lower() == "marketplace"


@lru_cache(maxsize=1)
def _load_discovery_snapshot_stores(
    base_dir: str = "config/discovery_snapshots",
) -> tuple[dict[str, Any], ...]:
    root = Path(base_dir)
    if not root.exists():
        return ()

    stores: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = payload.get("stores", []) if isinstance(payload, dict) else []
        stores.extend(cast(dict[str, Any], row) for row in rows if isinstance(row, dict))
    return tuple(stores)


def _nearby_snapshot_stores(point: GeoPoint, radius_km: float) -> list[dict[str, Any]]:
    nearby: list[dict[str, Any]] = []
    for stored in _load_discovery_snapshot_stores():
        tags = dict(stored.get("tags", {})) if isinstance(stored.get("tags"), dict) else {}
        if not _is_grocery_location(str(stored.get("name", "")), tags):
            continue
        try:
            latitude = float(stored["latitude"])
            longitude = float(stored["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        distance = calculate_distance_km(point.latitude, point.longitude, latitude, longitude)
        if distance > radius_km:
            continue
        row = dict(stored)
        row["distance_km"] = distance
        tags["source"] = "bundled_osm_snapshot"
        row["tags"] = tags
        nearby.append(row)
    nearby.sort(key=lambda store: float(store.get("distance_km", 0.0)))
    return nearby


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


def _http_get_json(url: str, timeout_seconds: int = 5) -> Any:
    req = Request(
        url=url,
        headers={
            "User-Agent": "grocery-optimizer/0.3 (postal area discovery)",
            "Accept": "application/json",
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
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None


def geocode_postal_code(postal_code: str, country_hint: str = "") -> GeoPoint | None:
    normalized = postal_code.upper().replace(" ", "")

    # Check in-memory cache first (covers both local hits and prior Nominatim results).
    cache_key = f"{normalized}|{country_hint}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    local_codes = load_postal_codes()
    if normalized in local_codes:
        item = local_codes[normalized]
        result = GeoPoint(
            latitude=item.latitude,
            longitude=item.longitude,
            display_name=f"{item.city}, {item.province_state}",
            country_code=item.country.lower(),
        )
        _geocode_cache[cache_key] = result
        return result

    # Fallback to Nominatim (no API key needed, usage policy applies)
    query = normalized
    if country_hint:
        query = f"{query}, {country_hint}"
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={quote(query)}&format=json&addressdetails=1&limit=1"
    )
    payload = _http_get_json(url)
    if not payload or not isinstance(payload, list):
        _geocode_cache[cache_key] = None
        return None
    if not payload:
        _geocode_cache[cache_key] = None
        return None

    first = payload[0]
    lat = first.get("lat")
    lon = first.get("lon")
    if lat is None or lon is None:
        _geocode_cache[cache_key] = None
        return None

    address = first.get("address", {})
    country_code = str(address.get("country_code", "")).lower()
    display_name = str(first.get("display_name", normalized))

    try:
        result = GeoPoint(
            latitude=float(lat),
            longitude=float(lon),
            display_name=display_name,
            country_code=country_code,
        )
        _geocode_cache[cache_key] = result
        return result
    except ValueError:
        _geocode_cache[cache_key] = None
        return None


def geocode_address(address: str, country_hint: str = "") -> GeoPoint | None:
    query = address.strip()
    if not query:
        return None

    if country_hint:
        query = f"{query}, {country_hint}"

    # Check cache (same cache as postal code geocoding)
    cache_key = f"addr|{query.lower()}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={quote(query)}&format=json&addressdetails=1&limit=1"
    )
    payload = _http_get_json(url)
    if not payload or not isinstance(payload, list) or not payload:
        _geocode_cache[cache_key] = None
        return None

    first = payload[0]
    lat = first.get("lat")
    lon = first.get("lon")
    if lat is None or lon is None:
        _geocode_cache[cache_key] = None
        return None

    address_payload = first.get("address", {})
    country_code = str(address_payload.get("country_code", "")).lower()
    display_name = str(first.get("display_name", query))

    try:
        result = GeoPoint(
            latitude=float(lat),
            longitude=float(lon),
            display_name=display_name,
            country_code=country_code,
        )
        _geocode_cache[cache_key] = result
        return result
    except ValueError:
        _geocode_cache[cache_key] = None
        return None


def _infer_price_tier_from_name(name: str) -> str:
    lower = name.lower()
    premium_keys = ["whole foods", "erewhon", "organic", "gourmet", "premium"]
    budget_keys = ["aldi", "maxi", "super c", "no frills", "dollar", "discount", "food 4 less"]

    if any(k in lower for k in premium_keys):
        return "premium"
    if any(k in lower for k in budget_keys):
        return "budget"
    return "mid"


def _infer_quality_rating(tags: dict[str, Any]) -> float:
    brand = str(tags.get("brand", "")).strip()
    opening_hours = str(tags.get("opening_hours", "")).strip()
    organic = str(tags.get("organic", "")).lower() in {"yes", "true"}

    base = 3.5
    if brand:
        base += 0.2
    if opening_hours:
        base += 0.1
    if organic:
        base += 0.2

    return max(2.5, min(round(base, 1), 4.9))


def _normalize_store_name(raw_name: str) -> str:
    cleaned = raw_name.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Food Store"


def discover_food_places(
    postal_code: str,
    radius_km: float = 12.0,
    country_hint: str = "",
) -> dict[str, Any]:
    # Check discovery cache first.
    disc_key = f"{postal_code.upper().replace(' ', '')}|{radius_km}|{country_hint}"
    if disc_key in _discovery_cache:
        return _discovery_cache[disc_key]

    point = geocode_postal_code(postal_code, country_hint=country_hint)
    if not point:
        return {
            "origin": None,
            "stores": [],
            "count": 0,
            "source": "osm_overpass",
            "detail": "Postal code geocoding failed.",
            "scanned_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    radius_m = int(max(1000, min(radius_km * 1000, 25000)))
    query = f"""
[out:json][timeout:25];
(
  node["shop"~"supermarket|grocery|greengrocer|health_food|wholesale"](around:{radius_m},{point.latitude},{point.longitude});
  way["shop"~"supermarket|grocery|greengrocer|health_food|wholesale"](around:{radius_m},{point.latitude},{point.longitude});
  relation["shop"~"supermarket|grocery|greengrocer|health_food|wholesale"](around:{radius_m},{point.latitude},{point.longitude});
  node["shop"="department_store"]["name"~"Walmart|Giant Tiger|Tigre Géant",i](around:{radius_m},{point.latitude},{point.longitude});
  way["shop"="department_store"]["name"~"Walmart|Giant Tiger|Tigre Géant",i](around:{radius_m},{point.latitude},{point.longitude});
  relation["shop"="department_store"]["name"~"Walmart|Giant Tiger|Tigre Géant",i](around:{radius_m},{point.latitude},{point.longitude});
  node["amenity"="marketplace"](around:{radius_m},{point.latitude},{point.longitude});
);
out center tags;
""".strip()

    payload: Any = None
    provider = ""
    encoded_query = quote(query)
    for endpoint in _OVERPASS_ENDPOINTS:
        candidate = _http_get_json(endpoint + encoded_query, timeout_seconds=4)
        if (
            isinstance(candidate, dict)
            and isinstance(candidate.get("elements"), list)
            and candidate["elements"]
        ):
            payload = candidate
            provider = endpoint.split("/api/", 1)[0]
            break

    if not payload or not isinstance(payload, dict):
        # Graceful fallback: use the bundled map snapshot and curated catalog.
        fallback_stores = _nearby_snapshot_stores(point, radius_km)
        seen_locations = {
            (
                str(store.get("name", "")).lower(),
                round(float(store.get("latitude", 0.0)), 4),
                round(float(store.get("longitude", 0.0)), 4),
            )
            for store in fallback_stores
        }
        for store in load_stores():
            distance = calculate_distance_km(point.latitude, point.longitude, store.latitude, store.longitude)
            if distance <= radius_km:
                location_key = (store.name.lower(), round(store.latitude, 4), round(store.longitude, 4))
                if location_key in seen_locations:
                    continue
                seen_locations.add(location_key)
                fallback_stores.append(
                    {
                        "store_id": store.store_id,
                        "name": store.name,
                        "chain": store.chain,
                        "address": store.address,
                        "distance_km": distance,
                        "price_tier": store.price_tier,
                        "quality_rating": store.quality_rating,
                        "location_id": store.location_id,
                        "latitude": round(float(store.latitude), 6),
                        "longitude": round(float(store.longitude), 6),
                        "tags": {"source": "local_config"},
                    }
                )

        fallback_stores.sort(key=lambda s: s["distance_km"])
        used_snapshot = any(
            isinstance(store.get("tags"), dict)
            and store["tags"].get("source") == "bundled_osm_snapshot"
            for store in fallback_stores
        )
        fallback_result = {
            "origin": {
                "postal_code": postal_code,
                "display_name": point.display_name,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "country_code": point.country_code.upper(),
            },
            "stores": fallback_stores,
            "count": len(fallback_stores),
            "source": "bundled_osm_snapshot" if used_snapshot else "local_config_fallback",
            "detail": (
                "Live area scan unavailable. Used the bundled OpenStreetMap location snapshot."
                if used_snapshot
                else "Area scan service unavailable. Used local store catalog fallback."
            ),
            "scanned_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        return fallback_result

    payload_dict = cast(dict[str, Any], payload)
    elements = payload_dict.get("elements", [])
    stores: list[dict[str, Any]] = []

    for el in elements:
        if not isinstance(el, dict):
            continue
        tags = el.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}
        raw_name = str(tags.get("name", "")).strip()
        if not raw_name:
            continue

        lat = el.get("lat")
        lon = el.get("lon")
        center = el.get("center", {})
        if lat is None:
            lat = center.get("lat")
        if lon is None:
            lon = center.get("lon")
        if lat is None or lon is None:
            continue

        name = _normalize_store_name(raw_name)
        if not _is_grocery_location(name, cast(dict[str, Any], tags)):
            continue
        chain = str(tags.get("brand", name)).strip() or name
        distance = calculate_distance_km(point.latitude, point.longitude, float(lat), float(lon))
        street = str(tags.get("addr:street", "")).strip()
        house = str(tags.get("addr:housenumber", "")).strip()
        city = str(tags.get("addr:city", "")).strip()
        address = " ".join(x for x in [house, street] if x)
        if city:
            address = f"{address}, {city}" if address else city
        if not address:
            address = "Address unavailable"

        store_id = sha1(f"{name}|{lat}|{lon}".encode()).hexdigest()[:12]

        stores.append(
            {
                "store_id": f"scan-{store_id}",
                "name": name,
                "chain": chain,
                "address": address,
                "distance_km": distance,
                "price_tier": _infer_price_tier_from_name(name),
                "quality_rating": _infer_quality_rating(tags),
                "location_id": "auto-discovered",
                "latitude": round(float(lat), 6),
                "longitude": round(float(lon), 6),
                "tags": {
                    "shop": tags.get("shop", ""),
                    "amenity": tags.get("amenity", ""),
                    "brand": tags.get("brand", ""),
                },
            }
        )

    # Deduplicate by (name, rounded lat/lon)
    seen: set[tuple[str, float, float]] = set()
    deduped: list[dict[str, Any]] = []
    for store in sorted(stores, key=lambda s: s["distance_km"]):
        key = (store["name"].lower(), round(store["latitude"], 4), round(store["longitude"], 4))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(store)

    result = {
        "origin": {
            "postal_code": postal_code.upper().replace(" ", ""),
            "display_name": point.display_name,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "country_code": point.country_code.upper(),
        },
        "stores": deduped,
        "count": len(deduped),
        "source": "osm_overpass",
        "provider": provider,
        "detail": "ok",
        "scanned_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    if deduped:
        _discovery_cache[disc_key] = result
    return result
