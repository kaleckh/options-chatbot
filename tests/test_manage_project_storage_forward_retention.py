from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.manage_project_storage import build_cleanup_plan


def _write_policy(root: Path, rule: dict[str, object]) -> Path:
    payload = {
        "schema_version": 1,
        "policy_id": "forward-test",
        "apply_acknowledgement": "ACK",
        "pre_vacuum_retirement_acknowledgement": "RETIRE",
        "default_mode": "dry_run",
        "protected_exact_paths": [],
        "protected_path_prefixes": [".git/"],
        "rebuildable_roots": [],
        "python_cache_names": [],
        "snapshot_rules": [rule],
        "log_rules": [],
        "audit_only_paths": [],
        "pre_vacuum_gate": {
            "active_db": "active.db",
            "pre_vacuum_backup": "old.db",
            "import_lock": "import.lock",
            "vacuum_log": "vacuum.log",
            "vacuum_required_markers": [],
            "import_log": "import.log",
            "import_required_markers": [],
            "pipeline_log": "pipeline.log",
            "pipeline_required_markers": [],
            "required_table": "rows",
        },
    }
    path = root / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_run(root: Path, family: str, stamp: str, status: str) -> None:
    payload = {"report_id": family, "generated_at_utc": stamp, "status": status}
    (root / f"{family}_{stamp}.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / f"{family}_{stamp}.md").write_text(f"# {family}\n\n- status: `{status}`\n", encoding="utf-8")


class ForwardRetentionTests(unittest.TestCase):
    def test_report_families_are_retained_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            output = root / "forward"
            output.mkdir()
            for stamp in ("20260101T000000Z", "20260201T000000Z", "20260202T000000Z", "20260203T000000Z"):
                _write_run(output, "frequent", stamp, "stable")
            _write_run(output, "infrequent", "20260101T000000Z", "stable")
            policy = _write_policy(
                root,
                {
                    "path": "forward",
                    "recursive": False,
                    "family_from_filename": True,
                    "keep_recent_runs": 2,
                    "keep_monthly_runs": 1,
                    "min_age_hours": 0,
                },
            )

            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            planned = {item["path"] for item in plan["candidates"]}

            self.assertIn("forward/frequent_20260101T000000Z.json", planned)
            self.assertNotIn("forward/infrequent_20260101T000000Z.json", planned)

    def test_status_transition_boundaries_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            output = root / "forward"
            output.mkdir()
            statuses = ["blocked", "blocked", "pass", "pass", "pass"]
            for index, status in enumerate(statuses, start=1):
                _write_run(output, "family", f"2026020{index}T000000Z", status)
            policy = _write_policy(
                root,
                {
                    "path": "forward",
                    "recursive": False,
                    "family_from_filename": True,
                    "keep_recent_runs": 1,
                    "keep_monthly_runs": 0,
                    "preserve_status_transitions": True,
                    "min_age_hours": 0,
                },
            )

            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            planned = {item["path"] for item in plan["candidates"]}

            self.assertNotIn("forward/family_20260202T000000Z.json", planned)
            self.assertNotIn("forward/family_20260203T000000Z.json", planned)
            self.assertIn("forward/family_20260204T000000Z.json", planned)

    def test_malformed_and_evidence_milestone_bundles_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            output = root / "forward"
            output.mkdir()
            _write_run(output, "family", "20260201T000000Z", "stable")
            malformed = output / "family_20260202T000000Z.json"
            malformed.write_text("{not json", encoding="utf-8")
            (output / "family_20260202T000000Z.md").write_text("malformed milestone", encoding="utf-8")
            milestone = {
                "report_id": "family",
                "status": "stable",
                "candidate_rows_staged": 1,
            }
            (output / "family_20260203T000000Z.json").write_text(json.dumps(milestone), encoding="utf-8")
            (output / "family_20260203T000000Z.md").write_text("candidate staged", encoding="utf-8")
            _write_run(output, "family", "20260204T000000Z", "stable")
            policy = _write_policy(
                root,
                {
                    "path": "forward",
                    "recursive": False,
                    "family_from_filename": True,
                    "keep_recent_runs": 1,
                    "keep_monthly_runs": 0,
                    "preserve_status_transitions": True,
                    "min_age_hours": 0,
                },
            )

            plan = build_cleanup_plan(
                root=root,
                policy_path=policy,
                categories=["generated_snapshots"],
                now=datetime(2026, 3, 1, tzinfo=UTC),
            )
            planned = {item["path"] for item in plan["candidates"]}

            self.assertNotIn("forward/family_20260202T000000Z.json", planned)
            self.assertNotIn("forward/family_20260203T000000Z.json", planned)


if __name__ == "__main__":
    unittest.main()
