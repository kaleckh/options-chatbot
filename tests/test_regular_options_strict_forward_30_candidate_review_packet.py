import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_30_candidate_review_packet as packet


NOW = "2026-06-27T02:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")


def _capture(**overrides):
    payload = {
        "report_id": "phase2_regular_options_forward_paper_shadow_capture",
        "status": "no_phase2_natural_selections_no_append",
        "generated_at_utc": "2026-06-27T01:56:00Z",
        "candidate_rows_staged": 0,
        "candidate_jsonl_exists": False,
        "append_requested": False,
        "cohort_append_performed": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
    }
    payload.update(overrides)
    return payload


def _collector(**overrides):
    payload = {
        "report_id": "regular_options_strict_forward_30_market_window_collector",
        "status": "waiting_for_valid_market_window",
        "generated_at_utc": "2026-06-27T01:55:00Z",
        "strict_forward_rows": 0,
        "required_rows": 30,
        "remaining_rows": 30,
        "accepted_profitability": False,
        "candidate_rows_staged": 0,
        "candidate_jsonl_exists": False,
        "cohort_append_performed": False,
    }
    payload.update(overrides)
    return payload


def _scheduler(**overrides):
    payload = {
        "report_id": "regular_options_strict_forward_30_scheduler_health",
        "status": "scheduler_ready_for_next_market_window",
        "generated_at_utc": "2026-06-27T01:56:00Z",
        "blockers": [],
    }
    payload.update(overrides)
    return payload


def _scan_task_health(**overrides):
    payload = {
        "report_id": "regular_options_strict_forward_scan_task_health",
        "status": "scan_tasks_ready_for_next_market_window",
        "generated_at_utc": "2026-06-27T01:56:00Z",
        "blockers": [],
    }
    payload.update(overrides)
    return payload


def _validation(append_allowed: bool = True):
    return {
        "overall_status": "candidate_validation_ready" if append_allowed else "candidate_validation_blocked",
        "candidate_append_validation": {
            "append_allowed": append_allowed,
            "candidate_rows": 1,
            "append_ready_rows": 1 if append_allowed else 0,
            "append_rejected_rows": 0 if append_allowed else 1,
            "append_reject_counts": {} if append_allowed else {"bad_row": 1},
        },
    }


class RegularOptionsStrictForward30CandidateReviewPacketTests(unittest.TestCase):
    def _paths(self, root: Path) -> dict[str, Path]:
        capture = root / "capture.json"
        collector = root / "collector.json"
        scheduler = root / "scheduler.json"
        scan_task_health = root / "regular_options_strict_forward_scan_task_health_latest.json"
        _write_json(capture, _capture())
        _write_json(collector, _collector())
        _write_json(scheduler, _scheduler())
        _write_json(scan_task_health, _scan_task_health())
        return {"capture": capture, "collector": collector, "scheduler": scheduler, "candidate": root / "candidate.jsonl"}

    def test_no_candidate_jsonl_waits_for_real_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._paths(Path(temp_dir))
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_real_candidate_jsonl")
        self.assertFalse(report["candidate_jsonl_exists"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertIn("validate_candidate_jsonl", report["operator_commands"])

    def test_append_allowed_candidate_requires_operator_review_without_append(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            candidate_text = '{"row_id":"candidate-1"}\n'
            paths["candidate"].write_text(candidate_text, encoding="utf8")
            _write_json(
                paths["capture"],
                _capture(
                    status="candidate_rows_valid_no_append",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    candidate_output_path=str(paths["candidate"]),
                    candidate_batch_sha256=packet._sha256_file(paths["candidate"]),
                ),
            )
            _write_json(paths["collector"], _collector(status="collector_stopped_candidate_review_required", candidate_rows_staged=1, candidate_jsonl_exists=True))
            with patch.object(packet.report_builder, "build_report", return_value=_validation(True)):
                report = packet.build_report(
                    candidate_jsonl_path=paths["candidate"],
                    capture_latest_path=paths["capture"],
                    collector_latest_path=paths["collector"],
                    scheduler_health_latest_path=paths["scheduler"],
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "candidate_review_required_append_allowed_no_append_performed")
        self.assertTrue(report["append_allowed_by_current_validation"])
        self.assertEqual(report["candidate_batch_provenance"]["status"], "candidate_batch_matches_fresh_capture")
        self.assertFalse(report["append_performed_by_review_packet"])
        self.assertIn("<EXPLICIT_OPERATOR_APPROVAL_TOKEN>", report["operator_commands"]["guarded_append_template"])

    def test_guarded_append_observed_waits_for_exits_without_safety_block(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            paths["candidate"].write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            _write_json(
                paths["capture"],
                _capture(
                    status="append_performed",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    append_requested=True,
                    cohort_append_performed=True,
                ),
            )
            _write_json(
                paths["collector"],
                _collector(
                    status="collector_stopped_after_guarded_append_waiting_for_exits",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    cohort_append_performed=True,
                ),
            )
            with patch.object(packet.report_builder, "build_report", return_value=_validation(False)):
                report = packet.build_report(
                    candidate_jsonl_path=paths["candidate"],
                    capture_latest_path=paths["capture"],
                    collector_latest_path=paths["collector"],
                    scheduler_health_latest_path=paths["scheduler"],
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "candidate_review_guarded_append_observed_waiting_for_exits")
        self.assertTrue(report["guarded_append_observed"])
        self.assertEqual(report["safety_violations"], [])

    def test_scheduler_blocked_waits_even_without_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._paths(Path(temp_dir))
            _write_json(paths["scheduler"], _scheduler(status="scheduler_config_blocked", blockers=["task_to_run_mismatch"]))
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_scheduler_health")
        self.assertEqual(report["scheduler_blockers"], ["task_to_run_mismatch"])

    def test_stale_scheduler_health_waits_for_fresh_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._paths(Path(temp_dir))
            _write_json(paths["collector"], _collector(generated_at_utc="2026-06-27T02:00:00Z"))
            _write_json(paths["scheduler"], _scheduler(generated_at_utc="2026-06-27T01:59:59Z"))
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_scheduler_health")
        self.assertEqual(report["scheduler_health_freshness"]["status"], "scheduler_health_older_than_collector")
        self.assertIn("scheduler_health_older_than_collector", report["scheduler_blockers"])

    def test_stale_scan_task_health_waits_for_fresh_scan_task_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            _write_json(paths["collector"], _collector(generated_at_utc="2026-06-27T02:00:00Z"))
            _write_json(paths["scheduler"], _scheduler(generated_at_utc="2026-06-27T02:00:01Z"))
            _write_json(root / "regular_options_strict_forward_scan_task_health_latest.json", _scan_task_health(generated_at_utc="2026-06-27T01:59:59Z"))
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_scan_task_health")
        self.assertEqual(report["scan_task_health_freshness"]["status"], "scan_task_health_older_than_collector")
        self.assertIn("scan_task_health_older_than_collector", report["scan_task_health_blockers"])

    def test_stale_capture_without_nested_capture_waits_for_fresh_capture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._paths(Path(temp_dir))
            _write_json(paths["collector"], _collector(generated_at_utc="2026-06-27T02:00:00Z"))
            _write_json(paths["scheduler"], _scheduler(generated_at_utc="2026-06-27T02:00:01Z"))
            _write_json(Path(temp_dir) / "regular_options_strict_forward_scan_task_health_latest.json", _scan_task_health(generated_at_utc="2026-06-27T02:00:01Z"))
            _write_json(paths["capture"], _capture(generated_at_utc="2026-06-27T01:59:59Z"))
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_fresh_capture_report")
        self.assertEqual(report["capture_freshness"]["status"], "capture_older_than_collector")

    def test_stale_capture_uses_fresh_collector_nested_capture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._paths(Path(temp_dir))
            _write_json(paths["capture"], _capture(status="stale_status", generated_at_utc="2026-06-27T01:59:59Z"))
            _write_json(paths["scheduler"], _scheduler(generated_at_utc="2026-06-27T02:00:01Z"))
            _write_json(Path(temp_dir) / "regular_options_strict_forward_scan_task_health_latest.json", _scan_task_health(generated_at_utc="2026-06-27T02:00:01Z"))
            _write_json(
                paths["collector"],
                _collector(
                    generated_at_utc="2026-06-27T02:00:00Z",
                    latest_goal_loop_report={
                        "capture_report": _capture(
                            status="market_window_not_confirmed_no_capture_started",
                            generated_at_utc="2026-06-27T02:00:00Z",
                        )
                    },
                ),
            )
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "candidate_review_waiting_for_real_candidate_jsonl")
        self.assertEqual(report["capture_status"], "market_window_not_confirmed_no_capture_started")
        self.assertEqual(report["capture_freshness"]["effective_capture_source"], "collector_nested_capture_report")

    def test_validation_failed_blocks_append_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            paths["candidate"].write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            _write_json(paths["capture"], _capture(status="candidate_rows_not_append_eligible", candidate_rows_staged=1, candidate_jsonl_exists=True))
            with patch.object(packet.report_builder, "build_report", return_value=_validation(False)):
                report = packet.build_report(
                    candidate_jsonl_path=paths["candidate"],
                    capture_latest_path=paths["capture"],
                    collector_latest_path=paths["collector"],
                    scheduler_health_latest_path=paths["scheduler"],
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "candidate_review_blocked_validation_failed")
        self.assertFalse(report["append_allowed_by_current_validation"])

    def test_candidate_jsonl_without_fresh_capture_hash_blocks_append_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            paths["candidate"].write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            _write_json(
                paths["capture"],
                _capture(
                    status="candidate_rows_valid_no_append",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    candidate_output_path=str(paths["candidate"]),
                ),
            )
            _write_json(paths["collector"], _collector(status="collector_stopped_candidate_review_required", candidate_rows_staged=1, candidate_jsonl_exists=True))
            with patch.object(packet.report_builder, "build_report", return_value=_validation(True)):
                report = packet.build_report(
                    candidate_jsonl_path=paths["candidate"],
                    capture_latest_path=paths["capture"],
                    collector_latest_path=paths["collector"],
                    scheduler_health_latest_path=paths["scheduler"],
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "candidate_review_blocked_candidate_batch_provenance")
        self.assertIn("candidate_batch_sha256_missing_from_fresh_capture", report["candidate_batch_provenance"]["blockers"])

    def test_candidate_jsonl_hash_mismatch_blocks_append_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            paths["candidate"].write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            _write_json(
                paths["capture"],
                _capture(
                    status="candidate_rows_valid_no_append",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    candidate_output_path=str(paths["candidate"]),
                    candidate_batch_sha256="not-the-current-hash",
                ),
            )
            _write_json(paths["collector"], _collector(status="collector_stopped_candidate_review_required", candidate_rows_staged=1, candidate_jsonl_exists=True))
            with patch.object(packet.report_builder, "build_report", return_value=_validation(True)):
                report = packet.build_report(
                    candidate_jsonl_path=paths["candidate"],
                    capture_latest_path=paths["capture"],
                    collector_latest_path=paths["collector"],
                    scheduler_health_latest_path=paths["scheduler"],
                    generated_at_utc=NOW,
                )

        self.assertEqual(report["status"], "candidate_review_blocked_candidate_batch_provenance")
        self.assertIn("candidate_batch_sha256_mismatch_with_fresh_capture", report["candidate_batch_provenance"]["blockers"])

    def test_write_outputs_creates_review_packet_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            report = packet.build_report(
                candidate_jsonl_path=paths["candidate"],
                capture_latest_path=paths["capture"],
                collector_latest_path=paths["collector"],
                scheduler_health_latest_path=paths["scheduler"],
                generated_at_utc=NOW,
            )
            artifacts = packet.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "regular_options_strict_forward_30_candidate_review_packet_latest.json").exists())
            self.assertTrue((root / "doc.md").exists())
            doc = (root / "doc.md").read_text(encoding="utf8")
            self.assertIn("Candidate batch provenance", doc)
            self.assertIn("Scan-task health freshness", doc)
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
