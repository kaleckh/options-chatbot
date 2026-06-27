import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_strict_forward_30_market_window_collector as collector


NOW = "2026-06-27T02:00:00Z"


def _goal_report(**overrides):
    payload = {
        "status": "blocked_no_phase2_natural_selections",
        "strict_forward_rows": 0,
        "required_rows": 30,
        "remaining_rows": 30,
        "accepted_profitability": False,
        "profitability_readiness": False,
        "candidate_rows_staged": 0,
        "candidate_jsonl_exists": False,
        "cohort_append_performed": False,
        "scan_sweep_started": True,
        "scan_sweep_exit_code": 0,
        "capture_status": "no_phase2_natural_selections_no_append",
        "throughput_status": "blocked_no_same_day_phase2_natural_selections",
        "candidate_starvation_evidence_status": "stage_counts_only_waiting_for_symbol_drop_reasons",
        "scheduled_phase2_drop_count_total": 63,
        "scheduled_phase2_scan_drop_reason_count_total": 0,
        "readiness_status": "market_window_blocked_no_candidate_jsonl",
        "safety_violations": [],
        "next_action": "keep_passive_sweep_enabled_for_next_valid_market_window",
        "market_window_schedule": {
            "next_window_trade_date": "2026-06-29",
            "safe_no_append_collection_command": "npm run options:goal-loop:strict-forward-30 -- --selection-date 2026-06-29 --market-window-confirmed --market-window-status open --run-scan-sweep --json",
        },
    }
    payload.update(overrides)
    return payload


class RegularOptionsStrictForward30MarketWindowCollectorTests(unittest.TestCase):
    def _build(self, goal_reports, **kwargs):
        reports = list(goal_reports)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(collector.goal_loop, "build_report", side_effect=reports) as build_goal:
                report = collector.build_report(
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    generated_at_utc=NOW,
                    write_outputs=False,
                    sleep_func=lambda _seconds: None,
                    **kwargs,
                )
        return report, build_goal

    def test_closed_or_unknown_market_waits_without_scan_or_append(self):
        report, build_goal = self._build(
            [_goal_report(status="waiting_for_valid_market_window", scan_sweep_started=False)],
            market_window_status="unknown",
            run_scan_sweep=True,
            append=True,
        )

        self.assertEqual(report["status"], "waiting_for_valid_market_window")
        self.assertEqual(report["attempt_count"], 1)
        called_kwargs = build_goal.call_args.kwargs
        self.assertFalse(called_kwargs["run_scan_sweep"])
        self.assertFalse(called_kwargs["append"])
        self.assertIsNone(called_kwargs["approval_token"])

    def test_open_market_exhausts_bounded_attempts_when_no_candidates(self):
        report, build_goal = self._build(
            [_goal_report(), _goal_report()],
            market_window_confirmed=True,
            market_window_status="open",
            run_scan_sweep=True,
            max_attempts=2,
            sleep_seconds=0,
        )

        self.assertEqual(report["status"], "collector_attempts_exhausted_waiting_for_more_rows")
        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual(build_goal.call_count, 2)
        self.assertTrue(build_goal.call_args.kwargs["run_scan_sweep"])
        self.assertEqual(report["latest_candidate_starvation_evidence_status"], "stage_counts_only_waiting_for_symbol_drop_reasons")
        self.assertEqual(report["latest_scheduled_phase2_drop_count_total"], 63)
        self.assertEqual(report["latest_scheduled_phase2_scan_drop_reason_count_total"], 0)
        self.assertEqual(
            report["attempt_reports"][0]["candidate_starvation_evidence_status"],
            "stage_counts_only_waiting_for_symbol_drop_reasons",
        )

    def test_open_market_attempts_get_fresh_timestamps_when_clock_not_fixed(self):
        reports = [_goal_report(), _goal_report()]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(collector, "_utc_now_iso", side_effect=["2026-06-29T14:00:00Z", "2026-06-29T14:00:01Z", "2026-06-29T14:05:01Z"]),
                patch.object(collector.goal_loop, "build_report", side_effect=reports) as build_goal,
            ):
                report = collector.build_report(
                    market_window_confirmed=True,
                    market_window_status="open",
                    source_scan_picks_path=root / "scan_picks.jsonl",
                    candidate_output_path=root / "candidate.jsonl",
                    cohort_log_path=root / "cohort.jsonl",
                    write_outputs=False,
                    sleep_func=lambda _seconds: None,
                    max_attempts=2,
                    sleep_seconds=0,
                )

        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual(build_goal.call_args_list[0].kwargs["generated_at_utc"], "2026-06-29T14:00:01Z")
        self.assertEqual(build_goal.call_args_list[1].kwargs["generated_at_utc"], "2026-06-29T14:05:01Z")

    def test_candidate_rows_stop_for_review_without_append(self):
        report, build_goal = self._build(
            [
                _goal_report(
                    status="candidate_rows_valid_no_append_requested",
                    candidate_rows_staged=2,
                    candidate_jsonl_exists=True,
                    capture_status="candidate_rows_valid_no_append",
                )
            ],
            market_window_confirmed=True,
            market_window_status="open",
            max_attempts=3,
        )

        self.assertEqual(report["status"], "collector_stopped_candidate_review_required")
        self.assertEqual(report["attempt_count"], 1)
        self.assertEqual(build_goal.call_count, 1)

    def test_guarded_append_stops_waiting_for_exits(self):
        report, _build_goal = self._build(
            [
                _goal_report(
                    status="append_performed_waiting_for_strict_completed_rows",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    cohort_append_performed=True,
                )
            ],
            market_window_confirmed=True,
            market_window_status="open",
            append=True,
            approval_token="explicit-operator-token",
            max_attempts=3,
        )

        self.assertEqual(report["status"], "collector_stopped_after_guarded_append_waiting_for_exits")
        self.assertTrue(report["cohort_append_performed"])

    def test_safety_violation_stops_collector(self):
        report, build_goal = self._build(
            [_goal_report(status="blocked_safety_violation", safety_violations=["payload_1:auto_track_allowed"])],
            market_window_confirmed=True,
            market_window_status="open",
            max_attempts=3,
        )

        self.assertEqual(report["status"], "collector_stopped_safety_violation")
        self.assertEqual(report["safety_violations"], ["payload_1:auto_track_allowed"])
        self.assertEqual(build_goal.call_count, 1)

    def test_completed_goal_stops_collector(self):
        report, _build_goal = self._build(
            [
                _goal_report(
                    status="strict_forward_30_goal_complete",
                    strict_forward_rows=30,
                    remaining_rows=0,
                    accepted_profitability=True,
                    profitability_readiness=True,
                )
            ],
            market_window_confirmed=True,
            market_window_status="open",
            max_attempts=3,
        )

        self.assertEqual(report["status"], "collector_completed_goal")
        self.assertEqual(report["strict_forward_rows"], 30)
        self.assertTrue(report["accepted_profitability"])


if __name__ == "__main__":
    unittest.main()
