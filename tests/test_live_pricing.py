import json
import tempfile
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import patch
from urllib.error import HTTPError

# pyright: reportPrivateUsage=false
from grocery_optimizer.live_pricing import (
    _extract_flipp_price,
    _parse_deal_unit_price,
    parsing,
    storage,
)
from grocery_optimizer.live_pricing.cache import LivePriceQuote
from grocery_optimizer.live_pricing.engine import LivePricingEngine
from grocery_optimizer.live_pricing.providers import (
    BaseLiveProvider,
    LocalSnapshotProvider,
    ProviderHealth,
    RetailerCatalogProvider,
)


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _StubProvider(BaseLiveProvider):
    def __init__(self, config: dict[str, object], quote: LivePriceQuote | None):
        super().__init__(config, timeout_seconds=1)
        self.stub_quote = quote

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type=str(self.config.get("type", "unknown")),
            configured=True,
            detail="ready",
        )

    def fetch_price(
        self,
        item_name: str,
        item_category: str,
        base_unit_price: float,
        store_chain: str,
        store_price_tier: str,
        postal_code: str,
        country: str,
        currency_hint: str,
    ) -> LivePriceQuote | None:
        return self.stub_quote


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

    def test_extract_flipp_price_prefers_token_matched_record_over_first_result_path(self):
        payload: dict[str, object] = {
            "results": [{"merchant_name": "Not Metro", "title": "Other item", "price": 8.99}],
            "response": {
                "data": [
                    {
                        "merchant_name": "Metro",
                        "title": "Bananas",
                        "deal_text": "2/$5",
                    }
                ]
            },
        }

        value = _extract_flipp_price(
            payload=payload,
            item_name="Bananas",
            store_chain="Metro",
            fallback_price_path="results.0.price",
        )

        self.assertEqual(value, 2.5)

    def test_extract_flipp_price_rejects_low_signal_candidates(self):
        payload: dict[str, object] = {
            "results": [
                {
                    "merchant_name": "Unknown",
                    "title": "Unknown",
                    "price": 9.99,
                }
            ]
        }

        value = _extract_flipp_price(
            payload=payload,
            item_name="Bananas",
            store_chain="Metro",
            fallback_price_path="",
        )

        self.assertIsNone(value)

    def test_http_json_closes_http_error_response_body(self):
        response_body = BytesIO(b"service unavailable")
        error = HTTPError(
            url="https://example.invalid",
            code=503,
            msg="Service Unavailable",
            hdrs=Message(),
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

    def test_get_live_price_median_reads_recent_non_fallback_quotes(self):
        with patch.dict("os.environ", {"GROCERY_LIVE_PRICING_DB": ":memory:"}, clear=False):
            storage._thread_local.conn = None
            storage._thread_local.path = None
            storage._thread_local.initialized = False

            storage.save_live_quote(
                provider_id="flipp_us_ca_partner",
                item_name="Bananas",
                store_chain="Metro",
                postal_code="H3A1A1",
                country="CA",
                currency="CAD",
                unit_price=1.0,
                confidence=0.85,
                fetched_at_utc="2026-07-01T00:00:00Z",
                source_url="https://example.com/1",
            )
            storage.save_live_quote(
                provider_id="openfoodfacts_us_ca",
                item_name="Bananas",
                store_chain="Metro",
                postal_code="H3A1A1",
                country="CA",
                currency="CAD",
                unit_price=2.0,
                confidence=0.9,
                fetched_at_utc="2026-07-01T00:10:00Z",
                source_url="https://example.com/2",
            )
            storage.save_live_quote(
                provider_id="fallback",
                item_name="Bananas",
                store_chain="Metro",
                postal_code="H3A1A1",
                country="CA",
                currency="CAD",
                unit_price=99.0,
                confidence=0.0,
                fetched_at_utc="2026-07-01T00:20:00Z",
                source_url="fallback:tier_estimate",
            )

            median, count = storage.get_live_price_median(
                item_name="Bananas",
                store_chain="Metro",
                postal_code="H3A1A1",
                min_confidence=0.5,
                max_rows=20,
            )

            self.assertEqual(count, 2)
            self.assertEqual(median, 1.5)

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
        concrete_quote = cast(LivePriceQuote, quote)
        self.assertEqual(concrete_quote.unit_price, 1.99)
        self.assertEqual(concrete_quote.currency, "CAD")

    def test_engine_prefers_higher_scored_quote_over_first_hit(self):
        engine = LivePricingEngine(config_path="config/live_pricing/does-not-exist.json")

        open_quote = LivePriceQuote(
            provider_id="openfoodfacts_us_ca",
            item_name="Bananas",
            currency="CAD",
            unit_price=2.15,
            confidence=0.72,
            fetched_at_utc="2026-07-01T00:00:00Z",
            source_url="https://example.com/open",
        )
        flipp_quote = LivePriceQuote(
            provider_id="flipp_us_ca_partner",
            item_name="Bananas",
            currency="CAD",
            unit_price=1.95,
            confidence=0.82,
            fetched_at_utc="2026-07-01T00:00:00Z",
            source_url="https://example.com/flipp",
        )

        engine._providers = cast(
            list[BaseLiveProvider],
            [
            _StubProvider(
                {"id": "openfoodfacts_us_ca", "type": "openfoodfacts_partner", "enabled": True},
                open_quote,
            ),
            _StubProvider(
                {"id": "flipp_us_ca_partner", "type": "flipp_partner", "enabled": True},
                flipp_quote,
            ),
            ],
        )
        engine._provider_config_by_id = {
            "openfoodfacts_us_ca": {"id": "openfoodfacts_us_ca", "type": "openfoodfacts_partner"},
            "flipp_us_ca_partner": {"id": "flipp_us_ca_partner", "type": "flipp_partner"},
        }

        quote = engine.fetch_quote(
            item_name="Bananas",
            item_category="produce",
            base_unit_price=2.0,
            store_chain="Metro",
            store_price_tier="mid",
            postal_code="H3A1A1",
            country="CA",
            currency_hint="CAD",
        )

        self.assertIsNotNone(quote)
        selected = cast(LivePriceQuote, quote)
        self.assertEqual(selected.provider_id, "flipp_us_ca_partner")

    def test_engine_filters_implausible_outlier_quote(self):
        engine = LivePricingEngine(config_path="config/live_pricing/does-not-exist.json")

        outlier_quote = LivePriceQuote(
            provider_id="flipp_us_ca_partner",
            item_name="Milk",
            currency="CAD",
            unit_price=39.99,
            confidence=0.95,
            fetched_at_utc="2026-07-01T00:00:00Z",
            source_url="https://example.com/flipp",
        )

        engine._providers = cast(
            list[BaseLiveProvider],
            [
            _StubProvider(
                {"id": "flipp_us_ca_partner", "type": "flipp_partner", "enabled": True},
                outlier_quote,
            ),
            ],
        )
        engine._provider_config_by_id = {
            "flipp_us_ca_partner": {"id": "flipp_us_ca_partner", "type": "flipp_partner"},
        }

        quote = engine.fetch_quote(
            item_name="Milk",
            item_category="dairy",
            base_unit_price=4.0,
            store_chain="Metro",
            store_price_tier="mid",
            postal_code="H3A1A1",
            country="CA",
            currency_hint="CAD",
        )

        self.assertIsNone(quote)

    def test_engine_filters_history_outlier_quote(self):
        engine = LivePricingEngine(config_path="config/live_pricing/does-not-exist.json")

        quote = LivePriceQuote(
            provider_id="flipp_us_ca_partner",
            item_name="Milk",
            currency="CAD",
            unit_price=8.5,
            confidence=0.9,
            fetched_at_utc="2026-07-01T00:00:00Z",
            source_url="https://example.com/flipp",
        )

        engine._providers = cast(
            list[BaseLiveProvider],
            [
                _StubProvider(
                    {"id": "flipp_us_ca_partner", "type": "flipp_partner", "enabled": True},
                    quote,
                ),
            ],
        )
        engine._provider_config_by_id = {
            "flipp_us_ca_partner": {"id": "flipp_us_ca_partner", "type": "flipp_partner"},
        }
        engine.history_min_samples = 5
        engine.history_max_deviation_ratio = 1.8

        with patch("grocery_optimizer.live_pricing.engine.get_live_price_median", return_value=(2.5, 8)):
            selected = engine.fetch_quote(
                item_name="Milk",
                item_category="dairy",
                base_unit_price=4.0,
                store_chain="Metro",
                store_price_tier="mid",
                postal_code="H3A1A1",
                country="CA",
                currency_hint="CAD",
            )

        self.assertIsNone(selected)

    def test_local_snapshot_provider_returns_chain_specific_quote(self):
        snapshot_payload = {
            "generated_at_utc": "2026-07-16T00:00:00Z",
            "source": "free-scraper",
            "quotes": [
                {
                    "item_name": "Bananas",
                    "store_chain": "Metro",
                    "postal_code": "H3A1A1",
                    "currency": "CAD",
                    "unit_price": 1.99,
                    "confidence": 0.78,
                    "source_url": "https://example.com/metro",
                    "fetched_at_utc": "2026-07-16T00:00:00Z",
                },
                {
                    "item_name": "Bananas",
                    "store_chain": "IGA",
                    "postal_code": "H3A1A1",
                    "currency": "CAD",
                    "unit_price": 2.49,
                    "confidence": 0.77,
                    "source_url": "https://example.com/iga",
                    "fetched_at_utc": "2026-07-16T00:00:00Z",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.json"
            snapshot_path.write_text(json.dumps(snapshot_payload), encoding="utf-8")

            provider = LocalSnapshotProvider(
                {
                    "id": "metro_qc_snapshot",
                    "type": "local_snapshot",
                    "enabled": True,
                    "snapshot_path": str(snapshot_path),
                },
                timeout_seconds=2,
            )

            quote = provider.fetch_price(
                item_name="Bananas",
                item_category="produce",
                base_unit_price=2.0,
                store_chain="Metro",
                store_price_tier="mid",
                postal_code="H3A1A1",
                country="CA",
                currency_hint="CAD",
            )

            self.assertIsNotNone(quote)
            selected = cast(LivePriceQuote, quote)
            self.assertEqual(selected.unit_price, 1.99)


if __name__ == "__main__":
    unittest.main()
