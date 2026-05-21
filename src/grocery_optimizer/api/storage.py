from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(os.getenv("GROCERY_DB_PATH", "data/grocery_optimizer.db"))
DEFAULT_TOKEN_TTL_MINUTES = int(os.getenv("GROCERY_TOKEN_TTL_MINUTES", "10080"))
SCHEMA_VERSION = 3


class _PostgresCursorAdapter:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", 0))

    def fetchone(self) -> dict[str, Any] | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._cursor.fetchall())


class _PostgresConnectionAdapter:
    driver = "postgresql"

    def __init__(self, raw: Any):
        self._raw = raw

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()) -> _PostgresCursorAdapter:
        cursor = self._raw.execute(query.replace("?", "%s"), tuple(params))
        return _PostgresCursorAdapter(cursor)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


def _database_url() -> str:
    return os.getenv("GROCERY_DATABASE_URL", "").strip()


def _is_postgres_url(value: str) -> bool:
    return value.startswith(("postgresql://", "postgres://"))


def _sqlite_path_from_url(value: str) -> Path | None:
    if not value.startswith("sqlite:///"):
        return None
    return Path(value.removeprefix("sqlite:///"))


def database_strategy(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    url = _database_url()
    if _is_postgres_url(url):
        return {
            "driver": "postgresql",
            "source": "GROCERY_DATABASE_URL",
            "managed_backups_required": True,
        }

    sqlite_url_path = _sqlite_path_from_url(url)
    path = sqlite_url_path or Path(db_path)
    return {
        "driver": "sqlite",
        "source": "GROCERY_DATABASE_URL" if sqlite_url_path else "GROCERY_DB_PATH",
        "path": str(path),
        "wal_enabled": True,
        "single_instance_recommended": True,
    }


def _connect(db_path: str | Path = DEFAULT_DB_PATH) -> Any:
    url = _database_url()
    if _is_postgres_url(url):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL storage requires installing psycopg[binary].") from exc
        return _PostgresConnectionAdapter(psycopg.connect(url, row_factory=dict_row))

    sqlite_url_path = _sqlite_path_from_url(url)
    path = sqlite_url_path or Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def _ensure_schema_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    if getattr(conn, "driver", "sqlite") == "postgresql":
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
            ("schema_version", "0"),
        )
    else:
        conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', '0')")


def _get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        return 0
    return int(row["value"])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'schema_version'", (str(version),))


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if getattr(conn, "driver", "sqlite") == "postgresql":
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
    else:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _apply_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    if current_version < 1:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                label TEXT NOT NULL,
                request_payload TEXT NOT NULL,
                result_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        _set_schema_version(conn, 1)
        current_version = 1

    if current_version < 2:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_user_id ON user_tokens(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_token_hash ON user_tokens(token_hash)")
        _set_schema_version(conn, 2)
        current_version = 2

    if current_version < 3:
        columns = _table_columns(conn, "users")
        if "password_hash" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        _set_schema_version(conn, 3)


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with closing(_connect(db_path)) as conn:
        _ensure_schema_meta(conn)
        current_version = _get_schema_version(conn)
        _apply_migrations(conn, current_version)
        conn.commit()


# ---------------------------------------------------------------------------
# Module-level initialization cache.  ``_ensure_initialized`` guarantees that
# ``init_db`` is invoked at most once per unique *db_path* per process
# lifetime.  The public ``init_db`` function remains available for explicit
# calls from tests or application startup code.
# ---------------------------------------------------------------------------
_initialized: dict[str, bool] = {}


def _database_key(db_path: str | Path = DEFAULT_DB_PATH) -> str:
    url = _database_url()
    if url:
        return url
    return str(db_path)


def _ensure_initialized(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    key = _database_key(db_path)
    if key not in _initialized:
        init_db(db_path)
        _initialized[key] = True


def create_user(
    name: str,
    email: str,
    password_hash: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    _ensure_initialized(db_path)
    user_id = str(uuid.uuid4())
    created_at = datetime.now(tz=UTC).isoformat()

    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, email.lower().strip(), password_hash, created_at),
        )
        conn.commit()

    return {"id": user_id, "name": name, "email": email.lower().strip(), "created_at": created_at}


def get_user(user_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return dict(row)


def get_user_by_email(email: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def get_user_auth_by_email(email: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, name, email, password_hash, created_at FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def save_plan(
    user_id: str,
    label: str,
    request_payload: dict[str, Any],
    result_payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    _ensure_initialized(db_path)
    plan_id = str(uuid.uuid4())
    created_at = datetime.now(tz=UTC).isoformat()

    with closing(_connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO plans (id, user_id, label, request_payload, result_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                label,
                json.dumps(request_payload),
                json.dumps(result_payload),
                created_at,
            ),
        )
        conn.commit()

    return {"id": plan_id, "user_id": user_id, "label": label, "created_at": created_at}


def list_user_plans(
    user_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    _ensure_initialized(db_path)
    query = (
        """
        SELECT id, user_id, label, request_payload, result_payload, created_at
        FROM plans
        WHERE user_id = ?
        ORDER BY created_at DESC
        """
    )
    params: list[Any] = [user_id]
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([max(limit, 1), max(offset, 0)])

    with closing(_connect(db_path)) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    plans: list[dict[str, Any]] = []
    for row in rows:
        plans.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "label": row["label"],
                "request": json.loads(row["request_payload"]),
                "result": json.loads(row["result_payload"]),
                "created_at": row["created_at"],
            }
        )
    return plans


def count_user_plans(user_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> int:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM plans WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["count"]) if row is not None else 0


def get_user_plan(user_id: str, plan_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, label, request_payload, result_payload, created_at
            FROM plans
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, plan_id),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "label": row["label"],
        "request": json.loads(row["request_payload"]),
        "result": json.loads(row["result_payload"]),
        "created_at": row["created_at"],
    }


def delete_user_plan(user_id: str, plan_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            "DELETE FROM plans WHERE id = ? AND user_id = ?",
            (plan_id, user_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def update_user_plan_label(
    user_id: str,
    plan_id: str,
    label: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bool:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE plans SET label = ? WHERE id = ? AND user_id = ?",
            (label, plan_id, user_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_user_token(
    user_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    ttl_minutes: int | None = DEFAULT_TOKEN_TTL_MINUTES,
) -> str:
    _ensure_initialized(db_path)
    token_id = str(uuid.uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    created_at = datetime.now(tz=UTC).isoformat()
    expires_at = None
    if ttl_minutes is not None:
        expires_at = (datetime.now(tz=UTC) + timedelta(minutes=ttl_minutes)).isoformat()

    with closing(_connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO user_tokens (id, user_id, token_hash, created_at, expires_at, revoked)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (token_id, user_id, token_hash, created_at, expires_at),
        )
        conn.commit()

    return raw_token


def validate_user_token(user_id: str, raw_token: str, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    _ensure_initialized(db_path)
    token_hash = _hash_token(raw_token)

    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM user_tokens
            WHERE user_id = ?
              AND token_hash = ?
              AND revoked = 0
              AND (expires_at IS NULL OR expires_at > ?)
            LIMIT 1
            """,
            (user_id, token_hash, datetime.now(tz=UTC).isoformat()),
        ).fetchone()

    return row is not None


def revoke_user_token(user_id: str, raw_token: str, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    _ensure_initialized(db_path)
    token_hash = _hash_token(raw_token)

    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE user_tokens
            SET revoked = 1
            WHERE user_id = ?
              AND token_hash = ?
              AND revoked = 0
            """,
            (user_id, token_hash),
        )
        conn.commit()

    return cursor.rowcount > 0


def revoke_all_user_tokens(user_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> int:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE user_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0",
            (user_id,),
        )
        conn.commit()

    return cursor.rowcount


def cleanup_tokens(
    db_path: str | Path = DEFAULT_DB_PATH,
    keep_revoked_days: int = 30,
) -> int:
    _ensure_initialized(db_path)
    cutoff = (datetime.now(tz=UTC) - timedelta(days=keep_revoked_days)).isoformat()

    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            """
            DELETE FROM user_tokens
            WHERE (revoked = 1 AND created_at < ?)
               OR (expires_at IS NOT NULL AND expires_at < ?)
            """,
            (cutoff, datetime.now(tz=UTC).isoformat()),
        )
        conn.commit()
    return cursor.rowcount


def get_schema_version(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    _ensure_initialized(db_path)
    with closing(_connect(db_path)) as conn:
        return _get_schema_version(conn)


def _active_sqlite_path(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    sqlite_url_path = _sqlite_path_from_url(_database_url())
    return sqlite_url_path or Path(db_path)


def backup_database(
    db_path: str | Path = DEFAULT_DB_PATH,
    backup_dir: str | Path = "data/backups",
) -> dict[str, Any]:
    """Create a consistent SQLite backup file.

    PostgreSQL production deployments should use managed PITR/backups from the
    database provider; this local endpoint is for dev and single-instance pilots.
    """
    if _is_postgres_url(_database_url()):
        raise RuntimeError("PostgreSQL backups must be managed by the database provider.")

    _ensure_initialized(db_path)
    source_path = _active_sqlite_path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Database file not found: {source_path}")

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    target_path = target_dir / f"{source_path.stem}-{timestamp}.db"

    with closing(sqlite3.connect(source_path, timeout=10.0)) as source:
        with closing(sqlite3.connect(target_path, timeout=10.0)) as target:
            source.backup(target)

    return {
        "backed_up": True,
        "driver": "sqlite",
        "source_path": str(source_path),
        "backup_path": str(target_path),
        "size_bytes": target_path.stat().st_size,
        "created_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }
