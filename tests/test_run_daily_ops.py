from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_daily_ops


class DailyOpsRunnerTests(unittest.TestCase):
    def test_daily_ops_order_is_read_only_and_places_heartbeat_before_gateboard(self) -> None:
        step_ids = [str(step["id"]) for step in run_daily_ops.DAILY_OP_STEPS]
        self.assertEqual(
            step_ids,
            [
                "point_in_time_earnings_calendar",
                "earnings_calendar_source_repair_packet",
                "historical_scanner_input_surface_tracker",
                "historical_frozen_scanner_replay_adapter",
                "historical_frozen_adapter_exit_quote_repair_demand",
                "frozen_daily_candidate_decisions",
                "frozen_candidate_generation_entrypoint",
                "frozen_candidate_generation_source_surface",
                "frozen_candidate_generation_engine",
                "historical_simulated_forward_audit",
                "historical_profitability_filter_iteration",
                "historical_filtered_simulated_forward_audit",
                "filtered_forward_paper_shadow_tracker",
                "filtered_forward_exit_evidence_capture",
                "filtered_forward_evidence_bar_evaluation",
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
                "historical_input_surface_tracking",
                "historical_input_surface_tracking",
                "historical_input_surface_tracking",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "historical_candidate_generation_audit",
                "paper_shadow_collection",
                "exit_evidence_capture",
                "paper_shadow_collection",
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
        self.assertIn([sys.executable, "scripts/build_regular_options_earnings_calendar_source_repair_packet.py"], calls)
        self.assertIn([sys.executable, "scripts/build_regular_options_historical_simulated_forward_audit.py"], calls)
        self.assertIn([sys.executable, "scripts/build_regular_options_historical_profitability_filter_iteration.py", "--record-consumption"], calls)
        self.assertIn([sys.executable, "scripts/build_regular_options_historical_filtered_simulated_forward_audit.py"], calls)
        self.assertIn([sys.executable, "scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py"], calls)
        self.assertIn([sys.executable, "scripts/capture_regular_options_filtered_forward_exit_evidence.py", "--no-write"], calls)
        self.assertIn([sys.executable, "scripts/build_regular_options_filtered_forward_evidence_bar_evaluation.py"], calls)
        self.assertEqual(report["required_stage_order"], list(run_daily_ops.REQUIRED_STAGE_ORDER))
        self.assertIn("earnings readiness and source-repair planning", report["boundary"])
        self.assertIn("historical simulated-forward audit every run", report["boundary"])
        self.assertIn("heartbeat health before the gateboard", report["boundary"])
        self.assertIn("evaluates the pre-registered forward evidence bar", report["boundary"])
        self.assertTrue(all(step["read_only_safe"] for step in report["steps"]))
        heartbeat_step = next(step for step in report["steps"] if step["id"] == "scheduled_scan_heartbeat_health")
        self.assertTrue(heartbeat_step["continue_after_failure"])

    def test_write_outputs_persists_daily_ops_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {
                "report_id": run_daily_ops.REPORT_ID,
                "status": "completed",
                "started_at_utc": "2026-06-14T01:00:00Z",
                "completed_at_utc": "2026-06-14T01:00:01Z",
                "step_count": 1,
                "failed_step_count": 0,
                "steps": [{"id": "historical_simulated_forward_audit", "stage": "historical_candidate_generation_audit", "status": "pass", "returncode": 0}],
                "boundary": "read-only",
            }
            artifacts = run_daily_ops.write_outputs(
                report,
                output_json=root / "regular_options_daily_ops_latest.json",
                output_md=root / "regular-options-daily-ops.md",
            )

            self.assertTrue((root / "regular_options_daily_ops_latest.json").exists())
            self.assertTrue((root / "regular-options-daily-ops.md").exists())
            persisted = json.loads((root / "regular_options_daily_ops_latest.json").read_text(encoding="utf8"))
            self.assertEqual(persisted["status"], "completed")
            self.assertIn("latest_json", artifacts)

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
        self.assertEqual(
            [step["id"] for step in report["steps"]],
            [
                "point_in_time_earnings_calendar",
                "earnings_calendar_source_repair_packet",
                "historical_scanner_input_surface_tracker",
                "historical_frozen_scanner_replay_adapter",
                "historical_frozen_adapter_exit_quote_repair_demand",
                "frozen_daily_candidate_decisions",
                "frozen_candidate_generation_entrypoint",
                "frozen_candidate_generation_source_surface",
                "frozen_candidate_generation_engine",
                "historical_simulated_forward_audit",
                "historical_profitability_filter_iteration",
                "historical_filtered_simulated_forward_audit",
                "filtered_forward_paper_shadow_tracker",
                "filtered_forward_exit_evidence_capture",
                "filtered_forward_evidence_bar_evaluation",
                "open_risk_exit_evidence_plan",
                "suggested_trade_review_plan",
            ],
        )
        self.assertEqual(run.call_count, 17)

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
