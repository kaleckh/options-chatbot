from __future__ import annotations

from datetime import UTC, datetime

from scripts.audit_suggested_trade_close_risk import build_report


def test_suggested_trade_close_risk_flags_non_executable_sell_and_stale_reviews():
    report = build_report(
        [
            {
                "id": 201,
                "status": "open",
                "ticker": "AAA",
                "direction": "call",
                "last_recommendation": "SELL",
                "last_reviewed_at": "2026-05-29T14:00:00Z",
                "last_pnl_pct": -24.0,
                "stop_loss_pct": 40.0,
                "profit_target_pct": 50.0,
                "source_pick_snapshot": {"playbook_id": "bullish_pullback_observation"},
                "latest_review": {
                    "reviewed_at": "2026-05-29T14:00:00Z",
                    "recommendation": "SELL",
                    "reason": "Indicator exit triggered.",
                    "pricing_source": "spread_display_only",
                    "current_pnl_pct": -24.0,
                    "exit_execution_price": None,
                    "exit_execution_basis": None,
                    "warnings": ["Using display-only spread marks."],
                    "metrics_snapshot": {
                        "pricing_state": "priced_display_only_last",
                        "price_trigger_ok": False,
                    },
                },
            },
            {
                "id": 202,
                "status": "open",
                "ticker": "BBB",
                "direction": "put",
                "last_pnl_pct": 8.0,
                "stop_loss_pct": 40.0,
                "profit_target_pct": 50.0,
                "source_pick_snapshot": {"playbook_id": "swing"},
                "latest_review": None,
            },
            {
                "id": 203,
                "status": "closed",
                "ticker": "CCC",
                "direction": "call",
                "last_pnl_pct": -12.0,
                "source_pick_snapshot": {"playbook_id": "short_term"},
                "latest_review": {
                    "reviewed_at": "2026-05-31T14:00:00Z",
                    "recommendation": "SELL",
                    "exit_execution_price": 1.25,
                    "exit_execution_basis": "bid_ask_spread",
                    "metrics_snapshot": {"price_trigger_ok": True},
                },
            },
        ],
        now=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
        stale_hours=24.0,
    )

    assert report["summary"]["rows"] == 2
    assert report["closed_summary"]["rows"] == 1
    assert report["action_counts"]["stored_non_executable_sell"] == 1
    assert report["evidence_counts"]["stale_mark_or_non_executable_review"] == 1
    assert report["evidence_counts"]["missing_review"] == 1
    assert report["close_risk_trade_ids"] == [201]
    assert report["stale_or_missing_review_trade_ids"] == [201, 202]
    assert report["attention_trade_ids"] == [201, 202]
    detail = report["attention_trades"][0]
    assert detail["id"] == 201
    assert detail["action_bucket"] == "stored_non_executable_sell"
    assert detail["pricing_state"] == "priced_display_only_last"
    assert detail["next_safe_action"].startswith("do_not_close_suggested_trade")
