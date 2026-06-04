from __future__ import annotations

import unittest

from scripts.replay_trading_desk_exit_policies import (
    ExitPolicy,
    POLICIES,
    build_report,
    simulate_exit_policy,
)


def _position(position_id: int, lane: str, final_pnl: float = -50.0):
    return {
        "id": position_id,
        "ticker": "JPM",
        "status": "closed",
        "filled_at": "2026-04-15T09:45:00-06:00",
        "expiry": "2026-06-19",
        "net_pnl_pct": final_pnl,
        "stop_loss_pct": 90,
        "profit_target_pct": 100,
        "time_exit_day": 20,
        "source_pick_snapshot": {"playbook_id": lane},
    }


def _review(day: str, pnl_pct: float, *, recommendation: str = "HOLD"):
    return {
        "reviewed_at": day,
        "net_pnl_pct": pnl_pct,
        "exit_execution_price": 1.0,
        "exit_execution_basis": "spread_bid_ask",
        "recommendation": recommendation,
        "reason": "fixture",
        "metrics_snapshot": {"price_trigger_ok": True},
    }


class TradingDeskExitPolicyReplayTests(unittest.TestCase):
    def test_current_policy_keeps_harvest_lane_limited(self):
        position = _position(1, "short_term")
        reviews = [_review("2026-04-16T10:00:00-06:00", 55.0)]

        result = simulate_exit_policy(position, reviews, ExitPolicy("current_policy_replay", "current"))

        self.assertEqual(result["status"], "held_through_reviews")
        self.assertEqual(result["pnl_pct"], 55.0)

    def test_profit_harvest_all_lanes_closes_short_term_winner(self):
        position = _position(1, "short_term")
        reviews = [_review("2026-04-16T10:00:00-06:00", 55.0)]

        result = simulate_exit_policy(
            position,
            reviews,
            ExitPolicy(
                "profit_harvest_all_lanes_50",
                "harvest",
                profit_harvest_lanes="all",
                profit_harvest_trigger_pct=50.0,
            ),
        )

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["reason"], "profit_harvest")
        self.assertEqual(result["pnl_pct"], 55.0)

    def test_trailing_giveback_closes_after_peak_declines_but_stays_profitable(self):
        position = _position(1, "swing")
        reviews = [
            _review("2026-04-16T10:00:00-06:00", 60.0),
            _review("2026-04-17T10:00:00-06:00", 35.0),
        ]

        result = simulate_exit_policy(
            position,
            reviews,
            ExitPolicy(
                "trailing_giveback_all_lanes_50_20",
                "giveback",
                profit_harvest_lanes="none",
                giveback_trigger_pct=50.0,
                giveback_pct=20.0,
                min_remaining_profit_pct=15.0,
            ),
        )

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["reason"], "trailing_giveback")
        self.assertEqual(result["pnl_pct"], 35.0)

    def test_build_report_marks_stored_sell_as_research_when_broader_metrics_are_weak(self):
        positions = [_position(26, "legacy_unlabeled", -44.0), _position(2, "short_term", 40.0)]
        reviews = {
            26: [
                _review("2026-04-15T10:00:00-06:00", -20.0),
                _review("2026-05-06T10:00:00-06:00", 45.0, recommendation="SELL"),
            ],
            2: [_review("2026-04-16T10:00:00-06:00", 40.0)],
        }

        report = build_report(
            positions,
            reviews_by_position=reviews,
            policies=[ExitPolicy("stored_sell_recommendation", "stored", use_stored_sell=True)],
        )

        policy = report["policies"][0]
        self.assertEqual(policy["legacy_targets"][0]["policy_pnl_pct"], 45.0)
        self.assertGreater(policy["avg_delta_vs_baseline_pct"], 0)
        self.assertIn(policy["recommendation"]["status"], {"research_candidate", "reject_current_shape"})

    def test_default_policy_set_includes_stop_grid(self):
        policy_ids = {policy.policy_id for policy in POLICIES}

        self.assertTrue({"stop_60", "stop_70", "stop_80", "stop_90"}.issubset(policy_ids))

    def test_build_report_tracks_deep_loss_and_stop_loss_impact(self):
        positions = [_position(1, "short_term", -95.0)]
        reviews = {
            1: [
                _review("2026-04-16T10:00:00-06:00", -82.0),
                _review("2026-04-17T10:00:00-06:00", -95.0),
            ],
        }

        report = build_report(
            positions,
            reviews_by_position=reviews,
            policies=[ExitPolicy("stop_80", "stop", stop_loss_pct=80.0)],
        )

        policy = report["policies"][0]
        self.assertEqual(report["baseline"]["loss_bucket_counts"]["loss_le_90_pct"], 1)
        self.assertEqual(policy["summary"]["loss_bucket_counts"]["loss_le_90_pct"], 0)
        self.assertEqual(policy["loss_bucket_delta_vs_baseline"]["loss_le_90_pct"], -1)
        self.assertEqual(policy["stop_loss_trigger_summary"]["count"], 1)
        self.assertEqual(policy["stop_loss_trigger_summary"]["avg_delta_vs_baseline_pct"], 13.0)
        self.assertEqual(policy["stop_loss_trigger_by_lane"]["short_term"]["count"], 1)
