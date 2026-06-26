from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_underlying_daily_source_acquisition_packet as acquisition
from workspace_tempdir import WorkspaceTempDir


HEADER_FIELDS = (
    "symbol",
    "bar_date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "fetched_at_utc",
    "adjustment_mode",
    "corporate_action_basis",
    "vendor",
    "source_event_date",
    "known_at_utc",
    "published_at_utc",
    "source_file_hash",
    "provenance_id",
    "source_quality",
)
HEADER = ",".join(HEADER_FIELDS)


def _write_feature_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"shared_quote_dates": ["2026-01-05", "2026-01-06"]}, indent=2) + "\n",
        encoding="utf8",
    )


def _row(
    symbol: str,
    bar_date: str,
    *,
    known_at: str,
    fetched_at: str | None = None,
    vendor: str = "Trusted Daily Vendor",
    provenance_id: str | None = None,
    source_quality: str = "trusted",
) -> str:
    if fetched_at is None:
        fetched_at = known_at.replace("21:15:00Z", "21:20:00Z")
    values = {
        "symbol": symbol,
        "bar_date": bar_date,
        "open": "100.00",
        "high": "102.00",
        "low": "99.00",
        "close": "101.00",
        "adjusted_close": "101.00",
        "volume": "1000000",
        "fetched_at_utc": fetched_at,
        "adjustment_mode": "split_and_dividend_adjusted",
        "corporate_action_basis": "vendor_adjusted_total_return_basis",
        "vendor": vendor,
        "source_event_date": bar_date,
        "known_at_utc": known_at,
        "published_at_utc": known_at.replace("21:15:00Z", "21:05:00Z"),
        "source_file_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "provenance_id": provenance_id or f"trusted:{symbol}:{bar_date}",
        "source_quality": source_quality,
    }
    return ",".join(values[field] for field in HEADER_FIELDS)


def _valid_csv(symbols: tuple[str, ...] = ("SPY", "QQQ")) -> str:
    rows = [HEADER]
    for symbol in symbols:
        rows.append(_row(symbol, "2026-01-02", known_at="2026-01-02T21:15:00Z"))
        rows.append(_row(symbol, "2026-01-05", known_at="2026-01-05T21:15:00Z"))
    return "\n".join(rows) + "\n"


class RegularOptionsUnderlyingDailySourceAcquisitionTests(unittest.TestCase):
    def _build(
        self,
        tmp: Path,
        *,
        source_file: Path | None = None,
        staging_dir: Path | None = None,
        symbols: tuple[str, ...] = ("SPY", "QQQ"),
    ) -> dict:
        feature_store = tmp / "feature-store.json"
        _write_feature_store(feature_store)
        return acquisition.build_report(
            staging_dir=staging_dir or (tmp / "staging"),
            source_file=source_file,
            feature_store=feature_store,
            output_dir=tmp / "out",
            docs_report=tmp / "doc.md",
            target_universe=symbols,
            target_start_date="2026-01-05",
            target_end_date="2026-01-06",
            as_of_date="2026-01-06",
            generated_at_utc="2026-06-25T00:00:00Z",
        )

    def test_empty_staging_fails_closed_without_writes(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            report = self._build(Path(tmp_dir))

        self.assertEqual(report["status"], "blocked_underlying_daily_source_acquisition_missing")
        self.assertEqual(report["blockers"], ["trusted_source_csv_missing"])
        self.assertFalse(report["source_rows_written"])
        self.assertFalse(report["source_import_command_executed"])
        self.assertEqual(report["candidate_file_count"], 0)

    def test_valid_staged_source_is_ready_for_operator_import_approval(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            tmp = Path(tmp_dir)
            staging = tmp / "staging"
            staging.mkdir()
            source = staging / "point_in_time_underlying_daily_ohlcv_adjusted_v1.csv"
            source.write_text(_valid_csv(), encoding="utf8")
            report = self._build(tmp, staging_dir=staging)

        self.assertEqual(report["status"], "ready_for_underlying_daily_source_import_approval")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["ready_candidate_count"], 1)
        self.assertIn("APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT", report["future_import_command"])
        self.assertIn("options:source-import:underlying-daily-history", report["future_import_command"])
        self.assertFalse(report["source_rows_written"])

    def test_local_market_data_db_shortcut_is_refused(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "shortcut.csv"
            source.write_text(
                _valid_csv().replace("trusted:SPY:2026-01-02", "market_data.db:daily_history:SPY:2026-01-02"),
                encoding="utf8",
            )
            report = self._build(tmp, source_file=source)

        self.assertEqual(report["status"], "blocked_underlying_daily_source_acquisition_invalid")
        self.assertIn("local_market_data_db_or_reconstructed_source_not_allowed", report["blockers"])
        self.assertEqual(report["candidate_source_files"][0]["local_shortcut_reject_count"], 1)

    def test_late_known_at_rows_fail_coverage(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "late.csv"
            source.write_text(
                "\n".join(
                    [
                        HEADER,
                        _row("SPY", "2026-01-02", known_at="2026-06-04T21:15:00Z", fetched_at="2026-06-04T21:20:00Z"),
                        _row("SPY", "2026-01-05", known_at="2026-06-04T21:15:00Z", fetched_at="2026-06-04T21:20:00Z"),
                        _row("QQQ", "2026-01-02", known_at="2026-06-04T21:15:00Z", fetched_at="2026-06-04T21:20:00Z"),
                        _row("QQQ", "2026-01-05", known_at="2026-06-04T21:15:00Z", fetched_at="2026-06-04T21:20:00Z"),
                    ]
                )
                + "\n",
                encoding="utf8",
            )
            report = self._build(tmp, source_file=source)

        self.assertEqual(report["status"], "blocked_underlying_daily_source_acquisition_invalid")
        self.assertIn("source_csv_coverage_not_ready", report["blockers"])
        self.assertFalse(report["candidate_source_files"][0]["validation"]["coverage_ready"])

    def test_leakage_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "leak.csv"
            source.write_text(f"{HEADER},pnl\n{_row('SPY', '2026-01-02', known_at='2026-01-02T21:15:00Z')},10\n", encoding="utf8")
            report = self._build(tmp, source_file=source)

        self.assertEqual(report["status"], "blocked_underlying_daily_source_acquisition_invalid")
        self.assertIn("source_csv_parser_rejected", report["blockers"])

    def test_manual_or_synthetic_markers_are_invalid(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-acquisition") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "manual.csv"
            source.write_text(_valid_csv().replace("trusted", "manual_synthetic_source_mark_only", 1), encoding="utf8")
            report = self._build(tmp, source_file=source)

        self.assertEqual(report["status"], "blocked_underlying_daily_source_acquisition_invalid")
        self.assertIn("source_csv_validation_rejected_rows", report["blockers"])
        self.assertIn(
            "stale_manual_synthetic_or_source_mark_only_row",
            report["candidate_source_files"][0]["validation"]["reject_counts"],
        )


if __name__ == "__main__":
    unittest.main()
