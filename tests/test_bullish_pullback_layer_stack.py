from __future__ import annotations

import unittest

from scripts.build_bullish_pullback_layer_stack import (
    _is_trusted_exact_opra_trade,
    classify_layer_status,
)


def _trade(**overrides):
    trade = {
        "priced": True,
        "entry_contract_resolution": "exact_listed_spread_contract",
        "exit_fill_basis": "imported_spread_mark",
    }
    trade.update(overrides)
    return trade


class BullishPullbackLayerStackTests(unittest.TestCase):
    def test_trusted_exact_opra_trade_allows_imported_expired_reason(self):
        self.assertTrue(_is_trusted_exact_opra_trade(_trade(exit_reason="expired")))

    def test_trusted_exact_opra_trade_rejects_nearest_and_intrinsic_rows(self):
        self.assertFalse(_is_trusted_exact_opra_trade(_trade(entry_contract_resolution="nearest_listed_contract")))
        self.assertFalse(_is_trusted_exact_opra_trade(_trade(exit_fill_basis="expiration_intrinsic")))
        self.assertFalse(_is_trusted_exact_opra_trade(_trade(priced=False)))

    def test_layer_status_marks_clean_robust_layer(self):
        status = classify_layer_status(
            {
                "exact_trade_count": 129,
                "unpriced_trade_count": 0,
                "quote_coverage_pct": 100.0,
                "profit_factor": 2.2,
                "avg_pnl_pct": 28.97,
                "stress_5pct_per_side_profit_factor": 1.67,
                "rolling_status": "passed",
                "rolling_first_test_profit_factor": 2.51,
            }
        )

        self.assertEqual(status["status"], "clean_paper_shadow_layer")
        self.assertTrue(status["robust_paper_shadow_met"])
        self.assertIn("below_200_trade_preferred_target", status["blockers"])

    def test_layer_status_rejects_high_count_pf_collapse(self):
        status = classify_layer_status(
            {
                "exact_trade_count": 165,
                "unpriced_trade_count": 17,
                "quote_coverage_pct": 90.7,
                "profit_factor": 1.49,
                "avg_pnl_pct": 14.0,
                "stress_5pct_per_side_profit_factor": 1.12,
                "rolling_status": "watch",
                "rolling_first_test_profit_factor": 2.25,
            }
        )

        self.assertEqual(status["status"], "research_or_rejected")
        self.assertIn("pf_below_2", status["blockers"])
        self.assertIn("quote_coverage_below_97_5", status["blockers"])


if __name__ == "__main__":
    unittest.main()
