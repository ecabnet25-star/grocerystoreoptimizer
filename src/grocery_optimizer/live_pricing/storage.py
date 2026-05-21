from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any

PRICE_DB_PATH = os.getenv("GROCERY_LIVE_PRICING_DB", "data/live_pricing.db")

_thread_local = threading.local()


def _get_price_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating the table on first use."""
    db_path = os.getenv("GROCERY_LIVE_PRICING_DB", PRICE_DB_PATH)
    conn = getattr(_thread_local, "conn", None)
    conn_path = getattr(_thread_local, "path", None)
    if conn is None or conn_path != db_path:
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            # Another local dev process may already be writing. History storage is best-effort.
            pass
        _thread_local.conn = conn
        _thread_local.path = db_path
        _thread_local.initialized = False

    if not getattr(_thread_local, "initialized", False):
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_price_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    store_chain TEXT NOT NULL,
                    postal_code TEXT NOT NULL,
                    country TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    unit_price REAL NOT NULL,
                    confidence REAL NOT NULL,
                    fetched_at_utc TEXT NOT NULL,
                    source_url TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_live_quote_lookup ON live_price_quotes(postal_code, fetched_at_utc DESC);"
            )
        except sqlite3.OperationalError:
            pass
        _thread_local.initialized = True
    return conn


def _ensure_price_db() -> None:
    _get_price_db()


def save_live_quote(
    *,
    provider_id: str,
    item_name: str,
    store_chain: str,
    postal_code: str,
    country: str,
    currency: str,
    unit_price: float,
    confidence: float,
    fetched_at_utc: str,
    source_url: str,
) -> None:
    conn = _get_price_db()
    try:
        conn.execute(
            """
            INSERT INTO live_price_quotes (
                provider_id, item_name, store_chain, postal_code, country,
                currency, unit_price, confidence, fetched_at_utc, source_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                item_name,
                store_chain,
                postal_code,
                country,
                currency,
                unit_price,
                confidence,
                fetched_at_utc,
                source_url,
            ),
        )
    except sqlite3.OperationalError:
        return


def flush_live_quotes() -> None:
    """Compatibility hook for callers; writes are autocommitted to avoid UI-blocking locks."""
    conn = _get_price_db()
    conn.commit()


def get_live_price_history(postal_code: str, limit: int = 200) -> list[dict[str, Any]]:
    conn = _get_price_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT provider_id, item_name, store_chain, postal_code, country,
               currency, unit_price, confidence, fetched_at_utc, source_url
        FROM live_price_quotes
        WHERE postal_code = ?
        ORDER BY fetched_at_utc DESC
        LIMIT ?
        """,
        (postal_code.upper().replace(" ", ""), max(1, min(limit, 2000))),
    ).fetchall()
    return [dict(row) for row in rows]
