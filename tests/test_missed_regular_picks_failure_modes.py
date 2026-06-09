from __future__ import annotations

import unittest

from scripts import analyze_missed_regular_picks_failure_modes as failure


def _row(playbook: str, ticker: str, net_pct: float, *, tracked: bool = False, dte: int = 12, debit_pct: float = 35.0) -> dict:
    return {
        "scan_date": "2026-06-01",
        "playbook": playbook,
        "ticker": ticker,
        "contract_symbol": f"{ticker}260612C00100000",
        "short_contract_symbol": f"{ticker}260612C00110000",
        "dte": dte,
        "net_debit": 3.5,
        "debit_pct_of_width": debit_pct,
        "tracked_match_count": 1 if tracked else 0,
        "tracked_positions": [{"pnl_pct": 11.0}] if tracked else [],
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
        _row("bad_lane", "BAD", -50.0, dte=40, debit_pct=55.0),
        _row("bad_lane", "BAD", -30.0, dte=42, debit_pct=50.0),
        _row("good_lane", "GOOD", 15.0, debit_pct=30.0),
        _row("good_lane", "OK", 10.0, debit_pct=30.0),
        _row("tracked_lane", "TRK", -5.0, tracked=True),
    ]
    return {
        "generated_at_utc": "2026-06-05T19:35:21Z",
        "inputs": {
            "source_labels": ["thetadata_opra_nbbo_1m"],
            "trusted_only": True,
            "quote_evidence": {
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "quote_evidence_label": "Trusted intraday OPRA/NBBO",
                "quote_snapshot_kind": "intraday",
                "quote_data_trust": "trusted",
                "production_proof_source_eligible": True,
            },
            "evidence_policy": {
                "record_class": "missed_regular_pick_research_mark",
                "evidence_group": "research_backfill",
                "production_proof": False,
                "research_learning": True,
            },
        },
        "summary": {
            "raw_row_count": len(rows),
            "tracked_row_count": 1,
            "untracked_row_count": 4,
            "tracked_rows_with_stored_pnl": 1,
            "mark_coverage_count": len(rows),
            "mark_unpriced_count": 0,
        },
        "lane_gate_rows": [
            {
                "playbook": "bad_lane",
                "auto_track_allowed": False,
                "blockers": ["profit_factor_below_lane_gate", "average_net_pnl_not_positive"],
                "metrics": failure._metrics(rows[:2]),
                "self_guardrails": {},
            },
            {
                "playbook": "good_lane",
                "auto_track_allowed": True,
                "blockers": [],
                "metrics": failure._metrics(rows[2:4]),
                "self_guardrails": {"max_debit_pct_of_width": 35.0, "blocked_tickers": []},
            },
        ],
        "rows": rows,
    }


def test_failure_report_classifies_clean_data_and_unprofitable_strategy() -> None:
    report = failure.build_failure_report(_outcome_report(), min_cluster_rows=2)

    assert report["data_quality"]["data_status"] == "clean_for_failure_analysis"
    assert report["summary"]["quote_evidence_class"] == "trusted_intraday_opra_nbbo"
    assert report["summary"]["row_evidence_group"] == "research_backfill"
    assert report["boundary"]["production_claim"] is False
    assert report["boundary"]["quote_evidence"]["quote_evidence_class"] == "trusted_intraday_opra_nbbo"
    assert report["overall_read"]["status"] == "data_clean_strategy_unprofitable"
    assert report["earn_back_policy"]["diagnostic_to_probation_requires"]["min_exact_marked_rows"] == 30
    assert report["earn_back_policy"]["diagnostic_to_probation_requires"]["min_later_date_or_out_of_sample_rows"] == 10

    decisions = {item["playbook"]: item for item in report["lane_decisions"]}
    assert decisions["good_lane"]["decision"] == "probation_candidate_flow_with_self_guardrails"
    assert decisions["bad_lane"]["decision"] == "diagnostic_only_until_earn_back"

    ticker_candidates = report["pre_entry_guardrail_candidates"]["ticker_quarantine_candidates"]
    assert any(item["ticker"] == "BAD" for item in ticker_candidates)
    assert report["pre_entry_guardrail_candidates"]["debit_pct_gte_45_diagnostic"]["rows"] == 2
    assert report["pre_entry_guardrail_candidates"]["dte_gte_36_diagnostic"]["rows"] == 2


def test_failure_report_markdown_contains_decisions_and_boundaries() -> None:
    report = failure.build_failure_report(_outcome_report(), min_cluster_rows=2)
    markdown = failure.render_markdown(report)

    assert "## Lane Decisions" in markdown
    assert "bad_lane" in markdown
    assert "good_lane" in markdown
    assert "Quote evidence class" in markdown
    assert "Production proof claim" in markdown
    assert "## Earn-Back Policy" in markdown
    assert "not broker execution evidence" in markdown


class MissedRegularPicksFailureModesTests(unittest.TestCase):
    def test_failure_report_classifies_clean_data_and_unprofitable_strategy(self) -> None:
        test_failure_report_classifies_clean_data_and_unprofitable_strategy()

    def test_failure_report_markdown_contains_decisions_and_boundaries(self) -> None:
        test_failure_report_markdown_contains_decisions_and_boundaries()
