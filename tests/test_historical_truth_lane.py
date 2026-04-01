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
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.synthetic_results_path = os.path.join(self._tmp.name, "wfo_results.json")
        self.imported_results_dir = os.path.join(self._tmp.name, "options_validation_runs")
        self.imported_latest_path = os.path.join(self.imported_results_dir, "latest.json")
        self.imported_daily_latest_path = os.path.join(self.imported_results_dir, "latest_daily.json")
        self.historical_db_path = os.path.join(self._tmp.name, "options_history.db")
        self.empty_historical_db_path = os.path.join(self._tmp.name, "options_history_empty.db")
        self.market_data_db_path = os.path.join(self._tmp.name, "market_data.db")
        self.csv_path = os.path.join(self._tmp.name, "historical_quotes.csv")
        self.daily_parquet_path = os.path.join(self._tmp.name, "spy_options.parquet")
        self.daily_underlying_path = os.path.join(self._tmp.name, "spy_underlying.parquet")
        self.histories = {
            "SPY": make_validation_history(length=140, start=500.0, step=0.7),
            "QQQ": make_validation_history(length=140, start=420.0, step=0.8),
        }
        write_historical_options_csv(self.csv_path, self.histories, strike_span=12)
        import_historical_option_snapshots(self.csv_path, "trusted_intraday", db_path=self.historical_db_path)

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.market_data_db_path}, clear=False))
        self.stack.enter_context(patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": self.historical_db_path}, clear=False))
        self.stack.enter_context(patch.object(wfo, "DEFAULT_WATCHLIST", ["SPY", "QQQ"]))
        self.stack.enter_context(patch.object(wfo, "IMPORTED_VALIDATION_UNIVERSE", ("SPY", "QQQ")))
        self.stack.enter_context(patch.object(wfo, "WFO_RESULTS_FILE", self.synthetic_results_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", self.imported_results_dir))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", self.imported_latest_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_DAILY_LATEST_FILE", self.imported_daily_latest_path))
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


if __name__ == "__main__":
    unittest.main()
