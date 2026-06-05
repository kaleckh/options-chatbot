from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_repair_attempt_readback as readback
from scripts.regular_options_repair_targets import repair_attempt_key


class RegularOptionsRepairAttemptReadbackTests(unittest.TestCase):
    def test_build_readback_flattens_attempt_keys_and_keeps_latest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_artifact = "data/options-validation/runs/wmt-replay.json"
            key = repair_attempt_key(
                source_artifact=source_artifact,
                ticker="WMT",
                contract_symbol="WMT260402C00140000",
                missing_quote_date="2026-03-25",
            )
            first = root / "first.json"
            first.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T10:00:00Z",
                        "dry_run": True,
                        "plan_only": False,
                        "write_artifacts": False,
                        "repair_attempts": [
                            {
                                "repair_attempt_key": key,
                                "repair_attempt_keys": [key],
                                "source_label": "thetadata_opra_nbbo_1m",
                                "outcome": "exact_date_no_match",
                                "proof_repair_status": "current_source_exhausted",
                                "exact_missing_date_status": "no_rows_found",
                                "exact_date_row_count": 0,
                                "lookahead_row_count": 0,
                                "total_row_count": 0,
                                "request_dates_attempted": ["2026-03-25"],
                                "available_quote_dates": [],
                                "current_source_exhausted_for_exact_date": True,
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )
            second = root / "second.json"
            second.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T11:00:00Z",
                        "dry_run": True,
                        "plan_only": False,
                        "write_artifacts": False,
                        "repair_attempts": [
                            {
                                "repair_attempt_key": key,
                                "repair_attempt_keys": [key],
                                "source_label": "thetadata_opra_nbbo_1m",
                                "outcome": "lookahead_only_rows_found",
                                "proof_repair_status": "lookahead_only_not_exact_proof",
                                "exact_missing_date_status": "no_rows_found",
                                "exact_date_row_count": 0,
                                "lookahead_row_count": 1,
                                "total_row_count": 1,
                                "request_dates_attempted": ["2026-03-25", "2026-03-26"],
                                "available_quote_dates": ["2026-03-26"],
                                "first_available_after_missing_date": "2026-03-26",
                                "current_source_exhausted_for_exact_date": True,
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )

            report = readback.build_readback([first, second])

        self.assertEqual(report["summary"]["attempt_record_count"], 2)
        self.assertEqual(report["summary"]["latest_attempt_count"], 1)
        self.assertEqual(report["summary"]["latest_outcome_counts"], {"lookahead_only_rows_found": 1})
        latest = report["latest_attempts"][0]
        self.assertEqual(latest["repair_attempt_key"], key)
        self.assertEqual(latest["source_artifact"], source_artifact)
        self.assertEqual(latest["ticker"], "WMT")
        self.assertEqual(latest["contract_symbol"], "WMT260402C00140000")
        self.assertEqual(latest["missing_quote_date"], "2026-03-25")
        self.assertEqual(latest["first_available_after_missing_date"], "2026-03-26")

    def test_build_readback_infers_legacy_summary_attempts_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = root / "run.json"
            csv_path = root / "quotes.csv"
            summary_path = root / "legacy-summary.json"
            run_path.write_text(
                json.dumps(
                    {
                        "unpriced_trades": [
                            {
                                "ticker": "WMT",
                                "date": "2026-02-25",
                                "missing_quote_date": "2026-03-25",
                                "missing_short_contract_symbol": "WMT260402C00140000",
                            },
                            {
                                "ticker": "PG",
                                "date": "2026-02-25",
                                "missing_quote_date": "2026-03-25",
                                "missing_short_contract_symbol": "PG260402C00170000",
                            },
                        ]
                    }
                ),
                encoding="utf8",
            )
            csv_path.write_text(
                "as_of_utc,contract_symbol,bid,ask\n"
                "2026-03-26T15:55:00Z,WMT260402C00140000,1.00,1.10\n",
                encoding="utf8",
            )
            summary_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "input_run_paths": [str(run_path)],
                        "lookahead_calendar_days": 1,
                        "csv_path": str(csv_path),
                        "rows_by_contract": {"WMT260402C00140000": 1},
                        "rows_by_date": {"2026-03-26": 1},
                        "errors": ["2026-03-25 WMT260402C00140000: no matched rows"],
                        "import_result": {"source_label": "thetadata_opra_nbbo_1m"},
                    }
                ),
                encoding="utf8",
            )

            report = readback.build_readback([summary_path])

        self.assertEqual(report["summary"]["latest_attempt_count"], 2)
        latest_by_contract = {row["contract_symbol"]: row for row in report["latest_attempts"]}
        wmt = latest_by_contract["WMT260402C00140000"]
        self.assertTrue(wmt["legacy_inferred"])
        self.assertEqual(wmt["outcome"], "lookahead_only_rows_found")
        self.assertEqual(wmt["proof_repair_status"], "lookahead_only_not_exact_proof")
        self.assertEqual(wmt["exact_date_row_count"], 0)
        self.assertEqual(wmt["lookahead_row_count"], 1)
        self.assertTrue(wmt["current_source_exhausted_for_exact_date"])
        pg = latest_by_contract["PG260402C00170000"]
        self.assertEqual(pg["outcome"], "exact_date_no_match")
        self.assertEqual(pg["proof_repair_status"], "current_source_exhausted")

    def test_legacy_summary_without_csv_does_not_assign_aggregate_dates_as_exact_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = root / "run.json"
            summary_path = root / "legacy-summary.json"
            run_path.write_text(
                json.dumps(
                    {
                        "unpriced_trades": [
                            {
                                "ticker": "WMT",
                                "missing_quote_date": "2026-03-25",
                                "missing_short_contract_symbol": "WMT260402C00140000",
                            },
                            {
                                "ticker": "PG",
                                "missing_quote_date": "2026-03-25",
                                "missing_short_contract_symbol": "PG260402C00170000",
                            },
                        ]
                    }
                ),
                encoding="utf8",
            )
            summary_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "input_run_paths": [str(run_path)],
                        "lookahead_calendar_days": 1,
                        "rows_by_contract": {
                            "WMT260402C00140000": 1,
                            "PG260402C00170000": 1,
                        },
                        "rows_by_date": {"2026-03-25": 2},
                        "import_result": {"source_label": "thetadata_opra_nbbo_1m"},
                    }
                ),
                encoding="utf8",
            )

            report = readback.build_readback([summary_path])

        self.assertEqual(report["summary"]["latest_attempt_count"], 2)
        for row in report["latest_attempts"]:
            self.assertEqual(row["exact_date_row_count"], 0)
            self.assertEqual(row["lookahead_row_count"], 1)
            self.assertEqual(row["total_row_count"], 1)
            self.assertEqual(row["outcome"], "lookahead_only_rows_found")
            self.assertTrue(row["legacy_aggregate_date_counts_unsafe"])
            self.assertLessEqual(
                int(row["exact_date_row_count"]) + int(row["lookahead_row_count"]),
                int(row["total_row_count"]),
            )


if __name__ == "__main__":
    unittest.main()
