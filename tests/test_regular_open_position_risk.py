from __future__ import annotations

from scripts.audit_regular_open_position_risk import build_report


def test_open_position_risk_details_non_executable_sell_without_close_claim():
    report = build_report(
        [
            {
                "id": 104,
                "status": "open",
                "ticker": "SBUX",
                "direction": "call",
                "last_recommendation": "SELL",
                "last_reviewed_at": "2026-05-31T18:00:28-06:00",
                "stop_loss_pct": 90.0,
                "source_pick_snapshot": {
                    "playbook_id": "bullish_pullback_observation",
                    "research_only": True,
                },
                "latest_review": {
                    "recommendation": "SELL",
                    "reason": "Indicator exit triggered.",
                    "pricing_source": "spread_display_only",
                    "pricing_state": "priced_display_only_last",
                    "current_option_price": 0.47,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                    "warnings": ["Using display-only spread marks."],
                    "metrics_snapshot": {
                        "price_trigger_ok": False,
                        "pricing_state": "priced_display_only_last",
                    },
                },
            },
            {
                "id": 105,
                "status": "open",
                "ticker": "AAPL",
                "direction": "call",
                "last_recommendation": "HOLD",
                "last_pnl_pct": 12.5,
                "source_pick_snapshot": {"playbook_id": "bullish_pullback_observation"},
                "latest_review": {
                    "recommendation": "HOLD",
                    "pricing_source": "bid",
                    "pricing_state": "priced_exact",
                    "current_pnl_pct": 12.5,
                    "exit_execution_price": 1.25,
                    "metrics_snapshot": {"price_trigger_ok": True},
                },
            },
        ]
    )

    assert report["action_counts"]["stored_non_executable_sell"] == 1
    assert report["actionable_position_ids"] == [104]
    detail = report["actionable_positions"][0]
    assert detail["id"] == 104
    assert detail["action_bucket"] == "stored_non_executable_sell"
    assert detail["pricing_state"] == "priced_display_only_last"
    assert detail["price_trigger_ok"] is False
    assert detail["exit_execution_price"] is None
    assert detail["next_safe_action"].startswith("do_not_auto_close_from_display_only_mark")


def test_open_risk_governor_treats_fresh_exact_hold_as_resolved_negative_risk():
    report = build_report(
        [
            {
                "id": 537,
                "status": "open",
                "ticker": "QQQ",
                "proof_class": "live_exact_tracked",
                "last_pnl_pct": -39.86,
                "source_pick_snapshot": {"playbook_id": "volatility_expansion_observation"},
                "latest_review": {
                    "reviewed_at": "2026-06-06T15:00:00Z",
                    "recommendation": "HOLD",
                    "pricing_source": "opra",
                    "pricing_state": "priced_exact",
                    "current_pnl_pct": -39.86,
                    "exit_execution_price": 2.4,
                    "exit_execution_basis": "spread_bid_ask",
                    "metrics_snapshot": {"price_trigger_ok": True},
                },
            },
            {
                "id": 104,
                "status": "open",
                "ticker": "SBUX",
                "last_pnl_pct": -88.0,
                "source_pick_snapshot": {
                    "playbook_id": "bullish_pullback_observation",
                    "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
                },
                "latest_review": {
                    "reviewed_at": "2026-06-06T15:00:00Z",
                    "recommendation": "SELL",
                    "pricing_source": "spread_display_only",
                    "pricing_state": "priced_display_only_last",
                    "current_pnl_pct": -88.0,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                },
            },
        ],
        as_of="2026-06-06T18:00:00Z",
    )

    governor = report["open_risk_governor"]
    assert governor["status"] == "open_risk_governor_pass"
    assert governor["live_entry_allowed"] is True
    assert governor["blockers"] == []
    assert governor["live_exact_negative_ids"] == [537]
    assert governor["live_exact_negative_resolved_hold_ids"] == [537]
    assert governor["live_exact_negative_unresolved_ids"] == []
    assert 104 not in governor["live_exact_negative_ids"]


def test_open_risk_governor_blocks_unresolved_live_exact_negative_rows_only():
    report = build_report(
        [
            {
                "id": 537,
                "status": "open",
                "ticker": "QQQ",
                "proof_class": "live_exact_tracked",
                "last_pnl_pct": -39.86,
                "source_pick_snapshot": {"playbook_id": "volatility_expansion_observation"},
                "latest_review": {
                    "reviewed_at": "2026-06-06T15:00:00Z",
                    "recommendation": "HOLD",
                    "pricing_source": "spread_display_only",
                    "pricing_state": "priced_display_only_last",
                    "current_pnl_pct": -39.86,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                    "metrics_snapshot": {"price_trigger_ok": False},
                },
            },
            {
                "id": 104,
                "status": "open",
                "ticker": "SBUX",
                "last_pnl_pct": -88.0,
                "source_pick_snapshot": {
                    "playbook_id": "bullish_pullback_observation",
                    "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
                },
                "latest_review": {
                    "reviewed_at": "2026-06-06T15:00:00Z",
                    "recommendation": "SELL",
                    "pricing_source": "spread_display_only",
                    "pricing_state": "priced_display_only_last",
                    "current_pnl_pct": -88.0,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                },
            },
        ],
        as_of="2026-06-06T18:00:00Z",
    )

    governor = report["open_risk_governor"]
    assert governor["status"] == "open_risk_governor_blocked"
    assert governor["live_entry_allowed"] is False
    assert governor["blockers"] == ["live_exact_negative_open_risk", "live_exact_review_stale_missing_or_non_executable"]
    assert governor["live_exact_negative_ids"] == [537]
    assert governor["live_exact_negative_unresolved_ids"] == [537]
    assert 104 not in governor["live_exact_negative_ids"]


def test_open_risk_governor_blocks_live_exact_non_executable_review():
    report = build_report(
        [
            {
                "id": 600,
                "status": "open",
                "ticker": "SPY",
                "proof_class": "live_exact_tracked",
                "last_pnl_pct": 4.0,
                "source_pick_snapshot": {"playbook_id": "swing"},
                "latest_review": {
                    "reviewed_at": "2026-06-06T15:00:00Z",
                    "recommendation": "HOLD",
                    "pricing_source": "spread_display_only",
                    "pricing_state": "priced_display_only_last",
                    "current_pnl_pct": 4.0,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                },
            }
        ],
        as_of="2026-06-06T18:00:00Z",
    )

    governor = report["open_risk_governor"]
    assert governor["status"] == "open_risk_governor_blocked"
    assert governor["blockers"] == ["live_exact_review_stale_missing_or_non_executable"]
    assert governor["live_exact_review_blocked_ids"] == [600]
