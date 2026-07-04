from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import options_chatbot as oc
from historical_options_store import init_schema
from scripts import build_regular_options_13_symbol_frozen_daily_candidate_decisions as decisions
from scripts import build_regular_options_historical_frozen_scanner_replay_adapter as adapter


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _cohort() -> dict:
    return {
        "contract_id": "forward-cohort-preregistration",
        "status": "active",
        "cohort": {"freeze_date": "2026-06-14", "eval_date": "2026-07-28", "frozen": True},
        "lanes": [
            {
                "lane_id": "volatility_expansion_observation",
                "policy_snapshot_sha256": "vol",
                "symbols": ["SPY", "QQQ", "IWM", "DIA"],
            },
            {
                "lane_id": "bullish_pullback_observation",
                "policy_snapshot_sha256": "bull",
                "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
            },
        ],
    }


def _feature() -> dict:
    return {
        "report_id": "regular_options_feature_store",
        "status": "feature_store_built",
        "shared_quote_dates": ["2026-02-02", "2026-02-03"],
    }


def _market_regime_blocked() -> dict:
    return {
        "report_id": "regular_options_point_in_time_market_regime_inputs",
        "status": "blocked_point_in_time_market_regime_inputs",
        "point_in_time_market_regime_inputs_available": False,
        "blockers": [
            "point_in_time_market_regime_row_validation_failed",
            "insufficient_month_coverage",
            "insufficient_date_coverage",
        ],
        "row_blocker_counts": {"market_regime_source_time_not_point_in_time": 2},
        "source_time_policy": {
            "source_time_field": "market_data.db:daily_history.fetched_at",
            "historical_reconstruction_can_clear_point_in_time_blockers": False,
        },
    }


def _vix_ready() -> dict:
    return {
        "report_id": "regular_options_point_in_time_vix_bucket",
        "status": "point_in_time_vix_bucket_ready",
        "blockers": [],
    }


def _write_trusted_option_rows(db_path: Path) -> None:
    init_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        batch_id = conn.execute(
            """
            INSERT INTO import_batches (
                source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thetadata_opra_nbbo_1m",
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "abc",
                "2026-06-04T00:00:00Z",
                2,
                2,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        rows = [
            ("SPY260220C00500000", 500.0, 4.1, 4.3, None, None, None),
            ("SPY260220C00505000", 505.0, 2.1, 2.3, None, None, None),
        ]
        for contract, strike, bid, ask, iv, volume, oi in rows:
            conn.execute(
                """
                INSERT INTO option_quote_snapshots (
                    as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                    contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                    underlying_price, volume, open_interest, source_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-02-03T15:12:00Z",
                    "2026-02-03",
                    10 * 60 + 12,
                    "intraday",
                    "SPY",
                    contract,
                    "2026-02-20",
                    "call",
                    strike,
                    bid,
                    ask,
                    None,
                    iv,
                    501.0,
                    volume,
                    oi,
                    batch_id,
                ),
            )
        conn.commit()


def _write_exit_rows(db_path: Path, *, long_bid: float, short_ask: float) -> None:
    init_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        batch_id = conn.execute(
            """
            INSERT INTO import_batches (
                source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thetadata_opra_nbbo_1m",
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "abc",
                "2026-06-04T00:00:00Z",
                2,
                2,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        rows = [
            ("SPY260204C00500000", 500.0, long_bid, long_bid + 0.2),
            ("SPY260204C00505000", 505.0, max(short_ask - 0.2, 0.0), short_ask),
        ]
        for contract, strike, bid, ask in rows:
            conn.execute(
                """
                INSERT INTO option_quote_snapshots (
                    as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                    contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                    underlying_price, volume, open_interest, source_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-02-04T20:56:00Z",
                    "2026-02-04",
                    15 * 60 + 56,
                    "intraday",
                    "SPY",
                    contract,
                    "2026-02-04",
                    "call",
                    strike,
                    bid,
                    ask,
                    None,
                    None,
                    503.0,
                    None,
                    None,
                    batch_id,
                ),
            )
        conn.commit()


class RegularOptionsHistoricalFrozenScannerReplayAdapterTests(unittest.TestCase):
    def test_required_scanner_signatures_are_available(self) -> None:
        contract = adapter._scanner_contract()

        self.assertTrue(contract["proof_safe_contract_available"])
        self.assertEqual(contract["blockers"], [])
        inspected = {(item["path"], item["function"]): item for item in contract["inspected_callables"]}
        self.assertIn("candidate_generation_date", inspected[("supervised_scan.py", "run_supervised_scan")]["parameters"])
        self.assertIn("as_of_date", inspected[("options_chatbot.py", "scan_daily_top_trades")]["parameters"])
        self.assertIn("no_write", inspected[("options_chatbot.py", "scan_daily_top_trades")]["parameters"])
        self.assertIn("candidate_generation_date", inspected[("options_chatbot.py", "_fetch_best_option")]["parameters"])
        self.assertIn("as_of_date", inspected[("options_chatbot.py", "_fetch_best_spread")]["parameters"])

    def test_historical_option_provider_reads_trusted_rows_and_preserves_missing_optional_fields(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_trusted_option_rows(db_path)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)}, clear=False), \
                 patch.object(oc, "_cached_options_metadata", side_effect=AssertionError("latest chain fallback called")):
                option = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.55,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                    return_context=True,
                )

        self.assertIsNotNone(option)
        assert option is not None
        self.assertEqual(option["contract_symbol"], "SPY260220C00500000")
        self.assertEqual(option["premium"], 4.3)
        self.assertEqual(option["quote_basis"], "ask")
        self.assertEqual(option["options_data_source"], "historical_options_store_trusted_thetadata_opra_nbbo")
        self.assertFalse(option["live_chain"])
        self.assertTrue(option["historical_chain"])
        self.assertIsNone(option["iv"])
        self.assertIsNone(option["volume"])
        self.assertIsNone(option["open_interest"])

    def test_historical_mode_does_not_call_latest_chain_fallback_when_rows_missing(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            init_schema(db_path)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)}, clear=False), \
                 patch.object(oc, "_cached_options_metadata", side_effect=AssertionError("latest chain fallback called")), \
                 patch.object(oc, "_cached_option_chain_metadata", side_effect=AssertionError("latest chain fallback called")):
                option = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.50,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                )

        self.assertIsNone(option)

    def test_attach_exit_pnl_emits_fee_adjusted_usd_and_floored_exit_flag(self) -> None:
        base_trade = {
            "entry_date": "2026-02-03",
            "expiry": "2026-02-04",
            "dte": 1,
            "entry_debit": 2.0,
            "long_contract_symbol": "SPY260204C00500000",
            "short_contract_symbol": "SPY260204C00505000",
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "positive.db"
            _write_exit_rows(db_path, long_bid=3.0, short_ask=0.8)
            with sqlite3.connect(db_path) as conn:
                priced = adapter._attach_exit_pnl(
                    conn,
                    trade=dict(base_trade),
                    market_dates=[adapter.date(2026, 2, 4)],
                    fee_per_contract_leg_usd=0.65,
                )

            floored_db = Path(tmp) / "floored.db"
            _write_exit_rows(floored_db, long_bid=3.0, short_ask=3.5)
            with sqlite3.connect(floored_db) as conn:
                floored = adapter._attach_exit_pnl(
                    conn,
                    trade=dict(base_trade),
                    market_dates=[adapter.date(2026, 2, 4)],
                    fee_per_contract_leg_usd=0.65,
                )

        self.assertEqual(priced["contract_multiplier"], 100)
        self.assertEqual(priced["total_fees_usd"], 2.6)
        self.assertEqual(priced["gross_pnl_usd"], 20.0)
        self.assertEqual(priced["net_pnl_usd"], 17.4)
        self.assertEqual(priced["pnl_pct"], 10.0)
        self.assertEqual(priced["net_pnl_pct_after_fees"], 8.7)
        self.assertFalse(priced["exit_value_floored_at_zero"])
        self.assertEqual(floored["exit_value"], 0.0)
        self.assertEqual(floored["gross_pnl_usd"], -200.0)
        self.assertEqual(floored["net_pnl_usd"], -202.6)
        self.assertTrue(floored["exit_value_floored_at_zero"])

    def test_adapter_fails_closed_with_specific_point_in_time_input_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            regime = root / "regime.json"
            vix = root / "vix.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(regime, _market_regime_blocked())
            _write_json(vix, _vix_ready())

            report = adapter.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                market_regime_inputs_path=regime,
                vix_bucket_path=vix,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_frozen_scanner_replay_adapter")
        self.assertEqual(report["daily_candidate_decision_row_count"], 28)
        self.assertEqual(
            report["daily_status_counts"],
            {"blocked_missing_historical_scanner_point_in_time_inputs": 28},
        )
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertFalse(any(row["proof_safe"] for row in report["daily_candidate_decisions"]))
        self.assertNotIn("scanner_api_missing_historical_no_write_contract", report["blockers"])
        self.assertNotIn("scanner_option_selection_missing_historical_as_of_contract", report["blockers"])
        self.assertIn("underlying_daily_history_source_not_point_in_time", report["blockers"])
        self.assertIn("missing_lane_specific_point_in_time_feature_inputs", report["blockers"])
        self.assertIn("missing_historical_option_chain_selection_surface", report["blockers"])
        self.assertIn("missing_historical_entry_underlying_price_surface", report["blockers"])
        self.assertIn("missing_point_in_time_earnings_calendar_source", report["blockers"])
        self.assertNotIn("missing_point_in_time_vix_source", report["blockers"])
        self.assertEqual(report["smallest_next_blocker_clearing_slice"], "underlying_daily_history_source_not_point_in_time")
        self.assertTrue(report["adapter_contract"]["default_no_write"])
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertFalse(report["adapter_contract"]["scanner_parity"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")

    def test_etf_rows_do_not_require_earnings_calendar_but_equity_rows_do(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            regime = root / "regime.json"
            vix = root / "vix.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(regime, _market_regime_blocked())
            _write_json(vix, _vix_ready())
            report = adapter.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                market_regime_inputs_path=regime,
                vix_bucket_path=vix,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        spy = next(row for row in report["daily_candidate_decisions"] if row["symbol"] == "SPY")
        aapl = next(row for row in report["daily_candidate_decisions"] if row["symbol"] == "AAPL")
        self.assertNotIn("missing_point_in_time_earnings_calendar_source", spy["blockers"])
        self.assertIn("missing_point_in_time_earnings_calendar_source", aapl["blockers"])

    def test_ready_earnings_calendar_removes_source_blocker_and_skips_event_window(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            db_path = root / "options_history.db"
            init_schema(db_path)
            market_regime = {
                "input_rows": [
                    {
                        "input_date_et": "2026-02-03",
                        "symbol_features": [
                            {
                                "symbol": "AAPL",
                                "prior_20_trading_day_return_pct": 1.0,
                                "prior_close": 190.0,
                                "prior_50_trading_day_sma": 185.0,
                                "above_prior_50_sma": True,
                                "known_at_utc": "2026-02-02T21:30:00Z",
                                "source_ref": "fixture://underlying/AAPL",
                                "source_row_hash": "hash-aapl",
                                "prior_bar_date_et": "2026-02-02",
                                "point_in_time_valid": True,
                                "proof_eligible": True,
                            }
                        ],
                    }
                ]
            }
            earnings_calendar = {
                "status": "point_in_time_earnings_calendar_ready",
                "blockers": [],
                "earnings_events": [
                    {
                        "symbol": "AAPL",
                        "earnings_date_et": "2026-02-20",
                        "known_at_utc": "2025-12-01T00:00:00Z",
                        "source_retrieved_at_utc": "2025-12-01T00:00:00Z",
                    }
                ],
            }
            surfaces = {"blockers": []}
            rows = adapter._build_rows(
                market_dates=[adapter.date(2026, 2, 3)],
                pairs=[{"lane": "bullish_pullback_observation", "underlying": "AAPL", "policy_snapshot_sha256": "bull"}],
                as_of=adapter.date(2026, 6, 4),
                cohort={"byte_frozen_policy_snapshot": {"lanes": {"bullish_pullback_observation": {"policy": {"target_dte": 35}}}}},
                market_regime=market_regime,
                scanner_contract={"blockers": []},
                surface_inventory=surfaces,
                earnings_calendar=earnings_calendar,
                options_db_path=db_path,
            )

        self.assertEqual(rows[0]["status"], "explicit_no_pick")
        self.assertEqual(rows[0]["no_pick_reason"], "earnings_within_hold_window")
        self.assertEqual(rows[0]["signal_evidence"]["earnings_event_date_et"], "2026-02-20")
        self.assertEqual(rows[0]["blockers"], [])
        self.assertFalse(rows[0]["scanner_parity"])
        self.assertFalse(rows[0]["production_scanner_replay"])

    def test_earnings_event_after_candidate_decision_does_not_block_historical_row(self) -> None:
        earnings_calendar = {
            "status": "point_in_time_earnings_calendar_ready",
            "blockers": [],
            "earnings_events": [
                {
                    "symbol": "AAPL",
                    "earnings_date_et": "2026-02-20",
                    "known_at_utc": "2026-02-10T14:00:00Z",
                    "source_retrieved_at_utc": "2026-02-10T14:00:00Z",
                }
            ],
        }
        earnings_index = adapter._earnings_dates_by_symbol(earnings_calendar)

        self.assertIsNone(
            adapter._earnings_within_hold_window(
                earnings_index,
                symbol="AAPL",
                candidate_date=adapter.date(2026, 2, 3),
                dte=35,
            )
        )
        self.assertEqual(
            adapter._earnings_within_hold_window(
                earnings_index,
                symbol="AAPL",
                candidate_date=adapter.date(2026, 2, 11),
                dte=35,
            ),
            adapter.date(2026, 2, 20),
        )

    def test_daily_materializer_consumes_adapter_blockers_without_inventing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            regime = root / "regime.json"
            vix = root / "vix.json"
            source = root / "adapter.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(regime, _market_regime_blocked())
            _write_json(vix, _vix_ready())
            adapter_report = adapter.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                market_regime_inputs_path=regime,
                vix_bucket_path=vix,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            _write_json(source, adapter_report)

            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_daily_candidate_decisions")
        self.assertEqual(
            report["daily_status_counts"],
            {"blocked_missing_historical_scanner_point_in_time_inputs": 28},
        )
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertIn("missing_historical_scanner_point_in_time_inputs", report["blockers"])
        self.assertIn("underlying_daily_history_source_not_point_in_time", report["blockers"])
        self.assertIn("missing_historical_option_chain_selection_surface", report["blockers"])
        self.assertFalse(any(row["proof_safe"] for row in report["daily_candidate_decisions"]))

    def test_write_outputs_creates_adapter_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            regime = root / "regime.json"
            vix = root / "vix.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(regime, _market_regime_blocked())
            _write_json(vix, _vix_ready())
            report = adapter.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                market_regime_inputs_path=regime,
                vix_bucket_path=vix,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            artifacts = adapter.write_outputs(report, output_dir=root / "out", docs_report=root / "out" / "latest.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "daily_candidate_decisions.jsonl").exists())
            self.assertTrue(artifacts["docs_report"].replace("\\", "/").endswith("/out/latest.md"))


if __name__ == "__main__":
    unittest.main()
