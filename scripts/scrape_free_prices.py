from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from grocery_optimizer.live_pricing.flipp import (  # noqa: E402
    chain_matches,
    fetch_flipp_search,
    parse_flipp_quotes,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _catalog_items(path: Path, max_items: int) -> list[dict[str, str]]:
    rows = _load_json(path).get("items", [])
    if not isinstance(rows, list):
        return []
    items: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if name:
            items.append({"name": name, "category": str(row.get("category", "other"))})
        if len(items) >= max_items:
            break
    return items


def _dedupe_quotes(quotes: list[dict[str, Any]], max_variants: int = 4) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in quotes:
        identity = str(row.get("source_item_id") or row.get("product_name", "")).strip().lower()
        key = (
            str(row.get("item_name", "")).strip().lower(),
            str(row.get("store_chain", "")).strip().lower(),
            str(row.get("postal_code", "")).strip().upper().replace(" ", ""),
            identity,
        )
        if not all(key):
            continue
        current = unique.get(key)
        if current is None or float(row.get("confidence", 0)) > float(current.get("confidence", 0)):
            unique[key] = row

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in unique.values():
        group_key = (
            str(row["item_name"]).lower(),
            str(row["store_chain"]).lower(),
            str(row["postal_code"]),
        )
        grouped.setdefault(group_key, []).append(row)

    output: list[dict[str, Any]] = []
    for rows in grouped.values():
        rows.sort(
            key=lambda row: (
                -float(row.get("confidence", 0)),
                0 if bool(row.get("on_sale")) else 1,
                float(row.get("unit_price", 10_000)),
            )
        )
        output.extend(rows[:max_variants])
    return sorted(
        output,
        key=lambda row: (
            str(row.get("postal_code", "")),
            str(row.get("item_name", "")),
            str(row.get("store_chain", "")),
            float(row.get("unit_price", 0)),
        ),
    )


def validate_snapshot(payload: dict[str, Any], min_quotes: int = 10) -> list[str]:
    errors: list[str] = []
    if int(payload.get("schema_version", 0) or 0) < 2:
        errors.append("schema_version must be at least 2")
    rows = payload.get("quotes", [])
    if not isinstance(rows, list) or len(rows) < min_quotes:
        errors.append(f"snapshot must contain at least {min_quotes} verified quotes")
        return errors
    diagnostics = payload.get("diagnostics", {})
    if isinstance(diagnostics, dict):
        query_count = max(1, int(diagnostics.get("query_count", 0) or 0))
        failures = diagnostics.get("query_failures", [])
        failure_count = len(failures) if isinstance(failures, list) else query_count
        if failure_count / query_count > 0.2:
            errors.append("more than 20% of source queries failed")
        chains = diagnostics.get("chains_with_quotes", [])
        if not isinstance(chains, list) or len(chains) < 3:
            errors.append("snapshot must include verified quotes from at least 3 retailer chains")
    required = {
        "item_name",
        "product_name",
        "store_chain",
        "postal_code",
        "unit_price",
        "source_type",
        "source_url",
        "fetched_at_utc",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"quote {index} is not an object")
            continue
        missing = sorted(field for field in required if row.get(field) in {None, ""})
        if missing:
            errors.append(f"quote {index} is missing: {', '.join(missing)}")
        if row.get("source_type") not in {"flyer_aggregator", "retailer_ecommerce"}:
            errors.append(f"quote {index} has an unverified source_type")
        try:
            if float(row.get("unit_price", 0)) <= 0:
                errors.append(f"quote {index} has an invalid price")
        except (TypeError, ValueError):
            errors.append(f"quote {index} has an invalid price")
    return errors[:25]


def _fetch_with_retry(*, item_name: str, postal_code: str, source_config: dict[str, Any], timeout: int) -> tuple[dict[str, Any], str]:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return fetch_flipp_search(
                item_name=item_name,
                postal_code=postal_code,
                locale=str(source_config.get("locale", "en-ca")),
                base_url=str(source_config.get("base_url", "")),
                timeout_seconds=timeout,
            )
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                delay = max(float(retry_after), 0.5 * (2**attempt))
            except ValueError:
                delay = 0.5 * (2**attempt)
            time.sleep(min(delay, 8.0))
        except (URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.5 * (2**attempt))
    if last_error:
        raise last_error
    raise RuntimeError("price source did not return a response")


def _scrape_once(args: argparse.Namespace) -> int:
    source_config = _load_json(PROJECT_ROOT / args.sources)
    items = _catalog_items(PROJECT_ROOT / args.catalog, max(1, args.max_items))
    postal_codes = [
        str(value).upper().replace(" ", "")
        for value in source_config.get("postal_codes", [])
        if str(value).strip()
    ]
    allowed_chains = [str(value).strip() for value in source_config.get("chains", []) if str(value).strip()]
    if not items or not postal_codes or not allowed_chains:
        print("Source configuration must define catalog items, postal_codes, and chains.")
        return 1

    quotes: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    started_at = datetime.now(UTC)
    for postal_code in postal_codes:
        for item in items:
            try:
                payload, source_url = _fetch_with_retry(
                    item_name=item["name"],
                    postal_code=postal_code,
                    source_config=source_config,
                    timeout=max(2, int(args.timeout_seconds)),
                )
                parsed = parse_flipp_quotes(
                    payload,
                    requested_item=item["name"],
                    item_category=item["category"],
                    source_url=source_url,
                    include_ecommerce=bool(source_config.get("include_ecommerce", True)),
                )
            except Exception as exc:
                failures.append({"item_name": item["name"], "postal_code": postal_code, "error": type(exc).__name__})
                continue
            for row in parsed:
                if not any(chain_matches(chain, str(row.get("store_chain", ""))) for chain in allowed_chains):
                    continue
                row.update({"postal_code": postal_code, "country": "CA"})
                quotes.append(row)
            time.sleep(max(0.0, float(source_config.get("request_delay_seconds", 0.15))))

    deduped = _dedupe_quotes(quotes, max_variants=max(1, int(args.max_variants)))
    generated_at = datetime.now(UTC)
    chains_with_quotes = sorted({str(row["store_chain"]) for row in deduped})
    payload = {
        "schema_version": 2,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (generated_at + timedelta(hours=48)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "flipp_public_structured_search",
        "acquisition": {
            "method": "structured_json",
            "base_url": source_config.get("base_url"),
            "requires_api_key": False,
            "retailer_direct_catalogs": "not_configured",
        },
        "quote_count": len(deduped),
        "quotes": deduped,
        "diagnostics": {
            "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
            "query_count": len(items) * len(postal_codes),
            "query_failures": failures,
            "catalog_item_count": len(items),
            "postal_codes": postal_codes,
            "configured_chains": allowed_chains,
            "chains_with_quotes": chains_with_quotes,
        },
    }
    errors = validate_snapshot(payload, min_quotes=max(1, int(args.min_quotes)))
    if errors:
        print("Snapshot validation failed; the existing snapshot was not overwritten.")
        for error in errors:
            print(f"- {error}")
        return 1

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(deduped)} verified current quotes from {len(chains_with_quotes)} chains to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a verified current-price snapshot from structured Flipp data.")
    parser.add_argument("--sources", default="config/live_pricing/free_scrape_sources.json")
    parser.add_argument("--catalog", default="config/catalog.json")
    parser.add_argument("--output", default="config/live_pricing/snapshots/latest.json")
    parser.add_argument("--max-items", type=int, default=30)
    parser.add_argument("--max-variants", type=int, default=4)
    parser.add_argument("--min-quotes", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=21600)
    args = parser.parse_args()

    if args.validate_only:
        errors = validate_snapshot(_load_json(PROJECT_ROOT / args.output), max(1, args.min_quotes))
        if errors:
            print("\n".join(errors))
            return 1
        print("Snapshot is valid.")
        return 0

    if not args.loop:
        return _scrape_once(args)
    while True:
        _scrape_once(args)
        time.sleep(max(300, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
