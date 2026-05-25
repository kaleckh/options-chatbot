from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from positions_repository import (
    PostgresTrackedPositionsRepository,
    UnavailableTrackedPositionsRepository,
    create_positions_repository,
)
from suggested_trades_repository import SQLiteSuggestedTradesRepository


class _FakeCursor:
    def __init__(self, executed_sql: list[str]):
        self.executed_sql = executed_sql

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed_sql.append(str(sql))


class _FakeConnection:
    def __init__(self, executed_sql: list[str]):
        self.executed_sql = executed_sql

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self.executed_sql)


class _FailingPostgresRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_available = True
        self.error_message = None

    def init_schema(self):
        return True

    def list_positions(self, status: str = "open"):
        raise RuntimeError("connection refused")


class PositionsRepositorySchemaTests(unittest.TestCase):
    def test_init_schema_adds_missing_review_columns_for_existing_tables(self):
        executed_sql: list[str] = []
        repo = PostgresTrackedPositionsRepository("postgresql://example/test")
        repo.is_available = True
        repo.error_message = None
        repo._connect = lambda: _FakeConnection(executed_sql)  # type: ignore[method-assign]

        self.assertTrue(repo.init_schema())
        self.assertTrue(executed_sql)
        schema_sql = executed_sql[0]
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS entry_execution_price DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS entry_underlying_price DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;", schema_sql)
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS gross_pnl_pct DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS entry_execution_price DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;", schema_sql)

    def test_configured_postgres_failure_does_not_silently_fallback_to_sqlite(self):
        with patch("positions_repository.PostgresTrackedPositionsRepository", _FailingPostgresRepository):
            repo = create_positions_repository("postgresql://example/test")

        self.assertIsInstance(repo, UnavailableTrackedPositionsRepository)
        self.assertFalse(repo.is_available)
        self.assertIn("DATABASE_URL", repo.error_message)
        self.assertIn("connection refused", repo.error_message)

    def test_suggested_trades_schema_upgrades_legacy_entry_underlying_price(self):
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
                        asset_class TEXT,
                        contracts INTEGER NOT NULL,
                        entry_option_price REAL NOT NULL,
                        filled_at TEXT NOT NULL,
                        stop_loss_pct REAL NOT NULL,
                        profit_target_pct REAL NOT NULL,
                        time_exit_day INTEGER NOT NULL,
                        peak_pnl_pct REAL,
                        last_option_price REAL,
                        last_pnl_pct REAL,
                        last_recommendation TEXT,
                        last_recommendation_reason TEXT,
                        last_reviewed_at TEXT,
                        source_pick_snapshot TEXT NOT NULL,
                        notes TEXT,
                        closed_at TEXT,
                        exit_option_price REAL,
                        exit_reason TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE suggested_trade_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position_id INTEGER NOT NULL,
                        reviewed_at TEXT NOT NULL,
                        pricing_source TEXT,
                        current_option_price REAL,
                        current_pnl_pct REAL,
                        recommendation TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        warnings TEXT NOT NULL DEFAULT '[]',
                        metrics_snapshot TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )

            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(suggested_trades)").fetchall()}

            self.assertIn("entry_underlying_price", columns)


if __name__ == "__main__":
    unittest.main()
