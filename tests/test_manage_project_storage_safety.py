from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from scripts.manage_project_storage import (
    StoragePolicyError,
    apply_cleanup_plan,
    build_cleanup_plan,
    build_pre_vacuum_retirement_report,
    retire_pre_vacuum_backup,
)


def _make_db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE option_quote_snapshots (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO option_quote_snapshots (value) VALUES (?)", (value,))
        conn.commit()


def _policy(root: Path) -> Path:
    payload = {
        "schema_version": 1,
        "policy_id": "safety-test",
        "apply_acknowledgement": "APPLY",
        "pre_vacuum_retirement_acknowledgement": "RETIRE",
        "default_mode": "dry_run",
        "protected_exact_paths": [
            "data/options-validation/options_history.db",
            "data/options-validation/options_history.db.pre_vacuum_backup",
        ],
        "protected_path_prefixes": [".git/"],
        "rebuildable_roots": [{"category": "next_build", "path": ".next", "min_age_hours": 0}],
        "python_cache_names": [],
        "snapshot_rules": [
            {"path": "generated", "keep_recent_runs": 1, "keep_monthly_runs": 0, "min_age_hours": 0}
        ],
        "log_rules": [{"path": "logs/worker.log", "max_bytes": 1, "min_age_hours": 0, "keep_archives": 2}],
        "audit_only_paths": [],
        "pre_vacuum_gate": {
            "active_db": "data/options-validation/options_history.db",
            "pre_vacuum_backup": "data/options-validation/options_history.db.pre_vacuum_backup",
            "import_lock": "data/options-validation/options_history_import.lock",
            "vacuum_log": "data/options-validation/vacuum.log",
            "vacuum_required_markers": ["VACUUM_OK"],
            "import_log": "data/options-validation/import.log",
            "import_required_markers": ["IMPORT_OK"],
            "pipeline_log": "data/options-validation/pipeline.log",
            "pipeline_required_markers": ["PIPELINE_OK"],
            "required_table": "option_quote_snapshots",
        },
    }
    path = root / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _git(root: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)


def _gate_files(root: Path) -> Path:
    data = root / "data" / "options-validation"
    data.mkdir(parents=True, exist_ok=True)
    (data / "vacuum.log").write_text("VACUUM_OK", encoding="utf-8")
    (data / "import.log").write_text("IMPORT_OK", encoding="utf-8")
    (data / "pipeline.log").write_text("PIPELINE_OK", encoding="utf-8")
    return data


class ProjectStorageSafetyTests(unittest.TestCase):
    def test_unrelated_same_row_count_database_is_not_a_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _policy(root)
            data = _gate_files(root)
            active = data / "options_history.db"
            old = data / "options_history.db.pre_vacuum_backup"
            replacement = root / "replacement.db"
            _make_db(active, "A")
            _make_db(old, "old")
            _make_db(replacement, "DIFFERENT")

            report = build_pre_vacuum_retirement_report(
                root=root,
                policy_path=policy,
                replacement_backup=replacement,
                verify_databases=True,
            )

            self.assertFalse(report["eligible"])
            self.assertFalse(report["checks"]["replacement_matches_active"])

    def test_retirement_rechecks_import_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _policy(root)
            data = _gate_files(root)
            active = data / "options_history.db"
            old = data / "options_history.db.pre_vacuum_backup"
            replacement = root / "replacement.db"
            _make_db(active, "A")
            _make_db(old, "old")
            shutil.copy2(active, replacement)
            report = build_pre_vacuum_retirement_report(
                root=root,
                policy_path=policy,
                replacement_backup=replacement,
                verify_databases=True,
            )
            self.assertTrue(report["eligible"])
            (data / "options_history_import.lock").write_text("writer", encoding="utf-8")

            with self.assertRaises(StoragePolicyError):
                retire_pre_vacuum_backup(report, root=root, policy_path=policy, acknowledgement="RETIRE")

            self.assertTrue(old.exists())

    def test_same_size_rewrite_invalidates_cleanup_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root)
            policy = _policy(root)
            generated = root / "generated"
            generated.mkdir()
            old = generated / "report_20260101T000000Z.json"
            old.write_text("AAAA", encoding="utf-8")
            (generated / "report_20260201T000000Z.json").write_text("new", encoding="utf-8")
            plan = build_cleanup_plan(root=root, policy_path=policy, categories=["generated_snapshots"])
            old.write_text("BBBB", encoding="utf-8")

            with self.assertRaises(StoragePolicyError):
                apply_cleanup_plan(plan, root=root, policy_path=policy, acknowledgement="APPLY")

            self.assertEqual(old.read_text(encoding="utf-8"), "BBBB")

    def test_tree_with_tracked_descendant_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root)
            policy = _policy(root)
            tracked = root / ".next" / "keep.txt"
            tracked.parent.mkdir()
            tracked.write_text("tracked", encoding="utf-8")
            subprocess.run(["git", "add", ".next/keep.txt", "--force"], cwd=root, check=True)
            plan = build_cleanup_plan(root=root, policy_path=policy, categories=["next_build"])

            result = apply_cleanup_plan(plan, root=root, policy_path=policy, acknowledgement="APPLY")

            self.assertEqual(result["status"], "applied_with_errors")
            self.assertTrue(tracked.exists())

    def test_log_archive_collision_preserves_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root)
            policy = _policy(root)
            log = root / "logs" / "worker.log"
            log.parent.mkdir()
            log.write_text("content", encoding="utf-8")
            now = datetime(2026, 7, 10, tzinfo=UTC)
            collision = log.with_name("worker.log.20260710T000000Z.gz")
            collision.write_bytes(b"existing")
            plan = build_cleanup_plan(root=root, policy_path=policy, categories=["logs"], now=now)

            result = apply_cleanup_plan(
                plan,
                root=root,
                policy_path=policy,
                acknowledgement="APPLY",
                now=now,
            )

            self.assertEqual(result["status"], "applied_with_errors")
            self.assertEqual(log.read_text(encoding="utf-8"), "content")
            self.assertEqual(collision.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
