import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from grocery_optimizer.api.storage import (  # noqa: E402
    cleanup_tokens,
    create_user,
    create_user_token,
    get_schema_version,
    revoke_user_token,
    validate_user_token,
)


class TestApiStorage(unittest.TestCase):
    def test_schema_version_applied(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "schema.db")
            create_user(name="Schema", email="schema@example.com", password_hash="hash", db_path=db_path)
            self.assertEqual(get_schema_version(db_path=db_path), 4)

    def test_v2_database_migrates_password_hash_column(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "legacy.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO schema_meta (key, value) VALUES ('schema_version', '2')")
            conn.execute(
                "CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE plans (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, label TEXT NOT NULL, request_payload TEXT NOT NULL, result_payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE user_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, revoked INTEGER NOT NULL DEFAULT 0)"
            )
            conn.commit()
            conn.close()

            create_user(name="Migrated", email="migrated@example.com", password_hash="hash", db_path=db_path)
            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            conn.close()

            self.assertEqual(get_schema_version(db_path=db_path), 4)
            self.assertIn("password_hash", columns)
            self.assertIn("preferences_json", columns)

    def test_token_revoke_and_expiry(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "token.db")
            user = create_user(name="Token", email="token@example.com", password_hash="hash", db_path=db_path)

            valid_token = create_user_token(user["id"], db_path=db_path, ttl_minutes=10)
            self.assertTrue(validate_user_token(user["id"], valid_token, db_path=db_path))

            revoked = revoke_user_token(user["id"], valid_token, db_path=db_path)
            self.assertTrue(revoked)
            self.assertFalse(validate_user_token(user["id"], valid_token, db_path=db_path))

            expired_token = create_user_token(user["id"], db_path=db_path, ttl_minutes=-1)
            self.assertFalse(validate_user_token(user["id"], expired_token, db_path=db_path))

            removed = cleanup_tokens(db_path=db_path, keep_revoked_days=0)
            self.assertGreaterEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()
