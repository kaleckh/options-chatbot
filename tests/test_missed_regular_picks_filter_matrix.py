from __future__ import annotations

import unittest

from scripts import analyze_missed_regular_picks_filter_matrix as matrix


def _row(
    playbook: str,
    ticker: str,
    net_pct: float,
    *,
    scan_date: str = "2026-06-01",
    tracked: bool = False,
    dte: int = 12,
    debit_pct: float = 35.0,
) -> dict:
    return {
        "scan_date": scan_date,
        "playbook": playbook,
        "ticker": ticker,
        "direction": "call",
        "expiry": "2026-06-12",
        "contract_symbol": f"{ticker}260612C00100000",
        "short_contract_symbol": f"{ticker}260612C00110000",
        "long_strike": 100.0,
        "short_strike": 110.0,
        "dte": dte,
        "net_debit": 3.5,
        "debit_pct_of_width": debit_pct,
        "tracked_match_count": 1 if tracked else 0,
        "mark": {
            "priced": True,
            "entry_debit": 3.5,
            "exit_credit": round(3.5 * (1.0 + net_pct / 100.0), 2),
            "net_pnl_pct": net_pct,
            "net_pnl_usd": net_pct,
        },
    }


def _outcome_report() -> dict:
    rows = [
        _row("bad_lane", "BAD", -80.0, scan_date="2026-06-01", dte=40, debit_pct=55.0),
        _row("bad_lane", "BAD", -20.0, scan_date="2026-06-02", dte=42, debit_pct=50.0),
        _row("good_lane", "GOOD", 30.0, scan_date="2026-06-03"),
        _row("good_lane", "OK", 20.0, scan_date="2026-06-04"),
        _row("tracked_lane", "TRK", -5.0, tracked=True),
    ]
    duplicate = dict(rows[2])
    duplicate["playbook"] = "other_good_lane"
    rows.append(duplicate)
    return {
        "generated_at_utc": "2026-06-05T19:35:21Z",
        "summary": {
            "raw_row_count": len(rows),
            "tracked_row_count": 1,
            "untracked_row_count": 5,
            "tracked_rows_with_stored_pnl": 1,
            "mark_coverage_count": len(rows),
            "mark_unpriced_count": 0,
        },
        "lane_gate_rows": [
            {
                "playbook": "bad_lane",
                "auto_track_allowed": False,
                "blockers": ["profit_factor_below_lane_gate"],
                "metrics": {},
                "self_guardrails": {},
            },
            {
                "playbook": "good_lane",
                "auto_track_allowed": True,
                "blockers": [],
                "metrics": {},
                "self_guardrails": {"max_debit_pct_of_width": 45.0, "blocked_tickers": []},
            },
            {
                "playbook": "other_good_lane",
                "auto_track_allowed": True,
                "blockers": [],
                "metrics": {},
                "self_guardrails": {"max_debit_pct_of_width": 45.0, "blocked_tickers": []},
            },
        ],
        "rows": rows,
    }


def test_filter_matrix_reports_lane_gate_and_dedupe_scenarios() -> None:
    report = matrix.build_filter_matrix_report(_outcome_report())
    scenarios = {item["scenario_id"]: item for item in report["scenarios"]}

    assert report["summary"]["priced_untracked_rows"] == 5
    assert scenarios["baseline_all_untracked"]["kept_metrics"]["profit_factor"] < 1.0
    assert scenarios["current_lane_gate_self_guardrails"]["kept_metrics"]["profit_factor"] == 999.0
    assert scenarios["current_lane_gate_self_guardrails"]["lost_winner_count"] == 0
    assert scenarios["exact_spread_dedupe_only"]["blocked_count"] == 1
    assert scenarios["lane_gate_self_guardrails_plus_exact_spread_dedupe"]["kept_count"] == 2


def test_filter_matrix_markdown_contains_policy_read() -> None:
    report = matrix.build_filter_matrix_report(_outcome_report())
    markdown = matrix.render_markdown(report)

    assert "## Matrix" in markdown
    assert "lane_gate_self_guardrails_plus_exact_spread_dedupe" in markdown
    assert "not live-production permission" in markdown


class MissedRegularPicksFilterMatrixTests(unittest.TestCase):
    def test_filter_matrix_reports_lane_gate_and_dedupe_scenarios(self) -> None:
        test_filter_matrix_reports_lane_gate_and_dedupe_scenarios()

    def test_filter_matrix_markdown_contains_policy_read(self) -> None:
        test_filter_matrix_markdown_contains_policy_read()
