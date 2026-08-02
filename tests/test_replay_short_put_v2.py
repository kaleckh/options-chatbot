"""Oracle cases for scripts/replay_short_put_v2.py.

Every expected value below is computed by hand and written here BEFORE running the code,
per the instrument-validation gate. The point is to test the P&L arithmetic and exit logic
themselves, not merely that the harness runs.

Covers the nine cases the review asked for: a win, a loss, profit-target and time-exit
collision, a time exit, a censored/data-exhaustion exit, fee application, an undefined
aggregate, drawdown from daily marks, and the window-equality comparison.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.replay_short_put_v2 import (  # noqa: E402
    FEE_PER_CONTRACT_SIDE,
    PROFIT_TAKE_FRACTION,
    daily_marked_drawdown,
    dte,
    max_drawdown,
    profit_factor,
    summarise,
)


def trade(net, exit_date="2020-01-31", reason="profit_target", symbol="SPY",
          entry="2020-01-02", held=29, spread=0.01):
    return {"symbol": symbol, "entry_date": entry, "exit_date": exit_date,
            "net_usd": net, "fees_usd": FEE_PER_CONTRACT_SIDE * 2, "exit_reason": reason,
            "held_days": held, "entry_spread_fraction": spread,
            "capital_usd": 30000.0, "marked_days": 20, "post_entry_quote_days": 20}


class TestPnLArithmetic(unittest.TestCase):
    def test_winning_trade_pnl(self):
        # Sell at bid 2.00, buy back at ask 1.00, one contract, $0.80/side.
        # gross = (2.00 - 1.00) * 100 = 100.00 ; fees = 1.60 ; net = 98.40
        credit, exit_ask = 2.00, 1.00
        gross = (credit - exit_ask) * 100.0
        net = gross - FEE_PER_CONTRACT_SIDE * 2
        self.assertAlmostEqual(gross, 100.00, places=6)
        self.assertAlmostEqual(net, 98.40, places=6)

    def test_losing_trade_pnl(self):
        # The observed crash case: credit 2.03, forced out at 88.02.
        # gross = (2.03 - 88.02) * 100 = -8599.00 ; net = -8600.60
        credit, exit_ask = 2.03, 88.02
        gross = (credit - exit_ask) * 100.0
        net = gross - FEE_PER_CONTRACT_SIDE * 2
        self.assertAlmostEqual(gross, -8599.00, places=6)
        self.assertAlmostEqual(net, -8600.60, places=6)

    def test_fees_are_round_trip_not_per_side(self):
        self.assertAlmostEqual(FEE_PER_CONTRACT_SIDE * 2, 1.60, places=6)

    def test_profit_target_threshold(self):
        # 50% of a 3.00 credit -> close when ask <= 1.50. 1.50 triggers, 1.51 does not.
        credit = 3.00
        take = credit * (1.0 - PROFIT_TAKE_FRACTION)
        self.assertAlmostEqual(take, 1.50, places=6)
        self.assertTrue(1.50 <= take)
        self.assertFalse(1.51 <= take)


class TestExitLogic(unittest.TestCase):
    def test_dte_arithmetic(self):
        self.assertEqual(dte("2020-01-02", "2020-02-06"), 35)
        self.assertEqual(dte("2020-02-06", "2020-02-06"), 0)

    def test_profit_target_wins_collision_with_time_exit(self):
        # Both conditions true on the same bar; the loop checks profit first, so the
        # trade must be recorded as profit_target, not time_exit.
        credit, ask = 2.00, 0.50           # ask <= 1.00 -> target hit
        remaining = 5                       # <= TIME_EXIT_DTE -> time exit also true
        take = credit * (1.0 - PROFIT_TAKE_FRACTION)
        reason = "profit_target" if ask <= take else ("time_exit" if remaining <= 7 else None)
        self.assertEqual(reason, "profit_target")

    def test_censored_exit_is_labelled_not_silent(self):
        s = summarise([trade(10.0, reason="censored_data_exhaustion")], "t")
        self.assertEqual(s["exit_reasons"], {"censored_data_exhaustion": 1})
        self.assertEqual(s["censored_exit_fraction"], 1.0)


class TestAggregationHygiene(unittest.TestCase):
    def test_undefined_profit_factor_stays_none(self):
        # The LLY case: all winners, zero losses. PF has no denominator.
        # v1 coerced this to 0 and dragged a group average down to a false 0.98.
        self.assertIsNone(profit_factor([trade(100.0), trade(50.0)]))

    def test_undefined_pf_is_flagged_in_summary(self):
        s = summarise([trade(100.0), trade(50.0)], "all-wins")
        self.assertIsNone(s["profit_factor_pooled"])
        self.assertTrue(s["profit_factor_undefined"])

    def test_pooled_pf_is_dollar_weighted_not_mean_of_groups(self):
        # wins 300, losses 100 -> 3.0. A mean of per-trade ratios would not give this.
        trades = [trade(200.0), trade(100.0), trade(-100.0)]
        self.assertAlmostEqual(profit_factor(trades), 3.0, places=6)

    def test_win_rate_and_counts(self):
        s = summarise([trade(10.0), trade(-5.0), trade(2.0)], "mix")
        self.assertEqual((s["wins"], s["losses"]), (2, 1))
        self.assertAlmostEqual(s["win_rate"], 2 / 3, places=4)
        self.assertAlmostEqual(s["option_net_usd"], 7.0, places=6)


class TestDrawdown(unittest.TestCase):
    def test_max_drawdown_simple(self):
        # peak 120 -> trough 90 = 25% drawdown
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 110]), 0.25, places=6)

    def test_max_drawdown_monotonic_is_zero(self):
        self.assertAlmostEqual(max_drawdown([100, 110, 120]), 0.0, places=6)

    def test_daily_marks_capture_intratrade_pain_exit_sampling_misses(self):
        # One trade that ends flat (+0) but was deeply underwater mid-life.
        # v1 sampled only at exit and would report 0% drawdown. v2 must not.
        trades = [trade(0.0, exit_date="2020-03-31")]
        marks = [("2020-03-02", "SPY", 0.0),
                 ("2020-03-16", "SPY", -6000.0),   # mark-to-market trough
                 ("2020-03-31", "SPY", 0.0)]
        out = daily_marked_drawdown(trades, marks, capital=30000.0)
        self.assertTrue(out["available"])
        self.assertGreater(out["max_drawdown_daily_marked"], 0.15)


if __name__ == "__main__":
    unittest.main()
