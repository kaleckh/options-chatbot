import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_strict_forward_30_goal_loop as goal_loop


NOW = "2026-06-27T02:00:00Z"


def _capture(**overrides):
    payload = {
        "status": "no_phase2_natural_selections_no_append",
        "candidate_rows_staged": 0,
        "candidate_jsonl_exists": False,
        "cohort_append_performed": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
    }
    payload.update(overrides)
    return payload


def _throughput(**overrides):
    payload = {
        "status": "blocked_no_same_day_phase2_natural_selections",
        "scheduled_phase2_all_lanes_scanned": True,
        "scheduled_phase2_scan_picks_count": 0,
        "scheduled_phase2_drop_count_total": 63,
        "scheduled_phase2_scan_drop_reason_count_total": 0,
        "candidate_starvation_evidence_status": "stage_counts_only_waiting_for_symbol_drop_reasons",
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
    }
    payload.update(overrides)
    return payload


def _readiness(**overrides):
    payload = {
        "overall_status": "market_window_blocked_no_candidate_jsonl",
        "strict_forward_rows": 0,
        "required_rows": 30,
        "accepted_profitability": False,
        "profitability_readiness": False,
        "candidate_throughput": {
            "scheduled_phase2_all_lanes_scanned": True,
            "scheduled_phase2_scan_picks_count": 0,
        },
        "scan_task_health_status": "scan_tasks_ready_for_next_market_window",
        "scan_task_health_blockers": [],
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
    }
    payload.update(overrides)
    return payload


class RegularOptionsStrictForward30GoalLoopTests(unittest.TestCase):
    def _build(self, **kwargs):
        generated_at_utc = kwargs.pop("generated_at_utc", NOW)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(goal_loop.capture_runner, "build_capture_report", return_value=_capture()),
                patch.object(goal_loop.throughput_audit, "build_report", return_value=_throughput()),
                patch.object(goal_loop.readiness_refresh, "build_report", return_value=_readiness()),
                patch.object(goal_loop.throughput_audit, "write_outputs"),
                patch.object(goal_loop.readiness_refresh, "write_outputs"),
            ):
                return goal_loop.build_report(
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    generated_at_utc=generated_at_utc,
                    write_outputs=False,
                    **kwargs,
                )

    def test_closed_or_unknown_market_waits_without_scan_or_append(self):
        report = self._build()

        self.assertEqual(report["status"], "waiting_for_valid_market_window")
        self.assertFalse(report["scan_sweep_started"])
        self.assertFalse(report["append_requested"])
        self.assertEqual(report["strict_forward_rows"], 0)
        self.assertEqual(report["remaining_rows"], 30)
        self.assertEqual(report["candidate_starvation_evidence_status"], "stage_counts_only_waiting_for_symbol_drop_reasons")
        self.assertEqual(report["scheduled_phase2_drop_count_total"], 63)
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_count_total"], 0)
        self.assertEqual(report["scan_task_health_status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(report["scan_task_health_blockers"], [])
        self.assertFalse(report["cohort_append_performed"])

    def test_market_window_schedule_rolls_after_hours_to_next_market_day(self):
        schedule = goal_loop._market_window_schedule("2026-06-27T01:54:01Z")

        self.assertEqual(schedule["status"], "waiting_for_next_market_day")
        self.assertEqual(schedule["current_market_date"], "2026-06-26")
        self.assertEqual(schedule["default_selection_date"], "2026-06-26")
        self.assertEqual(schedule["next_window_trade_date"], "2026-06-29")
        self.assertIn("--selection-date 2026-06-29", schedule["safe_no_append_collection_command"])
        self.assertIn("--run-scan-sweep", schedule["safe_no_append_collection_command"])

    def test_market_window_schedule_uses_prior_market_day_for_weekend_readback(self):
        schedule = goal_loop._market_window_schedule("2026-06-27T16:00:00Z")

        self.assertEqual(schedule["status"], "waiting_for_next_market_day")
        self.assertEqual(schedule["current_market_date"], "2026-06-27")
        self.assertFalse(schedule["current_date_is_market_day"])
        self.assertEqual(schedule["default_selection_date"], "2026-06-26")
        self.assertEqual(schedule["next_window_trade_date"], "2026-06-29")

    def test_market_window_schedule_marks_open_window(self):
        schedule = goal_loop._market_window_schedule("2026-06-29T14:15:00Z")

        self.assertEqual(schedule["status"], "market_window_open_now")
        self.assertTrue(schedule["market_window_open_now"])
        self.assertEqual(schedule["default_selection_date"], "2026-06-29")
        self.assertEqual(schedule["next_window_trade_date"], "2026-06-29")

    def test_default_selection_date_uses_current_market_date_not_utc_date(self):
        report = self._build(generated_at_utc="2026-06-27T01:54:01Z")

        self.assertEqual(report["selection_date"], "2026-06-26")

    def test_weekend_default_selection_date_uses_latest_completed_market_day(self):
        report = self._build(generated_at_utc="2026-06-27T16:00:00Z")

        self.assertEqual(report["selection_date"], "2026-06-26")

    def test_writes_fresh_throughput_before_readiness_refresh(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def write_throughput(_report):
                events.append("throughput_written")

            def build_readiness(*_args, **_kwargs):
                self.assertIn("throughput_written", events)
                return _readiness()

            with (
                patch.object(goal_loop.capture_runner, "build_capture_report", return_value=_capture()),
                patch.object(goal_loop.throughput_audit, "build_report", return_value=_throughput()),
                patch.object(goal_loop.throughput_audit, "write_outputs", side_effect=write_throughput),
                patch.object(goal_loop.readiness_refresh, "build_report", side_effect=build_readiness),
                patch.object(goal_loop.readiness_refresh, "write_outputs"),
            ):
                report = goal_loop.build_report(
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    output_dir=root / "out",
                    docs_report=root / "doc.md",
                    generated_at_utc=NOW,
                    write_outputs=True,
                )

        self.assertEqual(report["status"], "waiting_for_valid_market_window")

    def test_open_market_with_sweep_and_no_candidates_reports_candidate_starvation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(goal_loop.scan_sweep, "main", return_value=0) as scan,
                patch.object(goal_loop.capture_runner, "build_capture_report", return_value=_capture()),
                patch.object(goal_loop.throughput_audit, "build_report", return_value=_throughput()),
                patch.object(goal_loop.readiness_refresh, "build_report", return_value=_readiness()),
                patch.object(goal_loop.throughput_audit, "write_outputs"),
                patch.object(goal_loop.readiness_refresh, "write_outputs"),
            ):
                report = goal_loop.build_report(
                    market_window_confirmed=True,
                    market_window_status="open",
                    selection_date="2026-06-29",
                    run_scan_sweep=True,
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    generated_at_utc=NOW,
                    write_outputs=False,
                )

        self.assertEqual(report["status"], "blocked_no_phase2_natural_selections")
        self.assertTrue(report["scan_sweep_started"])
        scan.assert_called_once()
        self.assertIn("--force", scan.call_args.args[0])

    def test_valid_candidate_rows_do_not_append_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(
                    goal_loop.capture_runner,
                    "build_capture_report",
                    return_value=_capture(
                        status="candidate_rows_valid_no_append",
                        candidate_rows_staged=1,
                        candidate_jsonl_exists=True,
                    ),
                ),
                patch.object(goal_loop.throughput_audit, "build_report", return_value=_throughput(status="candidate_throughput_ready_for_validation")),
                patch.object(goal_loop.readiness_refresh, "build_report", return_value=_readiness()),
            ):
                report = goal_loop.build_report(
                    market_window_confirmed=True,
                    market_window_status="open",
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    generated_at_utc=NOW,
                    write_outputs=False,
                )

        self.assertEqual(report["status"], "candidate_rows_valid_no_append_requested")
        self.assertFalse(report["append_requested"])
        self.assertFalse(report["cohort_append_performed"])

    def test_safety_violation_blocks_goal_loop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(goal_loop.capture_runner, "build_capture_report", return_value=_capture(auto_track_allowed=True)),
                patch.object(goal_loop.throughput_audit, "build_report", return_value=_throughput()),
                patch.object(goal_loop.readiness_refresh, "build_report", return_value=_readiness()),
            ):
                report = goal_loop.build_report(
                    market_window_confirmed=True,
                    market_window_status="open",
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    generated_at_utc=NOW,
                    write_outputs=False,
                )

        self.assertEqual(report["status"], "blocked_safety_violation")
        self.assertIn("payload_1:auto_track_allowed", report["safety_violations"])


if __name__ == "__main__":
    unittest.main()
