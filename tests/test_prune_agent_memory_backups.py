from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts import prune_agent_memory_backups as retention


class AgentMemoryBackupRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "backups"
        self.root.mkdir()

    def _bundle(self, created: datetime, suffix: str = "deadbeef") -> Path:
        stamp = created.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_id = f"{stamp}-{suffix}"
        path = self.root / backup_id
        path.mkdir()
        (path / "agent_control.db").write_bytes(backup_id.encode("ascii"))
        (path / "manifest.json").write_text(
            json.dumps(
                {
                    "backup_id": backup_id,
                    "created_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _pass(_: Path) -> dict[str, str]:
        return {"status": "pass"}

    def test_plan_keeps_daily_and_weekly_union(self) -> None:
        start = datetime(2026, 7, 10, 12, tzinfo=UTC)
        paths = [self._bundle(start - timedelta(days=offset), f"id{offset}") for offset in range(10)]
        plan = retention.build_retention_plan(backup_root=self.root, keep_daily=3, keep_weekly=4)
        retained = {item["backup_id"] for item in plan["retained"]}
        expected = {paths[index].name for index in (0, 1, 2, 5)}
        self.assertEqual(retained, expected)
        self.assertEqual(plan["candidate_count"], 6)

    def test_invalid_bundle_is_preserved_not_selected(self) -> None:
        invalid = self.root / "incomplete"
        invalid.mkdir()
        plan = retention.build_retention_plan(backup_root=self.root)
        self.assertEqual(plan["candidate_count"], 0)
        self.assertEqual(Path(plan["preserved_invalid"][0]["path"]), invalid)

    def test_apply_refuses_any_failed_restore_before_deleting(self) -> None:
        start = datetime(2026, 7, 10, 12, tzinfo=UTC)
        paths = [self._bundle(start - timedelta(days=offset), f"id{offset}") for offset in range(4)]
        plan = retention.build_retention_plan(backup_root=self.root, keep_daily=1, keep_weekly=1)

        def verifier(path: Path) -> dict[str, str]:
            return {"status": "fail" if path == paths[-1] else "pass"}

        with self.assertRaises(retention.BackupRetentionError):
            retention.apply_retention_plan(
                plan,
                acknowledgement=retention.APPLY_ACKNOWLEDGEMENT,
                verifier=verifier,
            )
        self.assertTrue(all(path.exists() for path in paths))

    def test_apply_deletes_only_verified_candidates(self) -> None:
        start = datetime(2026, 7, 10, 12, tzinfo=UTC)
        paths = [self._bundle(start - timedelta(days=offset), f"id{offset}") for offset in range(5)]
        plan = retention.build_retention_plan(backup_root=self.root, keep_daily=2, keep_weekly=2)
        retained = {Path(item["path"]) for item in plan["retained"]}
        result = retention.apply_retention_plan(
            plan,
            acknowledgement=retention.APPLY_ACKNOWLEDGEMENT,
            verifier=self._pass,
        )
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["deleted_count"], plan["candidate_count"])
        self.assertTrue(all(path.exists() for path in retained))
        self.assertTrue(all(path.exists() == (path in retained) for path in paths))

    def test_apply_rejects_stale_plan(self) -> None:
        start = datetime(2026, 7, 10, 12, tzinfo=UTC)
        self._bundle(start, "newest")
        self._bundle(start - timedelta(days=1), "older")
        plan = retention.build_retention_plan(backup_root=self.root, keep_daily=1, keep_weekly=1)
        self._bundle(start + timedelta(days=1), "arrived")
        with self.assertRaises(retention.BackupRetentionError):
            retention.apply_retention_plan(
                plan,
                acknowledgement=retention.APPLY_ACKNOWLEDGEMENT,
                verifier=self._pass,
            )

    def test_explicit_degraded_mode_allows_only_mirror_only_failures(self) -> None:
        start = datetime(2026, 7, 10, 12, tzinfo=UTC)
        paths = [self._bundle(start - timedelta(days=offset), f"id{offset}") for offset in range(4)]
        plan = retention.build_retention_plan(backup_root=self.root, keep_daily=1, keep_weekly=1)

        def verifier(path: Path) -> dict[str, object]:
            if path == paths[0]:
                return {"status": "pass"}
            return {
                "status": "fail",
                "issues": ["events.jsonl mirror audit failed"],
                "ledger": {"status": "pass"},
                "event_outbox": {"status": "pass"},
                "anchors": {"status": "pass"},
                "event_mirror": {
                    "status": "issues",
                    "issues": [{"issue": "mirror contains duplicate outbox id"}],
                },
            }

        result = retention.apply_retention_plan(
            plan,
            acknowledgement=retention.DEGRADED_APPLY_ACKNOWLEDGEMENT,
            verifier=verifier,
        )

        self.assertTrue(paths[0].exists())
        self.assertTrue(all(not path.exists() for path in paths[1:]))
        self.assertEqual(result["deleted_count"], 3)
        self.assertEqual(
            {item["status"] for item in result["restore_checked"]},
            {"pass", "degraded_mirror_only"},
        )


if __name__ == "__main__":
    unittest.main()
