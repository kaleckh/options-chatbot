import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_30_completion_monitor as monitor


NOW = "2026-06-27T02:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")


def _phase2_report(**overrides):
    payload = {
        "overall_status": "cohort_log_missing_blocker",
        "cohort_log_state": "cohort_log_missing_blocker",
        "counts": {
            "total_natural_selections": 0,
            "exact_entry_captured_count": 0,
            "open_waiting_policy_exit_count": 0,
            "exact_completed_forward_pnl_count": 0,
        },
        "acceptance_readiness": {
            "post_freeze_strict_exact_completed_rows": 0,
            "minimum_required": 30,
            "positive_net_usd_pnl": False,
            "strict_profit_factor_usd": None,
            "bootstrap_pf_lower_bound_5pct_usd": None,
        },
        "gates": {
            "minimum_continuation_gate_passed": False,
        },
        "hard_fail_states": [],
        "warning_states": ["cohort_log_missing_blocker"],
        "strict_reject_counts": {},
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
    }
    payload.update(overrides)
    return payload


def _loaded_aux(root: Path):
    collector = root / "collector.json"
    candidate_review = root / "candidate_review.json"
    scheduler = root / "scheduler.json"
    scan_task_health = root / "regular_options_strict_forward_scan_task_health_latest.json"
    exit_evidence_plan = root / "regular_options_strict_forward_30_exit_evidence_plan_latest.json"
    exit_stager = root / "regular_options_strict_forward_30_exit_completion_stager_latest.json"
    lifecycle = root / "regular_options_strict_forward_30_lifecycle_audit_latest.json"
    _write_json(collector, {"status": "waiting_for_valid_market_window", "generated_at_utc": "2026-06-27T01:55:00Z", "cohort_append_performed": False})
    _write_json(
        candidate_review,
        {
            "status": "candidate_review_waiting_for_real_candidate_jsonl",
            "generated_at_utc": "2026-06-27T01:57:00Z",
            "scheduler_health_freshness": {"fresh": True, "status": "scheduler_health_fresh_for_candidate_review"},
            "capture_freshness": {"fresh": True, "status": "capture_latest_fresh_for_candidate_review"},
            "cohort_append_performed": False,
        },
    )
    _write_json(scheduler, {"status": "scheduler_ready_for_next_market_window", "generated_at_utc": "2026-06-27T01:56:00Z", "blockers": []})
    _write_json(scan_task_health, {"status": "scan_tasks_ready_for_next_market_window", "generated_at_utc": "2026-06-27T01:56:30Z", "blockers": []})
    _write_json(
        exit_evidence_plan,
        {
            "status": "exit_evidence_plan_waiting_for_open_forward_rows",
            "generated_at_utc": "2026-06-27T01:58:00Z",
            "quotes_imported": False,
            "broker_order_allowed": False,
            "auto_track_allowed": False,
            "cohort_append_performed": False,
        },
    )
    _write_json(
        exit_stager,
        {
            "status": "exit_completion_waiting_for_open_forward_rows",
            "generated_at_utc": "2026-06-27T01:58:30Z",
            "quotes_imported": False,
            "broker_order_allowed": False,
            "auto_track_allowed": False,
            "cohort_append_performed": False,
        },
    )
    _write_json(
        lifecycle,
        {
            "status": "lifecycle_waiting_for_first_entry_row",
            "generated_at_utc": "2026-06-27T01:59:00Z",
            "quotes_imported": False,
            "broker_order_allowed": False,
            "auto_track_allowed": False,
            "cohort_append_performed": False,
        },
    )
    return collector, candidate_review, scheduler


class RegularOptionsStrictForward30CompletionMonitorTests(unittest.TestCase):
    def test_missing_cohort_waits_for_first_row_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_waiting_for_first_cohort_row")
        self.assertEqual(report["strict_forward_rows"], 0)
        self.assertEqual(report["remaining_rows"], 30)
        self.assertIn("do_not_append_from_completion_monitor", report["prohibited_actions"])

    def test_phase2_report_source_is_marked_computed_inline_when_proposed_latest_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            proposed_latest = root / "missing_phase2_report_latest.json"
            phase2 = _phase2_report(report_id="volatility_expansion_forward_paper_shadow_report", generated_at_utc=NOW)
            with patch.object(monitor.forward_report, "PROPOSED_PHASE2_REPORT_PATH", proposed_latest):
                with patch.object(monitor.forward_report, "build_report", return_value=phase2):
                    report = monitor.build_report(
                        cohort_log_path=root / "cohort.jsonl",
                        schema_path=root / "schema.json",
                        collector_latest_path=collector,
                        candidate_review_latest_path=candidate_review,
                        scheduler_health_latest_path=scheduler,
                        generated_at_utc=NOW,
                    )

        source = report["source_artifacts"]["phase2_report"]
        self.assertEqual(source["source"], "computed_inline")
        self.assertIsNone(source["path"])
        self.assertEqual(source["proposed_report_path"], str(proposed_latest))
        self.assertFalse(source["proposed_report_exists"])
        self.assertEqual(source["report_id"], "volatility_expansion_forward_paper_shadow_report")
        self.assertEqual(report["phase2_forward_report"], phase2)

    def test_open_rows_wait_for_exact_exits(self):
        phase2 = _phase2_report(
            overall_status="awaiting_forward_paper_shadow_evidence",
            cohort_log_state="loaded_under_minimum",
            counts={
                "total_natural_selections": 4,
                "exact_entry_captured_count": 4,
                "open_waiting_policy_exit_count": 3,
                "exact_completed_forward_pnl_count": 1,
            },
            acceptance_readiness={
                "post_freeze_strict_exact_completed_rows": 1,
                "minimum_required": 30,
                "positive_net_usd_pnl": True,
                "strict_profit_factor_usd": None,
                "bootstrap_pf_lower_bound_5pct_usd": None,
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            with patch.object(monitor.forward_report, "build_report", return_value=phase2):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_waiting_for_exact_exits")
        self.assertEqual(report["open_waiting_policy_exit_count"], 3)

    def test_goal_complete_requires_rows_and_profitable_acceptance(self):
        phase2 = _phase2_report(
            overall_status="minimum_review_packet_ready_no_live_authorization",
            cohort_log_state="loaded",
            counts={
                "total_natural_selections": 35,
                "exact_entry_captured_count": 35,
                "open_waiting_policy_exit_count": 0,
                "exact_completed_forward_pnl_count": 30,
            },
            acceptance_readiness={
                "post_freeze_strict_exact_completed_rows": 30,
                "minimum_required": 30,
                "positive_net_usd_pnl": True,
                "strict_profit_factor_usd": 2.0,
                "bootstrap_pf_lower_bound_5pct_usd": 1.2,
            },
            gates={"minimum_continuation_gate_passed": True},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            with patch.object(monitor.forward_report, "build_report", return_value=phase2):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_goal_complete")
        self.assertTrue(report["accepted_profitability"])

    def test_safety_violation_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(collector, {"status": "bad", "auto_track_allowed": True})
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_safety_blocked")
        self.assertIn("payload_2:auto_track_allowed", report["safety_violations"])

    def test_guarded_append_collector_state_does_not_safety_block_monitor(self):
        phase2 = _phase2_report(
            overall_status="awaiting_forward_paper_shadow_evidence",
            cohort_log_state="loaded_under_minimum",
            counts={
                "total_natural_selections": 1,
                "exact_entry_captured_count": 1,
                "open_waiting_policy_exit_count": 1,
                "exact_completed_forward_pnl_count": 0,
            },
            acceptance_readiness={
                "post_freeze_strict_exact_completed_rows": 0,
                "minimum_required": 30,
                "positive_net_usd_pnl": False,
                "strict_profit_factor_usd": None,
                "bootstrap_pf_lower_bound_5pct_usd": None,
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(
                collector,
                {
                    "status": "collector_stopped_after_guarded_append_waiting_for_exits",
                    "generated_at_utc": "2026-06-27T01:55:00Z",
                    "append_requested": True,
                    "cohort_append_performed": True,
                },
            )
            _write_json(
                candidate_review,
                {
                    "status": "candidate_review_guarded_append_observed_waiting_for_exits",
                    "generated_at_utc": "2026-06-27T01:57:00Z",
                    "scheduler_health_freshness": {"fresh": True, "status": "scheduler_health_fresh_for_candidate_review"},
                    "capture_freshness": {"fresh": True, "status": "capture_latest_fresh_for_candidate_review"},
                    "guarded_append_observed": True,
                },
            )
            with patch.object(monitor.forward_report, "build_report", return_value=phase2):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_waiting_for_exact_exits")
        self.assertEqual(report["safety_violations"], [])

    def test_stale_candidate_review_blocks_completion_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(collector, {"status": "waiting_for_valid_market_window", "generated_at_utc": "2026-06-27T02:00:00Z", "cohort_append_performed": False})
            _write_json(candidate_review, {"status": "candidate_review_waiting_for_real_candidate_jsonl", "generated_at_utc": "2026-06-27T01:59:59Z", "cohort_append_performed": False})
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_dependency_freshness_blocked")
        self.assertIn("candidate_review_older_than_collector", report["dependency_blockers"])

    def test_stale_scan_task_health_blocks_completion_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(collector, {"status": "waiting_for_valid_market_window", "generated_at_utc": "2026-06-27T02:00:00Z", "cohort_append_performed": False})
            _write_json(
                root / "regular_options_strict_forward_scan_task_health_latest.json",
                {"status": "scan_tasks_ready_for_next_market_window", "generated_at_utc": "2026-06-27T01:59:59Z", "blockers": []},
            )
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_dependency_freshness_blocked")
        self.assertIn("scan_task_health_older_than_collector", report["dependency_blockers"])

    def test_stale_capture_review_blocks_completion_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(
                candidate_review,
                {
                    "status": "candidate_review_waiting_for_fresh_capture_report",
                    "generated_at_utc": "2026-06-27T02:01:00Z",
                    "scheduler_health_freshness": {"fresh": True, "status": "scheduler_health_fresh_for_candidate_review"},
                    "capture_freshness": {"fresh": False, "status": "capture_older_than_collector"},
                    "cohort_append_performed": False,
                },
            )
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_dependency_freshness_blocked")
        self.assertIn("candidate_review_capture_freshness:capture_older_than_collector", report["dependency_blockers"])

    def test_stale_exit_evidence_plan_blocks_completion_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(collector, {"status": "waiting_for_valid_market_window", "generated_at_utc": "2026-06-27T02:00:00Z", "cohort_append_performed": False})
            _write_json(
                root / "regular_options_strict_forward_30_exit_evidence_plan_latest.json",
                {
                    "status": "exit_evidence_plan_waiting_for_open_forward_rows",
                    "generated_at_utc": "2026-06-27T01:59:59Z",
                    "quotes_imported": False,
                    "broker_order_allowed": False,
                    "auto_track_allowed": False,
                    "cohort_append_performed": False,
                },
            )
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_dependency_freshness_blocked")
        self.assertIn("exit_evidence_plan_older_than_collector", report["dependency_blockers"])

    def test_exit_side_safety_violation_blocks_completion_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collector, candidate_review, scheduler = _loaded_aux(root)
            _write_json(
                root / "regular_options_strict_forward_30_exit_evidence_plan_latest.json",
                {
                    "status": "exit_evidence_plan_waiting_for_open_forward_rows",
                    "generated_at_utc": "2026-06-27T01:58:00Z",
                    "quotes_imported": True,
                    "broker_order_allowed": False,
                    "auto_track_allowed": False,
                    "cohort_append_performed": False,
                },
            )
            with patch.object(monitor.forward_report, "build_report", return_value=_phase2_report()):
                report = monitor.build_report(
                    cohort_log_path=root / "cohort.jsonl",
                    schema_path=root / "schema.json",
                    collector_latest_path=collector,
                    candidate_review_latest_path=candidate_review,
                    scheduler_health_latest_path=scheduler,
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "completion_monitor_safety_blocked")
        self.assertIn("payload_5:quotes_imported", report["safety_violations"])

    def test_write_outputs_creates_monitor_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = _phase2_report()
            report = {
                "report_id": monitor.REPORT_ID,
                "generated_at_utc": NOW,
                "status": "completion_monitor_waiting_for_first_cohort_row",
                "strict_forward_rows": 0,
                "required_rows": 30,
                "remaining_rows": 30,
                "accepted_profitability": False,
                "cohort_log_state": "cohort_log_missing_blocker",
                "open_waiting_policy_exit_count": 0,
                "exact_completed_forward_pnl_count": 0,
                "scheduler_status": "scheduler_ready_for_next_market_window",
                "scan_task_health_status": "scan_tasks_ready_for_next_market_window",
                "candidate_review_status": "candidate_review_waiting_for_real_candidate_jsonl",
                "collector_status": "waiting_for_valid_market_window",
                "safety_violations": [],
            }

            artifacts = monitor.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "regular_options_strict_forward_30_completion_monitor_latest.json").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
