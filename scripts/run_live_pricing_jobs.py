from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from grocery_optimizer.data_io import load_items_from_json
from grocery_optimizer.live_pricing import get_live_pricing_engine, reload_live_pricing_engine
from grocery_optimizer.live_pricing.storage import flush_live_quotes, save_live_quote


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_state(path: Path) -> dict[str, Any]:
    return _load_json(path)


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _job_is_due(job: dict[str, Any], state: dict[str, Any]) -> bool:
    if not bool(job.get("enabled", False)):
        return False
    job_id = str(job.get("id", "")).strip()
    if not job_id:
        return False

    every_minutes = max(5, int(job.get("every_minutes", 180)))
    runs = state.get("runs", {})
    last_epoch = float(runs.get(job_id, {}).get("last_run_epoch", 0.0))
    return (time.time() - last_epoch) >= (every_minutes * 60)


def _catalog_items_for_job(job: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_path = str(job.get("catalog_path", "config/catalog.json"))
    categories = {str(value).strip().lower() for value in job.get("categories", []) if str(value).strip()}
    max_items = max(1, int(job.get("max_items", 20)))

    payload = load_items_from_json(catalog_path)
    rows = [
        {
            "name": item.name,
            "category": item.category,
            "price": float(item.price),
        }
        for item in payload
    ]
    if categories:
        rows = [row for row in rows if str(row.get("category", "")).lower() in categories]
    return rows[:max_items]


def _run_job(job: dict[str, Any]) -> dict[str, Any]:
    engine = get_live_pricing_engine()
    engine.reset_snapshot_budget()

    provider_id = str(job.get("provider_id", "")).strip()
    store_chain = str(job.get("store_chain", "")).strip()
    country = str(job.get("country", "CA")).strip().upper()
    currency = str(job.get("currency", "CAD")).strip().upper()
    store_price_tier = str(job.get("store_price_tier", "mid")).strip().lower()
    postal_codes = [str(pc).strip() for pc in job.get("postal_codes", []) if str(pc).strip()]

    if not provider_id or not store_chain or not postal_codes:
        return {
            "quotes_saved": 0,
            "attempts": 0,
            "detail": "missing provider_id, store_chain, or postal_codes",
        }

    items = _catalog_items_for_job(job)
    if not items:
        return {
            "quotes_saved": 0,
            "attempts": 0,
            "detail": "no catalog items resolved",
        }

    quotes_saved = 0
    attempts = 0
    for postal_code in postal_codes:
        normalized_postal = postal_code.upper().replace(" ", "")
        for item in items:
            attempts += 1
            quote = engine.fetch_quote(
                item_name=str(item["name"]),
                item_category=str(item["category"]),
                base_unit_price=float(item["price"]),
                store_chain=store_chain,
                store_price_tier=store_price_tier,
                postal_code=normalized_postal,
                country=country,
                currency_hint=currency,
            )
            if not quote:
                continue
            if quote.provider_id != provider_id:
                continue

            save_live_quote(
                provider_id=quote.provider_id,
                item_name=str(item["name"]),
                store_chain=store_chain,
                postal_code=normalized_postal,
                country=country,
                currency=quote.currency,
                unit_price=quote.unit_price,
                confidence=quote.confidence,
                fetched_at_utc=quote.fetched_at_utc,
                source_url=quote.source_url,
            )
            quotes_saved += 1

    flush_live_quotes()
    return {
        "quotes_saved": quotes_saved,
        "attempts": attempts,
        "detail": "ok",
    }


def _run_due_jobs(config: dict[str, Any], state: dict[str, Any], force: bool) -> dict[str, Any]:
    jobs = [job for job in config.get("jobs", []) if isinstance(job, dict)]
    runs = state.setdefault("runs", {})
    report: dict[str, Any] = {"started_utc": _now_utc_iso(), "jobs": []}

    for job in jobs:
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue
        if not bool(job.get("enabled", False)):
            continue
        if not force and not _job_is_due(job, state):
            continue

        result = _run_job(job)
        runs[job_id] = {
            "last_run_epoch": time.time(),
            "last_run_utc": _now_utc_iso(),
            "quotes_saved": int(result.get("quotes_saved", 0)),
            "attempts": int(result.get("attempts", 0)),
            "detail": str(result.get("detail", "ok")),
        }
        report["jobs"].append({"job_id": job_id, **runs[job_id]})

    report["finished_utc"] = _now_utc_iso()
    report["jobs_run"] = len(report["jobs"])
    report["total_quotes_saved"] = sum(int(job.get("quotes_saved", 0)) for job in report["jobs"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheduled live pricing jobs.")
    parser.add_argument("--config", default="config/live_pricing/jobs.json", help="Path to jobs config JSON")
    parser.add_argument("--force", action="store_true", help="Run enabled jobs regardless of interval")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--poll-seconds", type=int, default=300, help="Polling interval for daemon mode")
    parser.add_argument("--reload-providers", action="store_true", help="Reload provider config before running")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = _load_json(config_path)
    state_path = Path(str(config.get("state_file", "data/live_pricing_job_state.json")))

    if args.reload_providers:
        reload_live_pricing_engine()

    if args.once:
        state = _load_state(state_path)
        report = _run_due_jobs(config, state, force=args.force)
        _save_state(state_path, state)
        print(json.dumps(report, indent=2))
        return 0

    poll_seconds = max(60, int(args.poll_seconds or config.get("poll_interval_seconds", 300)))
    while True:
        state = _load_state(state_path)
        report = _run_due_jobs(config, state, force=args.force)
        _save_state(state_path, state)
        print(json.dumps(report, indent=2))
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
