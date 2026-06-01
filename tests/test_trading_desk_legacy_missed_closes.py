from __future__ import annotations

from scripts.audit_trading_desk_legacy_missed_closes import build_report


def test_legacy_missed_close_audit_classifies_stale_non_autoclosing_review_path():
    position = {
        "id": 26,
        "ticker": "JPM",
        "status": "closed",
        "filled_at": "2026-04-01T10:00:00",
        "closed_at": "2026-05-01T10:00:00",
        "exit_reason": "manual_close",
        "time_exit_day": 14,
        "net_pnl_pct": -44.7,
        "source_pick_snapshot": {"playbook_id": "legacy_unlabeled"},
    }
    reviews = [
        {
            "position_id": 26,
            "reviewed_at": "2026-04-16T10:00:00",
            "exit_execution_price": 1.25,
            "exit_execution_basis": "spread_bid_ask",
            "net_pnl_pct": 6.5,
            "recommendation": "SELL",
            "reason": "Time exit reached after 15 calendar day(s), versus a 14-day limit.",
            "metrics_snapshot": {"price_trigger_ok": True},
        }
    ]

    report = build_report([position], reviews_by_position={26: reviews}, target_ids={26})

    assert report["summary"]["current_action_required_count"] == 0
    assert report["summary"]["historical_stale_path_count"] == 1
    assert report["summary"]["recommendation"] == "no_broad_exit_policy_change; preserve as historical stale-policy diagnostic"
    assert report["rows"][0]["diagnosis"] == "stale_or_non_autoclosing_review_path"
    assert report["rows"][0]["first_positive_executable_sell"]["pnl_pct"] == 6.5


def test_legacy_missed_close_audit_flags_still_open_current_action():
    position = {
        "id": 39,
        "ticker": "DIA",
        "status": "open",
        "filled_at": "2026-04-01T10:00:00",
        "closed_at": None,
        "exit_reason": None,
        "time_exit_day": 14,
        "net_pnl_pct": None,
        "source_pick_snapshot": {"playbook_id": "legacy_unlabeled"},
    }
    reviews = [
        {
            "position_id": 39,
            "reviewed_at": "2026-04-20T10:00:00",
            "exit_execution_price": 1.1,
            "exit_execution_basis": "spread_bid_ask",
            "net_pnl_pct": 3.0,
            "recommendation": "SELL",
            "reason": "Time exit reached after 19 calendar day(s), versus a 14-day limit.",
            "metrics_snapshot": {"price_trigger_ok": True},
        }
    ]

    report = build_report([position], reviews_by_position={39: reviews}, target_ids={39})

    assert report["summary"]["current_action_required_count"] == 1
    assert report["summary"]["recommendation"] == "fix_current_auto_close_path"
    assert report["rows"][0]["diagnosis"] == "still_open_but_policy_would_close"
