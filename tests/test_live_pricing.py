import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

# pyright: reportPrivateUsage=false
from grocery_optimizer.live_pricing import (
    _extract_flipp_price,
    _parse_deal_unit_price,
    parsing,
    storage,
)
from grocery_optimizer.live_pricing.providers import RetailerCatalogProvider


class _ClosableResponseBody:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestLivePricingParsing(unittest.TestCase):
    def test_vercel_uses_writable_tmp_price_history(self):
        with patch.dict("os.environ", {"VERCEL": "1"}, clear=False):
            self.assertEqual(storage._default_price_db_path(), "/tmp/grocery_optimizer_live_pricing.db")

    def test_parse_deal_two_for_price(self):
        self.assertEqual(_parse_deal_unit_price("2/$5"), 2.5)
        self.assertEqual(_parse_deal_unit_price("3 for $9"), 3.0)

    def test_parse_deal_unit_text(self):
        self.assertEqual(_parse_deal_unit_price("$1.99/lb"), 1.99)
        self.assertEqual(_parse_deal_unit_price("2.49 ea"), 2.49)

    def test_extract_flipp_price_from_variant_payload(self):
        payload: dict[str, object] = {
            "response": {
                "data": [
                    {
                        "merchant_name": "Metro",
                        "title": "Bananas",
                        "deal_text": "2/$5",
                    },
                    {
                        "merchant_name": "Other",
                        "title": "Bananas",
                        "price": 9.99,
                    },
                ]
            }
        }

        value = _extract_flipp_price(
            payload=payload,
            item_name="Bananas",
            store_chain="Metro",
            fallback_price_path="results.0.price",
        )

        self.assertEqual(value, 2.5)

    def test_http_json_closes_http_error_response_body(self):
        response_body = _ClosableResponseBody()
        error = HTTPError(
            url="https://example.invalid",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=response_body,
        )

        with patch("grocery_optimizer.live_pricing.parsing.urlopen", side_effect=error):
            value = parsing._http_json("https://example.invalid")

        self.assertIsNone(value)
        self.assertTrue(response_body.closed)

    def test_live_quote_save_is_best_effort_when_database_locked(self):
        class LockedConnection:
            def execute(self, *_args, **_kwargs):
                raise storage.sqlite3.OperationalError("database is locked")

            def commit(self):
                return None

        with patch("grocery_optimizer.live_pricing.storage.sqlite3.connect", return_value=LockedConnection()):
            with patch.dict("os.environ", {"GROCERY_LIVE_PRICING_DB": "locked-test.db"}):
                storage._thread_local.conn = None
                storage._thread_local.path = None
                storage._thread_local.initialized = False
                storage.save_live_quote(
                    provider_id="fallback",
                    item_name="Rice",
                    store_chain="Store",
                    postal_code="H3A1A1",
                    country="CA",
                    currency="CAD",
                    unit_price=1.23,
                    confidence=0.5,
                    fetched_at_utc="2026-05-21T00:00:00Z",
                    source_url="fallback:test",
                )

    def test_retailer_catalog_provider_extracts_matching_product(self):
        provider = RetailerCatalogProvider(
            {
                "id": "retailer_catalog_test",
                "type": "retailer_catalog",
                "enabled": True,
                "base_url": "https://retailer.example/search",
                "query": {"q": "{item_name}", "store": "{store_chain}"},
                "result_list_path": "products",
                "item_name_path": "title",
                "store_chain_path": "merchant",
                "price_path": "price.amount",
                "currency_path": "price.currency",
            },
            timeout_seconds=2,
        )
        payload = {
            "products": [
                {"title": "Bananas bunch", "merchant": "Metro", "price": {"amount": "1.99", "currency": "CAD"}}
            ]
        }

        with patch("grocery_optimizer.live_pricing.providers.urlopen", return_value=_JsonResponse(payload)):
            quote = provider.fetch_price(
                item_name="Bananas",
                item_category="produce",
                base_unit_price=2.5,
                store_chain="Metro",
                store_price_tier="mid",
                postal_code="H3A1A1",
                country="CA",
                currency_hint="CAD",
            )

        self.assertIsNotNone(quote)
        self.assertEqual(quote.unit_price, 1.99)
        self.assertEqual(quote.currency, "CAD")


if __name__ == "__main__":
    unittest.main()
