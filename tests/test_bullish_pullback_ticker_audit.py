from __future__ import annotations

import unittest

from scripts import audit_bullish_pullback_ticker_evidence as ticker_audit
from scripts.audit_bullish_pullback_ticker_evidence import classify_ticker


class BullishPullbackTickerAuditTests(unittest.TestCase):
    def test_classify_keeps_s_tier_symbol_in_current_lane(self):
        decision, lane, rationale = classify_ticker(
            "AAPL",
            {"exact_trade_count": 11, "candidate_trade_count": 13, "exact_profit_factor": 3.0, "exact_avg_pnl_pct": 30.0},
            {"best_tier": "S"},
        )

        self.assertEqual(decision, "keep-in-current-lane")
        self.assertEqual(lane, "bullish_pullback_observation")
        self.assertIn("S/A/B", rationale)

    def test_classify_moves_strategic_high_beta_failure_to_new_lane(self):
        decision, lane, _ = classify_ticker(
            "NVDA",
            {
                "exact_trade_count": 5,
                "candidate_trade_count": 7,
                "exact_profit_factor": 0.15,
                "exact_avg_pnl_pct": -38.0,
                "quote_coverage_pct": 71.4,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "move-to-different-lane")
        self.assertEqual(lane, "high_beta_momentum_volatility")

    def test_classify_removes_fully_priced_strategic_loser(self):
        decision, lane, _ = classify_ticker(
            "PLTR",
            {
                "exact_trade_count": 10,
                "candidate_trade_count": 10,
                "exact_profit_factor": 0.36,
                "exact_avg_pnl_pct": -17.4,
                "quote_coverage_pct": 100.0,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "remove")
        self.assertEqual(lane, "")

    def test_classify_removes_repeated_current_lane_loser(self):
        decision, lane, _ = classify_ticker(
            "ABBV",
            {
                "exact_trade_count": 10,
                "candidate_trade_count": 14,
                "exact_profit_factor": 0.63,
                "exact_avg_pnl_pct": -20.0,
                "quote_coverage_pct": 71.4,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "remove")
        self.assertEqual(lane, "")

    def test_classify_removes_six_trade_negative_sample(self):
        decision, lane, _ = classify_ticker(
            "RTX",
            {
                "exact_trade_count": 6,
                "candidate_trade_count": 12,
                "exact_profit_factor": 0.79,
                "exact_avg_pnl_pct": -2.9,
                "quote_coverage_pct": 50.0,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "remove")
        self.assertEqual(lane, "")

    def test_classify_removes_deep_negative_sample_even_with_low_coverage(self):
        decision, lane, _ = classify_ticker(
            "SLB",
            {
                "exact_trade_count": 6,
                "candidate_trade_count": 19,
                "exact_profit_factor": 0.23,
                "exact_avg_pnl_pct": -46.5,
                "quote_coverage_pct": 31.6,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "remove")
        self.assertEqual(lane, "")

    def test_classify_moves_thin_positive_index_etf_to_scout_lane(self):
        decision, lane, _ = classify_ticker(
            "QQQ",
            {
                "exact_trade_count": 2,
                "candidate_trade_count": 3,
                "exact_profit_factor": 124.0,
                "exact_avg_pnl_pct": 62.0,
                "quote_coverage_pct": 66.7,
            },
            {"best_tier": "C"},
        )

        self.assertEqual(decision, "move-to-different-lane")
        self.assertEqual(lane, "index_etf_control")

    def test_classify_keeps_thin_non_promoted_symbol_as_research(self):
        decision, lane, _ = classify_ticker(
            "KO",
            {
                "exact_trade_count": 2,
                "candidate_trade_count": 6,
                "exact_profit_factor": 19.0,
                "exact_avg_pnl_pct": 20.0,
                "quote_coverage_pct": 33.3,
            },
            {"best_tier": None},
        )

        self.assertEqual(decision, "research-only/data-needed")
        self.assertEqual(lane, "defensive_income")

    def test_n_floor_label_freezes_legacy_queue_disposition_below_30_exact(self):
        self.assertEqual(ticker_audit._n_floor_disposition("keep-in-current-lane", 2), "insufficient_n_frozen")
        self.assertFalse(ticker_audit._queue_change_allowed("remove", 29))
        self.assertEqual(ticker_audit._n_floor_disposition("remove", 30), "remove")
        self.assertTrue(ticker_audit._queue_change_allowed("remove", 30))

    def test_lane_parent_expectancy_is_trade_weighted(self):
        parent = ticker_audit._lane_parent_expectancy(
            {
                "AAA": {"exact_trade_count": 2, "exact_avg_pnl_pct": 100.0},
                "BBB": {"exact_trade_count": 8, "exact_avg_pnl_pct": 0.0},
            }
        )

        self.assertEqual(parent["trade_count"], 10)
        self.assertEqual(parent["avg_pnl_pct"], 20.0)


if __name__ == "__main__":
    unittest.main()
