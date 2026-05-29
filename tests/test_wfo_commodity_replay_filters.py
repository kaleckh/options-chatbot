from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wfo_optimizer as wfo


class WFOCommodityReplayFilterTests(unittest.TestCase):
    def test_commodity_replay_universe_filter_summary_uses_lane_liquidity_contract(self):
        playbook = wfo._get_replay_playbook("ai_commodity_infra_observation")

        summary = wfo._replay_underlying_filter_summary(playbook)

        self.assertEqual(
            set(summary),
            {
                "history_days_min",
                "avg_volume_20d_min",
                "avg_dollar_volume_20d_min",
                "rolling_window_days",
            },
        )
        self.assertEqual(summary["avg_volume_20d_min"], 1_000_000)
        self.assertEqual(summary["avg_dollar_volume_20d_min"], 100_000_000)

    def test_broad_replay_universe_filter_summary_keeps_broad_liquidity_contract(self):
        summary = wfo._replay_underlying_filter_summary("broad")

        self.assertEqual(summary["avg_volume_20d_min"], 3_000_000)
        self.assertEqual(summary["avg_dollar_volume_20d_min"], 250_000_000)

    def test_unknown_replay_playbook_fails_closed(self):
        with self.assertRaises(ValueError):
            wfo._get_replay_playbook("ai_commmodity_infra_observation")

    def test_replay_ticker_factory_uses_alpaca_when_provider_is_requested(self):
        sentinel_factory = object()

        with patch.dict(
            os.environ,
            {
                "OPTIONS_MARKET_DATA_PROVIDER": "alpaca",
                "ALPACA_ENABLE_DURING_TESTS": "1",
                "OPTIONS_RUN_MODE": "paper",
            },
            clear=False,
        ), patch.object(wfo, "make_alpaca_ticker_factory", return_value=sentinel_factory) as make_factory:
            factory = wfo._replay_ticker_factory()

        self.assertIs(factory, sentinel_factory)
        make_factory.assert_called_once_with(fallback_factory=None)

    def test_authoritative_profitability_gate_rejects_non_finite_metrics(self):
        gate = wfo._authoritative_profitability_gate(
            {
                "trade_count": 100,
                "profit_factor": float("inf"),
                "avg_pnl_pct": float("inf"),
                "directional_accuracy_pct": 75.0,
            },
            min_trade_count=1,
            min_profit_factor=1.05,
            min_avg_pnl_pct=0.0,
        )

        self.assertFalse(gate["passed"])
        self.assertIn("Exact-contract PF is non-finite.", gate["blockers"])
        self.assertIn("Exact-contract avg P&L is non-finite.", gate["blockers"])

    def test_stability_report_blocks_non_finite_window_metrics(self):
        result = {
            "run_at": "2026-04-01T12:00:00",
            "mode": "backtest",
            "lookback_years": 1,
            "pricing_lane": "historical_imported_daily",
            "playbook": "short_term",
            "truth_source": "historical_imported_daily",
            "quote_coverage_pct": 100.0,
            "priced_trade_count": 2,
            "unpriced_trade_count": 0,
            "trades": [
                {
                    "date": "2026-03-30",
                    "ticker": "SPY",
                    "type": "call",
                    "direction_score": 80.0,
                    "sector": "Index ETF",
                    "market_regime": "bullish",
                    "entry_contract_resolution": "exact_target_contract",
                    "directional_correct": True,
                    "pnl_pct": float("inf"),
                },
                {
                    "date": "2026-03-31",
                    "ticker": "QQQ",
                    "type": "call",
                    "direction_score": 82.0,
                    "sector": "Index ETF",
                    "market_regime": "bullish",
                    "entry_contract_resolution": "exact_target_contract",
                    "directional_correct": True,
                    "pnl_pct": float("inf"),
                },
            ],
        }

        report = wfo.build_options_stability_report(result=result, min_trades=1, min_profit_factor=1.05)

        self.assertEqual(report["overall_status"], "block")
        self.assertFalse(report["scenario_results"]["full_window"]["passes_quality_bar"])
        self.assertFalse(report["authoritative_profitability_gate"]["passed"])
        self.assertIn("Exact-contract PF is non-finite.", report["authoritative_profitability_gate"]["blockers"])

    def test_ai_commodity_imported_replay_blocks_when_shared_opra_dates_are_missing(self):
        class FakeStore:
            def has_quotes(self, **_kwargs):
                return True

            def snapshot_summary(self, *_args, **_kwargs):
                return {}

            def list_available_underlyings(self, **_kwargs):
                return wfo._imported_replay_underlyings_for_playbook(
                    wfo._get_replay_playbook("ai_commodity_infra_observation")
                )

            def available_quote_dates(self, *_args, **_kwargs):
                return ["2026-01-02", "2026-01-03"]

            def shared_quote_dates(self, *_args, **_kwargs):
                return []

        with patch.object(wfo, "HistoricalOptionsStore", FakeStore), patch.object(
            wfo,
            "ensure_strategy_profiles_current",
            lambda: None,
        ), patch.object(wfo, "_cached_history") as cached_history:
            result = wfo.run_historical_backtest(
                lookback_years=1,
                truth_lane=wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                playbook="ai_commodity_infra_observation",
                min_imported_calendar_dates=2,
                save_result=False,
            )

        cached_history.assert_not_called()
        self.assertEqual(result["status"], "insufficient_shared_quote_dates")
        self.assertEqual(result["evidence_status"], "insufficient_shared_quote_dates")
        self.assertIn("Benchmark-only quote dates", result["error"])
        self.assertEqual(
            result["replay_calendar"]["replay_quote_date_source"],
            "missing_shared_required_quote_dates",
        )
        self.assertEqual(result["replay_calendar"]["shared_quote_date_count"], 0)

    def test_broad_imported_replay_keeps_benchmark_date_fallback_when_shared_dates_are_missing(self):
        class FakeStore:
            def has_quotes(self, **_kwargs):
                return True

            def snapshot_summary(self, *_args, **_kwargs):
                return {}

            def list_available_underlyings(self, **_kwargs):
                return wfo.IMPORTED_VALIDATION_UNIVERSE

            def available_quote_dates(self, *_args, **_kwargs):
                return ["2026-01-02", "2026-01-03"]

            def shared_quote_dates(self, *_args, **_kwargs):
                return []

        with patch.object(wfo, "HistoricalOptionsStore", FakeStore), patch.object(
            wfo,
            "ensure_strategy_profiles_current",
            lambda: None,
        ), patch.object(wfo, "_cached_history", return_value=pd.DataFrame()) as cached_history:
            result = wfo.run_historical_backtest(
                lookback_years=1,
                truth_lane=wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                playbook="broad",
                min_imported_calendar_dates=2,
                save_result=False,
            )

        self.assertGreater(cached_history.call_count, 0)
        self.assertNotEqual(result.get("status"), "insufficient_shared_quote_dates")
        self.assertEqual(result["error"], "Could not fetch price history for watchlist tickers")

    def test_post_entry_denominator_truth_counts_filtered_candidates(self):
        fields = wfo._post_entry_denominator_truth(
            priced_trade_count=3,
            unpriced_trade_count=1,
            post_entry_filtered_trade_count=2,
        )

        self.assertEqual(fields["pre_post_entry_candidate_trade_count"], 6)
        self.assertEqual(fields["post_entry_reject_rate_pct"], 33.3)

    def test_profit_factor_denominator_truth_preserves_numeric_profit_factor_context(self):
        summary = wfo._comparison_trade_subset_summary(
            [
                {"pnl_pct": 10.0},
                {"pnl_pct": -4.0},
                {"pnl_pct": 0.0},
            ]
        )

        self.assertEqual(summary["profit_factor"], 2.5)
        self.assertEqual(summary["gross_win"], 10.0)
        self.assertEqual(summary["gross_loss"], 4.0)
        self.assertEqual(summary["win_trade_count"], 1)
        self.assertEqual(summary["loss_trade_count"], 1)
        self.assertEqual(summary["profit_factor_status"], "has_losses")

        no_loss_summary = wfo._comparison_trade_subset_summary([{"pnl_pct": 5.0}])
        self.assertEqual(no_loss_summary["profit_factor"], 5.0)
        self.assertEqual(no_loss_summary["profit_factor_status"], "no_losses")


if __name__ == "__main__":
    unittest.main()
