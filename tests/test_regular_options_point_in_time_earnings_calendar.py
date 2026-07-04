from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_earnings_calendar as earnings
from workspace_tempdir import WorkspaceTempDir


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsPointInTimeEarningsCalendarTests(unittest.TestCase):
    def _rows(self, symbols: tuple[str, ...] = ("AAPL", "GOOGL")) -> list[dict]:
        rows: list[dict] = []
        for index, symbol in enumerate(symbols, start=1):
            rows.append(
                {
                    "symbol": symbol,
                    "earnings_date_et": f"2026-0{index}-15",
                    "earnings_time": "after_market",
                    "known_at_utc": "2025-12-01T00:00:00Z",
                    "source_name": "fixture_earnings",
                    "source_ref": f"fixture://earnings/{symbol}",
                    "source_retrieved_at_utc": "2025-12-01T00:00:00Z",
                    "revision_id": "fixture-revision-1",
                    "point_in_time_valid": True,
                    "source_family": earnings.SOURCE_FAMILY,
                    "source_row_hash": f"hash-{symbol}",
                    "source_calendar_coverage_start_date_et": "2026-01-01",
                    "source_calendar_coverage_end_date_et": "2026-03-31",
                }
            )
        return rows

    def test_complete_symbol_coverage_is_ready(self) -> None:
        with WorkspaceTempDir(prefix="earnings-calendar") as tmp_dir:
            source = Path(tmp_dir) / "source.jsonl"
            _write_jsonl(source, self._rows())
            report = earnings.build_report(
                source_rows_path=source,
                window_start="2026-01-01",
                window_end="2026-02-28",
                max_dte=15,
                required_equity_symbols=("AAPL", "GOOGL"),
                generated_at_utc="2026-06-29T00:00:00Z",
            )

        self.assertEqual(report["status"], "point_in_time_earnings_calendar_ready")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(set(report["covered_equity_symbols"]), {"AAPL", "GOOGL"})
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])

    def test_missing_source_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="earnings-calendar-missing") as tmp_dir:
            report = earnings.build_report(
                source_rows_path=Path(tmp_dir) / "missing.jsonl",
                window_start="2026-01-01",
                window_end="2026-02-28",
                required_equity_symbols=("AAPL",),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_earnings_calendar")
        self.assertIn("point_in_time_earnings_calendar_source_missing", report["blockers"])
        self.assertEqual(report["earnings_events"], [])

    def test_symbol_coverage_must_span_window_plus_max_dte(self) -> None:
        with WorkspaceTempDir(prefix="earnings-calendar-coverage") as tmp_dir:
            source = Path(tmp_dir) / "source.jsonl"
            rows = self._rows(("AAPL",))
            rows[0]["source_calendar_coverage_end_date_et"] = "2026-02-28"
            _write_jsonl(source, rows)
            report = earnings.build_report(
                source_rows_path=source,
                window_start="2026-01-01",
                window_end="2026-02-28",
                max_dte=15,
                required_equity_symbols=("AAPL",),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_earnings_calendar")
        self.assertIn("point_in_time_earnings_calendar_symbol_coverage_incomplete", report["blockers"])

    def test_leakage_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="earnings-calendar-leakage") as tmp_dir:
            source = Path(tmp_dir) / "source.jsonl"
            rows = self._rows(("AAPL",))
            rows[0]["actual_eps"] = 2.31
            _write_jsonl(source, rows)
            report = earnings.build_report(
                source_rows_path=source,
                window_start="2026-01-01",
                window_end="2026-02-28",
                required_equity_symbols=("AAPL",),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_earnings_calendar")
        self.assertIn("point_in_time_earnings_calendar_row_validation_failed", report["blockers"])
        self.assertEqual(report["leakage_reject_count"], 1)


if __name__ == "__main__":
    unittest.main()
