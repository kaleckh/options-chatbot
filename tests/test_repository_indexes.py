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

from repository_indexes import (  # noqa: E402
    index_manifest,
    indexes_by_status,
)
from scripts.audit_repository_indexes import (  # noqa: E402
    audit_postgres_tracked_indexes,
    audit_sqlite_suggested_indexes,
)
from suggested_trades_repository import SQLiteSuggestedTradesRepository  # noqa: E402


class RepositoryIndexTests(unittest.TestCase):
    def test_index_manifest_names_existing_and_deferred_read_paths(self):
        manifest = index_manifest()
        ids = [entry["index_id"] for entry in manifest]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(indexes_by_status("db_existing"))
        self.assertTrue(indexes_by_status("candidate_deferred"))
        self.assertTrue(all(not bool(entry["unique"]) for entry in manifest))
        for entry in manifest:
            self.assertTrue(entry["supports"], entry["index_id"])
            self.assertIn(entry["status"], {"db_existing", "candidate_deferred"})

    def test_docs_name_index_owner_and_boundaries(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "migrations": (ROOT / "docs" / "repository-migrations.md").read_text(encoding="utf-8"),
            "constraints": (ROOT / "docs" / "repository-constraints.md").read_text(encoding="utf-8"),
            "indexes": (ROOT / "docs" / "repository-indexes.md").read_text(encoding="utf-8"),
        }
        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("repository_indexes.py", text)
                self.assertIn("repository-indexes.md", text)

        index_doc = docs["indexes"]
        self.assertIn("Indexes are read-path and performance support", index_doc)
        self.assertIn("Do not treat indexes as constraints", index_doc)
        self.assertIn("Do not add new Postgres index DDL in Point 13", index_doc)
        self.assertIn("proof_eligible", index_doc)

    def test_sqlite_suggested_index_audit_passes_on_initialized_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            audit = audit_sqlite_suggested_indexes(db_path)

        self.assertEqual(audit["status"], "pass")
        self.assertIn("idx_suggested_trades_status", audit["observed_indexes"])
        self.assertIn("idx_suggested_trades_filled_at", audit["observed_indexes"])
        self.assertIn("idx_suggested_trade_reviews_position_id", audit["observed_indexes"])

    def test_sqlite_suggested_index_audit_reports_missing_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "missing_index.db")
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
                    CREATE INDEX idx_suggested_trades_status
                        ON suggested_trades (status);
                    """
                )

            audit = audit_sqlite_suggested_indexes(db_path)

        self.assertEqual(audit["status"], "missing_indexes")
        missing_names = {entry["index_name"] for entry in audit["missing_indexes"]}
        self.assertIn("idx_suggested_trades_filled_at", missing_names)
        self.assertIn("idx_suggested_trade_reviews_position_id", missing_names)

    def test_postgres_index_audit_skips_without_database_url(self):
        audit = audit_postgres_tracked_indexes(None)

        self.assertEqual(audit["status"], "skipped")
        self.assertIn("DATABASE_URL", audit["reason"])


if __name__ == "__main__":
    unittest.main()
