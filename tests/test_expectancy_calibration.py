from __future__ import annotations

import unittest

import expectancy_calibration as ec


class ExpectancyCalibrationTests(unittest.TestCase):
    def test_score_bucket_handles_nan_inputs(self):
        self.assertEqual(ec.score_bucket(float("nan")), "00-09")

    def test_surface_metrics_sanitize_non_finite_pnl_inputs(self):
        surface = ec.build_expectancy_surface_from_trades(
            [
                {
                    "direction_score": 78,
                    "quality_score": 66,
                    "tech_score": 72,
                    "market_regime": "bullish",
                    "direction": "call",
                    "pnl_pct": float("inf"),
                    "directional_correct": True,
                },
                {
                    "direction_score": 78,
                    "quality_score": 66,
                    "tech_score": 72,
                    "market_regime": "bullish",
                    "direction": "call",
                    "pnl_pct": -10.0,
                    "directional_correct": False,
                },
            ],
            min_trades=1,
            shrinkage_trades=0.0,
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface["overall"]["avg_pnl_pct"], -5.0)
        self.assertEqual(surface["overall"]["profit_factor"], 0.0)

    def test_surface_reports_no_loss_sample_without_pf_sentinel(self):
        surface = ec.build_expectancy_surface_from_trades(
            [
                {
                    "direction_score": 78,
                    "quality_score": 66,
                    "tech_score": 72,
                    "market_regime": "bullish",
                    "direction": "call",
                    "pnl_pct": 4.0,
                    "directional_correct": True,
                }
            ],
            min_trades=1,
            shrinkage_trades=0.0,
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertIsNone(surface["overall"]["profit_factor"])
        self.assertTrue(surface["overall"]["no_loss_sample"])

    def test_build_expectancy_surface_preserves_provenance(self):
        trades = [
            {
                "direction_score": 78,
                "quality_score": 66,
                "tech_score": 72,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 4.0,
                "directional_correct": True,
            },
            {
                "direction_score": 78,
                "quality_score": 66,
                "tech_score": 72,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 5.0,
                "directional_correct": True,
            },
            {
                "direction_score": 78,
                "quality_score": 66,
                "tech_score": 72,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 6.0,
                "directional_correct": True,
            },
            {
                "direction_score": 78,
                "quality_score": 66,
                "tech_score": 72,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 7.0,
                "directional_correct": True,
            },
            {
                "direction_score": 78,
                "quality_score": 66,
                "tech_score": 72,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 8.0,
                "directional_correct": True,
            },
        ]
        source_metadata = {
            "run_at": "2026-03-31T10:00:00",
            "mode": "backtest",
            "profile": "mixed",
            "lookback_years": 1,
            "n_picks": 1,
            "iv_adj": 1.2,
            "pricing_lane": "mid",
            "playbook": "bullish_momentum",
            "truth_source": "historical_imported_daily",
            "promotion_status": "watch",
            "quote_coverage_pct": 91.5,
            "strategy_domain": "options",
            "contract_selection_basis": "historical_chain_nearest_listed_contract",
            "universe_filters": {"history_days_min": 100},
            "trades": trades,
            "equity_curve": [{"date": "2026-03-31", "cum_pnl_pct": 4.0}],
            "unpriced_trades": [],
        }

        surface = ec.build_expectancy_surface_from_trades(
            trades,
            source_metadata=source_metadata,
            min_trades=3,
            bucket_size=10,
            quality_bucket_size=10,
            tech_bucket_size=10,
        )
        self.assertIsNotNone(surface)
        assert surface is not None

        self.assertEqual(surface["source_playbook"], "bullish_momentum")
        self.assertEqual(surface["source_truth_source"], "historical_imported_daily")
        self.assertEqual(surface["source_promotion_status"], "watch")
        self.assertEqual(surface["source_quote_coverage_pct"], 91.5)
        self.assertEqual(surface["source_metadata"]["strategy_domain"], "options")

        lookup = ec.lookup_calibrated_expectancy(
            surface,
            direction_score=78,
            quality_score=66,
            market_regime="bullish",
            trade_type="call",
            tech_score=72,
            require_positive=True,
            allow_overall=False,
        )
        self.assertIsNotNone(lookup)
        assert lookup is not None
        self.assertTrue(lookup["dense_cohort"])
        self.assertEqual(lookup["cohort_density"], "dense")
        self.assertEqual(lookup["calibration_density"], "dense")
        self.assertTrue(lookup["calibration_is_dense"])
        self.assertEqual(lookup["surface_provenance"]["source_playbook"], "bullish_momentum")
        self.assertEqual(lookup["surface_provenance"]["source_truth_source"], "historical_imported_daily")
        self.assertEqual(lookup["surface_provenance"]["source_promotion_status"], "watch")

    def test_lookup_marks_sparse_cohort_and_keeps_surface_provenance(self):
        trades = [
            {
                "direction_score": 82,
                "quality_score": 70,
                "tech_score": 75,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 3.0,
                "directional_correct": True,
            },
            {
                "direction_score": 84,
                "quality_score": 72,
                "tech_score": 76,
                "market_regime": "bullish",
                "direction": "call",
                "pnl_pct": 4.0,
                "directional_correct": True,
            },
        ]
        surface = ec.build_expectancy_surface_from_trades(
            trades,
            source_metadata={
                "run_at": "2026-03-31T10:00:00",
                "playbook": "bullish_momentum",
                "truth_source": "historical_imported_daily",
                "promotion_status": "watch",
                "quote_coverage_pct": 75.0,
                "trades": trades,
            },
            min_trades=5,
        )
        self.assertIsNotNone(surface)
        assert surface is not None

        lookup = ec.lookup_calibrated_expectancy(
            surface,
            direction_score=83,
            quality_score=71,
            market_regime="bullish",
            trade_type="call",
            tech_score=75,
            require_positive=True,
            allow_overall=False,
        )
        self.assertIsNotNone(lookup)
        assert lookup is not None
        self.assertFalse(lookup["dense_cohort"])
        self.assertEqual(lookup["cohort_density"], "sparse")
        self.assertEqual(lookup["calibration_density"], "sparse")
        self.assertFalse(lookup["calibration_is_dense"])
        self.assertIsNotNone(lookup["sparse_warning"])
        self.assertEqual(lookup["surface_provenance"]["source_playbook"], "bullish_momentum")
        self.assertEqual(lookup["surface_provenance"]["source_truth_source"], "historical_imported_daily")


if __name__ == "__main__":
    unittest.main()
