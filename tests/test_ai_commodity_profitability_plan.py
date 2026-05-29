from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_ai_commodity_profitability_plan import (
    build_cohort_throughput,
    build_forward_session_summary,
    build_lane_b_throughput_diagnostics,
    build_liquidity_near_miss_log_summary,
    build_profitability_plan,
)


def _sample_progress():
    return {
        "generated_at": "2026-05-23T14:14:55Z",
        "provider": "alpaca:sip:opra",
        "proof_source_label": "alpaca_opra_daily_snapshot",
        "proof_window": {
            "current_shared_quote_dates": 3,
            "required_shared_quote_dates": 100,
            "approx_diagnostic_ready_date_if_one_capture_per_market_day": "2026-09-24",
            "approx_completion_date_if_one_capture_per_market_day": "2026-10-12",
        },
        "source_quality": {
            "status": "usable_quotes_waiting_for_history_depth",
            "min_executable_quote_pct": 100.0,
        },
        "verification_gate": {
            "status": "not_verified",
            "verified": False,
            "replay_total_trades": None,
            "replay_profit_factor": None,
            "replay_total_return_pct": None,
            "gates": {
                "live_scan_has_candidate": False,
                "exact_replay_profit_factor_positive": False,
            },
        },
        "profitability_evidence_scorecard": {
            "current_shared_quote_dates": 3,
            "required_shared_quote_dates": 100,
            "next_evidence_event_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-26",
            "next_evidence_event_not_before_user_local": "2026-05-26T14:20:00-06:00",
        },
        "scan": {
            "candidate_count": 0,
            "candidate_symbols": [],
            "scan_drop_reason_count": 4,
            "scan_drop_reason_symbols_by_drop": {
                "option_liquidity": ["AA", "CCJ"],
                "tech_score": ["VRT"],
                "momentum": ["FCX"],
            },
            "scan_funnel": {
                "raw_candidates": 0,
                "returned_picks": 0,
                "drop_counts": {
                    "option_liquidity": 2,
                    "tech_score": 1,
                    "momentum": 1,
                },
            },
            "drop_diagnostics": [
                {
                    "drop_key": "option_liquidity",
                    "count": 2,
                    "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    "nearest_examples": [
                        {
                            "symbol": "CCJ",
                            "liquidity_reasons": ["wide_leg_spread", "stale_leg_quote"],
                            "worst_leg_spread_excess_pct": 7.83,
                            "quote_age_excess_hours": 10.26,
                            "ask_bid": {"ask": 1.12, "bid": 0.78},
                            "executable_debit": 1.18,
                            "top_spread_alternatives": [
                                {"legs": ["CCJ250619C00045000", "CCJ250619C00050000"], "executable_debit": 1.18},
                                {"legs": ["CCJ250619C00044000", "CCJ250619C00049000"], "executable_debit": 1.06},
                            ],
                        }
                    ],
                }
            ],
        },
        "live_candidate_recovery_plan": {
            "dominant_drop_key": "option_liquidity",
            "safe_to_tune_production_filters": False,
            "top_drop_counts": [{"drop_key": "option_liquidity", "count": 2}],
        },
    }


def test_build_cohort_throughput_preserves_pre_registered_groups():
    cohorts = build_cohort_throughput(_sample_progress())
    by_id = {row["cohort"]: row for row in cohorts}

    assert by_id["full_24"]["symbol_count"] == 24
    assert by_id["core_options"]["symbol_count"] == 9
    assert by_id["conditional_options"]["symbol_count"] == 15
    assert by_id["full_24"]["dominant_drop_key"] == "option_liquidity"
    assert by_id["core_options"]["drop_counts"]["option_liquidity"] == 1


def test_build_profitability_plan_blocks_profit_claim_and_counts_true_playbook_only():
    plan = build_profitability_plan(
        _sample_progress(),
        forward_summary={
            "session_count": 14,
            "scan_picks_per_session": 0.0,
            "true_playbook_position_review_pnl": {
                "review_count": 0,
                "sum_net_pnl_usd": None,
                "policy": "only_reviews_whose_payload_source_pick_snapshot_playbook_id_matches_commodity_playbook_count",
            },
        },
        onclickmedia_eod={
            "source_label": "onclickmedia_research_grade_eod_bidask",
            "source_grade": "research_grade_eod_bidask",
            "proof_grade": False,
            "selected_shared_dates": {"count": 100, "first": "2026-01-02", "last": "2026-05-22"},
            "symbol_count": 24,
            "row_count": 1000,
            "executable_bid_ask_rows": 900,
            "executable_bid_ask_pct": 90.0,
            "usage_policy": "research_grade_eod_bidask_for_signal_and_fillability_research_not_opra_intraday_proof",
        },
    )

    assert plan["claim_status"] == "not_verified_unmeasured"
    assert plan["profitability_summary"]["forward_true_playbook_review_count"] == 0
    assert plan["proof_depth"]["current_shared_quote_dates"] == 3
    assert plan["proof_depth"]["remaining_shared_quote_dates"] == 97
    assert plan["opportunity_throughput"]["latest_candidate_count"] == 0
    assert plan["opportunity_throughput"]["dominant_drop_key"] == "option_liquidity"
    assert plan["gates"]["safe_to_tune_production_filters"] is False
    assert plan["research_grade_eod_bidask"]["available"] is True
    assert plan["research_grade_eod_bidask"]["proof_grade"] is False
    assert plan["event_macro_concentration_controls"]["policy"] == "research_only_no_production_gate_changes"
    assert "insufficient_records_for_research_controls" in plan["event_macro_concentration_controls"]["promotion_blockers"]
    assert any(item["status"] == "implemented_in_this_report" for item in plan["technical_plan"])
    assert "Do not count SPY/QQQ bullish-pullback P&L as commodity-lane profitability." in plan["non_goals"]
    assert "Do not promote OnclickMedia EOD chains as OPRA proof-grade intraday NBBO." in plan["non_goals"]


class AiCommodityProfitabilityPlanUnitTests(unittest.TestCase):
    def test_forward_session_summary_rejects_non_finite_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "forward.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE forward_sessions (
                        id INTEGER PRIMARY KEY,
                        playbook TEXT,
                        recorded_at_utc TEXT,
                        scan_picks_count INTEGER,
                        reviewed_positions_count INTEGER,
                        eligibility_status TEXT,
                        quote_freshness_status TEXT
                    );
                    CREATE TABLE forward_events (
                        id INTEGER PRIMARY KEY,
                        session_id INTEGER,
                        event_type TEXT,
                        payload_json TEXT,
                        net_pnl_pct REAL,
                        net_pnl_usd REAL
                    );
                    """
                )
                conn.execute(
                    """
                    INSERT INTO forward_sessions (
                        id, playbook, recorded_at_utc, scan_picks_count, reviewed_positions_count,
                        eligibility_status, quote_freshness_status
                    ) VALUES (1, 'ai_commodity_infra_observation', '2026-05-25T14:00:00Z', 1, 1, 'eligible', 'fresh')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO forward_events (
                        session_id, event_type, payload_json, net_pnl_pct, net_pnl_usd
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "position_review",
                        json.dumps({"source_pick_snapshot": {"playbook_id": "ai_commodity_infra_observation"}}),
                        float("inf"),
                        float("inf"),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            summary = build_forward_session_summary(db_path)

        self.assertEqual(summary["true_playbook_position_review_pnl"]["review_count"], 1)
        self.assertIsNone(summary["true_playbook_position_review_pnl"]["avg_net_pnl_pct"])
        self.assertIsNone(summary["true_playbook_position_review_pnl"]["sum_net_pnl_usd"])


def test_lane_b_throughput_diagnostics_preserves_gates_and_ranks_near_misses():
    diagnostics = build_lane_b_throughput_diagnostics(
        _sample_progress(),
        liquidity_near_miss_log={
            "status": "active",
            "record_count": 3,
        },
    )

    assert diagnostics["lane_id"] == "ai_commodity_infra_observation"
    assert diagnostics["status"] == "zero_returned_with_recorded_drop_reasons"
    assert diagnostics["production_gate_policy"] == "diagnostic_only_preserve_production_gates"
    assert diagnostics["safe_to_tune_production_filters"] is False
    assert diagnostics["safe_to_tune_reason"] == "exact_replay_and_oos_gates_not_ready"
    assert diagnostics["dominant_drop_key"] == "option_liquidity"
    assert diagnostics["drop_rank"][0] == {"drop_key": "option_liquidity", "count": 2}
    assert diagnostics["latest_funnel"]["returned_picks"] == 0
    assert diagnostics["cohort_throughput"][0]["cohort"] == "full_24"
    assert diagnostics["near_miss_queue"][0]["symbol"] == "CCJ"
    assert diagnostics["near_miss_queue"][0]["ask_bid"] == {"ask": 1.12, "bid": 0.78}
    assert diagnostics["near_miss_queue"][0]["executable_debit"] == 1.18
    assert diagnostics["near_miss_queue"][0]["top_spread_alternatives"][1]["executable_debit"] == 1.06
    assert diagnostics["near_miss_queue"][0]["research_only"] is True
    assert diagnostics["near_miss_queue"][0]["non_promotable"] is True
    assert diagnostics["near_miss_log_status"] == "active"
    assert "rerun_live_scan_inside_fresh_opra_window_before_filter_changes" in diagnostics["next_diagnostic_actions"]
    assert diagnostics["research_policy"]["research_only"] is True
    assert diagnostics["research_policy"]["non_promotable"] is True
    assert diagnostics["research_policy"]["near_miss_diagnostics_promotable"] is False
    assert "widen_spread_or_slippage_gates" in diagnostics["research_policy"]["forbidden_production_changes"]


def test_profitability_plan_embeds_lane_b_diagnostics_and_keeps_gate_closed():
    progress = _sample_progress()
    progress["live_candidate_recovery_plan"]["safe_to_tune_production_filters"] = True

    plan = build_profitability_plan(progress)

    assert plan["lane_b_throughput_diagnostics"]["dominant_drop_key"] == "option_liquidity"
    assert plan["lane_b_throughput_diagnostics"]["production_gate_policy"] == "diagnostic_only_preserve_production_gates"
    assert plan["opportunity_denominator_diagnostics"]["near_miss_log_status"] == "evidence_gap_missing_liquidity_near_misses_jsonl"
    assert plan["opportunity_denominator_diagnostics"]["near_miss_log_evidence_gap"]["kind"] == "missing_liquidity_near_misses_jsonl"
    assert plan["opportunity_denominator_diagnostics"]["dominant_drop_key"] == "option_liquidity"
    assert plan["opportunity_denominator_diagnostics"]["drop_counts"]["option_liquidity"] == 2
    assert plan["opportunity_denominator_diagnostics"]["near_miss_queue"][0]["non_promotable"] is True
    assert plan["opportunity_denominator_diagnostics"]["research_policy"]["near_miss_diagnostics_promotable"] is False
    assert plan["opportunity_throughput"]["denominator_diagnostics"]["near_miss_queue"][0]["research_only"] is True
    assert plan["gates"]["safe_to_tune_production_filters"] is False


def test_missing_liquidity_near_miss_log_is_explicit_evidence_gap(tmp_path):
    log_path = tmp_path / "liquidity_near_misses.jsonl"

    summary = build_liquidity_near_miss_log_summary(log_path)
    plan = build_profitability_plan(_sample_progress(), liquidity_near_miss_log=summary)

    assert summary["available"] is False
    assert summary["status"] == "evidence_gap_missing_liquidity_near_misses_jsonl"
    assert summary["evidence_gap"]["kind"] == "missing_liquidity_near_misses_jsonl"
    assert plan["near_miss_fillability_log"]["evidence_gap"]["log_path"] == str(log_path)
    assert plan["opportunity_denominator_diagnostics"]["near_miss_log_evidence_gap"]["severity"] == "evidence_gap"


def test_liquidity_near_miss_log_summary_preserves_executable_cost_fields_and_aliases(tmp_path):
    log_path = tmp_path / "liquidity_near_misses.jsonl"
    rows = [
        {
            "event_type": "liquidity_near_miss",
            "playbook_id": "ai_commodity_infra_observation",
            "logged_at": "2026-05-25T14:00:00Z",
            "scan_date": "2026-05-25",
            "ticker": "CCJ",
            "liquidity_reasons": ["wide_spread"],
            "distance_to_current_filters": 0.25,
            "distance_components": {"spread_slippage_excess_pct": 0.3},
            "ask_bid": {"ask": 1.12, "bid": 0.78},
            "intended_ask_bid_debit": 0.34,
            "intended_limit_debit": 0.34,
            "executable_debit": 1.18,
            "max_quote_age_hours": 12.5,
            "quote_age_excess_hours": 4.5,
            "no_fill_reason": "spread_ask_bid_not_fillable_inside_filters",
            "liquidity_reason": "wide_spread",
            "top_alternatives": [
                {"symbol": "CCJ", "executable_debit": 1.18, "spread_slippage_excess_pct": 0.3},
                {"symbol": "CCJ", "executable_debit": 1.06, "spread_slippage_excess_pct": 0.1},
            ],
        },
        {
            "event_type": "liquidity_near_miss",
            "playbook_id": "other_playbook",
            "ticker": "AA",
            "executable_debit": 9.99,
        },
    ]
    log_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")

    summary = build_liquidity_near_miss_log_summary(log_path)

    assert summary["status"] == "active"
    assert summary["record_count"] == 1
    assert summary["research_policy"]["research_only"] is True
    assert summary["research_policy"]["non_promotable"] is True
    assert summary["research_policy"]["near_miss_diagnostics_promotable"] is False
    nearest = summary["nearest_records"][0]
    assert nearest["ticker"] == "CCJ"
    assert nearest["ask_bid"] == {"ask": 1.12, "bid": 0.78}
    assert nearest["intended_ask_bid_debit"] == 0.34
    assert nearest["intended_limit_debit"] == 0.34
    assert nearest["executable_debit"] == 1.18
    assert nearest["max_quote_age_hours"] == 12.5
    assert nearest["quote_age_excess_hours"] == 4.5
    assert nearest["no_fill_reason"] == "spread_ask_bid_not_fillable_inside_filters"
    assert nearest["liquidity_reason"] == "wide_spread"
    assert nearest["distance_to_current_filters"] == 0.25
    assert nearest["distance_components"]["spread_slippage_excess_pct"] == 0.3
    assert nearest["top_alternatives"][1]["executable_debit"] == 1.06
    assert nearest["top_spread_alternatives"][1]["executable_debit"] == 1.06
    assert nearest["research_only"] is True
    assert nearest["non_promotable"] is True


def test_profitability_plan_marks_manual_log_records_research_only():
    plan = build_profitability_plan(
        _sample_progress(),
        liquidity_near_miss_log={
            "status": "active",
            "record_count": 1,
            "nearest_records": [
                {
                    "ticker": "CCJ",
                    "ask_bid": {"ask": 1.12, "bid": 0.78},
                    "executable_debit": 1.18,
                    "top_alternatives": [{"executable_debit": 1.18}],
                }
            ],
        },
    )

    nearest = plan["near_miss_fillability_log"]["nearest_records"][0]
    assert nearest["executable_debit"] == 1.18
    assert nearest["top_alternatives"][0]["executable_debit"] == 1.18
    assert nearest["top_spread_alternatives"][0]["executable_debit"] == 1.18
    assert nearest["research_only"] is True
    assert nearest["non_promotable"] is True
    assert plan["opportunity_denominator_diagnostics"]["near_miss_log_record_count"] == 1
    assert plan["opportunity_denominator_diagnostics"]["nearest_near_miss_log_records"][0]["research_only"] is True
