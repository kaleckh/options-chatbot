from __future__ import annotations

import unittest
import math
from types import SimpleNamespace
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd

import wfo_optimizer as wfo


def _trade_date(offset_days: int) -> str:
    return (datetime(2026, 3, 31) + timedelta(days=offset_days)).date().isoformat()


class WFOOptimizerCalibrationTests(unittest.TestCase):
    def test_model_window_charges_commission_and_slippage(self):
        prices = pd.Series(
            [100 + i * 0.25 + math.sin(i / 2) * 2 for i in range(160)],
            index=pd.date_range("2026-01-01", periods=160, freq="B"),
        )

        result = wfo._simulate_window(
            prices,
            weights={"iv_percentile": 0.4, "delta": 0.35, "dte": 0.25},
            dte_at_entry=10,
            stop_loss_pct=50,
            profit_target_pct=100,
            delta_target=0.3,
            min_confidence=0,
            min_ev_pct=-100,
            entry_momentum=0.0,
            time_exit_pct=50,
            entry_slippage_pct=1.0,
            exit_slippage_pct=1.0,
        )

        self.assertGreater(result["n_trades"], 0)
        trade = result["trades"][0]
        self.assertEqual(trade["fee_total_usd"], 1.3)
        self.assertGreater(trade["entry_px"], trade["entry_model_mark_px"])
        self.assertLess(trade["net_pnl_pct"], trade["gross_pnl_pct"])
        self.assertIn("model_bid", trade["exit_fill_basis"])
        self.assertEqual(result["profit_factor_basis"], "net_pnl_usd")

    def test_sharpe_has_no_small_sample_sentinel_and_does_not_scale_by_trade_count(self):
        self.assertIsNone(wfo._sharpe([1.0, -1.0, 1.0, -1.0]))
        short = wfo._sharpe([1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
        long = wfo._sharpe([1.0, 2.0] * 30)
        self.assertIsNotNone(short)
        self.assertIsNotNone(long)
        assert short is not None and long is not None
        self.assertLess(abs(long - short), 5.0)

    def test_imported_expiry_settlement_uses_expiry_day_close_not_next_session(self):
        dates = pd.date_range("2026-01-01", periods=10, freq="D")
        prices = np.array([100, 101, 102, 103, 104, 104, 104, 105, 50, 49], dtype=float)
        expiry = datetime(2026, 1, 8).date()
        entry_quote = SimpleNamespace(
            contract_symbol="SPY260108C00100000",
            expiry=expiry.isoformat(),
            strike=100.0,
            bid=0.9,
            ask=1.0,
            last=0.95,
            price_basis="bid_ask",
            as_of_utc="2026-01-01T15:00:00Z",
            quote_minute_et=600,
        )
        expiry_quote = SimpleNamespace(
            contract_symbol="SPY260108C00100000",
            expiry=expiry.isoformat(),
            strike=100.0,
            bid=5.0,
            ask=5.1,
            last=5.05,
            price_basis="bid_ask",
            as_of_utc="2026-01-08T20:55:00Z",
            quote_minute_et=955,
        )

        class _Store:
            def find_entry_quote_for_contract(self, **kwargs):
                return entry_quote

            def get_closing_quote(self, *, quote_date_et, **kwargs):
                return expiry_quote if quote_date_et <= expiry else None

        result = wfo._simulate_trade_outcome_imported(
            store=_Store(),
            ticker="SPY",
            dates=dates,
            prices=prices,
            i=0,
            trade_type="call",
            hv30=0.2,
            delta_target=0.3,
            dte_at_entry=7,
            stop_loss_pct=100,
            profit_target_pct=10000,
            time_exit_pct=200,
            trailing_profit_pct=10000,
            trailing_giveback_pct=0,
            _rsi14=np.full(len(prices), 50.0),
            _macd=np.zeros(len(prices)),
            _sma20=np.full(len(prices), 100.0),
            _sma50=np.full(len(prices), 100.0),
            tech_at_entry=50.0,
            entry_S0=100.0,
            archived_contract_symbol="SPY260108C00100000",
            pricing_lane="pessimistic",
        )

        self.assertTrue(result["priced"])
        self.assertEqual(result["exit_reason"], "expired")
        self.assertEqual(result["exit_stock_px"], 105.0)
        self.assertEqual(result["exit_day_idx"], 7)
        self.assertEqual(result["exit_px"], 5.0)

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
                    "entry_contract_resolution": "exact_target_contract",
                },
                {
                    "date": _trade_date(1),
                    "pnl_pct": 2.0,
                    "selection_source": "bootstrap_heuristic",
                    "entry_contract_resolution": "exact_target_contract",
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
