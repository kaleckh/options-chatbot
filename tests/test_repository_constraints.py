from __future__ import annotations

import os
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

from repository_constraints import (  # noqa: E402
    constraint_manifest,
    constraints_by_enforcement,
)
from repository_migrations import migration_manifest  # noqa: E402
from scripts.audit_repository_constraints import (  # noqa: E402
    audit_postgres_tracked_positions,
    audit_sqlite_suggested_trades,
)
from positions_repository import SqliteTrackedPositionsRepository  # noqa: E402
from suggested_trades_repository import SQLiteSuggestedTradesRepository  # noqa: E402


class RepositoryConstraintTests(unittest.TestCase):
    def test_constraint_manifest_separates_enforcement_layers(self):
        manifest = constraint_manifest()
        ids = [entry["constraint_id"] for entry in manifest]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(constraints_by_enforcement("db_enforced"))
        self.assertTrue(constraints_by_enforcement("api_service_enforced"))
        self.assertTrue(constraints_by_enforcement("proof_contract_owned"))
        self.assertTrue(constraints_by_enforcement("deferred"))
        self.assertIn("proof_truth_not_sql", ids)
        self.assertIn("candidate_check_constraints", ids)

    def test_constraint_manifest_covers_migration_ledgers_for_all_migration_stores(self):
        migration_stores = {entry["store_id"] for entry in migration_manifest()}
        ledger_stores = {
            entry["store_id"]
            for entry in constraint_manifest()
            if entry["table"] == "repository_schema_migrations"
            and entry["enforcement"] == "db_enforced"
        }

        self.assertEqual(ledger_stores, migration_stores)

    def test_docs_name_constraint_owner_and_boundaries(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "repository": (ROOT / "docs" / "repository-contract.md").read_text(encoding="utf-8"),
            "migrations": (ROOT / "docs" / "repository-migrations.md").read_text(encoding="utf-8"),
            "constraints": (ROOT / "docs" / "repository-constraints.md").read_text(encoding="utf-8"),
        }
        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("repository_constraints.py", text)
                self.assertIn("repository-constraints.md", text)

        constraints_doc = docs["constraints"]
        self.assertIn("Proof-contract-owned", constraints_doc)
        self.assertIn("Do not encode production proof as a DB constraint", constraints_doc)
        self.assertIn("SQLite table-level `CHECK` constraints require a table rebuild", constraints_doc)
        self.assertIn("Postgres `NOT VALID` checks also affect future updates", constraints_doc)

    def test_suggested_trades_repository_enforces_declared_review_foreign_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with repo._connect() as conn:  # noqa: SLF001 - verifying repository connection constraints.
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        """
                        INSERT INTO suggested_trade_reviews
                            (position_id, reviewed_at, recommendation, reason)
                        VALUES (?, ?, ?, ?)
                        """,
                        (999, "2026-06-04T10:00:00Z", "HOLD", "orphan review"),
                    )

    def test_sqlite_tracked_legacy_repository_enforces_declared_review_foreign_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tracked.db")
            repo = SqliteTrackedPositionsRepository(db_path)
            self.assertTrue(repo.init_schema())

            with repo._connect() as conn:  # noqa: SLF001 - verifying repository connection constraints.
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        """
                        INSERT INTO position_reviews
                            (position_id, reviewed_at, recommendation, reason)
                        VALUES (?, ?, ?, ?)
                        """,
                        (999, "2026-06-04T10:00:00Z", "HOLD", "orphan review"),
                    )

    def test_constraint_audit_passes_clean_initialized_sqlite_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            audit = audit_sqlite_suggested_trades(db_path)

        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["violations"], [])

    def test_constraint_audit_skips_missing_sqlite_without_creating_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "missing.db")

            audit = audit_sqlite_suggested_trades(db_path)
            exists_after_audit = os.path.exists(db_path)

        self.assertEqual(audit["status"], "skipped")
        self.assertIn("not found", audit["reason"])
        self.assertFalse(exists_after_audit)

    def test_constraint_audit_reports_sqlite_row_shape_violations_without_repairing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO suggested_trades (
                        id,
                        status,
                        ticker,
                        direction,
                        strike,
                        expiry,
                        contracts,
                        entry_option_price,
                        entry_execution_price,
                        entry_fee_total_usd,
                        filled_at,
                        stop_loss_pct,
                        profit_target_pct,
                        time_exit_day,
                        source_pick_snapshot,
                        exit_option_price,
                        exit_execution_price,
                        fee_total_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "maybe",
                        "",
                        "sideways",
                        -1.0,
                        "2026-06-19",
                        0,
                        -4.0,
                        0.0,
                        -0.65,
                        "2026-06-04T10:00:00Z",
                        0.0,
                        0.0,
                        0,
                        "{}",
                        -0.01,
                        -0.01,
                        -1.30,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO suggested_trade_reviews (
                        position_id,
                        reviewed_at,
                        recommendation,
                        reason,
                        current_option_price,
                        entry_execution_price,
                        exit_execution_price,
                        fee_total_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "2026-06-04T10:05:00Z",
                        "WAIT",
                        "invalid review shape",
                        -1.0,
                        0.0,
                        -0.01,
                        -1.30,
                    ),
                )
                conn.commit()

            audit = audit_sqlite_suggested_trades(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                trade_count = conn.execute("SELECT COUNT(*) FROM suggested_trades").fetchone()[0]
                review_count = conn.execute("SELECT COUNT(*) FROM suggested_trade_reviews").fetchone()[0]

        violations = {entry["constraint_id"]: entry["count"] for entry in audit["violations"]}
        self.assertEqual(audit["status"], "violations_found")
        self.assertEqual(violations["suggested_trades_status"], 1)
        self.assertEqual(violations["suggested_trades_direction"], 1)
        self.assertEqual(violations["suggested_trades_ticker"], 1)
        self.assertEqual(violations["suggested_trades_positive_required_numbers"], 1)
        self.assertEqual(violations["suggested_trades_nonnegative_nullable_numbers"], 1)
        self.assertEqual(violations["suggested_trade_reviews_recommendation"], 1)
        self.assertEqual(violations["suggested_trade_reviews_nonnegative_nullable_numbers"], 1)
        self.assertEqual(trade_count, 1)
        self.assertEqual(review_count, 1)

    def test_constraint_audit_reports_sqlite_orphan_without_mutating(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO suggested_trade_reviews
                        (position_id, reviewed_at, recommendation, reason)
                    VALUES (?, ?, ?, ?)
                    """,
                    (999, "2026-06-04T10:00:00Z", "HOLD", "orphan review"),
                )
                conn.commit()

            audit = audit_sqlite_suggested_trades(db_path)

        self.assertEqual(audit["status"], "violations_found")
        self.assertIn(
            {"constraint_id": "suggested_trade_reviews_orphan_position", "count": 1},
            audit["violations"],
        )

    def test_constraint_audit_reports_closed_sqlite_trade_missing_realized_pnl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO suggested_trades (
                        id,
                        status,
                        ticker,
                        direction,
                        strike,
                        expiry,
                        contracts,
                        entry_option_price,
                        entry_execution_price,
                        entry_fee_total_usd,
                        filled_at,
                        stop_loss_pct,
                        profit_target_pct,
                        time_exit_day,
                        source_pick_snapshot,
                        closed_at,
                        exit_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "closed",
                        "SPY",
                        "call",
                        740.0,
                        "2026-06-19",
                        1,
                        4.0,
                        4.0,
                        1.3,
                        "2026-06-04T10:00:00Z",
                        90.0,
                        150.0,
                        5,
                        "{}",
                        "2026-06-05T10:00:00Z",
                        "test_closed_without_pnl",
                    ),
                )
                conn.commit()

            audit = audit_sqlite_suggested_trades(db_path)

        self.assertEqual(audit["status"], "violations_found")
        self.assertIn(
            {"constraint_id": "suggested_trades_closed_missing_realized_pnl", "count": 1},
            audit["violations"],
        )

    def test_postgres_constraint_audit_skips_without_database_url(self):
        audit = audit_postgres_tracked_positions(None)

        self.assertEqual(audit["status"], "skipped")
        self.assertIn("DATABASE_URL", audit["reason"])


if __name__ == "__main__":
    unittest.main()
