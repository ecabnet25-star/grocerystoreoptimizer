from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _catalog_items(path: Path, max_items: int) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        category = str(row.get("category", "other")).strip().lower()
        if not name:
            continue
        output.append({"name": name, "category": category})
        if len(output) >= max_items:
            break
    return output


def _fetch_html(url: str, timeout_seconds: int = 12) -> str:
    req = Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; UniBiteFreeScraper/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="ignore")


def _fetch_json(url: str, timeout_seconds: int = 12) -> Any:
    req = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; UniBiteFreeScraper/1.0)",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="ignore"))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_price_candidates(text: str) -> list[float]:
    candidates: list[float] = []
    patterns = [
        r"\$\s*(\d+(?:\.\d{1,2})?)",
        r"\"price\"\s*:\s*\"?(\d+(?:\.\d{1,2})?)",
        r"\"salePrice\"\s*:\s*\"?(\d+(?:\.\d{1,2})?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                value = float(match.group(1))
            except (ValueError, TypeError):
                continue
            if 0.05 <= value <= 200:
                candidates.append(round(value, 2))
    return candidates


def _item_token_variants(item_name: str) -> list[str]:
    tokens = [token for token in re.findall(r"[a-z0-9]+", item_name.lower()) if len(token) >= 3]
    if not tokens:
        return []
    variants = [" ".join(tokens[:2]), tokens[0]]
    return list(dict.fromkeys([value for value in variants if value]))


def _best_price_from_html(html: str, item_name: str) -> float | None:
    compact = _normalize_space(html)
    variants = _item_token_variants(item_name)
    local_candidates: list[float] = []

    for variant in variants:
        start = 0
        variant_l = variant.lower()
        compact_l = compact.lower()
        while True:
            idx = compact_l.find(variant_l, start)
            if idx == -1:
                break
            window = compact[max(0, idx - 120): idx + 420]
            local_candidates.extend(_extract_price_candidates(window))
            start = idx + len(variant_l)

    if local_candidates:
        local_candidates.sort()
        return local_candidates[0]

    global_candidates = _extract_price_candidates(compact)
    if not global_candidates:
        return None
    global_candidates.sort()
    return global_candidates[0]


def _scrape_retailer_quotes(source_cfg: dict[str, Any], items: list[dict[str, Any]], postal_codes: list[str]) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    chain = str(source_cfg.get("chain", "")).strip()
    template = str(source_cfg.get("search_url_template", "")).strip()
    currency = str(source_cfg.get("currency", "CAD")).strip().upper()
    confidence = float(source_cfg.get("confidence", 0.74))
    if not chain or not template:
        return quotes

    for postal_code in postal_codes:
        normalized_postal = postal_code.upper().replace(" ", "")
        for item in items:
            item_name = str(item["name"])
            url = template.replace("{item_name}", quote_plus(item_name)).replace("{postal_code}", normalized_postal)
            try:
                html = _fetch_html(url)
            except Exception:
                continue
            price = _best_price_from_html(html, item_name)
            if price is None:
                continue
            quotes.append(
                {
                    "item_name": item_name,
                    "item_category": str(item.get("category", "other")),
                    "store_chain": chain,
                    "postal_code": normalized_postal,
                    "country": "CA",
                    "currency": currency,
                    "unit_price": round(price, 2),
                    "confidence": max(0.0, min(confidence, 1.0)),
                    "source_url": url,
                    "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            )
    return quotes


def _scrape_flipp_public_quotes(flyer_cfg: dict[str, Any], items: list[dict[str, Any]], postal_codes: list[str], chains: list[str]) -> list[dict[str, Any]]:
    if not bool(flyer_cfg.get("enabled", False)):
        return []

    template = str(flyer_cfg.get("search_url_template", "")).strip()
    if not template:
        return []

    currency = str(flyer_cfg.get("currency", "CAD")).strip().upper()
    confidence = float(flyer_cfg.get("confidence", 0.68))
    chain_tokens = {chain: chain.lower() for chain in chains}
    quotes: list[dict[str, Any]] = []

    for postal_code in postal_codes:
        normalized_postal = postal_code.upper().replace(" ", "")
        for item in items:
            item_name = str(item["name"])
            url = (
                template.replace("{item_name}", quote_plus(item_name))
                .replace("{postal_code}", normalized_postal)
            )
            try:
                html = _fetch_html(url)
            except Exception:
                continue

            compact = _normalize_space(html)
            compact_l = compact.lower()
            for chain, token in chain_tokens.items():
                if token not in compact_l:
                    continue
                idx = compact_l.find(token)
                window = compact[max(0, idx - 200): idx + 500]
                price = _best_price_from_html(window, item_name)
                if price is None:
                    continue
                quotes.append(
                    {
                        "item_name": item_name,
                        "item_category": str(item.get("category", "other")),
                        "store_chain": chain,
                        "postal_code": normalized_postal,
                        "country": "CA",
                        "currency": currency,
                        "unit_price": round(price, 2),
                        "confidence": max(0.0, min(confidence, 1.0)),
                        "source_url": url,
                        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "source_type": "flipp_public_scrape",
                    }
                )
    return quotes


def _chain_alias_map(chains: list[str]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {
        "metro": ["metro", "metro inc"],
        "iga": ["iga"],
        "maxi": ["maxi"],
        "provigo": ["provigo"],
        "super c": ["super c", "superc"],
    }
    result: dict[str, list[str]] = {}
    for chain in chains:
        key = chain.strip().lower()
        result[chain] = aliases.get(key, [key])
    return result


def _extract_off_price(product: dict[str, Any]) -> float | None:
    direct = product.get("price")
    try:
        if direct is not None:
            value = float(str(direct).replace(",", ""))
            if 0.05 <= value <= 200:
                return round(value, 2)
    except (TypeError, ValueError):
        pass

    prices = product.get("prices", [])
    if isinstance(prices, list):
        for item in prices:
            if isinstance(item, dict):
                candidate = item.get("price")
            else:
                candidate = item
            try:
                value = float(str(candidate).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if 0.05 <= value <= 200:
                return round(value, 2)
    return None


def _scrape_openfoodfacts_quotes(items: list[dict[str, Any]], postal_codes: list[str], chains: list[str]) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    alias_map = _chain_alias_map(chains)
    country_tag = "en:canada"

    for item in items:
        item_name = str(item["name"])
        query = urlencode(
            {
                "search_terms": item_name,
                "search_simple": "1",
                "action": "process",
                "json": "1",
                "page_size": "40",
                "tagtype_0": "countries",
                "tag_contains_0": "contains",
                "tag_0": country_tag,
                "fields": "product_name,stores,stores_tags,price,prices",
            }
        )
        url = f"https://world.openfoodfacts.org/cgi/search.pl?{query}"
        try:
            payload = _fetch_json(url)
        except Exception:
            continue

        products = payload.get("products", []) if isinstance(payload, dict) else []
        if not isinstance(products, list):
            continue

        for product in products:
            if not isinstance(product, dict):
                continue
            price = _extract_off_price(product)
            if price is None:
                continue

            store_text = str(product.get("stores", "")).lower()
            tags = product.get("stores_tags", [])
            tags_joined = " ".join(tag.lower() for tag in tags if isinstance(tag, str))
            haystack = f"{store_text} {tags_joined}"

            for chain in chains:
                aliases = alias_map.get(chain, [chain.lower()])
                if not any(alias in haystack for alias in aliases):
                    continue
                for postal_code in postal_codes:
                    quotes.append(
                        {
                            "item_name": item_name,
                            "item_category": str(item.get("category", "other")),
                            "store_chain": chain,
                            "postal_code": postal_code.upper().replace(" ", ""),
                            "country": "CA",
                            "currency": "CAD",
                            "unit_price": round(price, 2),
                            "confidence": 0.66,
                            "source_url": url,
                            "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                            "source_type": "openfoodfacts_public",
                        }
                    )
    return quotes


def _dedupe_quotes(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in quotes:
        item_name = str(row.get("item_name", "")).strip().lower()
        chain = str(row.get("store_chain", "")).strip().lower()
        postal = str(row.get("postal_code", "")).strip().upper().replace(" ", "")
        if not item_name or not chain or not postal:
            continue
        key = (item_name, chain, postal)
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        current_conf = float(current.get("confidence", 0.0))
        new_conf = float(row.get("confidence", 0.0))
        current_price = float(current.get("unit_price", 10_000.0))
        new_price = float(row.get("unit_price", 10_000.0))
        if new_conf > current_conf or (new_conf == current_conf and new_price < current_price):
            best[key] = row
    return list(best.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape free retailer and flyer pricing into local snapshots.")
    parser.add_argument("--sources", default="config/live_pricing/free_scrape_sources.json")
    parser.add_argument("--catalog", default="config/catalog.json")
    parser.add_argument("--output", default="config/live_pricing/snapshots/latest.json")
    parser.add_argument("--max-items", type=int, default=24)
    parser.add_argument("--loop", action="store_true", help="Run continuously on an interval")
    parser.add_argument("--interval-seconds", type=int, default=1800, help="Loop interval in seconds")
    args = parser.parse_args()

    def _run_once() -> int:
        source_cfg = _load_json(PROJECT_ROOT / args.sources)
        if not source_cfg:
            print("No source config found.")
            return 1

        items = _catalog_items(PROJECT_ROOT / args.catalog, max_items=max(1, args.max_items))
        if not items:
            print("No catalog items available for scraping.")
            return 1

        postal_codes = [str(pc).strip() for pc in source_cfg.get("postal_codes", []) if str(pc).strip()]
        if not postal_codes:
            postal_codes = ["H3A1A1"]

        quotes: list[dict[str, Any]] = []
        retailers = [row for row in source_cfg.get("retailers", []) if isinstance(row, dict)]
        chains: list[str] = []
        for retailer in retailers:
            chain = str(retailer.get("chain", "")).strip()
            if chain:
                chains.append(chain)
            quotes.extend(_scrape_retailer_quotes(retailer, items=items, postal_codes=postal_codes))

        flyer_cfg = source_cfg.get("flyer", {}) if isinstance(source_cfg.get("flyer", {}), dict) else {}
        quotes.extend(_scrape_flipp_public_quotes(flyer_cfg, items=items, postal_codes=postal_codes, chains=chains))
        quotes.extend(_scrape_openfoodfacts_quotes(items=items, postal_codes=postal_codes, chains=chains))

        deduped = _dedupe_quotes(quotes)

        output_path = PROJECT_ROOT / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": "free-scraper",
            "quote_count": len(deduped),
            "quotes": deduped,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved {len(deduped)} quotes to {output_path}")
        return 0

    if not args.loop:
        return _run_once()

    interval = max(60, int(args.interval_seconds))
    while True:
        _run_once()
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
