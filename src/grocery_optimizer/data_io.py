from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import GroceryItem


@lru_cache(maxsize=4)
def _load_items_cached(path_str: str) -> tuple[GroceryItem, ...]:
    source = Path(path_str)
    payload = json.loads(source.read_text(encoding="utf-8"))

    items: list[GroceryItem] = []
    for raw_item in payload.get("items", []):
        items.append(
            GroceryItem(
                name=raw_item["name"],
                category=raw_item["category"],
                price=float(raw_item["price"]),
                nutrition_score=float(raw_item["nutrition_score"]),
                shelf_life_days=int(raw_item["shelf_life_days"]),
                quantity=int(raw_item.get("quantity", 1)),
            )
        )
    return tuple(items)


def load_items_from_json(path: str | Path) -> list[GroceryItem]:
    return list(_load_items_cached(str(path)))
