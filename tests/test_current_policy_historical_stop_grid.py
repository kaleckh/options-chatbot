from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from scripts.replay_current_policy_historical_stop_grid import (  # noqa: E402
    _annual_replay_position_and_row,
    _coverage_by_ticker,
    _focus_loss_summary,
    _occ_expiry_from_contract_symbol,
    _summarize_stop_policy,
    simulate_position_stop_grid,
)


def _position():
    return {
        "id": 1,
        "ticker": "XYZ",
        "status": "closed",
        "filled_at": "2026-01-05T08:10:00-06:00",
        "closed_at": "2026-01-07T13:55:00-06:00",
        "expiry": "2026-01-09",
        "entry_execution_price": 10.0,
        "entry_fee_total_usd": 0.0,
        "contracts": 1,
        "profit_target_pct": 150.0,
        "time_exit_day": 5,
        "source_pick_snapshot": {
            "playbook_id": "short_term",
            "strategy_type": "vertical_spread",
            "contract_symbol": "XYZ260109C00100000",
            "short_contract_symbol": "XYZ260109C00105000",
            "market_regime": "bearish",
            "quality_score": 55.0,
            "debit_pct_of_width": 50.0,
            "spread_liquidity": {
                "spread_mid_debit": 8.0,
                "spread_entry_debit": 10.0,
                "long_bid": 10.0,
                "long_ask": 11.0,
                "short_bid": 1.0,
                "short_ask": 1.5,
            },
        },
    }


def _row(pnl_pct: float = -95.0):
    return {
        "trade_id": 1,
        "ticker": "XYZ",
        "lane": "short_term",
        "closed_at": "2026-01-07",
        "current_policy_decision": "would_take_today",
        "has_realized_pnl": True,
        "pnl_pct": pnl_pct,
        "evidence_group": "historical_paper",
    }


def _snapshot_func(prices: dict[str, float]):
    def snapshot(_pick, *, close_date, **_kwargs):
        price = prices.get(close_date.isoformat())
        if price is None:
            return {"priced": False, "unpriced_reason": "fixture_missing"}
        return {
            "priced": True,
            "quote_date_et": close_date.isoformat(),
            "exit_price": price,
            "exit_execution_basis": "fixture_spread_bid_ask",
        }

    return snapshot


class CurrentPolicyHistoricalStopGridTests(unittest.TestCase):
    def test_stop_grid_classifies_actionable_deep_loss_reduction(self):
        result = simulate_position_stop_grid(
            _position(),
            _row(-95.0),
            store=None,
            source_labels=["fixture"],
            pricing_lane="pessimistic",
            trusted_only=True,
            as_of=date(2026, 1, 9),
            stop_grid=[80.0],
            snapshot_func=_snapshot_func(
                {
                    "2026-01-05": 8.0,
                    "2026-01-06": 1.5,
                    "2026-01-07": 0.5,
                }
            ),
        )

        stop = result["stop_results"]["80"]

        self.assertEqual(result["status"], "replayed")
        self.assertTrue(stop["triggered"])
        self.assertEqual(stop["trigger_date"], "2026-01-06")
        self.assertEqual(stop["classification"], "deep_loss_reduced")
        self.assertEqual(stop["stop_quality"], "actionable_close_check_stop")

    def test_stop_grid_flags_first_priced_close_already_through_stop(self):
        result = simulate_position_stop_grid(
            _position(),
            _row(-95.0),
            store=None,
            source_labels=["fixture"],
            pricing_lane="pessimistic",
            trusted_only=True,
            as_of=date(2026, 1, 9),
            stop_grid=[80.0],
            snapshot_func=_snapshot_func(
                {
                    "2026-01-05": 1.0,
                    "2026-01-06": 0.8,
                    "2026-01-07": 0.5,
                }
            ),
        )

        stop = result["stop_results"]["80"]

        self.assertTrue(stop["triggered"])
        self.assertEqual(stop["trigger_date"], "2026-01-05")
        self.assertEqual(stop["stop_quality"], "same_day_close_already_through_stop")

    def test_stop_policy_summary_tracks_deep_loss_and_winner_damage(self):
        rows = [
            {
                "baseline_pnl_pct": -95.0,
                "stop_results": {
                    "80": {
                        "triggered": True,
                        "pnl_pct": -85.0,
                        "delta_vs_baseline_pct": 10.0,
                        "classification": "deep_loss_reduced",
                        "stop_quality": "actionable_close_check_stop",
                    }
                },
            },
            {
                "baseline_pnl_pct": 20.0,
                "stop_results": {
                    "80": {
                        "triggered": True,
                        "pnl_pct": -82.0,
                        "delta_vs_baseline_pct": -102.0,
                        "classification": "winner_flipped_to_loss",
                        "stop_quality": "actionable_close_check_stop",
                    }
                },
            },
        ]

        summary = _summarize_stop_policy(rows, "80")

        self.assertEqual(summary["triggered_count"], 2)
        self.assertEqual(summary["deep_loss_reduced_count"], 1)
        self.assertEqual(summary["winner_flip_count"], 1)
        self.assertEqual(summary["loss_bucket_counts"]["loss_le_80_pct"], 2)

    def test_focus_loss_summary_surfaces_entry_avoidance_signals(self):
        rows = [
            {
                "baseline_pnl_pct": -95.0,
                "lane": "short_term",
                "ticker": "XYZ",
                "evidence_group": "historical_paper",
                "entry_signals": {
                    "market_regime": "bearish",
                    "fill_degradation_pct": 25.0,
                    "debit_pct_of_width": 50.0,
                    "worst_leg_bid_ask_pct": 22.0,
                    "quality_score": 55.0,
                },
            },
            {
                "baseline_pnl_pct": 30.0,
                "lane": "swing",
                "ticker": "ABC",
                "entry_signals": {"market_regime": "bullish"},
            },
        ]

        summary = _focus_loss_summary(rows, loss_threshold_pct=50.0)

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["lane_counts"], {"short_term": 1})
        self.assertEqual(summary["high_fill_degradation_15_pct_count"], 1)
        self.assertEqual(summary["high_debit_45_pct_width_count"], 1)
        self.assertEqual(summary["worst_leg_spread_20_pct_count"], 1)
        self.assertEqual(summary["quality_below_60_count"], 1)

    def test_ticker_coverage_requires_zero_unresolved_for_each_ticker(self):
        coverage = _coverage_by_ticker(
            scoped_rows=[
                {"ticker": "XYZ"},
                {"ticker": "abc"},
                {"ticker": "XYZ"},
            ],
            replayed_rows=[
                {"ticker": "XYZ"},
                {"ticker": "ABC"},
                {"ticker": "XYZ"},
            ],
            unresolved_rows=[],
        )

        unresolved_by_ticker = {row["ticker"]: row["unresolved_count"] for row in coverage["by_ticker"]}

        self.assertTrue(coverage["all_tickers_resolved"])
        self.assertEqual(coverage["unresolved_ticker_count"], 0)
        self.assertEqual(unresolved_by_ticker, {"ABC": 0, "XYZ": 0})

    def test_annual_replay_rows_are_position_shaped_without_mutating_tracked_store(self):
        selected = {
            "dedupe_key": "2025-08-14|XYZ|call",
            "entry_date": "2025-08-14",
            "exit_date": "2025-09-18",
            "exact_priced": True,
            "lane_id": "annual_lane",
            "lane_family": "annual_family",
            "long_contract_symbol": "XYZ250926C00100000",
            "pnl_pct": 12.5,
            "priced": True,
            "proof_grade": "trusted_intraday_opra_nbbo",
            "short_contract_symbol": "XYZ250926C00105000",
            "source_result_path": "data/options-validation/runs/example.json",
            "ticker": "XYZ",
        }
        source = {
            "date": "2025-08-14",
            "exit_date": "2025-09-18",
            "entry_px": 2.5,
            "entry_fee_total_usd": 1.3,
            "contract_symbol": "XYZ250926C00100000",
            "short_contract_symbol": "XYZ250926C00105000",
            "strategy_type": "vertical_spread",
            "time_exit_day": 24,
            "type": "call",
        }

        position, row = _annual_replay_position_and_row(selected, source)

        self.assertEqual(_occ_expiry_from_contract_symbol("XYZ250926C00100000").isoformat(), "2025-09-26")
        self.assertEqual(position["id"], "annual_replay:annual_lane:2025-08-14:XYZ:call")
        self.assertEqual(position["expiry"], "2025-09-26")
        self.assertEqual(position["entry_execution_price"], 2.5)
        self.assertEqual(row["evidence_group"], "annual_replay_exact")
        self.assertEqual(row["current_policy_decision"], "would_take_today")


if __name__ == "__main__":
    unittest.main()
