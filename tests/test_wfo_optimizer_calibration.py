from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import wfo_optimizer as wfo


def _trade_date(offset_days: int) -> str:
    return (datetime(2026, 3, 31) + timedelta(days=offset_days)).date().isoformat()


class WFOOptimizerCalibrationTests(unittest.TestCase):
    def test_selection_calibration_summary_separates_dense_and_sparse(self):
        trades = [
            {
                "selection_source": "replay_calibrated",
                "calibration_density": "dense",
            },
            {
                "selection_source": "replay_calibrated",
                "calibration_density": "sparse",
                "calibration_sparse_warning": "direction cohort is sparse with only 2 trades.",
            },
            {
                "selection_source": "bootstrap_heuristic",
            },
        ]

        summary = wfo._selection_calibration_summary(trades, required_trades=2)

        self.assertEqual(summary["selection_source_counts"]["replay_calibrated"], 2)
        self.assertEqual(summary["replay_calibrated_trades"], 1)
        self.assertEqual(summary["replay_calibrated_dense_trades"], 1)
        self.assertEqual(summary["replay_calibrated_sparse_trades"], 1)
        self.assertEqual(summary["bootstrap_heuristic_trades"], 1)
        self.assertEqual(summary["dense_calibrated_trade_pct"], 33.3)
        self.assertEqual(summary["status"], "sparse_calibrated")

    def test_stability_report_blocks_sparse_calibration_from_readiness(self):
        result = {
            "run_at": "2026-03-31T10:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "mid",
            "playbook": "bullish_momentum",
            "truth_source": wfo.IMPORTED_TRUTH_SOURCE,
            "quote_coverage_pct": 100.0,
            "trades": [
                {
                    "date": _trade_date(0),
                    "pnl_pct": 4.0,
                    "selection_source": "replay_calibrated",
                    "calibration_density": "sparse",
                    "calibration_sparse_warning": "direction cohort is sparse with only 2 trades.",
                },
                {
                    "date": _trade_date(1),
                    "pnl_pct": 2.0,
                    "selection_source": "bootstrap_heuristic",
                },
            ],
        }

        def _promote_window_summary(label, subset, min_trades, pass_profit_factor, pass_avg_pnl_pct):
            start_date = min((str(trade.get("date")) for trade in subset if trade.get("date")), default=None)
            end_date = max((str(trade.get("date")) for trade in subset if trade.get("date")), default=None)
            return {
                "label": label,
                "trades": max(len(subset), int(min_trades)),
                "start_date": start_date,
                "end_date": end_date,
                "win_rate_pct": 75.0,
                "directional_accuracy_pct": 75.0,
                "profit_factor": 1.6,
                "avg_pnl_pct": 3.0,
                "passes_quality_bar": True,
            }

        with patch.object(wfo, "_window_summary", side_effect=_promote_window_summary):
            report = wfo.build_options_stability_report(
                result=result,
                min_trades=2,
                min_profit_factor=1.05,
            )

        self.assertEqual(report["calibration_summary"]["replay_calibrated_trades"], 0)
        self.assertEqual(report["calibration_summary"]["replay_calibrated_sparse_trades"], 1)
        self.assertEqual(report["calibration_summary"]["status"], "sparse_calibrated")
        self.assertEqual(report["overall_status"], "block")
        self.assertTrue(
            any("dense replay-calibrated trade" in text.lower() for text in report["recommendations"])
        )


if __name__ == "__main__":
    unittest.main()
