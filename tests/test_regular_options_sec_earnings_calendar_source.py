from __future__ import annotations

import csv
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_regular_options_sec_earnings_calendar_source as sec_source
from workspace_tempdir import WorkspaceTempDir


def _fake_sec_json(url: str, *, user_agent: str, timeout: int = 30) -> dict:
    if url == sec_source.SEC_TICKERS_URL:
        return {
            "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
            "1": {"ticker": "COP", "cik_str": 1163165, "title": "ConocoPhillips"},
        }
    if "CIK0000320193" in url:
        return {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-23-000010", "0000320193-26-000010", "0000320193-26-000011"],
                    "filingDate": ["2023-01-29", "2026-01-29", "2026-02-01"],
                    "acceptanceDateTime": [
                        "2023-01-29T21:30:00.000Z",
                        "2026-01-29T21:30:00.000Z",
                        "2026-02-01T12:00:00.000Z",
                    ],
                    "form": ["8-K", "8-K", "8-K"],
                    "items": ["2.02", "2.02,9.01", "5.02"],
                    "primaryDocument": ["aapl-20230129.htm", "aapl-20260129.htm", "aapl-other.htm"],
                }
            },
        }
    if "CIK0001163165" in url:
        return {
            "name": "ConocoPhillips",
            "filings": {
                "recent": {
                    "accessionNumber": ["0001163165-26-000020"],
                    "filingDate": ["2026-02-05"],
                    "acceptanceDateTime": ["2026-02-05T12:15:00.000Z"],
                    "form": ["8-K"],
                    "items": ["2.02"],
                    "primaryDocument": ["cop-20260205.htm"],
                }
            },
        }
    raise AssertionError(f"unexpected URL {url}")


class RegularOptionsSecEarningsCalendarSourceTests(unittest.TestCase):
    def test_build_report_writes_staged_csv_from_sec_item_202_rows(self) -> None:
        with WorkspaceTempDir(prefix="sec-earnings-source") as tmp_dir:
            tmp = Path(tmp_dir)
            output_csv = tmp / "earnings.csv"
            with mock.patch.object(sec_source, "_request_json", side_effect=_fake_sec_json):
                report = sec_source.build_report(
                    symbols=["AAPL", "COP"],
                    output_csv=output_csv,
                    output_dir=tmp / "out",
                    docs_report=tmp / "doc.md",
                    sleep_seconds=0,
                    write_outputs=True,
                    generated_at_utc="2026-06-29T00:00:00Z",
                )

            self.assertEqual(report["status"], "sec_earnings_calendar_source_ready")
            self.assertEqual(report["source_row_count"], 2)
            self.assertEqual(report["source_rows_by_symbol"], {"AAPL": 1, "COP": 1})
            self.assertEqual(report["diagnostics"][0]["out_of_window_item_2_02_count"], 1)
            self.assertTrue(output_csv.exists())
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "doc.md").exists())
            with output_csv.open(encoding="utf8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["symbol"] for row in rows], ["AAPL", "COP"])
            self.assertEqual(rows[0]["source_name"], "sec_edgar_8k_item_2_02")
            self.assertIn("Archives/edgar/data", rows[0]["source_url_or_file_name"])
            self.assertEqual(rows[0]["source_calendar_coverage_start_date_et"], "2024-06-01")
            self.assertEqual(rows[0]["source_calendar_coverage_end_date_et"], "2026-07-15")
            self.assertFalse(report["historical_replay_performed"])
            self.assertFalse(report["quotes_imported"])
            self.assertFalse(report["evidence_stores_mutated"])


if __name__ == "__main__":
    unittest.main()
