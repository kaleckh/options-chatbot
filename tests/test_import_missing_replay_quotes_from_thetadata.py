from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import import_missing_replay_quotes_from_thetadata as importer


def _write_run(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "unpriced_trades": [
                    {
                        "ticker": "UNH",
                        "date": "2025-10-28",
                        "missing_quote_date": "2025-11-10",
                        "missing_short_contract_symbol": "UNH251128C00410000",
                        "unpriced_reason": "missing_exit_quote_for_leg",
                    },
                    {
                        "ticker": "UNH",
                        "date": "2025-10-28",
                        "missing_quote_date": "2025-11-10",
                        "missing_short_contract_symbol": "UNH251128C00410000",
                        "unpriced_reason": "missing_exit_quote_for_leg",
                    },
                    {
                        "ticker": "UNH",
                        "date": "2025-10-29",
                        "missing_quote_date": "2025-11-20",
                        "missing_short_contract_symbol": "UNH251205C00390000",
                        "unpriced_reason": "missing_exit_quote_for_leg",
                    },
                ]
            }
        ),
        encoding="utf8",
    )


class ImportMissingReplayQuotesFromThetaDataTests(unittest.TestCase):
    def test_dry_run_fetches_but_does_not_write_summary_csv_or_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = root / "run.json"
            output_dir = root / "out"
            _write_run(run_path)
            stdout = io.StringIO()
            matched_rows = [
                {
                    "as_of_utc": "2025-11-10T15:55:00Z",
                    "contract_symbol": "UNH251128C00410000",
                }
            ]

            argv = [
                "import_missing_replay_quotes_from_thetadata.py",
                str(run_path),
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--json",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                importer, "_theta_rows_for_contract", return_value=matched_rows
            ) as theta_rows, mock.patch.object(
                importer, "import_historical_option_snapshots"
            ) as import_snapshots, redirect_stdout(stdout):
                self.assertEqual(importer.main(), 0)

            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["write_artifacts"])
            self.assertIsNone(payload["csv_path"])
            self.assertIsNone(payload["summary_path"])
            self.assertEqual(payload["base_unique_items"], 2)
            self.assertEqual(payload["repair_manifest"]["base_target_count"], 2)
            self.assertEqual(payload["repair_manifest"]["source_occurrence_count"], 3)
            self.assertEqual(payload["normalized_rows"], 2)
            self.assertEqual(theta_rows.call_count, 2)
            import_snapshots.assert_not_called()
            self.assertFalse(output_dir.exists())

    def test_plan_only_prints_de_duped_manifest_without_theta_requests_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = root / "run.json"
            output_dir = root / "out"
            _write_run(run_path)
            stdout = io.StringIO()

            argv = [
                "import_missing_replay_quotes_from_thetadata.py",
                str(run_path),
                "--output-dir",
                str(output_dir),
                "--lookahead-calendar-days",
                "2",
                "--max-requests",
                "1",
                "--plan-only",
                "--json",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                importer, "_theta_rows_for_contract"
            ) as theta_rows, redirect_stdout(stdout):
                self.assertEqual(importer.main(), 0)

            payload = json.loads(stdout.getvalue())
            manifest = payload["repair_manifest"]
            self.assertTrue(payload["plan_only"])
            self.assertFalse(payload["write_artifacts"])
            self.assertEqual(payload["request_count"], 0)
            self.assertEqual(payload["normalized_rows"], 0)
            self.assertEqual(payload["base_unique_items"], 2)
            self.assertGreater(payload["expanded_unique_items"], payload["unique_items"])
            self.assertEqual(payload["unique_items"], 1)
            self.assertTrue(manifest["max_requests_applied"])
            self.assertEqual(manifest["request_target_count"], 1)
            self.assertEqual(manifest["base_targets"][0]["contract_symbol"], "UNH251128C00410000")
            self.assertIsNone(payload["summary_path"])
            self.assertFalse(output_dir.exists())
            theta_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
