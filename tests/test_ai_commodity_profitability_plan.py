from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_ai_commodity_profitability_plan import (
    build_cohort_throughput,
    build_lane_b_throughput_diagnostics,
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
    assert diagnostics["near_miss_log_status"] == "active"
    assert "rerun_live_scan_inside_fresh_opra_window_before_filter_changes" in diagnostics["next_diagnostic_actions"]
    assert "widen_spread_or_slippage_gates" in diagnostics["research_policy"]["forbidden_production_changes"]


def test_profitability_plan_embeds_lane_b_diagnostics_and_keeps_gate_closed():
    progress = _sample_progress()
    progress["live_candidate_recovery_plan"]["safe_to_tune_production_filters"] = True

    plan = build_profitability_plan(progress)

    assert plan["lane_b_throughput_diagnostics"]["dominant_drop_key"] == "option_liquidity"
    assert plan["lane_b_throughput_diagnostics"]["production_gate_policy"] == "diagnostic_only_preserve_production_gates"
    assert plan["gates"]["safe_to_tune_production_filters"] is False
