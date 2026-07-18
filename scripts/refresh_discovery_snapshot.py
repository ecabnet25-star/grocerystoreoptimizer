from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_GROCERY_SHOP_TYPES = {"supermarket", "grocery", "greengrocer", "health_food", "wholesale"}
_GROCERY_DEPARTMENT_STORE_NAMES = ("walmart", "giant tiger", "tigre géant")


def _is_grocery_location(store: dict[str, object]) -> bool:
    raw_tags = store.get("tags", {})
    tags = raw_tags if isinstance(raw_tags, dict) else {}
    shop_types = {part.strip() for part in str(tags.get("shop", "")).lower().split(";") if part.strip()}
    if shop_types & _GROCERY_SHOP_TYPES:
        return True
    name = str(store.get("name", "")).lower()
    if "department_store" in shop_types and any(chain in name for chain in _GROCERY_DEPARTMENT_STORE_NAMES):
        return True
    return str(tags.get("amenity", "")).lower() == "marketplace"


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh a bundled grocery-location discovery snapshot.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--postal-code", required=True)
    parser.add_argument("--radius-km", type=float, default=12.0)
    parser.add_argument("--location-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    query = urlencode({"postal_code": args.postal_code, "radius_km": args.radius_km})
    request = Request(
        f"{args.api_url.rstrip('/')}/area/scan?{query}",
        headers={"Accept": "application/json", "User-Agent": "unibite-snapshot-refresh/1.0"},
    )
    with urlopen(request, timeout=45) as response:  # noqa: S310 - operator-supplied API URL
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("source") != "osm_overpass" or not payload.get("stores"):
        detail = payload.get("detail", "No live stores returned")
        raise RuntimeError(f"Refusing to replace snapshot with fallback data: {detail}")

    output = args.output or Path("config/discovery_snapshots") / f"{args.location_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    grocery_stores = [store for store in payload["stores"] if isinstance(store, dict) and _is_grocery_location(store)]
    snapshot = {
        "location_id": args.location_id,
        "postal_code": args.postal_code.upper().replace(" ", ""),
        "radius_km": args.radius_km,
        "source": payload.get("source"),
        "provider": payload.get("provider"),
        "attribution": "OpenStreetMap contributors",
        "license": "ODbL 1.0",
        "license_url": "https://www.openstreetmap.org/copyright",
        "captured_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "stores": grocery_stores,
    }
    output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshot['stores'])} stores to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
