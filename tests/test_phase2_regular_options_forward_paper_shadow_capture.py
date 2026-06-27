from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import build_regular_options_strict_forward_30_exit_completion_stager as exit_stager
from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report
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
        "entry_quote_snapshot": {
            "quote_timestamp_utc": "2026-06-23T15:00:00Z",
            "legs": [
                {"role": "long", "bid": 6.35, "ask": 6.37},
                {"role": "short", "bid": 1.70, "ask": 1.72},
            ],
        },
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
            staged = json.loads(candidate.read_text(encoding="utf8").splitlines()[0])
            self.assertEqual(staged["scanner_run_id"], "same-day-scan")

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

    def test_temp_entry_and_exit_lifecycle_counts_one_strict_completed_forward_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            entry_candidate = root / "entry-candidate.jsonl"
            exit_candidate = root / "exit-candidate.jsonl"
            exit_evidence = root / "exit-evidence.jsonl"
            cohort = root / "cohort.jsonl"
            _write_jsonl(scan_picks, [_real_phase2_scan_pick()])

            entry_report = capture.build_capture_report(
                source_scan_picks_path=scan_picks,
                candidate_output_path=entry_candidate,
                cohort_log_path=cohort,
                latest_json_path=root / "entry-latest.json",
                docs_report_path=root / "entry-report.md",
                market_window_confirmed=True,
                market_window_status="open",
                approval_token=appender.PHASE2_APPROVAL_TOKEN,
                append=True,
                generated_at_utc=NOW,
            )
            open_row = json.loads(cohort.read_text(encoding="utf8").splitlines()[0])
            _write_jsonl(
                exit_evidence,
                [
                    {
                        "selection_id": open_row["selection_id"],
                        "exit_quote_source": "opra_nbbo",
                        "exit_quote_timestamp_utc": "2026-06-29T19:55:00Z",
                        "exit_bid": 5.9,
                        "exit_ask": 6.0,
                        "policy_exit_condition": "policy_exit_at_profit_target",
                        "net_pnl_usd": 123.45,
                        "market_window_status": "open",
                        "captured_at_utc": "2026-06-29T19:55:03Z",
                    }
                ],
            )

            exit_stage_report = exit_stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=exit_evidence,
                output_path=exit_candidate,
                latest_json_path=root / "exit-latest.json",
                docs_report_path=root / "exit-report.md",
                generated_at_utc="2026-06-29T20:00:00Z",
            )
            exit_append_report = appender.build_append_report(
                candidate_rows_path=exit_candidate,
                cohort_log_path=cohort,
                schema_path=forward_report.DEFAULT_PHASE2_SCHEMA,
                allowed_lane_ids=forward_report.PHASE2_FROZEN_LANE_IDS,
                approval_token=appender.PHASE2_APPROVAL_TOKEN,
                market_window_confirmed=True,
                generated_at_utc="2026-06-29T20:00:00Z",
            )
            final_report = forward_report.build_report(
                cohort_log_path=cohort,
                schema_path=forward_report.DEFAULT_PHASE2_SCHEMA,
                allowed_lane_ids=forward_report.PHASE2_FROZEN_LANE_IDS,
                generated_at_utc="2026-06-29T20:01:00Z",
            )

        self.assertEqual(entry_report["status"], "append_performed")
        self.assertEqual(exit_stage_report["status"], "exit_completion_candidates_ready_no_append")
        self.assertTrue(exit_stage_report["append_allowed_by_validation"])
        self.assertEqual(exit_append_report["status"], "append_performed")
        self.assertTrue(exit_append_report["cohort_append_performed"])
        self.assertEqual(final_report["counts"]["open_waiting_policy_exit_count"], 1)
        self.assertEqual(final_report["counts"]["exact_completed_forward_pnl_count"], 1)
        self.assertEqual(final_report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 1)
        self.assertEqual(final_report["acceptance_readiness"]["strict_accepted_row_ids"][0], exit_stage_report["candidate_row_ids"][0])
        self.assertFalse(final_report["live_entry_allowed"])
        self.assertFalse(final_report["auto_track_allowed"])
        self.assertFalse(final_report["broker_order_allowed"])

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
