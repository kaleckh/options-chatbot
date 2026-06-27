from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_phase2_regular_options_forward_paper_shadow_candidate_rows as stager
from scripts import build_volatility_expansion_forward_paper_shadow_report as report_builder
from tests import test_volatility_expansion_forward_paper_shadow_report as report_fixtures


NOW = "2026-06-23T15:00:00Z"
FIXTURE = Path("tests/fixtures/phase2_forward_candidate_rows_valid.json")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class Phase2ForwardPaperShadowCandidateStagerTests(unittest.TestCase):
    def test_closed_market_no_write_blocks_without_candidate_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "candidate.jsonl"
            latest = root / "latest.json"
            docs = root / "report.md"

            report = stager.build_stage_report(
                output_path=output,
                latest_json_path=latest,
                docs_report_path=docs,
                no_write=True,
                market_window_status="closed",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "blocked_market_window_not_confirmed")
            self.assertFalse(output.exists())
            self.assertFalse(latest.exists())
            self.assertFalse(docs.exists())
            self.assertFalse(report["broker_order_allowed"])
            self.assertFalse(report["auto_track_allowed"])

    def test_fixture_stages_schema_valid_but_append_ineligible_phase2_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "candidate_fixture.jsonl"
            latest = root / "latest.json"
            docs = root / "report.md"

            report = stager.build_stage_report(
                fixture_path=FIXTURE,
                output_path=output,
                latest_json_path=latest,
                docs_report_path=docs,
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "fixture_rows_staged_append_ineligible")
            self.assertEqual(report["candidate_rows_staged"], 2)
            self.assertFalse(report["validation"]["append_allowed"])
            self.assertEqual(report["validation"]["append_reject_counts"]["fixture_rows_not_append_eligible"], 2)
            self.assertTrue(output.exists())
            self.assertTrue(latest.exists())
            self.assertTrue(docs.exists())
            staged_rows = [json.loads(line) for line in output.read_text(encoding="utf8").splitlines()]
            lanes = {row["lane_id"] for row in staged_rows}
            self.assertEqual(lanes, {"volatility_expansion_observation", "bullish_pullback_observation"})

    def test_fixture_to_canonical_output_quarantines_candidate_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl"
            output.write_text("{\"old\":\"fixture\"}\n", encoding="utf8")
            original_default = stager.DEFAULT_OUTPUT
            stager.DEFAULT_OUTPUT = output
            try:
                report = stager.build_stage_report(
                    fixture_path=FIXTURE,
                    output_path=output,
                    latest_json_path=root / "latest.json",
                    docs_report_path=root / "report.md",
                    generated_at_utc=NOW,
                )
            finally:
                stager.DEFAULT_OUTPUT = original_default

            self.assertEqual(report["status"], "fixture_rows_staged_append_ineligible")
            self.assertFalse(output.exists())
            self.assertFalse(report["candidate_jsonl_written"])
            self.assertFalse(report["validation"]["append_allowed"])

    def test_real_market_window_scan_pick_can_be_append_ready_in_temp_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
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
                    "quote_source": "opra_nbbo",
                    "legs": [
                        {"role": "long", "bid": 6.35, "ask": 6.37},
                        {"role": "short", "bid": 1.70, "ask": 1.72},
                    ],
                },
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "candidate_rows_staged_validation_passed")
            self.assertTrue(report["validation"]["append_allowed"])
            self.assertTrue((root / "candidate.jsonl").exists())
            staged = json.loads((root / "candidate.jsonl").read_text(encoding="utf8").splitlines()[0])
            self.assertEqual(staged["scanner_run_id"], "same-day-scan")

    def test_real_mode_rejects_missing_entry_quote_source_instead_of_defaulting_to_opra(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
                "scan_date": "2026-06-23",
                "ticker": "SPY",
                "playbook_id": "volatility_expansion_observation",
                "contract_symbol": "SPY260630C00753000",
                "short_contract_symbol": "SPY260630C00765000",
                "quote_timestamp_utc": "2026-06-23T15:00:00Z",
                "scan_run_id": "same-day-scan",
                "entry_quote_snapshot": {
                    "quote_timestamp_utc": "2026-06-23T15:00:00Z",
                    "legs": [
                        {"role": "long", "bid": 6.35, "ask": 6.37},
                        {"role": "short", "bid": 1.70, "ask": 1.72},
                    ],
                },
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "no_phase2_natural_selections")
            self.assertEqual(report["candidate_rows_staged"], 0)
            self.assertEqual(report["rejected_counts"]["missing_entry_quote_source"], 1)
            self.assertFalse((root / "candidate.jsonl").exists())

    def test_real_mode_rejects_untrusted_entry_quote_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
                "scan_date": "2026-06-23",
                "ticker": "SPY",
                "playbook_id": "volatility_expansion_observation",
                "contract_symbol": "SPY260630C00753000",
                "short_contract_symbol": "SPY260630C00765000",
                "quote_timestamp_utc": "2026-06-23T15:00:00Z",
                "quote_source": "unknown_vendor",
                "scan_run_id": "same-day-scan",
                "entry_quote_snapshot": {
                    "quote_timestamp_utc": "2026-06-23T15:00:00Z",
                    "legs": [
                        {"role": "long", "bid": 6.35, "ask": 6.37},
                        {"role": "short", "bid": 1.70, "ask": 1.72},
                    ],
                },
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "no_phase2_natural_selections")
            self.assertEqual(report["candidate_rows_staged"], 0)
            self.assertEqual(report["rejected_counts"]["untrusted_entry_quote_source"], 1)
            self.assertFalse((root / "candidate.jsonl").exists())

    def test_real_mode_does_not_stage_stale_scan_pick_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
                "scan_date": "2026-06-16",
                "ticker": "SPY",
                "playbook_id": "volatility_expansion_observation",
                "contract_symbol": "SPY260630C00753000",
                "short_contract_symbol": "SPY260630C00765000",
                "quote_timestamp_utc": "2026-06-16T17:45:13Z",
                "scan_run_id": "old-scan",
                "entry_execution_price": 4.67,
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc=NOW,
            )

            self.assertEqual(report["status"], "no_phase2_natural_selections")
            self.assertEqual(report["candidate_rows_staged"], 0)
            self.assertEqual(report["rejected_counts"]["not_current_market_window_selection"], 1)

    def test_default_selection_date_uses_new_york_market_date_not_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
                "scan_date": "2026-06-26",
                "ticker": "SPY",
                "playbook_id": "volatility_expansion_observation",
                "contract_symbol": "SPY260630C00753000",
                "short_contract_symbol": "SPY260630C00765000",
                "quote_source": "opra_nbbo",
                "quote_timestamp_utc": "2026-06-26T19:55:00Z",
                "scan_run_id": "after-hours-source",
                "entry_quote_snapshot": {
                    "quote_timestamp_utc": "2026-06-26T19:55:00Z",
                    "quote_source": "opra_nbbo",
                    "legs": [
                        {"role": "long", "bid": 6.35, "ask": 6.37},
                        {"role": "short", "bid": 1.70, "ask": 1.72},
                    ],
                },
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc="2026-06-27T03:25:22Z",
            )

            self.assertEqual(report["status"], "candidate_rows_staged_validation_passed")
            self.assertEqual(report["candidate_rows_staged"], 1)
            self.assertTrue((root / "candidate.jsonl").exists())

    def test_row_timestamp_fallback_uses_new_york_market_date_not_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scan_picks = root / "scan_picks.jsonl"
            source_row = {
                "ticker": "SPY",
                "playbook_id": "volatility_expansion_observation",
                "contract_symbol": "SPY260630C00753000",
                "short_contract_symbol": "SPY260630C00765000",
                "quote_source": "opra_nbbo",
                "selection_timestamp_utc": "2026-06-27T01:25:00Z",
                "quote_timestamp_utc": "2026-06-27T01:25:00Z",
                "scanner_run_id": "late-utc-source",
                "entry_quote_snapshot": {
                    "quote_timestamp_utc": "2026-06-27T01:25:00Z",
                    "quote_source": "opra_nbbo",
                    "legs": [
                        {"role": "long", "bid": 6.35, "ask": 6.37},
                        {"role": "short", "bid": 1.70, "ask": 1.72},
                    ],
                },
            }
            _write_jsonl(scan_picks, [source_row])

            report = stager.build_stage_report(
                source_scan_picks_path=scan_picks,
                output_path=root / "candidate.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "report.md",
                market_window_confirmed=True,
                market_window_status="open",
                generated_at_utc="2026-06-27T03:25:22Z",
            )
            staged_rows = [json.loads(line) for line in (root / "candidate.jsonl").read_text(encoding="utf8").splitlines()]

            self.assertEqual(report["status"], "candidate_rows_staged_validation_passed")
            self.assertEqual(report["candidate_rows_staged"], 1)
            self.assertEqual(staged_rows[0]["selection_date"], "2026-06-26")

    def test_report_counts_selection_lifecycle_once(self) -> None:
        entry = report_fixtures._row(
            1,
            None,
            row_id="lifecycle-entry",
            selection_id="same-selection",
            denominator_status="open_waiting_policy_exit",
        )
        exit_row = report_fixtures._row(
            2,
            25.0,
            row_id="lifecycle-exit",
            selection_id="same-selection",
            selection_date=entry["selection_date"],
            selection_timestamp_utc=entry["selection_timestamp_utc"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = report_fixtures._base_sources(root)
            _write_jsonl(paths["cohort_log_path"], [entry, exit_row])
            report = report_builder.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["counts"]["event_row_count"], 2)
        self.assertEqual(report["counts"]["total_natural_selections"], 1)
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 1)


if __name__ == "__main__":
    unittest.main()
