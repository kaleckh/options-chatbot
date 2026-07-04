from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from historical_options_store import init_schema
from scripts import build_regular_options_historical_scanner_input_surface_tracker as tracker


SYMBOLS = tracker.ALLOWED_UNIVERSE
DATES = ("2026-01-05", "2026-01-06")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _feature(path: Path) -> Path:
    _write_json(path, {"report_id": "regular_options_feature_store", "status": "feature_store_built", "shared_quote_dates": list(DATES)})
    return path


def _market_regime(path: Path) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_point_in_time_market_regime_inputs",
            "status": "point_in_time_market_regime_inputs_ready",
            "point_in_time_market_regime_inputs_available": True,
            "blockers": [],
        },
    )
    return path


def _vix(path: Path) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_point_in_time_vix_bucket",
            "status": "point_in_time_vix_bucket_ready",
            "blockers": [],
        },
    )
    return path


def _daily_rows(path: Path) -> Path:
    rows = [
        {
            "input_date_et": day,
            "symbol": symbol,
            "point_in_time_valid": True,
            "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
        }
        for day in DATES
        for symbol in SYMBOLS
    ]
    _write_jsonl(path, rows)
    return path


def _minute_rows(path: Path, symbols: tuple[str, ...] = SYMBOLS) -> Path:
    rows = [
        {
            "price_date_et": day,
            "underlying": symbol,
            "price_minute_et": 610,
            "close": 100.0,
            "point_in_time_valid": True,
            "source_family": "alpaca_sip_underlying_minute_price_v1",
        }
        for day in DATES
        for symbol in symbols
    ]
    _write_jsonl(path, rows)
    return path


def _option_db(path: Path, *, omit_symbol: str | None = None) -> Path:
    init_schema(path)
    with sqlite3.connect(path) as conn:
        batch_id = conn.execute(
            """
            INSERT INTO import_batches (
                source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tracker.THETADATA_SOURCE_LABEL,
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "abc",
                "2026-06-04T00:00:00Z",
                1,
                1,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        for day in DATES:
            for symbol in SYMBOLS:
                if symbol == omit_symbol:
                    continue
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots (
                        as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                        contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                        underlying_price, volume, open_interest, source_batch_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{day}T15:10:00Z",
                        day,
                        tracker.ENTRY_QUOTE_MINUTE_ET,
                        "intraday",
                        symbol,
                        f"{symbol}260116C00100000",
                        "2026-01-16",
                        "call",
                        100.0,
                        1.0,
                        1.1,
                        None,
                        None,
                        None,
                        None,
                        None,
                        batch_id,
                    ),
                )
        conn.commit()
    return path


def _earnings_calendar(path: Path) -> Path:
    equities = [symbol for symbol in SYMBOLS if symbol not in tracker.ETF_OR_INDEX_SYMBOLS]
    _write_json(
        path,
        {
            "report_id": "regular_options_point_in_time_earnings_calendar",
            "status": "point_in_time_earnings_calendar_ready",
            "blockers": [],
            "requested_window": {
                "window_start": "2026-01-01",
                "window_end": "2026-01-31",
                "max_dte": 45,
                "coverage_end_required": "2026-03-17",
            },
            "covered_equity_symbols": equities,
            "missing_equity_symbols": [],
        },
    )
    return path


def _frozen_adapter(path: Path) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_historical_frozen_scanner_replay_adapter",
            "status": "historical_frozen_scanner_replay_adapter_ready",
            "blockers": [],
            "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
            "scanner_parity": False,
            "production_scanner_replay": False,
        },
    )
    return path


def _frozen_engine(path: Path) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_13_symbol_frozen_candidate_generation_engine",
            "status": "frozen_13_symbol_candidate_generation_engine_ready",
            "blockers": [],
            "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
            "scanner_parity": False,
            "production_scanner_replay": False,
        },
    )
    return path


class RegularOptionsHistoricalScannerInputSurfaceTrackerTests(unittest.TestCase):
    def test_paid_source_surfaces_clear_their_own_blockers_but_replay_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            report = tracker.build_report(
                feature_store_path=_feature(root / "feature.json"),
                market_regime_inputs_path=_market_regime(root / "regime.json"),
                vix_bucket_path=_vix(root / "vix.json"),
                underlying_daily_source_rows_path=_daily_rows(root / "daily.jsonl"),
                alpaca_minute_source_rows_path=_minute_rows(root / "minute.jsonl"),
                frozen_adapter_path=root / "missing-adapter.json",
                frozen_engine_path=root / "missing-engine.json",
                options_history_db_path=_option_db(root / "options.db"),
                window_start="2026-01-01",
                window_end="2026-01-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-29T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_scanner_input_surfaces")
        self.assertTrue(report["surface_readiness"]["underlying_daily_feature_source_rows"]["available"])
        self.assertTrue(report["surface_readiness"]["entry_underlying_price_surface"]["available"])
        self.assertTrue(report["surface_readiness"]["option_chain_selection_surface"]["available"])
        self.assertNotIn("missing_historical_entry_underlying_price_surface", report["blockers"])
        self.assertNotIn("missing_historical_option_chain_selection_surface", report["blockers"])
        self.assertIn("missing_point_in_time_earnings_calendar_source", report["blockers"])
        self.assertIn("missing_lane_specific_point_in_time_feature_inputs", report["blockers"])
        self.assertIn("missing_historical_candidate_decision_replay_execution", report["blockers"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["broker_order_allowed"])

    def test_partial_alpaca_minute_and_thetadata_coverage_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            report = tracker.build_report(
                feature_store_path=_feature(root / "feature.json"),
                market_regime_inputs_path=_market_regime(root / "regime.json"),
                vix_bucket_path=_vix(root / "vix.json"),
                underlying_daily_source_rows_path=_daily_rows(root / "daily.jsonl"),
                alpaca_minute_source_rows_path=_minute_rows(root / "minute.jsonl", symbols=("SPY", "QQQ", "IWM", "DIA")),
                frozen_adapter_path=root / "missing-adapter.json",
                frozen_engine_path=root / "missing-engine.json",
                options_history_db_path=_option_db(root / "options.db", omit_symbol="AAPL"),
                window_start="2026-01-01",
                window_end="2026-01-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-29T00:00:00Z",
            )

        entry = report["surface_readiness"]["entry_underlying_price_surface"]
        chain = report["surface_readiness"]["option_chain_selection_surface"]
        self.assertFalse(entry["available"])
        self.assertFalse(chain["available"])
        self.assertEqual(entry["covered_symbol_date_count"], len(DATES) * 4)
        self.assertEqual(chain["missing_by_symbol"], {"AAPL": len(DATES)})
        self.assertIn("missing_historical_entry_underlying_price_surface", report["blockers"])
        self.assertIn("missing_historical_option_chain_selection_surface", report["blockers"])

    def test_ready_earnings_calendar_clears_tracker_earnings_blocker_only(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            report = tracker.build_report(
                feature_store_path=_feature(root / "feature.json"),
                market_regime_inputs_path=_market_regime(root / "regime.json"),
                vix_bucket_path=_vix(root / "vix.json"),
                underlying_daily_source_rows_path=_daily_rows(root / "daily.jsonl"),
                alpaca_minute_source_rows_path=_minute_rows(root / "minute.jsonl"),
                earnings_calendar_path=_earnings_calendar(root / "earnings.json"),
                frozen_adapter_path=root / "missing-adapter.json",
                frozen_engine_path=root / "missing-engine.json",
                options_history_db_path=_option_db(root / "options.db"),
                window_start="2026-01-01",
                window_end="2026-01-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-29T00:00:00Z",
            )

        self.assertTrue(report["surface_readiness"]["earnings_calendar"]["available"])
        self.assertNotIn("missing_point_in_time_earnings_calendar_source", report["blockers"])
        self.assertIn("missing_lane_specific_point_in_time_feature_inputs", report["blockers"])
        self.assertIn("missing_historical_candidate_decision_replay_execution", report["blockers"])

    def test_ready_deterministic_materializer_clears_downstream_replay_blockers_without_scanner_parity(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            report = tracker.build_report(
                feature_store_path=_feature(root / "feature.json"),
                market_regime_inputs_path=_market_regime(root / "regime.json"),
                vix_bucket_path=_vix(root / "vix.json"),
                underlying_daily_source_rows_path=_daily_rows(root / "daily.jsonl"),
                alpaca_minute_source_rows_path=_minute_rows(root / "minute.jsonl"),
                earnings_calendar_path=_earnings_calendar(root / "earnings.json"),
                frozen_adapter_path=_frozen_adapter(root / "adapter.json"),
                frozen_engine_path=_frozen_engine(root / "engine.json"),
                options_history_db_path=_option_db(root / "options.db"),
                window_start="2026-01-01",
                window_end="2026-01-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-29T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_scanner_input_surfaces_ready")
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["surface_readiness"]["lane_specific_feature_inputs"]["available"])
        self.assertFalse(report["surface_readiness"]["lane_specific_feature_inputs"]["production_scanner_parity"])
        self.assertTrue(report["surface_readiness"]["candidate_decision_replay_execution"]["available"])
        self.assertEqual(
            report["surface_readiness"]["candidate_decision_replay_execution"]["candidate_materialization_basis"],
            "deterministic_local_pit_candidate_materializer_v1",
        )
        self.assertFalse(report["surface_readiness"]["candidate_decision_replay_execution"]["production_scanner_parity"])

    def test_write_outputs_creates_latest_json_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            report = tracker.build_report(
                feature_store_path=_feature(root / "feature.json"),
                market_regime_inputs_path=_market_regime(root / "regime.json"),
                vix_bucket_path=_vix(root / "vix.json"),
                underlying_daily_source_rows_path=_daily_rows(root / "daily.jsonl"),
                alpaca_minute_source_rows_path=_minute_rows(root / "minute.jsonl"),
                frozen_adapter_path=root / "missing-adapter.json",
                frozen_engine_path=root / "missing-engine.json",
                options_history_db_path=_option_db(root / "options.db"),
                window_start="2026-01-01",
                window_end="2026-01-31",
                generated_at_utc="2026-06-29T00:00:00Z",
            )
            artifacts = tracker.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["docs_report"].endswith("doc.md"))


if __name__ == "__main__":
    unittest.main()
