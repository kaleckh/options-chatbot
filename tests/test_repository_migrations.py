from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from positions_repository import PostgresTrackedPositionsRepository, SqliteTrackedPositionsRepository
from repository_migrations import (
    MIGRATION_LEDGER_TABLE,
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
    SQLITE_TRACKED_POSITIONS_STORE_ID,
    apply_postgres_repository_migrations,
    apply_sqlite_repository_migrations,
    migration_manifest,
    repository_migrations_for_store,
)
from suggested_trades_repository import SQLiteSuggestedTradesRepository


class _FakeCursor:
    def __init__(self, fetchone_results=None):
        self.executed: list[tuple[str, object]] = []
        self.fetchone_results = list(fetchone_results or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


class RepositoryMigrationTests(unittest.TestCase):
    def test_baseline_migration_checksums_are_stable(self):
        baselines = {
            (entry["store_id"], entry["migration_id"]): entry["checksum"]
            for entry in migration_manifest()
        }
        expected = {
            (
                POSTGRES_TRACKED_POSITIONS_STORE_ID,
                "tracked_positions_postgres_0001_current_schema_baseline",
            ): "4e912465f3325b99265de59c2b99f886775d146bd8dd58338ad6fe0f73aef21b",
            (
                SQLITE_TRACKED_POSITIONS_STORE_ID,
                "tracked_positions_sqlite_0001_current_schema_baseline",
            ): "a3a07a0e25c74c853c0a285398e9b5544ee857616418d728ff13a58004d2deff",
            (
                SQLITE_SUGGESTED_TRADES_STORE_ID,
                "suggested_trades_sqlite_0001_current_schema_baseline",
            ): "d318e2cf4bc5f69a3966e500c3932f2b365acdc5ac1c7d785b9fc9dbf9b0b48f",
        }

        for key, checksum in expected.items():
            with self.subTest(store_id=key[0], migration_id=key[1]):
                self.assertEqual(baselines[key], checksum)

    def test_migration_manifest_versions_are_ordered_per_store(self):
        versions_by_store: dict[str, list[int]] = {}
        for entry in migration_manifest():
            match = re.search(r"_(\d{4})_", entry["migration_id"])
            self.assertIsNotNone(match, entry["migration_id"])
            versions_by_store.setdefault(entry["store_id"], []).append(int(match.group(1)))

        for store_id, versions in versions_by_store.items():
            with self.subTest(store_id=store_id):
                self.assertEqual(versions, sorted(versions))
                self.assertEqual(len(versions), len(set(versions)))

    def test_manifest_has_unique_expected_store_migrations(self):
        manifest = migration_manifest()
        keys = {(entry["store_id"], entry["migration_id"]) for entry in manifest}

        self.assertEqual(len(keys), len(manifest))
        self.assertEqual(
            {entry["store_id"] for entry in manifest},
            {
                POSTGRES_TRACKED_POSITIONS_STORE_ID,
                SQLITE_TRACKED_POSITIONS_STORE_ID,
                SQLITE_SUGGESTED_TRADES_STORE_ID,
            },
        )
        for entry in manifest:
            self.assertRegex(entry["migration_id"], r"_0001_current_schema_baseline$")
            self.assertIn(entry["dialect"], {"postgres", "sqlite"})
            self.assertGreater(len(entry["checksum"]), 40)
            self.assertTrue(entry["tables"])

    def test_sqlite_unknown_store_migration_fails_without_creating_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "unknown.db")
            with closing(sqlite3.connect(db_path)) as conn:
                with self.assertRaises(ValueError):
                    apply_sqlite_repository_migrations(conn, "unknown_store")
                table_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (MIGRATION_LEDGER_TABLE,),
                ).fetchone()

        self.assertIsNone(table_exists)

    def test_sqlite_suggested_trades_records_baseline_idempotently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)

            self.assertTrue(repo.init_schema())
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                rows = conn.execute(
                    f"""
                    SELECT store_id, migration_id, checksum
                    FROM {MIGRATION_LEDGER_TABLE}
                    WHERE store_id = ?
                    """,
                    (SQLITE_SUGGESTED_TRADES_STORE_ID,),
                ).fetchall()

        expected = repository_migrations_for_store(SQLITE_SUGGESTED_TRADES_STORE_ID)
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(rows[0][1], expected[0].migration_id)
        self.assertEqual(rows[0][2], expected[0].checksum)

    def test_sqlite_tracked_positions_records_test_legacy_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tracked.db")
            repo = SqliteTrackedPositionsRepository(db_path)

            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                store_ids = {
                    row[0]
                    for row in conn.execute(
                        f"SELECT store_id FROM {MIGRATION_LEDGER_TABLE}"
                    ).fetchall()
                }

        self.assertEqual(store_ids, {SQLITE_TRACKED_POSITIONS_STORE_ID})

    def test_sqlite_migration_ledger_primary_key_rejects_duplicate_rows(self):
        repositories = (
            (SQLITE_TRACKED_POSITIONS_STORE_ID, SqliteTrackedPositionsRepository, "tracked.db"),
            (SQLITE_SUGGESTED_TRADES_STORE_ID, SQLiteSuggestedTradesRepository, "suggested.db"),
        )

        for store_id, repository_cls, filename in repositories:
            with self.subTest(store_id=store_id), tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, filename)
                repo = repository_cls(db_path)
                self.assertTrue(repo.init_schema())
                migration = repository_migrations_for_store(store_id)[0]

                with closing(sqlite3.connect(db_path)) as conn:
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(
                            f"""
                            INSERT INTO {MIGRATION_LEDGER_TABLE}
                                (store_id, migration_id, checksum, description, dialect, tables)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                migration.store_id,
                                migration.migration_id,
                                migration.checksum,
                                migration.description,
                                migration.dialect,
                                ",".join(migration.tables),
                            ),
                        )

    def test_sqlite_legacy_suggested_schema_upgrades_and_records_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy_suggested.db")
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE suggested_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        status TEXT NOT NULL DEFAULT 'open',
                        ticker TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        strike REAL NOT NULL,
                        expiry TEXT NOT NULL,
                        contracts INTEGER NOT NULL,
                        entry_option_price REAL NOT NULL,
                        filled_at TEXT NOT NULL,
                        stop_loss_pct REAL NOT NULL,
                        profit_target_pct REAL NOT NULL,
                        time_exit_day INTEGER NOT NULL,
                        source_pick_snapshot TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE suggested_trade_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position_id INTEGER NOT NULL,
                        reviewed_at TEXT NOT NULL,
                        recommendation TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )

            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(suggested_trades)").fetchall()
                }
                ledger_count = conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {MIGRATION_LEDGER_TABLE}
                    WHERE store_id = ?
                    """,
                    (SQLITE_SUGGESTED_TRADES_STORE_ID,),
                ).fetchone()[0]

        self.assertIn("entry_underlying_price", columns)
        self.assertEqual(ledger_count, 1)

    def test_sqlite_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            migration = repository_migrations_for_store(SQLITE_SUGGESTED_TRADES_STORE_ID)[0]
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    f"""
                    UPDATE {MIGRATION_LEDGER_TABLE}
                    SET checksum = 'wrong-checksum'
                    WHERE store_id = ? AND migration_id = ?
                    """,
                    (migration.store_id, migration.migration_id),
                )
                conn.commit()

            drifted_repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertFalse(drifted_repo.init_schema())
            self.assertFalse(drifted_repo.is_available)
            self.assertIn("checksum mismatch", drifted_repo.error_message or "")

    def test_sqlite_tracked_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tracked.db")
            repo = SqliteTrackedPositionsRepository(db_path)
            self.assertTrue(repo.init_schema())

            migration = repository_migrations_for_store(SQLITE_TRACKED_POSITIONS_STORE_ID)[0]
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    f"""
                    UPDATE {MIGRATION_LEDGER_TABLE}
                    SET checksum = 'wrong-checksum'
                    WHERE store_id = ? AND migration_id = ?
                    """,
                    (migration.store_id, migration.migration_id),
                )
                conn.commit()

            drifted_repo = SqliteTrackedPositionsRepository(db_path)
            self.assertFalse(drifted_repo.init_schema())
            self.assertFalse(drifted_repo.is_available)
            self.assertIn("checksum mismatch", drifted_repo.error_message or "")

    def test_postgres_checksum_mismatch_fails_closed(self):
        fake_cursor = _FakeCursor(fetchone_results=[{"checksum": "wrong-checksum"}])

        with self.assertRaises(RuntimeError) as ctx:
            apply_postgres_repository_migrations(fake_cursor, POSTGRES_TRACKED_POSITIONS_STORE_ID)

        self.assertIn("checksum mismatch", str(ctx.exception))

    def test_postgres_init_schema_records_migration_ledger_sql(self):
        fake_connection = _FakeConnection()
        repo = PostgresTrackedPositionsRepository("postgresql://example/test")
        repo.is_available = True
        repo.error_message = None
        repo._connect = lambda: fake_connection  # type: ignore[method-assign]

        self.assertTrue(repo.init_schema())

        sql_statements = [sql for sql, _params in fake_connection.cursor_obj.executed]
        self.assertIn("CREATE TABLE IF NOT EXISTS tracked_positions", sql_statements[0])
        self.assertTrue(
            any(f"CREATE TABLE IF NOT EXISTS {MIGRATION_LEDGER_TABLE}" in sql for sql in sql_statements)
        )
        self.assertTrue(
            any(f"INSERT INTO {MIGRATION_LEDGER_TABLE}" in sql for sql in sql_statements)
        )
        self.assertTrue(
            any(params and POSTGRES_TRACKED_POSITIONS_STORE_ID in params for _sql, params in fake_connection.cursor_obj.executed)
        )

    def test_docs_name_repository_migration_owner_and_exclusions(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "repository": (ROOT / "docs" / "repository-contract.md").read_text(encoding="utf-8"),
            "migration": (ROOT / "docs" / "repository-migrations.md").read_text(encoding="utf-8"),
        }

        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("repository_migrations.py", text)
                self.assertIn("repository-migrations.md", text)

        migration_doc = docs["migration"]
        self.assertIn("data/options-validation/options_history.db", migration_doc)
        self.assertIn("data/ai-commodity-infra/", migration_doc)
        self.assertIn("No Alembic", migration_doc)
        self.assertIn("no silent tracked-position SQLite fallback", migration_doc)


if __name__ == "__main__":
    unittest.main()
