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
