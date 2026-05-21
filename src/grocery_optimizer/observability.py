from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_metrics_lock = threading.Lock()
_request_latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
_request_totals: dict[str, dict[str, Any]] = {}
_provider_totals: dict[str, dict[str, Any]] = {}


class JsonLogFormatter(logging.Formatter):
    """Small JSON formatter for production-friendly stdout logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "") or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client",
            "provider_id",
            "outcome",
            "error_type",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_json_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_grocery_json_logging", False):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root._grocery_json_logging = True


def set_request_id(request_id: str) -> contextvars.Token[str]:
    return _request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id_var.reset(token)


def get_request_id() -> str:
    return _request_id_var.get()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def record_request(method: str, path: str, status_code: int, duration_ms: float) -> None:
    key = f"{method.upper()} {path}"
    with _metrics_lock:
        stat = _request_totals.setdefault(
            key,
            {
                "method": method.upper(),
                "path": path,
                "count": 0,
                "errors": 0,
                "total_latency_ms": 0.0,
                "last_status_code": 0,
                "last_seen_utc": "",
            },
        )
        stat["count"] = int(stat["count"]) + 1
        stat["errors"] = int(stat["errors"]) + (1 if status_code >= 500 else 0)
        stat["total_latency_ms"] = float(stat["total_latency_ms"]) + duration_ms
        stat["last_status_code"] = status_code
        stat["last_seen_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _request_latencies[key].append(duration_ms)


def record_provider_call(
    provider_id: str,
    *,
    outcome: str,
    duration_ms: float,
    error_type: str = "",
) -> None:
    with _metrics_lock:
        stat = _provider_totals.setdefault(
            provider_id,
            {
                "provider_id": provider_id,
                "attempts": 0,
                "hits": 0,
                "misses": 0,
                "failures": 0,
                "skipped": 0,
                "total_latency_ms": 0.0,
                "last_outcome": "",
                "last_error_type": "",
                "last_seen_utc": "",
            },
        )
        stat["attempts"] = int(stat["attempts"]) + (0 if outcome == "skipped" else 1)
        if outcome == "hit":
            stat["hits"] = int(stat["hits"]) + 1
        elif outcome == "miss":
            stat["misses"] = int(stat["misses"]) + 1
        elif outcome == "failure":
            stat["failures"] = int(stat["failures"]) + 1
        elif outcome == "skipped":
            stat["skipped"] = int(stat["skipped"]) + 1
        stat["total_latency_ms"] = float(stat["total_latency_ms"]) + duration_ms
        stat["last_outcome"] = outcome
        stat["last_error_type"] = error_type
        stat["last_seen_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request_metrics_snapshot() -> dict[str, Any]:
    with _metrics_lock:
        endpoints = []
        total_count = 0
        total_errors = 0
        for key, stat in sorted(_request_totals.items()):
            count = int(stat["count"])
            errors = int(stat["errors"])
            latencies = list(_request_latencies.get(key, ()))
            total_count += count
            total_errors += errors
            endpoints.append(
                {
                    **stat,
                    "average_latency_ms": round(float(stat["total_latency_ms"]) / count, 2) if count else 0.0,
                    "p95_latency_ms": _percentile(latencies, 0.95),
                }
            )

        return {
            "requests": {
                "total": total_count,
                "errors": total_errors,
                "error_rate_percent": round((total_errors / total_count) * 100, 2) if total_count else 0.0,
                "endpoints": endpoints,
            },
            "providers": provider_metrics_snapshot_unlocked(),
        }


def provider_metrics_snapshot_unlocked() -> list[dict[str, Any]]:
    providers = []
    for stat in sorted(_provider_totals.values(), key=lambda row: row["provider_id"]):
        attempts = int(stat["attempts"])
        providers.append(
            {
                **stat,
                "average_latency_ms": round(float(stat["total_latency_ms"]) / attempts, 2) if attempts else 0.0,
                "failure_rate_percent": round((int(stat["failures"]) / attempts) * 100, 2) if attempts else 0.0,
                "hit_rate_percent": round((int(stat["hits"]) / attempts) * 100, 2) if attempts else 0.0,
            }
        )
    return providers


def provider_metrics_snapshot() -> list[dict[str, Any]]:
    with _metrics_lock:
        return provider_metrics_snapshot_unlocked()
