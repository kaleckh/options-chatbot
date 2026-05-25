from __future__ import annotations

import unittest

from scripts.bullish_index_exit_sweep import parse_exit_configs, run_exit_sweep


class BullishIndexExitSweepTests(unittest.TestCase):
    def test_parse_exit_configs_reads_stop_and_time_pairs(self):
        self.assertEqual(
            parse_exit_configs("90:55, 70:45"),
            [
                {"spread_stop_loss_pct": 90.0, "spread_time_exit_pct": 55.0},
                {"spread_stop_loss_pct": 70.0, "spread_time_exit_pct": 45.0},
            ],
        )

    def test_parse_exit_configs_rejects_bad_shape(self):
        with self.assertRaises(ValueError):
            parse_exit_configs("90")

    def test_run_exit_sweep_restores_profiles_after_replay(self):
        import options_chatbot as oc
        import wfo_optimizer as wfo

        original_stop = oc.STRATEGY_PROFILES["index"]["spread"]["stop_loss_pct"]
        calls = []

        def fake_backtest(**kwargs):
            calls.append(
                {
                    "stop": oc.STRATEGY_PROFILES["index"]["spread"]["stop_loss_pct"],
                    "time": oc.STRATEGY_PROFILES["index"]["spread"]["time_exit_pct"],
                    "kwargs": kwargs,
                }
            )
            return {
                "mode": "backtest",
                "truth_source": "historical_imported_daily",
                "trades": [],
            }

        def fake_matrix(**kwargs):
            return {
                "authoritative_profitability_metrics": {
                    "trade_count": 1,
                    "profit_factor": 1.0,
                    "avg_pnl_pct": 0.0,
                    "directional_accuracy_pct": 50.0,
                    "exit_reasons": [],
                },
                "authoritative_profitability_gate": {"passed": False, "blockers": []},
                "experiments": [],
            }

        old_backtest = wfo.run_historical_backtest
        old_matrix = wfo.build_options_experiment_matrix
        try:
            wfo.run_historical_backtest = fake_backtest
            wfo.build_options_experiment_matrix = fake_matrix
            report = run_exit_sweep(
                configs=parse_exit_configs("80:50"),
                variant="bullish_index_calls_score70",
            )
        finally:
            wfo.run_historical_backtest = old_backtest
            wfo.build_options_experiment_matrix = old_matrix

        self.assertEqual(calls[0]["stop"], 80.0)
        self.assertEqual(calls[0]["time"], 50.0)
        self.assertEqual(report["results"][0]["summary"]["trade_count"], 1)
        self.assertEqual(oc.STRATEGY_PROFILES["index"]["spread"]["stop_loss_pct"], original_stop)


if __name__ == "__main__":
    unittest.main()
