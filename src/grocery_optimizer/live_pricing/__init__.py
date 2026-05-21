"""live_pricing package -- re-exports the same public API as the former single-file module."""

from __future__ import annotations

from ._singleton import (
    get_live_pricing_engine as get_live_pricing_engine,
)
from ._singleton import (
    reload_live_pricing_engine as reload_live_pricing_engine,
)

# Public API used by grocery_optimizer.api.app / service
from .engine import build_store_live_pricing_snapshot as build_store_live_pricing_snapshot

# Internal names imported by tests (kept for backward compatibility)
from .parsing import (
    _extract_flipp_price as _extract_flipp_price,
)
from .parsing import (
    _parse_deal_unit_price as _parse_deal_unit_price,
)
from .parsing import (
    parse_deal_text as parse_deal_text,
)
from .storage import get_live_price_history as get_live_price_history

__all__ = [
    "build_store_live_pricing_snapshot",
    "get_live_pricing_engine",
    "get_live_price_history",
    "reload_live_pricing_engine",
    "parse_deal_text",
]
