import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from grocery_optimizer.live_pricing.deals import load_verified_deals


def test_verified_deals_filter_and_sort(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    payload = {
        "schema_version": 2,
        "generated_at_utc": now.isoformat(),
        "source": "test",
        "diagnostics": {"configured_chains": ["Metro", "IGA"]},
        "quotes": [
            {
                "item_name": "Romaine Hearts",
                "item_category": "produce",
                "product_name": "Romaine Hearts 3 Pack",
                "store_chain": "Metro",
                "postal_code": "H3A1A1",
                "unit_price": 2.99,
                "regular_price": 4.99,
                "on_sale": True,
                "source_type": "flyer_aggregator",
                "source_url": "https://example.com/romaine",
                "fetched_at_utc": now.isoformat(),
                "valid_to_utc": (now + timedelta(days=3)).isoformat(),
            },
            {
                "item_name": "Spinach",
                "item_category": "produce",
                "product_name": "Spinach 312 g",
                "store_chain": "Metro",
                "postal_code": "H3A1A1",
                "unit_price": 3.99,
                "regular_price": 4.49,
                "on_sale": True,
                "source_type": "flyer_aggregator",
                "source_url": "https://example.com/spinach",
                "fetched_at_utc": now.isoformat(),
                "valid_to_utc": (now + timedelta(days=3)).isoformat(),
            },
        ],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = load_verified_deals(snapshot_path=path, postal_code="H3A 1A1", category="produce")
    assert result["count"] == 2
    assert result["deals"][0]["item_name"] == "Romaine Hearts"
    assert result["deals"][0]["savings_amount"] == 2.0
    assert result["coverage"][1]["status"] == "no_current_matches"
