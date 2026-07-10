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
from scripts import (
    build_regular_options_13_symbol_frozen_daily_candidate_decisions as decisions,
)
from scripts import (
    build_regular_options_historical_frozen_scanner_replay_adapter as adapter,
)
from scripts import regular_options_frozen_candidate_generation_entrypoint as entrypoint


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )


def _cohort() -> dict:
    return {
        "contract_id": "forward-cohort-preregistration",
        "status": "active",
        "cohort": {
            "freeze_date": "2026-06-14",
            "eval_date": "2026-07-28",
            "frozen": True,
        },
        "lanes": [
            {
                "lane_id": "volatility_expansion_observation",
                "policy_snapshot_sha256": "vol",
                "symbols": ["SPY", "QQQ", "IWM", "DIA"],
            },
            {
                "lane_id": "bullish_pullback_observation",
                "policy_snapshot_sha256": "bull",
                "symbols": [
                    "IWM",
                    "AAPL",
                    "GOOGL",
                    "UNH",
                    "LLY",
                    "JNJ",
                    "XOM",
                    "CVX",
                    "COP",
                    "NEM",
                ],
            },
        ],
    }


def _feature() -> dict:
    return {
        "report_id": "regular_options_feature_store",
        "status": "feature_store_built",
        "shared_quote_dates": ["2026-02-02", "2026-02-03"],
    }


def _ready_cohort() -> dict:
    cohort = _cohort()
    cohort["byte_frozen_policy_snapshot"] = {
        "lanes": {
            "bullish_pullback_observation": {"policy": {"target_dte": 17}},
            "volatility_expansion_observation": {"policy": {"target_dte": 17}},
        }
    }
    return cohort


def _ready_market_regime() -> dict:
    return {
        "report_id": "regular_options_point_in_time_market_regime_inputs",
        "status": "point_in_time_market_regime_inputs_ready",
        "point_in_time_market_regime_inputs_available": True,
        "blockers": [],
        "input_rows": [
            {
                "input_date_et": "2026-02-03",
                "symbol_features": [
                    {
                        "symbol": symbol,
                        "prior_20_trading_day_return_pct": 1.0,
                        "prior_close": 190.0 if symbol == "AAPL" else 100.0,
                        "prior_50_trading_day_sma": 180.0 if symbol == "AAPL" else 90.0,
                        "above_prior_50_sma": True,
                        "known_at_utc": "2026-02-02T21:30:00Z",
                        "source_ref": f"fixture://underlying/{symbol}",
                        "source_row_hash": f"hash-{symbol}",
                        "prior_bar_date_et": "2026-02-02",
                        "point_in_time_valid": True,
                        "proof_eligible": True,
                    }
                    for symbol in adapter.ALLOWED_UNIVERSE
                ],
            }
        ],
    }


def _ready_input_surface_tracker() -> dict:
    return {
        "report_id": "regular_options_historical_scanner_input_surface_tracker",
        "status": "historical_scanner_input_surface_tracker_ready",
        "requested_window": {
            "window_start": "2026-02-03",
            "window_end": "2026-02-03",
            "symbol_date_count": len(adapter.ALLOWED_UNIVERSE),
        },
        "surface_readiness": {
            "entry_underlying_price_surface": {"available": True},
            "option_chain_selection_surface": {"available": True},
        },
    }


def _ready_earnings_calendar() -> dict:
    return {
        "report_id": "regular_options_point_in_time_earnings_calendar",
        "status": "point_in_time_earnings_calendar_ready",
        "blockers": [],
        "requested_window": {"window_start": "2026-02-03", "window_end": "2026-02-03"},
        "earnings_events": [],
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
                    "2026-02-04T20:55:00Z",
                    "2026-02-04",
                    15 * 60 + 55,
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


def _write_aapl_entry_and_exit_rows(db_path: Path) -> None:
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
                adapter.THETADATA_SOURCE_LABEL,
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "ready",
                "2026-02-19T00:00:00Z",
                4,
                4,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        rows = [
            (
                "2026-02-03T15:12:00Z",
                "2026-02-03",
                612,
                "AAPL260220C00190000",
                190.0,
                3.3,
                3.5,
            ),
            (
                "2026-02-03T15:12:00Z",
                "2026-02-03",
                612,
                "AAPL260220C00195000",
                195.0,
                1.0,
                1.2,
            ),
            (
                "2026-02-17T20:55:00Z",
                "2026-02-17",
                955,
                "AAPL260220C00190000",
                190.0,
                5.0,
                5.2,
            ),
            (
                "2026-02-17T20:55:00Z",
                "2026-02-17",
                955,
                "AAPL260220C00195000",
                195.0,
                0.8,
                1.0,
            ),
        ]
        for as_of, quote_date, minute, contract, strike, bid, ask in rows:
            conn.execute(
                """
                INSERT INTO option_quote_snapshots (
                    as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                    contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                    underlying_price, volume, open_interest, source_batch_id
                ) VALUES (?, ?, ?, 'intraday', 'AAPL', ?, '2026-02-20', 'call', ?, ?, ?, NULL, NULL, 190.0, NULL, NULL, ?)
                """,
                (as_of, quote_date, minute, contract, strike, bid, ask, batch_id),
            )
        conn.commit()


class RegularOptionsHistoricalFrozenScannerReplayAdapterTests(unittest.TestCase):
    def test_scanner_contract_separates_signature_support_from_end_to_end_replay(
        self,
    ) -> None:
        contract = adapter._scanner_contract()

        self.assertTrue(contract["signature_support_available"])
        self.assertTrue(contract["historical_option_provider_support_available"])
        self.assertTrue(contract["research_materializer_support_available"])
        self.assertFalse(contract["end_to_end_no_write_scanner_replay_available"])
        self.assertFalse(contract["proof_safe_contract_available"])
        self.assertIn(
            "end_to_end_no_write_scanner_replay_unavailable", contract["blockers"]
        )
        self.assertTrue(contract["observed_no_write_empty_short_circuit"])
        inspected = {
            (item["path"], item["function"]): item
            for item in contract["inspected_callables"]
        }
        self.assertIn(
            "candidate_generation_date",
            inspected[("supervised_scan.py", "run_supervised_scan")]["parameters"],
        )
        self.assertIn(
            "as_of_date",
            inspected[("options_chatbot.py", "scan_daily_top_trades")]["parameters"],
        )
        self.assertIn(
            "no_write",
            inspected[("options_chatbot.py", "scan_daily_top_trades")]["parameters"],
        )
        self.assertIn(
            "candidate_generation_date",
            inspected[("options_chatbot.py", "_fetch_best_option")]["parameters"],
        )
        self.assertIn(
            "as_of_date",
            inspected[("options_chatbot.py", "_fetch_best_spread")]["parameters"],
        )

    def test_historical_option_provider_reads_trusted_rows_and_preserves_missing_optional_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_trusted_option_rows(db_path)
            with (
                patch.dict(
                    os.environ,
                    {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)},
                    clear=False,
                ),
                patch.object(
                    oc,
                    "_cached_options_metadata",
                    side_effect=AssertionError("latest chain fallback called"),
                ),
            ):
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
        self.assertEqual(
            option["options_data_source"],
            "historical_options_store_trusted_thetadata_opra_nbbo",
        )
        self.assertFalse(option["live_chain"])
        self.assertTrue(option["historical_chain"])
        self.assertIsNone(option["iv"])
        self.assertIsNone(option["volume"])
        self.assertIsNone(option["open_interest"])

    def test_historical_mode_does_not_call_latest_chain_fallback_when_rows_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            init_schema(db_path)
            with (
                patch.dict(
                    os.environ,
                    {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)},
                    clear=False,
                ),
                patch.object(
                    oc,
                    "_cached_options_metadata",
                    side_effect=AssertionError("latest chain fallback called"),
                ),
                patch.object(
                    oc,
                    "_cached_option_chain_metadata",
                    side_effect=AssertionError("latest chain fallback called"),
                ),
            ):
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

    def test_select_spread_rejects_unsynchronized_leg_quote_timestamps(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_trusted_option_rows(db_path)
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE option_quote_snapshots
                    SET as_of_utc = ?, quote_minute_et = ?
                    WHERE contract_symbol = ?
                    """,
                    ("2026-02-03T15:13:00Z", 10 * 60 + 13, "SPY260220C00505000"),
                )
                conn.commit()
                trade, reason = adapter._select_spread(
                    conn,
                    symbol="SPY",
                    day=adapter.date(2026, 2, 3),
                    direction="call",
                    policy={"target_dte": 17},
                    stock_price=501.0,
                )

        self.assertIsNone(trade)
        self.assertEqual(reason, "no_synchronized_exact_entry_quote_pair")

    def test_fractional_second_asof_mismatches_do_not_synchronize_entry_or_exit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            entry_db = Path(tmp) / "entry.db"
            _write_trusted_option_rows(entry_db)
            with sqlite3.connect(entry_db) as conn:
                conn.execute(
                    "UPDATE option_quote_snapshots SET as_of_utc = '2026-02-03T15:12:00.100Z' WHERE contract_symbol = 'SPY260220C00500000'"
                )
                conn.execute(
                    "UPDATE option_quote_snapshots SET as_of_utc = '2026-02-03T15:12:00.900Z' WHERE contract_symbol = 'SPY260220C00505000'"
                )
                conn.commit()
                trade, reason = adapter._select_spread(
                    conn,
                    symbol="SPY",
                    day=adapter.date(2026, 2, 3),
                    direction="call",
                    policy={"target_dte": 17},
                    stock_price=501.0,
                )

            exit_db = Path(tmp) / "exit.db"
            _write_exit_rows(exit_db, long_bid=3.0, short_ask=0.8)
            with sqlite3.connect(exit_db) as conn:
                conn.execute(
                    "UPDATE option_quote_snapshots SET as_of_utc = '2026-02-04T20:55:00.100Z' WHERE contract_symbol = 'SPY260204C00500000'"
                )
                conn.execute(
                    "UPDATE option_quote_snapshots SET as_of_utc = '2026-02-04T20:55:00.900Z' WHERE contract_symbol = 'SPY260204C00505000'"
                )
                conn.commit()
                priced = adapter._attach_exit_pnl(
                    conn,
                    trade={
                        "entry_date": "2026-02-03",
                        "expiry": "2026-02-04",
                        "dte": 1,
                        "entry_debit": 2.0,
                        "long_contract_symbol": "SPY260204C00500000",
                        "short_contract_symbol": "SPY260204C00505000",
                    },
                    market_dates=[adapter.date(2026, 2, 4)],
                )

        self.assertIsNone(trade)
        self.assertEqual(reason, "no_synchronized_exact_entry_quote_pair")
        self.assertFalse(priced.get("exact_priced", False))
        self.assertEqual(
            priced["exit_evidence_blocker"],
            "missing_synchronized_exact_exit_quote_pair",
        )

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
        self.assertEqual(priced["gross_pnl_pct"], 10.0)
        self.assertEqual(priced["net_pnl_pct"], 8.5884)
        self.assertEqual(priced["net_pnl_pct_after_fees"], 8.5884)
        self.assertEqual(priced["exit_quote_timestamp_utc"], "2026-02-04T20:55:00Z")
        self.assertEqual(
            priced["exit_price_lineage_status"],
            "trusted_synchronized_exact_exit_price_lineage",
        )
        self.assertFalse(priced["exit_value_floored_at_zero"])
        self.assertEqual(floored["exit_value"], 0.0)
        self.assertEqual(floored["gross_pnl_usd"], -200.0)
        self.assertEqual(floored["net_pnl_usd"], -202.6)
        self.assertTrue(floored["exit_value_floored_at_zero"])
        self.assertEqual(floored["net_pnl_pct"], -100.0)

    def test_attach_exit_pnl_distinguishes_missing_calendar_from_right_censoring(
        self,
    ) -> None:
        trade = {
            "entry_date": "2026-02-03",
            "expiry": "2026-02-20",
            "dte": 17,
            "entry_debit": 2.0,
            "long_contract_symbol": "SPY260220C00500000",
            "short_contract_symbol": "SPY260220C00505000",
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "empty.db"
            init_schema(db_path)
            with sqlite3.connect(db_path) as conn:
                result = adapter._attach_exit_pnl(
                    conn,
                    trade=trade,
                    market_dates=[adapter.date(2026, 2, 3)],
                    as_of=adapter.date(2026, 2, 18),
                )

        self.assertFalse(result["exit_right_censored"])
        self.assertEqual(result["policy_exit_target_date"], "2026-02-17")
        self.assertEqual(
            result["exit_evidence_blocker"], "missing_policy_exit_calendar_date"
        )
        self.assertEqual(
            result["exit_pricing_status"], "missing_policy_exit_calendar_date"
        )

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "empty.db"
            init_schema(db_path)
            with sqlite3.connect(db_path) as conn:
                censored = adapter._attach_exit_pnl(
                    conn,
                    trade={**trade, "exit_evidence_blocker": None},
                    market_dates=[],
                    as_of=adapter.date(2026, 2, 10),
                )
        self.assertTrue(censored["exit_right_censored"])
        self.assertEqual(
            censored["exit_evidence_blocker"], "policy_exit_right_censored"
        )

    def test_attach_exit_pnl_rejects_unsynchronized_or_non_1555_exit_quotes(
        self,
    ) -> None:
        trade = {
            "entry_date": "2026-02-03",
            "expiry": "2026-02-04",
            "dte": 1,
            "entry_debit": 2.0,
            "long_contract_symbol": "SPY260204C00500000",
            "short_contract_symbol": "SPY260204C00505000",
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "mismatch.db"
            _write_exit_rows(db_path, long_bid=3.0, short_ask=0.8)
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE option_quote_snapshots
                    SET as_of_utc = '2026-02-04T20:56:00Z', quote_minute_et = 956
                    WHERE contract_symbol = 'SPY260204C00505000'
                    """
                )
                conn.commit()
                result = adapter._attach_exit_pnl(
                    conn,
                    trade=trade,
                    market_dates=[adapter.date(2026, 2, 4)],
                )

        self.assertFalse(result.get("exact_priced", False))
        self.assertEqual(
            result["exit_evidence_blocker"],
            "missing_synchronized_exact_exit_quote_pair",
        )

    def test_partial_quote_surface_keeps_selected_diagnostics_but_blocks_denominator_acceptance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            cohort_path = root / "cohort.json"
            feature_path = root / "feature.json"
            regime_path = root / "regime.json"
            vix_path = root / "vix.json"
            tracker_path = root / "tracker.json"
            earnings_path = root / "earnings.json"
            db_path = root / "options_history.db"
            adapter_path = root / "adapter.json"
            decisions_path = root / "decisions.json"
            _write_json(cohort_path, _ready_cohort())
            _write_json(
                feature_path,
                {
                    "report_id": "regular_options_feature_store",
                    "status": "feature_store_built",
                    "shared_quote_dates": ["2026-02-03"],
                },
            )
            _write_json(regime_path, _ready_market_regime())
            _write_json(vix_path, _vix_ready())
            _write_json(tracker_path, _ready_input_surface_tracker())
            _write_json(earnings_path, _ready_earnings_calendar())
            _write_aapl_entry_and_exit_rows(db_path)

            adapter_report = adapter.build_report(
                forward_cohort_path=cohort_path,
                feature_store_path=feature_path,
                market_regime_inputs_path=regime_path,
                vix_bucket_path=vix_path,
                input_surface_tracker_path=tracker_path,
                earnings_calendar_path=earnings_path,
                options_db_path=db_path,
                window_start="2026-02-03",
                window_end="2026-02-03",
                as_of_date="2026-02-18",
            )
            _write_json(adapter_path, adapter_report)
            daily_report = decisions.build_report(
                forward_cohort_path=cohort_path,
                feature_store_path=feature_path,
                source_daily_decisions_path=adapter_path,
                window_start="2026-02-03",
                window_end="2026-02-03",
                as_of_date="2026-02-18",
            )
            _write_json(decisions_path, daily_report)
            entrypoint_report = entrypoint.build_report(
                source_candidate_generation_path=decisions_path,
                feature_store_path=feature_path,
                forward_cohort_path=cohort_path,
                window_start="2026-02-03",
                window_end="2026-02-03",
                as_of_date="2026-02-18",
            )

        for report in (adapter_report, daily_report, entrypoint_report):
            self.assertFalse(report["research_materializer_ready"])
            self.assertIn(
                "end_to_end_no_write_scanner_replay_unavailable", report["blockers"]
            )
            self.assertFalse(report["production_scanner_replay"])
            self.assertFalse(
                all(
                    row["research_materializer_safe"]
                    for row in report["daily_candidate_generation"]
                )
            )
            self.assertFalse(
                any(row["proof_safe"] for row in report["daily_candidate_generation"])
            )
        self.assertEqual(adapter_report["selected_candidate_row_count"], 1)
        self.assertEqual(daily_report["selected_candidate_row_count"], 1)
        self.assertEqual(entrypoint_report["selected_candidate_row_count"], 0)
        self.assertEqual(adapter_report["daily_candidate_generation_row_count"], 14)
        self.assertEqual(
            adapter_report["daily_status_counts"][
                "blocked_missing_historical_scanner_point_in_time_inputs"
            ],
            9,
        )
        self.assertIn("missing_trusted_entry_quote_surface", adapter_report["blockers"])
        self.assertIn(
            "manifest_bound_quote_corpus_not_established",
            adapter_report["proof_or_nomination_blockers"],
        )
        mismatch_ids = {
            item["mismatch_id"]
            for item in adapter_report["production_parity_mismatches"]
        }
        self.assertIn(
            "fixed_time_exit_vs_active_path_dependent_exit_policy", mismatch_ids
        )
        self.assertIn("selection_conditioned_current_universe_backfill", mismatch_ids)
        self.assertTrue(
            adapter_report["historical_selection_conditioning"][
                "selection_conditioned_profitability_estimate"
            ]
        )

    def test_adapter_fails_closed_with_specific_point_in_time_input_blockers(
        self,
    ) -> None:
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

        self.assertEqual(
            report["status"], "blocked_historical_frozen_scanner_replay_adapter"
        )
        self.assertEqual(report["daily_candidate_decision_row_count"], 28)
        self.assertEqual(
            report["daily_status_counts"],
            {"blocked_missing_historical_scanner_point_in_time_inputs": 28},
        )
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertFalse(
            any(row["proof_safe"] for row in report["daily_candidate_decisions"])
        )
        self.assertNotIn(
            "scanner_api_missing_historical_no_write_contract", report["blockers"]
        )
        self.assertNotIn(
            "scanner_option_selection_missing_historical_as_of_contract",
            report["blockers"],
        )
        self.assertIn(
            "underlying_daily_history_source_not_point_in_time", report["blockers"]
        )
        self.assertIn(
            "missing_lane_specific_point_in_time_feature_inputs", report["blockers"]
        )
        self.assertIn(
            "missing_historical_option_chain_selection_surface", report["blockers"]
        )
        self.assertIn(
            "missing_historical_entry_underlying_price_surface", report["blockers"]
        )
        self.assertIn(
            "missing_point_in_time_earnings_calendar_source", report["blockers"]
        )
        self.assertNotIn("missing_point_in_time_vix_source", report["blockers"])
        self.assertEqual(
            report["smallest_next_blocker_clearing_slice"],
            "underlying_daily_history_source_not_point_in_time",
        )
        self.assertTrue(report["adapter_contract"]["default_no_write"])
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertFalse(report["adapter_contract"]["scanner_parity"])
        self.assertIn(
            "end_to_end_no_write_scanner_replay_unavailable", report["blockers"]
        )
        self.assertEqual(
            report["candidate_materialization_basis"],
            "deterministic_local_pit_candidate_materializer_v1",
        )

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

        spy = next(
            row for row in report["daily_candidate_decisions"] if row["symbol"] == "SPY"
        )
        aapl = next(
            row
            for row in report["daily_candidate_decisions"]
            if row["symbol"] == "AAPL"
        )
        self.assertNotIn(
            "missing_point_in_time_earnings_calendar_source", spy["blockers"]
        )
        self.assertIn(
            "missing_point_in_time_earnings_calendar_source", aapl["blockers"]
        )

    def test_ready_earnings_calendar_removes_source_blocker_and_skips_event_window(
        self,
    ) -> None:
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
                pairs=[
                    {
                        "lane": "bullish_pullback_observation",
                        "underlying": "AAPL",
                        "policy_snapshot_sha256": "bull",
                    }
                ],
                as_of=adapter.date(2026, 6, 4),
                cohort={
                    "byte_frozen_policy_snapshot": {
                        "lanes": {
                            "bullish_pullback_observation": {
                                "policy": {"target_dte": 35}
                            }
                        }
                    }
                },
                market_regime=market_regime,
                scanner_contract={"blockers": []},
                surface_inventory=surfaces,
                earnings_calendar=earnings_calendar,
                options_db_path=db_path,
            )

        self.assertEqual(rows[0]["status"], "explicit_no_pick")
        self.assertEqual(rows[0]["no_pick_reason"], "earnings_within_hold_window")
        self.assertEqual(
            rows[0]["signal_evidence"]["earnings_event_date_et"], "2026-02-20"
        )
        self.assertEqual(rows[0]["blockers"], [])
        self.assertFalse(rows[0]["proof_safe"])
        self.assertEqual(rows[0]["tradable_after"], "2026-02-03T15:10:00Z")
        self.assertEqual(rows[0]["decision_timestamp_utc"], "2026-02-03T15:10:00Z")
        self.assertFalse(rows[0]["scanner_parity"])
        self.assertFalse(rows[0]["production_scanner_replay"])

    def test_earnings_event_after_candidate_decision_does_not_block_historical_row(
        self,
    ) -> None:
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
                decision_timestamp_utc="2026-02-03T15:12:00Z",
            )
        )
        self.assertEqual(
            adapter._earnings_within_hold_window(
                earnings_index,
                symbol="AAPL",
                candidate_date=adapter.date(2026, 2, 11),
                dte=35,
                decision_timestamp_utc="2026-02-11T15:12:00Z",
            ),
            adapter.date(2026, 2, 20),
        )

    def test_feature_known_at_must_be_aware_causal_and_unique_per_symbol_date(
        self,
    ) -> None:
        feature = {
            "symbol": "AAPL",
            "prior_20_trading_day_return_pct": 1.0,
            "prior_close": 190.0,
            "prior_50_trading_day_sma": 185.0,
            "above_prior_50_sma": True,
            "prior_bar_date_et": "2026-02-02",
            "point_in_time_valid": True,
            "proof_eligible": True,
            "source_ref": "fixture://underlying/AAPL",
            "source_row_hash": "first",
        }
        candidate_date = adapter.date(2026, 2, 3)
        self.assertFalse(
            adapter._feature_ready(
                {**feature, "known_at_utc": "2026-02-02T21:00:00"},
                candidate_date=candidate_date,
                decision_timestamp_utc="2026-02-03T15:12:00Z",
            )
        )
        self.assertFalse(
            adapter._feature_ready(
                {**feature, "known_at_utc": "2026-02-03T15:12:00.001Z"},
                candidate_date=candidate_date,
                decision_timestamp_utc="2026-02-03T15:12:00Z",
            )
        )
        self.assertTrue(
            adapter._feature_ready(
                {**feature, "known_at_utc": "2026-02-03T10:12:00-05:00"},
                candidate_date=candidate_date,
                decision_timestamp_utc="2026-02-03T15:12:00Z",
            )
        )
        indexed = adapter._symbol_features_by_date(
            {
                "input_rows": [
                    {
                        "input_date_et": "2026-02-03",
                        "symbol_features": [
                            {**feature, "known_at_utc": "2026-02-02T21:00:00Z"},
                            {
                                **feature,
                                "known_at_utc": "2026-02-02T21:00:00Z",
                                "source_row_hash": "second",
                            },
                        ],
                    }
                ]
            }
        )
        duplicate = indexed["2026-02-03"]["AAPL"]
        self.assertTrue(duplicate["_duplicate_feature_lineage"])
        direction, blockers, _evidence = adapter._direction_for_row(
            lane="bullish_pullback_observation",
            symbol="AAPL",
            feature=duplicate,
            candidate_date=candidate_date,
        )
        self.assertIsNone(direction)
        self.assertIn("duplicate_symbol_date_feature_lineage", blockers)

    def test_missing_entry_evidence_blocks_denominator_but_full_surface_no_executable_is_no_pick(
        self,
    ) -> None:
        market_regime = {
            "input_rows": [
                {
                    "input_date_et": "2026-02-03",
                    "symbol_features": [
                        {
                            "symbol": "SPY",
                            "prior_20_trading_day_return_pct": 1.0,
                            "prior_close": 501.0,
                            "prior_50_trading_day_sma": 490.0,
                            "above_prior_50_sma": True,
                            "known_at_utc": "2026-02-02T21:00:00Z",
                            "source_ref": "fixture://underlying/SPY",
                            "source_row_hash": "hash-spy",
                            "prior_bar_date_et": "2026-02-02",
                            "point_in_time_valid": True,
                            "proof_eligible": True,
                        }
                    ],
                }
            ]
        }
        common = {
            "market_dates": [adapter.date(2026, 2, 3)],
            "pairs": [
                {
                    "lane": "bullish_pullback_observation",
                    "underlying": "SPY",
                    "policy_snapshot_sha256": "bull",
                }
            ],
            "as_of": adapter.date(2026, 6, 4),
            "market_regime": market_regime,
            "scanner_contract": {"blockers": []},
            "surface_inventory": {"blockers": []},
            "earnings_calendar": _ready_earnings_calendar(),
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            missing_db = root / "missing.db"
            init_schema(missing_db)
            missing = adapter._build_rows(
                **common,
                cohort={
                    "byte_frozen_policy_snapshot": {
                        "lanes": {
                            "bullish_pullback_observation": {
                                "policy": {"target_dte": 17}
                            }
                        }
                    }
                },
                options_db_path=missing_db,
            )[0]
            full_db = root / "full.db"
            _write_trusted_option_rows(full_db)
            no_executable = adapter._build_rows(
                **common,
                cohort={
                    "byte_frozen_policy_snapshot": {
                        "lanes": {
                            "bullish_pullback_observation": {
                                "policy": {
                                    "target_dte": 17,
                                    "profitability_repair_max_debit_pct_of_width": 1.0,
                                }
                            }
                        }
                    }
                },
                options_db_path=full_db,
            )[0]

        self.assertEqual(
            missing["status"], "blocked_missing_historical_scanner_point_in_time_inputs"
        )
        self.assertFalse(missing["explicit_no_pick"])
        self.assertIn("missing_trusted_entry_quote_surface", missing["blockers"])
        self.assertEqual(no_executable["status"], "explicit_no_pick")
        self.assertEqual(
            no_executable["no_pick_reason"], "no_executable_vertical_spread_candidate"
        )
        self.assertEqual(no_executable["blockers"], [])

    def test_earnings_known_before_actual_quote_decision_blocks_without_midnight_shortcut(
        self,
    ) -> None:
        earnings_index = adapter._earnings_dates_by_symbol(
            {
                "status": "point_in_time_earnings_calendar_ready",
                "earnings_events": [
                    {
                        "symbol": "AAPL",
                        "earnings_date_et": "2026-02-20",
                        "known_at_utc": "2026-02-03T10:11:00-05:00",
                        "source_retrieved_at_utc": "2026-02-03T15:11:00Z",
                    }
                ],
            }
        )
        self.assertIsNone(
            adapter._earnings_within_hold_window(
                earnings_index,
                symbol="AAPL",
                candidate_date=adapter.date(2026, 2, 3),
                dte=35,
                decision_timestamp_utc="2026-02-03T15:10:00Z",
            )
        )
        self.assertEqual(
            adapter._earnings_within_hold_window(
                earnings_index,
                symbol="AAPL",
                candidate_date=adapter.date(2026, 2, 3),
                dte=35,
                decision_timestamp_utc="2026-02-03T15:12:00Z",
            ),
            adapter.date(2026, 2, 20),
        )

    def test_entry_selection_uses_earliest_synchronized_surface_and_exact_mode_is_1010_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_trusted_option_rows(db_path)
            with sqlite3.connect(db_path) as conn:
                for contract, bid, ask in (
                    ("SPY260220C00500000", 3.9, 4.0),
                    ("SPY260220C00505000", 3.0, 3.1),
                ):
                    conn.execute(
                        """
                        INSERT INTO option_quote_snapshots (
                            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                            contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                            underlying_price, volume, open_interest, source_batch_id
                        )
                        SELECT '2026-02-03T15:20:00Z', quote_date_et, 620, snapshot_kind, underlying,
                               contract_symbol, expiry, option_type, strike, ?, ?, last, iv,
                               underlying_price, volume, open_interest, source_batch_id
                        FROM option_quote_snapshots WHERE contract_symbol = ? LIMIT 1
                        """,
                        (bid, ask, contract),
                    )
                conn.commit()
                selected, reason = adapter._select_spread(
                    conn,
                    symbol="SPY",
                    day=adapter.date(2026, 2, 3),
                    direction="call",
                    policy={"target_dte": 17},
                    stock_price=501.0,
                )
                exact, exact_reason = adapter._select_spread(
                    conn,
                    symbol="SPY",
                    day=adapter.date(2026, 2, 3),
                    direction="call",
                    policy={"target_dte": 17},
                    stock_price=501.0,
                    entry_surface_mode=adapter.ENTRY_SURFACE_MODE_EXACT_START,
                )

        self.assertIsNone(reason)
        assert selected is not None
        self.assertEqual(selected["entry_quote_timestamp_utc"], "2026-02-03T15:12:00Z")
        self.assertEqual(
            selected["entry_surface_selection_policy"],
            adapter.ENTRY_SURFACE_MODE_DIAGNOSTIC_WINDOW,
        )
        self.assertIsNone(exact)
        self.assertEqual(exact_reason, "no_trusted_entry_option_quotes")

    def test_daily_materializer_consumes_adapter_blockers_without_inventing_rows(
        self,
    ) -> None:
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
        self.assertIn(
            "missing_historical_scanner_point_in_time_inputs", report["blockers"]
        )
        self.assertIn(
            "underlying_daily_history_source_not_point_in_time", report["blockers"]
        )
        self.assertIn(
            "missing_historical_option_chain_selection_surface", report["blockers"]
        )
        self.assertFalse(
            any(row["proof_safe"] for row in report["daily_candidate_decisions"])
        )

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
            artifacts = adapter.write_outputs(
                report, output_dir=root / "out", docs_report=root / "out" / "latest.md"
            )

            self.assertFalse(report["no_write"])
            self.assertTrue(report["report_artifact_write_performed"])
            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "daily_candidate_decisions.jsonl").exists())
            self.assertTrue(
                artifacts["docs_report"].replace("\\", "/").endswith("/out/latest.md")
            )


if __name__ == "__main__":
    unittest.main()
