from __future__ import annotations

import json
import hashlib
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import import_regular_options_underlying_daily_history as underlying_import
from scripts import build_regular_options_point_in_time_market_regime_inputs as regime
from workspace_tempdir import WorkspaceTempDir


UNIVERSE = "SPY,QQQ,IWM,DIA,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _feature_store(path: Path, dates: list[str]) -> None:
    _write_json(
        path,
        {
            "report_id": "regular_options_feature_store",
            "status": "feature_store_built",
            "shared_quote_dates": dates,
            "summary": {"overall_status": "feature_store_built", "shared_quote_date_count": len(dates)},
        },
    )


def _market_db(
    path: Path,
    *,
    direction: str = "up",
    omit_symbols: set[str] | None = None,
    day_count: int = 90,
    fetched_at_mode: str = "point_in_time",
    include_invalid_rows: bool = False,
) -> None:
    omit_symbols = omit_symbols or set()
    conn = sqlite3.connect(path)
    conn.execute(
        """
        create table daily_history (
            symbol text not null,
            bar_date text not null,
            open real,
            high real,
            low real,
            close real,
            adj_close real,
            volume real,
            fetched_at text,
            source text,
            adjustment_mode text,
            primary key (symbol, bar_date, source, adjustment_mode)
        )
        """
    )
    symbols = [item.strip() for item in UNIVERSE.split(",")]
    days = _weekdays(date(2025, 1, 2), day_count)
    for symbol_index, symbol in enumerate(symbols):
        if symbol in omit_symbols:
            continue
        for day_index, day in enumerate(days):
            if direction == "down":
                close = 200.0 + symbol_index - (day_index * 0.5)
            elif symbol_index < 8:
                close = 100.0 + symbol_index + day_index
            else:
                close = 100.0 + symbol_index - (day_index * 0.2)
            fetched_at = "2026-06-04T00:00:00Z" if fetched_at_mode == "late" else f"{day.isoformat()}T22:00:00Z"
            conn.execute(
                """
                insert into daily_history (
                    symbol, bar_date, open, high, low, close, adj_close,
                    volume, fetched_at, source, adjustment_mode
                )
                values (?, ?, ?, ?, ?, ?, null, 1000, ?, 'alpaca_sip', 'adjusted')
                """,
                (symbol, day.isoformat(), close, close + 1.0, close - 1.0, close, fetched_at),
            )
    if include_invalid_rows:
        conn.execute(
            """
            insert or replace into daily_history (
                symbol, bar_date, open, high, low, close, adj_close,
                volume, fetched_at, source, adjustment_mode
            )
            values ('SPY', '2025-04-08', 1, 1, 1, -1, null, 1000, '2025-04-08T22:00:00Z', 'alpaca_sip', 'adjusted')
            """
        )
        conn.execute(
            """
            insert or replace into daily_history (
                symbol, bar_date, open, high, low, close, adj_close,
                volume, fetched_at, source, adjustment_mode
            )
            values ('QQQ', '2025-04-08', 1, 1, 1, 1, null, 1000, 'not-a-timestamp', 'alpaca_sip', 'adjusted')
            """
        )
    conn.commit()
    conn.close()


def _write_source_rows(
    path: Path,
    *,
    dates: list[str],
    symbols: list[str],
    source_family: str = regime.UNDERLYING_SOURCE_FAMILY,
    marker: str = "source_vendor",
    coverage_symbols: set[str] | None = None,
    proof_eligible: bool = False,
) -> None:
    coverage_symbols = coverage_symbols or set(symbols)
    source_file_hash = hashlib.sha256(f"{marker}:source-file".encode("utf8")).hexdigest()
    rows: list[dict[str, object]] = []
    for date_index, input_date in enumerate(dates):
        prior = date.fromisoformat(input_date) - timedelta(days=1)
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)
        for symbol_index, symbol in enumerate(symbols):
            if symbol not in coverage_symbols:
                continue
            close = 100.0 + symbol_index + date_index
            source_row_hash = hashlib.sha256(f"{marker}:{symbol}:{input_date}".encode("utf8")).hexdigest()
            rows.append(
                {
                    "input_date_et": input_date,
                    "symbol": symbol,
                    "prior_bar_date_et": prior.isoformat(),
                    "close": close,
                    "known_at_utc": f"{prior.isoformat()}T21:30:00Z",
                    "source_timestamp_utc": f"{prior.isoformat()}T21:05:00Z",
                    "source_ref": f"{marker}:{symbol}:{prior.isoformat()}",
                    "source_file_hash": source_file_hash,
                    "source_row_hash": source_row_hash,
                    "source_family": source_family,
                    "source": marker,
                    "vendor": marker,
                    "point_in_time_valid": True,
                    "proof_eligible": proof_eligible,
                    "prior_20_trading_day_return_pct": 2.0,
                    "prior_50_trading_day_sma": close - 1.0,
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _underlying_daily_csv(symbols: list[str], start: date, end: date) -> str:
    lines = [
        "symbol,bar_date,open,high,low,close,adjusted_close,volume,fetched_at_utc,adjustment_mode,corporate_action_basis,vendor,source_event_date,known_at_utc,published_at_utc,source_file_hash,provenance_id,source_quality",
    ]
    for day_index, day in enumerate(_weekdays(start, (end - start).days + 1)):
        if day > end:
            break
        for symbol_index, symbol in enumerate(symbols):
            close = 100.0 + symbol_index + (day_index * 0.5)
            lines.append(
                f"{symbol},{day.isoformat()},{close - 1},{close + 1},{close - 2},{close},{close},1000000,{day.isoformat()}T21:20:00Z,split_and_dividend_adjusted,vendor_adjusted_total_return_basis,trusted_vendor,{day.isoformat()},{day.isoformat()}T21:15:00Z,{day.isoformat()}T21:05:00Z,,trusted_vendor:{symbol}:{day.isoformat()},trusted"
            )
    return "\n".join(lines) + "\n"


class RegularOptionsPointInTimeMarketRegimeInputsTests(unittest.TestCase):
    def test_ready_fixture_materializes_prior_day_confirmations(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 5)]
            _market_db(db)
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertEqual(report["coverage"]["date_coverage_pct"], 100.0)
        self.assertEqual(len(report["input_rows"]), 5)
        row = report["input_rows"][0]
        self.assertTrue(row["spy_momentum_confirmed"])
        self.assertTrue(row["qqq_momentum_confirmed"])
        self.assertTrue(row["breadth_confirmed"])
        self.assertEqual(row["available_symbol_count"], 13)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["point_in_time_market_regime_inputs_available"])
        self.assertEqual(report["source_time_policy"]["source_time_mode"], "historical_prior_bar_reconstruction")
        self.assertIn("missing_or_invalid_verified_underlying_source_rows", report["blockers"])
        self.assertTrue(all(item["proof_eligible"] is False for item in row["symbol_features"]))

    def test_valid_underlying_source_rows_are_preferred_and_mark_research_inputs_proof_eligible(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-source-rows") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            source_rows = tmp / "explicit_fixture_source_rows.jsonl"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 5)]
            _market_db(db, fetched_at_mode="late")
            _feature_store(feature, requested)
            _write_source_rows(source_rows, dates=requested, symbols=UNIVERSE.split(","))
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=source_rows,
                underlying_source_import_report_path=None,
                start_date="2025-04-01",
                end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "point_in_time_market_regime_inputs_ready")
        self.assertTrue(report["point_in_time_market_regime_inputs_available"])
        self.assertEqual(report["source_inventory"]["source_mode"], "point_in_time_verified_daily_history_source_rows")
        self.assertEqual(report["source_inventory"]["market_data_db"]["status"], "not_used_source_rows_preferred")
        self.assertTrue(report["input_rows"][0]["proof_eligible"])
        self.assertTrue(all(item["proof_eligible"] is True for item in report["input_rows"][0]["symbol_features"]))
        self.assertIn("explicit_fixture_source_rows.jsonl", report["input_rows"][0]["spy_feature"]["source_ref"])
        self.assertFalse(report["accepted_profitability"])

    def test_importer_output_clears_market_regime_without_synthetic_metrics(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-importer-integration") as tmp_dir:
            tmp = Path(tmp_dir)
            symbols = UNIVERSE.split(",")
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 5)]
            source_file = tmp / "trusted_underlying.csv"
            source_rows = tmp / "source_rows.jsonl"
            feature = tmp / "feature.json"
            import_report_path = tmp / "import_report.json"
            source_file.write_text(_underlying_daily_csv(symbols, date(2025, 1, 2), date(2025, 4, 7)), encoding="utf8")
            _feature_store(feature, requested)

            import_report = underlying_import.build_report(
                source_file=source_file,
                target_start_date="2025-04-01",
                target_end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
                approval_token=underlying_import.APPROVAL_TOKEN,
                no_replay=True,
                source_rows_path=source_rows,
                feature_store_path=feature,
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            _write_json(import_report_path, import_report)
            report = regime.build_report(
                market_data_db_path=tmp / "missing_market_data.db",
                feature_store_path=feature,
                underlying_source_rows_path=source_rows,
                underlying_source_import_report_path=import_report_path,
                start_date="2025-04-01",
                end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(import_report["status"], "underlying_daily_history_source_import_materialized")
        self.assertEqual(report["status"], "point_in_time_market_regime_inputs_ready")
        self.assertEqual(report["source_inventory"]["source_mode"], "point_in_time_verified_daily_history_source_rows")
        self.assertTrue(report["source_inventory"]["underlying_source_rows"]["source_import_report_binding"]["bound"])
        self.assertEqual(report["source_inventory"]["market_data_db"]["status"], "not_used_source_rows_preferred")
        self.assertGreater(report["input_rows"][0]["spy_feature"]["prior_20_trading_day_return_pct"], 0)

    def test_false_confirmations_are_valid_fail_closed_inputs_not_missing_rows(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 3)]
            _market_db(db, direction="down")
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-03",
                as_of_date="2025-04-03",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertFalse(report["input_rows"][0]["spy_momentum_confirmed"])
        self.assertFalse(report["input_rows"][0]["qqq_momentum_confirmed"])
        self.assertFalse(report["input_rows"][0]["breadth_confirmed"])
        self.assertEqual(report["row_blocker_counts"], {})
        self.assertIn("market_regime_inputs_using_historical_reconstruction", report["blockers"])

    def test_missing_market_data_db_fails_closed_without_inventing_rows(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            feature = tmp / "feature.json"
            _feature_store(feature, [day.isoformat() for day in _weekdays(date(2025, 4, 1), 3)])
            report = regime.build_report(
                market_data_db_path=tmp / "missing.db",
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-03",
                as_of_date="2025-04-03",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertIn("missing_or_unreadable_market_data_db", report["blockers"])
        self.assertIn("insufficient_date_coverage", report["blockers"])

    def test_default_fixture_source_rows_are_rejected_and_do_not_clear_fallback(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-default-fixture") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            source_rows = tmp / "source_rows.jsonl"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 2)]
            _market_db(db)
            _feature_store(feature, requested)
            _write_source_rows(source_rows, dates=requested, symbols=UNIVERSE.split(","), marker="fixture_vendor")
            original_default = regime.DEFAULT_UNDERLYING_SOURCE_ROWS
            regime.DEFAULT_UNDERLYING_SOURCE_ROWS = source_rows
            try:
                report = regime.build_report(
                    market_data_db_path=db,
                    feature_store_path=feature,
                    underlying_source_rows_path=source_rows,
                    underlying_source_import_report_path=None,
                    start_date="2025-04-01",
                    end_date="2025-04-02",
                    as_of_date="2025-04-02",
                    universe=UNIVERSE,
                )
            finally:
                regime.DEFAULT_UNDERLYING_SOURCE_ROWS = original_default

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertIn(
            "default_source_rows_fixture_or_sample_contamination",
            report["source_inventory"]["underlying_source_rows"]["reject_counts"],
        )
        self.assertEqual(report["source_inventory"]["source_mode"], "historical_prior_bar_reconstruction")

    def test_source_rows_wrong_source_family_and_proof_eligible_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-source-family") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            source_rows = tmp / "source_rows.jsonl"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 2)]
            _market_db(db)
            _feature_store(feature, requested)
            _write_source_rows(
                source_rows,
                dates=requested,
                symbols=UNIVERSE.split(","),
                source_family="wrong_family",
                proof_eligible=True,
            )
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=source_rows,
                underlying_source_import_report_path=None,
                start_date="2025-04-01",
                end_date="2025-04-02",
                as_of_date="2025-04-02",
                universe=UNIVERSE,
            )

        rejects = report["source_inventory"]["underlying_source_rows"]["reject_counts"]
        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertIn("source_family_mismatch", rejects)
        self.assertIn("source_rows_proof_eligible_true", rejects)

    def test_source_rows_invalid_hashes_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-source-hashes") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            source_rows = tmp / "source_rows.jsonl"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 2)]
            _market_db(db)
            _feature_store(feature, requested)
            _write_source_rows(source_rows, dates=requested, symbols=UNIVERSE.split(","))
            rows = [json.loads(line) for line in source_rows.read_text(encoding="utf8").splitlines()]
            rows[0]["source_file_hash"] = "not-a-sha256"
            rows[1]["source_row_hash"] = "also-not-a-sha256"
            source_rows.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=source_rows,
                underlying_source_import_report_path=None,
                start_date="2025-04-01",
                end_date="2025-04-02",
                as_of_date="2025-04-02",
                universe=UNIVERSE,
            )

        rejects = report["source_inventory"]["underlying_source_rows"]["reject_counts"]
        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertIn("invalid_source_file_hash", rejects)
        self.assertIn("invalid_source_row_hash", rejects)

    def test_source_rows_insufficient_coverage_falls_back_with_explicit_blocker(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-source-coverage") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            source_rows = tmp / "source_rows.jsonl"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 5)]
            _market_db(db)
            _feature_store(feature, requested)
            _write_source_rows(source_rows, dates=requested, symbols=UNIVERSE.split(","), coverage_symbols={"SPY", "QQQ"})
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=source_rows,
                underlying_source_import_report_path=None,
                start_date="2025-04-01",
                end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertFalse(report["source_inventory"]["underlying_source_rows"]["coverage_ready"])
        self.assertEqual(report["source_inventory"]["underlying_source_rows"]["per_symbol_coverage"]["IWM"]["coverage_pct"], 0.0)
        self.assertIn("missing_or_invalid_verified_underlying_source_rows", report["blockers"])

    def test_missing_spy_history_trips_coverage_floor(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 5)]
            _market_db(db, omit_symbols={"SPY"})
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-07",
                as_of_date="2025-04-07",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertIn("missing_key_market_data_daily_history_symbols", report["blockers"])
        self.assertIn("point_in_time_market_regime_row_validation_failed", report["blockers"])
        self.assertEqual(report["row_blocker_counts"]["missing_spy_momentum_inputs"], 5)
        self.assertEqual(report["coverage"]["covered_date_count"], 0)

    def test_late_fetched_at_downgrades_to_historical_reconstruction(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 3)]
            _market_db(db, fetched_at_mode="late")
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-03",
                as_of_date="2025-04-03",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertFalse(report["point_in_time_market_regime_inputs_available"])
        self.assertEqual(report["source_time_policy"]["source_time_mode"], "historical_prior_bar_reconstruction")
        self.assertEqual(report["row_blocker_counts"]["market_regime_source_time_not_point_in_time"], 3)
        self.assertTrue(report["input_rows"][0]["historical_prior_bar_reconstruction"])

    def test_same_day_and_future_bars_are_excluded_from_prior_feature(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = ["2025-04-01"]
            _market_db(db)
            conn = sqlite3.connect(db)
            conn.execute(
                """
                update daily_history
                set close = 9999, fetched_at = '2025-03-31T22:00:00Z'
                where symbol = 'SPY' and bar_date = '2025-04-01'
                """
            )
            conn.commit()
            conn.close()
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-01",
                as_of_date="2025-04-01",
                universe=UNIVERSE,
            )

        row = report["input_rows"][0]
        self.assertLess(row["spy_feature"]["prior_bar_date_et"], "2025-04-01")
        self.assertNotEqual(row["spy_feature"]["prior_close"], 9999)

    def test_insufficient_lookback_blocks_rows(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 1, 15), 2)]
            _market_db(db, day_count=15)
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-01-15",
                end_date="2025-01-16",
                as_of_date="2025-01-16",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertEqual(report["row_blocker_counts"]["missing_spy_momentum_inputs"], 2)
        self.assertEqual(report["row_blocker_counts"]["missing_qqq_momentum_inputs"], 2)
        self.assertEqual(report["row_blocker_counts"]["insufficient_breadth_symbol_coverage"], 2)

    def test_invalid_daily_history_rows_are_rejected_explicitly(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = ["2025-04-09"]
            _market_db(db, include_invalid_rows=True)
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-09",
                end_date="2025-04-09",
                as_of_date="2025-04-09",
                universe=UNIVERSE,
            )

        rejects = report["source_inventory"]["market_data_db"]["rejected_row_counts"]
        self.assertEqual(rejects["invalid_close"], 1)
        self.assertEqual(rejects["invalid_fetched_at"], 1)

    def test_missing_non_key_symbol_is_policy_reported_but_not_global_blocker(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            requested = [day.isoformat() for day in _weekdays(date(2025, 4, 1), 2)]
            _market_db(db, omit_symbols={"NEM"})
            _feature_store(feature, requested)
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                start_date="2025-04-01",
                end_date="2025-04-02",
                as_of_date="2025-04-02",
                universe=UNIVERSE,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_market_regime_inputs")
        self.assertNotIn("missing_key_market_data_daily_history_symbols", report["blockers"])
        self.assertEqual(report["source_inventory"]["missing_non_key_symbols"], ["NEM"])
        self.assertEqual(report["input_rows"][0]["available_symbol_count"], 12)

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="market-regime-inputs") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "market_data.db"
            feature = tmp / "feature.json"
            _market_db(db)
            _feature_store(feature, [day.isoformat() for day in _weekdays(date(2025, 4, 1), 2)])
            report = regime.build_report(
                market_data_db_path=db,
                feature_store_path=feature,
                underlying_source_rows_path=tmp / "missing_source_rows.jsonl",
                start_date="2025-04-01",
                end_date="2025-04-02",
                as_of_date="2025-04-02",
                universe=UNIVERSE,
            )
            artifacts = regime.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
