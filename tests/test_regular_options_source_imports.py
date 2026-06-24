from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import import_regular_options_direct_vix_source as vix_import
from scripts import import_regular_options_flow_extreme_volume_oi as flow_import
from scripts import import_regular_options_macro_event_calendar as macro_import
from scripts import import_regular_options_underlying_daily_history as underlying_import
from workspace_tempdir import WorkspaceTempDir


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _feature_store(path: Path, dates: list[str], symbols: list[str] | None = None) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_feature_store",
            "status": "feature_store_built",
            "summary": {
                "overall_status": "feature_store_built",
                "first_shared_quote_date_et": dates[0],
                "latest_shared_quote_date_et": dates[-1],
                "shared_quote_date_count": len(dates),
            },
            "shared_quote_dates": dates,
            "inputs": {"symbols": symbols or []},
            "symbol_surface_rows": [{"symbol": symbol} for symbol in (symbols or [])],
        },
    )
    return path


def _weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _underlying_daily_csv(symbols: list[str], start: date, end: date, *, vendor: str = "trusted_vendor") -> str:
    lines = [
        "symbol,bar_date,open,high,low,close,adjusted_close,volume,fetched_at_utc,adjustment_mode,corporate_action_basis,vendor,source_event_date,known_at_utc,published_at_utc,source_file_hash,provenance_id,source_quality",
    ]
    for day_index, day in enumerate(_weekdays(start, end)):
        for symbol_index, symbol in enumerate(symbols):
            close = 100.0 + symbol_index + (day_index * 0.5)
            lines.append(
                f"{symbol},{day.isoformat()},{close - 1},{close + 1},{close - 2},{close},{close},1000000,{day.isoformat()}T21:20:00Z,split_and_dividend_adjusted,vendor_adjusted_total_return_basis,{vendor},{day.isoformat()},{day.isoformat()}T21:15:00Z,{day.isoformat()}T21:05:00Z,,{vendor}:{symbol}:{day.isoformat()},trusted"
            )
    return "\n".join(lines) + "\n"


class RegularOptionsSourceImportTests(unittest.TestCase):
    def test_direct_vix_import_materializes_rows_and_clears_bucket_validator(self) -> None:
        with WorkspaceTempDir(prefix="source-import-vix") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = tmp / "VIX_History.csv"
            _write_text(
                source_file,
                "\n".join(
                    [
                        "DATE,OPEN,HIGH,LOW,CLOSE",
                        "01/02/2026,14,15,13,14.2",
                        "01/05/2026,20,21,19,20.0",
                    ]
                )
                + "\n",
            )
            report = vix_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-01",
                target_end_date="2026-01-31",
                as_of_date="2026-01-31",
                approval_token=vix_import.APPROVAL_TOKEN,
                no_replay=True,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06"]),
                source_rows_path=tmp / "source_rows.jsonl",
                threshold_policy_path=tmp / "policy.json",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "direct_vix_source_import_materialized")
        self.assertTrue(report["source_rows_written"])
        self.assertEqual(report["source_row_count"], 2)
        self.assertEqual(report["downstream_vix_bucket_status"], "point_in_time_vix_bucket_ready")
        self.assertEqual(report["downstream_vix_coverage_pct"], 100.0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])

    def test_direct_vix_import_requires_token(self) -> None:
        with WorkspaceTempDir(prefix="source-import-vix-token") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = tmp / "VIX_History.csv"
            _write_text(source_file, "DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,14,15,13,14.2\n")
            report = vix_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-01",
                target_end_date="2026-01-31",
                as_of_date="2026-01-31",
                approval_token="",
                no_replay=True,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05"]),
                source_rows_path=tmp / "source_rows.jsonl",
                threshold_policy_path=tmp / "policy.json",
            )

        self.assertEqual(report["status"], "blocked_direct_vix_source_import")
        self.assertIn("missing_or_invalid_approval_token", report["blockers"])
        self.assertFalse((tmp / "source_rows.jsonl").exists())

    def test_macro_event_import_materializes_calendar_rows(self) -> None:
        with WorkspaceTempDir(prefix="source-import-macro") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = [
                ("cpi-1", "cpi", "2026-01-13T08:30:00"),
                ("minutes-1", "fomc_minutes", "2026-01-14T14:00:00"),
                ("rate-1", "fomc_rate_decision", "2026-01-28T14:00:00"),
                ("nfp-1", "nonfarm_payrolls", "2026-02-06T08:30:00"),
                ("pce-1", "pce", "2026-02-27T08:30:00"),
                ("chair-1", "scheduled_fed_chair_testimony", "2026-03-03T10:00:00"),
            ]
            lines = [
                "event_id,event_category,scheduled_event_datetime_et,event_window_type,source_name,source_url_or_file_name,source_published_at_utc,known_at_utc,revision_status"
            ]
            for event_id, category, event_dt in rows:
                lines.append(
                    f"{event_id},{category},{event_dt} America/New_York,,fixture_macro,fixture://macro/{event_id},2025-12-01T00:00:00Z,2025-12-01T00:00:00Z,scheduled"
                )
            source_file = tmp / "macro.csv"
            _write_text(source_file, "\n".join(lines) + "\n")
            report = macro_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-01",
                target_end_date="2026-03-31",
                as_of_date="2026-03-31",
                approval_token=macro_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=tmp / "source_rows.jsonl",
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-02"]),
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "macro_event_calendar_source_import_materialized")
        self.assertEqual(report["source_row_count"], 6)
        self.assertEqual(report["downstream_macro_event_calendar_status"], "macro_event_calendar_ready_for_readiness_recheck")
        self.assertEqual(set(report["covered_categories"]), set(macro_import.source_packet.REQUIRED_CATEGORIES))

    def test_flow_import_materializes_point_in_time_input_rows(self) -> None:
        with WorkspaceTempDir(prefix="source-import-flow") as tmp_dir:
            tmp = Path(tmp_dir)
            lines = [
                "source_date,underlying,total_option_volume,call_volume,put_volume,total_open_interest,call_open_interest,put_open_interest,source_name,source_url_or_file_name,known_at_utc,data_trust,revision_status",
            ]
            for day in ("2026-01-02", "2026-01-05", "2026-01-06"):
                for symbol in ("SPY", "QQQ"):
                    lines.append(
                        f"{day},{symbol},1000,450,550,10000,4800,5200,fixture_flow,fixture://flow/{day}/{symbol},{day}T22:00:00Z,trusted,final"
                    )
            source_file = tmp / "flow.csv"
            _write_text(source_file, "\n".join(lines) + "\n")
            report = flow_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-01",
                target_end_date="2026-01-31",
                as_of_date="2026-01-31",
                underlyings="SPY,QQQ",
                approval_token=flow_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=tmp / "source_rows.jsonl",
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06", "2026-01-07"], ["SPY", "QQQ"]),
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "flow_extreme_volume_oi_source_import_materialized")
        self.assertEqual(report["source_row_count"], 6)
        self.assertEqual(report["downstream_flow_extreme_input_status"], "point_in_time_flow_extreme_input_available")
        self.assertEqual(report["date_coverage_pct"], 100.0)

    def test_underlying_daily_import_materializes_prior_bar_rows(self) -> None:
        with WorkspaceTempDir(prefix="source-import-underlying") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = tmp / "underlying.csv"
            source_rows = tmp / "source_rows.jsonl"
            _write_text(source_file, _underlying_daily_csv(["SPY", "QQQ"], date(2025, 10, 1), date(2026, 1, 7)))
            report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-05",
                target_end_date="2026-01-07",
                as_of_date="2026-01-31",
                universe="SPY,QQQ",
                approval_token=underlying_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=source_rows,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06", "2026-01-07"], ["SPY", "QQQ"]),
                generated_at_utc="2026-06-24T00:00:00Z",
            )

            materialized = [json.loads(line) for line in source_rows.read_text(encoding="utf8").splitlines()]

        self.assertEqual(report["status"], "underlying_daily_history_source_import_materialized")
        self.assertTrue(report["approval_token_valid"])
        self.assertTrue(report["source_family_binding"]["matched"])
        self.assertTrue(report["source_rows_written"])
        self.assertEqual(report["source_row_count"], 6)
        self.assertEqual(report["requested_market_date_count"], 3)
        self.assertEqual(report["parser_validation"]["min_date_coverage_pct"], 100.0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["evidence_stores_mutated"])
        first_spy = next(row for row in materialized if row["input_date_et"] == "2026-01-05" and row["symbol"] == "SPY")
        self.assertEqual(first_spy["prior_bar_date_et"], "2026-01-02")
        self.assertIn("prior_20_trading_day_return_pct", first_spy)
        self.assertIn("prior_50_trading_day_sma", first_spy)
        self.assertGreaterEqual(first_spy["rolling_metric_prior_row_count"], 50)
        self.assertTrue(first_spy["point_in_time_valid"])
        self.assertFalse(first_spy["proof_eligible"])
        self.assertEqual(first_spy["source_family"], underlying_import.SOURCE_FAMILY)

    def test_underlying_daily_import_blocks_insufficient_lookback_before_writing_source_rows(self) -> None:
        with WorkspaceTempDir(prefix="source-import-underlying-lookback") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = tmp / "underlying.csv"
            source_rows = tmp / "source_rows.jsonl"
            _write_text(source_file, _underlying_daily_csv(["SPY"], date(2026, 1, 2), date(2026, 1, 6)))
            report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-05",
                target_end_date="2026-01-06",
                as_of_date="2026-01-31",
                universe="SPY",
                approval_token=underlying_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=source_rows,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06"], ["SPY"]),
            )

        self.assertEqual(report["status"], "blocked_underlying_daily_history_source_import")
        self.assertIn("underlying_source_row_materialization_rejected_dates", report["blockers"])
        self.assertEqual(report["rejected_rows"][0]["reason"], "insufficient_prior_50_trading_day_lookback")
        self.assertFalse(source_rows.exists())

    def test_underlying_daily_import_blocks_tests_fixtures_from_default_source_rows_path(self) -> None:
        with WorkspaceTempDir(prefix="source-import-underlying-fixture-default") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = underlying_import.ROOT / "tests" / "fixtures" / "underlying_daily" / "point_in_time_underlying_daily_sample.csv"
            report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-05",
                target_end_date="2026-01-07",
                as_of_date="2026-01-31",
                universe="SPY,QQQ",
                approval_token=underlying_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=underlying_import.DEFAULT_SOURCE_ROWS,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06", "2026-01-07"], ["SPY", "QQQ"]),
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_underlying_daily_history_source_import")
        self.assertIn("fixture_source_file_requires_non_default_source_rows_path", report["blockers"])
        self.assertFalse(report["source_rows_written"])
        self.assertTrue(report["source_file_under_tests_fixtures"])
        self.assertTrue(report["source_rows_path_is_default"])

    def test_underlying_daily_import_still_requires_lookback_for_explicit_fixture_source_rows_path(self) -> None:
        with WorkspaceTempDir(prefix="source-import-underlying-fixture-explicit") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = underlying_import.ROOT / "tests" / "fixtures" / "underlying_daily" / "point_in_time_underlying_daily_sample.csv"
            source_rows = tmp / "fixture_source_rows.jsonl"
            report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-05",
                target_end_date="2026-01-07",
                as_of_date="2026-01-31",
                universe="SPY,QQQ",
                approval_token=underlying_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=source_rows,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05", "2026-01-06", "2026-01-07"], ["SPY", "QQQ"]),
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            source_rows_exists = source_rows.exists()

        self.assertEqual(report["status"], "blocked_underlying_daily_history_source_import")
        self.assertIn("underlying_source_row_materialization_rejected_dates", report["blockers"])
        self.assertFalse(report["source_rows_written"])
        self.assertFalse(report["source_rows_path_is_default"])
        self.assertFalse(source_rows_exists)

    def test_underlying_daily_import_requires_token_and_does_not_write_source_rows(self) -> None:
        with WorkspaceTempDir(prefix="source-import-underlying-token") as tmp_dir:
            tmp = Path(tmp_dir)
            source_file = tmp / "underlying.csv"
            source_rows = tmp / "source_rows.jsonl"
            _write_text(
                source_file,
                "\n".join(
                    [
                        "symbol,bar_date,open,high,low,close,adjusted_close,volume,fetched_at_utc,adjustment_mode,corporate_action_basis,vendor,source_event_date,known_at_utc,published_at_utc,source_file_hash,provenance_id,source_quality",
                        "SPY,2026-01-02,469,471,468,470,470,1000000,2026-01-02T21:20:00Z,split_and_dividend_adjusted,vendor_adjusted_total_return_basis,fixture_vendor,2026-01-02,2026-01-02T21:15:00Z,2026-01-02T21:05:00Z,fixture_file_hash,fixture:SPY:2026-01-02,trusted",
                    ]
                )
                + "\n",
            )
            report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2026-01-05",
                target_end_date="2026-01-05",
                as_of_date="2026-01-31",
                universe="SPY",
                approval_token="",
                no_replay=True,
                source_rows_path=source_rows,
                feature_store_path=_feature_store(tmp / "feature-store.json", ["2026-01-05"], ["SPY"]),
            )

        self.assertEqual(report["status"], "blocked_underlying_daily_history_source_import")
        self.assertIn("missing_or_invalid_approval_token", report["blockers"])
        self.assertFalse(report["source_rows_written"])
        self.assertFalse(source_rows.exists())


if __name__ == "__main__":
    unittest.main()
