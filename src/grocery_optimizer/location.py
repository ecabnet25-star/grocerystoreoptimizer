from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .models import GroceryItem


@dataclass(frozen=True)
class LocationProfile:
    location_id: str
    display_name: str
    currency: str
    price_multiplier: float
    category_price_multipliers: dict[str, float]
    supported_postal_prefixes: list[str]
    stores: list[str]


def normalize_location_id(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


@lru_cache(maxsize=8)
def _load_location_cached(normalized: str, base_dir_str: str) -> LocationProfile:
    path = Path(base_dir_str) / f"{normalized}.json"
    if not path.exists():
        raise FileNotFoundError(f"Location profile not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return LocationProfile(
        location_id=payload["location_id"],
        display_name=payload["display_name"],
        currency=payload.get("currency", "CAD"),
        price_multiplier=float(payload.get("price_multiplier", 1.0)),
        category_price_multipliers={
            str(k): float(v) for k, v in payload.get("category_price_multipliers", {}).items()
        },
        supported_postal_prefixes=[str(x) for x in payload.get("supported_postal_prefixes", [])],
        stores=[str(x) for x in payload.get("stores", [])],
    )


def load_location_profile(location_id: str, base_dir: str | Path = "config/locations") -> LocationProfile:
    normalized = normalize_location_id(location_id)
    return _load_location_cached(normalized, str(base_dir))


def apply_location_pricing(items: list[GroceryItem], profile: LocationProfile) -> list[GroceryItem]:
    adjusted: list[GroceryItem] = []

    for item in items:
        category_multiplier = profile.category_price_multipliers.get(item.category, 1.0)
        adjusted_price = round(item.price * profile.price_multiplier * category_multiplier, 2)
        adjusted.append(
            GroceryItem(
                name=item.name,
                category=item.category,
                price=adjusted_price,
                nutrition_score=item.nutrition_score,
                shelf_life_days=item.shelf_life_days,
                quantity=item.quantity,
                package_size=item.package_size,
                package_unit=item.package_unit,
                package_label=item.package_label,
            )
        )

    return adjusted


def list_available_locations(base_dir: str | Path = "config/locations") -> list[str]:
    root = Path(base_dir)
    if not root.exists():
        return []
    return sorted(path.stem for path in root.glob("*.json"))
