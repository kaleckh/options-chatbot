from __future__ import annotations

from pathlib import Path

from scripts.build_regular_profitability_operating_scorecard import build_scorecard


def test_scorecard_marks_product_progress_but_keeps_proof_blocked(tmp_path: Path):
    autoresearch = tmp_path / "autoresearch.json"
    autoresearch.write_text(
        """
        {
          "experiment_batch": "batch",
          "best": {
            "variant_id": "lane_a_goal_test",
            "score": 0,
            "research_score": 166.55,
            "status": "scout_or_blocked",
            "promotion_blockers": ["lane_a_conservative_pf_below_1_30"],
            "autoresearch_metrics": {
              "promotable_clean_count": 0,
              "scout_count": 191,
              "lane_a_conservative_profit_factor": 0.92,
              "zero_bid_exit_rate_pct": 43.24
            }
          }
        }
        """,
        encoding="utf8",
    )
    guardrails = tmp_path / "guardrails.json"
    guardrails.write_text(
        """
        {
          "baseline": {
            "rows": 429,
            "priced": 383,
            "avg_pnl_pct": 5.21,
            "median_pnl_pct": -1.58,
            "negative_rate_priced_pct": 50.4
          },
          "combined_promoted_guardrails": {
            "kept": {
              "rows": 130,
              "priced": 116,
              "avg_pnl_pct": 53.08,
              "median_pnl_pct": 46.4,
              "negative_rate_priced_pct": 25.0
            },
            "blocked": {
              "rows": 299,
              "priced": 267,
              "avg_pnl_pct": -15.59,
              "median_pnl_pct": -25.08,
              "negative_rate_priced_pct": 61.4
            }
          },
          "promoted_guardrails": ["debit_gt_45_width"]
        }
        """,
        encoding="utf8",
    )
    negative = tmp_path / "negative.json"
    negative.write_text(
        """
        {
          "legacy_missed_close_targets": [
            {
              "trade_id": 26,
              "ticker": "JPM",
              "final_pnl_pct": -44.7,
              "failure_category": "missed_executable_profit_exit_before_final_loss"
            }
          ],
          "negative_trades": [
            {"failure_category": "entry_guardrail_now_blocks"}
          ]
        }
        """,
        encoding="utf8",
    )
    exit_replay = tmp_path / "exit.json"
    exit_replay.write_text(
        """
        {
          "baseline": {"avg_pnl_pct": 37.28},
          "policies": [
            {
              "policy_id": "current_policy_replay",
              "recommendation": {"status": "research_candidate"},
              "legacy_targets": [
                {
                  "trade_id": 26,
                  "ticker": "JPM",
                  "baseline_pnl_pct": -44.7,
                  "policy_pnl_pct": 3.9,
                  "delta_vs_baseline_pct": 48.6,
                  "reason": "time_exit"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf8",
    )
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        """
        {
          "summary": {
            "target_count": 1,
            "diagnosis_counts": {"stale_or_non_autoclosing_review_path": 1},
            "current_action_required_count": 0,
            "historical_stale_path_count": 1,
            "recommendation": "no_broad_exit_policy_change; preserve as historical stale-policy diagnostic"
          },
          "rows": []
        }
        """,
        encoding="utf8",
    )
    starvation = tmp_path / "starvation.json"
    starvation.write_text(
        """
        {
          "generated_at_utc": "2026-06-01T00:00:00Z",
          "overall": {
            "status": "upstream_zero_candidate_scan_pressure",
            "playbooks_requested": 13,
            "playbooks_completed": 13,
            "candidate_count_total": 0,
            "returned_count_total": 0,
            "candidate_decision_counts": {},
            "starvation_playbooks": [],
            "zero_candidate_playbooks": ["short_term", "swing"],
            "top_drop_counts": [{"value": "option_liquidity", "count": 96}]
          },
          "errors": []
        }
        """,
        encoding="utf8",
    )
    open_risk = tmp_path / "open-risk.json"
    open_risk.write_text(
        """
        {
          "generated_at_utc": "2026-06-01T00:05:00Z",
          "summary": {
            "rows": 48,
            "priced_or_marked": 47,
            "avg_pnl_pct": 10.04
          },
          "evidence_counts": {
            "fresh_executable_review": 47,
            "fresh_unpriced_review": 1
          },
          "action_counts": {
            "hold_or_positive": 32,
            "negative_mark_hold_or_unknown": 15,
            "stored_non_executable_sell": 1
          },
          "actionable_position_ids": [104],
          "actionable_positions": [
            {
              "id": 104,
              "ticker": "SBUX",
              "action_bucket": "stored_non_executable_sell",
              "pricing_state": "priced_display_only_last",
              "next_safe_action": "do_not_auto_close_from_display_only_mark_rerun_explicit_review_during_fresh_executable_quote_window"
            }
          ]
        }
        """,
        encoding="utf8",
    )
    suggested_risk = tmp_path / "suggested-risk.json"
    suggested_risk.write_text(
        """
        {
          "generated_at_utc": "2026-06-01T00:10:00Z",
          "storage_available": true,
          "summary": {
            "rows": 2,
            "priced_or_marked": 1,
            "avg_pnl_pct": -24.0
          },
          "closed_summary": {
            "rows": 1,
            "priced_or_marked": 1
          },
          "evidence_counts": {
            "stale_mark_or_non_executable_review": 1,
            "missing_review": 1
          },
          "action_counts": {
            "stored_non_executable_sell": 1,
            "no_stored_review": 1
          },
          "close_risk_trade_ids": [201],
          "stale_or_missing_review_trade_ids": [201, 202],
          "attention_trade_ids": [201, 202],
          "attention_trades": [
            {
              "id": 201,
              "ticker": "AAA",
              "action_bucket": "stored_non_executable_sell",
              "pricing_state": "priced_display_only_last",
              "next_safe_action": "do_not_close_suggested_trade_from_non_executable_mark_rerun_explicit_review"
            },
            {
              "id": 202,
              "ticker": "BBB",
              "action_bucket": "no_stored_review",
              "pricing_state": null,
              "next_safe_action": "refresh_explicit_suggested_trade_review_before_using_close_or_pnl_state"
            }
          ]
        }
        """,
        encoding="utf8",
    )
    api_performance = tmp_path / "api-performance.json"
    api_performance.write_text(
        """
        {
          "generated_at_utc": "2026-06-01T00:15:00Z",
          "summary": {
            "status": "ok",
            "endpoint_count": 6,
            "ok_endpoint_count": 6,
            "error_endpoint_count": 0,
            "frontend_max_elapsed_ms": 121.4,
            "frontend_total_payload_bytes": 45200,
            "backend_max_duration_ms": 72.8,
            "slowest_frontend_endpoint": {
              "label": "next_tracked_positions_closed_page_100",
              "target": "next_route",
              "path": "/api/positions?status=closed&limit=100&offset=0",
              "status_code": 200,
              "elapsed_ms": 121.4,
              "backend_duration_ms": 72.8,
              "payload_bytes": 34000,
              "row_count": 100,
              "page": {"limit": 100, "offset": 0, "returned": 100}
            },
            "largest_payload_endpoint": {
              "label": "next_tracked_positions_closed_page_100",
              "target": "next_route",
              "path": "/api/positions?status=closed&limit=100&offset=0",
              "status_code": 200,
              "elapsed_ms": 121.4,
              "backend_duration_ms": 72.8,
              "payload_bytes": 34000,
              "row_count": 100,
              "page": {"limit": 100, "offset": 0, "returned": 100}
            },
            "cache_stats": {
              "status": "ok",
              "memory_cache_entries": 12,
              "totals": {"hit": 4, "miss": 2}
            }
          },
          "endpoints": []
        }
        """,
        encoding="utf8",
    )
    ai_commodity = tmp_path / "ai-commodity-progress.json"
    ai_commodity.write_text(
        """
        {
          "generated_at": "2026-05-31T09:10:46Z",
          "provider": "alpaca:sip:opra",
          "proof_source_label": "alpaca_opra_daily_snapshot",
          "proof_window": {
            "current_shared_quote_dates": 3,
            "required_shared_quote_dates": 100,
            "remaining_shared_quote_dates": 97,
            "progress_pct": 3.0,
            "diagnostic_ready": false,
            "approx_completion_date_if_one_capture_per_weekday": "2026-10-12"
          },
          "verification_gate": {
            "status": "not_verified",
            "verified": false,
            "blockers": ["shared_quote_dates:3/100", "live_scan_candidates:0"],
            "current_shared_quote_dates": 3,
            "required_shared_quote_dates": 100,
            "replay_total_trades": null,
            "replay_profit_factor": null,
            "replay_total_return_pct": null,
            "live_scan_candidate_count": 0,
            "proof_eligible_candidate_count": 0,
            "source_quality_status": "usable_quotes_waiting_for_history_depth"
          },
          "readiness": {
            "status": "partial",
            "blocker": "thin_required_history",
            "thin_required_underlyings": ["AA", "FCX"],
            "missing_required_underlyings": []
          },
          "scan": {
            "candidate_count": 0,
            "proof_eligible_candidate_count": 0,
            "scan_drop_reason_count": 24,
            "drop_diagnostics": [
              {
                "drop_key": "option_liquidity",
                "count": 13,
                "example_symbols": ["AA", "BHP", "FCX"],
                "next_diagnostic_action": "after_fresh_quotes_recheck_quote_age_then_structural_spread_distance"
              }
            ]
          },
          "capture": {
            "status": "no_rows_captured",
            "target_date": "2026-05-26",
            "target_capture_complete": false,
            "missing_target_date_symbols_after": ["AA", "BHP", "FCX"]
          },
          "lane_next_step": {
            "phase": "proof_universe_alignment",
            "priority_action": "repair_full_scan_universe_capture_and_proof_alignment",
            "primary_blocker": "capture_target_incomplete",
            "blocked_gates": ["capture_target_complete", "enough_exact_shared_quote_dates"],
            "safe_to_tune_filters": false,
            "next_timed_event_kind": "fresh_opra_scan",
            "next_timed_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            "next_timed_event_user_local": "2026-06-01T08:10:00-06:00"
          },
          "lane_next_step_plan": {
            "status": "waiting_for_not_before",
            "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "run_next_execution_command": false
          },
          "guarded_command_decision": {
            "status": "waiting_until_next_guarded_event",
            "safe_to_execute_now": false,
            "command": null,
            "next_command_when_allowed": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "reason": "waiting_until_not_before:2026-06-01T08:10:00-06:00",
            "next_not_before_user_local": "2026-06-01T08:10:00-06:00"
          },
          "exact_capture_progress_outcome": {
            "status": "exact_capture_progress_failed_or_not_observed",
            "material_progress": false,
            "next_action": "recapture_or_inspect_exact_alpaca_opra_import_failure",
            "blockers": ["shared_quote_dates_increased_from_contract", "capture_target_complete_true"]
          },
          "profitability_evidence_scorecard_status": "recording_progress_waiting_for_exact_history_depth",
          "profitability_evidence_scorecard_passed_requirement_count": 4,
          "profitability_evidence_scorecard_total_requirement_count": 9,
          "profitability_evidence_scorecard_blockers": ["alpaca_opra_daily_snapshot_shared_quote_dates:3/100"],
          "goal_completion_failed_requirements": [
            "has_required_exact_alpaca_opra_history_depth",
            "exact_replay_is_profitable"
          ]
        }
        """,
        encoding="utf8",
    )
    entry_filter_monitor = tmp_path / "entry-filter-monitor.json"
    entry_filter_monitor.write_text(
        """
        {
          "generated_at_utc": "2026-06-02T02:02:39Z",
          "inputs": {
            "since_date": "2026-06-02",
            "champion_filter_id": "short_term_fill_degradation_ge_15"
          },
          "baseline": {
            "rows": 0,
            "closed_rows": 0,
            "priced_rows": 0,
            "avg_pnl_pct": null,
            "median_pnl_pct": null
          },
          "champion": {
            "matched": {
              "rows": 0,
              "closed_rows": 0,
              "avg_pnl_pct": null
            },
            "kept": {
              "avg_pnl_pct": null,
              "median_pnl_pct": null
            }
          },
          "gate": {
            "status": "collecting",
            "failures": ["insufficient_fresh_rows"],
            "live_policy_change": false
          }
        }
        """,
        encoding="utf8",
    )
    entry_filter_walkforward = tmp_path / "entry-filter-walkforward.json"
    entry_filter_walkforward.write_text(
        """
        {
          "generated_at_utc": "2026-06-02T03:00:00Z",
          "inputs": {
            "row_count": 112,
            "months": ["2026-04", "2026-05"],
            "latest_holdout_month": "2026-05"
          },
          "decision_summary": {
            "status": "mixed_walkforward_watch_not_promoted",
            "candidate_filter_id": "short_term_fill_degradation_ge_15",
            "live_policy_change": false,
            "recommended_next_action": "Keep paper-only."
          },
          "portfolio": {
            "frozen_champion": {
              "status": "historical_pass_candidate",
              "matched": {"rows": 9},
              "kept": {"avg_pnl_pct": 61.01, "median_pnl_pct": 53.33},
              "avoided_deep_losses": 5,
              "avoided_near_total_losses": 3,
              "lost_winners": 2
            },
            "broad_all_lanes_fill_degradation_ge_15": {
              "status": "winner_damage_too_high",
              "matched": {"rows": 19},
              "lost_winners": 10
            }
          },
          "chronological_holdout": {
            "train": {"status": "winner_damage_too_high"},
            "holdout": {
              "status": "historical_pass_candidate",
              "matched": {"rows": 6},
              "kept": {"avg_pnl_pct": 14.37}
            }
          },
          "concentration": {
            "lane_statuses": {
              "short_term": "historical_pass_candidate",
              "swing": "no_deep_loss_reduction"
            },
            "passing_months": ["2026-05"],
            "failing_months": ["2026-04"]
          }
        }
        """,
        encoding="utf8",
    )
    profit_capture_queue = tmp_path / "profit-capture-queue.json"
    profit_capture_queue.write_text(
        """
        {
          "generated_at_utc": "2026-06-02T04:00:00Z",
          "status": "research_paper_capture_queue",
          "live_policy_change": false,
          "summary": {
            "queue_rows": 3,
            "tier_counts": {
              "tier_a_clean_exact_capture": 1,
              "tier_b_profitable_watch_repair": 2
            },
            "evidence_repair_priority_counts": {
              "high": 1,
              "none": 1,
              "medium": 1
            },
            "fresh_scan_match_count": 2,
            "fresh_scan_guardrail_decision_counts": {
              "blocked": 1,
              "clear": 1
            },
            "blocked_but_interesting_count": 1,
            "high_priority_evidence_repair_count": 1,
            "quarantine_queue_count": 2,
            "quarantine_overlay_count": 1,
            "live_policy_change": false
          },
          "final_readback": {
            "top_clean_exact": [
              {
                "symbol": "NEM",
                "lane_id": "bullish_pullback_observation",
                "capture_tier": "tier_a_clean_exact_capture",
                "status": "keep",
                "metrics": {
                  "exact_trusted_priced_trades": 16,
                  "unresolved_rows": 0,
                  "quote_coverage": 100.0,
                  "profit_factor": 13.37,
                  "avg_pnl": 84.03,
                  "median_pnl": 80.0
                },
                "evidence_repair_priority": "none",
                "reason_codes": []
              }
            ],
            "top_watch_repair": [
              {
                "symbol": "GOOGL",
                "lane_id": "tracked_winner_primary",
                "capture_tier": "tier_b_profitable_watch_repair",
                "status": "watch",
                "metrics": {
                  "exact_trusted_priced_trades": 34,
                  "unresolved_rows": 7,
                  "quote_coverage": 82.93,
                  "profit_factor": 7.14,
                  "avg_pnl": 54.01,
                  "median_pnl": 45.0
                },
                "evidence_repair_priority": "high",
                "reason_codes": ["unresolved_rows_remain"]
              }
            ],
            "evidence_repair_queue": [
              {
                "symbol": "GOOGL",
                "lane_id": "tracked_winner_primary",
                "capture_tier": "tier_b_profitable_watch_repair",
                "status": "watch",
                "metrics": {
                  "exact_trusted_priced_trades": 34,
                  "unresolved_rows": 7,
                  "quote_coverage": 82.93,
                  "profit_factor": 7.14,
                  "avg_pnl": 54.01,
                  "median_pnl": 45.0
                },
                "evidence_repair_priority": "high",
                "reason_codes": ["unresolved_rows_remain"]
              }
            ],
            "fresh_scan_matches": [
              {
                "symbol": "SPY",
                "playbook_id": "swing",
                "capture_tier": "tier_c_fresh_scan_signature_match",
                "guardrail_decision": "clear",
                "match_type": "lane_signature",
                "debit_pct_of_width": 37.9,
                "quality_score": 97.9,
                "guardrail_reasons": [],
                "matched_sleeves": []
              }
            ],
            "blocked_but_interesting": [
              {
                "symbol": "QQQ",
                "playbook_id": "speculative",
                "capture_tier": "blocked_but_interesting",
                "guardrail_decision": "blocked",
                "match_type": "symbol_only",
                "debit_pct_of_width": 49.9,
                "quality_score": 63.6,
                "guardrail_reasons": ["quality below minimum"],
                "matched_sleeves": []
              }
            ]
          }
        }
        """,
        encoding="utf8",
    )

    scorecard = build_scorecard(
        autoresearch_path=autoresearch,
        guardrails_path=guardrails,
        negative_audit_path=negative,
        exit_replay_path=exit_replay,
        legacy_missed_close_path=legacy,
        guardrail_starvation_path=starvation,
        open_position_risk_path=open_risk,
        suggested_trade_close_risk_path=suggested_risk,
        api_performance_path=api_performance,
        ai_commodity_progress_path=ai_commodity,
        entry_filter_monitor_path=entry_filter_monitor,
        entry_filter_walkforward_path=entry_filter_walkforward,
        profit_capture_queue_path=profit_capture_queue,
    )

    assert scorecard["scope"] == "active_options_operating_scorecard"
    assert scorecard["status"] == "visible_product_profitability_progress_but_proof_still_blocked"
    assert scorecard["product_profitability_progress_visible"] is True
    assert scorecard["proof_grade_profitability_progress_visible"] is False
    assert scorecard["trading_desk_guardrails"]["deltas_vs_baseline"]["avg_pnl_pct"] == 47.87
    assert scorecard["trading_desk_guardrails"]["promoted_guardrails"] == ["debit_gt_45_width"]
    assert scorecard["negative_decision_audit"]["legacy_missed_close_target_count"] == 1
    assert scorecard["legacy_missed_close_audit"]["current_action_required_count"] == 0
    assert scorecard["guardrail_starvation_audit"]["status"] == "upstream_zero_candidate_scan_pressure"
    assert scorecard["entry_filter_paper_monitor"]["status"] == "collecting"
    assert scorecard["entry_filter_paper_monitor"]["champion_filter_id"] == "short_term_fill_degradation_ge_15"
    assert scorecard["entry_filter_paper_monitor"]["live_policy_change"] is False
    assert scorecard["entry_filter_walkforward"]["status"] == "mixed_walkforward_watch_not_promoted"
    assert scorecard["entry_filter_walkforward"]["candidate_filter_id"] == "short_term_fill_degradation_ge_15"
    assert scorecard["entry_filter_walkforward"]["frozen_avoided_deep_losses"] == 5
    assert scorecard["entry_filter_walkforward"]["broad_all_lanes_status"] == "winner_damage_too_high"
    assert scorecard["entry_filter_walkforward"]["latest_holdout_status"] == "historical_pass_candidate"
    assert scorecard["entry_filter_walkforward"]["live_policy_change"] is False
    assert scorecard["profit_capture_queue"]["status"] == "research_paper_capture_queue"
    assert scorecard["profit_capture_queue"]["queue_rows"] == 3
    assert scorecard["profit_capture_queue"]["tier_counts"]["tier_a_clean_exact_capture"] == 1
    assert scorecard["profit_capture_queue"]["high_priority_evidence_repair_count"] == 1
    assert scorecard["profit_capture_queue"]["fresh_scan_guardrail_decision_counts"]["clear"] == 1
    assert scorecard["profit_capture_queue"]["blocked_but_interesting_count"] == 1
    assert scorecard["profit_capture_queue"]["quarantine_queue_count"] == 2
    assert scorecard["profit_capture_queue"]["top_watch_repair"][0]["symbol"] == "GOOGL"
    assert scorecard["profit_capture_queue"]["live_policy_change"] is False
    assert scorecard["open_position_risk"]["open_rows"] == 48
    assert scorecard["open_position_risk"]["review_required_count"] == 1
    assert scorecard["open_position_risk"]["executable_close_ready_count"] == 0
    assert scorecard["open_position_risk"]["actionable_position_ids"] == [104]
    assert scorecard["suggested_trade_close_risk"]["open_rows"] == 2
    assert scorecard["suggested_trade_close_risk"]["stored_non_executable_sell_count"] == 1
    assert scorecard["suggested_trade_close_risk"]["stale_or_missing_review_count"] == 2
    assert scorecard["suggested_trade_close_risk"]["review_required_count"] == 2
    assert scorecard["api_performance"]["status"] == "ok"
    assert scorecard["api_performance"]["frontend_max_elapsed_ms"] == 121.4
    assert scorecard["api_performance"]["backend_max_duration_ms"] == 72.8
    assert scorecard["api_performance"]["cache_stats"]["memory_cache_entries"] == 12
    assert scorecard["api_performance"]["largest_payload_endpoint"]["row_count"] == 100
    assert scorecard["ai_commodity_progress"]["status"] == "recording_progress_waiting_for_exact_history_depth"
    assert scorecard["ai_commodity_progress"]["provider"] == "alpaca:sip:opra"
    assert scorecard["ai_commodity_progress"]["current_shared_quote_dates"] == 3
    assert scorecard["ai_commodity_progress"]["required_shared_quote_dates"] == 100
    assert scorecard["ai_commodity_progress"]["capture_target_complete"] is False
    assert scorecard["ai_commodity_progress"]["missing_target_symbol_count"] == 3
    assert scorecard["ai_commodity_progress"]["guarded_command_safe_to_execute_now"] is False
    assert scorecard["ai_commodity_progress"]["safe_to_tune_filters"] is False
    assert scorecard["ai_commodity_progress"]["top_scan_drops"][0]["drop_key"] == "option_liquidity"
    assert any("display-only marks" in action for action in scorecard["next_actions"])
    assert any("suggested trades from stale/display-only marks" in action for action in scorecard["next_actions"])
    assert any("stale or missing suggested-trade reviews" in action for action in scorecard["next_actions"])
    assert any("historical stale-policy diagnostics" in action for action in scorecard["next_actions"])
    assert any("Do not loosen promoted Trading Desk entry guardrails" in action for action in scorecard["next_actions"])
    assert any("short-term fill-degradation entry filter paper-only" in action for action in scorecard["next_actions"])
    assert any("all-lane walk-forward rejects the broad fill>=15 rule" in action for action in scorecard["next_actions"])
    assert any("profit capture queue" in action for action in scorecard["next_actions"])
    assert any("Tier C matches" in action for action in scorecard["next_actions"])
    assert any("profitable-looking candidates blocked" in action for action in scorecard["next_actions"])
    assert any("AI commodity production filters locked" in action for action in scorecard["next_actions"])
    assert any("AI commodity exact OPRA capture failure" in action for action in scorecard["next_actions"])
