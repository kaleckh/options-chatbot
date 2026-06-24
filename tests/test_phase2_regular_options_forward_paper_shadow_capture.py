from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import run_phase2_regular_options_forward_paper_shadow_capture as capture


NOW = "2026-06-23T15:00:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _real_phase2_scan_pick() -> dict:
    return {
        "scan_date": "2026-06-23",
        "ticker": "SPY",
        "playbook_id": "volatility_expansion_observation",
        "contract_symbol": "SPY260630C00753000",
        "short_contract_symbol": "SPY260630C00765000",
        "quote_timestamp_utc": "2026-06-23T15:00:00Z",
        "quote_source": "opra_nbbo",
        "scan_run_id": "same-day-scan",
        "entry_execution_price": 4.67,
    }


class Phase2ForwardPaperShadowCaptureTests(unittest.TestCase):
    def test_real_zero_rows_no_append_and_removes_stale_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            candidate = root / "candidate.jsonl"
            cohort = root / "cohort.jsonl"
            _write_jsonl(
                scan_picks,
                [
                    {
                        "scan_date": "2026-06-16",
                        "ticker": "SPY",
                        "playbook_id": "volatility_expansion_observation",
                        "contract_symbol": "SPY260630C00753000",
                        "short_contract_symbol": "SPY260630C00765000",
                        "quote_timestamp_utc": "2026-06-16T17:45:13Z",
                        "scan_run_id": "old-scan",
                        "entry_execution_price": 4.67,
                    }
                ],
            )
            candidate.write_text('{"stale":true}\n', encoding="utf8")

            report = capture.build_capture_report(
                source_scan_picks_path=scan_picks,
                candidate_output_path=candidate,
                cohort_log_path=cohort,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "no_phase2_natural_selections_no_append")
            self.assertEqual(report["candidate_rows_staged"], 0)
            self.assertFalse(candidate.exists())
            self.assertFalse(cohort.exists())
            self.assertFalse(report["cohort_append_performed"])
            self.assertFalse(report["live_entry_allowed"])
            self.assertFalse(report["auto_track_allowed"])
            self.assertFalse(report["broker_order_allowed"])

    def test_valid_real_rows_default_no_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            candidate = root / "candidate.jsonl"
            cohort = root / "cohort.jsonl"
            _write_jsonl(scan_picks, [_real_phase2_scan_pick()])

            report = capture.build_capture_report(
                source_scan_picks_path=scan_picks,
                candidate_output_path=candidate,
                cohort_log_path=cohort,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "candidate_rows_valid_no_append")
            self.assertEqual(report["candidate_rows_staged"], 1)
            self.assertTrue(candidate.exists())
            self.assertFalse(cohort.exists())
            self.assertTrue(report["stage_report"]["validation"]["append_allowed"])
            self.assertFalse(report["cohort_append_performed"])

    def test_append_valid_real_rows_to_temp_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            candidate = root / "candidate.jsonl"
            cohort = root / "cohort.jsonl"
            _write_jsonl(scan_picks, [_real_phase2_scan_pick()])

            report = capture.build_capture_report(
                source_scan_picks_path=scan_picks,
                candidate_output_path=candidate,
                cohort_log_path=cohort,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                approval_token=appender.PHASE2_APPROVAL_TOKEN,
                append=True,
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "append_performed")
            self.assertTrue(report["cohort_append_performed"])
            self.assertEqual(report["append_report"]["appended_rows"], 1)
            self.assertTrue(report["append_report"]["post_append_verification"]["passed"])
            self.assertTrue(cohort.exists())
            self.assertEqual(len(cohort.read_text(encoding="utf8").strip().splitlines()), 1)
            self.assertFalse(report["broker_order_allowed"])
            self.assertFalse(report["auto_track_allowed"])

    def test_append_dry_run_does_not_write_temp_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            candidate = root / "candidate.jsonl"
            cohort = root / "cohort.jsonl"
            _write_jsonl(scan_picks, [_real_phase2_scan_pick()])

            report = capture.build_capture_report(
                source_scan_picks_path=scan_picks,
                candidate_output_path=candidate,
                cohort_log_path=cohort,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                approval_token=appender.PHASE2_APPROVAL_TOKEN,
                append=True,
                dry_run=True,
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "append_ready_dry_run")
            self.assertFalse(report["cohort_append_performed"])
            self.assertFalse(cohort.exists())

    def test_runner_does_not_call_scanner_or_trading_paths(self) -> None:
        source = Path(capture.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

        forbidden_calls = {
            "run_daily_ops",
            "log_scan_picks",
            "validate_pending_scan_candidates",
            "submit_order",
            "create_position",
            "auto_track",
        }
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
