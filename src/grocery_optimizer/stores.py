from __future__ import annotations

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Store:
    """Represents a grocery store with location and pricing information."""
    store_id: str
    name: str
    chain: str
    address: str
    postal_code: str
    latitude: float
    longitude: float
    price_tier: str  # budget, mid, premium
    quality_rating: float  # 1.0 to 5.0
    location_id: str  # montreal, toronto, etc.


@dataclass(frozen=True)
class PostalCodeInfo:
    """Postal code geographic information."""
    postal_code: str
    latitude: float
    longitude: float
    city: str
    province_state: str
    country: str


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return round(R * c, 2)


@lru_cache(maxsize=1)
def _load_stores_cached(base_dir: str) -> tuple[Store, ...]:
    """Load all stores from JSON files (cached, returns immutable tuple)."""
    root = Path(base_dir)
    if not root.exists():
        return ()

    stores = []
    for path in root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for store_data in payload.get("stores", []):
            stores.append(Store(
                store_id=store_data["store_id"],
                name=store_data["name"],
                chain=store_data["chain"],
                address=store_data["address"],
                postal_code=store_data["postal_code"],
                latitude=float(store_data["latitude"]),
                longitude=float(store_data["longitude"]),
                price_tier=store_data.get("price_tier", "mid"),
                quality_rating=float(store_data.get("quality_rating", 3.5)),
                location_id=store_data["location_id"],
            ))

    return tuple(stores)


def load_stores(base_dir: str | Path = "config/stores") -> list[Store]:
    """Load all stores from JSON files."""
    return list(_load_stores_cached(str(base_dir)))


@lru_cache(maxsize=1)
def _load_postal_codes_cached(base_dir: str) -> tuple[tuple[str, PostalCodeInfo], ...]:
    """Load postal code lookup data (cached, returns immutable tuple of pairs)."""
    root = Path(base_dir)
    if not root.exists():
        return ()

    postal_codes = {}
    for path in root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for pc_data in payload.get("postal_codes", []):
            pc = pc_data["postal_code"]
            postal_codes[pc] = PostalCodeInfo(
                postal_code=pc,
                latitude=float(pc_data["latitude"]),
                longitude=float(pc_data["longitude"]),
                city=pc_data["city"],
                province_state=pc_data["province_state"],
                country=pc_data["country"],
            )

    return tuple(postal_codes.items())


def load_postal_codes(base_dir: str | Path = "config/postal_codes") -> dict[str, PostalCodeInfo]:
    """Load postal code lookup data."""
    return dict(_load_postal_codes_cached(str(base_dir)))


def find_nearby_stores(
    postal_code: str,
    stores: list[Store],
    postal_codes: dict[str, PostalCodeInfo],
    max_distance_km: float = 20.0,
) -> list[tuple[Store, float]]:
    """Find stores near a postal code, returning (store, distance_km) tuples."""
    pc_info = postal_codes.get(postal_code.upper().replace(" ", ""))
    if not pc_info:
        return []
    
    nearby = []
    for store in stores:
        distance = calculate_distance_km(
            pc_info.latitude, pc_info.longitude,
            store.latitude, store.longitude
        )
        if distance <= max_distance_km:
            nearby.append((store, distance))
    
    # Sort by distance
    nearby.sort(key=lambda x: x[1])
    return nearby


def find_nearby_stores_from_coordinates(
    latitude: float,
    longitude: float,
    stores: list[Store],
    max_distance_km: float = 20.0,
) -> list[tuple[Store, float]]:
    """Find stores near arbitrary coordinates, returning (store, distance_km) tuples."""
    nearby = []
    for store in stores:
        distance = calculate_distance_km(latitude, longitude, store.latitude, store.longitude)
        if distance <= max_distance_km:
            nearby.append((store, distance))
    nearby.sort(key=lambda x: x[1])
    return nearby


def optimize_route(stores: list[Store], origin: PostalCodeInfo) -> list[tuple[Store, float, int]]:
    """
    Simple nearest-neighbor route optimization.
    Returns list of (store, distance_from_previous, order) tuples.
    """
    if not stores:
        return []
    
    route = []
    remaining = list(stores)
    current_lat, current_lon = origin.latitude, origin.longitude
    order = 1
    
    # Start from origin to first store
    distances = [
        (store, calculate_distance_km(current_lat, current_lon, store.latitude, store.longitude))
        for store in remaining
    ]
    distances.sort(key=lambda x: x[1])
    first_store, first_dist = distances[0]
    route.append((first_store, first_dist, order))
    remaining.remove(first_store)
    current_lat, current_lon = first_store.latitude, first_store.longitude
    order += 1
    
    # Visit remaining stores using nearest neighbor
    while remaining:
        distances = [
            (store, calculate_distance_km(current_lat, current_lon, store.latitude, store.longitude))
            for store in remaining
        ]
        distances.sort(key=lambda x: x[1])
        next_store, next_dist = distances[0]
        route.append((next_store, next_dist, order))
        remaining.remove(next_store)
        current_lat, current_lon = next_store.latitude, next_store.longitude
        order += 1
    
    return route


def optimize_route_from_coordinates(
    stores: list[Store],
    origin_latitude: float,
    origin_longitude: float,
) -> list[tuple[Store, float, int]]:
    """Nearest-neighbor route optimization starting from custom coordinates."""
    if not stores:
        return []

    route = []
    remaining = list(stores)
    current_lat, current_lon = origin_latitude, origin_longitude
    order = 1

    while remaining:
        distances = [
            (store, calculate_distance_km(current_lat, current_lon, store.latitude, store.longitude))
            for store in remaining
        ]
        distances.sort(key=lambda x: x[1])
        next_store, next_dist = distances[0]
        route.append((next_store, next_dist, order))
        remaining.remove(next_store)
        current_lat, current_lon = next_store.latitude, next_store.longitude
        order += 1

    return route


def get_price_tier_multiplier(tier: str) -> float:
    """Get price multiplier for store tier."""
    multipliers = {
        "budget": 0.85,
        "mid": 1.0,
        "premium": 1.25,
    }
    return multipliers.get(tier, 1.0)
