from datetime import UTC, datetime

from grocery_optimizer.live_pricing.flipp import chain_matches, item_match_score, parse_flipp_quotes
from grocery_optimizer.unit_pricing import normalized_unit_price, parse_package_size


def test_package_size_and_normalized_unit_price() -> None:
    size, unit, label = parse_package_size("Greek yogurt 750 g")
    assert (size, unit, label) == (750.0, "g", "750 g")
    assert normalized_unit_price(6.0, size, unit) == (0.8, "100 g")
    assert normalized_unit_price(5.88, 1, "lb") == (1.2963, "100 g")


def test_product_identity_rejects_processed_lookalikes() -> None:
    assert item_match_score("Brown Rice", "Brown Rice Chips BBQ") < 0.72
    assert item_match_score("Chicken Breast", "Fresh boneless skinless chicken breasts") >= 0.72
    assert item_match_score("Chicken Breast", "Smoked deli chicken breast slices") < 0.72
    assert item_match_score("Eggs", "Made Foods Egg Salad Wedge") < 0.72
    assert item_match_score("Peanut Butter", "Tasc Peanut Butter Bird House") == 0
    assert item_match_score("Peanut Butter", "SLIMYGLOOP Chunky Peanut Butter") == 0
    assert item_match_score("Peanut Butter", "ONE REESE'S Peanut Butter") < 0.72
    assert item_match_score("Quinoa", "Lekue Quinoa And Rice Cooker Green") == 0
    assert item_match_score("Quinoa", "Promise Gluten Free Quinoa & Chia Loaf") < 0.72
    assert item_match_score("Quinoa", "Country Harvest Flax & Quinoa Sliced Bread") < 0.72
    assert item_match_score("Olive Oil", "Becel With Olive Oil 400g") < 0.72
    assert item_match_score("Olive Oil", "Gabriel Sardines In Olive Oil 120") < 0.72
    assert item_match_score("Olive Oil", "Great Value Canola Olive Oil Blend 1 L") < 0.72
    assert item_match_score("Milk", "Grace coconut milk") < 0.72
    assert item_match_score("Milk", "Cedar Sweetened Condensed Milk") < 0.72
    assert item_match_score("Sweet Potatoes", "Baby sweet potatoes puree pouch") < 0.72
    assert item_match_score("Peanut Butter", "Nature Valley Crunchy Peanut Butter 210g") == 0


def test_distinct_loblaw_banners_do_not_match() -> None:
    assert not chain_matches("Maxi", "Provigo")
    assert chain_matches("PA", "Supermarche PA")
    assert chain_matches("Super C", "Super C")


def test_flipp_parser_handles_multi_buy_and_validity() -> None:
    payload = {
        "items": [
            {
                "name": "Romaine Hearts 3 Pack",
                "merchant_name": "Supermarche PA",
                "current_price": 4,
                "original_price": 6,
                "pre_price_text": "2/",
                "valid_from": "2026-07-16T00:00:00Z",
                "valid_to": "2026-07-22T23:59:59Z",
                "flyer_item_id": "romaine-pa",
            }
        ]
    }
    quotes = parse_flipp_quotes(
        payload,
        requested_item="Romaine Hearts",
        requested_chain="PA",
        item_category="produce",
        source_url="https://example.com/search",
        now=datetime(2026, 7, 18, tzinfo=UTC),
    )
    assert len(quotes) == 1
    assert quotes[0]["unit_price"] == 2.0
    assert quotes[0]["offer_quantity"] == 2
    assert quotes[0]["normalized_unit_price"] == 0.6667
    assert quotes[0]["normalized_unit_basis"] == "unit"


def test_flipp_parser_rejects_liquid_result_for_fresh_produce() -> None:
    payload = {
        "ecom_items": [
            {
                "name": "E-Bggr Banana 200ml",
                "merchant_name": "Walmart",
                "current_price": 8.97,
                "original_price": 9.97,
                "item_id": "not-produce",
            }
        ]
    }
    assert not parse_flipp_quotes(
        payload,
        requested_item="Bananas",
        requested_chain="Walmart",
        item_category="produce",
        now=datetime(2026, 7, 18, tzinfo=UTC),
    )
