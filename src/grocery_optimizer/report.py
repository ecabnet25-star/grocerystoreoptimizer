from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import OptimizationResult


def _as_payload(result: OptimizationResult, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "metadata": metadata or {},
        "strategy": result.strategy,
        "summary": {
            "total_cost": result.total_cost,
            "budget_remaining": result.budget_remaining,
            "total_nutrition_score": result.total_nutrition_score,
            "total_shelf_life_days": result.total_shelf_life_days,
            "total_utility_score": result.total_utility_score,
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
            }
            for item in result.selected_items
        ],
    }


def write_report_json(
    path: str | Path,
    result: OptimizationResult,
    metadata: dict[str, Any] | None = None,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_as_payload(result, metadata=metadata), indent=2), encoding="utf-8")


def write_report_csv(path: str | Path, result: OptimizationResult) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "name",
                "category",
                "price",
                "quantity",
                "total_cost",
                "nutrition_score",
                "shelf_life_days",
            ]
        )
        for item in result.selected_items:
            writer.writerow(
                [
                    item.name,
                    item.category,
                    f"{item.price:.2f}",
                    item.quantity,
                    f"{item.total_cost:.2f}",
                    f"{item.nutrition_score:.2f}",
                    item.shelf_life_days,
                ]
            )
