from __future__ import annotations

from scripts.replay_trading_desk_exit_policies import (
    ExitPolicy,
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


def test_current_policy_keeps_harvest_lane_limited():
    position = _position(1, "short_term")
    reviews = [_review("2026-04-16T10:00:00-06:00", 55.0)]

    result = simulate_exit_policy(position, reviews, ExitPolicy("current_policy_replay", "current"))

    assert result["status"] == "held_through_reviews"
    assert result["pnl_pct"] == 55.0


def test_profit_harvest_all_lanes_closes_short_term_winner():
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

    assert result["status"] == "closed"
    assert result["reason"] == "profit_harvest"
    assert result["pnl_pct"] == 55.0


def test_trailing_giveback_closes_after_peak_declines_but_stays_profitable():
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

    assert result["status"] == "closed"
    assert result["reason"] == "trailing_giveback"
    assert result["pnl_pct"] == 35.0


def test_build_report_marks_stored_sell_as_research_when_broader_metrics_are_weak():
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
    assert policy["legacy_targets"][0]["policy_pnl_pct"] == 45.0
    assert policy["avg_delta_vs_baseline_pct"] > 0
    assert policy["recommendation"]["status"] in {"research_candidate", "reject_current_shape"}
