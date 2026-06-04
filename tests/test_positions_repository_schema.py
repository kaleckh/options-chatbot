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
    _PostgresConnectionPool,
    PostgresTrackedPositionsRepository,
    SqliteTrackedPositionsRepository,
    UnavailableTrackedPositionsRepository,
    create_positions_repository,
)
from options_execution import commission_total_usd, option_pnl_snapshot
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

    def fetchone(self):
        return None


class _FakeConnection:
    def __init__(self, executed_sql: list[str]):
        self.executed_sql = executed_sql

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self.executed_sql)


class _PoolConnection:
    def __init__(self):
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self.close_count = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True
        self.close_count += 1


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
    def _preclosed_payload(self) -> dict:
        entry_fee = commission_total_usd(contracts=2, sides=1)
        exit_fee = commission_total_usd(contracts=2, sides=1)
        pnl = option_pnl_snapshot(
            entry_execution_price=4.0,
            exit_execution_price=5.0,
            contracts=2,
            entry_fee_total_usd=entry_fee,
            exit_fee_total_usd=exit_fee,
        )
        return {
            "status": "closed",
            "ticker": "SPY",
            "direction": "call",
            "contract_symbol": "SPY260619C00500000",
            "strike": 500.0,
            "expiry": "2026-06-19",
            "asset_class": "equity",
            "contracts": 2,
            "entry_option_price": 4.0,
            "entry_execution_price": 4.0,
            "entry_execution_basis": "ask",
            "entry_fee_total_usd": entry_fee,
            "entry_underlying_price": 500.0,
            "filled_at": "2026-06-01T10:00:00",
            "stop_loss_pct": 90.0,
            "profit_target_pct": 150.0,
            "time_exit_day": 14,
            "peak_pnl_pct": pnl["gross_pnl_pct"],
            "last_option_price": 5.0,
            "last_pnl_pct": pnl["gross_pnl_pct"],
            "last_recommendation": "SELL",
            "last_recommendation_reason": "historical_time_exit",
            "last_reviewed_at": "2026-06-10T15:55:00",
            "source_pick_snapshot": {"ticker": "SPY", "strategy_type": "single_leg"},
            "notes": "preclosed fixture",
            "closed_at": "2026-06-10T15:55:00",
            "exit_option_price": 5.0,
            "exit_execution_price": 5.0,
            "exit_execution_basis": "bid",
            "exit_reason": "historical_time_exit",
            "gross_pnl_pct": pnl["gross_pnl_pct"],
            "net_pnl_pct": pnl["net_pnl_pct"],
            "gross_pnl_usd": pnl["gross_pnl_usd"],
            "net_pnl_usd": pnl["net_pnl_usd"],
            "fee_total_usd": pnl["fee_total_usd"],
            "proof_eligible": False,
            "proof_ineligibility_reason": None,
            "proof_class": "ineligible",
            "proof_class_reason": "test",
        }

    def test_sqlite_tracked_positions_preserves_preclosed_realized_pnl_on_create(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tracked.db")
            repo = SqliteTrackedPositionsRepository(db_path)
            self.assertTrue(repo.init_schema())

            payload = self._preclosed_payload()
            created = repo.create_position(payload)

            self.assertEqual(created["gross_pnl_pct"], payload["gross_pnl_pct"])
            self.assertEqual(created["net_pnl_pct"], payload["net_pnl_pct"])
            self.assertEqual(created["gross_pnl_usd"], payload["gross_pnl_usd"])
            self.assertEqual(created["net_pnl_usd"], payload["net_pnl_usd"])
            self.assertEqual(created["latest_review"]["net_pnl_pct"], payload["net_pnl_pct"])
            self.assertEqual(created["latest_review"]["metrics_snapshot"]["net_pnl_pct"], payload["net_pnl_pct"])

            with closing(sqlite3.connect(db_path)) as conn:
                raw = conn.execute(
                    """
                    SELECT gross_pnl_pct, net_pnl_pct, gross_pnl_usd, net_pnl_usd, fee_total_usd
                    FROM tracked_positions
                    WHERE id = ?
                    """,
                    (created["id"],),
                ).fetchone()

            self.assertEqual(raw, (
                payload["gross_pnl_pct"],
                payload["net_pnl_pct"],
                payload["gross_pnl_usd"],
                payload["net_pnl_usd"],
                payload["fee_total_usd"],
            ))

    def test_sqlite_tracked_positions_calculates_closed_pnl_from_exit_price_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tracked.db")
            repo = SqliteTrackedPositionsRepository(db_path)
            self.assertTrue(repo.init_schema())

            payload = self._preclosed_payload()
            expected_net = payload["net_pnl_pct"]
            for key in ("gross_pnl_pct", "net_pnl_pct", "gross_pnl_usd", "net_pnl_usd"):
                payload.pop(key)

            created = repo.create_position(payload)

            self.assertEqual(created["net_pnl_pct"], expected_net)
            self.assertEqual(created["latest_review"]["net_pnl_pct"], expected_net)
            self.assertEqual(created["latest_review"]["metrics_snapshot"]["pricing_state"], "closed")

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

    def test_postgres_connection_pool_reuses_successful_connections(self):
        created: list[_PoolConnection] = []

        def connect():
            conn = _PoolConnection()
            created.append(conn)
            return conn

        pool = _PostgresConnectionPool(connect, max_size=1)

        with pool.connection() as first:
            self.assertIs(first, created[0])
        with pool.connection() as second:
            self.assertIs(second, first)

        self.assertEqual(len(created), 1)
        self.assertEqual(first.commits, 2)
        self.assertEqual(first.rollbacks, 0)
        self.assertFalse(first.closed)

    def test_postgres_connection_pool_discards_failed_connections(self):
        created: list[_PoolConnection] = []

        def connect():
            conn = _PoolConnection()
            created.append(conn)
            return conn

        pool = _PostgresConnectionPool(connect, max_size=1)

        with self.assertRaises(RuntimeError):
            with pool.connection():
                raise RuntimeError("boom")
        with pool.connection() as next_conn:
            self.assertIs(next_conn, created[1])

        self.assertEqual(len(created), 2)
        self.assertEqual(created[0].rollbacks, 1)
        self.assertTrue(created[0].closed)

    def test_configured_postgres_failure_does_not_silently_fallback_to_sqlite(self):
        with patch("positions_repository.PostgresTrackedPositionsRepository", _FailingPostgresRepository):
            repo = create_positions_repository("postgresql://example/test")

        self.assertIsInstance(repo, UnavailableTrackedPositionsRepository)
        self.assertFalse(repo.is_available)
        self.assertIn("DATABASE_URL", repo.error_message)
        self.assertIn("connection refused", repo.error_message)

    def test_missing_database_url_does_not_silently_fallback_to_sqlite(self):
        repo = create_positions_repository(None)

        self.assertIsInstance(repo, UnavailableTrackedPositionsRepository)
        self.assertFalse(repo.is_available)
        self.assertIn("DATABASE_URL", repo.error_message)
        self.assertIn("Postgres", repo.error_message)

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
