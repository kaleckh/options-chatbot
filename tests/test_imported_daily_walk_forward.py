import os
import unittest
from unittest.mock import patch

from scripts.imported_daily_walk_forward import (
    _metrics,
    _window_dates,
    build_imported_daily_walk_forward_validation,
    run_imported_daily_walk_forward_validation,
)


def _trade(day: int, resolution: str, pnl: float, correct: bool = True) -> dict:
    return {
        "date": f"2026-05-{day:02d}",
        "ticker": "SPY",
        "entry_contract_resolution": resolution,
        "pnl_pct": pnl,
        "directional_correct": correct,
    }


class ImportedDailyWalkForwardTests(unittest.TestCase):
    def test_validation_uses_frozen_universe_and_exact_contract_oos_gate(self):
        replay = {
            "truth_source": "historical_imported_daily",
            "playbook": "bullish_pullback_observation",
            "pricing_lane": "pessimistic",
            "validation_universe": ["QQQ", "SPY"],
            "priced_trade_count": 8,
            "candidate_trade_count": 8,
            "trades": [
                _trade(1, "exact_target_contract", 4.0),
                _trade(2, "nearest_listed_contract", 20.0),
                _trade(3, "exact_archived_contract", 6.0),
                _trade(4, "nearest_listed_contract", -5.0, False),
                _trade(5, "exact_target_contract", 7.0),
                _trade(6, "exact_target_contract", -2.0, False),
            ],
        }

        report = build_imported_daily_walk_forward_validation(
            replay,
            train_days=2,
            test_days=2,
            min_exact_test_trades=1,
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["frozen_universe"], ["QQQ", "SPY"])
        self.assertEqual(report["authoritative_profitability_basis"], "exact_contract_only")
        self.assertEqual(report["source_contract_accounting"]["exact_contract_match_count"], 4)
        self.assertEqual(report["window_count"], 2)
        self.assertEqual(report["windows"][0]["exact_test"]["trade_count"], 1)
        self.assertEqual(report["windows"][0]["research_test_trade_count"], 1)

    def test_validation_blocks_when_there_are_not_enough_oos_dates(self):
        report = build_imported_daily_walk_forward_validation(
            {
                "truth_source": "historical_imported_daily",
                "validation_universe": ["SPY"],
                "trades": [_trade(1, "exact_target_contract", 4.0)],
            },
            train_days=2,
            test_days=2,
            min_exact_test_trades=1,
        )

        self.assertEqual(report["status"], "blocked_insufficient_oos_dates")
        self.assertIn("need_at_least_4_trade_dates_for_one_window", report["blockers"])

    def test_validation_blocks_oos_windows_with_unpriced_candidates(self):
        replay = {
            "truth_source": "historical_imported_daily",
            "validation_universe": ["SPY"],
            "priced_trade_count": 3,
            "candidate_trade_count": 4,
            "trades": [
                _trade(1, "exact_target_contract", 4.0),
                _trade(2, "exact_target_contract", 5.0),
                _trade(3, "exact_target_contract", 6.0),
            ],
            "unpriced_trades": [
                {
                    "date": "2026-05-04",
                    "ticker": "SPY",
                    "entry_contract_resolution": "exact_target_contract",
                    "unpriced_reason": "missing_exit_quote",
                }
            ],
        }

        report = build_imported_daily_walk_forward_validation(
            replay,
            train_days=2,
            test_days=2,
            min_exact_test_trades=1,
        )

        self.assertEqual(report["status"], "watch")
        self.assertIn("unpriced_test_candidates_present", report["blockers"])
        self.assertEqual(report["source_unpriced_trade_count"], 1)
        self.assertEqual(report["source_candidate_trade_count"], 4)
        self.assertEqual(report["windows"][0]["unpriced_test_candidate_count"], 1)
        self.assertEqual(report["windows"][0]["test_candidate_count"], 2)
        self.assertEqual(report["windows"][0]["test_quote_coverage_pct"], 50.0)

    def test_metrics_do_not_treat_string_false_as_directional_hit(self):
        metrics = _metrics(
            [
                {"pnl_pct": 3.0, "directional_correct": "False"},
                {"pnl_pct": 2.0, "directional_correct": "true"},
            ]
        )

        self.assertEqual(metrics["directional_accuracy_pct"], 50.0)
        self.assertEqual(metrics["profit_factor"], 999.0)

    def test_window_dates_rejects_non_positive_steps(self):
        with self.assertRaises(ValueError):
            _window_dates(["2026-05-01"], train_days=1, test_days=0)
        with self.assertRaises(ValueError):
            _window_dates(["2026-05-01"], train_days=0, test_days=1)

    def test_runner_invokes_imported_daily_replay_without_saving_result(self):
        replay = {
            "truth_source": "historical_imported_daily",
            "playbook": "bullish_pullback_observation",
            "validation_universe": ["SPY"],
            "trades": [_trade(1, "exact_target_contract", 4.0), _trade(2, "exact_target_contract", 3.0)],
        }

        with patch("scripts.imported_daily_walk_forward.wfo.run_historical_backtest", return_value=replay) as run_backtest:
            report = run_imported_daily_walk_forward_validation(
                playbook="bullish_pullback_observation",
                lookback_years=1,
                n_picks=1,
                pricing_lane="pessimistic",
                train_days=1,
                test_days=1,
                min_exact_test_trades=1,
                min_imported_calendar_dates=1,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(run_backtest.call_args.kwargs["truth_lane"], "historical_imported_daily")
        self.assertEqual(run_backtest.call_args.kwargs["playbook"], "bullish_pullback_observation")
        self.assertFalse(run_backtest.call_args.kwargs["save_result"])
        self.assertEqual(run_backtest.call_args.kwargs["min_imported_calendar_dates"], 1)

    def test_runner_can_pin_historical_options_db_path(self):
        with patch("scripts.imported_daily_walk_forward.wfo.run_historical_backtest", return_value={"trades": []}):
            with patch.dict(os.environ, {}, clear=True):
                run_imported_daily_walk_forward_validation(
                    playbook="bullish_pullback_observation",
                    lookback_years=1,
                    n_picks=1,
                    pricing_lane="pessimistic",
                    train_days=1,
                    test_days=1,
                    min_exact_test_trades=1,
                    min_imported_calendar_dates=1,
                    db_path="custom_options_history.db",
                )
                self.assertEqual(os.environ["HISTORICAL_OPTIONS_DB_PATH"], "custom_options_history.db")


if __name__ == "__main__":
    unittest.main()
