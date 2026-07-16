from __future__ import annotations

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false
import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import GroceryItem
from ..observability import provider_metrics_snapshot, record_provider_call
from .cache import LivePriceQuote, PriceCache
from .providers import (
    BaseLiveProvider,
    FlippPartnerProvider,
    HtmlRegexProvider,
    JsonFeedProvider,
    LocalSnapshotProvider,
    OpenFoodFactsPartnerProvider,
    PublicMarketProvider,
    RetailerCatalogProvider,
)
from .storage import flush_live_quotes, save_live_quote
from .storage import get_live_price_median


class LivePricingEngine:
    def __init__(self, config_path: str | Path = "config/live_pricing/providers.json"):
        self.config_path = Path(config_path)
        self._config = self._raw_config()
        self._providers = self._load_providers()
        self.cache_ttl_seconds = int(self._config.get("cache_ttl_seconds", 900))
        self.max_quotes_per_snapshot = int(self._config.get("max_live_quotes_per_snapshot", 60))
        self.min_quote_confidence = float(self._config.get("min_quote_confidence", 0.55))
        self.min_price_ratio = float(self._config.get("min_price_ratio", 0.35))
        self.max_price_ratio = float(self._config.get("max_price_ratio", 2.5))
        self.history_min_samples = int(self._config.get("history_min_samples", 5))
        self.history_min_confidence = float(self._config.get("history_min_confidence", 0.6))
        self.history_max_rows = int(self._config.get("history_max_rows", 120))
        self.history_max_deviation_ratio = float(self._config.get("history_max_deviation_ratio", 1.8))
        self._cache = PriceCache(ttl_seconds=self.cache_ttl_seconds)
        self._quote_budget_counter = 0
        self._provider_config_by_id = {
            str(cfg.get("id", "")).strip(): cfg
            for cfg in self._config.get("providers", [])
            if isinstance(cfg, dict)
        }

    def _raw_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"providers": []}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"providers": []}

    def _load_providers(self) -> list[BaseLiveProvider]:
        raw = self._config
        timeout_seconds = int(raw.get("request_timeout_seconds", 3))
        providers: list[BaseLiveProvider] = []
        for provider_cfg in raw.get("providers", []):
            provider_type = str(provider_cfg.get("type", "")).strip().lower()
            if provider_type == "json_feed":
                providers.append(JsonFeedProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "html_regex":
                providers.append(HtmlRegexProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "openfoodfacts_partner":
                providers.append(OpenFoodFactsPartnerProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "flipp_partner":
                providers.append(FlippPartnerProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "local_snapshot":
                providers.append(LocalSnapshotProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "public_market":
                providers.append(PublicMarketProvider(provider_cfg, timeout_seconds=timeout_seconds))
            elif provider_type == "retailer_catalog":
                providers.append(RetailerCatalogProvider(provider_cfg, timeout_seconds=timeout_seconds))
        return providers

    def _provider_weight(self, provider_id: str, provider: BaseLiveProvider) -> float:
        cfg = self._provider_config_by_id.get(provider_id, {})
        configured = cfg.get("reliability_weight")
        if configured is not None:
            try:
                return max(0.1, min(float(configured), 2.0))
            except (TypeError, ValueError):
                pass

        provider_type = str(provider.config.get("type", "")).strip().lower()
        default_by_type = {
            "retailer_catalog": 1.0,
            "json_feed": 0.92,
            "flipp_partner": 0.88,
            "openfoodfacts_partner": 0.8,
            "html_regex": 0.65,
            "public_market": 0.58,
        }
        return default_by_type.get(provider_type, 0.7)

    def _store_chain_allowed(self, provider_id: str, store_chain: str) -> bool:
        cfg = self._provider_config_by_id.get(provider_id, {})
        chain = store_chain.strip().lower()
        if not chain:
            return True

        allowlist = cfg.get("store_chain_allowlist", [])
        if isinstance(allowlist, list) and allowlist:
            allowed = {str(value).strip().lower() for value in allowlist if str(value).strip()}
            if allowed and chain not in allowed:
                return False

        denylist = cfg.get("store_chain_denylist", [])
        if isinstance(denylist, list) and denylist:
            denied = {str(value).strip().lower() for value in denylist if str(value).strip()}
            if chain in denied:
                return False

        return True

    def _quote_is_plausible(
        self,
        *,
        quote: LivePriceQuote,
        base_unit_price: float,
        store_price_tier: str,
        provider_id: str,
    ) -> bool:
        if quote.unit_price <= 0 or not math.isfinite(quote.unit_price):
            return False

        if quote.confidence < self.min_quote_confidence and provider_id != "public_market_benchmark":
            return False

        base = max(float(base_unit_price), 0.01)
        ratio = quote.unit_price / base
        if not math.isfinite(ratio):
            return False

        cfg = self._provider_config_by_id.get(provider_id, {})
        min_ratio = float(cfg.get("min_price_ratio", self.min_price_ratio))
        max_ratio = float(cfg.get("max_price_ratio", self.max_price_ratio))
        tier = store_price_tier.strip().lower()
        tier_bounds: dict[str, tuple[float, float]] = {
            "budget": (max(0.2, min_ratio), min(max_ratio, 1.75)),
            "mid": (max(0.25, min_ratio), min(max_ratio, 2.0)),
            "premium": (max(0.3, min_ratio), min(max_ratio, 2.4)),
        }
        lower, upper = tier_bounds.get(tier, (min_ratio, max_ratio))
        return lower <= ratio <= upper

    def _quote_score(self, provider_id: str, provider: BaseLiveProvider, quote: LivePriceQuote) -> float:
        reliability = self._provider_weight(provider_id, provider)
        return float(quote.confidence) * reliability

    def _quote_passes_history_sanity(
        self,
        *,
        quote: LivePriceQuote,
        item_name: str,
        store_chain: str,
        postal_code: str,
        provider_id: str,
    ) -> bool:
        if provider_id == "public_market_benchmark":
            return True

        median, sample_count = get_live_price_median(
            item_name=item_name,
            store_chain=store_chain,
            postal_code=postal_code,
            min_confidence=self.history_min_confidence,
            max_rows=self.history_max_rows,
        )

        if not median or sample_count < self.history_min_samples:
            return True

        ratio = quote.unit_price / max(median, 0.01)
        lower = max(0.01, 1.0 / max(self.history_max_deviation_ratio, 1.01))
        upper = max(self.history_max_deviation_ratio, 1.01)
        return lower <= ratio <= upper

    def provider_health(self) -> list[dict[str, Any]]:
        metrics = {row["provider_id"]: row for row in provider_metrics_snapshot()}
        return [
            {
                **h.__dict__,
                "metrics": metrics.get(h.provider_id, {}),
            }
            for h in (provider.health() for provider in self._providers)
        ]

    def fetch_quote(
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
        candidates: list[tuple[float, LivePriceQuote]] = []
        for provider in self._providers:
            health = provider.health()
            if not health.enabled or not health.configured:
                record_provider_call(provider.provider_id, outcome="skipped", duration_ms=0.0)
                continue

            if not self._store_chain_allowed(provider.provider_id, store_chain):
                record_provider_call(provider.provider_id, outcome="skipped", duration_ms=0.0)
                continue

            key = PriceCache.make_key(provider.provider_id, store_chain, item_name, postal_code)
            cached = self._cache.get(key)
            if cached:
                record_provider_call(provider.provider_id, outcome="hit", duration_ms=0.0)
                if self._quote_is_plausible(
                    quote=cached,
                    base_unit_price=base_unit_price,
                    store_price_tier=store_price_tier,
                    provider_id=provider.provider_id,
                ) and self._quote_passes_history_sanity(
                    quote=cached,
                    item_name=item_name,
                    store_chain=store_chain,
                    postal_code=postal_code,
                    provider_id=provider.provider_id,
                ):
                    candidates.append((self._quote_score(provider.provider_id, provider, cached), cached))
                continue

            if self._quote_budget_counter >= self.max_quotes_per_snapshot:
                break

            started = time.perf_counter()
            try:
                quote = provider.fetch_price(
                    item_name=item_name,
                    item_category=item_category,
                    base_unit_price=base_unit_price,
                    store_chain=store_chain,
                    store_price_tier=store_price_tier,
                    postal_code=postal_code,
                    country=country,
                    currency_hint=currency_hint,
                )
                record_provider_call(
                    provider.provider_id,
                    outcome="hit" if quote else "miss",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            except Exception as exc:
                record_provider_call(
                    provider.provider_id,
                    outcome="failure",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    error_type=type(exc).__name__,
                )
                quote = None
            self._quote_budget_counter += 1
            if quote:
                self._cache.set(key, quote)
                if self._quote_is_plausible(
                    quote=quote,
                    base_unit_price=base_unit_price,
                    store_price_tier=store_price_tier,
                    provider_id=provider.provider_id,
                ) and self._quote_passes_history_sanity(
                    quote=quote,
                    item_name=item_name,
                    store_chain=store_chain,
                    postal_code=postal_code,
                    provider_id=provider.provider_id,
                ):
                    candidates.append((self._quote_score(provider.provider_id, provider, quote), quote))

        if not candidates:
            return None

        candidates.sort(key=lambda row: row[0], reverse=True)
        return candidates[0][1]

    def reset_snapshot_budget(self) -> None:
        self._quote_budget_counter = 0


def build_store_live_pricing_snapshot(
    *,
    stores: list[dict[str, Any]],
    selected_items: list[GroceryItem],
    postal_code: str,
    country: str,
    currency: str,
    fallback_multiplier_resolver: Callable[[str], float],
    use_live_providers: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from ._singleton import get_live_pricing_engine

    engine = get_live_pricing_engine()
    engine.reset_snapshot_budget()

    chain_fallback_adjustments = {
        "maxi": 0.95,
        "super c": 0.94,
        "walmart": 0.95,
        "costco": 0.93,
        "metro": 1.02,
        "iga": 1.03,
        "provigo": 1.04,
    }

    def _chain_fallback_multiplier(chain_name: str) -> float:
        key = chain_name.strip().lower()
        if key in chain_fallback_adjustments:
            return chain_fallback_adjustments[key]
        for alias, multiplier in chain_fallback_adjustments.items():
            if alias in key:
                return multiplier
        return 1.0

    compared_stores: list[dict[str, Any]] = []
    sources: set[str] = set()
    overall_live_quotes = 0
    overall_quotes = 0
    latest_timestamp = ""
    item_quote_rows: list[dict[str, Any]] = []

    for store in stores:
        tier_multiplier = fallback_multiplier_resolver(store["price_tier"])
        store_total = 0.0
        live_count = 0
        fallback_count = 0
        confidence_sum = 0.0
        store_provider_ids: set[str] = set()

        for item in selected_items:
            overall_quotes += 1
            quote = None
            if use_live_providers:
                quote = engine.fetch_quote(
                    item_name=item.name,
                    item_category=item.category,
                    base_unit_price=item.price,
                    store_chain=store["chain"],
                    store_price_tier=store["price_tier"],
                    postal_code=postal_code,
                    country=country,
                    currency_hint=currency,
                )
            if quote:
                live_count += 1
                overall_live_quotes += 1
                sources.add(quote.provider_id)
                store_provider_ids.add(quote.provider_id)
                confidence_sum += quote.confidence
                if quote.fetched_at_utc > latest_timestamp:
                    latest_timestamp = quote.fetched_at_utc
                store_total += quote.unit_price * item.quantity
                save_live_quote(
                    provider_id=quote.provider_id,
                    item_name=item.name,
                    store_chain=store["chain"],
                    postal_code=postal_code,
                    country=country,
                    currency=quote.currency,
                    unit_price=quote.unit_price,
                    confidence=quote.confidence,
                    fetched_at_utc=quote.fetched_at_utc,
                    source_url=quote.source_url,
                )
                item_quote_rows.append(
                    {
                        "store_id": store["store_id"],
                        "store_name": store["name"],
                        "item_name": item.name,
                        "quantity": item.quantity,
                        "unit_price": round(quote.unit_price, 2),
                        "line_total": round(quote.unit_price * item.quantity, 2),
                        "currency": quote.currency,
                        "provider_id": quote.provider_id,
                        "confidence": quote.confidence,
                        "pricing_source": "public_benchmark_live"
                        if quote.provider_id == "public_market_benchmark"
                        else "third_party_live",
                    }
                )
            else:
                fallback_count += 1
                chain_multiplier = _chain_fallback_multiplier(str(store.get("chain", "")))
                effective_multiplier = tier_multiplier * chain_multiplier
                store_total += item.total_cost * effective_multiplier
                fallback_unit = round(item.price * effective_multiplier, 2)
                save_live_quote(
                    provider_id="fallback",
                    item_name=item.name,
                    store_chain=store["chain"],
                    postal_code=postal_code,
                    country=country,
                    currency=currency,
                    unit_price=fallback_unit,
                    confidence=0.0,
                    fetched_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    source_url="fallback:tier_estimate",
                )
                item_quote_rows.append(
                    {
                        "store_id": store["store_id"],
                        "store_name": store["name"],
                        "item_name": item.name,
                        "quantity": item.quantity,
                        "unit_price": fallback_unit,
                        "line_total": round(item.total_cost * effective_multiplier, 2),
                        "currency": currency,
                        "provider_id": "fallback",
                        "confidence": 0.0,
                        "pricing_source": "tier_estimate_fallback",
                    }
                )

        live_coverage = round((live_count / len(selected_items)) * 100, 1) if selected_items else 0.0
        confidence = round((confidence_sum / live_count), 2) if live_count else 0.0
        benchmark_only_live = bool(store_provider_ids) and store_provider_ids.issubset({"public_market_benchmark"})
        store_pricing_source = (
            "public_benchmark_live"
            if benchmark_only_live
            else ("third_party_live" if live_count > 0 else "tier_estimate_fallback")
        )

        compared_stores.append(
            {
                **store,
                "estimated_total": round(store_total, 2),
                "value_score": round(store["quality_rating"] / (max(store_total, 0.01) / 10), 2),
                "pricing_source": store_pricing_source,
                "live_item_quotes": live_count,
                "fallback_item_quotes": fallback_count,
                "live_coverage_percent": live_coverage,
                "confidence_score": confidence,
            }
        )

    compared_stores.sort(key=lambda x: x["estimated_total"])

    snapshot_meta = {
        "providers_checked": sorted({h["provider_id"] for h in engine.provider_health()}),
        "providers_with_live_quotes": sorted(sources),
        "live_quotes": overall_live_quotes,
        "total_quote_attempts": overall_quotes,
        "live_coverage_percent": round((overall_live_quotes / overall_quotes) * 100, 1) if overall_quotes else 0.0,
        "last_updated_utc": latest_timestamp
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "provider_health": engine.provider_health(),
        "item_quotes": item_quote_rows,
        "alerts": [
            {
                "code": "LOW_LIVE_COVERAGE",
                "severity": "warning",
                "message": "Live quote coverage is below 40%. Fallback estimates dominate current snapshot.",
            }
        ] if use_live_providers and overall_quotes and (overall_live_quotes / overall_quotes) < 0.4 else [],
    }

    # Flush all accumulated quote inserts in a single commit.
    flush_live_quotes()

    return compared_stores, snapshot_meta
