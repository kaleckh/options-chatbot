from __future__ import annotations

import json
import sqlite3
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
)


ACK = "APPLY_PROJECT_STORAGE_RETENTION_V1"


def _policy(root: Path) -> Path:
    payload = {
        "schema_version": 1,
        "policy_id": "test",
        "apply_acknowledgement": ACK,
        "pre_vacuum_retirement_acknowledgement": "RETIRE",
        "default_mode": "dry_run",
        "protected_exact_paths": [
            "data/options-validation/options_history.db",
            "data/options-validation/options_history.db.pre_vacuum_backup",
        ],
        "protected_path_prefixes": [".git/", "data/agent-control/"],
        "rebuildable_roots": [{"category": "next_build", "path": ".next", "min_age_hours": 0}],
        "python_cache_names": ["__pycache__", ".pytest_cache"],
        "snapshot_rules": [
            {
                "path": "generated",
                "keep_recent_runs": 2,
                "keep_monthly_runs": 1,
                "min_age_hours": 0,
            }
        ],
        "log_rules": [
            {"path": "logs/worker.txt", "max_bytes": 10, "min_age_hours": 0, "keep_archives": 2}
        ],
        "audit_only_paths": [],
        "pre_vacuum_gate": {
            "active_db": "data/options-validation/options_history.db",
            "pre_vacuum_backup": "data/options-validation/options_history.db.pre_vacuum_backup",
            "import_lock": "data/options-validation/options_history_import.lock",
            "vacuum_log": "data/options-validation/vacuum.log",
            "vacuum_required_markers": ["VACUUM_OK"],
            "import_log": "data/options-validation/import.log",
            "import_required_markers": ["IMPORTS_COMPLETE"],
            "pipeline_log": "data/options-validation/pipeline.log",
            "pipeline_required_markers": ["PIPELINE_COMPLETE"],
            "required_table": "option_quote_snapshots",
        },
    }
    path = root / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _init_git(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)


def _make_db(path: Path, rows: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE option_quote_snapshots (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO option_quote_snapshots DEFAULT VALUES", [() for _ in range(rows)])
        conn.commit()


class ProjectStorageTests(unittest.TestCase):
    def test_snapshot_plan_is_dry_run_and_keeps_recent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git(root)
            policy = _policy(root)
            generated = root / "generated"
            generated.mkdir()
            for stamp in ("20260101T000000Z", "20260201T000000Z", "20260202T000000Z", "20260203T000000Z"):
                (generated / f"report_{stamp}.json").write_text(stamp, encoding="utf-8")
            (generated / "latest.json").write_text("current", encoding="utf-8")

            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )

            self.assertEqual(plan["status"], "dry_run")
            self.assertEqual(
                [item["path"] for item in plan["candidates"]],
                [
                    "generated/report_20260101T000000Z.json",
                    "generated/report_20260201T000000Z.json",
                ],
            )
            self.assertTrue((generated / "report_20260101T000000Z.json").exists())

    def test_apply_requires_token_and_removes_only_planned_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git(root)
            policy = _policy(root)
            generated = root / "generated"
            generated.mkdir()
            old = generated / "report_20260101T000000Z.json"
            old.write_text("old", encoding="utf-8")
            for stamp in ("20260201T000000Z", "20260202T000000Z", "20260203T000000Z"):
                (generated / f"report_{stamp}.json").write_text(stamp, encoding="utf-8")
            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            with self.assertRaises(StoragePolicyError):
                apply_cleanup_plan(plan, root=root, policy_path=policy, acknowledgement="wrong")
            result = apply_cleanup_plan(plan, root=root, policy_path=policy, acknowledgement=ACK)
            self.assertEqual(result["status"], "applied")
            self.assertFalse(old.exists())
            self.assertTrue((generated / "report_20260203T000000Z.json").exists())

    def test_apply_rejects_injected_untracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git(root)
            policy = _policy(root)
            victim = root / "untracked-user-work.txt"
            victim.write_text("preserve me", encoding="utf-8")
            plan = build_cleanup_plan(root=root, policy_path=policy, categories=["generated_snapshots"])
            plan["candidates"].append(
                {
                    "path": victim.name,
                    "category": "generated_snapshots",
                    "action": "delete_file",
                    "reason": "injected",
                    "size_bytes": victim.stat().st_size,
                }
            )

            with self.assertRaises(StoragePolicyError):
                apply_cleanup_plan(plan, root=root, policy_path=policy, acknowledgement=ACK)

            self.assertTrue(victim.exists())

    def test_tracked_reference_protects_timestamped_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import subprocess

            root = Path(tmp)
            _init_git(root)
            policy = _policy(root)
            generated = root / "generated"
            generated.mkdir()
            referenced = generated / "report_20260101T000000Z.json"
            referenced.write_text("old referenced run", encoding="utf-8")
            unreferenced = generated / "report_20260201T000000Z.json"
            unreferenced.write_text("old unreferenced run", encoding="utf-8")
            for stamp in ("20260202T000000Z", "20260203T000000Z"):
                (generated / f"report_{stamp}.json").write_text(stamp, encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            reference_doc = docs / "milestone.md"
            reference_doc.write_text("Keep report_20260101T000000Z.json", encoding="utf-8")
            subprocess.run(["git", "add", "docs/milestone.md"], cwd=root, check=True)

            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            planned = {item["path"] for item in plan["candidates"]}

            self.assertNotIn("generated/report_20260101T000000Z.json", planned)
            self.assertIn("generated/report_20260201T000000Z.json", planned)

    def test_stale_log_rotation_preserves_compressed_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import gzip

            root = Path(tmp)
            _init_git(root)
            policy = _policy(root)
            log = root / "logs" / "worker.txt"
            log.parent.mkdir()
            content = "repeat me\n" * 100
            log.write_text(content, encoding="utf-8")
            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["logs"],
                now=datetime.now(UTC),
            )
            result = apply_cleanup_plan(
                plan,
                root=root,
                policy_path=policy,
                acknowledgement=ACK,
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            archive = root / result["applied"][0]["archive_path"]
            self.assertEqual(log.stat().st_size, 0)
            with gzip.open(archive, "rt", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), content)

    def test_pre_vacuum_gate_fails_closed_without_completion_and_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _policy(root)
            data = root / "data" / "options-validation"
            _make_db(data / "options_history.db")
            _make_db(data / "options_history.db.pre_vacuum_backup")
            (data / "vacuum.log").write_text("VACUUM_OK", encoding="utf-8")

            report = build_pre_vacuum_retirement_report(root=root, policy_path=policy, verify_databases=True)

            self.assertFalse(report["eligible"])
            self.assertFalse(report["checks"]["import_log"]["pass"])
            self.assertFalse(report["checks"]["replacement_backup_supplied"])

    def test_pre_vacuum_gate_accepts_verified_matching_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _policy(root)
            data = root / "data" / "options-validation"
            active = data / "options_history.db"
            old = data / "options_history.db.pre_vacuum_backup"
            replacement = root / "replacement.db"
            _make_db(active, rows=4)
            _make_db(old, rows=2)
            _make_db(replacement, rows=4)
            (data / "vacuum.log").write_text("VACUUM_OK", encoding="utf-8")
            (data / "import.log").write_text("IMPORTS_COMPLETE", encoding="utf-8")
            (data / "pipeline.log").write_text("PIPELINE_COMPLETE", encoding="utf-8")

            report = build_pre_vacuum_retirement_report(
                root=root,
                policy_path=policy,
                replacement_backup=replacement,
                verify_databases=True,
            )

            self.assertTrue(report["eligible"])
            self.assertTrue(report["checks"]["replacement_matches_active"])


if __name__ == "__main__":
    unittest.main()
