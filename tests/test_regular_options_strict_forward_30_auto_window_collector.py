import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_strict_forward_30_auto_window_collector as auto_collector


def _collector_report(**overrides):
    payload = {
        "status": "waiting_for_valid_market_window",
        "strict_forward_rows": 0,
        "required_rows": 30,
        "remaining_rows": 30,
        "accepted_profitability": False,
        "candidate_rows_staged": 0,
        "candidate_jsonl_exists": False,
        "cohort_append_performed": False,
        "run_scan_sweep_requested": False,
        "append_requested": False,
        "safety_violations": [],
        "next_action": "wait_for_valid_market_window_then_run_safe_no_append_collector_command",
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")


class RegularOptionsStrictForward30AutoWindowCollectorTests(unittest.TestCase):
    def test_market_window_state_marks_saturday_closed(self):
        window = auto_collector.market_window_state("2026-06-27T16:00:00Z")

        self.assertEqual(window["market_window_status"], "closed")
        self.assertFalse(window["market_window_confirmed"])
        self.assertFalse(window["current_date_is_market_day"])
        self.assertEqual(window["default_selection_date"], "2026-06-26")

    def test_market_window_state_marks_regular_open_window(self):
        window = auto_collector.market_window_state("2026-06-29T14:00:00Z")

        self.assertEqual(window["market_window_status"], "open")
        self.assertTrue(window["market_window_confirmed"])
        self.assertEqual(window["current_market_date"], "2026-06-29")
        self.assertEqual(window["default_selection_date"], "2026-06-29")

    def test_closed_window_calls_collector_without_scan_or_append(self):
        with patch.object(auto_collector.collector, "build_report", return_value=_collector_report()) as build:
            report = auto_collector.build_report(
                generated_at_utc="2026-06-27T16:00:00Z",
                write_outputs=False,
            )

        self.assertEqual(report["status"], "auto_window_collector_waiting_for_open_market_window")
        called = build.call_args.kwargs
        self.assertFalse(called["market_window_confirmed"])
        self.assertEqual(called["market_window_status"], "closed")
        self.assertFalse(called["run_scan_sweep"])
        self.assertFalse(called["append"])
        self.assertEqual(called["selection_date"], "2026-06-26")

    def test_open_window_calls_bounded_collector_with_scan_no_append(self):
        with patch.object(
            auto_collector.collector,
            "build_report",
            return_value=_collector_report(
                status="collector_attempts_exhausted_waiting_for_more_rows",
                run_scan_sweep_requested=True,
            ),
        ) as build:
            report = auto_collector.build_report(
                generated_at_utc="2026-06-29T14:00:00Z",
                max_attempts=2,
                sleep_seconds=0,
                write_outputs=False,
            )

        self.assertEqual(report["status"], "auto_window_collector_ran_open_window")
        called = build.call_args.kwargs
        self.assertTrue(called["market_window_confirmed"])
        self.assertEqual(called["market_window_status"], "open")
        self.assertTrue(called["run_scan_sweep"])
        self.assertFalse(called["append"])
        self.assertEqual(called["max_attempts"], 2)
        self.assertEqual(called["selection_date"], "2026-06-29")

    def test_open_window_pauses_when_candidate_batch_is_pending_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.jsonl"
            capture = root / "capture.json"
            collector_latest = root / "collector.json"
            candidate.write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            candidate_sha = auto_collector._sha256_file(candidate)
            _write_json(
                capture,
                {
                    "status": "candidate_rows_valid_no_append",
                    "generated_at_utc": "2026-06-29T14:00:00Z",
                    "candidate_rows_staged": 1,
                    "candidate_jsonl_exists": True,
                    "candidate_output_path": str(candidate),
                    "candidate_batch_sha256": candidate_sha,
                    "append_requested": False,
                    "cohort_append_performed": False,
                },
            )
            _write_json(
                collector_latest,
                _collector_report(
                    status="collector_stopped_candidate_review_required",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                    run_scan_sweep_requested=True,
                    next_action="review_candidate_jsonl_and_only_append_with_explicit_operator_approval_token",
                ),
            )
            with patch.object(auto_collector.collector, "build_report") as build:
                report = auto_collector.build_report(
                    generated_at_utc="2026-06-29T14:05:00Z",
                    candidate_output_path=candidate,
                    capture_latest_path=capture,
                    collector_latest_path=collector_latest,
                    write_outputs=False,
                )
            candidate_still_exists = candidate.exists()

        build.assert_not_called()
        self.assertEqual(report["status"], "auto_window_collector_paused_pending_candidate_review")
        self.assertFalse(report["run_scan_sweep_requested"])
        self.assertTrue(report["pending_candidate_review"]["pending"])
        self.assertEqual(report["collector_status"], "collector_stopped_candidate_review_required")
        self.assertEqual(report["candidate_rows_staged"], 1)
        self.assertTrue(candidate_still_exists)

    def test_open_window_skip_scan_sweep_still_pauses_when_candidate_batch_is_pending_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.jsonl"
            capture = root / "capture.json"
            collector_latest = root / "collector.json"
            candidate.write_text('{"row_id":"candidate-1"}\n', encoding="utf8")
            candidate_sha = auto_collector._sha256_file(candidate)
            _write_json(
                capture,
                {
                    "status": "candidate_rows_valid_no_append",
                    "generated_at_utc": "2026-06-29T14:00:00Z",
                    "candidate_rows_staged": 1,
                    "candidate_jsonl_exists": True,
                    "candidate_output_path": str(candidate),
                    "candidate_batch_sha256": candidate_sha,
                    "append_requested": False,
                    "cohort_append_performed": False,
                },
            )
            _write_json(
                collector_latest,
                _collector_report(
                    status="collector_stopped_candidate_review_required",
                    candidate_rows_staged=1,
                    candidate_jsonl_exists=True,
                ),
            )
            with patch.object(auto_collector.collector, "build_report") as build:
                report = auto_collector.build_report(
                    generated_at_utc="2026-06-29T14:05:00Z",
                    skip_scan_sweep=True,
                    candidate_output_path=candidate,
                    capture_latest_path=capture,
                    collector_latest_path=collector_latest,
                    write_outputs=False,
                )

        build.assert_not_called()
        self.assertEqual(report["status"], "auto_window_collector_paused_pending_candidate_review")
        self.assertTrue(report["skip_scan_sweep_requested"])
        self.assertFalse(report["run_scan_sweep_requested"])
        self.assertTrue(report["pending_candidate_review"]["pending"])

    def test_open_window_skip_scan_sweep_uses_existing_scan_picks(self):
        with patch.object(auto_collector.collector, "build_report", return_value=_collector_report()) as build:
            report = auto_collector.build_report(
                generated_at_utc="2026-06-29T14:00:00Z",
                skip_scan_sweep=True,
                write_outputs=False,
            )

        self.assertEqual(report["status"], "auto_window_collector_ran_open_window")
        self.assertTrue(report["skip_scan_sweep_requested"])
        called = build.call_args.kwargs
        self.assertTrue(called["market_window_confirmed"])
        self.assertFalse(called["run_scan_sweep"])
        self.assertFalse(called["append"])

    def test_write_outputs_persists_auto_window_latest_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "forward"
            docs_report = Path(tmp) / "docs" / "auto.md"
            with patch.object(auto_collector.collector, "build_report", return_value=_collector_report()):
                report = auto_collector.build_report(
                    generated_at_utc="2026-06-27T16:00:00Z",
                    output_dir=output_dir,
                    docs_report=docs_report,
                )

            latest_json = output_dir / "regular_options_strict_forward_30_auto_window_collector_latest.json"
            latest_md = output_dir / "regular_options_strict_forward_30_auto_window_collector_latest.md"
            self.assertTrue(latest_json.exists())
            self.assertTrue(latest_md.exists())
            self.assertTrue(docs_report.exists())
            payload = json.loads(latest_json.read_text(encoding="utf8"))
            self.assertEqual(payload["status"], "auto_window_collector_waiting_for_open_market_window")
            self.assertEqual(payload["artifacts"]["latest_json"], str(latest_json))
            self.assertIn("Auto-Window Collector", latest_md.read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
