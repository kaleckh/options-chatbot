from __future__ import annotations

from scripts import replay_short_term_filter_point_in_time as replay


def _fill(
    ticker: str,
    *,
    position_id: int | None,
    playbook_id: str = "short_term",
    fill_degradation: float = 16.0,
    label: str = "executable_opra_paper_candidate",
    basis: str = "spread_ask_bid",
):
    row = {
        "event_type": "candidate_shown",
        "status": "shown",
        "scan_date": "2026-06-02",
        "playbook_id": playbook_id,
        "ticker": ticker,
        "direction": "call",
        "expiry": "2026-06-26",
        "fill_degradation_vs_mid_pct": fill_degradation,
        "candidate_execution_label": label,
        "attempted_limit_basis": basis,
        "fill_status": "auto_tracked",
        "fill_outcome": "paper_fill_recorded",
        "selected_spread": {
            "long_contract_symbol": f"{ticker}260626C00100000",
            "long_strike": 100.0,
            "short_strike": 110.0,
        },
    }
    if position_id is not None:
        row["auto_track_position_id"] = position_id
    return row


def _stop_row(position_id: int, pnl: float):
    return {
        "position_id": position_id,
        "baseline_pnl_pct": pnl,
        "entry_execution_basis": "spread_ask_bid",
        "exit_execution_basis": "historical_spread_bid_ask",
    }


def test_point_in_time_replay_keeps_filter_lane_scoped_and_counts_winner_damage():
    report = replay.build_report(
        fill_attempt_rows=[
            _fill("SPY", position_id=1, fill_degradation=16.0),
            _fill("QQQ", position_id=2, fill_degradation=18.0),
            _fill("IWM", position_id=3, fill_degradation=10.0),
            _fill("DIA", position_id=4, playbook_id="swing", fill_degradation=20.0),
        ],
        stop_grid={"report_id": "fixture_stop_grid", "rows": [_stop_row(1, -95.0), _stop_row(2, 45.0), _stop_row(3, 30.0), _stop_row(4, -80.0)]},
        starvation_audit={},
    )

    assert report["matched"]["rows"] == 2
    assert report["matched"]["exact_priced_rows"] == 2
    assert report["effects"]["avoided_near_total_losses"] == 1
    assert report["effects"]["lost_winners"] == 1
    assert report["kept"]["rows"] == 2
    assert report["coverage"]["matched_ticker_counts"] == {"SPY": 1, "QQQ": 1}


def test_point_in_time_replay_rejects_stale_or_unlinked_rows_as_unpriced():
    report = replay.build_report(
        fill_attempt_rows=[
            _fill("SPY", position_id=1, label="stale_snapshot_candidate"),
            _fill("QQQ", position_id=None),
        ],
        stop_grid={"rows": [_stop_row(1, -90.0)]},
        starvation_audit={
            "generated_at_utc": "2026-06-02T21:00:00Z",
            "playbooks": [{"playbook_id": "short_term", "returned_count": 0}],
        },
    )

    assert report["matched"]["rows"] == 2
    assert report["matched"]["exact_priced_rows"] == 0
    assert report["coverage"]["unpriced_or_non_executable_count"] == 2
    assert report["coverage"]["unpriced_reasons"] == {
        "entry_not_fresh_executable_opra_nbbo": 1,
        "missing_realized_pnl": 1,
    }
    assert report["coverage"]["zero_pick_days"] == ["2026-06-02"]
    assert "unpriced_or_non_executable_rows_present" in report["decision_summary"]["promotion_blockers"]
