from __future__ import annotations

from scripts.audit_trading_desk_negative_trade_decisions import build_report


def _row(position_id: int, ticker: str, playbook_id: str, pnl_pct: float, **overrides):
    snapshot = {
        "playbook_id": playbook_id,
        "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
        "candidate_execution_label": "executable_opra_paper_candidate",
        "spread_width": 10.0,
        "net_debit": 3.0,
        "ret5": 0.0,
        "quality_score": 50.0,
        "direction_score": 50.0,
    }
    snapshot.update(overrides.pop("source_pick_snapshot", {}))
    row = {
        "id": position_id,
        "ticker": ticker,
        "status": "closed",
        "contract_symbol": f"{ticker}260619C00100000",
        "entry_execution_basis": "spread_bid_ask",
        "exit_execution_basis": "spread_bid_ask",
        "net_pnl_pct": pnl_pct,
        "stop_loss_pct": 90,
        "profit_target_pct": 100,
        "time_exit_day": 14,
        "source_pick_snapshot": snapshot,
    }
    row.update(overrides)
    return row


def _review(reviewed_at: str, pnl_pct: float, *, recommendation: str = "HOLD"):
    return {
        "reviewed_at": reviewed_at,
        "net_pnl_pct": pnl_pct,
        "exit_execution_price": 1.0,
        "exit_execution_basis": "spread_bid_ask",
        "recommendation": recommendation,
        "reason": "fixture",
        "metrics_snapshot": {"price_trigger_ok": True},
    }


def test_negative_audit_marks_rows_current_guardrails_now_block():
    report = build_report(
        [
            _row(
                1,
                "XLK",
                "short_term",
                -50.0,
                source_pick_snapshot={"spread_width": 10.0, "net_debit": 5.0},
            )
        ],
        keep_tickers={"IWM", "AAPL", "GOOGL"},
    )

    row = report["negative_trades"][0]
    assert row["failure_category"] == "entry_guardrail_now_blocks"
    assert "debit_gt_45_width" in row["protections_failed_or_missing"]
    assert "lane_ticker_quarantine" in row["protections_failed_or_missing"]
    assert "playbook=short_term" in row["why_picked"]


def test_negative_audit_distinguishes_before_first_negative_from_before_final_loss():
    report = build_report(
        [_row(26, "JPM", "legacy_unlabeled", -44.0, source_pick_snapshot={"backfill_audit_id": ""})],
        reviews_by_position={
            26: [
                _review("2026-04-15T10:00:00-06:00", -20.0),
                _review("2026-05-06T10:00:00-06:00", 45.0, recommendation="SELL"),
            ]
        },
    )

    row = report["negative_trades"][0]
    assert row["executable_exit_before_negative"] is False
    assert row["executable_profit_sell_before_final_loss"] is True
    assert row["failure_category"] == "missed_executable_profit_exit_before_final_loss"
    assert report["summary"]["executable_profit_sell_before_final_loss_count"] == 1


def test_negative_audit_marks_missing_timeline_without_overclaiming_missed_exit():
    report = build_report(
        [_row(2, "ORCL", "short_term", -20.0)],
        reviews_by_position={},
        keep_tickers={"IWM", "AAPL", "GOOGL"},
    )

    row = report["negative_trades"][0]
    assert row["failure_category"] == "missing_review_timeline"
    assert row["executable_exit_before_negative"] is False
    assert row["executable_profit_sell_before_final_loss"] is False
