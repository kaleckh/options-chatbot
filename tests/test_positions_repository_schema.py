from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from positions_repository import PostgresTrackedPositionsRepository


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
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;", schema_sql)
        self.assertIn("ALTER TABLE tracked_positions\n        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS gross_pnl_pct DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS entry_execution_price DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;", schema_sql)
        self.assertIn("ALTER TABLE position_reviews\n        ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;", schema_sql)


if __name__ == "__main__":
    unittest.main()
