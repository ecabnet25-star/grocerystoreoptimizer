from __future__ import annotations

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .cache import LivePriceQuote
from .parsing import (
    _close_http_error,
    _extract_flipp_currency,
    _extract_flipp_price,
    _extract_partner_price,
    _extract_path,
    _http_json,
    _product_matches_store,
    _to_float,
)


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    enabled: bool
    provider_type: str
    configured: bool
    detail: str


class BaseLiveProvider:
    def __init__(self, config: dict[str, Any], timeout_seconds: int):
        self.config = config
        self.timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return str(self.config.get("id", "unknown-provider"))

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type=str(self.config.get("type", "unknown")),
            configured=self.enabled,
            detail="ready" if self.enabled else "disabled",
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
        raise NotImplementedError


class JsonFeedProvider(BaseLiveProvider):
    def health(self) -> ProviderHealth:
        api_key_env = str(self.config.get("api_key_env", "")).strip()
        configured = bool(self.config.get("base_url")) and (not api_key_env or bool(os.getenv(api_key_env)))
        detail = "ready" if configured else "missing base_url or API key env"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="json_feed",
            configured=configured,
            detail=detail,
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
        if not self.enabled:
            return None

        base_url = str(self.config.get("base_url", "")).strip()
        if not base_url:
            return None

        query_template = dict(self.config.get("query", {}))
        query = {
            k: str(v)
            .replace("{item_name}", item_name)
            .replace("{store_chain}", store_chain)
            .replace("{postal_code}", postal_code)
            .replace("{country}", country)
            for k, v in query_template.items()
        }
        url = f"{base_url}?{urlencode(query)}" if query else base_url

        headers = {"Accept": "application/json", "User-Agent": "grocery-optimizer/0.3"}
        headers.update({str(k): str(v) for k, v in dict(self.config.get("headers", {})).items()})

        api_key_env = str(self.config.get("api_key_env", "")).strip()
        if api_key_env:
            api_key = os.getenv(api_key_env, "")
            if not api_key:
                return None
            key_header = str(self.config.get("api_key_header", "x-rapidapi-key"))
            headers[key_header] = api_key

        req = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except HTTPError as error:
            _close_http_error(error)
            return None
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

        price = _extract_path(payload, str(self.config.get("price_path", "")))
        if price is None:
            return None

        currency = _extract_path(payload, str(self.config.get("currency_path", ""))) or currency_hint
        normalized_price = _to_float(price)
        if normalized_price is None:
            return None

        confidence = float(self.config.get("confidence", 0.85))
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return LivePriceQuote(
            provider_id=self.provider_id,
            item_name=item_name,
            currency=str(currency),
            unit_price=normalized_price,
            confidence=max(0.0, min(confidence, 1.0)),
            fetched_at_utc=timestamp,
            source_url=base_url,
        )


class RetailerCatalogProvider(BaseLiveProvider):
    """Partner API adapter for retailer product catalogs and search endpoints."""

    def health(self) -> ProviderHealth:
        api_key_env = str(self.config.get("api_key_env", "")).strip()
        configured = bool(self.config.get("base_url")) and (not api_key_env or bool(os.getenv(api_key_env)))
        detail = "ready" if configured else "missing base_url or API key env"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="retailer_catalog",
            configured=configured,
            detail=detail,
        )

    def _candidate_rows(self, payload: Any) -> list[dict[str, Any]]:
        configured_path = str(self.config.get("result_list_path", "")).strip()
        candidates: Any = _extract_path(payload, configured_path) if configured_path else None
        if candidates is None and isinstance(payload, dict):
            for fallback_path in ("results", "products", "items", "data"):
                candidates = _extract_path(payload, fallback_path)
                if isinstance(candidates, list):
                    break
        if candidates is None and isinstance(payload, list):
            candidates = payload
        if not isinstance(candidates, list):
            return []
        return [cast(dict[str, Any], row) for row in candidates if isinstance(row, dict)]

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
        if not self.enabled:
            return None

        base_url = str(self.config.get("base_url", "")).strip()
        if not base_url:
            return None

        query_template = dict(self.config.get("query", {}))
        query = {
            k: str(v)
            .replace("{item_name}", item_name)
            .replace("{item_category}", item_category)
            .replace("{store_chain}", store_chain)
            .replace("{postal_code}", postal_code)
            .replace("{country}", country)
            for k, v in query_template.items()
        }
        url = f"{base_url}?{urlencode(query)}" if query else base_url

        headers = {"Accept": "application/json", "User-Agent": "grocery-optimizer/0.3"}
        headers.update({str(k): str(v) for k, v in dict(self.config.get("headers", {})).items()})
        api_key_env = str(self.config.get("api_key_env", "")).strip()
        if api_key_env:
            api_key = os.getenv(api_key_env, "")
            if not api_key:
                return None
            headers[str(self.config.get("api_key_header", "Authorization"))] = str(
                self.config.get("api_key_prefix", "Bearer ")
            ) + api_key

        req = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except HTTPError as error:
            _close_http_error(error)
            return None
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

        item_name_path = str(self.config.get("item_name_path", "name"))
        store_chain_path = str(self.config.get("store_chain_path", "store.chain"))
        price_path = str(self.config.get("price_path", "price"))
        currency_path = str(self.config.get("currency_path", "currency"))
        item_lower = item_name.lower()
        store_lower = store_chain.lower()

        for row in self._candidate_rows(payload):
            product_name = str(_extract_path(row, item_name_path) or row.get("name", "")).lower()
            product_store = str(_extract_path(row, store_chain_path) or row.get("store", "")).lower()
            if product_name and item_lower not in product_name and product_name not in item_lower:
                continue
            if product_store and store_lower not in product_store and product_store not in store_lower:
                continue

            normalized_price = _to_float(_extract_path(row, price_path))
            if normalized_price is None or normalized_price <= 0:
                continue

            confidence = float(self.config.get("confidence", 0.88))
            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            return LivePriceQuote(
                provider_id=self.provider_id,
                item_name=item_name,
                currency=str(_extract_path(row, currency_path) or currency_hint),
                unit_price=round(normalized_price, 2),
                confidence=max(0.0, min(confidence, 1.0)),
                fetched_at_utc=timestamp,
                source_url=url,
            )

        return None


class HtmlRegexProvider(BaseLiveProvider):
    def health(self) -> ProviderHealth:
        allow_scraping_env = os.getenv("LIVE_PRICING_ALLOW_SCRAPING", "false").lower() == "true"
        allow_scraping_cfg = bool(self.config.get("allow_scraping", False))
        configured = bool(self.config.get("url_template")) and bool(self.config.get("price_regex"))
        if not configured:
            detail = "missing url_template or price_regex"
        elif not (allow_scraping_env and allow_scraping_cfg):
            detail = "set LIVE_PRICING_ALLOW_SCRAPING=true to enable"
        else:
            detail = "ready"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="html_regex",
            configured=configured,
            detail=detail,
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
        if not self.enabled:
            return None

        if os.getenv("LIVE_PRICING_ALLOW_SCRAPING", "false").lower() != "true":
            return None

        url_template = str(self.config.get("url_template", "")).strip()
        if not url_template:
            return None

        url = (
            url_template.replace("{item_name}", item_name)
            .replace("{store_chain}", store_chain)
            .replace("{postal_code}", postal_code)
            .replace("{country}", country)
        )

        req = Request(
            url=url,
            headers={
                "User-Agent": "grocery-optimizer/0.3 (respect robots and site terms)",
                "Accept": "text/html,application/xhtml+xml",
            },
            method="GET",
        )

        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as error:
            _close_http_error(error)
            return None
        except (URLError, TimeoutError):
            return None

        pattern = str(self.config.get("price_regex", ""))
        if not pattern:
            return None

        match = re.search(pattern, html, flags=re.IGNORECASE)
        if not match:
            return None

        normalized_price = _to_float(match.group(1))
        if normalized_price is None:
            return None

        confidence = float(self.config.get("confidence", 0.6))
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return LivePriceQuote(
            provider_id=self.provider_id,
            item_name=item_name,
            currency=currency_hint,
            unit_price=normalized_price,
            confidence=max(0.0, min(confidence, 1.0)),
            fetched_at_utc=timestamp,
            source_url=url,
        )


class PublicMarketProvider(BaseLiveProvider):
    """Non-scraping provider that estimates shelf prices from public market data signals."""

    def __init__(self, config: dict[str, Any], timeout_seconds: int):
        super().__init__(config, timeout_seconds)
        self._inflation_cache: dict[str, tuple[float, float]] = {}
        benchmark_path = str(config.get("benchmark_path", "config/live_pricing/public_benchmarks.json"))
        self._benchmark_path = Path(benchmark_path)
        self._benchmarks_cache: dict[str, Any] | None = None

    def _load_benchmarks(self) -> dict[str, Any]:
        if self._benchmarks_cache is not None:
            return self._benchmarks_cache
        if not self._benchmark_path.exists():
            return {}
        try:
            self._benchmarks_cache = json.loads(self._benchmark_path.read_text(encoding="utf-8"))
            return self._benchmarks_cache  # type: ignore[return-value]
        except json.JSONDecodeError:
            return {}

    def _country_inflation_multiplier(self, country: str) -> float:
        now = time.time()
        cached = self._inflation_cache.get(country.upper())
        if cached and cached[1] > now:
            return cached[0]

        indicator = str(self.config.get("world_bank_indicator", "FP.CPI.TOTL.ZG"))
        url = (
            f"https://api.worldbank.org/v2/country/{country.upper()}/indicator/{indicator}?"
            "format=json&per_page=60"
        )
        payload = _http_json(url, timeout_seconds=self.timeout_seconds)
        multiplier = 1.0
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
            rows = cast(list[dict[str, Any]], payload[1])
            for row in rows:
                value = row.get("value")
                number = _to_float(value)
                if number is None:
                    continue
                # Convert annual food inflation % into smooth multiplier.
                multiplier = max(0.8, min(1.4, 1.0 + (number / 100.0)))
                break

        ttl = int(self.config.get("inflation_cache_seconds", 43200))
        self._inflation_cache[country.upper()] = (multiplier, now + ttl)
        return multiplier

    def health(self) -> ProviderHealth:
        configured = self._benchmark_path.exists()
        detail = "ready" if configured else f"missing benchmark file: {self._benchmark_path}"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="public_market",
            configured=configured,
            detail=detail,
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
        if not self.enabled:
            return None

        benchmarks = self._load_benchmarks()
        countries = cast(dict[str, Any], benchmarks.get("countries", {}))
        country_cfg = cast(dict[str, Any], countries.get(country.upper(), {}))
        tier_map = cast(dict[str, Any], country_cfg.get("tier_multipliers", {}))
        category_map = cast(dict[str, Any], country_cfg.get("category_multipliers", {}))

        tier_mult = _to_float(tier_map.get(store_price_tier, 1.0)) or 1.0
        category_mult = _to_float(category_map.get(item_category, 1.0)) or 1.0
        baseline_mult = _to_float(country_cfg.get("baseline_multiplier", 1.0)) or 1.0

        inflation_mult = self._country_inflation_multiplier(country)

        estimated = round(float(base_unit_price) * baseline_mult * tier_mult * category_mult * inflation_mult, 2)
        if estimated <= 0:
            return None

        confidence = float(self.config.get("confidence", 0.58))
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        source_url = str(country_cfg.get("source_url", "https://api.worldbank.org/"))
        return LivePriceQuote(
            provider_id=self.provider_id,
            item_name=item_name,
            currency=currency_hint,
            unit_price=estimated,
            confidence=max(0.0, min(confidence, 1.0)),
            fetched_at_utc=timestamp,
            source_url=source_url,
        )


class OpenFoodFactsPartnerProvider(BaseLiveProvider):
    """Direct partner adapter for US/Canada crowdsourced shelf prices (Open Food Facts ecosystem)."""

    def health(self) -> ProviderHealth:
        detail = "ready"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="openfoodfacts_partner",
            configured=True,
            detail=detail,
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
        if not self.enabled:
            return None

        country_tag = "en:canada" if country.upper() == "CA" else "en:united-states"
        search_url = (
            "https://world.openfoodfacts.org/cgi/search.pl?"
            + urlencode(
                {
                    "search_terms": item_name,
                    "search_simple": "1",
                    "action": "process",
                    "json": "1",
                    "page_size": str(int(self.config.get("page_size", 20))),
                    "tagtype_0": "countries",
                    "tag_contains_0": "contains",
                    "tag_0": country_tag,
                    "fields": "product_name,stores,stores_tags,price,prices,countries_tags",
                }
            )
        )

        payload = _http_json(search_url, timeout_seconds=self.timeout_seconds)
        if not isinstance(payload, dict):
            return None

        products = payload.get("products", [])
        if not isinstance(products, list):
            return None

        store_chain_lower = store_chain.strip().lower()
        for product in products:
            if not isinstance(product, dict):
                continue

            if not _product_matches_store(product, store_chain_lower):
                continue

            price = _extract_partner_price(product)
            if price is None:
                continue

            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            confidence = float(self.config.get("confidence", 0.72))
            return LivePriceQuote(
                provider_id=self.provider_id,
                item_name=item_name,
                currency=currency_hint,
                unit_price=round(price, 2),
                confidence=max(0.0, min(confidence, 1.0)),
                fetched_at_utc=timestamp,
                source_url=search_url,
            )

        return None


class FlippPartnerProvider(BaseLiveProvider):
    """Concrete adapter for Flipp/retail flyer partner feeds (US/CA), requires API key."""

    def health(self) -> ProviderHealth:
        api_key_env = str(self.config.get("api_key_env", "")).strip()
        has_key = bool(api_key_env and os.getenv(api_key_env))
        configured = bool(self.config.get("base_url")) and has_key
        detail = "ready" if configured else "missing base_url or API key env"
        if not self.enabled:
            detail = "disabled"
        return ProviderHealth(
            provider_id=self.provider_id,
            enabled=self.enabled,
            provider_type="flipp_partner",
            configured=configured,
            detail=detail,
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
        if not self.enabled:
            return None

        api_key_env = str(self.config.get("api_key_env", "")).strip()
        api_key = os.getenv(api_key_env, "") if api_key_env else ""
        if not api_key:
            return None

        base_url = str(self.config.get("base_url", "")).strip()
        if not base_url:
            return None

        query_params = {
            "q": item_name,
            "merchant": store_chain,
            "postal_code": postal_code,
            "country": country,
        }
        url = f"{base_url}?{urlencode(query_params)}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "grocery-optimizer/0.3",
            str(self.config.get("api_key_header", "x-rapidapi-key")): api_key,
        }
        host_header_name = str(self.config.get("host_header_name", "x-rapidapi-host"))
        host_header_value = str(self.config.get("host_header_value", "")).strip()
        if host_header_value:
            headers[host_header_name] = host_header_value

        req = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except HTTPError as error:
            _close_http_error(error)
            return None
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

        value = _extract_flipp_price(
            payload=payload,
            item_name=item_name,
            store_chain=store_chain,
            fallback_price_path=str(self.config.get("price_path", "results.0.price")),
        )
        if value is None:
            return None

        currency = (
            _extract_flipp_currency(
                payload=payload,
                fallback_currency_path=str(self.config.get("currency_path", "results.0.currency")),
            )
            or currency_hint
        )
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        confidence = float(self.config.get("confidence", 0.82))
        return LivePriceQuote(
            provider_id=self.provider_id,
            item_name=item_name,
            currency=str(currency),
            unit_price=round(value, 2),
            confidence=max(0.0, min(confidence, 1.0)),
            fetched_at_utc=timestamp,
            source_url=base_url,
        )
