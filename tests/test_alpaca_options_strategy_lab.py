from __future__ import annotations

import unittest
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_alpaca_options_strategy_lab import (  # noqa: E402
    LANE_PRESETS,
    SimulatedTrade,
    _build_candidates,
    _lane_arg,
    _lane_report,
)


def _trade(*, entry_date: date, exact: bool = True, pnl_pct: float = 10.0) -> SimulatedTrade:
    return SimulatedTrade(
        lane="bullish",
        structure="call_debit_spread",
        symbol="SPY",
        entry_date=entry_date.isoformat(),
        exit_date=(entry_date + timedelta(days=10)).isoformat(),
        expiry=(entry_date + timedelta(days=35)).isoformat(),
        pnl_pct=pnl_pct,
        pnl_usd=pnl_pct,
        risk_usd=100.0,
        entry_value=1.0,
        exit_value=1.1,
        gross_pnl_usd=pnl_pct,
        fees_usd=2.6,
        evidence_level="exact_bid_ask" if exact else "alpaca_opra_historical_bars_no_bidask",
        data_source="local_daily_exact_bid_ask" if exact else "alpaca_opra_historical_bars",
        exact_bid_ask=exact,
        option_bar_fallback=not exact,
        legs=[],
        signal={},
        exit_reason="test",
    )


class AlpacaOptionsStrategyLabTests(unittest.TestCase):
    def test_lane_preset_overrides_default_arguments(self):
        args = SimpleNamespace(preset="spy_qqq_exact", hold_days=10, width_pct=0.025)

        self.assertEqual(_lane_arg(args, "bullish", "variant", "baseline"), "pullback_uptrend")
        self.assertEqual(_lane_arg(args, "bullish", "hold_days", args.hold_days), 15)
        self.assertEqual(_lane_arg(args, "bearish", "width_pct", args.width_pct), 0.08)
        self.assertIn("sideways", LANE_PRESETS["spy_qqq_exact"])

    def test_lane_report_promotes_only_exact_bid_ask_oos_positive_trades(self):
        trades = []
        for idx in range(30):
            trades.append(_trade(entry_date=date(2024, 2, 1) + timedelta(days=idx * 7), pnl_pct=8.0))
        for idx in range(25):
            trades.append(_trade(entry_date=date(2025, 7, 1) + timedelta(days=idx * 7), pnl_pct=6.0))

        report = _lane_report(
            "bullish",
            trades,
            rejected={},
            oos_start=date(2025, 7, 1),
            min_total_trades=50,
            min_oos_trades=20,
            min_profit_factor=1.15,
            preferred_profit_factor=1.25,
        )

        self.assertTrue(report["promotion_allowed"])
        self.assertTrue(report["gates"]["min_50_exact_trades"])
        self.assertTrue(report["gates"]["min_oos_exact_trades"])
        self.assertEqual(report["exact_bid_ask_proof_summary"]["trade_count"], 55)

    def test_lane_report_keeps_bar_only_trades_research_only(self):
        trades = [_trade(entry_date=date(2025, 7, 1) + timedelta(days=idx), exact=False) for idx in range(60)]

        report = _lane_report(
            "bullish",
            trades,
            rejected={},
            oos_start=date(2025, 7, 1),
            min_total_trades=50,
            min_oos_trades=20,
            min_profit_factor=1.15,
            preferred_profit_factor=1.25,
        )

        self.assertFalse(report["promotion_allowed"])
        self.assertFalse(report["gates"]["min_50_exact_trades"])
        self.assertEqual(report["all_trade_summary"]["bar_fallback_count"], 60)

    def test_pullback_uptrend_variant_selects_defined_bullish_candidate(self):
        frame = pd.DataFrame(
            [
                {
                    "Close": 100.0,
                    "sma20": 101.0,
                    "sma50": 95.0,
                    "ret5": -1.5,
                    "ret10": -0.5,
                    "ret20": 5.0,
                    "vol20": 0.18,
                    "range_pct20": 1.0,
                }
            ],
            index=[date(2024, 2, 2)],
        )

        candidates, rejected = _build_candidates(
            {"SPY": frame},
            lane="bullish",
            variant="pullback_uptrend",
            start=date(2024, 2, 1),
            end=date(2024, 2, 29),
            max_per_week=1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].signal["variant"], "pullback_uptrend")
        self.assertEqual(rejected["bullish_signal_filter"], 0)


if __name__ == "__main__":
    unittest.main()
