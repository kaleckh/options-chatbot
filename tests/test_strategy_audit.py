import copy
import json
import os
import tempfile
import unittest
from datetime import datetime as _RealDateTime
from unittest.mock import patch

import numpy as np
import pandas as pd

import expectancy_calibration as ec
import market_data_service as mds
import options_chatbot as oc
import options_profitability_forensics as opf
import supervised_scan as ss
import wfo_optimizer as wfo


def _make_close_history(length: int, start: float = 100.0, volume: float = 8_000_000) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=length, freq="B")
    closes = [start + i for i in range(length)]
    opens = [price - 0.5 for price in closes]
    volumes = [float(volume)] * length
    return pd.DataFrame({"Open": opens, "Close": closes, "Volume": volumes}, index=dates)


def _make_calibration_trade(
    *,
    pnl_pct: float,
    market_regime: str = "bullish",
    trade_type: str = "call",
    direction_score: float = 75.0,
    quality_score: float = 65.0,
    tech_score: float = 70.0,
    directional_correct: bool = True,
    exit_day_idx: int = 1,
) -> dict:
    return {
        "market_regime": market_regime,
        "type": trade_type,
        "direction_score": direction_score,
        "quality_score": quality_score,
        "tech_score": tech_score,
        "pnl_pct": pnl_pct,
        "directional_correct": directional_correct,
        "exit_day_idx": exit_day_idx,
    }


class _ScanTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.info = {"sector": "Technology"}
        self.earnings_dates = pd.DataFrame()

    def history(self, period="90d", start=None, end=None, interval=None):
        return _make_close_history(320, 100.0 if self.symbol != "SPY" else 400.0)


class _BacktestTicker:
    def __init__(self, symbol: str, histories: dict[str, pd.DataFrame]):
        self.symbol = symbol
        self._histories = histories
        self.info = {"sector": "Technology"}

    def history(self, period="90d", start=None, end=None, interval=None):
        return self._histories[self.symbol].copy()


class _CountingScanTicker(_ScanTicker):
    def __init__(self, symbol: str):
        super().__init__(symbol)
        self.history_calls: list[tuple[str | None, str | None, str | None, str | None]] = []
        self.info_calls = 0

    @property
    def info(self):
        self.info_calls += 1
        return self._info_payload

    @info.setter
    def info(self, value):
        self._info_payload = value

    def history(self, period="90d", start=None, end=None, interval=None):
        self.history_calls.append((period, str(start), str(end), interval))
        return super().history(period=period, start=start, end=end, interval=interval)


class _CountingBacktestTicker(_BacktestTicker):
    def __init__(self, symbol: str, histories: dict[str, pd.DataFrame]):
        super().__init__(symbol, histories)
        self.history_calls: list[tuple[str | None, str | None, str | None, str | None]] = []
        self.info_calls = 0

    @property
    def info(self):
        self.info_calls += 1
        return self._info_payload

    @info.setter
    def info(self, value):
        self._info_payload = value

    def history(self, period="90d", start=None, end=None, interval=None):
        self.history_calls.append((period, str(start), str(end), interval))
        return super().history(period=period, start=start, end=end, interval=interval)


class _StrategyAuditDateTime(_RealDateTime):
    @classmethod
    def now(cls, tz=None):
        base = _RealDateTime(2025, 3, 24, 12, 0, 0)
        if tz is None:
            return cls(base.year, base.month, base.day, base.hour, base.minute, base.second)
        aware = base.replace(tzinfo=tz)
        return cls(
            aware.year,
            aware.month,
            aware.day,
            aware.hour,
            aware.minute,
            aware.second,
            aware.microsecond,
            tzinfo=aware.tzinfo,
        )


class StrategyAuditTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.market_data_db_path = os.path.join(self._tmp.name, "market_data.db")
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()
        self._env_patch = patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.market_data_db_path}, clear=False)
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        self._md_datetime_patch = patch.object(mds, "datetime", _StrategyAuditDateTime)
        self._md_datetime_patch.start()
        self.addCleanup(self._md_datetime_patch.stop)
        self._expectancy_surface_patch = patch.object(oc, "_load_expectancy_surface_for_live", return_value=None)
        self._expectancy_surface_patch.start()
        self.addCleanup(self._expectancy_surface_patch.stop)

    def test_calculate_position_size_uses_risk_bands_and_fails_closed_when_one_contract_is_too_large(self):
        with patch.dict(
            oc.risk_settings,
            {
                "account_size": 10_000.0,
                "min_position_pct": 0.5,
                "max_position_pct": 3.0,
                "dte_0_max_pct": 0.5,
                "stop_loss_pct": 50.0,
                "max_drawdown_pct": 20.0,
            },
            clear=False,
        ):
            oversized = json.loads(oc.calculate_position_size(option_price=1.0, confidence=1, dte=7))
            sized = json.loads(oc.calculate_position_size(option_price=2.0, confidence=10, dte=7))

        self.assertEqual(oversized["error"], "Trade exceeds the current risk budget.")
        self.assertEqual(oversized["confidence_sizing"]["risk_pct_applied"], 0.5)
        self.assertEqual(sized["confidence_sizing"]["risk_pct_applied"], 3.0)
        self.assertEqual(sized["sizing"]["max_contracts"], 1)
        self.assertEqual(sized["sizing"]["max_loss_if_zero"], 200.0)

    def test_replay_time_exit_does_not_capture_beyond_profit_target(self):
        prices = np.array([100.0, 100.0, 100.0, 100.0, 100.0], dtype=float)
        rsi = np.full(len(prices), 50.0)
        macd = np.zeros(len(prices))
        sma = np.full(len(prices), 100.0)

        def fake_bs_greeks(S, K, T, r, vol, trade_type):
            price_map = {
                round(4 / 365.0, 6): 1.0,
                round(3 / 365.0, 6): 1.2,
                round(2 / 365.0, 6): 2.4,
                round(1 / 365.0, 6): 2.6,
            }
            return {"delta": 0.30, "bs_price": price_map.get(round(T, 6), 1.0)}

        with patch.object(wfo, "_market_strike_grid", return_value=[100.0]), \
             patch.object(wfo, "_bs_greeks", side_effect=fake_bs_greeks):
            outcome = wfo._simulate_trade_outcome_hist(
                prices=prices,
                i=0,
                trade_type="call",
                hv30=0.2,
                delta_target=0.30,
                dte_at_entry=4,
                stop_loss_pct=50.0,
                profit_target_pct=100.0,
                time_exit_pct=50.0,
                trailing_profit_pct=40.0,
                trailing_giveback_pct=50.0,
                _rsi14=rsi,
                _macd=macd,
                _sma20=sma,
                _sma50=sma,
                tech_at_entry=80.0,
                entry_S0=100.0,
                iv_adj=1.2,
                pricing_lane="mid",
            )

        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["exit_reason"], "target")
        self.assertEqual(outcome["exit_fill_basis"], "target_limit")
        self.assertEqual(outcome["exit_px"], 2.0)

    def test_replay_trailing_exit_uses_profile_thresholds(self):
        prices = np.array([100.0, 100.0, 100.0, 100.0, 100.0], dtype=float)
        rsi = np.full(len(prices), 50.0)
        macd = np.zeros(len(prices))
        sma = np.full(len(prices), 100.0)

        def fake_bs_greeks(S, K, T, r, vol, trade_type):
            price_map = {
                round(4 / 365.0, 6): 1.0,
                round(3 / 365.0, 6): 1.5,
                round(2 / 365.0, 6): 1.2,
                round(1 / 365.0, 6): 1.15,
            }
            return {"delta": 0.30, "bs_price": price_map.get(round(T, 6), 1.0)}

        with patch.object(wfo, "_market_strike_grid", return_value=[100.0]), \
             patch.object(wfo, "_bs_greeks", side_effect=fake_bs_greeks):
            outcome = wfo._simulate_trade_outcome_hist(
                prices=prices,
                i=0,
                trade_type="call",
                hv30=0.2,
                delta_target=0.30,
                dte_at_entry=4,
                stop_loss_pct=50.0,
                profit_target_pct=100.0,
                time_exit_pct=100.0,
                trailing_profit_pct=25.0,
                trailing_giveback_pct=50.0,
                _rsi14=rsi,
                _macd=macd,
                _sma20=sma,
                _sma50=sma,
                tech_at_entry=80.0,
                entry_S0=100.0,
                iv_adj=1.2,
                pricing_lane="mid",
            )

        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["exit_reason"], "trailing_stop")
        self.assertEqual(outcome["exit_px"], 1.2)

    def test_replay_history_sanitizer_drops_bogus_range_free_bars(self):
        frame = pd.DataFrame(
            {
                "Open": [537.3, 533.0, 540.4],
                "High": [540.4, np.nan, 543.6],
                "Low": [537.2, np.nan, 539.7],
                "Close": [540.0, 534.0, 543.2],
                "Volume": [32_789_900.0, 75_000_000.0, 41_488_400.0],
            },
            index=pd.to_datetime(["2024-07-03", "2024-07-04", "2024-07-05"]),
        )

        sanitized = wfo._sanitize_replay_history_frame(frame)

        self.assertEqual(
            [str(ts.date()) for ts in sanitized.index],
            ["2024-07-03", "2024-07-05"],
        )

    def test_direction_score_respects_trade_direction(self):
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["equity"])
        favorable = oc._compute_direction_score(
            tech_score=60.0,
            trade_type="put",
            rsi14=45.0,
            ret5=-4.0,
            spy_ret5=0.0,
            sp=sp,
        )
        adverse = oc._compute_direction_score(
            tech_score=60.0,
            trade_type="put",
            rsi14=45.0,
            ret5=4.0,
            spy_ret5=0.0,
            sp=sp,
        )
        self.assertGreater(favorable, adverse)

    def test_replay_playbook_filters_to_bearish_defensive_slice(self):
        playbook = wfo._get_replay_playbook("bearish_defensive")
        allowed = {
            "ticker": "PFE",
            "trade_type": "put",
            "quality_score": 78.0,
            "market_regime": "bearish",
            "sector": "Healthcare",
        }
        self.assertTrue(wfo._candidate_matches_replay_playbook(allowed, playbook))

        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "trade_type": "call"}, playbook)
        )
        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "sector": "Technology"}, playbook)
        )
        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "market_regime": "bullish"}, playbook)
        )
        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "quality_score": 62.0}, playbook)
        )

    def test_replay_playbook_filters_to_bullish_mean_reversion_slice(self):
        playbook = wfo._get_replay_playbook("bullish_mean_reversion")
        allowed = {
            "ticker": "AAPL",
            "trade_type": "call",
            "signal_family": "bullish_mean_reversion",
            "quality_score": 66.0,
            "market_regime": "bullish",
            "sector": "Technology",
        }
        self.assertTrue(wfo._candidate_matches_replay_playbook(allowed, playbook))

        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "signal_family": "momentum"}, playbook)
        )
        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "trade_type": "put"}, playbook)
        )
        self.assertFalse(
            wfo._candidate_matches_replay_playbook({**allowed, "market_regime": "neutral"}, playbook)
        )

    def test_replay_entry_signal_requires_trend_pullback_and_reversal_for_mean_reversion(self):
        playbook = wfo._get_replay_playbook("bullish_mean_reversion")
        day_data = {
            "S0": 101.0,
            "ret5": -2.4,
            "sma20": 102.0,
            "sma50": 97.0,
            "rsi14": 43.0,
            "macd": 1.2,
            "macd_prev": 0.7,
        }

        signal = wfo._resolve_replay_entry_signal(
            day_data,
            playbook,
            {"entry_momentum": 0.5},
            prior_close=100.0,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["trade_type"], "call")
        self.assertEqual(signal["signal_family"], "bullish_mean_reversion")

        self.assertIsNone(
            wfo._resolve_replay_entry_signal(
                {**day_data, "S0": 96.0},
                playbook,
                {"entry_momentum": 0.5},
                prior_close=100.0,
            )
        )
        self.assertIsNone(
            wfo._resolve_replay_entry_signal(
                {**day_data, "ret5": -0.8},
                playbook,
                {"entry_momentum": 0.5},
                prior_close=100.0,
            )
        )
        self.assertIsNone(
            wfo._resolve_replay_entry_signal(
                {**day_data, "macd": 0.4, "macd_prev": 0.7},
                playbook,
                {"entry_momentum": 0.5},
                prior_close=99.5,
            )
        )

    def test_scan_uses_profile_dte_per_ticker_without_cross_ticker_leak(self):
        requested_dtes = {}

        def fake_fetch_best_option(ticker, trade_type, delta_target, target_dte, stock_price=0.0, hv30_fallback=0.30, **kwargs):
            requested_dtes[ticker] = target_dte
            # Return different strikes for long vs short leg so spread validation passes
            is_long_leg = delta_target > 0.35
            strike = 95.0 if is_long_leg else 100.0
            premium = 3.0 if is_long_leg else 1.5
            return {
                "strike": strike,
                "premium": premium,
                "bid": premium - 0.01,
                "ask": premium + 0.01,
                "expiry": "2026-04-17",
                "dte": 19 if ticker == "SPY" else 8,
                "delta": delta_target,
            }

        with patch.object(oc, "DEFAULT_WATCHLIST", ["SPY", "AAPL"]), \
             patch.object(oc.yf, "Ticker", side_effect=lambda symbol: _ScanTicker(symbol)), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_fetch_best_option", side_effect=fake_fetch_best_option), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }):
            picks = oc.scan_daily_top_trades(n_picks=2)

        self.assertEqual(requested_dtes["SPY"], int(oc.STRATEGY_PROFILES["index"]["targets"]["dte_optimal"]))
        self.assertEqual(requested_dtes["AAPL"], int(oc.STRATEGY_PROFILES["equity"]["targets"]["dte_optimal"]))
        self.assertTrue(any(pick["ticker"] == "SPY" and pick["dte"] == 19 for pick in picks))

    def test_scan_uses_live_current_spot_for_contract_selection_when_market_is_open(self):
        requested_prices = {}

        def fake_fetch_best_option(ticker, trade_type, delta_target, target_dte, stock_price=0.0, hv30_fallback=0.30, **kwargs):
            requested_prices[ticker] = stock_price
            is_long_leg = delta_target > 0.35
            strike = 95.0 if is_long_leg else 100.0
            premium = 3.0 if is_long_leg else 1.5
            return {
                "strike": strike,
                "premium": premium,
                "bid": premium - 0.01,
                "ask": premium + 0.01,
                "expiry": "2026-04-17",
                "dte": 19,
                "delta": delta_target,
            }

        with patch.object(oc, "DEFAULT_WATCHLIST", ["SPY"]), \
             patch.object(oc.yf, "Ticker", side_effect=lambda symbol: _ScanTicker(symbol)), \
             patch.object(oc, "_market_is_open", return_value=True), \
             patch.object(oc, "_cached_fast_info", return_value={"last_price": 250.0}), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_fetch_best_option", side_effect=fake_fetch_best_option), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_generate_trade_strategy", return_value={
                 "label": "Hold to target",
                 "comment": "Uses live spot",
                 "sl_option_px": 1.0,
                 "tp_option_px": 3.0,
                 "stock_sl": 245.0,
                 "stock_tp": 260.0,
             }), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }):
            picks = oc.scan_daily_top_trades(n_picks=1)

        self.assertEqual(requested_prices["SPY"], 250.0)
        self.assertEqual(picks[0]["stock_price"], 250.0)
        self.assertEqual(picks[0]["current_spot"], 250.0)
        self.assertEqual(picks[0]["underlying_price_at_selection"], 250.0)
        self.assertNotEqual(picks[0]["entry_price"], picks[0]["stock_price"])

    def test_scan_rejects_options_without_live_quotes(self):
        with patch.object(oc, "DEFAULT_WATCHLIST", ["AAPL"]), \
             patch.object(oc.yf, "Ticker", side_effect=lambda symbol: _ScanTicker(symbol)), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_fetch_best_option", return_value={
                 "strike": 100.0,
                 "premium": 1.5,
                 "bid": None,
                 "ask": None,
                 "expiry": "2026-04-17",
                 "dte": 10,
                 "delta": 0.30,
             }), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }):
            picks = oc.scan_daily_top_trades(n_picks=1)

        self.assertEqual(picks, [])

    def test_compute_tech_score_live_uses_completed_bar_when_market_is_open(self):
        dates = pd.date_range("2024-01-01", periods=70, freq="B")
        closes = [100.0 + i for i in range(69)] + [50.0]
        history = pd.DataFrame({"Close": closes}, index=dates)

        with patch.object(oc, "_cached_history", return_value=history), \
             patch.object(oc, "_market_is_open", return_value=True):
            open_score, _, open_ret5 = oc._compute_tech_score_live("AAPL", "call")

        with patch.object(oc, "_cached_history", return_value=history), \
             patch.object(oc, "_market_is_open", return_value=False):
            closed_score, _, closed_ret5 = oc._compute_tech_score_live("AAPL", "call")

        self.assertGreater(open_score, closed_score)
        self.assertGreater(open_ret5, 0.0)
        self.assertLess(closed_ret5, 0.0)

    def test_scan_reuses_cached_history_and_sector_between_identical_calls(self):
        tickers = {symbol: _CountingScanTicker(symbol) for symbol in ["SPY", "AAPL", "^VIX"]}

        _fake_spread = {
            "long_leg": {
                "strike": 95.0, "premium": 3.0, "delta": 0.50,
                "bid": 2.99, "ask": 3.01, "iv": None, "last": None,
                "contract_symbol": None, "volume": None, "open_interest": None,
                "quote_age_hours": None, "quote_basis": None,
            },
            "short_leg": {
                "strike": 100.0, "premium": 1.5, "delta": 0.20,
                "bid": 1.49, "ask": 1.51, "iv": None, "last": None,
                "contract_symbol": None, "volume": None, "open_interest": None,
                "quote_age_hours": None, "quote_basis": None,
            },
            "spread_width": 5.0,
            "net_debit": 1.5,
            "max_profit": 3.5,
            "max_loss": 1.5,
            "net_delta": 0.30,
            "debit_pct_of_width": 30.0,
            "risk_reward_ratio": 2.33,
            "expiry": "2026-04-17",
            "dte": 10,
            "live_chain": False,
            "options_snapshot_status": None,
            "option_chain_status": None,
        }

        with patch.object(oc, "DEFAULT_WATCHLIST", ["AAPL"]), \
             patch.object(oc.yf, "Ticker", side_effect=lambda symbol: tickers[symbol]), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_compute_direction_score", return_value=72.0), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_fetch_best_spread", return_value=_fake_spread), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }):
            first = oc.scan_daily_top_trades(n_picks=1)
            second = oc.scan_daily_top_trades(n_picks=1)

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(tickers["AAPL"].info_calls, 1)
        self.assertEqual(len(tickers["AAPL"].history_calls), 2)
        # SPY history is fetched for two different periods (10d and 70d) per scan run
        self.assertEqual(len(tickers["SPY"].history_calls), 4)

    def test_put_call_ratio_reuses_cached_options_data_between_calls(self):
        class _RatioTicker:
            def __init__(self):
                self.history_calls = []
                self.options_calls = 0
                self.option_chain_calls = []

            def history(self, period="1d", start=None, end=None, interval=None):
                self.history_calls.append((period, str(start), str(end), interval))
                return pd.DataFrame(
                    {"Close": [100.0, 101.5]},
                    index=pd.date_range("2025-03-20 09:35", periods=2, freq="5min"),
                )

            @property
            def options(self):
                self.options_calls += 1
                return ["2025-04-04"]

            def option_chain(self, expiry):
                self.option_chain_calls.append(expiry)
                calls = pd.DataFrame(
                    [{"strike": 105.0, "volume": 120, "openInterest": 300}]
                )
                puts = pd.DataFrame(
                    [{"strike": 95.0, "volume": 80, "openInterest": 250}]
                )
                return type("Chain", (), {"calls": calls, "puts": puts})()

        ticker = _RatioTicker()
        with patch.object(oc.yf, "Ticker", return_value=ticker), \
             patch.object(oc, "datetime", _StrategyAuditDateTime), \
             patch.object(mds, "datetime", _StrategyAuditDateTime):
            first = json.loads(oc.get_put_call_ratio("AAA", max_dte=21))
            second = json.loads(oc.get_put_call_ratio("AAA", max_dte=21))

        self.assertEqual(first["symbol"], "AAA")
        self.assertEqual(second["overall"]["put_call_ratio"], first["overall"]["put_call_ratio"])
        self.assertEqual(ticker.options_calls, 1)
        self.assertEqual(ticker.option_chain_calls.count("2025-04-04"), 1)
        self.assertEqual(len(ticker.history_calls), 1)

    def test_evaluate_trade_signal_uses_symbol_profile_risk_settings(self):
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        sp["risk"]["stop_loss_pct"] = 42.0
        sp["risk"]["profit_target_pct"] = 88.0
        sp["filters"]["min_ev_return_pct"] = 12.0
        profile_calls = []

        class _EvalTicker:
            earnings_dates = pd.DataFrame()

            def history(self, period="10d", start=None, end=None, interval=None):
                return _make_close_history(10, 400.0)

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            return sp

        with patch.object(oc, "_get_profile", side_effect=fake_get_profile), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }), \
             patch.object(oc.yf, "Ticker", return_value=_EvalTicker()):
            result = json.loads(
                oc.evaluate_trade_signal(
                    symbol="SPY",
                    option_type="call",
                    strike=500.0,
                    expiry="2026-04-17",
                    bid=1.00,
                    ask=1.01,
                    delta=0.30,
                    iv_percentile=30.0,
                    dte=20,
                    position_dollars=1000.0,
                )
            )

        self.assertEqual(result["adjusted_parameters"]["stop_loss_pct"], 42.0)
        self.assertEqual(result["adjusted_parameters"]["profit_target_pct"], 88.0)
        self.assertEqual(result["expected_value"]["required_ev_pct"], 12.0)
        self.assertEqual(profile_calls[0], ("SPY", "call"))

    def test_evaluate_trade_signal_blocks_missing_quotes(self):
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])

        class _EvalTicker:
            earnings_dates = pd.DataFrame()

            def history(self, period="10d", start=None, end=None, interval=None):
                return _make_close_history(10, 400.0)

        with patch.object(oc, "_get_profile", return_value=sp), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }), \
             patch.object(oc.yf, "Ticker", return_value=_EvalTicker()):
            result = json.loads(
                oc.evaluate_trade_signal(
                    symbol="SPY",
                    option_type="call",
                    strike=500.0,
                    expiry="2026-04-17",
                    delta=0.30,
                    iv_percentile=30.0,
                    dte=20,
                    position_dollars=1000.0,
                )
            )

        self.assertEqual(result["liquidity"]["reasons"], ["no_valid_bid_ask"])
        self.assertIn("No valid bid/ask", result["recommendation"]["blocks"])
        self.assertTrue(result["recommendation"]["signal"].endswith("AVOID"))

    def test_evaluate_trade_signal_uses_contract_liquidity_diagnostics(self):
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])

        class _EvalTicker:
            earnings_dates = pd.DataFrame()

            def history(self, period="10d", start=None, end=None, interval=None):
                return _make_close_history(10, 400.0)

        with patch.object(oc, "_get_profile", return_value=sp), \
             patch.object(oc, "_compute_tech_score_from_close_series", return_value=(80.0, 55.0, 2.0)), \
             patch.object(oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(oc, "_calculate_iv_skew", return_value={"iv_crush_penalty_pts": 0.0, "iv_crush_warning": ""}), \
             patch.object(oc, "_get_market_regime", return_value={
                 "position_size_mult": 1.0,
                 "stop_loss_mult": 1.0,
                 "regime_notes": ["Normal market conditions"],
                 "defense_mode": False,
                 "vix": 18.0,
                 "atr_14d": 0.015,
             }), \
             patch.object(oc.yf, "Ticker", return_value=_EvalTicker()):
            result = json.loads(
                oc.evaluate_trade_signal(
                    symbol="SPY",
                    option_type="call",
                    strike=500.0,
                    expiry="2026-04-17",
                    bid=1.00,
                    ask=1.04,
                    contract_volume=5,
                    open_interest=25,
                    quote_age_hours=72.0,
                    delta=0.30,
                    iv_percentile=30.0,
                    dte=20,
                    position_dollars=1000.0,
                )
            )

        reasons = set(result["liquidity"]["reasons"])
        self.assertTrue({"wide_spread", "low_contract_volume", "low_open_interest", "stale_quote"}.issubset(reasons))
        self.assertIn("Contract blocked:", result["liquidity"]["flag"])

    def test_pending_pick_grading_uses_direction_aware_profile(self):
        profile_calls = []
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        sp["early_exit"]["enabled"] = False
        predictions = [
            {
                "id": 1,
                "ticker": "SPY",
                "direction": "call",
                "type": "daily_scan",
                "entry_date": "2025-03-20",
                "entry_price": 100.0,
                "target_date": "2025-03-31",
                "est_premium": 2.0,
                "delta_est": 0.3,
                "stop_loss_pct": 50.0,
                "profit_target_pct": 100.0,
            }
        ]
        ticker_hist = pd.DataFrame(
            {
                "Open": [100.2, 100.5],
                "High": [101.0, 101.1],
                "Low": [99.8, 100.0],
                "Close": [100.8, 100.9],
            },
            index=pd.to_datetime(["2025-03-21", "2025-03-24"]),
        )
        spy_hist = pd.DataFrame(
            {"Close": [400.0, 401.0, 402.0, 403.0, 404.0, 405.0]},
            index=pd.date_range("2025-03-14", periods=6, freq="B"),
        )

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            return copy.deepcopy(sp)

        def fake_history(symbol, *args, **kwargs):
            return spy_hist if str(symbol).upper() == "SPY" and kwargs.get("period") == "10d" else ticker_hist

        with patch.object(oc, "datetime", _StrategyAuditDateTime), \
             patch.object(oc, "_load_predictions", return_value=copy.deepcopy(predictions)), \
             patch.object(oc, "_save_predictions"), \
             patch.object(oc, "_cached_history", side_effect=fake_history), \
             patch.object(oc, "_cached_options", return_value=[]), \
             patch.object(oc, "_get_profile", side_effect=fake_get_profile):
            oc.log_prediction(action="grade")

        self.assertIn(("SPY", "call"), profile_calls)

    def test_check_early_exit_maps_bullish_and_bearish_to_side_profiles(self):
        profile_calls = []
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        sp["early_exit"]["enabled"] = False

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            return copy.deepcopy(sp)

        with patch.object(oc, "_get_profile", side_effect=fake_get_profile):
            oc._check_early_exit({"ticker": "SPY", "direction": "bullish"}, 10.0, 12.0)
            oc._check_early_exit({"ticker": "SPY", "direction": "bearish"}, 10.0, 12.0)

        self.assertIn(("SPY", "call"), profile_calls)
        self.assertIn(("SPY", "put"), profile_calls)

    def test_calculate_iv_skew_uses_option_side_profile_when_profile_missing(self):
        profile_calls = []
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        price_history = pd.DataFrame(
            {"Close": [499.0, 500.0, 501.0]},
            index=pd.date_range("2025-03-19", periods=3, freq="B"),
        )
        put_chain = type(
            "Chain",
            (),
            {
                "calls": pd.DataFrame({"strike": [500.0], "impliedVolatility": [0.2]}),
                "puts": pd.DataFrame({"strike": [500.0], "impliedVolatility": [0.24]}),
            },
        )()

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            return copy.deepcopy(sp)

        with patch.object(oc, "_get_profile", side_effect=fake_get_profile), \
             patch.object(oc, "_cached_history", return_value=price_history), \
             patch.object(oc, "_cached_option_chain", return_value=put_chain), \
             patch.object(oc, "_cached_options", return_value=["2026-04-17"]):
            oc._calculate_iv_skew("SPY", 500.0, "put", "2026-04-17")

        self.assertIn(("SPY", "put"), profile_calls)

    def test_backtest_strategy_uses_side_specific_profile_for_explicit_option_type(self):
        profile_calls = []
        sp = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        short_history = pd.DataFrame(
            {
                "Open": [100.0 + i for i in range(20)],
                "High": [100.5 + i for i in range(20)],
                "Low": [99.5 + i for i in range(20)],
                "Close": [100.0 + i for i in range(20)],
                "Volume": [8_000_000.0 for _ in range(20)],
            },
            index=pd.date_range("2025-01-01", periods=20, freq="B"),
        )

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            return copy.deepcopy(sp)

        with patch.object(oc, "_get_profile", side_effect=fake_get_profile), \
             patch.object(oc, "_cached_history", return_value=short_history):
            result = json.loads(oc.backtest_strategy("SPY", option_type="call", lookback_days=5))

        self.assertIn("error", result)
        self.assertEqual(profile_calls[0], ("SPY", "call"))
        self.assertNotIn(("SPY", None), profile_calls)

    def test_backtest_strategy_signal_stays_neutral_until_side_is_selected(self):
        profile_calls = []
        neutral_profile = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        call_profile = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        put_profile = copy.deepcopy(oc.STRATEGY_PROFILES["index"])
        call_profile["entry"]["min_tech_score"] = 0.0
        call_profile["entry"]["min_direction_score"] = 0.0
        call_profile["filters"]["min_ev_return_pct"] = -100.0
        put_profile["entry"]["min_tech_score"] = 0.0
        put_profile["entry"]["min_direction_score"] = 99.0
        put_profile["filters"]["min_ev_return_pct"] = 99.0
        history = pd.DataFrame(
            {
                "Open": [100.0 + i for i in range(120)],
                "High": [100.5 + i for i in range(120)],
                "Low": [99.5 + i for i in range(120)],
                "Close": [100.0 + i for i in range(120)],
                "Volume": [8_000_000.0 for _ in range(120)],
            },
            index=pd.date_range("2024-01-01", periods=120, freq="B"),
        )

        def fake_get_profile(symbol, direction=None):
            profile_calls.append((symbol, direction))
            if direction == "call":
                return copy.deepcopy(call_profile)
            if direction == "put":
                return copy.deepcopy(put_profile)
            return copy.deepcopy(neutral_profile)

        def fake_bs_greeks(S, K, T, r, vol, trade_type):
            return {"delta": 0.30, "bs_price": 1.0}

        with patch.object(oc, "_get_profile", side_effect=fake_get_profile), \
             patch.object(oc, "_cached_history", return_value=history), \
             patch.object(oc, "_cached_earnings_dates", return_value=pd.DataFrame()), \
             patch.object(oc, "_bs_greeks", side_effect=fake_bs_greeks):
            result = json.loads(oc.backtest_strategy("SPY", option_type="signal", lookback_days=10))

        self.assertNotIn("error", result)
        self.assertEqual(profile_calls[0], ("SPY", None))
        self.assertIn(("SPY", "call"), profile_calls)

    def test_profitability_forensics_groups_core_options_slices(self):
        result = {
            "run_at": "2026-04-03T14:18:04",
            "mode": "backtest",
            "lookback_years": 2,
            "pricing_lane": "historical_imported_daily",
            "playbook": "broad",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 99.2,
            "priced_trade_count": 6,
            "trades": [
                {
                    "ticker": "SPY",
                    "type": "call",
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "exact_target_contract",
                    "direction_score": 82.0,
                    "quality_score": 72.0,
                    "tech_score": 71.0,
                    "dte": 7,
                    "exit_reason": "target",
                    "pnl_pct": 25.0,
                    "directional_correct": True,
                },
                {
                    "ticker": "SPY",
                    "type": "call",
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "nearest_listed_contract",
                    "direction_score": 76.0,
                    "quality_score": 70.0,
                    "tech_score": 68.0,
                    "dte": 9,
                    "exit_reason": "stop",
                    "pnl_pct": -15.0,
                    "directional_correct": False,
                },
                {
                    "ticker": "QQQ",
                    "type": "put",
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "nearest_listed_contract",
                    "direction_score": 61.0,
                    "quality_score": 65.0,
                    "tech_score": 62.0,
                    "dte": 18,
                    "exit_reason": "stop",
                    "pnl_pct": -35.0,
                    "directional_correct": False,
                },
                {
                    "ticker": "QQQ",
                    "type": "call",
                    "selection_source": "replay_calibrated",
                    "entry_contract_resolution": "exact_target_contract",
                    "direction_score": 84.0,
                    "quality_score": 74.0,
                    "tech_score": 73.0,
                    "dte": 14,
                    "exit_reason": "target",
                    "pnl_pct": 18.0,
                    "directional_correct": True,
                },
                {
                    "ticker": "SPY",
                    "type": "put",
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "nearest_listed_contract",
                    "direction_score": 58.0,
                    "quality_score": 60.0,
                    "tech_score": 59.0,
                    "dte": 24,
                    "exit_reason": "time_exit",
                    "pnl_pct": -12.0,
                    "directional_correct": True,
                },
                {
                    "ticker": "QQQ",
                    "type": "call",
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "exact_target_contract",
                    "direction_score": 45.0,
                    "quality_score": 55.0,
                    "tech_score": 54.0,
                    "dte": 28,
                    "exit_reason": "time_exit",
                    "pnl_pct": -8.0,
                    "directional_correct": False,
                },
            ],
        }

        report = opf.build_options_profitability_forensics(result, min_trades=1)

        self.assertTrue(
            {
                "generated_at",
                "source",
                "quality_bar",
                "overall",
                "exactness_view",
                "category_order",
                "by_category",
                "best_dense_slices",
                "worst_dense_slices",
                "blockers",
                "recommendations",
            }.issubset(report.keys())
        )
        self.assertEqual(
            report["category_order"],
            [
                "symbol",
                "side",
                "symbol_side",
                "selection_source",
                "contract_resolution",
                "score_bands",
                "dte_bucket",
                "exit_reason",
            ],
        )
        self.assertTrue(report["by_category"]["symbol"])
        self.assertTrue(report["by_category"]["side"])
        self.assertIn("exact_only", report["exactness_view"])
        self.assertEqual(report["exactness_view"]["exact_only"]["trades"], 3)
        self.assertEqual(report["exactness_view"]["nearest_only"]["trades"], 3)
        self.assertTrue(any(item["value"] == "SPY:call" for item in report["by_category"]["symbol_side"]))

    def test_profitability_forensics_uses_exact_contract_authoritative_lens(self):
        result = {
            "run_at": "2026-04-03T14:18:04",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "truth_source": "historical_imported_daily",
            "trades": [
                {
                    "ticker": "SPY",
                    "type": "call",
                    "selection_source": "replay_calibrated",
                    "entry_contract_resolution": "exact_target_contract",
                    "direction_score": 80.0,
                    "quality_score": 72.0,
                    "tech_score": 71.0,
                    "dte": 7,
                    "exit_reason": "stop",
                    "pnl_pct": -12.0,
                    "directional_correct": False,
                },
                {
                    "ticker": "QQQ",
                    "type": "call",
                    "selection_source": "replay_calibrated",
                    "entry_contract_resolution": "exact_target_contract",
                    "direction_score": 78.0,
                    "quality_score": 70.0,
                    "tech_score": 69.0,
                    "dte": 9,
                    "exit_reason": "stop",
                    "pnl_pct": -8.0,
                    "directional_correct": False,
                },
                {
                    "ticker": "SPY",
                    "type": "call",
                    "selection_source": "replay_calibrated",
                    "entry_contract_resolution": "nearest_listed_contract",
                    "direction_score": 82.0,
                    "quality_score": 74.0,
                    "tech_score": 73.0,
                    "dte": 8,
                    "exit_reason": "target",
                    "pnl_pct": 15.0,
                    "directional_correct": True,
                },
                {
                    "ticker": "QQQ",
                    "type": "call",
                    "selection_source": "replay_calibrated",
                    "entry_contract_resolution": "nearest_listed_contract",
                    "direction_score": 84.0,
                    "quality_score": 76.0,
                    "tech_score": 75.0,
                    "dte": 10,
                    "exit_reason": "target",
                    "pnl_pct": 14.0,
                    "directional_correct": True,
                },
            ],
        }

        report = opf.build_options_profitability_forensics(result, min_trades=1)

        self.assertEqual(report["authoritative_profitability_label"], "Exact-contract subset")
        self.assertEqual(report["overall"]["trades"], 2)
        self.assertEqual(report["aggregate_overall"]["trades"], 4)
        self.assertEqual(report["research_only_overall"]["trades"], 2)
        self.assertEqual(report["exactness_view"]["authoritative_only"]["trades"], 2)
        self.assertIn("Exact-contract subset profit factor is below 1.0.", report["blockers"])

    def test_historical_backtest_uses_spy_aligned_open_series(self):
        spy_dates = pd.date_range("2024-01-01", periods=100, freq="B")
        aaa_dates = pd.date_range("2024-01-01", periods=105, freq="B")
        histories = {
            "SPY": pd.DataFrame({
                "Open": [2000.0 + i for i in range(100)],
                "Close": [400.0 + i for i in range(100)],
                "Volume": [75_000_000.0 for _ in range(100)],
            }, index=spy_dates),
            "AAA": pd.DataFrame({
                "Open": [1000.0 + i for i in range(105)],
                "Close": [100.0 + i for i in range(105)],
                "Volume": [9_000_000.0 for _ in range(105)],
            }, index=aaa_dates),
        }
        captured_entry_opens = []

        def fake_simulate_trade_outcome_hist(**kwargs):
            captured_entry_opens.append(kwargs["entry_S0"])
            return {
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0,
                "exit_reason": "target",
                "strike": 100.0,
                "delta_val": 0.3,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": 0.2,
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": kwargs.get("pricing_lane", "pessimistic"),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_results = os.path.join(tmpdir, "wfo_results.json")
            with patch.object(wfo, "WFO_RESULTS_FILE", temp_results), \
                 patch.object(wfo, "DEFAULT_WATCHLIST", ["AAA"]), \
                 patch.object(wfo.yf, "Ticker", side_effect=lambda symbol: _BacktestTicker(symbol, histories)), \
                 patch.object(wfo, "_tech_score", return_value=80.0), \
                 patch.object(wfo, "_compute_direction_score", return_value=80.0), \
                 patch.object(wfo, "_compute_quality_score", return_value=70.0), \
                 patch.object(wfo, "_pick_top_n_daily", side_effect=lambda candidates, n: candidates[:n]), \
                 patch.object(wfo, "_simulate_trade_outcome_hist", side_effect=fake_simulate_trade_outcome_hist), \
                 patch.object(wfo, "_simulate_spread_outcome_hist", side_effect=fake_simulate_trade_outcome_hist):
                wfo.run_historical_backtest(lookback_years=1, n_picks=1, iv_adj=1.0)

        self.assertTrue(captured_entry_opens)
        self.assertEqual(captured_entry_opens[0], 1057.0)

    def test_historical_backtest_normalizes_tz_aware_history_indexes(self):
        spy_dates = pd.date_range("2024-01-01", periods=320, freq="B")
        aaa_dates = pd.date_range("2024-01-01", periods=320, freq="B", tz="UTC")
        histories = {
            "SPY": pd.DataFrame({
                "Open": [400.0 + i for i in range(320)],
                "Close": [401.0 + i for i in range(320)],
                "Volume": [75_000_000.0 for _ in range(320)],
            }, index=spy_dates),
            "AAA": pd.DataFrame({
                "Open": [100.0 + i for i in range(320)],
                "Close": [101.0 + i for i in range(320)],
                "Volume": [8_500_000.0 for _ in range(320)],
            }, index=aaa_dates),
        }

        def fake_simulate_trade_outcome_hist(**kwargs):
            return {
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0,
                "exit_reason": "target",
                "strike": 100.0,
                "delta_val": 0.3,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": 0.2,
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": kwargs.get("pricing_lane", "pessimistic"),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_results = os.path.join(tmpdir, "wfo_results.json")
            with patch.object(wfo, "WFO_RESULTS_FILE", temp_results), \
                 patch.object(wfo, "DEFAULT_WATCHLIST", ["AAA"]), \
                 patch.object(wfo.yf, "Ticker", side_effect=lambda symbol: _BacktestTicker(symbol, histories)), \
                 patch.object(wfo, "_tech_score", return_value=80.0), \
                 patch.object(wfo, "_compute_direction_score", return_value=80.0), \
                 patch.object(wfo, "_compute_quality_score", return_value=70.0), \
                 patch.object(wfo, "_pick_top_n_daily", side_effect=lambda candidates, n: candidates[:n]), \
                 patch.object(wfo, "_simulate_trade_outcome_hist", side_effect=fake_simulate_trade_outcome_hist):
                result = wfo.run_historical_backtest(lookback_years=1, n_picks=1, iv_adj=1.0)

        self.assertGreater(result["total_trades"], 0)
        self.assertIn("AAA", result["eligible_tickers"])

    def test_historical_backtest_excludes_short_history_symbols(self):
        spy_dates = pd.date_range("2024-01-01", periods=320, freq="B")
        aaa_dates = pd.date_range("2024-01-01", periods=320, freq="B")
        new_dates = pd.date_range("2024-08-01", periods=160, freq="B")
        histories = {
            "SPY": pd.DataFrame({
                "Open": [400.0 + i for i in range(320)],
                "Close": [401.0 + i for i in range(320)],
                "Volume": [75_000_000.0 for _ in range(320)],
            }, index=spy_dates),
            "AAA": pd.DataFrame({
                "Open": [100.0 + i for i in range(320)],
                "Close": [101.0 + i for i in range(320)],
                "Volume": [8_500_000.0 for _ in range(320)],
            }, index=aaa_dates),
            "NEW": pd.DataFrame({
                "Open": [50.0 + i for i in range(160)],
                "Close": [51.0 + i for i in range(160)],
                "Volume": [9_500_000.0 for _ in range(160)],
            }, index=new_dates),
        }

        def fake_simulate_trade_outcome_hist(**kwargs):
            return {
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0,
                "exit_reason": "target",
                "strike": 100.0,
                "delta_val": 0.3,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": 0.2,
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": kwargs.get("pricing_lane", "pessimistic"),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_results = os.path.join(tmpdir, "wfo_results.json")
            with patch.object(wfo, "WFO_RESULTS_FILE", temp_results), \
                 patch.object(wfo, "DEFAULT_WATCHLIST", ["AAA", "NEW"]), \
                 patch.object(wfo.yf, "Ticker", side_effect=lambda symbol: _BacktestTicker(symbol, histories)), \
                 patch.object(wfo, "_tech_score", return_value=80.0), \
                 patch.object(wfo, "_compute_direction_score", return_value=80.0), \
                 patch.object(wfo, "_compute_quality_score", return_value=70.0), \
                 patch.object(wfo, "_pick_top_n_daily", side_effect=lambda candidates, n: candidates[:n]), \
                 patch.object(wfo, "_simulate_trade_outcome_hist", side_effect=fake_simulate_trade_outcome_hist):
                result = wfo.run_historical_backtest(lookback_years=1, n_picks=1, iv_adj=1.0)

        excluded = {item["ticker"]: item["reason"] for item in result["excluded_tickers"]}
        self.assertEqual(excluded.get("NEW"), "insufficient_history")
        self.assertIn("AAA", result["eligible_tickers"])

    def test_historical_backtest_reuses_cached_history_and_sector_between_runs(self):
        spy_dates = pd.date_range("2024-01-01", periods=320, freq="B")
        histories = {
            "SPY": pd.DataFrame({
                "Open": [400.0 + i for i in range(320)],
                "Close": [401.0 + i for i in range(320)],
                "Volume": [75_000_000.0 for _ in range(320)],
            }, index=spy_dates),
            "AAA": pd.DataFrame({
                "Open": [100.0 + i for i in range(320)],
                "Close": [101.0 + i for i in range(320)],
                "Volume": [8_500_000.0 for _ in range(320)],
            }, index=spy_dates),
        }
        tickers = {
            symbol: _CountingBacktestTicker(symbol, histories)
            for symbol in histories
        }

        def fake_simulate_trade_outcome_hist(**kwargs):
            return {
                "entry_px": 1.0,
                "exit_px": 1.2,
                "pnl_pct": 20.0,
                "exit_reason": "target",
                "strike": 100.0,
                "delta_val": 0.3,
                "stock_px": kwargs["entry_S0"],
                "exit_stock_px": kwargs["entry_S0"] * 1.01,
                "stock_move_pct": 1.0,
                "directional_correct": True,
                "hv30": 0.2,
                "iv_adj": kwargs["iv_adj"],
                "dte": kwargs["dte_at_entry"],
                "entry_day_idx": kwargs["i"],
                "exit_day_idx": kwargs["i"] + 1,
                "pricing_lane": kwargs.get("pricing_lane", "pessimistic"),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_results = os.path.join(tmpdir, "wfo_results.json")
            with patch.object(wfo, "WFO_RESULTS_FILE", temp_results), \
                 patch.object(wfo, "DEFAULT_WATCHLIST", ["AAA"]), \
                 patch.object(wfo.yf, "Ticker", side_effect=lambda symbol: tickers[symbol]), \
                 patch.object(wfo, "_tech_score", return_value=80.0), \
                 patch.object(wfo, "_compute_direction_score", return_value=80.0), \
                 patch.object(wfo, "_compute_quality_score", return_value=70.0), \
                 patch.object(wfo, "_pick_top_n_daily", side_effect=lambda candidates, n: candidates[:n]), \
                 patch.object(wfo, "_simulate_trade_outcome_hist", side_effect=fake_simulate_trade_outcome_hist):
                first = wfo.run_historical_backtest(lookback_years=1, n_picks=1, iv_adj=1.0)
                second = wfo.run_historical_backtest(lookback_years=1, n_picks=1, iv_adj=1.0)

        self.assertGreater(first["total_trades"], 0)
        self.assertGreater(second["total_trades"], 0)
        self.assertEqual(tickers["AAA"].info_calls, 1)
        self.assertEqual(len(tickers["AAA"].history_calls), 2)
        self.assertEqual(len(tickers["SPY"].history_calls), 2)

    def test_prediction_replay_report_groups_trades(self):
        result = {
            "run_at": "2026-03-29T19:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "trades": [
                {
                    "ticker": "AAPL",
                    "sector": "Technology",
                    "market_regime": "bullish",
                    "direction_score": 64.0,
                    "quality_score": 58.0,
                    "ev": 42.0,
                    "prediction_outcome": "hit",
                    "directional_correct": True,
                    "pnl_pct": 25.0,
                },
                {
                    "ticker": "AAPL",
                    "sector": "Technology",
                    "market_regime": "bullish",
                    "direction_score": 61.0,
                    "quality_score": 54.0,
                    "ev": 35.0,
                    "prediction_outcome": "miss",
                    "directional_correct": False,
                    "pnl_pct": -15.0,
                },
                {
                    "ticker": "XOM",
                    "sector": "Energy",
                    "market_regime": "bearish",
                    "direction_score": 82.0,
                    "quality_score": 63.0,
                    "ev": 51.0,
                    "prediction_outcome": "directional",
                    "directional_correct": True,
                    "pnl_pct": 5.0,
                },
            ],
        }

        report = wfo.build_prediction_replay_report(result=result, min_trades=2)

        self.assertEqual(report["source"]["total_trades"], 3)
        self.assertEqual(report["overall"]["trades"], 3)
        self.assertEqual(report["overall"]["full_hit_rate_pct"], 33.3)
        score_bucket = next(item for item in report["by_direction_score"] if item["value"] == "60-69")
        self.assertEqual(score_bucket["trades"], 2)
        self.assertEqual(score_bucket["share_of_total_pct"], 66.7)
        ticker_bucket = next(item for item in report["by_ticker"] if item["value"] == "AAPL")
        self.assertEqual(ticker_bucket["directional_accuracy_pct"], 50.0)
        regime_bucket = next(item for item in report["by_regime"] if item["value"] == "bullish")
        self.assertEqual(regime_bucket["trades"], 2)
        self.assertTrue(any(item["value"] == "AAPL" for item in report["best_segments"] + report["weakest_segments"]))


class CalibrationSurfaceAuditTests(unittest.TestCase):
    def test_expectancy_surface_builds_hierarchical_levels(self):
        trades = [
            _make_calibration_trade(pnl_pct=25.0, market_regime="bullish", direction_score=74.0, quality_score=66.0),
            _make_calibration_trade(pnl_pct=15.0, market_regime="bearish", direction_score=71.0, quality_score=64.0),
            _make_calibration_trade(pnl_pct=-5.0, market_regime="neutral", direction_score=78.0, quality_score=62.0, directional_correct=False),
        ]

        surface = ec.build_expectancy_surface_from_trades(
            trades,
            min_trades=2,
            bucket_size=10,
            shrinkage_trades=2.0,
            sparse_warning_trades=2,
        )

        self.assertIsNotNone(surface)
        self.assertFalse(surface["include_tech_band"])
        self.assertEqual(
            surface["lookup_order"],
            [
                "regime_direction_dir_quality",
                "direction_dir_quality",
                "regime_direction_dir",
                "direction_dir",
                "regime_direction",
                "direction",
                "overall",
            ],
        )
        self.assertIn("direction", surface["levels"])
        self.assertIn("direction_dir_quality", surface["levels"])
        self.assertIn("overall", surface["levels"])
        density_levels = [row["level"] for row in surface["diagnostics"]["level_density"]]
        self.assertIn("direction", density_levels)
        self.assertIn("regime_direction_dir_quality", density_levels)

    def test_expectancy_lookup_uses_deterministic_fallback_order(self):
        trades = [
            _make_calibration_trade(
                pnl_pct=-10.0,
                market_regime="bullish",
                trade_type="call",
                direction_score=75.0,
                quality_score=75.0,
                tech_score=70.0,
                directional_correct=False,
            ),
            _make_calibration_trade(
                pnl_pct=30.0,
                market_regime="bearish",
                trade_type="call",
                direction_score=75.0,
                quality_score=75.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=20.0,
                market_regime="neutral",
                trade_type="call",
                direction_score=75.0,
                quality_score=75.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=50.0,
                market_regime="bullish",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
        ]

        surface = ec.build_expectancy_surface_from_trades(
            trades,
            min_trades=1,
            bucket_size=10,
            shrinkage_trades=0.0,
            sparse_warning_trades=1,
        )
        calibration = ec.lookup_calibrated_expectancy(
            surface,
            direction_score=75.0,
            quality_score=75.0,
            market_regime="bullish",
            trade_type="call",
            tech_score=70.0,
            require_positive=True,
            allow_overall=False,
        )

        self.assertIsNotNone(calibration)
        self.assertEqual(calibration["lookup_source"], "direction_dir_quality")
        self.assertEqual(calibration["avg_pnl_pct"], 13.33)

    def test_expectancy_shrinkage_pulls_sparse_child_toward_parent(self):
        trades = [
            _make_calibration_trade(
                pnl_pct=100.0,
                market_regime="bullish",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=10.0,
                market_regime="bearish",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=10.0,
                market_regime="neutral",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=10.0,
                market_regime="neutral",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
            _make_calibration_trade(
                pnl_pct=10.0,
                market_regime="bearish",
                trade_type="call",
                direction_score=75.0,
                quality_score=65.0,
                tech_score=70.0,
            ),
        ]

        surface = ec.build_expectancy_surface_from_trades(
            trades,
            min_trades=1,
            bucket_size=10,
            shrinkage_trades=4.0,
            sparse_warning_trades=5,
        )
        child = surface["levels"]["regime_direction_dir_quality"]["bullish|call|70-79|60-69"]

        self.assertEqual(child["avg_pnl_pct_raw"], 100.0)
        self.assertEqual(child["parent_avg_pnl_pct"], 28.0)
        self.assertEqual(child["avg_pnl_pct"], 42.4)
        self.assertTrue(child["used_parent_shrinkage"])
        self.assertTrue(child["sparse_cohort"])

    def test_replay_calibration_pool_excludes_open_or_future_trades(self):
        trades = [
            {"ticker": "AAA", "exit_day_idx": 9, "entry_contract_resolution": "exact_target_contract"},
            {"ticker": "BBB", "exit_day_idx": 10, "entry_contract_resolution": "nearest_listed_contract"},
            {"ticker": "CCC", "exit_day_idx": 11, "entry_contract_resolution": "exact_target_contract"},
        ]

        pool = wfo._closed_trades_for_calibration(trades, day_idx=10)

        self.assertEqual([trade["ticker"] for trade in pool], ["AAA"])

    def test_live_candidate_rank_ignores_non_dense_calibration_values(self):
        sparse_low = {
            "direction_score": 70.0,
            "quality_score": 65.0,
            "tech_score": 68.0,
            "calibrated_expectancy_pct": 5.0,
            "calibration_is_dense": False,
            "promotion_class": "research_sparse_calibration",
        }
        sparse_high = {
            **sparse_low,
            "calibrated_expectancy_pct": 55.0,
        }
        dense = {
            **sparse_low,
            "calibrated_expectancy_pct": 8.0,
            "calibration_is_dense": True,
            "promotion_class": "promotable_exact_contract",
        }

        self.assertEqual(oc._candidate_rank_tuple(sparse_low), oc._candidate_rank_tuple(sparse_high))
        ranked = sorted([sparse_high, dense], key=oc._candidate_rank_tuple, reverse=True)
        self.assertIs(ranked[0], dense)

    def test_live_candidate_rank_prefers_dense_expectancy_within_promotable_exact_cohort(self):
        lower_expectancy = {
            "direction_score": 82.0,
            "quality_score": 88.0,
            "tech_score": 84.0,
            "calibrated_expectancy_pct": 12.0,
            "calibration_is_dense": True,
            "promotion_class": "promotable_exact_contract",
        }
        higher_expectancy = {
            "direction_score": 71.0,
            "quality_score": 72.0,
            "tech_score": 70.0,
            "calibrated_expectancy_pct": 28.0,
            "calibration_is_dense": True,
            "promotion_class": "promotable_exact_contract",
        }

        ranked = sorted([lower_expectancy, higher_expectancy], key=oc._candidate_rank_tuple, reverse=True)
        self.assertIs(ranked[0], higher_expectancy)

    def test_trade_promotion_class_marks_nearest_sparse_and_bootstrap(self):
        promotable = {
            "entry_contract_resolution": "exact_target_contract",
            "selection_source": "replay_calibrated",
            "calibration_density": "dense",
        }
        nearest = {
            **promotable,
            "entry_contract_resolution": "nearest_listed_contract",
        }
        sparse = {
            **promotable,
            "calibration_density": "sparse",
        }
        bootstrap = {
            **promotable,
            "selection_source": "bootstrap_heuristic",
        }

        self.assertEqual(wfo._trade_promotion_class(promotable), "promotable_exact_contract")
        self.assertEqual(wfo._trade_promotion_class(nearest), "research_nearest_listed")
        self.assertEqual(wfo._trade_promotion_class(sparse), "research_sparse_calibration")
        self.assertEqual(wfo._trade_promotion_class(bootstrap), "research_bootstrap")

    def test_trade_calibration_density_does_not_promote_legacy_missing_density_rows(self):
        legacy = {
            "entry_contract_resolution": "exact_target_contract",
            "selection_source": "replay_calibrated",
            "calibration_is_dense": False,
        }
        missing_density = {
            "entry_contract_resolution": "exact_target_contract",
            "selection_source": "replay_calibrated",
        }

        self.assertEqual(wfo._trade_calibration_density(legacy), "sparse")
        self.assertEqual(wfo._trade_promotion_class(legacy), "research_sparse_calibration")
        self.assertEqual(wfo._trade_calibration_density(missing_density), "unknown")
        self.assertNotEqual(wfo._trade_promotion_class(missing_density), "promotable_exact_contract")

    def test_live_policy_splits_symbol_promotion_status(self):
        def _trade(ticker: str, pnl_pct: float) -> dict:
            return {
                "ticker": ticker,
                "type": "call",
                "direction_score": 72.0,
                "quality_score": 78.0,
                "tech_score": 80.0,
                "sector": "Index ETF",
                "market_regime": "bullish",
                "selection_source": "replay_calibrated",
                "calibration_density": "dense",
                "entry_contract_resolution": "exact_target_contract",
                "exit_reason": "target" if pnl_pct > 0 else "stop",
                "directional_correct": pnl_pct > 0,
                "pnl_pct": pnl_pct,
            }

        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 50,
            "unpriced_trade_count": 0,
            "trades": [*[_trade("SPY", 12.0) for _ in range(25)], *[_trade("QQQ", -6.0) for _ in range(25)]],
        }
        matrix = {
            "source": {
                "pricing_lane": "historical_imported_daily",
                "playbook": "short_term",
                "quote_coverage_pct": 100.0,
                "priced_trade_count": 50,
                "unpriced_trade_count": 0,
                "nearest_contract_match_count": 0,
            },
            "source_run_at": "2026-04-01T12:00:00",
            "source_mode": "backtest",
            "lookback_years": 1,
            "strategy_domain": "options",
            "trade_types": ["call"],
            "overall": {"profit_factor": 1.1},
            "by_category": {
                "score_bands": [],
                "asset_class_by_regime": [],
                "sector": [],
                "ticker": [],
            },
        }
        stability = {
            "overall_status": "watch",
            "promotion_recommendations": {"approved_filters": {}},
            "recommendations": [],
        }

        with patch.object(wfo, "build_options_experiment_matrix", return_value=matrix), \
             patch.object(wfo, "build_options_stability_report", return_value=stability):
            policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "watch")
        self.assertEqual(policy["by_symbol"]["SPY"]["promotion_metrics"]["promotion_status"], "promote")
        self.assertEqual(policy["by_symbol"]["QQQ"]["promotion_metrics"]["promotion_status"], "block")
        self.assertIn("stability_not_promote", policy["readiness_blockers"])
        self.assertEqual(policy["scan_policy"]["hard_filters"]["approved_tickers"], ["SPY"])

    def test_live_policy_blocks_when_exact_contract_subset_is_not_profitable(self):
        def _trade(*, pnl_pct: float, dense: bool) -> dict:
            return {
                "ticker": "SPY",
                "type": "call",
                "direction_score": 72.0,
                "quality_score": 78.0,
                "tech_score": 80.0,
                "sector": "Index ETF",
                "market_regime": "bullish",
                "selection_source": "replay_calibrated",
                "calibration_density": "dense" if dense else "sparse",
                "entry_contract_resolution": "exact_target_contract",
                "exit_reason": "target" if pnl_pct > 0 else "stop",
                "directional_correct": pnl_pct > 0,
                "pnl_pct": pnl_pct,
            }

        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 50,
            "unpriced_trade_count": 0,
            "trades": [*[_trade(pnl_pct=12.0, dense=True) for _ in range(25)], *[_trade(pnl_pct=-20.0, dense=False) for _ in range(25)]],
        }
        matrix = {
            "source": {
                "pricing_lane": "historical_imported_daily",
                "playbook": "short_term",
                "quote_coverage_pct": 100.0,
                "priced_trade_count": 50,
                "unpriced_trade_count": 0,
                "nearest_contract_match_count": 0,
            },
            "source_run_at": "2026-04-01T12:00:00",
            "source_mode": "backtest",
            "lookback_years": 1,
            "strategy_domain": "options",
            "trade_types": ["call"],
            "overall": {"profit_factor": 1.2},
            "by_category": {
                "score_bands": [],
                "asset_class_by_regime": [],
                "sector": [],
                "ticker": [],
            },
        }
        stability = {
            "overall_status": "promote",
            "promotion_recommendations": {"approved_filters": {}},
            "recommendations": [],
        }

        with patch.object(wfo, "build_options_experiment_matrix", return_value=matrix), \
             patch.object(wfo, "build_options_stability_report", return_value=stability):
            policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "block")
        self.assertFalse(policy["authoritative_profitability_gate"]["passed"])
        self.assertIn("authoritative_exact_profitability_not_clear", policy["readiness_blockers"])
        self.assertEqual(policy["scan_policy"]["hard_filters"]["approved_tickers"], [])
        self.assertEqual(policy["by_symbol"]["SPY"]["promotion_metrics"]["promotion_status"], "block")

    def test_live_policy_stays_watch_when_archived_evidence_is_insufficient(self):
        trade = {
            "ticker": "SPY",
            "type": "call",
            "direction_score": 72.0,
            "quality_score": 78.0,
            "tech_score": 80.0,
            "sector": "Index ETF",
            "market_regime": "bullish",
            "selection_source": "replay_calibrated",
            "calibration_density": "dense",
            "entry_contract_resolution": "exact_target_contract",
            "exit_reason": "target",
            "directional_correct": True,
            "pnl_pct": 12.0,
        }
        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 30,
            "unpriced_trade_count": 0,
            "trades": [dict(trade) for _ in range(30)],
            "preferred_evidence_source": {"status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS},
            "evidence_status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS,
        }
        matrix = {
            "source": {
                "pricing_lane": "historical_imported_daily",
                "playbook": "short_term",
                "quote_coverage_pct": 100.0,
                "priced_trade_count": 30,
                "unpriced_trade_count": 0,
                "nearest_contract_match_count": 0,
            },
            "source_run_at": "2026-04-01T12:00:00",
            "source_mode": "backtest",
            "lookback_years": 1,
            "strategy_domain": "options",
            "trade_types": ["call"],
            "overall": {"profit_factor": 1.2},
            "by_category": {
                "score_bands": [],
                "asset_class_by_regime": [],
                "sector": [],
                "ticker": [],
            },
        }
        stability = {
            "overall_status": "promote",
            "promotion_recommendations": {"approved_filters": {}},
            "recommendations": [],
        }

        with patch.object(wfo, "build_options_experiment_matrix", return_value=matrix), \
             patch.object(wfo, "build_options_stability_report", return_value=stability):
            policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "watch")
        self.assertEqual(policy["managed_lane_status"], "watch_only")
        self.assertIn(f"evidence_status:{wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS}", policy["readiness_blockers"])

    def test_live_policy_promotes_from_exact_subset_even_when_nearest_listed_replay_is_negative(self):
        trade_dates = pd.date_range("2025-01-02", periods=50, freq="B")

        def _trade(date_value: pd.Timestamp, ticker: str, pnl_pct: float, resolution: str) -> dict:
            return {
                "ticker": ticker,
                "date": str(date_value.date()),
                "type": "call",
                "direction_score": 72.0,
                "quality_score": 78.0,
                "tech_score": 80.0,
                "sector": "Index ETF",
                "market_regime": "bullish",
                "selection_source": "replay_calibrated",
                "calibration_density": "dense",
                "entry_contract_resolution": resolution,
                "exit_reason": "target" if pnl_pct > 0 else "stop",
                "directional_correct": pnl_pct > 0,
                "pnl_pct": pnl_pct,
            }

        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 50,
            "unpriced_trade_count": 0,
            "exact_contract_match_count": 25,
            "nearest_contract_match_count": 25,
            "trades": [
                *[
                    _trade(trade_dates[idx], "SPY", 12.0, "exact_target_contract")
                    for idx in range(25)
                ],
                *[
                    _trade(trade_dates[idx + 25], "QQQ", -20.0, "nearest_listed_contract")
                    for idx in range(25)
                ],
            ],
        }

        policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "promote")
        self.assertEqual(policy["managed_lane_status"], "open")
        self.assertEqual(policy["authoritative_profitability_lens"], "exact_contract_only")
        self.assertEqual(policy["authoritative_profitability_metrics"]["trade_count"], 25)
        self.assertEqual(policy["authoritative_exact_contract_metrics"]["trade_count"], 25)
        self.assertEqual(policy["nearest_listed_metrics"]["trade_count"], 25)
        self.assertEqual(policy["scan_policy"]["hard_filters"]["approved_tickers"], ["SPY"])
        self.assertNotIn("authoritative_exact_profitability_not_clear", policy["readiness_blockers"])

    def test_live_policy_blocks_when_only_nearest_listed_subset_is_profitable(self):
        trade_dates = pd.date_range("2025-01-02", periods=50, freq="B")

        def _trade(date_value: pd.Timestamp, ticker: str, pnl_pct: float, resolution: str) -> dict:
            return {
                "ticker": ticker,
                "date": str(date_value.date()),
                "type": "call",
                "direction_score": 72.0,
                "quality_score": 78.0,
                "tech_score": 80.0,
                "sector": "Index ETF",
                "market_regime": "bullish",
                "selection_source": "replay_calibrated",
                "calibration_density": "dense",
                "entry_contract_resolution": resolution,
                "exit_reason": "target" if pnl_pct > 0 else "stop",
                "directional_correct": pnl_pct > 0,
                "pnl_pct": pnl_pct,
            }

        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 50,
            "unpriced_trade_count": 0,
            "exact_contract_match_count": 25,
            "nearest_contract_match_count": 25,
            "trades": [
                *[
                    _trade(trade_dates[idx], "SPY", -8.0, "exact_target_contract")
                    for idx in range(25)
                ],
                *[
                    _trade(trade_dates[idx + 25], "QQQ", 20.0, "nearest_listed_contract")
                    for idx in range(25)
                ],
            ],
        }

        policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "block")
        self.assertEqual(policy["managed_lane_status"], "blocked_no_approved_symbols")
        self.assertEqual(policy["authoritative_profitability_lens"], "exact_contract_only")
        self.assertEqual(policy["authoritative_profitability_metrics"]["trade_count"], 25)
        self.assertEqual(policy["authoritative_exact_contract_metrics"]["profit_factor"], 0.0)
        self.assertGreater(policy["nearest_listed_metrics"]["profit_factor"], 1.0)
        self.assertIn("authoritative_exact_profitability_not_clear", policy["readiness_blockers"])
        self.assertEqual(policy["scan_policy"]["hard_filters"]["approved_tickers"], [])

    def test_live_policy_marks_truth_window_stale_and_blocks_managed_lane(self):
        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "candidate_source": wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
            "quote_coverage_pct": 0.0,
            "priced_trade_count": 0,
            "unpriced_trade_count": 0,
            "primary_judge_trade_class": "exact_archived_contract",
            "primary_judge_trade_count": 0,
            "pending_truth_horizon_count": 4,
            "trades": [],
            "preferred_evidence_source": {
                "mode": "archived_forward_daily",
                "status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS,
                "truth_window_status": "stale",
            },
            "evidence_status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS,
            "truth_window_status": "stale",
            "authoritative_evidence_source": "archived_forward_daily",
            "authoritative_evidence_status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS,
        }
        matrix = {
            "source": {
                "pricing_lane": "historical_imported_daily",
                "playbook": "short_term",
                "quote_coverage_pct": 0.0,
                "priced_trade_count": 0,
                "unpriced_trade_count": 0,
                "nearest_contract_match_count": 0,
                "candidate_source": wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
                "evidence_status": wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS,
                "truth_window_status": "stale",
            },
            "source_run_at": "2026-04-01T12:00:00",
            "source_mode": "backtest",
            "lookback_years": 1,
            "strategy_domain": "options",
            "trade_types": ["call"],
            "overall": {"profit_factor": 0.0},
            "by_category": {
                "score_bands": [],
                "asset_class_by_regime": [],
                "sector": [],
                "ticker": [],
            },
        }
        stability = {
            "overall_status": "promote",
            "promotion_recommendations": {"approved_filters": {}},
            "recommendations": [],
        }
        fallback_watch_source = {
            "by_symbol": {
                "SPY": {"exact_contract_metrics": {"trade_count": 25, "profit_factor": 1.2, "avg_pnl_pct": 4.15}},
                "QQQ": {"exact_contract_metrics": {"trade_count": 32, "profit_factor": 0.52, "avg_pnl_pct": -17.41}},
            }
        }

        with patch.object(wfo, "build_options_experiment_matrix", return_value=matrix), \
             patch.object(wfo, "build_options_stability_report", return_value=stability), \
             patch.object(wfo, "load_last_imported_daily_results", return_value=fallback_watch_source):
            policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["truth_window_status"], "stale")
        self.assertEqual(policy["managed_lane_status"], "blocked_truth_stale")
        self.assertEqual(policy["promotion_status"], "block")
        self.assertEqual(policy["authoritative_evidence_source"], "archived_forward_daily")
        self.assertEqual(policy["authoritative_evidence_status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)
        self.assertEqual(policy["watch_priority_symbols"], ["SPY"])
        self.assertEqual(policy["watch_deprioritized_symbols"], ["QQQ"])
        self.assertIn("truth_window_stale", policy["readiness_blockers"])

    def test_live_policy_requires_exact_directional_accuracy_for_promotion(self):
        def _trade(directionally_correct: bool, pnl_pct: float) -> dict:
            return {
                "ticker": "SPY",
                "type": "call",
                "direction_score": 72.0,
                "quality_score": 78.0,
                "tech_score": 80.0,
                "sector": "Index ETF",
                "market_regime": "bullish",
                "selection_source": "replay_calibrated",
                "calibration_density": "dense",
                "entry_contract_resolution": "exact_target_contract",
                "exit_reason": "target" if pnl_pct > 0 else "stop",
                "directional_correct": directionally_correct,
                "pnl_pct": pnl_pct,
            }

        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 25,
            "unpriced_trade_count": 0,
            "trades": [
                *[_trade(True, 12.0) for _ in range(10)],
                *[_trade(False, -1.0) for _ in range(15)],
            ],
        }
        matrix = {
            "source": {
                "pricing_lane": "historical_imported_daily",
                "playbook": "short_term",
                "quote_coverage_pct": 100.0,
                "priced_trade_count": 25,
                "unpriced_trade_count": 0,
                "nearest_contract_match_count": 0,
            },
            "source_run_at": "2026-04-01T12:00:00",
            "source_mode": "backtest",
            "lookback_years": 1,
            "strategy_domain": "options",
            "trade_types": ["call"],
            "overall": {"profit_factor": 8.0, "avg_pnl_pct": 4.2},
            "aggregate_overall": {"profit_factor": 8.0, "avg_pnl_pct": 4.2},
            "by_category": {
                "score_bands": [],
                "asset_class_by_regime": [],
                "sector": [],
                "ticker": [],
            },
        }
        stability = {
            "overall_status": "promote",
            "promotion_recommendations": {"approved_filters": {}},
            "recommendations": [],
        }

        with patch.object(wfo, "build_options_experiment_matrix", return_value=matrix), \
             patch.object(wfo, "build_options_stability_report", return_value=stability):
            policy = wfo.build_live_options_trade_policy(result=result, min_trades=1)

        self.assertEqual(policy["promotion_status"], "block")
        self.assertIn("authoritative_exact_profitability_not_clear", policy["readiness_blockers"])
        self.assertEqual(
            policy["authoritative_profitability_gate"]["thresholds"]["min_directional_accuracy_pct"],
            50.0,
        )
        self.assertFalse(policy["authoritative_profitability_gate"]["passed"])

    def test_experiment_matrix_uses_exact_contract_authoritative_lens(self):
        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "trades": [
                {
                    "ticker": "SPY",
                    "type": "call",
                    "direction_score": 80.0,
                    "sector": "Index ETF",
                    "market_regime": "bullish",
                    "entry_contract_resolution": "exact_target_contract",
                    "directional_correct": False,
                    "pnl_pct": -10.0,
                },
                {
                    "ticker": "QQQ",
                    "type": "call",
                    "direction_score": 78.0,
                    "sector": "Index ETF",
                    "market_regime": "bullish",
                    "entry_contract_resolution": "exact_target_contract",
                    "directional_correct": False,
                    "pnl_pct": -10.0,
                },
                *[
                    {
                        "ticker": "SPY",
                        "type": "call",
                        "direction_score": 82.0,
                        "sector": "Index ETF",
                        "market_regime": "bullish",
                        "entry_contract_resolution": "nearest_listed_contract",
                        "directional_correct": True,
                        "pnl_pct": 12.0,
                    }
                    for _ in range(8)
                ],
            ],
        }

        matrix = wfo.build_options_experiment_matrix(result=result, min_trades=1)

        self.assertEqual(matrix["authoritative_profitability_lens"], "exact_contract_only")
        self.assertEqual(matrix["overall"]["trades"], 2)
        self.assertLess(matrix["overall"]["avg_pnl_pct"], 0.0)
        self.assertEqual(matrix["aggregate_overall"]["trades"], 10)
        self.assertGreater(matrix["aggregate_overall"]["avg_pnl_pct"], 0.0)
        self.assertFalse(matrix["authoritative_profitability_gate"]["passed"])

    def test_supervised_policy_ranking_prefers_dense_expectancy_after_decision(self):
        policy = {
            "watch_priority_symbols": ["SPY"],
            "watch_deprioritized_symbols": ["QQQ"],
            "scan_policy": {
                "promotion_status": "promote",
                "hard_filters": {
                    "direction_score_min": 0.0,
                    "tech_score_min": 0.0,
                    "approved_tickers": ["SPY", "QQQ"],
                },
                "preferred_filters": {},
            }
        }
        higher_score_lower_ev = {
            "ticker": "SPY",
            "direction": "call",
            "asset_class": "index",
            "market_regime": "bullish",
            "sector": "Index ETF",
            "direction_score": 82.0,
            "quality_score": 82.0,
            "tech_score": 82.0,
            "promotion_class": "promotable_exact_contract",
            "calibration_is_dense": True,
            "calibrated_expectancy_pct": 12.0,
        }
        lower_score_higher_ev = {
            **higher_score_lower_ev,
            "ticker": "QQQ",
            "direction_score": 70.0,
            "quality_score": 70.0,
            "tech_score": 70.0,
            "calibrated_expectancy_pct": 28.0,
        }

        ranked = ss.apply_trade_policy_to_scan(
            [higher_score_lower_ev, lower_score_higher_ev],
            policy=policy,
            include_blocked=False,
        )["ranked_picks"]

        self.assertEqual([pick["ticker"] for pick in ranked], ["QQQ", "SPY"])

    def test_supervised_policy_watch_priority_prefers_spy_over_qqq(self):
        policy = {
            "watch_priority_symbols": ["SPY"],
            "watch_deprioritized_symbols": ["QQQ"],
            "scan_policy": {
                "promotion_status": "watch",
                "hard_filters": {
                    "direction_score_min": 0.0,
                    "tech_score_min": 0.0,
                    "approved_tickers": [],
                },
                "preferred_filters": {},
                "watch_priority_symbols": ["SPY"],
                "watch_deprioritized_symbols": ["QQQ"],
            },
        }
        spy = {
            "ticker": "SPY",
            "direction": "call",
            "asset_class": "index",
            "market_regime": "bullish",
            "sector": "Index ETF",
            "direction_score": 72.0,
            "quality_score": 72.0,
            "tech_score": 72.0,
            "promotion_class": "promotable_exact_contract",
            "calibration_is_dense": True,
            "calibrated_expectancy_pct": 18.0,
        }
        qqq = {
            **spy,
            "ticker": "QQQ",
        }

        ranked = ss.apply_trade_policy_to_scan([qqq, spy], policy=policy, include_blocked=False)["ranked_picks"]

        self.assertEqual([pick["ticker"] for pick in ranked], ["SPY", "QQQ"])

    def test_run_supervised_scan_returns_approved_only_picks_and_separate_watch_picks(self):
        class _AvailablePositionsRepo:
            is_available = True

            def list_positions(self, status: str):
                return []

        approved_pick = {
            "ticker": "SPY",
            "direction": "call",
            "asset_class": "index",
            "sector": "Index ETF",
            "market_regime": "bullish",
            "spy_ret5": 1.1,
            "direction_score": 75.0,
            "quality_score": 74.0,
            "tech_score": 72.0,
            "promotion_class": "promotable_exact_contract",
            "promotable": True,
            "selection_source": "live_chain_exact_contract",
            "contract_selection_source": "live_chain_exact_contract",
            "options_snapshot_status": "fresh",
            "option_chain_status": "fresh",
            "calibration_is_dense": True,
            "calibrated_expectancy_pct": 18.0,
            "type": "daily_scan",
            "dte": 7,
        }
        watch_pick = {
            **approved_pick,
            "ticker": "QQQ",
            "selection_source": "model_contract_fallback",
            "contract_selection_source": "model_contract_fallback",
            "promotion_class": "research_bootstrap",
            "promotable": False,
            "calibration_is_dense": False,
            "calibrated_expectancy_pct": None,
        }
        policy = {
            "promotion_status": "promote",
            "managed_lane_status": "open",
            "truth_window_status": "current",
            "authoritative_evidence_source": "archived_forward_daily",
            "authoritative_evidence_status": wfo.ARCHIVED_EXACT_PRIMARY_STATUS,
            "watch_priority_symbols": ["SPY"],
            "watch_deprioritized_symbols": ["QQQ"],
            "scan_policy": {
                "promotion_status": "promote",
                "managed_lane_status": "open",
                "truth_window_status": "current",
                "hard_filters": {
                    "direction_score_min": 0.0,
                    "tech_score_min": 0.0,
                    "approved_tickers": ["SPY"],
                },
                "preferred_filters": {},
                "watch_priority_symbols": ["SPY"],
                "watch_deprioritized_symbols": ["QQQ"],
            },
        }

        with patch.object(ss, "build_live_options_trade_policy", return_value=policy), \
             patch.object(ss, "build_playbook_exit_audit", return_value={"playbook": "short_term"}):
            result = ss.run_supervised_scan(
                scan_func=lambda **_: [approved_pick, watch_pick],
                positions_repository=_AvailablePositionsRepo(),
                n_picks=2,
                watchlist_size=2,
                playbook_id="short_term",
                use_recommended_policy=True,
                truth_lane=wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                min_trades=1,
            )

        self.assertTrue(result["policy_applied"])
        self.assertEqual([pick["ticker"] for pick in result["picks"]], ["SPY"])
        self.assertEqual([pick["ticker"] for pick in result["watch_picks"]], ["QQQ"])
        self.assertTrue(result["picks"][0]["managed_eligible"])
        self.assertFalse(result["watch_picks"][0]["managed_eligible"])
        self.assertEqual(result["watch_picks"][0]["managed_block_reason"], "promotion_class:research_bootstrap")

    def test_scan_daily_top_trades_skips_equity_when_earnings_lookup_fails(self):
        with patch.object(oc, "DEFAULT_WATCHLIST", ["AAA", "SPY"]), \
             patch.object(oc.yf, "Ticker", side_effect=lambda symbol: _ScanTicker(symbol)), \
             patch.object(oc, "_market_is_open", return_value=False), \
             patch.object(
                 oc,
                 "_cached_earnings_dates",
                 side_effect=lambda symbol: (_ for _ in ()).throw(RuntimeError("earnings unavailable"))
                 if str(symbol).upper() == "AAA"
                 else pd.DataFrame(),
             ):
            picks = oc.scan_daily_top_trades(n_picks=3)

        self.assertNotIn("AAA", {pick["ticker"] for pick in picks})

    def test_preferred_loader_uses_archived_forward_daily_result_before_model_daily(self):
        archived = {
            "truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE,
            "candidate_source": wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
            "primary_judge_trade_class": "exact_archived_contract",
            "primary_judge_trade_count": 30,
        }
        fallback = {"truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE}
        with patch.object(wfo, "load_last_archived_forward_daily_results", return_value=archived), \
             patch.object(wfo, "load_last_imported_daily_results", return_value=fallback):
            preferred = wfo.load_preferred_results_by_truth_lane(wfo.IMPORTED_DAILY_TRUTH_SOURCE)

        self.assertEqual(preferred["candidate_source"], wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE)
        self.assertEqual(preferred["preferred_evidence_source"]["mode"], "archived_forward_daily")
        self.assertFalse(preferred["preferred_evidence_source"]["fallback_used"])
        self.assertEqual(preferred["preferred_evidence_source"]["status"], wfo.ARCHIVED_EXACT_PRIMARY_STATUS)
        self.assertEqual(preferred["evidence_status"], wfo.ARCHIVED_EXACT_PRIMARY_STATUS)

    def test_preferred_loader_keeps_archived_forward_primary_when_insufficient(self):
        fallback = {"truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE}
        with patch.object(
            wfo,
            "load_last_archived_forward_daily_results",
            return_value={
                "truth_source": wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                "candidate_source": wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
                "insufficient_archived_evidence": True,
                "status": "insufficient_archived_evidence",
                "pending_truth_horizon_count": 3,
            },
        ), \
             patch.object(wfo, "load_last_imported_daily_results", return_value=fallback):
            preferred = wfo.load_preferred_results_by_truth_lane(wfo.IMPORTED_DAILY_TRUTH_SOURCE)

        self.assertEqual(preferred["truth_source"], wfo.IMPORTED_DAILY_TRUTH_SOURCE)
        self.assertEqual(preferred["preferred_evidence_source"]["mode"], "archived_forward_daily")
        self.assertFalse(preferred["preferred_evidence_source"]["fallback_used"])
        self.assertEqual(preferred["preferred_evidence_source"]["status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)
        self.assertEqual(preferred["truth_window_status"], "stale")


if __name__ == "__main__":
    unittest.main()
