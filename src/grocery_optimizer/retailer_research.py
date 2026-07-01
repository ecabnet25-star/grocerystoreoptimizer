from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=16)
def load_retailer_research(location_id: str, base_dir: str | Path = "config/retailer_research") -> dict[str, Any]:
    """Load retailer research metadata for a supported market."""
    safe_location = location_id.strip().lower().replace(" ", "-")
    path = Path(base_dir) / f"{safe_location}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def summarize_retailer_research(location_id: str) -> dict[str, Any]:
    research = load_retailer_research(location_id)
    if not research:
        return {}

    priority = research.get("priority_retailers", [])
    tiers = research.get("acquisition_tiers", [])
    seeds = research.get("verified_store_seeds", [])
    useful = research.get("useful", [])
    not_useful = research.get("not_useful_for_direct_build", [])

    return {
        "location_id": research.get("location_id", location_id),
        "compiled_at": research.get("compiled_at", ""),
        "purpose": research.get("purpose", ""),
        "top_priority_retailers": priority[:6] if isinstance(priority, list) else [],
        "acquisition_tiers": tiers if isinstance(tiers, list) else [],
        "verified_seed_count": len(seeds) if isinstance(seeds, list) else 0,
        "useful_categories": useful if isinstance(useful, list) else [],
        "deferred_categories": not_useful if isinstance(not_useful, list) else [],
        "launch_tasks": research.get("launch_tasks_from_workbook", []),
    }
