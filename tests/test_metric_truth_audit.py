import unittest

import metric_truth_audit as audit


class MetricTruthAuditTests(unittest.TestCase):
    def test_build_metric_truth_report_flags_unprofitable_and_miscalibrated_scores(self):
        result = {
            "run_at": "2026-03-30T10:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "pessimistic",
            "playbook": "broad",
            "total_days": 100,
            "trades": [
                {
                    "direction_score": 82,
                    "quality_score": 65,
                    "tech_score": 74,
                    "ev": 25,
                    "pnl_pct": -12,
                    "directional_correct": False,
                    "prediction_outcome": "miss",
                },
                {
                    "direction_score": 84,
                    "quality_score": 67,
                    "tech_score": 72,
                    "ev": 28,
                    "pnl_pct": -8,
                    "directional_correct": False,
                    "prediction_outcome": "miss",
                },
                {
                    "direction_score": 42,
                    "quality_score": 45,
                    "tech_score": 52,
                    "ev": 4,
                    "pnl_pct": 10,
                    "directional_correct": True,
                    "prediction_outcome": "hit",
                },
                {
                    "direction_score": 44,
                    "quality_score": 48,
                    "tech_score": 55,
                    "ev": 6,
                    "pnl_pct": 9,
                    "directional_correct": True,
                    "prediction_outcome": "hit",
                },
            ],
        }

        report = audit.build_metric_truth_report(result, min_trades=2)

        self.assertEqual(report["source"]["pricing_lane"], "pessimistic")
        self.assertEqual(report["source"]["playbook"], "broad")
        self.assertLess(report["overall"]["profit_factor"], 1.0)
        self.assertTrue(any("not profitable" in flag.lower() for flag in report["risk_flags"]))
        self.assertTrue(any("miscalibrated" in flag.lower() for flag in report["risk_flags"]))
        self.assertTrue(any("higher direction-score bands are not outperforming" in flag.lower() for flag in report["risk_flags"]))

    def test_best_floor_prefers_threshold_with_best_risk_reward_tradeoff(self):
        result = {
            "run_at": "2026-03-30T10:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "total_days": 100,
            "trades": [
                {"direction_score": 42, "quality_score": 45, "tech_score": 55, "ev": 3, "pnl_pct": -5, "directional_correct": False},
                {"direction_score": 48, "quality_score": 50, "tech_score": 58, "ev": 4, "pnl_pct": -4, "directional_correct": False},
                {"direction_score": 61, "quality_score": 55, "tech_score": 66, "ev": 7, "pnl_pct": 8, "directional_correct": True},
                {"direction_score": 64, "quality_score": 58, "tech_score": 68, "ev": 9, "pnl_pct": 7, "directional_correct": True},
                {"direction_score": 82, "quality_score": 70, "tech_score": 85, "ev": 18, "pnl_pct": 15, "directional_correct": True},
                {"direction_score": 86, "quality_score": 72, "tech_score": 87, "ev": 20, "pnl_pct": 14, "directional_correct": True},
            ],
        }

        report = audit.build_metric_truth_report(result, min_trades=2)
        best_floor = report["metric_health"]["direction_score"]["best_floor"]

        self.assertIsNotNone(best_floor)
        self.assertEqual(best_floor["floor"], 50)
        self.assertGreater(best_floor["profit_factor"], report["overall"]["profit_factor"])
        self.assertGreater(best_floor["avg_pnl_pct"], report["overall"]["avg_pnl_pct"])

    def test_bucket_report_includes_calibration_gap_for_direction_score(self):
        result = {
            "run_at": "2026-03-30T10:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "total_days": 100,
            "trades": [
                {"direction_score": 71, "quality_score": 60, "tech_score": 70, "ev": 12, "pnl_pct": 5, "directional_correct": True},
                {"direction_score": 73, "quality_score": 62, "tech_score": 72, "ev": 13, "pnl_pct": -2, "directional_correct": False},
            ],
        }

        report = audit.build_metric_truth_report(result, min_trades=1)
        bucket = next(item for item in report["metric_buckets"]["direction_score"] if item["label"] == "70-79")

        self.assertIn("calibration_gap_pct", bucket)
        self.assertEqual(bucket["trades"], 2)
        self.assertEqual(bucket["directional_accuracy_pct"], 50.0)
        self.assertEqual(bucket["calibration_gap_pct"], -22.0)


if __name__ == "__main__":
    unittest.main()
