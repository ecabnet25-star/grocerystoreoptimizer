from __future__ import annotations

from .engine import LivePricingEngine

_engine_instance: LivePricingEngine | None = None


def get_live_pricing_engine() -> LivePricingEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = LivePricingEngine()
    return _engine_instance


def reload_live_pricing_engine() -> LivePricingEngine:
    global _engine_instance
    _engine_instance = LivePricingEngine()
    return _engine_instance
