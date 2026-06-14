from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_daily_ops


class DailyOpsRunnerTests(unittest.TestCase):
    def test_daily_ops_order_is_read_only_and_places_heartbeat_before_gateboard(self) -> None:
        step_ids = [str(step["id"]) for step in run_daily_ops.DAILY_OP_STEPS]
        self.assertEqual(
            step_ids,
            [
                "open_risk_exit_evidence_plan",
                "suggested_trade_review_plan",
                "fill_attempt_evidence_capture_plan",
                "paper_shadow_monitor",
                "paper_shortlist_gate",
                "fresh_evidence_loop",
                "candidate_outcome_ledger",
                "scheduled_scan_heartbeat_health",
                "operator_gateboard",
            ],
        )
        self.assertLess(
            step_ids.index("scheduled_scan_heartbeat_health"),
            step_ids.index("operator_gateboard"),
        )
        self.assertTrue(all(bool(step["read_only_safe"]) for step in run_daily_ops.DAILY_OP_STEPS))
        self.assertEqual(
            [step["stage"] for step in run_daily_ops.DAILY_OP_STEPS],
            [
                "exit_evidence_capture",
                "suggested_trade_review_plan_execution",
                "paper_shadow_collection",
                "paper_shadow_collection",
                "paper_shadow_collection",
                "paper_shadow_collection",
                "paper_shadow_collection",
                "heartbeat_check",
                "gateboard_refresh",
            ],
        )

    def test_run_daily_ops_invokes_commands_in_declared_order(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command, **kwargs):
            calls.append(list(command))
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

        with (
            patch.object(run_daily_ops.subprocess, "run", side_effect=fake_run),
            patch.object(run_daily_ops, "_utc_now_iso", side_effect=["2026-06-14T01:00:00Z", "2026-06-14T01:00:01Z"]),
        ):
            report = run_daily_ops.run_daily_ops()

        self.assertEqual(report["status"], "completed")
        self.assertEqual([step["id"] for step in report["steps"]], [step["id"] for step in run_daily_ops.DAILY_OP_STEPS])
        self.assertEqual(calls, [list(step["command"]) for step in run_daily_ops.DAILY_OP_STEPS])
        self.assertIn([sys.executable, "scripts/scan_heartbeat.py", "--health"], calls)
        self.assertEqual(report["required_stage_order"], list(run_daily_ops.REQUIRED_STAGE_ORDER))
        self.assertIn("heartbeat health before the gateboard", report["boundary"])
        self.assertTrue(all(step["read_only_safe"] for step in report["steps"]))
        heartbeat_step = next(step for step in report["steps"] if step["id"] == "scheduled_scan_heartbeat_health")
        self.assertTrue(heartbeat_step["continue_after_failure"])

    def test_run_daily_ops_stops_on_first_failure_by_default(self) -> None:
        def fake_run(command, **kwargs):
            if any(str(part).endswith("build_regular_options_suggested_trade_review_plan.py") for part in command):
                return SimpleNamespace(returncode=2, stdout="", stderr="failed\n")
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

        with (
            patch.object(run_daily_ops.subprocess, "run", side_effect=fake_run) as run,
            patch.object(run_daily_ops, "_utc_now_iso", side_effect=["2026-06-14T01:00:00Z", "2026-06-14T01:00:01Z"]),
        ):
            report = run_daily_ops.run_daily_ops()

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_step_count"], 1)
        self.assertEqual([step["id"] for step in report["steps"]], ["open_risk_exit_evidence_plan", "suggested_trade_review_plan"])
        self.assertEqual(run.call_count, 2)

    def test_continue_on_failure_keeps_collecting_read_only_statuses(self) -> None:
        def fake_run(command, **kwargs):
            if any(str(part).endswith("build_regular_options_suggested_trade_review_plan.py") for part in command):
                return SimpleNamespace(returncode=2, stdout="", stderr="failed\n")
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

        with (
            patch.object(run_daily_ops.subprocess, "run", side_effect=fake_run),
            patch.object(run_daily_ops, "_utc_now_iso", side_effect=["2026-06-14T01:00:00Z", "2026-06-14T01:00:01Z"]),
        ):
            report = run_daily_ops.run_daily_ops(stop_on_failure=False)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_step_count"], 1)
        self.assertEqual([step["id"] for step in report["steps"]], [step["id"] for step in run_daily_ops.DAILY_OP_STEPS])

    def test_heartbeat_failure_still_refreshes_gateboard(self) -> None:
        def fake_run(command, **kwargs):
            if any(str(part).endswith("scan_heartbeat.py") for part in command):
                return SimpleNamespace(returncode=1, stdout='{"state":"fail"}\n', stderr="")
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

        with (
            patch.object(run_daily_ops.subprocess, "run", side_effect=fake_run),
            patch.object(run_daily_ops, "_utc_now_iso", side_effect=["2026-06-14T01:00:00Z", "2026-06-14T01:00:01Z"]),
        ):
            report = run_daily_ops.run_daily_ops()

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["steps"][-2]["id"], "scheduled_scan_heartbeat_health")
        self.assertEqual(report["steps"][-2]["status"], "fail")
        self.assertEqual(report["steps"][-1]["id"], "operator_gateboard")
        self.assertEqual(report["steps"][-1]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
