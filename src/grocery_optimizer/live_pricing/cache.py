from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LivePriceQuote:
    provider_id: str
    item_name: str
    currency: str
    unit_price: float
    confidence: float
    fetched_at_utc: str
    source_url: str
    product_name: str = ""
    store_chain: str = ""
    package_size: float | None = None
    package_unit: str = "package"
    package_label: str = ""
    regular_price: float | None = None
    on_sale: bool = False
    valid_from_utc: str = ""
    valid_to_utc: str = ""
    source_type: str = "unknown"
    offer_quantity: int = 1
    offer_price: float | None = None
    normalized_unit_price: float | None = None
    normalized_unit_basis: str = "package"
    source_item_id: str = ""
    image_url: str = ""
    price_basis_text: str = ""


class PriceCache:
    """In-memory TTL cache for live price quotes."""

    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[LivePriceQuote, float]] = {}

    @staticmethod
    def make_key(provider_id: str, store_chain: str, item_name: str, postal_code: str) -> str:
        return f"{provider_id}|{store_chain.lower()}|{item_name.lower()}|{postal_code.upper()}"

    def get(self, key: str) -> LivePriceQuote | None:
        record = self._store.get(key)
        if not record:
            return None
        quote, expires_at = record
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return quote

    def set(self, key: str, quote: LivePriceQuote) -> None:
        self._store[key] = (quote, time.time() + self.ttl_seconds)
