import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import market_data_service as mds
import numpy as np
import pandas as pd
import wfo_optimizer as wfo

from forward_options_ledger import record_forward_snapshot
from historical_options_store import HistoricalOptionsStore, import_historical_option_snapshots

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from historical_options_fixtures import (
    make_historical_replay_ticker_factory,
    make_validation_history,
    write_daily_options_parquet,
    write_historical_options_csv,
    write_underlying_daily_parquet,
)
from options_algorithm_fixtures import FrozenDateTime


class HistoricalTruthLaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._shared_tmp = tempfile.TemporaryDirectory()
        shared_root = Path(cls._shared_tmp.name)
        cls.csv_path = str(shared_root / "historical_quotes.csv")
        cls.historical_db_path = str(shared_root / "options_history.db")
        cls.histories = {
            "SPY": make_validation_history(length=140, start=500.0, step=0.7),
            "QQQ": make_validation_history(length=140, start=420.0, step=0.8),
        }
        write_historical_options_csv(cls.csv_path, cls.histories, strike_span=12)
        import_historical_option_snapshots(cls.csv_path, "trusted_intraday", db_path=cls.historical_db_path)

    @classmethod
    def tearDownClass(cls):
        cls._shared_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.synthetic_results_path = os.path.join(self._tmp.name, "wfo_results.json")
        self.imported_results_dir = os.path.join(self._tmp.name, "options_validation_runs")
        self.imported_latest_path = os.path.join(self.imported_results_dir, "latest.json")
        self.imported_daily_latest_path = os.path.join(self.imported_results_dir, "latest_daily.json")
        self.imported_daily_forward_latest_path = os.path.join(self.imported_results_dir, "latest_daily_forward.json")
        self.historical_db_path = type(self).historical_db_path
        self.empty_historical_db_path = os.path.join(self._tmp.name, "options_history_empty.db")
        self.market_data_db_path = os.path.join(self._tmp.name, "market_data.db")
        self.forward_ledger_db_path = os.path.join(self._tmp.name, "forward_tracking.db")
        self.daily_parquet_path = os.path.join(self._tmp.name, "spy_options.parquet")
        self.daily_underlying_path = os.path.join(self._tmp.name, "spy_underlying.parquet")
        self.csv_path = type(self).csv_path
        self.histories = type(self).histories

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.market_data_db_path}, clear=False))
        self.stack.enter_context(patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": self.historical_db_path}, clear=False))
        self.stack.enter_context(patch.dict(os.environ, {"FORWARD_OPTIONS_LEDGER_DB_PATH": self.forward_ledger_db_path}, clear=False))
        self.stack.enter_context(patch.object(wfo, "DEFAULT_WATCHLIST", ["SPY", "QQQ"]))
        self.stack.enter_context(patch.object(wfo, "IMPORTED_VALIDATION_UNIVERSE", ("SPY", "QQQ")))
        self.stack.enter_context(patch.object(wfo, "WFO_RESULTS_FILE", self.synthetic_results_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", self.imported_results_dir))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", self.imported_latest_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_DAILY_LATEST_FILE", self.imported_daily_latest_path))
        self.stack.enter_context(
            patch.object(wfo, "OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE", self.imported_daily_forward_latest_path)
        )
        self.stack.enter_context(patch.object(wfo.yf, "Ticker", side_effect=make_historical_replay_ticker_factory(self.histories)))
        self.stack.enter_context(patch.object(mds.yf, "Ticker", side_effect=make_historical_replay_ticker_factory(self.histories)))
        self.stack.enter_context(patch.object(wfo, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(mds, "datetime", FrozenDateTime))
        self.stack.enter_context(
            patch.object(
                wfo,
                "_resolve_replay_entry_signal",
                return_value={"trade_type": "call", "signal_family": "momentum"},
            )
        )
        self.stack.enter_context(patch.object(wfo, "_compute_direction_score", return_value=82.0))
        self.stack.enter_context(patch.object(wfo, "_compute_quality_score", return_value=76.0))
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()

    def test_imported_backtest_emits_coverage_metadata_and_comparison(self):
        synthetic = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            pricing_lane="pessimistic",
            truth_lane="synthetic",
        )
        imported = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            truth_lane="historical_imported",
        )

        self.assertEqual(synthetic["truth_source"], wfo.SYNTHETIC_TRUTH_SOURCE)
        self.assertEqual(imported["truth_source"], wfo.IMPORTED_TRUTH_SOURCE)
        self.assertEqual(imported["pricing_lane"], wfo.IMPORTED_TRUTH_SOURCE)
        self.assertIn("priced_trade_count", imported)
        self.assertIn("unpriced_trade_count", imported)
        self.assertIn("quote_coverage_pct", imported)
        self.assertIn("contract_resolution_counts", imported)
        self.assertIn("exact_contract_match_count", imported)
        self.assertIn("nearest_contract_match_count", imported)
        self.assertIn("truth_store", imported)
        self.assertGreater(imported["truth_store"]["quote_count"], 0)
        self.assertGreater(imported["priced_trade_count"], 0)
        self.assertGreater(imported["quote_coverage_pct"], 0.0)
        self.assertTrue(os.path.exists(self.imported_latest_path))

        comparison = wfo.build_truth_lane_comparison()
        self.assertIn("deltas", comparison)
        self.assertEqual(comparison["imported"]["truth_source"], wfo.IMPORTED_TRUTH_SOURCE)
        self.assertIn("unsupported_by_import_count", comparison)

    def test_live_policy_prefers_imported_truth_when_present(self):
        wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            pricing_lane="pessimistic",
            truth_lane="synthetic",
        )
        imported = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            truth_lane="historical_imported",
        )

        policy = wfo.build_live_options_trade_policy(min_trades=1)
        self.assertEqual(policy["truth_source"], wfo.IMPORTED_TRUTH_SOURCE)
        self.assertFalse(policy["synthetic_only"])
        self.assertEqual(policy["quote_coverage_pct"], imported["quote_coverage_pct"])

        synthetic_policy = wfo.build_live_options_trade_policy(
            result=wfo.load_last_synthetic_results(),
            min_trades=1,
        )
        self.assertTrue(synthetic_policy["synthetic_only"])
        self.assertEqual(synthetic_policy["truth_source"], wfo.SYNTHETIC_TRUTH_SOURCE)

    def test_fixture_imports_do_not_count_as_trusted_validation(self):
        fixture_db_path = os.path.join(self._tmp.name, "options_history_fixture.db")
        import_historical_option_snapshots(self.csv_path, "acceptance_fixture", db_path=fixture_db_path)

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": fixture_db_path}, clear=False):
            imported = wfo.run_historical_backtest(
                lookback_years=1,
                n_picks=1,
                iv_adj=1.0,
                truth_lane="historical_imported",
            )
            self.assertIn("error", imported)
            self.assertIn("trusted imported historical option data", imported["error"])
            self.assertIsNone(wfo.load_last_imported_results())

    def test_daily_imported_backtest_is_supported_and_stays_watch_only(self):
        daily_db_path = os.path.join(self._tmp.name, "options_history_daily.db")
        write_daily_options_parquet(self.daily_parquet_path, self.histories, symbol="SPY", strike_span=12)
        write_daily_options_parquet(
            os.path.join(self._tmp.name, "qqq_options.parquet"),
            self.histories,
            symbol="QQQ",
            strike_span=12,
        )
        write_underlying_daily_parquet(self.daily_underlying_path, self.histories, symbol="SPY")
        write_underlying_daily_parquet(
            os.path.join(self._tmp.name, "qqq_underlying.parquet"),
            self.histories,
            symbol="QQQ",
        )
        from historical_options_store import import_daily_option_parquet

        import_daily_option_parquet(
            self.daily_parquet_path,
            "spy-daily",
            underlying="SPY",
            underlying_input=self.daily_underlying_path,
            db_path=daily_db_path,
        )
        import_daily_option_parquet(
            os.path.join(self._tmp.name, "qqq_options.parquet"),
            "qqq-daily",
            underlying="QQQ",
            underlying_input=os.path.join(self._tmp.name, "qqq_underlying.parquet"),
            db_path=daily_db_path,
        )
        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": daily_db_path}, clear=False):
            imported = wfo.run_historical_backtest(
                lookback_years=1,
                n_picks=1,
                iv_adj=1.0,
                truth_lane="historical_imported_daily",
            )
        self.assertEqual(imported["truth_source"], "historical_imported_daily")
        self.assertEqual(imported["pricing_lane"], "historical_imported_daily")
        self.assertEqual(imported["entry_quote_time_et"], "End-of-day snapshot ET")
        self.assertGreater(imported["quote_coverage_pct"], 0.0)
        self.assertIn("contract_resolution_counts", imported)
        self.assertIn("exact_contract_metrics", imported)
        self.assertIn("nearest_listed_metrics", imported)
        self.assertIn("promotion_metrics", imported)
        self.assertIn("by_symbol", imported)
        self.assertTrue(os.path.exists(self.imported_daily_latest_path))

        policy = wfo.build_live_options_trade_policy(
            result=imported,
            min_trades=1,
        )
        self.assertEqual(policy["truth_source"], "historical_imported_daily")
        self.assertIn(policy["promotion_status"], {"watch", "block"})
        self.assertNotEqual(policy["promotion_status"], "promote")
        self.assertIn("by_symbol", policy)
        self.assertIn("promotion_metrics", policy)

    def test_imported_outcome_prefers_archived_exact_contract_when_present(self):
        store = HistoricalOptionsStore(self.historical_db_path)
        dates = self.histories["SPY"].index
        prices = self.histories["SPY"]["Close"].to_numpy(dtype=float)
        entry_idx = 60
        entry_date = pd.Timestamp(dates[entry_idx]).date()
        archived_quote = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=entry_date,
            option_type="call",
            target_expiry=entry_date + pd.Timedelta(days=10),
            target_strike=float(prices[entry_idx]),
            snapshot_kind=wfo.INTRADAY_SNAPSHOT_KIND,
            allow_last_price=False,
        )
        self.assertIsNotNone(archived_quote)

        with patch.object(wfo, "_select_target_contract", return_value=(None, None)):
            outcome = wfo._simulate_trade_outcome_imported(
                store=store,
                ticker="SPY",
                dates=dates,
                prices=prices,
                i=entry_idx,
                trade_type="call",
                hv30=0.20,
                delta_target=0.30,
                dte_at_entry=10,
                stop_loss_pct=45.0,
                profit_target_pct=100.0,
                time_exit_pct=50.0,
                trailing_profit_pct=40.0,
                trailing_giveback_pct=50.0,
                _rsi14=np.full(len(prices), 55.0),
                _macd=np.full(len(prices), 0.2),
                _sma20=np.full(len(prices), float(prices[entry_idx] - 2.0)),
                _sma50=np.full(len(prices), float(prices[entry_idx] - 4.0)),
                tech_at_entry=80.0,
                entry_S0=float(prices[entry_idx]),
                iv_adj=1.0,
                truth_source=wfo.IMPORTED_TRUTH_SOURCE,
                snapshot_kind=wfo.INTRADAY_SNAPSHOT_KIND,
                archived_contract_symbol=archived_quote.contract_symbol,
                archived_expiry=archived_quote.expiry,
                archived_strike=archived_quote.strike,
                archived_option_type=archived_quote.option_type,
                archived_quote_basis=archived_quote.price_basis,
                archived_underlying_price_at_selection=float(prices[entry_idx]),
                archived_selection_source="live_chain_exact_contract",
            )

        self.assertTrue(outcome["priced"])
        self.assertEqual(outcome["entry_contract_resolution"], "exact_archived_contract")
        self.assertEqual(outcome["contract_symbol"], archived_quote.contract_symbol)

    def test_imported_outcome_falls_back_to_model_target_when_archived_contract_missing(self):
        store = HistoricalOptionsStore(self.historical_db_path)
        dates = self.histories["SPY"].index
        prices = self.histories["SPY"]["Close"].to_numpy(dtype=float)
        entry_idx = 60
        entry_date = pd.Timestamp(dates[entry_idx]).date()
        model_quote = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=entry_date,
            option_type="call",
            target_expiry=entry_date + pd.Timedelta(days=10),
            target_strike=float(prices[entry_idx]),
            snapshot_kind=wfo.INTRADAY_SNAPSHOT_KIND,
            allow_last_price=False,
        )
        self.assertIsNotNone(model_quote)
        dte_at_entry = (pd.Timestamp(model_quote.expiry).date() - entry_date).days

        with patch.object(
            wfo,
            "_select_target_contract",
            return_value=(float(model_quote.strike), {"delta": 0.30}),
        ):
            outcome = wfo._simulate_trade_outcome_imported(
                store=store,
                ticker="SPY",
                dates=dates,
                prices=prices,
                i=entry_idx,
                trade_type="call",
                hv30=0.20,
                delta_target=0.30,
                dte_at_entry=dte_at_entry,
                stop_loss_pct=45.0,
                profit_target_pct=100.0,
                time_exit_pct=50.0,
                trailing_profit_pct=40.0,
                trailing_giveback_pct=50.0,
                _rsi14=np.full(len(prices), 55.0),
                _macd=np.full(len(prices), 0.2),
                _sma20=np.full(len(prices), float(prices[entry_idx] - 2.0)),
                _sma50=np.full(len(prices), float(prices[entry_idx] - 4.0)),
                tech_at_entry=80.0,
                entry_S0=float(prices[entry_idx]),
                iv_adj=1.0,
                truth_source=wfo.IMPORTED_TRUTH_SOURCE,
                snapshot_kind=wfo.INTRADAY_SNAPSHOT_KIND,
                archived_contract_symbol="SPY999999C00000000",
                archived_expiry=model_quote.expiry,
                archived_strike=model_quote.strike,
                archived_option_type=model_quote.option_type,
                archived_quote_basis=model_quote.price_basis,
                archived_underlying_price_at_selection=float(prices[entry_idx]),
                archived_selection_source="live_chain_exact_contract",
            )

        self.assertTrue(outcome["priced"])
        self.assertEqual(outcome["entry_contract_resolution"], "exact_target_contract")
        self.assertEqual(outcome["contract_selection_source"], "model_target_contract")
        self.assertEqual(outcome["requested_contract_symbol"], "SPY999999C00000000")

    def test_imported_artifact_is_ignored_when_backing_store_is_missing(self):
        imported = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            truth_lane="historical_imported",
        )
        self.assertEqual(imported["truth_source"], wfo.IMPORTED_TRUTH_SOURCE)
        self.assertIsNotNone(wfo.load_last_results_by_truth_lane("historical_imported"))

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": self.empty_historical_db_path}, clear=False):
            self.assertIsNone(wfo.load_last_results_by_truth_lane("historical_imported"))

    def test_truth_lane_health_summary_reports_store_mismatch_and_missing_store(self):
        imported = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=1,
            iv_adj=1.0,
            truth_lane="historical_imported",
        )
        self.assertEqual(imported["truth_source"], wfo.IMPORTED_TRUTH_SOURCE)

        healthy = wfo.build_truth_lane_health_summary()
        self.assertEqual(healthy["historical_imported"]["status"], "loadable")
        self.assertTrue(healthy["historical_imported"]["loadable"])
        self.assertEqual(healthy["default_selected_truth_source"], wfo.IMPORTED_TRUTH_SOURCE)

        stale_payload = dict(imported)
        stale_store = dict(stale_payload.get("truth_store") or {})
        stale_store["quote_count"] = int(stale_store.get("quote_count", 0) or 0) + 1
        stale_payload["truth_store"] = stale_store
        with open(self.imported_latest_path, "w", encoding="utf8") as handle:
            import json

            json.dump(stale_payload, handle, indent=2)

        mismatched = wfo.build_truth_lane_health_summary()
        self.assertEqual(mismatched["historical_imported"]["status"], "store_mismatch")
        self.assertFalse(mismatched["historical_imported"]["loadable"])
        self.assertEqual(mismatched["historical_imported"]["rejection_reason"], "store_mismatch")

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": self.empty_historical_db_path}, clear=False):
            missing_store = wfo.build_truth_lane_health_summary()
        self.assertEqual(missing_store["historical_imported"]["status"], "missing_current_store")
        self.assertFalse(missing_store["historical_imported"]["loadable"])
        self.assertEqual(
            missing_store["historical_imported"]["rejection_reason"],
            "missing_current_store",
        )

    def test_daily_imported_backtest_uses_trusted_benchmark_quote_calendar_without_hiding_peer_gaps(self):
        daily_db_path = os.path.join(self._tmp.name, "options_history_daily_calendar.db")
        spy_path = os.path.join(self._tmp.name, "spy_calendar.parquet")
        qqq_path = os.path.join(self._tmp.name, "qqq_calendar.parquet")
        write_daily_options_parquet(spy_path, self.histories, symbol="SPY", strike_span=12)
        write_daily_options_parquet(qqq_path, self.histories, symbol="QQQ", strike_span=12)

        missing_date = str(pd.Timestamp(self.histories["QQQ"].index[57]).date())
        qqq_frame = pd.read_parquet(qqq_path)
        qqq_frame = qqq_frame.loc[qqq_frame["date"] != missing_date].copy()
        qqq_frame.to_parquet(qqq_path, index=False)

        from historical_options_store import import_daily_option_parquet

        import_daily_option_parquet(spy_path, "spy-daily-calendar", underlying="SPY", db_path=daily_db_path)
        import_daily_option_parquet(qqq_path, "qqq-daily-calendar", underlying="QQQ", db_path=daily_db_path)

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": daily_db_path}, clear=False), \
             patch.object(wfo, "_tech_score", return_value=80.0), \
             patch.object(
                 wfo,
                 "_pick_top_n_daily",
                 side_effect=lambda candidates, n: (
                     [candidate for candidate in candidates if candidate["ticker"] == "QQQ"][:n]
                     or candidates[:n]
                 ),
             ):
            imported = wfo.run_historical_backtest(
                lookback_years=1,
                n_picks=1,
                iv_adj=1.0,
                truth_lane="historical_imported_daily",
            )

        unpriced_dates = {
            str(item.get("date"))
            for item in (imported.get("unpriced_trades") or [])
            if str(item.get("date") or "").strip()
        }
        self.assertEqual(imported["replay_calendar"]["source"], "trusted_imported_benchmark_quote_dates")
        self.assertEqual(imported["replay_calendar"]["benchmark_underlying"], "SPY")
        self.assertEqual(imported["replay_calendar"]["calendar_gap_date_count"], 1)
        self.assertIn(missing_date, unpriced_dates)
        self.assertEqual(
            imported["unpriced_trade_diagnostics"]["reason_counts"].get("missing_entry_quote"),
            1,
        )

    def test_daily_imported_backtest_emits_missing_quote_diagnostics_summary(self):
        daily_db_path = os.path.join(self._tmp.name, "options_history_daily_diagnostics.db")
        write_daily_options_parquet(self.daily_parquet_path, self.histories, symbol="SPY", strike_span=12)
        write_daily_options_parquet(
            os.path.join(self._tmp.name, "qqq_options_diag.parquet"),
            self.histories,
            symbol="QQQ",
            strike_span=12,
        )

        from historical_options_store import import_daily_option_parquet

        import_daily_option_parquet(
            self.daily_parquet_path,
            "spy-daily-diagnostics",
            underlying="SPY",
            db_path=daily_db_path,
        )
        import_daily_option_parquet(
            os.path.join(self._tmp.name, "qqq_options_diag.parquet"),
            "qqq-daily-diagnostics",
            underlying="QQQ",
            db_path=daily_db_path,
        )

        call_count = {"value": 0}

        def fake_imported_outcome(**kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                return {
                    "priced": False,
                    "unpriced_reason": "missing_entry_quote",
                    "entry_day_idx": kwargs["i"],
                    "truth_source": "historical_imported_daily",
                    "pricing_lane": "historical_imported_daily",
                    "target_strike": 530.0,
                    "target_expiry": "2024-07-10",
                }
            if call_count["value"] == 2:
                return {
                    "priced": False,
                    "unpriced_reason": "missing_exit_quote",
                    "entry_day_idx": kwargs["i"],
                    "truth_source": "historical_imported_daily",
                    "pricing_lane": "historical_imported_daily",
                    "contract_symbol": "SPY240712C00550000",
                    "missing_quote_date": "2024-07-04",
                    "entry_quote_at_utc": "2024-06-24T19:55:00Z",
                    "entry_quote_basis": "mid",
                    "entry_quote_time_et": "End-of-day snapshot ET",
                    "target_strike": 550.0,
                    "target_expiry": "2024-07-15",
                    "entry_contract_resolution": "nearest_listed_contract",
                }
            return {
                "priced": True,
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0,
                "exit_reason": "target",
                "exit_fill_basis": "historical_mid",
                "strike": 100.0,
                "delta_val": 0.3,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": kwargs["hv30"],
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": "historical_imported_daily",
                "contract_symbol": "SPY240712C00550000",
                "entry_contract_resolution": "exact_target_contract",
                "entry_quote_at_utc": "2024-06-24T19:55:00Z",
                "entry_quote_basis": "mid",
                "entry_quote_time_et": "End-of-day snapshot ET",
                "exit_quote_at_utc": "2024-06-25T19:55:00Z",
                "exit_quote_basis": "mid",
                "exit_quote_time_et": "End-of-day snapshot each trading day ET",
            }

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": daily_db_path}, clear=False), \
             patch.object(wfo, "_tech_score", return_value=80.0), \
             patch.object(wfo, "_simulate_trade_outcome_imported", side_effect=fake_imported_outcome):
            imported = wfo.run_historical_backtest(
                lookback_years=1,
                n_picks=1,
                iv_adj=1.0,
                truth_lane="historical_imported_daily",
            )

        diagnostics = imported["unpriced_trade_diagnostics"]
        self.assertEqual(
            diagnostics["reason_counts"],
            {"missing_entry_quote": 1, "missing_exit_quote": 1},
        )
        self.assertEqual(
            diagnostics["entry_contract_resolution_counts"],
            {"nearest_listed_contract": 1},
        )
        self.assertEqual(
            diagnostics["top_missing_quote_dates"],
            [{"date": "2024-07-04", "count": 1}],
        )

    def test_archived_forward_daily_backtest_returns_clean_insufficient_result_without_scan_picks(self):
        result = wfo.run_archived_forward_daily_backtest()

        self.assertTrue(result["insufficient_archived_evidence"])
        self.assertEqual(result["status"], "insufficient_archived_evidence")
        self.assertEqual(result["insufficient_reason"], "no_archived_scan_pick_events")
        self.assertEqual(result["candidate_source"], wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE)
        self.assertEqual(result["primary_judge_trade_class"], wfo.PRIMARY_JUDGE_TRADE_CLASS)
        self.assertEqual(result["evidence_status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)
        self.assertEqual(result["archived_sample_date_coverage"]["entry_date_count"], 0)
        self.assertFalse(os.path.exists(self.imported_daily_forward_latest_path))

    def test_archived_forward_daily_backtest_marks_future_live_picks_as_pending_truth_horizon(self):
        daily_db_path = os.path.join(self._tmp.name, "options_history_daily_pending.db")
        spy_path = os.path.join(self._tmp.name, "spy_pending.parquet")
        write_daily_options_parquet(spy_path, self.histories, symbol="SPY", strike_span=12)

        from historical_options_store import import_daily_option_parquet

        import_daily_option_parquet(spy_path, "spy-daily-pending", underlying="SPY", db_path=daily_db_path)

        record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "option_type": "call",
                        "contract_symbol": "SPY260415C00560000",
                        "expiry": "2026-04-15",
                        "strike": 560.0,
                        "dte": 7,
                        "quote_time_et": "2026-04-08",
                        "quote_basis": "mid",
                        "underlying_price_at_selection": 550.0,
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "research_bootstrap",
                        "candidate_rank": 1,
                        "entry_date": "2026-04-08",
                    }
                ],
                "evidence_class": "live_production",
                "is_fixture": False,
                "run_mode": "live",
                "policy_applied": True,
                "policy": {
                    "truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="api_scan_auto",
            db_path=self.forward_ledger_db_path,
        )

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": daily_db_path}, clear=False):
            result = wfo.run_archived_forward_daily_backtest()

        self.assertTrue(result["insufficient_archived_evidence"])
        self.assertEqual(result["insufficient_reason"], "pending_truth_horizon_only")
        self.assertEqual(result["truth_window_status"], "stale")
        self.assertEqual(result["authoritative_evidence_source"], "archived_forward_daily")
        self.assertEqual(result["authoritative_evidence_status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)
        self.assertEqual(result["pending_truth_horizon_count"], 1)
        self.assertEqual(len(result["pending_truth_horizon_trades"]), 1)
        self.assertEqual(
            result["pending_truth_horizon_trades"][0]["pending_reason"],
            "entry_date_beyond_trusted_truth_horizon",
        )
        self.assertEqual(result["unpriced_trade_count"], 0)
        self.assertTrue(os.path.exists(self.imported_daily_forward_latest_path))

    def test_archived_forward_daily_backtest_writes_separate_truth_artifact_with_fallback_provenance(self):
        daily_db_path = os.path.join(self._tmp.name, "options_history_daily_forward.db")
        spy_path = os.path.join(self._tmp.name, "spy_forward.parquet")
        write_daily_options_parquet(spy_path, self.histories, symbol="SPY", strike_span=12)

        from historical_options_store import import_daily_option_parquet

        import_daily_option_parquet(spy_path, "spy-daily-forward", underlying="SPY", db_path=daily_db_path)
        daily_store = HistoricalOptionsStore(daily_db_path)
        entry_idx = 60
        entry_date = pd.Timestamp(self.histories["SPY"].index[entry_idx]).date()
        entry_price = float(self.histories["SPY"]["Close"].iloc[entry_idx])
        daily_frame = pd.read_parquet(spy_path)
        future_dates = [
            pd.Timestamp(self.histories["SPY"].index[entry_idx + offset]).date().isoformat()
            for offset in range(0, 5)
        ]
        common_contracts = None
        for future_date in future_dates:
            contract_ids = set(
                daily_frame.loc[daily_frame["date"] == future_date, "contract_id"].astype(str)
            )
            common_contracts = contract_ids if common_contracts is None else (common_contracts & contract_ids)
        target_row = daily_frame.loc[
            (daily_frame["date"] == entry_date.isoformat())
            & (daily_frame["type"] == "call")
            & (daily_frame["contract_id"].astype(str).isin(sorted(common_contracts or set())))
            & ((pd.to_datetime(daily_frame["expiration"]) - pd.Timestamp(entry_date)).dt.days >= 7)
        ].iloc[0]
        target_quote = type(
            "Quote",
            (),
            {
                "contract_symbol": str(target_row["contract_id"]),
                "expiry": str(target_row["expiration"]),
                "strike": float(target_row["strike"]),
            },
        )()
        dte_at_entry = (pd.Timestamp(target_quote.expiry).date() - entry_date).days

        record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "option_type": "call",
                        "contract_symbol": target_quote.contract_symbol,
                        "expiry": target_quote.expiry,
                        "strike": float(target_quote.strike),
                        "dte": dte_at_entry,
                        "quote_time_et": entry_date.isoformat(),
                        "quote_basis": "eod",
                        "underlying_price_at_selection": entry_price,
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "candidate_rank": 1,
                        "direction_score": 80.0,
                        "quality_score": 75.0,
                        "tech_score": 78.0,
                        "delta": 0.30,
                        "stop_loss_pct": 45.0,
                        "profit_target_pct": 100.0,
                        "time_exit_pct": 50.0,
                        "entry_date": entry_date.isoformat(),
                    },
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "option_type": "call",
                        "contract_symbol": "SPY_MISSING_ARCHIVED",
                        "expiry": target_quote.expiry,
                        "strike": float(target_quote.strike),
                        "dte": dte_at_entry,
                        "quote_time_et": entry_date.isoformat(),
                        "quote_basis": "eod",
                        "underlying_price_at_selection": entry_price,
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "candidate_rank": 2,
                        "direction_score": 79.0,
                        "quality_score": 74.0,
                        "tech_score": 77.0,
                        "delta": 0.30,
                        "stop_loss_pct": 45.0,
                        "profit_target_pct": 100.0,
                        "time_exit_pct": 50.0,
                        "entry_date": entry_date.isoformat(),
                    },
                ],
                "policy_applied": True,
                "policy": {"truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE, "promotion_status": "watch"},
                "playbook": {"id": "short_term"},
                "scan_funnel": {
                    "raw_candidates": 2,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 2,
                    "returned_picks": 2,
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="api_scan_auto",
            db_path=self.forward_ledger_db_path,
        )

        def _fake_archived_forward_outcome(**kwargs):
            resolution = (
                "exact_archived_contract"
                if kwargs.get("archived_contract_symbol") == target_quote.contract_symbol
                else "exact_target_contract"
            )
            return {
                "priced": True,
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0 if resolution == "exact_archived_contract" else 10.0,
                "exit_reason": "target",
                "exit_fill_basis": "historical_mid",
                "strike": float(target_quote.strike),
                "delta_val": 0.30,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": kwargs["hv30"],
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": "historical_imported_daily",
                "contract_symbol": target_quote.contract_symbol,
                "entry_contract_resolution": resolution,
                "contract_selection_source": (
                    "archived_exact_contract"
                    if resolution == "exact_archived_contract"
                    else "model_target_contract"
                ),
                "entry_quote_at_utc": "2025-12-10T20:55:00Z",
                "entry_quote_basis": "mid",
                "entry_quote_time_et": "End-of-day snapshot ET",
                "exit_quote_at_utc": "2025-12-11T20:55:00Z",
                "exit_quote_basis": "mid",
                "exit_quote_time_et": "End-of-day snapshot each trading day ET",
            }

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": daily_db_path}, clear=False), patch.object(
            wfo,
            "_simulate_trade_outcome_imported",
            side_effect=_fake_archived_forward_outcome,
        ):
            result = wfo.run_archived_forward_daily_backtest()

        self.assertEqual(result["candidate_source"], wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE)
        self.assertEqual(result["primary_judge_trade_class"], "exact_archived_contract")
        self.assertEqual(result["evidence_status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)
        self.assertEqual(result["archived_exact_contract_metrics"]["trade_count"], 1)
        self.assertEqual(result["model_exact_contract_metrics"]["trade_count"], 1)
        self.assertTrue(result["primary_judge_fallback_used"])
        self.assertEqual(result["primary_judge_fallback_reason"], "missing_archived_contract_quote")
        self.assertEqual(result["archived_sample_date_coverage"]["entry_date_count"], 1)
        self.assertEqual(result["archived_sample_date_coverage"]["source_label"], "api_scan_auto")
        self.assertTrue(os.path.exists(self.imported_daily_forward_latest_path))


if __name__ == "__main__":
    unittest.main()
