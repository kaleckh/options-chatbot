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

from local_db_hardening import (  # noqa: E402
    local_database_manifest,
    local_database_role,
    local_database_roles_by_mutability,
)
from scripts.audit_local_databases import (  # noqa: E402
    audit_sqlite_database,
    build_local_database_audit,
)
from suggested_trades_repository import SQLiteSuggestedTradesRepository  # noqa: E402


class LocalDbHardeningTests(unittest.TestCase):
    def test_manifest_classifies_local_database_roles(self):
        manifest = local_database_manifest()
        ids = [entry["database_id"] for entry in manifest]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(local_database_roles_by_mutability("active_mutable"))
        self.assertTrue(local_database_roles_by_mutability("test_legacy_mutable"))
        self.assertTrue(local_database_roles_by_mutability("outside_repository_scope"))
        self.assertTrue(local_database_roles_by_mutability("ignored_sidecar_or_backup"))

        suggested = local_database_role("chat_history_sqlite_suggested_trades")
        self.assertEqual(suggested.path_pattern, "chat_history.db")
        self.assertEqual(suggested.mutability, "active_mutable")
        self.assertIn("suggested_trades", suggested.expected_tables)
        self.assertIn("PRAGMA foreign_keys=ON", " ".join(suggested.expected_connection_policy))

        tracked = local_database_role("tracked_positions_sqlite_test_legacy")
        self.assertEqual(tracked.path_pattern, "data/tracked_positions.db")
        self.assertEqual(tracked.mutability, "test_legacy_mutable")
        self.assertIn("never the browser tracked-position fallback", tracked.active_scope)

    def test_manifest_marks_truth_forward_market_and_ai_stores_out_of_scope(self):
        manifest = {entry["database_id"]: entry for entry in local_database_manifest()}

        for database_id in (
            "options_history_truth_store",
            "forward_tracking_ledgers",
            "market_data_cache",
            "ai_commodity_artifacts",
        ):
            with self.subTest(database_id=database_id):
                self.assertEqual(manifest[database_id]["mutability"], "outside_repository_scope")
                self.assertIn("classified_out_of_scope", manifest[database_id]["audit_checks"])

    def test_read_only_audit_skips_missing_db_without_creating_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.db"
            audit = audit_sqlite_database(
                local_database_role("chat_history_sqlite_suggested_trades"),
                missing,
            )

            self.assertFalse(missing.exists())

        self.assertEqual(audit["status"], "skipped")
        self.assertFalse(audit["created"])
        self.assertIn("not found", audit["reason"])

    def test_read_only_audit_passes_initialized_suggested_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            repo = SQLiteSuggestedTradesRepository(str(db_path))
            self.assertTrue(repo.init_schema())

            before = db_path.stat()
            audit = audit_sqlite_database(
                local_database_role("chat_history_sqlite_suggested_trades"),
                db_path,
            )
            after = db_path.stat()

        self.assertIn(audit["status"], {"pass", "pass_with_warnings"})
        self.assertEqual(audit["quick_check"], ["ok"])
        self.assertEqual(audit["foreign_key_check_count"], 0)
        self.assertFalse(audit["missing_required_tables"])
        self.assertFalse(audit["modified_during_audit"])
        self.assertEqual(before.st_size, after.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)

    def test_read_only_audit_reports_required_table_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute("CREATE TABLE suggested_trades (id INTEGER PRIMARY KEY)")
                conn.commit()

            audit = audit_sqlite_database(
                local_database_role("chat_history_sqlite_suggested_trades"),
                db_path,
            )

        self.assertEqual(audit["status"], "issues_found")
        self.assertIn("suggested_trade_reviews", audit["missing_required_tables"])

    def test_default_build_audit_does_not_open_out_of_scope_or_legacy_databases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            suggested_db = Path(tmpdir) / "missing.db"
            audit = build_local_database_audit(sqlite_suggested_db=suggested_db)

            self.assertFalse(suggested_db.exists())

        self.assertEqual(len(audit["stores"]), 1)
        self.assertEqual(audit["stores"][0]["status"], "skipped")
        self.assertTrue(audit["rules"]["read_only"])
        self.assertFalse(audit["rules"]["creates_missing_databases"])
        out_of_scope_ids = {entry["database_id"] for entry in audit["classified_out_of_scope"]}
        self.assertIn("options_history_truth_store", out_of_scope_ids)
        self.assertIn("ai_commodity_artifacts", out_of_scope_ids)

    def test_docs_and_gitignore_name_local_db_hardening_boundaries(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "repository": (ROOT / "docs" / "repository-contract.md").read_text(encoding="utf-8"),
            "migrations": (ROOT / "docs" / "repository-migrations.md").read_text(encoding="utf-8"),
            "constraints": (ROOT / "docs" / "repository-constraints.md").read_text(encoding="utf-8"),
            "indexes": (ROOT / "docs" / "repository-indexes.md").read_text(encoding="utf-8"),
            "architecture": (ROOT / "docs" / "architecture-overview.md").read_text(encoding="utf-8"),
            "project": (ROOT / "docs" / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
            "local": (ROOT / "docs" / "local-db-hardening.md").read_text(encoding="utf-8"),
        }
        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("local-db-hardening.md", text)
                self.assertIn("local_db_hardening.py", text)

        local_doc = docs["local"]
        self.assertIn("does not migrate, repair, vacuum, delete", local_doc)
        self.assertIn("Do not add a silent tracked-position SQLite fallback", local_doc)
        self.assertIn("data/options-validation/options_history.db", local_doc)
        self.assertIn("data/ai-commodity-infra/*", local_doc)

        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            "chat_history.db",
            "chat_history.backup-*.db",
            "market_data.db",
            "*.db-shm",
            "*.db-wal",
            "data/tracked_positions.db",
            "data/tracked_positions.backup-*",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)


if __name__ == "__main__":
    unittest.main()
