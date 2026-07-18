from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_current_snapshot_contract_and_chain_coverage() -> None:
    snapshot = _json("config/live_pricing/snapshots/latest.json")
    generated = datetime.fromisoformat(snapshot["generated_at_utc"].replace("Z", "+00:00"))
    quotes = snapshot["quotes"]

    assert snapshot["schema_version"] == 2
    assert generated >= datetime.now(UTC) - timedelta(hours=50)
    assert len(quotes) >= 100
    assert len({quote["store_chain"] for quote in quotes}) >= 6
    assert {quote["source_type"] for quote in quotes} <= {"flyer_aggregator", "retailer_ecommerce"}
    assert all(quote.get("source_url") and quote.get("fetched_at_utc") for quote in quotes)
    assert all(quote.get("product_name") and quote.get("postal_code") for quote in quotes)
    rejected_product_phrases = {
        "bird house",
        "condensed milk",
        "coconut milk",
        "quinoa and rice cooker",
        "slimygloop",
        "sweet potatoes puree",
    }
    assert all(
        not any(phrase in quote["product_name"].lower() for phrase in rejected_product_phrases)
        for quote in quotes
    )


def test_public_verified_pricing_is_the_only_enabled_live_path() -> None:
    config = _json("config/live_pricing/providers.json")
    enabled = {provider["id"] for provider in config["providers"] if provider.get("enabled")}

    assert enabled == {"verified_flipp_snapshot", "flipp_public_current"}
    assert all(
        not provider.get("enabled")
        for provider in config["providers"]
        if provider["id"] in {"public_market_benchmark", "flipp_us_ca_partner", "public_flyer_ocr_pipeline"}
    )


def test_catalog_is_diverse_and_unit_comparable() -> None:
    items = _json("config/catalog.json")["items"]

    assert len(items) >= 30
    assert {item["category"] for item in items} >= {"produce", "protein", "grains", "dairy", "pantry"}
    assert all(item.get("package_size") and item.get("package_unit") and item.get("package_label") for item in items)


def test_pa_du_fort_seed_is_exact() -> None:
    stores = _json("config/stores/montreal.json")["stores"]
    pa_du_fort = next(store for store in stores if store["store_id"] == "pa-du-fort-mtl")

    assert pa_du_fort["address"] == "1420 Rue du Fort, Montreal, QC H3H 2C2"
    assert abs(pa_du_fort["latitude"] - 45.492147) < 0.000001
    assert abs(pa_du_fort["longitude"] - (-73.582181)) < 0.000001


def test_frontend_keeps_workbook_truthfulness_guards() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    script = (ROOT / "web/plan.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/styles.css").read_text(encoding="utf-8")

    assert 'id="locationQuery"' in html
    assert 'id="mustHaveItems"' in html
    assert "Sample balanced allocation" in html
    assert "Dairy / alternatives" in html
    assert "Congratulations" not in html + script
    assert 'data-label="${itemTableLabels[0]}"' in script
    assert "savings_is_verified" in script
    assert "bodyScroll" not in script
    assert "grid-template-columns: minmax(0, 1fr);" in styles


def test_resolution_document_covers_every_workbook_id() -> None:
    resolution = (ROOT / "docs/unibite-workbook-resolution.md").read_text(encoding="utf-8")

    for issue_number in range(1, 19):
        assert f"Q{issue_number:03d}" in resolution
