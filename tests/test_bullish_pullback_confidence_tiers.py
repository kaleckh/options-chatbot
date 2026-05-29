from __future__ import annotations

import unittest

from scripts.analyze_bullish_pullback_confidence_tiers import (
    _is_exact_quoted_trade,
    confidence_score,
    metrics,
)


def _trade(**overrides):
    trade = {
        "ticker": "AAPL",
        "date": "2026-01-05",
        "type": "call",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "exit_fill_basis": "imported_spread_mark",
        "exit_reason": "time_exit",
        "priced": True,
        "direction_score": 86.0,
        "quality_score": 84.0,
        "tech_score": 83.0,
        "signal_ret20": 9.0,
        "signal_ret5": -1.0,
        "tradability_score": 95.0,
        "long_prior_quote_days": 12,
        "short_prior_quote_days": 11,
        "short_delta_val": 0.24,
        "avg_volume_20d": 18_000_000,
        "promotion_class": "research_bootstrap",
        "pnl_pct": 42.0,
    }
    trade.update(overrides)
    return trade


class BullishPullbackConfidenceTierTests(unittest.TestCase):
    def test_exact_quoted_trade_requires_time_exit_and_imported_spread_mark(self):
        self.assertTrue(_is_exact_quoted_trade(_trade()))
        self.assertFalse(_is_exact_quoted_trade(_trade(exit_fill_basis="expiration_intrinsic")))
        self.assertFalse(_is_exact_quoted_trade(_trade(entry_contract_resolution="nearest_listed_contract")))

    def test_confidence_score_marks_strong_exact_trade_as_s_tier(self):
        source = {"role": "S_reference", "evidence_points": 15}

        scored = confidence_score(_trade(), source)

        self.assertEqual(scored["confidence_tier"], "S")
        self.assertGreaterEqual(scored["confidence_score"], 80.0)
        self.assertEqual(scored["evidence_cap"], "research_bootstrap")
        self.assertEqual(scored["blockers"], [])

    def test_confidence_score_caps_low_ret20_to_scout(self):
        source = {"role": "S_reference", "evidence_points": 15}

        scored = confidence_score(_trade(signal_ret20=2.0), source)

        self.assertEqual(scored["confidence_tier"], "C")
        self.assertIn("signal_ret20_below_4", scored["blockers"])

    def test_metrics_calculates_profit_factor_and_symbol_count(self):
        row = metrics(
            [
                _trade(ticker="AAPL", pnl_pct=20.0),
                _trade(ticker="MSFT", pnl_pct=-10.0),
                _trade(ticker="MSFT", pnl_pct=5.0),
            ]
        )

        self.assertEqual(row["trade_count"], 3)
        self.assertEqual(row["symbol_count"], 2)
        self.assertEqual(row["profit_factor"], 2.5)
        self.assertEqual(row["avg_pnl_pct"], 5.0)


if __name__ == "__main__":
    unittest.main()
