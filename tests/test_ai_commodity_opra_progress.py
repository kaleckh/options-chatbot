from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_ai_commodity_opra_progress import (  # noqa: E402
    _load_recent_progress_history_entries,
    _scan_summary,
    annotate_scan_quote_freshness_timing,
    annotate_scheduled_capture_timing,
    automation_schedule_coverage,
    build_alpaca_opra_data_usage_audit,
    build_capture_action_summary,
    build_compact_progress_summary,
    build_diagnostic_replay_summary,
    build_deferred_variant_promotion_review,
    build_exact_history_backfill_capability_audit,
    build_exact_history_acquisition_plan,
    build_exact_capture_import_health,
    build_exact_capture_post_run_evaluation,
    build_exact_capture_progress_contract,
    build_exact_capture_progress_outcome,
    build_exact_profitability_blocker_review,
    build_exact_replay_readiness_checklist,
    build_exact_replay_runway_progress_contract,
    build_exact_replay_smoke_probe_observation,
    build_exact_replay_smoke_probe_plan,
    build_exact_replay_smoke_zero_trade_diagnostic,
    build_exact_replay_unlock_contract,
    build_goal_completion_audit,
    build_goal_completion_evidence_plan,
    build_goal_completion_verification_contract,
    build_guarded_capture_runbook_packet,
    build_fresh_scan_iteration_decision,
    build_fresh_scan_post_run_evaluation,
    build_iteration_ledger,
    build_lane_iteration_plan,
    build_lane_next_step_summary,
    build_lane_next_step_plan,
    build_live_candidate_recovery_plan,
    build_next_profitability_evidence_sequence,
    build_auxiliary_proof_event_queue,
    build_last_execution_review,
    build_next_execution_contract,
    build_next_execution_cli_payload,
    build_next_execution_preflight,
    build_next_proof_event_checkpoint,
    build_post_fresh_scan_research_backlog,
    build_profitability_evidence_scorecard,
    build_profitability_evidence_scorecard_delta,
    build_previous_auxiliary_proof_event_outcome,
    build_previous_proof_event_outcome,
    build_proof_window,
    build_proof_source_audit,
    build_proof_source_isolation_contract,
    build_progress_delta,
    build_progress_history_summary,
    build_raw_drop_reason_evidence_contract,
    build_scan_proof_universe_alignment,
    build_source_quality_summary,
    build_run_auxiliary_proof_event_guard_summary,
    build_strict_accuracy_gate,
    build_verified_profitability_gate,
    capture_status_from_import,
    attach_deferred_variant_result_collection,
    attach_progress_record_summary_fields,
    collect_deferred_variant_results,
    diagnostic_replay_required_shared_quote_dates,
    diagnostic_replay_blockers,
    diagnostic_replay_max_dte_from_wfo,
    load_capture_automation_health,
    load_latest_commodity_research_lab,
    load_latest_exact_replay_smoke_probe_observation,
    load_previous_progress_report,
    main,
    materialize_deferred_variant_configs,
    next_blocker,
    next_fresh_scan_time,
    refresh_derived_fields_from_latest,
    replay_simulation_min_shared_quote_dates,
    render_markdown,
    run_deferred_variant_sweeps,
    run_progress,
    scheduled_capture_time_for_trade_date,
    symbols_missing_target_date,
    write_progress_report,
    write_exact_replay_smoke_probe_observation,
)


class _FakeStore:
    def __init__(self, dates_by_symbol, *, source_dates_by_symbol=None, source_labels=None):
        self.dates_by_symbol = dates_by_symbol
        self.source_dates_by_symbol = source_dates_by_symbol or {}
        self.source_labels = source_labels or []

    def available_quote_dates(self, symbol, *, snapshot_kind=None, trusted_only=False, source_labels=None):
        labels = [str(label) for label in (source_labels or []) if str(label)]
        if labels:
            dates: set[str] = set()
            for label in labels:
                dates.update(self.source_dates_by_symbol.get(label, {}).get(symbol, []))
            return sorted(dates)
        return list(self.dates_by_symbol.get(symbol, []))

    def shared_quote_dates(self, symbols, *, snapshot_kind=None, trusted_only=False, source_labels=None):
        symbol_list = [str(symbol).upper() for symbol in symbols]
        if not symbol_list:
            return []
        shared = set(self.available_quote_dates(symbol_list[0], source_labels=source_labels))
        for symbol in symbol_list[1:]:
            shared &= set(self.available_quote_dates(symbol, source_labels=source_labels))
        return sorted(shared)

    def summarize_imports(self, snapshot_kind=None, *, trusted_only=False):
        return {"source_labels": list(self.source_labels)}


class _ScopedInventoryFakeStore(_FakeStore):
    def source_inventory(
        self,
        snapshot_kind=None,
        *,
        trusted_only=False,
        source_labels=None,
        underlyings=None,
    ):
        requested = [str(symbol or "").strip().upper() for symbol in underlyings or [] if str(symbol or "").strip()]
        labels_with_quotes: list[str] = []
        sources: list[dict[str, object]] = []
        for source_label in self.source_labels:
            source_dates = self.source_dates_by_symbol.get(source_label, {})
            underlyings_in_scope = [
                symbol for symbol in requested
                if source_dates.get(symbol)
            ]
            if underlyings_in_scope:
                labels_with_quotes.append(source_label)
            sources.append(
                {
                    "source_label": source_label,
                    "quote_rows_in_scope": len(underlyings_in_scope),
                    "underlyings_in_scope": underlyings_in_scope,
                    "quote_dates": {
                        "count": len(
                            {
                                date_text
                                for symbol in underlyings_in_scope
                                for date_text in source_dates.get(symbol, [])
                            }
                        )
                    },
                }
            )
        return {
            "status": "summarized",
            "source_labels_seen": list(self.source_labels),
            "source_labels_with_quotes_in_scope": labels_with_quotes,
            "sources": sources,
        }


class AiCommodityOpraProgressTests(unittest.TestCase):
    def _clean_proof_source_isolation_contract(self):
        return {
            "status": "isolated_to_alpaca_opra_proof_source",
            "decision": "only_alpaca_opra_daily_snapshot_counts_for_exact_profitability_proof",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "exact_profitability_proof_source_labels": ["alpaca_opra_daily_snapshot"],
            "research_only_source_labels": [],
            "non_proof_sources_with_quotes_in_scope": [],
            "non_proof_sources_with_shared_dates": [],
            "top_level_shared_dates_match_proof_source": True,
            "blockers": [],
            "next_action": "continue_using_alpaca_opra_proof_source",
        }

    def _verified_profitable_goal_report(self):
        return {
            "generated_at": "2026-05-21T20:30:00Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "current_shared_quote_dates": 100,
                "required_shared_quote_dates": 100,
            },
            "readiness": {"status": "ready_for_exact_replay"},
            "verification_gate": {
                "status": "verified_profitable",
                "verified": True,
                "blockers": [],
                "replay_profit_factor": 1.4,
                "replay_total_return_pct": 8.2,
                "replay_total_trades": 22,
                "live_scan_candidate_count": 1,
                "live_scan_candidate_symbols": ["FCX"],
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": True,
                    "readiness_ready_for_exact_replay": True,
                    "exact_replay_completed": True,
                    "exact_replay_has_trades": True,
                    "exact_replay_profit_factor_positive": True,
                    "exact_replay_total_return_positive": True,
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": True,
                },
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T20:30:00Z",
                "status": "verified_profitable",
                "next_evidence_action": "goal_complete",
            },
            "next_execution_contract": {
                "status": "verified",
                "matches_next_timed_event": True,
            },
            "automation_health": {"healthy": True},
        }

    def test_load_previous_progress_report_returns_none_when_missing_or_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_previous_progress_report(Path(tmp)))
            latest = Path(tmp) / "latest.json"
            latest.write_text("{not-json", encoding="utf8")
            self.assertIsNone(load_previous_progress_report(Path(tmp)))

    def test_load_previous_progress_report_reads_latest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "latest.json"
            latest.write_text(json.dumps({"generated_at": "2026-05-20T20:00:00Z"}), encoding="utf8")

            loaded = load_previous_progress_report(Path(tmp))

        self.assertEqual(loaded, {"generated_at": "2026-05-20T20:00:00Z"})

    def test_load_latest_commodity_research_lab_marks_bar_only_research_non_verifying(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "latest.json"
            latest.write_text(
                json.dumps(
                    {
                        "run_at_utc": "2026-05-21T06:00:10Z",
                        "scope": "commodity",
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-20",
                        "symbols": ["FCX", "PWR"],
                        "data_policy": {
                            "option_research_fallback": "alpaca_opra_historical_bars_no_bidask",
                            "promotion_trade_basis": "exact_bid_ask only",
                        },
                        "artifact_paths": {"latest_json": "latest.json"},
                        "lanes": [
                            {
                                "lane": "bullish",
                                "status": "research_only",
                                "promotion_allowed": False,
                                "variant": "pullback_uptrend",
                                "all_trade_summary": {
                                    "trade_count": 6,
                                    "bar_fallback_count": 6,
                                    "profit_factor": 0.0,
                                    "avg_pnl_pct": -74.83,
                                },
                                "exact_bid_ask_proof_summary": {"trade_count": 0},
                                "rejected_candidate_reasons": {"missing_exit_date": 1},
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )

            summary = load_latest_commodity_research_lab(Path(tmp))

        self.assertTrue(summary["present"])
        self.assertEqual(summary["status"], "commodity_research_only")
        self.assertFalse(summary["used_for_verification"])
        self.assertEqual(summary["total_bar_fallback_trades"], 6)
        self.assertEqual(summary["total_exact_bid_ask_trades"], 0)
        self.assertEqual(
            summary["next_action"],
            "do_not_promote_bar_only_research_accumulate_exact_alpaca_opra_bid_ask_dates",
        )
        self.assertEqual(summary["lane_summaries"][0]["all_avg_pnl_pct"], -74.83)

    def test_load_latest_commodity_research_lab_rejects_non_commodity_latest_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "latest.json"
            latest.write_text(json.dumps({"scope": "normal", "lanes": []}), encoding="utf8")

            summary = load_latest_commodity_research_lab(Path(tmp))

        self.assertEqual(summary["status"], "latest_lab_not_commodity_scope")
        self.assertFalse(summary["used_for_verification"])

    def test_build_progress_delta_records_improvements_and_regressions(self):
        previous = {
            "generated_at": "2026-05-20T20:00:00Z",
            "proof_source_label": "thetadata_free_eod",
            "proof_source_audit": {
                "trusted_only": False,
                "all_required_symbols_have_proof_source_data": False,
            },
            "shared_quote_dates_after": {"count": 1},
            "proof_window": {"remaining_shared_quote_dates": 99},
            "scan": {
                "candidate_count": 0,
                "gate_sensitivity": {
                    "closest_ev_floor": {
                        "symbol": "FCX",
                        "candidate_heuristic_ev_pct": 1.0,
                        "heuristic_ev_shortfall_pct": 4.0,
                    },
                    "closest_option_liquidity": {
                        "symbol": "ETN",
                        "combined_gate_distance": 8.0,
                    },
                },
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "review_count": 1,
                        "lowest_distance_to_current_filter": 6.5,
                    }
                ]
            },
            "replay": {"error": "too few dates"},
            "automation_health": {"healthy": False},
            "source_quality": {
                "status": "missing_required_underlyings",
                "total_quote_rows": 10,
                "available_required_underlying_count": 1,
                "min_executable_quote_pct": 80.0,
                "total_missing_bid_ask_rows": 2,
                "total_crossed_quote_rows": 1,
            },
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "capture_automation_healthy": False,
                    "enough_exact_shared_quote_dates": False,
                    "live_scan_has_candidate": False,
                },
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
            },
        }
        current = {
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_audit": {
                "trusted_only": True,
                "all_required_symbols_have_proof_source_data": True,
            },
            "shared_quote_dates_after": {"count": 2},
            "proof_window": {"remaining_shared_quote_dates": 98},
            "scan": {
                "candidate_count": 1,
                "gate_sensitivity": {
                    "closest_ev_floor": {
                        "symbol": "FCX",
                        "candidate_heuristic_ev_pct": 3.0,
                        "heuristic_ev_shortfall_pct": 2.0,
                    },
                    "closest_option_liquidity": {
                        "symbol": "SCCO",
                        "combined_gate_distance": 3.0,
                    },
                },
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "review_count": 1,
                        "lowest_distance_to_current_filter": 5.0,
                    },
                    {
                        "symbol": "PWR",
                        "drop_keys": ["tech_score"],
                        "review_count": 1,
                        "lowest_distance_to_current_filter": 12.0,
                    },
                ]
            },
            "replay": {"error": None},
            "automation_health": {"healthy": True},
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "total_quote_rows": 30,
                "available_required_underlying_count": 2,
                "min_executable_quote_pct": 95.5,
                "total_missing_bid_ask_rows": 0,
                "total_crossed_quote_rows": 0,
            },
            "next_blocker": "profitability_not_verified",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "capture_automation_healthy": True,
                    "enough_exact_shared_quote_dates": True,
                    "live_scan_has_candidate": True,
                    "exact_replay_profit_factor_positive": False,
                },
                "blockers": ["profit_factor:0.9"],
            },
        }

        delta = build_progress_delta(previous, current)

        self.assertTrue(delta["previous_report_found"])
        self.assertEqual(delta["previous_generated_at"], "2026-05-20T20:00:00Z")
        self.assertEqual(delta["shared_quote_dates_delta"], 1.0)
        self.assertEqual(delta["remaining_shared_quote_dates_delta"], -1.0)
        self.assertEqual(delta["scan_candidate_count_delta"], 1.0)
        self.assertEqual(delta["run_classification"], "improved")
        self.assertIsNone(delta["no_progress_reason"])
        self.assertEqual(delta["scan_closest_ev_symbol_before"], "FCX")
        self.assertEqual(delta["scan_closest_ev_symbol_after"], "FCX")
        self.assertEqual(delta["scan_ev_shortfall_delta"], -2.0)
        self.assertEqual(delta["scan_candidate_heuristic_ev_delta"], 2.0)
        self.assertEqual(delta["scan_closest_liquidity_symbol_before"], "ETN")
        self.assertEqual(delta["scan_closest_liquidity_symbol_after"], "SCCO")
        self.assertEqual(delta["scan_liquidity_gate_distance_delta"], -5.0)
        self.assertTrue(delta["next_blocker_changed"])
        self.assertTrue(delta["replay_error_changed"])
        self.assertTrue(delta["automation_healthy_changed"])
        self.assertEqual(delta["source_quality_status_before"], "missing_required_underlyings")
        self.assertEqual(delta["source_quality_status_after"], "usable_quotes_waiting_for_history_depth")
        self.assertFalse(delta["source_quality_usable_before"])
        self.assertTrue(delta["source_quality_usable_after"])
        self.assertEqual(delta["source_quality_total_quote_rows_delta"], 20.0)
        self.assertEqual(delta["source_quality_available_underlyings_delta"], 1.0)
        self.assertEqual(delta["source_quality_min_executable_pct_delta"], 15.5)
        self.assertEqual(delta["source_quality_missing_bid_ask_rows_delta"], -2.0)
        self.assertEqual(delta["source_quality_crossed_quote_rows_delta"], -1.0)
        self.assertEqual(
            delta["read_only_watchlist_distance_deltas"],
            [
                {
                    "symbol": "ALB",
                    "drop_keys": ["option_liquidity"],
                    "previous_distance_to_current_filter": 6.5,
                    "current_distance_to_current_filter": 5.0,
                    "distance_delta": -1.5,
                    "direction": "closer_to_current_filters",
                    "material": True,
                }
            ],
        )
        self.assertEqual(delta["read_only_watchlist_symbols_added"], ["PWR"])
        self.assertEqual(delta["read_only_watchlist_symbols_removed"], [])
        self.assertEqual(delta["read_only_watchlist_material_improvement_count"], 1)
        self.assertEqual(delta["read_only_watchlist_material_regression_count"], 0)
        self.assertEqual(delta["read_only_watchlist_best_distance_delta"], -1.5)
        self.assertEqual(delta["proof_source_label_before"], "thetadata_free_eod")
        self.assertEqual(delta["proof_source_label_after"], "alpaca_opra_daily_snapshot")
        self.assertTrue(delta["proof_source_label_changed"])
        self.assertFalse(delta["proof_source_trusted_only_before"])
        self.assertTrue(delta["proof_source_trusted_only_after"])
        self.assertTrue(delta["proof_source_trusted_only_changed"])
        self.assertFalse(delta["proof_source_all_required_symbols_available_before"])
        self.assertTrue(delta["proof_source_all_required_symbols_available_after"])
        self.assertTrue(delta["proof_source_all_required_symbols_available_changed"])
        self.assertEqual(delta["verification_status_before"], "not_verified")
        self.assertEqual(delta["verification_status_after"], "not_verified")
        self.assertEqual(
            delta["verification_gates_newly_passed"],
            [
                "capture_automation_healthy",
                "enough_exact_shared_quote_dates",
                "live_scan_has_candidate",
            ],
        )
        self.assertEqual(delta["verification_gates_regressed"], [])
        self.assertEqual(delta["verification_gates_still_blocked"], ["exact_replay_profit_factor_positive"])
        self.assertEqual(
            delta["improvement_flags"],
            [
                "source_filtered_shared_quote_dates_increased",
                "remaining_capture_dates_decreased",
                "live_scan_candidates_increased",
                "scan_ev_shortfall_decreased",
                "scan_candidate_heuristic_ev_increased",
                "scan_liquidity_gate_distance_decreased",
                "replay_error_cleared",
                "capture_automation_restored",
                "source_quality_became_usable",
                "source_quality_quote_rows_increased",
                "source_quality_available_underlyings_increased",
                "source_quality_min_executable_pct_increased",
                "source_quality_missing_bid_ask_rows_decreased",
                "source_quality_crossed_quote_rows_decreased",
                "read_only_watchlist_distance_decreased",
                "proof_source_switched_to_alpaca_opra_daily_snapshot",
                "proof_source_trusted_only_enabled",
                "proof_source_all_required_symbols_available",
                "verification_gates_newly_passed",
            ],
        )
        self.assertEqual(delta["regression_flags"], [])

    def test_build_progress_delta_handles_missing_previous_report(self):
        delta = build_progress_delta(None, {"next_blocker": "x"})

        self.assertFalse(delta["previous_report_found"])
        self.assertEqual(delta["run_classification"], "initial_report")
        self.assertIsNone(delta["no_progress_reason"])
        self.assertEqual(delta["non_material_flags"], [])
        self.assertEqual(delta["improvement_flags"], [])
        self.assertEqual(delta["regression_flags"], [])

    def test_scan_summary_requires_proof_grade_source_for_proof_eligible_picks(self):
        summary = _scan_summary(
            {
                "candidate_count": 1,
                "candidate_audit_picks": [
                    {
                        "ticker": "FCX",
                        "proof_eligible": True,
                        "guardrail_decision": "clear",
                        "source_label": "onclickmedia_research_grade_eod_bidask",
                    },
                    {
                        "ticker": "NUE",
                        "proof_eligible": True,
                        "guardrail_decision": "clear",
                        "source_label": "non_opra_vendor",
                    },
                    {
                        "ticker": "AA",
                        "proof_eligible": True,
                        "guardrail_decision": "clear",
                        "source_label": "alpaca_opra_daily_snapshot",
                    },
                ],
            }
        )

        self.assertEqual(summary["proof_eligible_candidate_count"], 1)
        self.assertEqual(summary["proof_eligible_candidate_symbols"], ["AA"])

    def test_verified_profitability_gate_rejects_non_finite_replay_metrics(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {"current_shared_quote_dates": 100, "required_shared_quote_dates": 100},
                "automation_health": {"healthy": True},
                "source_quality": {"status": "usable"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12, "profit_factor": float("inf"), "total_return_pct": float("inf")},
                "scan": {"proof_eligible_candidate_count": 1, "proof_eligible_candidate_symbols": ["FCX"]},
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "scan_universe_count": 1,
                    "proof_universe_count": 1,
                    "live_scan_candidates_all_inside_exact_proof": True,
                },
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 1,
                    "target_capture_complete": True,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["exact_replay_profit_factor_positive"])
        self.assertFalse(gate["gates"]["exact_replay_total_return_positive"])

    def test_build_progress_delta_classifies_watchlist_distance_regression_and_noise(self):
        previous = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "lowest_distance_to_current_filter": 5.0,
                    },
                    {
                        "symbol": "PWR",
                        "drop_keys": ["tech_score"],
                        "lowest_distance_to_current_filter": 10.0,
                    },
                ]
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
        }
        current = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "lowest_distance_to_current_filter": 5.4,
                    },
                    {
                        "symbol": "PWR",
                        "drop_keys": ["tech_score"],
                        "lowest_distance_to_current_filter": 10.1,
                    },
                ]
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "regressed")
        self.assertEqual(delta["read_only_watchlist_material_regression_count"], 1)
        self.assertEqual(delta["read_only_watchlist_non_material_change_count"], 1)
        self.assertEqual(delta["read_only_watchlist_worst_distance_delta"], 0.4)
        self.assertIn("read_only_watchlist_distance_increased", delta["regression_flags"])
        self.assertNotIn("read_only_watchlist_distance_delta_below_materiality", delta["non_material_flags"])

    def test_build_progress_delta_marks_tiny_watchlist_distance_change_non_material(self):
        previous = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "lowest_distance_to_current_filter": 5.0,
                    }
                ]
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
        }
        current = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_watchlist": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "lowest_distance_to_current_filter": 5.1,
                    }
                ]
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "unchanged_same_blocker")
        self.assertEqual(delta["read_only_watchlist_non_material_change_count"], 1)
        self.assertEqual(delta["non_material_flags"], ["read_only_watchlist_distance_delta_below_materiality"])
        self.assertEqual(delta["improvement_flags"], [])
        self.assertEqual(delta["regression_flags"], [])

    def test_build_progress_delta_records_read_only_missing_field_progress(self):
        previous = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measurement_plan": {
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    }
                }
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }
        current = {
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measurement_plan": {
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["sma20"],
                        "BHP": ["sma20"],
                        "CEG": ["sma20"],
                    }
                }
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "improved")
        self.assertEqual(delta["read_only_missing_field_count_before"], 9)
        self.assertEqual(delta["read_only_missing_field_count_after"], 3)
        self.assertEqual(delta["read_only_missing_field_count_delta"], -6.0)
        self.assertEqual(
            delta["read_only_filled_missing_fields_by_symbol"],
            {
                "AA": ["momentum_signal_distance_pct", "price"],
                "BHP": ["momentum_signal_distance_pct", "price"],
                "CEG": ["momentum_signal_distance_pct", "price"],
            },
        )
        self.assertEqual(
            delta["read_only_still_missing_fields_by_symbol"],
            {"AA": ["sma20"], "BHP": ["sma20"], "CEG": ["sma20"]},
        )
        self.assertEqual(delta["read_only_newly_missing_fields_by_symbol"], {})
        self.assertIn("read_only_missing_fields_filled", delta["improvement_flags"])
        self.assertEqual(delta["regression_flags"], [])

    def test_build_progress_delta_records_scan_drop_reason_audit_progress(self):
        previous = {
            "scan": {
                "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                "scan_drop_reason_count": 0,
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }
        current = {
            "scan": {
                "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                "scan_drop_reason_count": 12,
                "scan_drop_reason_symbols_by_drop": {"momentum": ["AA"]},
                "scan_drop_reason_detail_fields_by_drop": {
                    "momentum": ["ret5", "price", "sma20"]
                },
                "scan_drop_reason_derived_fields_by_drop": {
                    "momentum": ["momentum_signal_distance_pct"]
                },
                "scan_drop_reason_examples_by_symbol": {
                    "AA": {"symbol": "AA", "drop_key": "momentum", "ret5": 1.2}
                },
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "improved")
        self.assertEqual(
            delta["scan_drop_reason_audit_status_before"],
            "waiting_for_next_scan_result_with_raw_drop_reasons",
        )
        self.assertEqual(delta["scan_drop_reason_audit_status_after"], "raw_drop_reasons_recorded")
        self.assertTrue(delta["scan_drop_reason_audit_status_changed"])
        self.assertEqual(delta["scan_drop_reason_count_before"], 0)
        self.assertEqual(delta["scan_drop_reason_count_after"], 12)
        self.assertEqual(delta["scan_drop_reason_count_delta"], 12.0)
        self.assertEqual(delta["scan_drop_reason_symbols_by_drop_after"], {"momentum": ["AA"]})
        self.assertEqual(
            delta["scan_drop_reason_derived_fields_by_drop_after"],
            {"momentum": ["momentum_signal_distance_pct"]},
        )
        self.assertIn("scan_drop_reason_audit_recorded", delta["improvement_flags"])
        self.assertIn("scan_drop_reason_count_increased", delta["improvement_flags"])
        self.assertEqual(delta["regression_flags"], [])

    def test_build_progress_delta_does_not_count_skipped_scan_as_drop_reason_regression(self):
        previous = {
            "scan": {
                "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                "scan_drop_reason_count": 12,
            },
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }
        current = {
            "fresh_scan_decision_status": "scan_not_run",
            "fresh_scan_post_run_status": "scan_not_run",
            "scan_proof_universe_alignment": {"status": "scan_skipped"},
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "next_blocker": "live_scan_candidates:0",
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["scan_delta_evaluation_status"], "not_evaluated_scan_skipped")
        self.assertEqual(delta["scan_drop_reason_audit_status_before"], "raw_drop_reasons_recorded")
        self.assertEqual(delta["scan_drop_reason_audit_status_after"], "raw_drop_reasons_recorded")
        self.assertFalse(delta["scan_drop_reason_audit_status_changed"])
        self.assertEqual(delta["scan_drop_reason_count_delta"], 0.0)
        self.assertNotIn("scan_drop_reason_audit_lost", delta["regression_flags"])

    def test_attach_progress_record_summary_fields_copies_live_recovery_drop_audit(self):
        report: dict[str, object] = {}
        summary = {
            "live_candidate_recovery_scan_drop_reason_audit": {
                "status": "raw_drop_reasons_recorded",
                "count": 12,
                "symbols_by_drop": {"momentum": ["AA"]},
            },
            "live_candidate_recovery_scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
            "live_candidate_recovery_scan_drop_reason_count": 12,
            "live_candidate_recovery_scan_drop_reason_audit_blockers": [],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(
            report["live_candidate_recovery_scan_drop_reason_audit"],
            {
                "status": "raw_drop_reasons_recorded",
                "count": 12,
                "symbols_by_drop": {"momentum": ["AA"]},
            },
        )
        self.assertEqual(
            report["live_candidate_recovery_scan_drop_reason_audit_status"],
            "raw_drop_reasons_recorded",
        )
        self.assertEqual(report["live_candidate_recovery_scan_drop_reason_count"], 12)
        self.assertEqual(report["live_candidate_recovery_scan_drop_reason_audit_blockers"], [])

    def test_attach_progress_record_summary_fields_copies_live_recovery_distance_evidence(self):
        report: dict[str, object] = {}
        summary = {
            "live_candidate_recovery_status": "zero_candidates_waiting_for_exact_replay_unlock",
            "live_candidate_recovery_read_only_distance_measured_count": 2,
            "live_candidate_recovery_read_only_partial_distance_measurement_count": 1,
            "live_candidate_recovery_read_only_distance_measurement_gap_count": 1,
            "live_candidate_recovery_read_only_distance_measurement_missing_field_count": 3,
            "live_candidate_recovery_read_only_distance_measurement_missing_fields_by_symbol": {
                "AA": ["momentum_signal_distance_pct", "price", "sma20"]
            },
            "live_candidate_recovery_read_only_distance_measurement_plan_status": (
                "waiting_for_fresh_scan_signal_context"
            ),
            "live_candidate_recovery_read_only_symbols_to_watch": ["AA", "PWR"],
            "live_candidate_recovery_read_only_recovery_material_progress_if": [
                "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count decreases"
            ],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["live_candidate_recovery_status"], summary["live_candidate_recovery_status"])
        self.assertEqual(report["live_candidate_recovery_read_only_distance_measured_count"], 2)
        self.assertEqual(report["live_candidate_recovery_read_only_partial_distance_measurement_count"], 1)
        self.assertEqual(report["live_candidate_recovery_read_only_distance_measurement_gap_count"], 1)
        self.assertEqual(report["live_candidate_recovery_read_only_distance_measurement_missing_field_count"], 3)
        self.assertEqual(
            report["live_candidate_recovery_read_only_distance_measurement_missing_fields_by_symbol"],
            {"AA": ["momentum_signal_distance_pct", "price", "sma20"]},
        )
        self.assertEqual(
            report["live_candidate_recovery_read_only_distance_measurement_plan_status"],
            "waiting_for_fresh_scan_signal_context",
        )
        self.assertEqual(report["live_candidate_recovery_read_only_symbols_to_watch"], ["AA", "PWR"])
        self.assertEqual(
            report["live_candidate_recovery_read_only_recovery_material_progress_if"],
            [
                "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count decreases"
            ],
        )

    def test_attach_progress_record_summary_fields_copies_iteration_read_only_progress(self):
        report: dict[str, object] = {}
        summary = {
            "iteration_ledger_read_only_watchlist_progress": {
                "symbols_after": ["AA", "ALB"],
                "material_improvement_count": 1,
                "best_distance_delta": -0.5,
            },
            "iteration_ledger_read_only_missing_field_progress": {
                "missing_field_count_before": 9,
                "missing_field_count_after": 6,
                "filled_missing_field_count": 3,
                "still_missing_fields_by_symbol": {"AA": ["sma20"]},
            },
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(
            report["iteration_ledger_read_only_watchlist_progress"],
            {
                "symbols_after": ["AA", "ALB"],
                "material_improvement_count": 1,
                "best_distance_delta": -0.5,
            },
        )
        self.assertEqual(
            report["iteration_ledger_read_only_missing_field_progress"],
            {
                "missing_field_count_before": 9,
                "missing_field_count_after": 6,
                "filled_missing_field_count": 3,
                "still_missing_fields_by_symbol": {"AA": ["sma20"]},
            },
        )

    def test_attach_progress_record_summary_fields_copies_auxiliary_first_event(self):
        report: dict[str, object] = {}
        first_event = {
            "event_kind": "read_only_distance_measurement_fresh_scan",
            "status": "waiting_until_auxiliary_proof_event",
            "target_goal_requirement": "live_scan_has_verifiable_candidate",
            "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "not_before_user_local": "2026-05-22T08:10:00-06:00",
            "fields_to_compare_after_run": [
                "scan.candidate_count",
                "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count",
            ],
            "material_progress_if": [
                "future_fresh_alpaca_opra_scan.candidate_count > 0",
            ],
            "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        }
        summary = {
            "auxiliary_proof_event_count": 1,
            "auxiliary_first_proof_event": first_event,
            "auxiliary_first_proof_event_kind": first_event["event_kind"],
            "auxiliary_first_proof_event_status": first_event["status"],
            "auxiliary_first_proof_event_target_goal_requirement": first_event[
                "target_goal_requirement"
            ],
            "auxiliary_first_proof_event_command": first_event["command"],
            "auxiliary_first_proof_event_material_progress_if": first_event["material_progress_if"],
            "auxiliary_first_proof_event_fields_to_compare_after_run": first_event[
                "fields_to_compare_after_run"
            ],
            "auxiliary_first_proof_event_no_mutation_guard": first_event["no_mutation_guard"],
            "lane_next_step_plan_earliest_guarded_evidence_source": "auxiliary_evidence_opportunity",
            "lane_next_step_plan_earliest_guarded_evidence_command": first_event["command"],
            "lane_next_step_plan_earliest_guarded_evidence_command_role": (
                "fresh_live_candidate_scan_evidence"
            ),
            "lane_next_step_plan_earliest_guarded_evidence_not_before_user_local": first_event[
                "not_before_user_local"
            ],
            "lane_next_step_plan_earliest_guarded_evidence_material_progress_if": first_event[
                "material_progress_if"
            ],
            "lane_next_step_plan_earliest_guarded_evidence_blockers": [
                "scan_drop_reason_count_zero_or_missing"
            ],
            "lane_next_step_plan_earliest_guarded_evidence_no_mutation_guard": first_event[
                "no_mutation_guard"
            ],
            "next_execution_status": "waiting_until_not_before",
            "next_execution_selected_step": "post_close_full_universe_capture",
            "next_execution_not_before_user_local": "2026-05-22T14:20:00-06:00",
            "next_execution_command": [
                "python",
                "scripts/run_ai_commodity_opra_progress.py",
                "--force-capture",
                "--target-date",
                "2026-05-22",
            ],
            "next_execution_runbook_command": (
                "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
            ),
            "next_execution_runbook_guard_status": "clock_guard_active",
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["auxiliary_first_proof_event"], first_event)
        self.assertEqual(
            report["auxiliary_first_proof_event_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            report["auxiliary_first_proof_event_fields_to_compare_after_run"],
            [
                "scan.candidate_count",
                "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count",
            ],
        )
        self.assertEqual(
            report["auxiliary_first_proof_event_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_source"],
            "auxiliary_evidence_opportunity",
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_command_role"],
            "fresh_live_candidate_scan_evidence",
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_material_progress_if"],
            [
                "future_fresh_alpaca_opra_scan.candidate_count > 0",
            ],
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_blockers"],
            ["scan_drop_reason_count_zero_or_missing"],
        )
        self.assertEqual(
            report["lane_next_step_plan_earliest_guarded_evidence_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertEqual(report["next_execution_status"], "waiting_until_not_before")
        self.assertEqual(report["next_execution_selected_step"], "post_close_full_universe_capture")
        self.assertEqual(
            report["next_execution_not_before_user_local"],
            "2026-05-22T14:20:00-06:00",
        )
        self.assertEqual(
            report["next_execution_runbook_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
        )
        self.assertEqual(report["next_execution_runbook_guard_status"], "clock_guard_active")

    def test_attach_progress_record_summary_fields_copies_exact_replay_smoke_probe_plan(self):
        report: dict[str, object] = {}
        plan = {
            "status": "available_non_verifying_exact_replay_smoke_probe",
            "used_for_goal_verification": False,
            "counts_for_exact_replay_profitability_gate": False,
            "non_verification_policy": "smoke_probe_never_satisfies_exact_replay_profitability_gate",
            "command": (
                "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan "
                "--min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json"
            ),
            "blockers": [],
            "latest_observation": {
                "status": "zero_trades_insufficient_replay_calendar_runway",
                "replay_total_trades": 0,
                "replay_total_days": 0,
                "replay_candidate_trade_count": 0,
                "replay_profit_factor": 0.0,
                "zero_trade_primary_cause": "insufficient_selected_quote_dates_for_replay_start_index",
                "selected_dates_shortfall_to_first_entry": 56,
                "selected_dates_shortfall_to_diagnostic_replay": 86,
                "used_for_goal_verification": False,
            },
            "latest_observation_status": "zero_trades_insufficient_replay_calendar_runway",
            "latest_observation_generated_at": "2026-05-22T02:37:19Z",
            "latest_observation_observed_at_utc": "2026-05-22T02:40:00Z",
            "latest_observation_replay_total_trades": 0,
            "latest_observation_replay_total_days": 0,
            "latest_observation_replay_candidate_trade_count": 0,
            "latest_observation_replay_profit_factor": 0.0,
            "latest_observation_zero_trade_primary_cause": (
                "insufficient_selected_quote_dates_for_replay_start_index"
            ),
            "latest_observation_selected_dates_shortfall_to_first_entry": 56,
            "latest_observation_selected_dates_shortfall_to_diagnostic_replay": 86,
            "latest_observation_used_for_goal_verification": False,
        }
        summary = {
            "exact_replay_smoke_probe_plan": plan,
            "exact_replay_smoke_probe_status": plan["status"],
            "exact_replay_smoke_probe_command": plan["command"],
            "exact_replay_smoke_probe_used_for_goal_verification": plan["used_for_goal_verification"],
            "exact_replay_smoke_probe_counts_for_exact_profitability_gate": plan[
                "counts_for_exact_replay_profitability_gate"
            ],
            "exact_replay_smoke_probe_non_verification_policy": plan["non_verification_policy"],
            "exact_replay_smoke_probe_blockers": plan["blockers"],
            "exact_replay_smoke_probe_latest_observation": plan["latest_observation"],
            "exact_replay_smoke_probe_latest_observation_status": plan["latest_observation_status"],
            "exact_replay_smoke_probe_latest_observation_generated_at": plan[
                "latest_observation_generated_at"
            ],
            "exact_replay_smoke_probe_latest_observation_observed_at_utc": plan[
                "latest_observation_observed_at_utc"
            ],
            "exact_replay_smoke_probe_latest_observation_replay_total_trades": plan[
                "latest_observation_replay_total_trades"
            ],
            "exact_replay_smoke_probe_latest_observation_replay_total_days": plan[
                "latest_observation_replay_total_days"
            ],
            "exact_replay_smoke_probe_latest_observation_replay_candidate_trade_count": plan[
                "latest_observation_replay_candidate_trade_count"
            ],
            "exact_replay_smoke_probe_latest_observation_replay_profit_factor": plan[
                "latest_observation_replay_profit_factor"
            ],
            "exact_replay_smoke_probe_latest_observation_zero_trade_primary_cause": plan[
                "latest_observation_zero_trade_primary_cause"
            ],
            "exact_replay_smoke_probe_latest_observation_selected_dates_shortfall_to_first_entry": plan[
                "latest_observation_selected_dates_shortfall_to_first_entry"
            ],
            "exact_replay_smoke_probe_latest_observation_selected_dates_shortfall_to_diagnostic_replay": plan[
                "latest_observation_selected_dates_shortfall_to_diagnostic_replay"
            ],
            "exact_replay_smoke_probe_latest_observation_used_for_goal_verification": plan[
                "latest_observation_used_for_goal_verification"
            ],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["exact_replay_smoke_probe_plan"], plan)
        self.assertEqual(
            report["exact_replay_smoke_probe_status"],
            "available_non_verifying_exact_replay_smoke_probe",
        )
        self.assertEqual(report["exact_replay_smoke_probe_command"], plan["command"])
        self.assertFalse(report["exact_replay_smoke_probe_used_for_goal_verification"])
        self.assertFalse(report["exact_replay_smoke_probe_counts_for_exact_profitability_gate"])
        self.assertEqual(
            report["exact_replay_smoke_probe_non_verification_policy"],
            "smoke_probe_never_satisfies_exact_replay_profitability_gate",
        )
        self.assertEqual(
            report["exact_replay_smoke_probe_latest_observation_status"],
            "zero_trades_insufficient_replay_calendar_runway",
        )
        self.assertEqual(report["exact_replay_smoke_probe_latest_observation_replay_total_trades"], 0)
        self.assertEqual(report["exact_replay_smoke_probe_latest_observation_replay_total_days"], 0)
        self.assertEqual(
            report["exact_replay_smoke_probe_latest_observation_zero_trade_primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertFalse(report["exact_replay_smoke_probe_latest_observation_used_for_goal_verification"])

    def test_attach_progress_record_summary_fields_copies_exact_replay_runway_progress(self):
        report: dict[str, object] = {}
        runway = {
            "status": "waiting_for_first_replay_entry_runway",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "current_shared_quote_dates": 2,
            "minimum_selected_dates_for_first_entry": 58,
            "diagnostic_required_shared_quote_dates": 88,
            "full_required_shared_quote_dates": 100,
            "shortfall_to_first_entry": 56,
            "shortfall_to_diagnostic_replay": 86,
            "shortfall_to_full_exact_replay": 98,
            "expected_after_next_capture": {
                "shared_quote_dates": 3,
                "shortfall_to_first_entry": 55,
                "shortfall_to_diagnostic_replay": 85,
                "shortfall_to_full_exact_replay": 97,
            },
            "first_entry_unlocked_after_next_capture": False,
            "diagnostic_unlocked_after_next_capture": False,
            "full_unlocked_after_next_capture": False,
            "latest_smoke_zero_trade_primary_cause": (
                "insufficient_selected_quote_dates_for_replay_start_index"
            ),
            "next_capture_command": (
                "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
            ),
            "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
            "post_capture_readback_command": (
                "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
            ),
            "material_progress_if": ["proof_window.current_shared_quote_dates increases"],
            "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
            "blockers": ["first_replay_entry_shared_quote_dates:2/58"],
            "next_action": "continue_forward_capture_until_replay_calendar_can_simulate_entries",
        }
        summary = {
            "exact_replay_runway_progress": runway,
            "exact_replay_runway_status": runway["status"],
            "exact_replay_runway_provider": runway["provider"],
            "exact_replay_runway_proof_source_label": runway["proof_source_label"],
            "exact_replay_runway_current_shared_quote_dates": runway["current_shared_quote_dates"],
            "exact_replay_runway_minimum_selected_dates_for_first_entry": runway[
                "minimum_selected_dates_for_first_entry"
            ],
            "exact_replay_runway_diagnostic_required_shared_quote_dates": runway[
                "diagnostic_required_shared_quote_dates"
            ],
            "exact_replay_runway_full_required_shared_quote_dates": runway[
                "full_required_shared_quote_dates"
            ],
            "exact_replay_runway_shortfall_to_first_entry": runway["shortfall_to_first_entry"],
            "exact_replay_runway_shortfall_to_diagnostic_replay": runway[
                "shortfall_to_diagnostic_replay"
            ],
            "exact_replay_runway_shortfall_to_full_exact_replay": runway[
                "shortfall_to_full_exact_replay"
            ],
            "exact_replay_runway_expected_after_next_capture": runway["expected_after_next_capture"],
            "exact_replay_runway_first_entry_unlocked_after_next_capture": runway[
                "first_entry_unlocked_after_next_capture"
            ],
            "exact_replay_runway_diagnostic_unlocked_after_next_capture": runway[
                "diagnostic_unlocked_after_next_capture"
            ],
            "exact_replay_runway_full_unlocked_after_next_capture": runway[
                "full_unlocked_after_next_capture"
            ],
            "exact_replay_runway_latest_smoke_zero_trade_primary_cause": runway[
                "latest_smoke_zero_trade_primary_cause"
            ],
            "exact_replay_runway_next_capture_command": runway["next_capture_command"],
            "exact_replay_runway_next_capture_not_before_user_local": runway[
                "next_capture_not_before_user_local"
            ],
            "exact_replay_runway_post_capture_readback_command": runway["post_capture_readback_command"],
            "exact_replay_runway_material_progress_if": runway["material_progress_if"],
            "exact_replay_runway_no_mutation_guard": runway["no_mutation_guard"],
            "exact_replay_runway_blockers": runway["blockers"],
            "exact_replay_runway_next_action": runway["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["exact_replay_runway_progress"], runway)
        self.assertEqual(report["exact_replay_runway_status"], "waiting_for_first_replay_entry_runway")
        self.assertEqual(report["exact_replay_runway_current_shared_quote_dates"], 2)
        self.assertEqual(report["exact_replay_runway_shortfall_to_first_entry"], 56)
        self.assertEqual(
            report["exact_replay_runway_expected_after_next_capture"]["shared_quote_dates"],
            3,
        )
        self.assertFalse(report["exact_replay_runway_first_entry_unlocked_after_next_capture"])
        self.assertEqual(
            report["exact_replay_runway_latest_smoke_zero_trade_primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertEqual(
            report["exact_replay_runway_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )

    def test_attach_progress_record_summary_fields_copies_next_profitability_evidence_sequence(self):
        report: dict[str, object] = {}
        sequence = {
            "status": "waiting_for_next_profitability_evidence_event",
            "event_count": 3,
            "events": [{"event_kind": "fresh_scan_raw_drop_reason_audit"}],
            "next_event": {
                "event_kind": "fresh_scan_raw_drop_reason_audit",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            },
            "next_event_kind": "fresh_scan_raw_drop_reason_audit",
            "next_event_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "next_event_not_before_user_local": "2026-05-22T08:10:00-06:00",
            "next_event_no_mutation_guard": (
                "production_filters_preserved_until_exact_alpaca_opra_replay_unlock"
            ),
            "current_replay_runway_status": "waiting_for_first_replay_entry_runway",
            "current_replay_runway_shortfalls": {
                "first_entry": 56,
                "diagnostic_replay": 86,
                "full_exact_replay": 98,
            },
            "post_event_readback_command": (
                "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
            ),
            "blockers": ["first_replay_entry_shared_quote_dates:2/58"],
            "next_action": "wait_until_next_event_not_before_then_run_guarded_command",
        }
        summary = {
            "next_profitability_evidence_sequence": sequence,
            "next_profitability_evidence_sequence_status": sequence["status"],
            "next_profitability_evidence_sequence_event_count": sequence["event_count"],
            "next_profitability_evidence_sequence_events": sequence["events"],
            "next_profitability_evidence_next_event": sequence["next_event"],
            "next_profitability_evidence_next_event_kind": sequence["next_event_kind"],
            "next_profitability_evidence_next_event_command": sequence["next_event_command"],
            "next_profitability_evidence_next_event_not_before_user_local": sequence[
                "next_event_not_before_user_local"
            ],
            "next_profitability_evidence_next_event_no_mutation_guard": sequence[
                "next_event_no_mutation_guard"
            ],
            "next_profitability_evidence_current_replay_runway_status": sequence[
                "current_replay_runway_status"
            ],
            "next_profitability_evidence_current_replay_runway_shortfalls": sequence[
                "current_replay_runway_shortfalls"
            ],
            "next_profitability_evidence_post_event_readback_command": sequence[
                "post_event_readback_command"
            ],
            "next_profitability_evidence_blockers": sequence["blockers"],
            "next_profitability_evidence_next_action": sequence["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["next_profitability_evidence_sequence"], sequence)
        self.assertEqual(
            report["next_profitability_evidence_next_event_kind"],
            "fresh_scan_raw_drop_reason_audit",
        )
        self.assertEqual(
            report["next_profitability_evidence_next_event_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            report["next_profitability_evidence_current_replay_runway_shortfalls"]["full_exact_replay"],
            98,
        )

    def test_attach_progress_record_summary_fields_copies_profitability_evidence_scorecard(self):
        report: dict[str, object] = {}
        scorecard = {
            "status": "recording_progress_waiting_for_exact_history_depth",
            "passed_requirement_count": 2,
            "total_requirement_count": 8,
            "rows": [{"requirement": "required_exact_history_depth", "passed": False}],
            "blockers": ["alpaca_opra_daily_snapshot_shared_quote_dates:2/100"],
            "current_shared_quote_dates": 2,
            "required_shared_quote_dates": 100,
            "replay_runway_status": "waiting_for_first_replay_entry_runway",
            "next_evidence_event_kind": "fresh_scan_raw_drop_reason_audit",
            "next_evidence_event_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "next_evidence_event_not_before_user_local": "2026-05-22T08:10:00-06:00",
            "next_evidence_event_readiness": {
                "status": "waiting_until_not_before",
                "command_matches_guarded_command": True,
                "safe_to_execute_now": False,
                "guarded_command_decision_action": "wait_until_not_before",
                "guarded_command_decision_reason": (
                    "waiting_until_not_before:2026-05-22T08:10:00-06:00"
                ),
            },
            "post_event_scoring_rules": {
                "exact_opra_forward_capture": {
                    "fields_to_compare": ["alpaca_opra_data_usage_proof_window_shared_quote_dates"]
                }
            },
            "post_event_readback_packet": {
                "status": "waiting_until_not_before",
                "readback_command": (
                    "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
                ),
                "readback_projection_shell": "powershell",
                "readback_projection_command": (
                    "$r = python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest | "
                    "ConvertFrom-Json; [pscustomobject]@{ provider = $r.provider; "
                    "profitability_evidence_scorecard_delta_status = "
                    "$r.profitability_evidence_scorecard_delta_status } | ConvertTo-Json -Depth 6"
                ),
                "readback_projection_success_criteria": [
                    "projection exits with code 0",
                    "profitability_evidence_scorecard_delta_status is not null",
                ],
                "baseline_snapshot": {
                    "provider": "alpaca:sip:opra",
                    "profitability_evidence_scorecard_status": (
                        "recording_progress_waiting_for_exact_history_depth"
                    ),
                    "alpaca_opra_data_usage_proof_window_shared_quote_dates": 2,
                },
                "baseline_snapshot_fields": [
                    "provider",
                    "profitability_evidence_scorecard_status",
                    "alpaca_opra_data_usage_proof_window_shared_quote_dates",
                ],
                "baseline_compare_policy": (
                    "compare_projection_after_guarded_event_against_baseline_snapshot"
                ),
                "baseline_comparison_assertions": [
                    {
                        "field": "scan_candidate_count",
                        "baseline": 0,
                        "material_progress_if": "after > baseline",
                    }
                ],
                "baseline_no_progress_conditions": ["scan_candidate_count <= baseline"],
                "readback_fields": [
                    "provider",
                    "alpaca_opra_data_usage_proof_window_shared_quote_dates",
                    "profitability_evidence_scorecard_delta_status",
                ],
                "readback_field_groups": {
                    "history_depth": ["alpaca_opra_data_usage_proof_window_shared_quote_dates"]
                },
                "progress_success_rules": {
                    "exact_opra_forward_capture": {
                        "fields_to_compare": [
                            "alpaca_opra_data_usage_proof_window_shared_quote_dates"
                        ]
                    }
                },
                "no_mutation_guard": (
                    "production_filters_preserved_until_exact_alpaca_opra_replay_unlock"
                ),
            },
            "non_verifying_replay_wiring_probe": {
                "status": "zero_trades_insufficient_replay_calendar_runway",
                "counts_for_exact_replay_profitability_gate": False,
            },
            "post_event_readback_command": (
                "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
            ),
            "next_action": "run_next_guarded_evidence_event_and_compare_scorecard",
        }
        summary = {
            "profitability_evidence_scorecard": scorecard,
            "profitability_evidence_scorecard_status": scorecard["status"],
            "profitability_evidence_scorecard_passed_requirement_count": scorecard[
                "passed_requirement_count"
            ],
            "profitability_evidence_scorecard_total_requirement_count": scorecard[
                "total_requirement_count"
            ],
            "profitability_evidence_scorecard_rows": scorecard["rows"],
            "profitability_evidence_scorecard_blockers": scorecard["blockers"],
            "profitability_evidence_scorecard_current_shared_quote_dates": scorecard[
                "current_shared_quote_dates"
            ],
            "profitability_evidence_scorecard_required_shared_quote_dates": scorecard[
                "required_shared_quote_dates"
            ],
            "profitability_evidence_scorecard_replay_runway_status": scorecard["replay_runway_status"],
            "profitability_evidence_scorecard_next_evidence_event_kind": scorecard[
                "next_evidence_event_kind"
            ],
            "profitability_evidence_scorecard_next_evidence_event_command": scorecard[
                "next_evidence_event_command"
            ],
            "profitability_evidence_scorecard_next_evidence_event_not_before_user_local": scorecard[
                "next_evidence_event_not_before_user_local"
            ],
            "profitability_evidence_scorecard_next_evidence_event_readiness": scorecard[
                "next_evidence_event_readiness"
            ],
            "profitability_evidence_scorecard_next_evidence_event_readiness_status": scorecard[
                "next_evidence_event_readiness"
            ]["status"],
            "profitability_evidence_scorecard_next_evidence_event_command_matches_guard": scorecard[
                "next_evidence_event_readiness"
            ]["command_matches_guarded_command"],
            "profitability_evidence_scorecard_next_evidence_event_safe_to_execute_now": scorecard[
                "next_evidence_event_readiness"
            ]["safe_to_execute_now"],
            "profitability_evidence_scorecard_next_evidence_event_guarded_action": scorecard[
                "next_evidence_event_readiness"
            ]["guarded_command_decision_action"],
            "profitability_evidence_scorecard_next_evidence_event_guarded_reason": scorecard[
                "next_evidence_event_readiness"
            ]["guarded_command_decision_reason"],
            "profitability_evidence_scorecard_post_event_scoring_rules": scorecard[
                "post_event_scoring_rules"
            ],
            "profitability_evidence_scorecard_post_event_readback_packet": scorecard[
                "post_event_readback_packet"
            ],
            "profitability_evidence_scorecard_readback_fields": scorecard[
                "post_event_readback_packet"
            ]["readback_fields"],
            "profitability_evidence_scorecard_readback_projection_shell": scorecard[
                "post_event_readback_packet"
            ]["readback_projection_shell"],
            "profitability_evidence_scorecard_readback_projection_command": scorecard[
                "post_event_readback_packet"
            ]["readback_projection_command"],
            "profitability_evidence_scorecard_readback_projection_success_criteria": scorecard[
                "post_event_readback_packet"
            ]["readback_projection_success_criteria"],
            "profitability_evidence_scorecard_readback_baseline_snapshot": scorecard[
                "post_event_readback_packet"
            ]["baseline_snapshot"],
            "profitability_evidence_scorecard_readback_baseline_snapshot_fields": scorecard[
                "post_event_readback_packet"
            ]["baseline_snapshot_fields"],
            "profitability_evidence_scorecard_readback_baseline_compare_policy": scorecard[
                "post_event_readback_packet"
            ]["baseline_compare_policy"],
            "profitability_evidence_scorecard_readback_baseline_comparison_assertions": scorecard[
                "post_event_readback_packet"
            ]["baseline_comparison_assertions"],
            "profitability_evidence_scorecard_readback_baseline_no_progress_conditions": scorecard[
                "post_event_readback_packet"
            ]["baseline_no_progress_conditions"],
            "profitability_evidence_scorecard_readback_field_groups": scorecard[
                "post_event_readback_packet"
            ]["readback_field_groups"],
            "profitability_evidence_scorecard_readback_success_rules": scorecard[
                "post_event_readback_packet"
            ]["progress_success_rules"],
            "profitability_evidence_scorecard_readback_no_mutation_guard": scorecard[
                "post_event_readback_packet"
            ]["no_mutation_guard"],
            "profitability_evidence_scorecard_non_verifying_replay_wiring_probe": scorecard[
                "non_verifying_replay_wiring_probe"
            ],
            "profitability_evidence_scorecard_post_event_readback_command": scorecard[
                "post_event_readback_command"
            ],
            "profitability_evidence_scorecard_next_action": scorecard["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["profitability_evidence_scorecard"], scorecard)
        self.assertEqual(
            report["profitability_evidence_scorecard_status"],
            "recording_progress_waiting_for_exact_history_depth",
        )
        self.assertEqual(report["profitability_evidence_scorecard_passed_requirement_count"], 2)
        self.assertEqual(
            report["profitability_evidence_scorecard_next_evidence_event_kind"],
            "fresh_scan_raw_drop_reason_audit",
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_post_event_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_post_event_readback_packet"]["status"],
            "waiting_until_not_before",
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status",
            report["profitability_evidence_scorecard_readback_fields"],
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_readback_projection_shell"],
            "powershell",
        )
        self.assertIn(
            "ConvertFrom-Json",
            report["profitability_evidence_scorecard_readback_projection_command"],
        )
        self.assertIn(
            "projection exits with code 0",
            report["profitability_evidence_scorecard_readback_projection_success_criteria"],
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_readback_baseline_snapshot"]["provider"],
            "alpaca:sip:opra",
        )
        self.assertIn(
            "profitability_evidence_scorecard_status",
            report["profitability_evidence_scorecard_readback_baseline_snapshot_fields"],
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_readback_baseline_compare_policy"],
            "compare_projection_after_guarded_event_against_baseline_snapshot",
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_readback_baseline_comparison_assertions"][0][
                "field"
            ],
            "scan_candidate_count",
        )
        self.assertIn(
            "scan_candidate_count <= baseline",
            report["profitability_evidence_scorecard_readback_baseline_no_progress_conditions"],
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_readback_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_next_evidence_event_readiness"]["status"],
            "waiting_until_not_before",
        )
        self.assertTrue(report["profitability_evidence_scorecard_next_evidence_event_command_matches_guard"])
        self.assertFalse(report["profitability_evidence_scorecard_next_evidence_event_safe_to_execute_now"])
        self.assertEqual(
            report["profitability_evidence_scorecard_next_evidence_event_guarded_action"],
            "wait_until_not_before",
        )
        self.assertFalse(
            report["profitability_evidence_scorecard_non_verifying_replay_wiring_probe"][
                "counts_for_exact_replay_profitability_gate"
            ]
        )

    def test_attach_progress_record_summary_fields_copies_profitability_evidence_scorecard_delta(self):
        report: dict[str, object] = {}
        delta = {
            "status": "improved",
            "material_progress": True,
            "evidence_progress": True,
            "material_evidence_progress": True,
            "evidence_progress_reasons": ["alpaca_opra_shared_quote_dates_increased"],
            "profit_improved": False,
            "profit_improvement_reason": None,
            "profitability_metrics_before": {
                "profit_factor": None,
                "total_return_pct": None,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
            },
            "profitability_metrics_after": {
                "profit_factor": None,
                "total_return_pct": None,
                "current_shared_quote_dates": 3,
                "required_shared_quote_dates": 100,
            },
            "profitability_metrics_same_window": False,
            "profitability_metric_improvements": [],
            "profitability_metric_regressions": [],
            "passed_requirement_count_before": 2,
            "passed_requirement_count_after": 3,
            "passed_requirement_count_delta": 1,
            "current_shared_quote_dates_before": 2,
            "current_shared_quote_dates_after": 3,
            "current_shared_quote_dates_delta": 1,
            "blockers_removed": ["live_scan_zero_candidates_without_raw_drop_reasons"],
            "blockers_added": ["alpaca_opra_daily_snapshot_shared_quote_dates:3/100"],
            "blockers_persisting": ["first_replay_entry_runway_not_ready"],
            "requirement_row_changes": [
                {"requirement": "live_scan_candidate_or_raw_drop_reasons", "passed_after": True}
            ],
            "regressions": [],
            "auxiliary_progress": True,
            "auxiliary_progress_reasons": ["non_verifying_replay_wiring_probe_refreshed"],
            "baseline_comparison_evaluation": {
                "status": "material_progress",
                "material_progress": True,
            },
            "baseline_comparison_status": "material_progress",
            "baseline_comparison_material_progress": True,
            "baseline_comparison_assertion_results": [
                {"field": "scan_drop_reason_count", "after": 3, "passed": True}
            ],
            "baseline_comparison_no_progress_conditions": [
                "scan_drop_reason_count is null_or_zero"
            ],
            "baseline_comparison_no_progress_condition_results": [
                {
                    "condition": "scan_drop_reason_count is null_or_zero",
                    "status": "unsupported_condition",
                    "matched": None,
                }
            ],
            "baseline_comparison_no_progress_detected": False,
            "non_verifying_replay_wiring_probe_before": {
                "observed_at_utc": "2026-05-22T02:40:00Z"
            },
            "non_verifying_replay_wiring_probe_after": {
                "observed_at_utc": "2026-05-22T03:54:11Z"
            },
            "post_event_readback_command": (
                "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
            ),
            "next_action": "continue_guarded_profitability_evidence_sequence",
        }
        summary = {
            "profitability_evidence_scorecard_delta": delta,
            "profitability_evidence_scorecard_delta_status": delta["status"],
            "profitability_evidence_scorecard_delta_material_progress": delta["material_progress"],
            "profitability_evidence_scorecard_delta_evidence_progress": delta["evidence_progress"],
            "profitability_evidence_scorecard_delta_material_evidence_progress": delta[
                "material_evidence_progress"
            ],
            "profitability_evidence_scorecard_delta_evidence_progress_reasons": delta[
                "evidence_progress_reasons"
            ],
            "profitability_evidence_scorecard_delta_profit_improved": delta["profit_improved"],
            "profitability_evidence_scorecard_delta_profit_improvement_reason": delta[
                "profit_improvement_reason"
            ],
            "profitability_evidence_scorecard_delta_profitability_metrics_before": delta[
                "profitability_metrics_before"
            ],
            "profitability_evidence_scorecard_delta_profitability_metrics_after": delta[
                "profitability_metrics_after"
            ],
            "profitability_evidence_scorecard_delta_profitability_metrics_same_window": delta[
                "profitability_metrics_same_window"
            ],
            "profitability_evidence_scorecard_delta_profitability_metric_improvements": delta[
                "profitability_metric_improvements"
            ],
            "profitability_evidence_scorecard_delta_profitability_metric_regressions": delta[
                "profitability_metric_regressions"
            ],
            "profitability_evidence_scorecard_delta_passed_requirement_count_before": delta[
                "passed_requirement_count_before"
            ],
            "profitability_evidence_scorecard_delta_passed_requirement_count_after": delta[
                "passed_requirement_count_after"
            ],
            "profitability_evidence_scorecard_delta_passed_requirement_count_delta": delta[
                "passed_requirement_count_delta"
            ],
            "profitability_evidence_scorecard_delta_current_shared_quote_dates_before": delta[
                "current_shared_quote_dates_before"
            ],
            "profitability_evidence_scorecard_delta_current_shared_quote_dates_after": delta[
                "current_shared_quote_dates_after"
            ],
            "profitability_evidence_scorecard_delta_current_shared_quote_dates_delta": delta[
                "current_shared_quote_dates_delta"
            ],
            "profitability_evidence_scorecard_delta_blockers_removed": delta["blockers_removed"],
            "profitability_evidence_scorecard_delta_blockers_added": delta["blockers_added"],
            "profitability_evidence_scorecard_delta_blockers_persisting": delta["blockers_persisting"],
            "profitability_evidence_scorecard_delta_requirement_row_changes": delta[
                "requirement_row_changes"
            ],
            "profitability_evidence_scorecard_delta_regressions": delta["regressions"],
            "profitability_evidence_scorecard_delta_auxiliary_progress": delta["auxiliary_progress"],
            "profitability_evidence_scorecard_delta_auxiliary_progress_reasons": delta[
                "auxiliary_progress_reasons"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_evaluation": delta[
                "baseline_comparison_evaluation"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_status": delta[
                "baseline_comparison_status"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_material_progress": delta[
                "baseline_comparison_material_progress"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_assertion_results": delta[
                "baseline_comparison_assertion_results"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_conditions": delta[
                "baseline_comparison_no_progress_conditions"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_condition_results": delta[
                "baseline_comparison_no_progress_condition_results"
            ],
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_detected": delta[
                "baseline_comparison_no_progress_detected"
            ],
            "profitability_evidence_scorecard_delta_non_verifying_replay_wiring_probe_before": delta[
                "non_verifying_replay_wiring_probe_before"
            ],
            "profitability_evidence_scorecard_delta_non_verifying_replay_wiring_probe_after": delta[
                "non_verifying_replay_wiring_probe_after"
            ],
            "profitability_evidence_scorecard_delta_post_event_readback_command": delta[
                "post_event_readback_command"
            ],
            "profitability_evidence_scorecard_delta_next_action": delta["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["profitability_evidence_scorecard_delta"], delta)
        self.assertEqual(report["profitability_evidence_scorecard_delta_status"], "improved")
        self.assertTrue(report["profitability_evidence_scorecard_delta_material_progress"])
        self.assertTrue(report["profitability_evidence_scorecard_delta_evidence_progress"])
        self.assertTrue(report["profitability_evidence_scorecard_delta_material_evidence_progress"])
        self.assertFalse(report["profitability_evidence_scorecard_delta_profit_improved"])
        self.assertEqual(
            report["profitability_evidence_scorecard_delta_evidence_progress_reasons"],
            ["alpaca_opra_shared_quote_dates_increased"],
        )
        self.assertEqual(report["profitability_evidence_scorecard_delta_passed_requirement_count_delta"], 1)
        self.assertEqual(report["profitability_evidence_scorecard_delta_current_shared_quote_dates_delta"], 1)
        self.assertTrue(report["profitability_evidence_scorecard_delta_auxiliary_progress"])
        self.assertIn(
            "non_verifying_replay_wiring_probe_refreshed",
            report["profitability_evidence_scorecard_delta_auxiliary_progress_reasons"],
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_delta_baseline_comparison_status"],
            "material_progress",
        )
        self.assertTrue(
            report[
                "profitability_evidence_scorecard_delta_baseline_comparison_material_progress"
            ]
        )
        self.assertEqual(
            report[
                "profitability_evidence_scorecard_delta_baseline_comparison_assertion_results"
            ][0]["field"],
            "scan_drop_reason_count",
        )
        self.assertFalse(
            report[
                "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_detected"
            ]
        )
        self.assertEqual(
            report["profitability_evidence_scorecard_delta_post_event_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )

    def test_attach_progress_record_summary_fields_copies_exact_history_backfill_fields(self):
        report: dict[str, object] = {}
        audit = {
            "status": "forward_capture_required_for_exact_bid_ask_history",
            "missing_capability": "historical_option_quote_bbo_method_for_contracts",
            "can_accelerate_exact_history": False,
            "next_action": "continue_forward_daily_alpaca_opra_snapshot_capture",
        }
        summary = {
            "exact_history_acquisition_plan": {
                "status": "forward_capture_required",
                "next_capture_trade_date": "2026-05-22",
            },
            "exact_history_acquisition_status": "forward_capture_required",
            "exact_history_backfill_status": "forward_daily_snapshot_capture_required",
            "exact_history_next_capture_trade_date": "2026-05-22",
            "exact_history_next_capture_command": (
                "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
            ),
            "exact_history_next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
            "exact_history_forward_capture_queue": [{"trade_date": "2026-05-22"}],
            "exact_history_forward_capture_queue_summary": [{"rank": 1, "trade_date": "2026-05-22"}],
            "exact_history_unlock_milestones": {
                "full_exact_replay": {"unlock_trade_date": "2026-10-12"}
            },
            "exact_history_capture_continuity_contract": {
                "status": "on_track_no_missed_capture_dates"
            },
            "exact_history_capture_continuity_status": "on_track_no_missed_capture_dates",
            "exact_history_missed_capture_trade_dates": [],
            "exact_history_missed_capture_policy": (
                "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
            ),
            "exact_history_can_accelerate_with_existing_sources": False,
            "exact_history_backfill_capability_audit": audit,
            "exact_history_backfill_capability_status": audit["status"],
            "exact_history_backfill_missing_capability": audit["missing_capability"],
            "exact_history_backfill_can_accelerate": audit["can_accelerate_exact_history"],
            "exact_history_backfill_acceleration_decision": {
                "decision": "do_not_accelerate_exact_history_from_alpaca_historical_bars_or_trades"
            },
            "exact_history_backfill_review_checked_at": "2026-05-22",
            "exact_history_backfill_next_action": audit["next_action"],
            "lane_next_step_plan_success_branch": (
                "if_shared_dates_increment_then_continue_daily_capture_runway"
            ),
            "lane_next_step_plan_history_acceleration_status": (
                "forward_daily_snapshot_capture_required"
            ),
            "lane_next_step_plan_history_backfill_blockers": [
                "no_historical_option_quote_bbo_endpoint"
            ],
            "lane_next_step_plan_snapshot_updated_since_is_backfill_capability": False,
            "lane_next_step_plan_filter_policy": (
                "locked_until_exact_alpaca_opra_replay_profitability_gate_can_measure_changes"
            ),
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(
            report["exact_history_backfill_capability_status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        self.assertFalse(report["exact_history_backfill_can_accelerate"])
        self.assertEqual(report["exact_history_backfill_capability_audit"], audit)
        self.assertEqual(report["exact_history_next_capture_trade_date"], "2026-05-22")
        self.assertIn(
            "no_historical_option_quote_bbo_endpoint",
            report["lane_next_step_plan_history_backfill_blockers"],
        )
        self.assertFalse(report["lane_next_step_plan_snapshot_updated_since_is_backfill_capability"])

    def test_attach_progress_record_summary_fields_copies_exact_replay_unlock_fields(self):
        report: dict[str, object] = {}
        contract = {
            "status": "waiting_for_diagnostic_replay_history",
            "diagnostic_remaining_shared_quote_dates": 86,
            "full_remaining_shared_quote_dates": 98,
            "ready_to_run_full_exact_replay": False,
            "blockers": [
                "diagnostic_replay_waiting_for_exact_opra_history_depth",
                "full_exact_replay_waiting_for_exact_opra_history_depth",
            ],
            "next_action": "continue_forward_daily_alpaca_opra_capture",
        }
        summary = {
            "exact_replay_unlock_contract": contract,
            "exact_replay_unlock_status": contract["status"],
            "exact_replay_unlock_diagnostic_remaining_shared_quote_dates": contract[
                "diagnostic_remaining_shared_quote_dates"
            ],
            "exact_replay_unlock_full_remaining_shared_quote_dates": contract[
                "full_remaining_shared_quote_dates"
            ],
            "exact_replay_unlock_diagnostic_trade_date": "2026-09-24",
            "exact_replay_unlock_full_trade_date": "2026-10-12",
            "exact_replay_unlock_immediate_next_capture_command": (
                "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
            ),
            "exact_replay_unlock_replay_command_when_unlocked": (
                "python scripts/run_ai_commodity_opra_progress.py"
            ),
            "exact_replay_readiness_checklist": {
                "status": "waiting_for_exact_opra_history_depth",
            },
            "exact_replay_readiness_checklist_status": "waiting_for_exact_opra_history_depth",
            "exact_replay_ready_to_run_full_exact_replay": False,
            "exact_replay_readiness_checklist_blockers": [
                "full_exact_replay_history_depth_available"
            ],
            "exact_replay_readiness_checklist_next_action": "continue_forward_daily_alpaca_opra_capture",
            "exact_replay_readiness_checklist_next_command": (
                "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
            ),
            "exact_replay_unlock_blockers": contract["blockers"],
            "exact_replay_unlock_next_action": contract["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["exact_replay_unlock_contract"], contract)
        self.assertEqual(report["exact_replay_unlock_status"], "waiting_for_diagnostic_replay_history")
        self.assertEqual(report["exact_replay_unlock_diagnostic_remaining_shared_quote_dates"], 86)
        self.assertEqual(report["exact_replay_unlock_full_remaining_shared_quote_dates"], 98)
        self.assertEqual(report["exact_replay_unlock_full_trade_date"], "2026-10-12")
        self.assertFalse(report["exact_replay_ready_to_run_full_exact_replay"])
        self.assertEqual(
            report["exact_replay_unlock_next_action"],
            "continue_forward_daily_alpaca_opra_capture",
        )

    def test_attach_progress_record_summary_fields_copies_fresh_scan_drop_reason_fields(self):
        report: dict[str, object] = {}
        summary = {
            "fresh_scan_decision_status": "fresh_scan_zero_candidates_structural_review",
            "fresh_scan_decision_branch": "structural_blocker_branch",
            "fresh_scan_decision_next_action": "rank_remaining_drop_counts_without_relaxing_production_filters",
            "fresh_scan_decision_safe_to_tune_filters": False,
            "fresh_scan_decision_top_drop_counts": [
                {"drop_key": "momentum", "count": 12},
                {"drop_key": "option_liquidity", "count": 7},
            ],
            "fresh_scan_decision_selected_outcome_effect": "remains_blocked_records_raw_scan_drop_reasons",
            "fresh_scan_decision_selected_outcome_next_command": (
                "python scripts/run_ai_commodity_opra_progress.py --skip-capture"
            ),
            "fresh_scan_post_run_status": "fresh_scan_zero_candidates_after_fresh_quotes",
            "fresh_scan_post_run_next_action": "review_zero_candidate_structural_blockers",
            "fresh_scan_post_run_blockers": ["live_scan_has_candidate"],
            "scan_candidate_count": 0,
            "scan_quote_freshness_status": "fresh_or_not_age_limited",
            "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
            "scan_drop_reason_count": 4,
            "scan_drop_reason_symbols_by_drop": {"momentum": ["CCJ"]},
            "scan_drop_reason_detail_fields_by_drop": {"momentum": ["price", "sma20"]},
            "scan_drop_reason_derived_fields_by_drop": {"momentum": ["momentum_signal_distance_pct"]},
            "fresh_scan_zero_candidate_structural_review_status": "ready_after_fresh_quotes_zero_candidates",
            "fresh_scan_zero_candidate_read_only_review_allowed_now": True,
            "fresh_scan_zero_candidate_dominant_drop_key": "momentum",
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(
            report["fresh_scan_decision_status"],
            "fresh_scan_zero_candidates_structural_review",
        )
        self.assertFalse(report["fresh_scan_decision_safe_to_tune_filters"])
        self.assertEqual(report["fresh_scan_decision_top_drop_counts"][0]["drop_key"], "momentum")
        self.assertEqual(report["fresh_scan_post_run_status"], "fresh_scan_zero_candidates_after_fresh_quotes")
        self.assertEqual(report["scan_candidate_count"], 0)
        self.assertEqual(report["scan_quote_freshness_status"], "fresh_or_not_age_limited")
        self.assertEqual(report["scan_drop_reason_audit_status"], "raw_drop_reasons_recorded")
        self.assertEqual(report["scan_drop_reason_count"], 4)
        self.assertEqual(report["scan_drop_reason_symbols_by_drop"]["momentum"], ["CCJ"])
        self.assertTrue(report["fresh_scan_zero_candidate_read_only_review_allowed_now"])
        self.assertEqual(report["fresh_scan_zero_candidate_dominant_drop_key"], "momentum")

    def test_attach_progress_record_summary_fields_copies_raw_drop_reason_contract(self):
        report: dict[str, object] = {}
        contract = {
            "status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
            "requirement_satisfied_by": None,
            "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
            "not_before_user_local": "2026-05-22T08:10:00-06:00",
            "window_end_user_local": "2026-05-22T14:00:00-06:00",
            "safe_to_tune_filters": False,
            "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
            "required_evidence_fields": ["scan.scan_drop_reason_audit_status"],
            "material_progress_if": ["scan.scan_drop_reason_count > 0"],
            "no_progress_blockers_to_record": ["scan_drop_reason_count_zero_or_missing"],
            "blockers": ["scan_drop_reason_count_zero_or_missing"],
            "post_run_audit_card": {
                "status": "pending_guarded_fresh_scan_readback",
                "readback_command": "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
            },
            "post_run_readback_command": (
                "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
            ),
            "post_run_fields_to_compare": [
                "raw_drop_reason_evidence_status",
                "scan_drop_reason_count",
            ],
            "post_run_success_statuses": ["raw_drop_reasons_recorded_zero_candidate_reviewable"],
            "post_run_still_blocked_if": ["scan_drop_reason_count is null or <= 0"],
            "next_action": "wait_until_auxiliary_fresh_scan_not_before",
        }
        summary = {
            "raw_drop_reason_evidence_contract": contract,
            "raw_drop_reason_evidence_status": contract["status"],
            "raw_drop_reason_evidence_requirement_satisfied_by": contract[
                "requirement_satisfied_by"
            ],
            "raw_drop_reason_evidence_command": contract["command"],
            "raw_drop_reason_evidence_not_before_user_local": contract["not_before_user_local"],
            "raw_drop_reason_evidence_window_end_user_local": contract["window_end_user_local"],
            "raw_drop_reason_evidence_safe_to_tune_filters": contract["safe_to_tune_filters"],
            "raw_drop_reason_evidence_no_mutation_guard": contract["no_mutation_guard"],
            "raw_drop_reason_evidence_required_fields": contract["required_evidence_fields"],
            "raw_drop_reason_evidence_material_progress_if": contract["material_progress_if"],
            "raw_drop_reason_evidence_no_progress_blockers_to_record": contract[
                "no_progress_blockers_to_record"
            ],
            "raw_drop_reason_evidence_blockers": contract["blockers"],
            "raw_drop_reason_evidence_post_run_audit_card": contract["post_run_audit_card"],
            "raw_drop_reason_evidence_post_run_readback_command": contract[
                "post_run_readback_command"
            ],
            "raw_drop_reason_evidence_post_run_fields_to_compare": contract[
                "post_run_fields_to_compare"
            ],
            "raw_drop_reason_evidence_post_run_success_statuses": contract[
                "post_run_success_statuses"
            ],
            "raw_drop_reason_evidence_post_run_still_blocked_if": contract[
                "post_run_still_blocked_if"
            ],
            "raw_drop_reason_evidence_next_action": contract["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(report["raw_drop_reason_evidence_contract"], contract)
        self.assertEqual(
            report["raw_drop_reason_evidence_status"],
            "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
        )
        self.assertIsNone(report["raw_drop_reason_evidence_requirement_satisfied_by"])
        self.assertEqual(
            report["raw_drop_reason_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertFalse(report["raw_drop_reason_evidence_safe_to_tune_filters"])
        self.assertIn(
            "scan.scan_drop_reason_audit_status",
            report["raw_drop_reason_evidence_required_fields"],
        )
        self.assertEqual(
            report["raw_drop_reason_evidence_post_run_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertIn(
            "raw_drop_reason_evidence_status",
            report["raw_drop_reason_evidence_post_run_fields_to_compare"],
        )

    def test_build_alpaca_opra_data_usage_audit_marks_current_proof_source_in_use(self):
        audit = build_alpaca_opra_data_usage_audit(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
                "proof_source_audit": {
                    "snapshot_kind": "daily_eod",
                    "trusted_only": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_shared_quote_dates": {
                        "count": 2,
                        "first": "2026-05-20",
                        "last": "2026-05-21",
                    },
                    "all_required_symbols_have_proof_source_data": True,
                    "proof_source_required_symbol_coverage": {
                        "required_symbol_count": 24,
                        "available_required_symbol_count": 24,
                        "min_symbol_quote_date_count": 2,
                        "max_symbol_quote_date_count": 2,
                    },
                    "proof_source_store_inventory": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "quote_rows_in_scope": 24490,
                        "quote_dates": {
                            "count": 2,
                            "first": "2026-05-20",
                            "last": "2026-05-21",
                        },
                    },
                    "store_inventory": {
                        "source_labels_with_quotes_in_scope": [
                            "alpaca_opra_daily_snapshot",
                            "thetadata_free_eod",
                        ],
                    },
                    "non_proof_alpaca_like_source_labels": [],
                    "excluded_trusted_shared_quote_dates": {"count": 0},
                    "excluded_trusted_source_labels": [],
                },
            }
        )

        self.assertEqual(
            audit["status"],
            "using_alpaca_opra_daily_snapshot_waiting_for_history_depth",
        )
        self.assertEqual(audit["proof_window_shared_quote_dates"], 2)
        self.assertEqual(audit["remaining_shared_quote_dates"], 98)
        self.assertTrue(audit["proof_window_matches_proof_source_inventory"])
        self.assertTrue(audit["all_required_symbols_have_alpaca_opra_data"])
        self.assertEqual(audit["non_proof_sources_with_quotes_in_scope"], ["thetadata_free_eod"])
        self.assertEqual(audit["blockers"], [])

    def test_attach_progress_record_summary_fields_copies_alpaca_data_usage_audit(self):
        report: dict[str, object] = {}
        usage = {
            "status": "using_alpaca_opra_daily_snapshot_waiting_for_history_depth",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window_shared_quote_dates": 2,
            "required_shared_quote_dates": 100,
            "remaining_shared_quote_dates": 98,
            "all_required_symbols_have_alpaca_opra_data": True,
            "source_inventory": {"quote_rows_in_scope": 24490},
            "non_proof_sources_with_quotes_in_scope": ["thetadata_free_eod"],
            "blockers": [],
            "next_action": "continue_forward_alpaca_opra_capture_until_required_shared_dates",
        }
        summary = {
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_shared_quote_dates": {"count": 2, "first": "2026-05-20", "last": "2026-05-21"},
            "proof_source_store_inventory": {"quote_rows_in_scope": 24490},
            "proof_source_all_required_symbols_available": True,
            "alpaca_opra_data_usage_audit": usage,
            "alpaca_opra_data_usage_status": usage["status"],
            "alpaca_opra_data_usage_proof_source_label": usage["proof_source_label"],
            "alpaca_opra_data_usage_proof_window_shared_quote_dates": usage[
                "proof_window_shared_quote_dates"
            ],
            "alpaca_opra_data_usage_required_shared_quote_dates": usage["required_shared_quote_dates"],
            "alpaca_opra_data_usage_remaining_shared_quote_dates": usage["remaining_shared_quote_dates"],
            "alpaca_opra_data_usage_all_required_symbols_have_data": usage[
                "all_required_symbols_have_alpaca_opra_data"
            ],
            "alpaca_opra_data_usage_source_inventory": usage["source_inventory"],
            "alpaca_opra_data_usage_non_proof_sources_with_quotes": usage[
                "non_proof_sources_with_quotes_in_scope"
            ],
            "alpaca_opra_data_usage_blockers": usage["blockers"],
            "alpaca_opra_data_usage_next_action": usage["next_action"],
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertEqual(
            report["alpaca_opra_data_usage_status"],
            "using_alpaca_opra_daily_snapshot_waiting_for_history_depth",
        )
        self.assertEqual(report["alpaca_opra_data_usage_remaining_shared_quote_dates"], 98)
        self.assertEqual(report["proof_source_shared_quote_dates"]["count"], 2)
        self.assertTrue(report["proof_source_all_required_symbols_available"])

    def test_attach_progress_record_summary_fields_copies_automation_health_fields(self):
        report: dict[str, object] = {}
        summary = {
            "automation_healthy": True,
            "automation_covers_fresh_opra_scan": True,
            "automation_covers_post_close_capture": True,
            "automation_schedule_exact_required_times": True,
            "automation_unexpected_intraday_times": [],
            "automation_scheduled_intraday_times": ["08:10:00", "14:20:00"],
            "automation_prompt_mentions_lane_next_step_plan": True,
            "automation_prompt_mentions_iteration_ledger": True,
            "automation_prompt_mentions_next_execution_runbook_card": True,
            "automation_prompt_mentions_run_next_execution_command_guard": True,
            "automation_prompt_mentions_profitability_scorecard_readback_packet": True,
            "automation_prompt_mentions_profitability_scorecard_readback_projection": True,
            "automation_prompt_mentions_profitability_scorecard_no_progress_condition_results": True,
            "automation_prompt_mentions_profitability_scorecard_no_progress_detected": True,
        }

        attach_progress_record_summary_fields(report, summary)

        self.assertTrue(report["automation_healthy"])
        self.assertTrue(report["automation_covers_fresh_opra_scan"])
        self.assertTrue(report["automation_covers_post_close_capture"])
        self.assertTrue(report["automation_schedule_exact_required_times"])
        self.assertEqual(report["automation_unexpected_intraday_times"], [])
        self.assertEqual(report["automation_scheduled_intraday_times"], ["08:10:00", "14:20:00"])
        self.assertTrue(report["automation_prompt_mentions_lane_next_step_plan"])
        self.assertTrue(report["automation_prompt_mentions_iteration_ledger"])
        self.assertTrue(report["automation_prompt_mentions_next_execution_runbook_card"])
        self.assertTrue(report["automation_prompt_mentions_run_next_execution_command_guard"])
        self.assertTrue(report["automation_prompt_mentions_profitability_scorecard_readback_packet"])
        self.assertTrue(report["automation_prompt_mentions_profitability_scorecard_readback_projection"])
        self.assertTrue(
            report["automation_prompt_mentions_profitability_scorecard_no_progress_condition_results"]
        )
        self.assertTrue(report["automation_prompt_mentions_profitability_scorecard_no_progress_detected"])

    def test_build_progress_history_summary_tracks_same_blocker_streak(self):
        summary = build_progress_history_summary(
            [
                {
                    "generated_at": "2026-05-21T10:00:00Z",
                    "next_blocker": "live_scan_candidates:0",
                    "run_classification": "unchanged",
                    "shared_quote_dates": {"count": 1},
                    "iteration_ledger_shared_quote_dates": {"remaining": 99},
                },
                {
                    "generated_at": "2026-05-21T10:30:00Z",
                    "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                    "run_classification": "unchanged_waiting_for_fresh_opra_scan",
                    "shared_quote_dates": {"count": 1},
                    "iteration_ledger_shared_quote_dates": {"remaining": 99},
                },
            ],
            {
                "generated_at": "2026-05-21T11:00:00Z",
                "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "run_classification": "unchanged_waiting_for_fresh_opra_scan",
                "no_progress_reason": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                "shared_quote_dates": {"count": 2},
                "iteration_ledger_shared_quote_dates": {"remaining": 98},
                "iteration_ledger_improvements": ["source_filtered_shared_quote_dates_increased"],
                "iteration_ledger_regressions": [],
                "guarded_command_decision_status": "waiting_until_next_guarded_event",
                "guarded_command_decision_action": "wait_until_not_before",
                "guarded_command_decision_source": "auxiliary_proof_event",
                "guarded_command_decision_safe_to_execute_now": False,
                "guarded_command_decision_command": None,
                "guarded_command_decision_reason": "waiting_until_not_before:2026-05-21T08:10:00-06:00",
                "guarded_command_decision_next_command_when_allowed": (
                    "python scripts/run_ai_commodity_opra_progress.py --skip-capture"
                ),
                "guarded_command_decision_next_command_role_when_allowed": (
                    "read_only_distance_measurement_no_filter_mutation"
                ),
                "previous_auxiliary_proof_event_status": "not_due_yet",
                "previous_auxiliary_proof_event_material_progress": False,
                "previous_auxiliary_proof_event_blockers": [
                    "waiting_until_not_before:2026-05-21T14:10:00Z"
                ],
            },
        )

        self.assertEqual(summary["status"], "summarized")
        self.assertEqual(summary["entry_count_including_current"], 3)
        self.assertEqual(summary["same_next_blocker_streak"], 2)
        self.assertEqual(summary["latest_shared_quote_dates"], 2)
        self.assertEqual(summary["previous_shared_quote_dates"], 1)

        self.assertEqual(summary["shared_quote_dates_delta_from_previous_entry"], 1)
        self.assertEqual(summary["remaining_quote_dates_delta_from_previous_entry"], -1)
        self.assertEqual(summary["latest_improvements"], ["source_filtered_shared_quote_dates_increased"])
        self.assertEqual(summary["latest_guarded_command_decision_status"], "waiting_until_next_guarded_event")
        self.assertEqual(summary["latest_guarded_command_decision_action"], "wait_until_not_before")
        self.assertEqual(summary["latest_guarded_command_decision_source"], "auxiliary_proof_event")
        self.assertFalse(summary["latest_guarded_command_decision_safe_to_execute_now"])
        self.assertIsNone(summary["latest_guarded_command_decision_command"])
        self.assertEqual(
            summary["latest_guarded_command_decision_next_command_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            summary["latest_guarded_command_decision_next_command_role_when_allowed"],
            "read_only_distance_measurement_no_filter_mutation",
        )
        self.assertEqual(summary["latest_previous_auxiliary_proof_event_status"], "not_due_yet")
        self.assertFalse(summary["latest_previous_auxiliary_proof_event_material_progress"])
        self.assertEqual(
            summary["latest_previous_auxiliary_proof_event_blockers"],
            ["waiting_until_not_before:2026-05-21T14:10:00Z"],
        )

    def test_recent_progress_history_loader_tails_jsonl_without_full_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "progress_history.jsonl"
            history_path.write_text(
                "\n".join(
                    [json.dumps({"sequence": idx}) for idx in range(10)]
                    + ["not-json"]
                    + [json.dumps({"sequence": 10})]
                ),
                encoding="utf8",
            )

            entries = _load_recent_progress_history_entries(history_path, limit=3)

        self.assertEqual([entry["sequence"] for entry in entries], [8, 9, 10])

    def test_build_iteration_ledger_records_blockers_and_next_evidence_action(self):
        report = {
            "generated_at": "2026-05-21T07:50:50Z",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                },
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "diagnostic_required_shared_quote_dates": 88,
                "diagnostic_remaining_shared_quote_dates": 87,
                "diagnostic_ready": False,
                "capture_cadence": "one shared exact OPRA date per market-day capture",
                "current_target_trade_date": "2026-05-21",
                "current_target_captured": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "capture_health_status": "capture_due_for_current_target",
                "missed_capture_trade_date_count": 0,
                "missed_capture_trade_dates_since_latest_shared": [],
                "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-18",
                "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
            },
            "proof_source_audit": {
                "trusted_only": True,
                "all_required_symbols_have_proof_source_data": True,
                "alpaca_like_source_labels_seen": ["alpaca_opra_daily_snapshot"],
                "non_proof_alpaca_like_source_labels": [],
            },
            "lane_next_step": {
                "priority_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                "safe_to_tune_filters": False,
            },
            "progress_delta": {
                "run_classification": "unchanged_waiting_for_fresh_opra_scan",
                "previous_generated_at": "2026-05-21T07:40:28Z",
                "improvement_flags": [],
                "regression_flags": [],
                "non_material_flags": ["scan_liquidity_gate_distance_delta_below_materiality"],
                "verification_gates_still_blocked": [
                    "enough_exact_shared_quote_dates",
                    "live_scan_has_candidate",
                ],
                "shared_quote_dates_delta": 0.0,
                "remaining_shared_quote_dates_delta": 0.0,
                "scan_candidate_count_delta": 0.0,
                "scan_ev_shortfall_delta": None,
                "scan_candidate_heuristic_ev_delta": None,
                "scan_liquidity_gate_distance_delta": 0.04,
                "read_only_watchlist_distance_deltas": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "previous_distance_to_current_filter": 6.0,
                        "current_distance_to_current_filter": 5.5,
                        "distance_delta": -0.5,
                        "direction": "closer_to_current_filters",
                        "material": True,
                    }
                ],
                "read_only_watchlist_symbols_before": ["ALB"],
                "read_only_watchlist_symbols_after": ["ALB", "PWR"],
                "read_only_watchlist_symbols_added": ["PWR"],
                "read_only_watchlist_symbols_removed": [],
                "read_only_watchlist_material_improvement_count": 1,
                "read_only_watchlist_material_regression_count": 0,
                "read_only_watchlist_non_material_change_count": 0,
                "read_only_watchlist_best_distance_delta": -0.5,
                "read_only_watchlist_worst_distance_delta": -0.5,
                "read_only_watchlist_distance_threshold": 0.25,
                "read_only_missing_fields_available_before": True,
                "read_only_missing_fields_available_after": True,
                "read_only_missing_fields_by_symbol_before": {
                    "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                    "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                },
                "read_only_missing_fields_by_symbol_after": {
                    "AA": ["sma20"],
                    "BHP": ["sma20"],
                },
                "read_only_missing_fields_symbols_before": ["AA", "BHP"],
                "read_only_missing_fields_symbols_after": ["AA", "BHP"],
                "read_only_missing_fields_symbols_added": [],
                "read_only_missing_fields_symbols_removed": [],
                "read_only_missing_field_count_before": 6,
                "read_only_missing_field_count_after": 2,
                "read_only_missing_field_count_delta": -4.0,
                "read_only_filled_missing_fields_by_symbol": {
                    "AA": ["momentum_signal_distance_pct", "price"],
                    "BHP": ["momentum_signal_distance_pct", "price"],
                },
                "read_only_newly_missing_fields_by_symbol": {},
                "read_only_still_missing_fields_by_symbol": {
                    "AA": ["sma20"],
                    "BHP": ["sma20"],
                },
                "read_only_filled_missing_field_count": 4,
                "read_only_newly_missing_field_count": 0,
                "read_only_still_missing_field_count": 2,
                "scan_drop_reason_audit_status_before": "waiting_for_next_scan_result_with_raw_drop_reasons",
                "scan_drop_reason_audit_status_after": "raw_drop_reasons_recorded",
                "scan_drop_reason_audit_status_changed": True,
                "scan_drop_reason_count_before": 0,
                "scan_drop_reason_count_after": 12,
                "scan_drop_reason_count_delta": 12.0,
                "scan_drop_reason_symbols_by_drop_after": {"momentum": ["AA"]},
                "scan_drop_reason_detail_fields_by_drop_after": {
                    "momentum": ["ret5", "price", "sma20"]
                },
                "scan_drop_reason_derived_fields_by_drop_after": {
                    "momentum": ["momentum_signal_distance_pct"]
                },
                "proof_source_label_before": "thetadata_free_eod",
                "proof_source_label_after": "alpaca_opra_daily_snapshot",
                "proof_source_label_changed": True,
                "proof_source_trusted_only_before": False,
                "proof_source_trusted_only_after": True,
                "proof_source_trusted_only_changed": True,
                "proof_source_all_required_symbols_available_before": False,
                "proof_source_all_required_symbols_available_after": True,
                "proof_source_all_required_symbols_available_changed": True,
            },
            "diagnostic_replay": {"blockers": ["insufficient_replay_simulation_quote_dates"]},
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "stale_quote_blocked"},
                "fresh_scan_retest_plan": {
                    "status": "scheduled",
                    "primary_probe_symbol": "FCX",
                },
                "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                "scan_drop_reason_count": 12,
                "scan_drop_reason_symbols_by_drop": {"momentum": ["AA"]},
                "scan_drop_reason_detail_fields_by_drop": {"momentum": ["ret5", "price", "sma20"]},
                "scan_drop_reason_derived_fields_by_drop": {
                    "momentum": ["momentum_signal_distance_pct"]
                },
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
            },
            "last_execution_review": {
                "status": "not_due_yet",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "goal_completion_audit": {
                "status": "not_complete",
                "complete": False,
                "failed_requirements": [
                    "has_required_exact_alpaca_opra_history_depth",
                    "live_scan_has_verifiable_candidate",
                ],
                "may_mark_goal_complete": False,
                "next_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "fresh_scan_iteration_decision": {
                "status": "waiting_for_fresh_opra_scan",
                "branch": "clock_guard_branch",
                "next_action": "run_fresh_opra_scan_at_not_before_time",
                "safe_to_tune_filters": False,
                "top_drop_counts": [{"drop_key": "option_liquidity", "count": 9}],
                "zero_candidate_diagnostic_plan": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["FCX"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "post_run_playbook": [
                    {
                        "condition": "fresh_scan_candidate_count_above_zero",
                        "next_action": "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
                    },
                    {
                        "condition": "quote_freshness_cleared_and_candidates_still_zero",
                        "diagnostic_drop_keys": ["option_liquidity"],
                    },
                ],
                "post_run_playbook_status": "pending_fresh_scan_execution",
                "selected_post_run_condition": None,
                "selected_post_run_next_action": None,
            },
            "iteration_ledger": {
                "status": "unchanged_waiting_for_fresh_opra_scan",
                "improvements": ["proof_source_isolation_contract_clean"],
                "regressions": [],
                "non_material_flags": ["scan_liquidity_gate_distance_delta_below_materiality"],
                "active_blockers": ["has_required_exact_alpaca_opra_history_depth"],
                "shared_quote_dates": {
                    "current": 1,
                    "required": 100,
                    "remaining": 99,
                    "diagnostic_required": 88,
                    "diagnostic_remaining": 87,
                },
                "capture_runway": {
                    "next_missing_capture_trade_date": "2026-05-21",
                    "approx_diagnostic_ready_date": "2026-09-18",
                    "approx_exact_replay_ready_date": "2026-10-06",
                },
                "unlock_conditions": {
                    "diagnostic_replay": {
                        "status": "blocked_until_shared_quote_dates",
                        "remaining_shared_quote_dates": 87,
                    },
                    "full_exact_replay": {
                        "status": "blocked_until_shared_quote_dates",
                        "remaining_shared_quote_dates": 99,
                    },
                    "filter_tuning": {"status": "locked_until_exact_replay_is_ready"},
                },
            },
        }

        ledger = build_iteration_ledger(report)

        self.assertEqual(ledger["status"], "unchanged_waiting_for_fresh_opra_scan")
        self.assertEqual(ledger["evidence_basis"], "alpaca_opra_current_report_vs_previous_latest")
        self.assertEqual(ledger["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(ledger["shared_quote_dates"]["current"], 1)
        self.assertEqual(ledger["shared_quote_dates"]["required"], 100)
        self.assertEqual(
            ledger["proof_source_integrity"],
            {
                "label": "alpaca_opra_daily_snapshot",
                "previous_label": "thetadata_free_eod",
                "label_changed": True,
                "trusted_only": True,
                "trusted_only_before": False,
                "trusted_only_changed": True,
                "all_required_symbols_available": True,
                "all_required_symbols_available_before": False,
                "all_required_symbols_available_changed": True,
                "alpaca_like_source_labels_seen": ["alpaca_opra_daily_snapshot"],
                "non_proof_alpaca_like_source_labels": [],
            },
        )
        self.assertEqual(
            ledger["capture_runway"],
            {
                "capture_cadence": "one shared exact OPRA date per market-day capture",
                "capture_calendar": "us_equity_market_days",
                "remaining_market_day_capture_count": 99,
                "diagnostic_remaining_market_day_capture_count": 87,
                "full_replay_remaining_market_day_capture_count": 99,
                "legacy_weekday_fields_are_market_day_aware": True,
                "current_target_trade_date": "2026-05-21",
                "current_target_captured": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "capture_health_status": "capture_due_for_current_target",
                "missed_capture_trade_date_count": 0,
                "missed_capture_trade_dates_since_latest_shared": [],
                "approx_diagnostic_ready_date": "2026-09-18",
                "approx_diagnostic_ready_date_market_day": "2026-09-18",
                "approx_exact_replay_ready_date": "2026-10-06",
                "approx_exact_replay_ready_date_market_day": "2026-10-06",
            },
        )
        self.assertEqual(ledger["capture_debt"]["status"], "blocked_until_forward_captures")
        self.assertEqual(ledger["capture_debt"]["remaining_shared_quote_dates"], 99)
        self.assertEqual(ledger["capture_debt"]["forward_capture_queue"][0]["trade_date"], "2026-05-21")
        self.assertEqual(ledger["capture_debt"]["forward_capture_queue"][1]["trade_date"], "2026-05-22")
        self.assertEqual(ledger["capture_debt"]["forward_capture_queue"][2]["trade_date"], "2026-05-26")
        self.assertEqual(
            ledger["capture_debt"]["unlock_milestones"]["diagnostic_replay"]["unlock_trade_date"],
            "2026-09-24",
        )
        self.assertEqual(
            ledger["capture_debt"]["unlock_milestones"]["full_exact_replay"]["unlock_trade_date"],
            "2026-10-12",
        )
        self.assertEqual(
            ledger["unlock_conditions"]["diagnostic_replay"],
            {
                "status": "blocked_until_shared_quote_dates",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 88,
                "remaining_shared_quote_dates": 87,
                "remaining_market_day_capture_count": 87,
                "approx_ready_date": "2026-09-18",
                "approx_ready_date_market_day": "2026-09-18",
            },
        )
        self.assertEqual(
            ledger["unlock_conditions"]["full_exact_replay"],
            {
                "status": "blocked_until_shared_quote_dates",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "remaining_market_day_capture_count": 99,
                "approx_ready_date": "2026-10-06",
                "approx_ready_date_market_day": "2026-10-06",
            },
        )
        self.assertEqual(
            ledger["unlock_conditions"]["filter_tuning"]["status"],
            "locked_until_exact_replay_is_ready",
        )
        self.assertEqual(ledger["improvements"], [])
        self.assertEqual(ledger["regressions"], [])
        self.assertIn("alpaca_opra_daily_snapshot_shared_quote_dates:1/100", ledger["active_blockers"])
        self.assertIn("live_scan_candidates:0", ledger["active_blockers"])
        self.assertIn("waiting_until_not_before:2026-05-21T14:10:00Z", ledger["active_blockers"])
        self.assertEqual(
            ledger["gates_still_blocked"],
            ["enough_exact_shared_quote_dates", "live_scan_has_candidate"],
        )
        self.assertEqual(
            ledger["full_universe_gates"],
            {
                "capture_scope_full_scan_universe": True,
                "capture_target_complete": True,
                "proof_scan_universe_aligned": True,
            },
        )
        self.assertEqual(ledger["scan_snapshot"]["quote_freshness_status"], "stale_quote_blocked")
        self.assertEqual(
            ledger["material_deltas"]["read_only_watchlist_best_distance"],
            -0.5,
        )
        self.assertEqual(ledger["material_deltas"]["read_only_missing_field_count"], -4.0)
        self.assertEqual(ledger["material_deltas"]["scan_drop_reason_count"], 12.0)
        self.assertEqual(
            ledger["read_only_watchlist_progress"],
            {
                "distance_deltas": [
                    {
                        "symbol": "ALB",
                        "drop_keys": ["option_liquidity"],
                        "previous_distance_to_current_filter": 6.0,
                        "current_distance_to_current_filter": 5.5,
                        "distance_delta": -0.5,
                        "direction": "closer_to_current_filters",
                        "material": True,
                    }
                ],
                "symbols_before": ["ALB"],
                "symbols_after": ["ALB", "PWR"],
                "symbols_added": ["PWR"],
                "symbols_removed": [],
                "material_improvement_count": 1,
                "material_regression_count": 0,
                "non_material_change_count": 0,
                "best_distance_delta": -0.5,
                "worst_distance_delta": -0.5,
                "distance_threshold": 0.25,
            },
        )
        self.assertEqual(
            ledger["read_only_missing_field_progress"],
            {
                "available_before": True,
                "available_after": True,
                "missing_fields_by_symbol_before": {
                    "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                    "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                },
                "missing_fields_by_symbol_after": {"AA": ["sma20"], "BHP": ["sma20"]},
                "symbols_before": ["AA", "BHP"],
                "symbols_after": ["AA", "BHP"],
                "symbols_added": [],
                "symbols_removed": [],
                "missing_field_count_before": 6,
                "missing_field_count_after": 2,
                "missing_field_count_delta": -4.0,
                "filled_missing_fields_by_symbol": {
                    "AA": ["momentum_signal_distance_pct", "price"],
                    "BHP": ["momentum_signal_distance_pct", "price"],
                },
                "newly_missing_fields_by_symbol": {},
                "still_missing_fields_by_symbol": {"AA": ["sma20"], "BHP": ["sma20"]},
                "filled_missing_field_count": 4,
                "newly_missing_field_count": 0,
                "still_missing_field_count": 2,
            },
        )
        self.assertEqual(
            ledger["scan_drop_reason_audit"],
            {
                "status_before": "waiting_for_next_scan_result_with_raw_drop_reasons",
                "status_after": "raw_drop_reasons_recorded",
                "status_changed": True,
                "count_before": 0,
                "count_after": 12,
                "count_delta": 12.0,
                "symbols_by_drop_after": {"momentum": ["AA"]},
                "detail_fields_by_drop_after": {"momentum": ["ret5", "price", "sma20"]},
                "derived_fields_by_drop_after": {"momentum": ["momentum_signal_distance_pct"]},
            },
        )
        self.assertEqual(ledger["filter_policy"], "locked_until_exact_alpaca_opra_replay_is_ready")
        self.assertEqual(
            ledger["next_evidence_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertEqual(ledger["next_execution_status"], "waiting_until_not_before")
        self.assertEqual(ledger["next_execution_not_before_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(
            ledger["next_execution_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )

    def test_build_iteration_ledger_records_previous_auxiliary_proof_event_outcome(self):
        base_report = {
            "generated_at": "2026-05-22T14:20:00Z",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
            },
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:2/100"],
                "gates": {},
            },
            "progress_delta": {
                "run_classification": "fresh_scan_auxiliary_review",
                "improvement_flags": [],
                "regression_flags": [],
                "non_material_flags": [],
                "verification_gates_still_blocked": ["live_scan_has_candidate"],
            },
            "lane_next_step": {"safe_to_tune_filters": False},
            "scan": {"candidate_count": 0},
        }
        progress_report = {
            **base_report,
            "previous_auxiliary_proof_event_outcome": {
                "status": "material_progress",
                "target_goal_requirement": "live_scan_has_verifiable_candidate",
                "advanced_goal_requirement": False,
                "material_progress": True,
                "blockers": [],
            },
        }

        progress_ledger = build_iteration_ledger(progress_report)

        self.assertIn(
            "auxiliary_proof_event_material_progress:live_scan_has_verifiable_candidate",
            progress_ledger["improvements"],
        )
        self.assertEqual(
            progress_ledger["previous_auxiliary_proof_event_status"],
            "material_progress",
        )
        self.assertEqual(
            progress_ledger["previous_auxiliary_proof_event_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        summary = build_compact_progress_summary(
            {
                **progress_report,
                "iteration_ledger": {"status": "stale_without_auxiliary_outcome"},
            }
        )
        self.assertIn(
            "auxiliary_proof_event_material_progress:live_scan_has_verifiable_candidate",
            summary["iteration_ledger_improvements"],
        )
        self.assertEqual(summary["iteration_ledger_status"], "fresh_scan_auxiliary_review")

        blocked_report = {
            **base_report,
            "previous_auxiliary_proof_event_outcome": {
                "status": "no_material_progress",
                "target_goal_requirement": "live_scan_has_verifiable_candidate",
                "advanced_goal_requirement": False,
                "material_progress": False,
                "blockers": [
                    "distance_measurement_gap_count_unchanged",
                    "fresh_scan_candidate_count_still_zero",
                ],
            },
        }

        blocked_ledger = build_iteration_ledger(blocked_report)

        self.assertIn("auxiliary_proof_event_no_material_progress", blocked_ledger["non_material_flags"])
        self.assertIn("distance_measurement_gap_count_unchanged", blocked_ledger["active_blockers"])
        self.assertIn("fresh_scan_candidate_count_still_zero", blocked_ledger["active_blockers"])

    def test_build_goal_completion_audit_blocks_until_exact_profitability_is_proven(self):
        report = {
            "generated_at": "2026-05-21T07:50:50Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
            },
            "readiness": {"status": "partial"},
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
                "replay_total_trades": None,
                "live_scan_candidate_count": 0,
                "live_scan_candidate_symbols": [],
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "exact_replay_has_trades": False,
                    "exact_replay_profit_factor_positive": False,
                    "exact_replay_total_return_positive": False,
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T07:50:50Z",
                "status": "unchanged_waiting_for_fresh_opra_scan",
                "next_evidence_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "matches_next_timed_event": True,
                "not_before_utc": "2026-05-21T14:10:00Z",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "automation_health": {"healthy": True},
        }

        audit = build_goal_completion_audit(report)

        self.assertEqual(audit["status"], "not_complete")
        self.assertFalse(audit["complete"])
        self.assertFalse(audit["may_mark_goal_complete"])
        self.assertNotIn("uses_alpaca_sip_opra_live_source", audit["failed_requirements"])
        self.assertNotIn(
            "exact_profitability_uses_isolated_alpaca_opra_proof_source",
            audit["failed_requirements"],
        )
        self.assertNotIn("full_scan_universe_is_exact_proof_scope", audit["failed_requirements"])
        self.assertIn("has_required_exact_alpaca_opra_history_depth", audit["failed_requirements"])
        self.assertIn("exact_replay_is_profitable", audit["failed_requirements"])
        self.assertIn("live_scan_has_verifiable_candidate", audit["failed_requirements"])
        self.assertIn("shared_quote_dates:1/100", audit["blockers"])
        self.assertIn("waiting_until_not_before:2026-05-21T14:10:00Z", audit["blockers"])
        self.assertEqual(
            audit["next_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )

    def test_build_goal_completion_audit_allows_completion_only_when_all_requirements_pass(self):
        report = {
            "generated_at": "2026-05-21T20:30:00Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "current_shared_quote_dates": 100,
                "required_shared_quote_dates": 100,
            },
            "readiness": {"status": "ready_for_exact_replay"},
            "verification_gate": {
                "status": "verified_profitable",
                "verified": True,
                "blockers": [],
                "replay_profit_factor": 1.4,
                "replay_total_return_pct": 8.2,
                "replay_total_trades": 22,
                "live_scan_candidate_count": 1,
                "live_scan_candidate_symbols": ["FCX"],
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": True,
                    "readiness_ready_for_exact_replay": True,
                    "exact_replay_completed": True,
                    "exact_replay_has_trades": True,
                    "exact_replay_profit_factor_positive": True,
                    "exact_replay_total_return_positive": True,
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": True,
                },
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T20:30:00Z",
                "status": "verified_profitable",
                "next_evidence_action": "goal_complete",
            },
            "next_execution_contract": {
                "status": "verified",
                "matches_next_timed_event": True,
            },
            "automation_health": {"healthy": True},
        }

        audit = build_goal_completion_audit(report)

        self.assertEqual(audit["status"], "complete")
        self.assertTrue(audit["complete"])
        self.assertTrue(audit["may_mark_goal_complete"])
        self.assertEqual(audit["failed_requirements"], [])
        self.assertEqual(audit["blockers"], [])
        self.assertEqual(audit["next_action"], "goal_complete")

    def test_build_goal_completion_audit_blocks_lowered_history_threshold_below_default_floor(self):
        report = self._verified_profitable_goal_report()
        report["proof_window"] = {
            "current_shared_quote_dates": 2,
            "required_shared_quote_dates": 2,
        }

        audit = build_goal_completion_audit(report)
        history_requirement = next(
            item
            for item in audit["requirements"]
            if item["requirement"] == "has_required_exact_alpaca_opra_history_depth"
        )

        self.assertEqual(audit["status"], "not_complete")
        self.assertFalse(audit["may_mark_goal_complete"])
        self.assertIn("has_required_exact_alpaca_opra_history_depth", audit["failed_requirements"])
        self.assertEqual(history_requirement["blocker"], "exact_history_depth_floor_not_satisfied")
        self.assertEqual(history_requirement["evidence"]["current_shared_quote_dates"], 2)
        self.assertEqual(history_requirement["evidence"]["requested_required_shared_quote_dates"], 2)
        self.assertEqual(history_requirement["evidence"]["default_required_shared_quote_dates_floor"], 100)
        self.assertEqual(history_requirement["evidence"]["effective_goal_required_shared_quote_dates"], 100)
        self.assertFalse(history_requirement["evidence"]["exact_history_depth_floor_satisfied"])
        self.assertIn("exact_history_depth_floor_not_satisfied", audit["blockers"])

    def test_build_goal_completion_audit_blocks_when_proof_source_isolation_contract_is_missing(self):
        report = self._verified_profitable_goal_report()
        report.pop("proof_source_isolation_contract")

        audit = build_goal_completion_audit(report)

        self.assertEqual(audit["status"], "not_complete")
        self.assertFalse(audit["may_mark_goal_complete"])
        self.assertIn(
            "exact_profitability_uses_isolated_alpaca_opra_proof_source",
            audit["failed_requirements"],
        )
        self.assertIn("proof_source_isolation_contract_not_clean", audit["blockers"])
        self.assertIn("proof_source_trusted_only", audit["blockers"])
        self.assertIn("proof_source_all_required_symbols_available", audit["blockers"])

    def test_build_goal_completion_audit_blocks_when_proof_source_isolation_has_blockers(self):
        report = self._verified_profitable_goal_report()
        report["proof_source_isolation_contract"] = {
            **self._clean_proof_source_isolation_contract(),
            "status": "proof_source_isolation_blocked",
            "blockers": ["non_proof_shared_dates_are_excluded"],
            "next_action": "repair_proof_source_isolation_before_profitability_claims",
        }

        audit = build_goal_completion_audit(report)

        self.assertEqual(audit["status"], "not_complete")
        self.assertFalse(audit["complete"])
        self.assertFalse(audit["may_mark_goal_complete"])
        self.assertEqual(
            audit["failed_requirements"],
            ["exact_profitability_uses_isolated_alpaca_opra_proof_source"],
        )
        self.assertIn("non_proof_shared_dates_are_excluded", audit["blockers"])

    def test_build_goal_completion_evidence_plan_maps_failed_requirements_to_commands(self):
        report = {
            "generated_at": "2026-05-21T07:50:50Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
            },
            "exact_history_acquisition_plan": {
                "backfill_capability_audit": {
                    "local_exact_store_usage_decision": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                    "local_exact_store_refresh_can_advance_history_depth": False,
                    "local_exact_available_shared_quote_dates": 1,
                    "local_exact_store_matches_proof_window": True,
                },
                "unlock_milestones": {
                    "full_exact_replay": {
                        "not_before_user_local": "2026-10-12T14:20:00-06:00",
                    },
                },
            },
            "readiness": {"status": "partial"},
            "replay": {"error": "Selected dates: 1."},
            "diagnostic_replay": {"status": "skipped", "next_action": "accumulate_replay_simulation_shared_opra_dates"},
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                },
            },
            "capture_action": {"next_action": "wait_until_next_missing_date_is_capturable:2026-05-21"},
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
                "replay_total_trades": None,
                "live_scan_candidate_count": 0,
                "live_scan_candidate_symbols": [],
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "exact_replay_has_trades": False,
                    "exact_replay_profit_factor_positive": False,
                    "exact_replay_total_return_positive": False,
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T07:50:50Z",
                "next_evidence_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "fresh_opra_live_scan",
                        "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                        "not_before_utc": "2026-05-21T14:10:00Z",
                    },
                    {
                        "step": "post_close_full_universe_capture",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-21",
                        ],
                        "not_before_utc": "2026-05-21T20:20:00Z",
                    },
                    {
                        "step": "full_exact_replay_profitability_gate",
                        "command": ["python", "scripts/run_ai_commodity_opra_progress.py"],
                    },
                ]
            },
            "next_execution_contract": {
                "selected_step": "fresh_opra_live_scan",
                "status": "waiting_until_not_before",
                "matches_next_timed_event": True,
                "not_before_utc": "2026-05-21T14:10:00Z",
            },
            "next_execution_runbook_card": {
                "selected_step": "fresh_opra_live_scan",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
            },
            "automation_health": {"healthy": True},
        }
        report["goal_completion_audit"] = build_goal_completion_audit(report)

        plan = build_goal_completion_evidence_plan(report)
        requirements = {item["requirement"]: item for item in plan["requirements"]}

        self.assertEqual(plan["status"], "not_complete")
        self.assertFalse(plan["may_mark_goal_complete"])
        self.assertEqual(plan["next_requirement_to_unblock"], "live_scan_has_verifiable_candidate")
        self.assertEqual(plan["primary_next_requirement_to_unblock"], "live_scan_has_verifiable_candidate")
        self.assertEqual(plan["next_evidence_command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(plan["next_evidence_command_role"], "fresh_live_candidate_scan_evidence")
        self.assertEqual(plan["next_evidence_not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(plan["primary_next_evidence_opportunity"]["source"], "primary_next_evidence")
        self.assertEqual(plan["earliest_evidence_opportunity_source"], "primary_next_evidence")
        self.assertEqual(
            plan["earliest_evidence_opportunity_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            plan["first_auxiliary_evidence_opportunity"]["target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            plan["first_auxiliary_evidence_opportunity"]["material_progress_if"],
        )
        self.assertEqual(requirements["uses_alpaca_sip_opra_live_source"]["status"], "proven")
        self.assertEqual(
            requirements["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["status"],
            "proven",
        )
        self.assertEqual(
            requirements["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["current_evidence"]["status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertIn(
            "proof_source_isolation_contract.blockers == []",
            requirements["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["evidence_needed"],
        )
        self.assertEqual(requirements["has_required_exact_alpaca_opra_history_depth"]["current_evidence"]["remaining_shared_quote_dates"], 99)
        self.assertEqual(
            requirements["has_required_exact_alpaca_opra_history_depth"]["current_evidence"][
                "local_exact_store_usage_decision"
            ],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(
            requirements["has_required_exact_alpaca_opra_history_depth"]["current_evidence"][
                "local_exact_store_refresh_can_advance_history_depth"
            ]
        )
        self.assertIn(
            "local exact Alpaca OPRA store dates are not ahead of proof_window.current_shared_quote_dates",
            requirements["has_required_exact_alpaca_opra_history_depth"]["evidence_needed"],
        )
        self.assertEqual(
            requirements["has_required_exact_alpaca_opra_history_depth"]["evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            requirements["has_required_exact_alpaca_opra_history_depth"]["evidence_command_role"],
            "guarded_forward_alpaca_opra_capture",
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates increases",
            requirements["has_required_exact_alpaca_opra_history_depth"]["material_progress_if"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth true triggers refresh before waiting",
            requirements["has_required_exact_alpaca_opra_history_depth"]["material_progress_if"],
        )
        self.assertEqual(
            requirements["exact_replay_is_profitable"]["blocked_until_requirement"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            requirements["exact_replay_is_profitable"]["evidence_command_role"],
            "exact_replay_profitability_measurement",
        )
        self.assertEqual(
            requirements["exact_replay_is_profitable"]["blocked_until_not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            requirements["exact_replay_is_profitable"]["not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertIn("fresh OPRA quotes inside the guarded scan window", requirements["live_scan_has_verifiable_candidate"]["evidence_needed"])
        self.assertIn(
            "raw scan drop reasons recorded when zero candidates persist",
            requirements["live_scan_has_verifiable_candidate"]["evidence_needed"],
        )
        self.assertIn(
            "scan.scan_drop_reason_count > 0",
            requirements["live_scan_has_verifiable_candidate"]["material_progress_if"],
        )

    def test_goal_completion_evidence_plan_does_not_use_capture_command_for_live_scan_evidence(self):
        report = {
            "generated_at": "2026-05-21T20:20:51Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
            },
            "readiness": {"status": "partial"},
            "replay": {"error": "Selected dates: 2."},
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "fresh_or_not_age_limited",
                    "recommended_action": "use_scan_blocker_examples_after_exact_opra_replay_is_ready",
                },
            },
            "capture_action": {
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-22",
            },
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:2/100", "live_scan_candidates:0"],
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
                "replay_total_trades": None,
                "live_scan_candidate_count": 0,
                "live_scan_candidate_symbols": [],
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "exact_replay_has_trades": False,
                    "exact_replay_profit_factor_positive": False,
                    "exact_replay_total_return_positive": False,
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T20:20:51Z",
                "next_evidence_action": "wait_until_next_missing_date_is_capturable:2026-05-22",
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "post_close_full_universe_capture",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-22",
                        ],
                        "not_before_utc": "2026-05-22T20:20:00Z",
                    }
                ]
            },
            "next_execution_contract": {
                "selected_step": "post_close_full_universe_capture",
                "status": "waiting_until_not_before",
                "matches_next_timed_event": True,
                "not_before_utc": "2026-05-22T20:20:00Z",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-22",
                ],
            },
            "next_execution_runbook_card": {
                "selected_step": "post_close_full_universe_capture",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
                "not_before_user_local": "2026-05-22T14:20:00-06:00",
            },
            "automation_health": {"healthy": True},
        }
        report["goal_completion_audit"] = build_goal_completion_audit(report)

        plan = build_goal_completion_evidence_plan(report)
        requirements = {item["requirement"]: item for item in plan["requirements"]}

        self.assertEqual(plan["next_requirement_to_unblock"], "has_required_exact_alpaca_opra_history_depth")
        self.assertEqual(
            plan["primary_next_requirement_to_unblock"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            plan["next_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
        )
        self.assertEqual(
            plan["primary_next_evidence_opportunity"]["target_goal_requirement"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(plan["earliest_evidence_opportunity_source"], "auxiliary_evidence_opportunity")
        self.assertEqual(
            plan["earliest_evidence_opportunity_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            plan["earliest_evidence_opportunity_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            plan["earliest_evidence_opportunity_not_before_user_local"],
            "2026-05-22T08:10:00-06:00",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["evidence_command_role"],
            "fresh_live_candidate_scan_evidence",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["next_action"],
            "run_read_only_fresh_opra_scan_to_record_raw_drop_reasons_or_live_candidate",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["not_before_user_local"],
            "2026-05-22T08:10:00-06:00",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["window_end_user_local"],
            "2026-05-22T14:00:00-06:00",
        )
        self.assertEqual(
            requirements["live_scan_has_verifiable_candidate"]["scan_drop_reason_audit_blockers"],
            [
                "scan_drop_reason_audit_status_not_raw_drop_reasons_recorded",
                "scan_drop_reason_count_zero_or_missing",
            ],
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            requirements["live_scan_has_verifiable_candidate"]["material_progress_if"],
        )
        self.assertEqual(
            plan["first_auxiliary_evidence_opportunity"]["not_before_user_local"],
            "2026-05-22T08:10:00-06:00",
        )
        self.assertTrue(plan["first_auxiliary_evidence_opportunity"]["precedes_primary_next_evidence"])
        self.assertEqual(plan["first_auxiliary_evidence_opportunity"]["minutes_before_primary_next_evidence"], 370.0)
        self.assertEqual(
            plan["first_auxiliary_evidence_opportunity"]["window_end_user_local"],
            "2026-05-22T14:00:00-06:00",
        )
        self.assertNotEqual(
            requirements["live_scan_has_verifiable_candidate"]["evidence_command"],
            plan["next_evidence_command"],
        )

    def test_fresh_scan_decision_does_not_treat_post_close_capture_as_next_fresh_scan(self):
        decision = build_fresh_scan_iteration_decision(
            {
                "scan": {
                    "candidate_count": 0,
                    "candidate_symbols": [],
                    "quote_freshness_context": {
                        "status": "fresh_or_not_age_limited",
                        "recommended_action": "use_scan_blocker_examples_after_exact_opra_replay_is_ready",
                    },
                    "scan_funnel": {"drop_counts": {"tech_score": 8}},
                    "drop_diagnostics": [{"drop_key": "tech_score", "count": 8}],
                },
                "lane_next_step": {
                    "next_timed_event_kind": "post_close_opra_capture",
                    "next_timed_event_utc": "2026-05-22T20:20:00Z",
                },
                "verification_gate": {"blockers": ["live_scan_candidates:0"]},
                "goal_completion_audit": {
                    "failed_requirements": [
                        "has_required_exact_alpaca_opra_history_depth",
                        "live_scan_has_verifiable_candidate",
                    ]
                },
            }
        )

        self.assertEqual(decision["status"], "fresh_scan_zero_candidates_structural_review")
        self.assertIsNone(decision["next_fresh_scan_utc"])
        self.assertEqual(
            decision["selected_fresh_scan_outcome_next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )

    def test_build_goal_completion_verification_contract_blocks_goal_update(self):
        report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 1."},
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                },
            },
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 24,
                "scan_universe_count": 24,
                "candidate_symbols": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "capture": {
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
            },
            "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
            "automation_health": {"healthy": True},
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "matches_next_timed_event": True,
                "not_before_utc": "2026-05-21T14:10:00Z",
            },
            "next_execution_runbook_card": {
                "guard_status": "clock_guard_active",
                "selected_step": "fresh_opra_live_scan",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
            },
            "iteration_ledger": {
                "generated_at": "2026-05-21T10:37:15Z",
                "status": "unchanged_waiting_for_fresh_opra_scan",
                "next_evidence_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "derived_refresh": {
                "status": "derived_fields_refreshed_from_latest_without_market_data",
                "refreshed_at_utc": "2026-05-21T10:45:00Z",
                "market_data_commands_run": False,
                "automation_health_refreshed": True,
                "historical_store_refreshed": True,
                "historical_store_refresh_error": None,
                "historical_store_shared_quote_dates_before": 1,
                "historical_store_shared_quote_dates_after": 1,
                "historical_store_shared_quote_dates_changed": False,
                "preserved_evidence_stale_after_historical_store_refresh": False,
                "preserved_evidence_stale_fields": [],
                "preserved_evidence_refresh_command": None,
                "preserved_evidence_refresh_reason": None,
                "next_blocker_before": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "raw_next_blocker_after": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "next_blocker_after": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "next_blocker_changed": False,
            },
        }
        report["verification_gate"] = build_verified_profitability_gate(report)
        report["goal_completion_audit"] = build_goal_completion_audit(report)
        report["goal_completion_evidence_plan"] = build_goal_completion_evidence_plan(report)

        contract = build_goal_completion_verification_contract(report)
        rows = {item["requirement"]: item for item in contract["requirements"]}

        self.assertEqual(contract["status"], "blocked")
        self.assertFalse(contract["completion_claim_allowed"])
        self.assertEqual(
            contract["goal_update_policy"],
            "call_update_goal_complete_only_when_completion_claim_allowed_true",
        )
        self.assertEqual(contract["current_shared_quote_dates"], 1)
        self.assertEqual(contract["required_shared_quote_dates"], 100)
        self.assertEqual(contract["live_scan_candidate_count"], 0)
        self.assertEqual(contract["record_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertEqual(contract["derived_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertTrue(contract["automation_health_refreshed_in_current_refresh"])
        self.assertIn("has_required_exact_alpaca_opra_history_depth", contract["unproven_requirements"])
        self.assertEqual(contract["next_requirement_to_unblock"], "live_scan_has_verifiable_candidate")
        self.assertEqual(contract["next_evidence_command_role"], "fresh_live_candidate_scan_evidence")
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            rows["has_required_exact_alpaca_opra_history_depth"]["authoritative_evidence_fields"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision",
            rows["has_required_exact_alpaca_opra_history_depth"]["authoritative_evidence_fields"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth",
            rows["has_required_exact_alpaca_opra_history_depth"]["authoritative_evidence_fields"],
        )
        self.assertEqual(rows["uses_alpaca_sip_opra_live_source"]["inspection_result"], "proves_requirement")
        self.assertEqual(
            rows["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["inspection_result"],
            "proves_requirement",
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            rows["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["authoritative_evidence_fields"],
        )
        self.assertEqual(
            rows["exact_profitability_uses_isolated_alpaca_opra_proof_source"]["current_evidence"]["blockers"],
            [],
        )
        self.assertEqual(rows["exact_replay_is_profitable"]["inspection_result"], "missing_or_incomplete_evidence")
        self.assertEqual(
            rows["exact_replay_is_profitable"]["evidence_command_role"],
            "exact_replay_profitability_measurement",
        )
        self.assertEqual(
            rows["exact_replay_is_profitable"]["blocked_until_requirement"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(rows["live_scan_has_verifiable_candidate"]["evidence_strength"], "insufficient_current_artifact")
        self.assertIn(
            "scan.scan_drop_reason_audit_status",
            rows["live_scan_has_verifiable_candidate"]["authoritative_evidence_fields"],
        )
        self.assertIn(
            "scan.scan_drop_reason_count",
            rows["live_scan_has_verifiable_candidate"]["authoritative_evidence_fields"],
        )
        self.assertIn(
            "goal_completion_evidence_plan.first_auxiliary_evidence_opportunity",
            rows["live_scan_has_verifiable_candidate"]["authoritative_evidence_fields"],
        )
        self.assertEqual(
            rows["live_scan_has_verifiable_candidate"]["evidence_command_role"],
            "fresh_live_candidate_scan_evidence",
        )
        self.assertIn(
            "live_scan_has_candidate true",
            rows["live_scan_has_verifiable_candidate"]["material_progress_if"],
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            rows["live_scan_has_verifiable_candidate"]["material_progress_if"],
        )
        self.assertIn(
            "scan.scan_drop_reason_count > 0",
            rows["live_scan_has_verifiable_candidate"]["material_progress_if"],
        )
        iteration_evidence = rows["iteration_record_is_current"]["current_evidence"]
        self.assertEqual(iteration_evidence["record_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertEqual(
            iteration_evidence["derived_refresh_status"],
            "derived_fields_refreshed_from_latest_without_market_data",
        )
        self.assertFalse(iteration_evidence["derived_refresh_market_data_commands_run"])

    def test_build_exact_history_backfill_capability_audit_blocks_historical_bar_shortcut(self):
        audit = build_exact_history_backfill_capability_audit(
            {
                "proof_window": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                }
            }
        )

        self.assertEqual(audit["status"], "forward_capture_required_for_exact_bid_ask_history")
        self.assertFalse(audit["can_accelerate_exact_history"])
        self.assertEqual(
            audit["acceleration_decision"]["decision"],
            "do_not_accelerate_exact_history_from_alpaca_historical_bars_or_trades",
        )
        self.assertEqual(audit["acceleration_decision"]["reviewed_at"], "2026-05-22")
        self.assertEqual(
            audit["acceleration_decision"]["required_to_change_decision"],
            "official_alpaca_historical_option_quote_bbo_endpoint_or_contract_snapshot_history",
        )
        self.assertEqual(audit["official_endpoint_review_checked_at"], "2026-05-22")
        self.assertFalse(
            audit["official_reference_index_review"]["historical_option_quotes_reference_entry_found"]
        )
        self.assertFalse(
            audit["official_reference_index_review"][
                "historical_option_bbo_backfill_reference_entry_found"
            ]
        )
        self.assertIn(
            "latest_option_quotes",
            audit["official_reference_index_review"]["observed_option_market_data_reference_entries"],
        )
        self.assertEqual(
            audit["official_reference_index_review"]["review_conclusion"],
            "official_reference_index_lists_no_historical_option_quote_bbo_endpoint",
        )
        self.assertEqual(audit["missing_capability"], "historical_option_quote_bbo_method_for_contracts")
        self.assertIn("no_historical_option_quote_bbo_endpoint", audit["acceleration_blockers"])
        self.assertIn(
            "option_snapshot_updated_since_filters_recent_updates_not_historical_as_of_snapshots",
            audit["acceleration_blockers"],
        )
        self.assertEqual(audit["current_exact_capture_source"], "alpaca_opra_daily_snapshot")
        self.assertEqual(
            audit["local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(audit["local_exact_store_refresh_can_advance_history_depth"])
        self.assertIsNone(audit["local_exact_available_shared_quote_dates"])
        self.assertFalse(audit["can_use_historical_bars_for_exact_profitability"])
        self.assertFalse(audit["can_use_historical_trades_for_exact_profitability"])
        self.assertTrue(audit["can_use_latest_quote_snapshot_for_forward_capture"])
        self.assertFalse(audit["historical_option_quote_endpoint_found"])
        self.assertFalse(audit["historical_option_bbo_backfill_endpoint_found"])
        self.assertFalse(audit["snapshot_updated_since_is_backfill_capability"])
        self.assertIn("not an as-of-date historical BBO", audit["snapshot_updated_since_interpretation"])
        self.assertIn("option_snapshots", audit["safe_forward_capture_inputs"])
        self.assertIn("latest_option_snapshots_with_updated_since_for_prior_dates", audit["unsafe_exact_backfill_shortcuts"])
        self.assertEqual(audit["next_action"], "continue_forward_daily_alpaca_opra_snapshot_capture")
        surface = {item["method"]: item for item in audit["alpaca_current_surface"]}
        self.assertFalse(surface["get_option_bars"]["counts_for_exact_bid_ask_profitability"])
        self.assertFalse(surface["get_option_trades"]["counts_for_exact_bid_ask_profitability"])
        self.assertEqual(surface["get_option_latest_quote"]["history_scope"], "current_latest_only")
        docs = {item["label"]: item for item in audit["docs_reviewed"]}
        self.assertIn("historical-option-data", docs["Alpaca historical option data"]["url"])
        self.assertIn("optionlatestquotes", docs["Alpaca latest option quotes"]["url"])
        endpoint_review = {item["capability"]: item for item in audit["official_endpoint_review"]}
        self.assertEqual(endpoint_review["historical_option_bars"]["history_scope"], "historical_aggregates")
        self.assertFalse(endpoint_review["historical_option_bars"]["counts_for_exact_bid_ask_profitability"])
        self.assertIn("aggregates", endpoint_review["historical_option_bars"]["official_surface_observed"])
        self.assertEqual(endpoint_review["historical_option_trades"]["history_scope"], "historical_prints")
        self.assertFalse(endpoint_review["historical_option_trades"]["counts_for_exact_bid_ask_profitability"])
        self.assertEqual(endpoint_review["latest_option_quotes"]["history_scope"], "current_latest_only")
        self.assertIn("bid and ask", endpoint_review["latest_option_quotes"]["official_surface_observed"])
        self.assertEqual(endpoint_review["option_chain_snapshots"]["history_scope"], "current_latest_snapshot_only")
        self.assertFalse(endpoint_review["option_chain_snapshots"]["updated_since_filter_is_historical_backfill"])
        self.assertFalse(endpoint_review["option_snapshots"]["updated_since_filter_is_historical_backfill"])

    def test_build_exact_history_backfill_capability_audit_flags_stale_proof_window_against_local_store(self):
        audit = build_exact_history_backfill_capability_audit(
            {
                "proof_window": {
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
                "proof_source_audit": {
                    "proof_source_shared_quote_dates": {
                        "count": 3,
                        "first": "2026-05-20",
                        "last": "2026-05-22",
                    },
                    "proof_source_required_symbol_coverage": {
                        "required_symbol_count": 24,
                        "available_required_symbol_count": 24,
                        "missing_required_symbols": [],
                    },
                    "proof_source_store_inventory": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "quote_dates": {
                            "count": 3,
                            "first": "2026-05-20",
                            "last": "2026-05-22",
                        },
                        "underlying_count_in_scope": 24,
                    },
                },
            }
        )

        self.assertEqual(audit["status"], "local_exact_store_refresh_required")
        self.assertTrue(audit["local_exact_store_refresh_can_advance_history_depth"])
        self.assertTrue(audit["local_exact_store_has_more_dates_than_proof_window"])
        self.assertFalse(audit["local_exact_store_matches_proof_window"])
        self.assertEqual(audit["local_exact_available_shared_quote_dates"], 3)
        self.assertEqual(
            audit["local_exact_store_usage_decision"],
            "refresh_derived_history_from_local_alpaca_opra_store_before_waiting_for_forward_capture",
        )
        self.assertEqual(audit["next_action"], "refresh_derived_history_from_local_alpaca_opra_store")

    def test_build_exact_capture_import_health_tracks_duplicate_reruns_and_next_success(self):
        health = build_exact_capture_import_health(
            {
                "proof_window": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_audit": {
                    "snapshot_kind": "daily_eod",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_required_symbol_coverage": {"required_symbol_count": 24},
                    "proof_source_store_inventory": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "batch_count": 3,
                        "batch_total_rows": 25728,
                        "batch_imported_rows": 11836,
                        "batch_duplicate_rows": 13892,
                        "batch_rejected_rows": 0,
                        "latest_imported_at_utc": "2026-05-21T06:20:22Z",
                        "quote_rows_in_scope": 11836,
                        "quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                        "underlying_count_in_scope": 24,
                        "requested_underlying_count": 24,
                    },
                },
                "capture": {
                    "status": "skipped_existing_shared_date",
                    "target_capture_complete": True,
                },
                "capture_action": {
                    "next_scheduled_capture": {
                        "scheduled_utc": "2026-05-21T20:20:00Z",
                        "scheduled_user_local": "2026-05-21T14:20:00-06:00",
                    },
                },
            }
        )

        self.assertEqual(health["status"], "healthy_forward_capture_wait_with_duplicate_reruns")
        self.assertEqual(health["current_shared_quote_dates"], 1)
        self.assertEqual(health["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(health["next_capture_not_before_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(health["next_capture_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(health["batch_duplicate_rows"], 13892)
        self.assertGreater(health["batch_duplicate_row_pct"], 50.0)
        self.assertTrue(health["all_required_underlyings_in_scope"])
        self.assertEqual(health["duplicate_rows_interpretation"], "idempotent_same_date_reimports_or_reruns")
        self.assertIn("shared_quote_dates_count_increments_to_2", health["success_criteria_for_next_capture"])
        self.assertIn(
            "duplicate_rows_are_ok_only_when_shared_quote_dates_already_include_target_date",
            health["failure_signals_after_next_capture"],
        )
        self.assertEqual(health["next_action"], "run_next_scheduled_exact_opra_capture_after_not_before")

        derived_local_time = build_exact_capture_import_health(
            {
                "proof_window": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_audit": {
                    "proof_source_store_inventory": {
                        "batch_count": 1,
                        "batch_total_rows": 10,
                        "batch_imported_rows": 10,
                        "batch_duplicate_rows": 0,
                        "batch_rejected_rows": 0,
                        "quote_dates": {"count": 1},
                        "underlying_count_in_scope": 1,
                        "requested_underlying_count": 1,
                    },
                },
                "capture_action": {
                    "next_scheduled_capture": {"scheduled_utc": "2026-05-21T20:20:00Z"},
                },
            }
        )
        self.assertEqual(
            derived_local_time["next_capture_not_before_user_local"],
            "2026-05-21T14:20:00-06:00",
        )

    def test_build_exact_capture_post_run_evaluation_waits_for_next_capture(self):
        evaluation = build_exact_capture_post_run_evaluation(
            {
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_audit": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "trusted_only": True,
                    "all_required_symbols_have_proof_source_data": True,
                    "proof_source_shared_quote_dates": {"count": 1},
                    "proof_source_store_inventory": {"quote_dates": {"count": 1}},
                    "proof_source_required_symbol_coverage": {
                        "available_required_symbol_count": 24,
                        "required_symbol_count": 24,
                    },
                },
                "exact_history_acquisition_plan": {
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                    },
                },
                "exact_capture_import_health": {
                    "status": "healthy_forward_capture_wait_with_duplicate_reruns",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "batch_imported_rows": 11836,
                    "batch_duplicate_rows": 13892,
                    "batch_rejected_rows": 0,
                    "all_required_underlyings_in_scope": True,
                    "success_criteria_for_next_capture": ["shared_quote_dates_count_increments_to_2"],
                    "failure_signals_after_next_capture": ["capture_target_complete_false"],
                },
                "capture": {
                    "status": "skipped_existing_shared_date",
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "capture_action": {
                    "status": "waiting_for_next_market_close",
                    "can_attempt_capture_now": False,
                },
            }
        )

        self.assertEqual(evaluation["status"], "waiting_for_next_exact_capture_execution")
        self.assertEqual(
            evaluation["next_action"],
            "wait_until_next_capture_not_before_then_run_guarded_capture",
        )
        self.assertEqual(
            evaluation["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(evaluation["next_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(
            evaluation["post_capture_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            evaluation["post_capture_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(
            evaluation["post_capture_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertIn(
            "exact_replay_unlock_contract.full_exact_replay_unlocked",
            evaluation["post_capture_profitability_gate_fields"],
        )
        self.assertEqual(
            [step["step"] for step in evaluation["post_capture_profitability_handoff"]],
            [
                "readback_next_execution_after_capture",
                "refresh_readiness_replay_if_local_store_changed",
                "run_exact_replay_when_unlocked",
            ],
        )
        evidence_contract = evaluation["post_capture_evidence_contract"]
        self.assertEqual(evidence_contract["status"], "waiting_for_guarded_capture_run")
        self.assertEqual(evaluation["next_capture_evidence_state"], "next_capture_target_waiting_until_not_before")
        self.assertFalse(evaluation["next_capture_target_observed"])
        self.assertEqual(evaluation["latest_capture_evidence_status"], "waiting_for_guarded_capture_run")
        self.assertFalse(evaluation["stale_success_guard_for_next_target"])
        self.assertEqual(
            evaluation["next_capture_pending_reason"],
            "waiting_until_not_before:2026-05-21T14:20:00-06:00",
        )
        self.assertEqual(evidence_contract["next_capture_evidence_state"], "next_capture_target_waiting_until_not_before")
        self.assertFalse(evidence_contract["next_capture_target_observed"])
        self.assertFalse(evidence_contract["stale_success_guard_for_next_target"])
        self.assertEqual(evidence_contract["target_goal_requirement"], "has_required_exact_alpaca_opra_history_depth")
        self.assertEqual(evidence_contract["target_trade_date"], "2026-05-21")
        self.assertEqual(evidence_contract["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertIn("next_execution_runbook_card.run_next_execution_command true", evidence_contract["required_before_run"])
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            evidence_contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision",
            evidence_contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth",
            evidence_contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_available_shared_quote_dates",
            evidence_contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window",
            evidence_contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates >= 2",
            evidence_contract["material_progress_if"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window true",
            evidence_contract["material_progress_if"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates < 2",
            evidence_contract["failure_signals_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth true",
            evidence_contract["failure_signals_after_run"],
        )
        self.assertEqual(
            evaluation["local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(evaluation["local_exact_store_refresh_can_advance_history_depth"])
        self.assertEqual(evaluation["local_exact_available_shared_quote_dates"], 1)
        self.assertTrue(evaluation["local_exact_store_matches_proof_window"])
        self.assertEqual(evaluation["current_shared_quote_dates"], 1)
        self.assertEqual(evaluation["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(evaluation["blockers"], [])
        checks = {check["name"]: check for check in evaluation["checks"]}
        self.assertTrue(checks["proof_source_is_alpaca_opra_daily_snapshot"]["passed"])
        self.assertTrue(checks["proof_source_trusted_only"]["passed"])
        self.assertTrue(checks["proof_source_all_required_symbols_available"]["passed"])
        self.assertTrue(checks["batch_rejected_rows_zero"]["passed"])

    def test_build_exact_capture_post_run_evaluation_marks_previous_success_stale_for_next_target(self):
        evaluation = build_exact_capture_post_run_evaluation(
            {
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-22",
                },
                "proof_source_audit": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "trusted_only": True,
                    "all_required_symbols_have_proof_source_data": True,
                },
                "exact_history_acquisition_plan": {
                    "next_capture_trade_date": "2026-05-22",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
                    "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
                },
                "exact_capture_import_health": {
                    "status": "healthy_forward_capture_wait_with_duplicate_reruns",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 3,
                    "next_capture_trade_date": "2026-05-22",
                    "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
                    "batch_rejected_rows": 0,
                    "all_required_underlyings_in_scope": True,
                },
                "capture": {
                    "status": "captured",
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "capture_action": {
                    "status": "waiting_for_next_market_close",
                    "can_attempt_capture_now": False,
                },
                "last_execution_review": {
                    "previous_selected_step": "post_close_full_universe_capture",
                    "status": "passed",
                },
            }
        )

        evidence_contract = evaluation["post_capture_evidence_contract"]
        self.assertEqual(evaluation["status"], "exact_capture_advanced_shared_history")
        self.assertEqual(evidence_contract["status"], "post_capture_progress_observed")
        self.assertEqual(evaluation["latest_capture_evidence_status"], "post_capture_progress_observed")
        self.assertEqual(evaluation["next_capture_evidence_state"], "next_capture_target_waiting_until_not_before")
        self.assertFalse(evaluation["next_capture_target_observed"])
        self.assertTrue(evaluation["stale_success_guard_for_next_target"])
        self.assertEqual(
            evaluation["next_capture_pending_reason"],
            "waiting_until_not_before:2026-05-22T14:20:00-06:00",
        )
        self.assertEqual(evidence_contract["next_capture_evidence_state"], "next_capture_target_waiting_until_not_before")
        self.assertFalse(evidence_contract["next_capture_target_observed"])
        self.assertTrue(evidence_contract["stale_success_guard_for_next_target"])

    def test_build_exact_capture_post_run_evaluation_reports_failed_capture(self):
        evaluation = build_exact_capture_post_run_evaluation(
            {
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_audit": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "trusted_only": True,
                    "all_required_symbols_have_proof_source_data": True,
                },
                "exact_capture_import_health": {
                    "status": "healthy_forward_capture_wait",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "next_capture_trade_date": "2026-05-21",
                    "batch_imported_rows": 11836,
                    "batch_duplicate_rows": 0,
                    "batch_rejected_rows": 0,
                    "all_required_underlyings_in_scope": True,
                },
                "capture": {
                    "status": "captured",
                    "target_capture_complete": False,
                    "missing_target_date_symbols_after": ["FCX"],
                },
                "last_execution_review": {
                    "previous_selected_step": "post_close_full_universe_capture",
                    "status": "failed",
                    "blockers": ["capture_target_complete_true"],
                },
            }
        )

        self.assertEqual(evaluation["status"], "exact_capture_failed_or_did_not_advance")
        self.assertEqual(evaluation["next_action"], "recapture_or_inspect_exact_alpaca_opra_import_failure")
        self.assertEqual(
            evaluation["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(evaluation["blockers"], ["capture_target_complete_true"])
        self.assertEqual(evaluation["missing_target_date_symbols_after"], ["FCX"])

    def test_build_exact_capture_progress_contract_records_expected_increment(self):
        contract = build_exact_capture_progress_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_audit": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_shared_quote_dates": {"count": 1},
                    "proof_source_store_inventory": {"quote_dates": {"count": 1}},
                    "proof_source_required_symbol_coverage": {
                        "available_required_symbol_count": 24,
                        "required_symbol_count": 24,
                        "missing_required_symbols": [],
                    },
                },
                "proof_source_isolation_contract": {
                    "status": "isolated_to_alpaca_opra_proof_source",
                    "blockers": [],
                },
                "verification_gate": {
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                    }
                },
                "exact_history_acquisition_plan": {
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                    },
                },
                "exact_capture_import_health": {
                    "status": "healthy_forward_capture_wait",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                },
                "capture": {"target_capture_complete": True},
            }
        )

        self.assertEqual(contract["status"], "awaiting_guarded_capture_to_advance_history")
        self.assertEqual(contract["target_trade_date"], "2026-05-21")
        self.assertEqual(
            contract["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(contract["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(contract["remaining_shared_quote_dates_before"], 99)
        self.assertEqual(contract["remaining_shared_quote_dates_after_success"], 98)
        self.assertEqual(contract["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(contract["proof_source_isolation_blockers"], [])
        self.assertEqual(contract["capture_continuity_status"], "on_track_no_missed_capture_dates")
        self.assertEqual(contract["capture_continuity_missed_capture_trade_dates"], [])
        self.assertEqual(
            contract["capture_continuity_missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertEqual(
            contract["local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(contract["local_exact_store_refresh_can_advance_history_depth"])
        self.assertEqual(contract["local_exact_available_shared_quote_dates"], 1)
        self.assertTrue(contract["local_exact_store_matches_proof_window"])
        self.assertIn("proof_window.current_shared_quote_dates == 2", contract["material_progress_if"])
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            contract["material_progress_if"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window true",
            contract["material_progress_if"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_trade_dates empty",
            contract["material_progress_if"],
        )
        self.assertIn("proof_window.current_shared_quote_dates", contract["fields_to_compare_after_run"])
        self.assertIn("proof_source_isolation_contract.status", contract["fields_to_compare_after_run"])
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_available_shared_quote_dates",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.status",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_policy",
            contract["fields_to_compare_after_run"],
        )
        self.assertIn("proof_window.current_shared_quote_dates < 2", contract["failure_signals_after_run"])
        self.assertIn(
            "proof_source_isolation_contract.status != isolated_to_alpaca_opra_proof_source",
            contract["failure_signals_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth true",
            contract["failure_signals_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_trade_dates nonempty",
            contract["failure_signals_after_run"],
        )
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(contract["next_action"], "run_guarded_capture_after_not_before")

    def test_build_exact_capture_progress_contract_blocks_missed_capture_continuity(self):
        contract = build_exact_capture_progress_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "proof_source_isolation_contract": {
                    "status": "isolated_to_alpaca_opra_proof_source",
                    "blockers": [],
                },
                "verification_gate": {
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                    }
                },
                "exact_history_acquisition_plan": {
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "capture_continuity_contract": {
                        "status": "intervention_required_missed_capture_dates",
                        "missed_capture_trade_dates": ["2026-05-18"],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": False,
                    },
                },
                "exact_capture_import_health": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 2,
                },
                "capture": {"target_capture_complete": True},
            }
        )

        self.assertEqual(contract["status"], "capture_progress_contract_blocked")
        self.assertIn("capture_continuity_status_on_track_or_complete", contract["blockers"])
        self.assertIn("capture_continuity_has_no_missed_dates", contract["blockers"])
        self.assertEqual(contract["capture_continuity_missed_capture_trade_dates"], ["2026-05-18"])
        self.assertEqual(contract["next_action"], "repair_capture_progress_contract_before_next_capture")

    def test_build_exact_capture_progress_contract_marks_depth_ready(self):
        contract = build_exact_capture_progress_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "verification_gate": {
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                    }
                },
                "exact_capture_import_health": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 100,
                },
            }
        )

        self.assertEqual(contract["status"], "history_depth_ready_no_capture_needed")
        self.assertEqual(contract["next_action"], "run_exact_replay_profitability_gate")
        self.assertEqual(contract["remaining_shared_quote_dates_before"], 0)
        self.assertEqual(contract["remaining_shared_quote_dates_after_success"], 0)

    def test_build_exact_capture_progress_outcome_verifies_previous_contract_increment(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "exact_capture_progress_contract": {
                "status": "awaiting_guarded_capture_to_advance_history",
                "target_trade_date": "2026-05-21",
                "current_shared_quote_dates": 1,
                "expected_shared_quote_dates_after_next_capture": 2,
                "remaining_shared_quote_dates_after_success": 98,
                "not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "next_execution_contract": {"not_before_utc": "2026-05-21T20:20:00Z"},
            "proof_window": {"current_shared_quote_dates": 1, "remaining_shared_quote_dates": 99},
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "remaining_shared_quote_dates": 98,
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_source_shared_quote_dates": {"count": 2},
                "proof_source_store_inventory": {"quote_dates": {"count": 2}},
                "proof_source_required_symbol_coverage": {
                    "available_required_symbol_count": 24,
                    "required_symbol_count": 24,
                    "missing_required_symbols": [],
                },
            },
            "proof_source_isolation_contract": {
                "status": "isolated_to_alpaca_opra_proof_source",
                "blockers": [],
            },
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }

        outcome = build_exact_capture_progress_outcome(previous, current)

        self.assertEqual(outcome["status"], "exact_capture_progress_verified")
        self.assertEqual(outcome["contract_source"], "previous_report")
        self.assertEqual(outcome["target_trade_date"], "2026-05-21")
        self.assertEqual(outcome["shared_quote_dates_before"], 1)
        self.assertEqual(outcome["shared_quote_dates_after"], 2)
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(
            outcome["evidence"]["proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(
            outcome["evidence"]["local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(outcome["evidence"]["local_exact_store_refresh_can_advance_history_depth"])
        self.assertEqual(outcome["evidence"]["local_exact_available_shared_quote_dates"], 2)
        self.assertTrue(outcome["evidence"]["local_exact_store_matches_proof_window"])
        self.assertEqual(outcome["next_action"], "continue_daily_exact_opra_capture_runway")

    def test_build_exact_capture_progress_outcome_blocks_local_store_mismatch_after_capture(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "exact_capture_progress_contract": {
                "status": "awaiting_guarded_capture_to_advance_history",
                "target_trade_date": "2026-05-21",
                "current_shared_quote_dates": 1,
                "expected_shared_quote_dates_after_next_capture": 2,
                "remaining_shared_quote_dates_after_success": 98,
            },
            "next_execution_contract": {"not_before_utc": "2026-05-21T20:20:00Z"},
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "remaining_shared_quote_dates": 98,
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_source_shared_quote_dates": {"count": 3},
                "proof_source_store_inventory": {"quote_dates": {"count": 3}},
                "proof_source_required_symbol_coverage": {
                    "available_required_symbol_count": 24,
                    "required_symbol_count": 24,
                    "missing_required_symbols": [],
                },
            },
            "proof_source_isolation_contract": {
                "status": "isolated_to_alpaca_opra_proof_source",
                "blockers": [],
            },
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }

        outcome = build_exact_capture_progress_outcome(previous, current)

        self.assertEqual(outcome["status"], "exact_capture_progress_partial_with_import_blockers")
        self.assertIn("local_exact_store_matches_proof_window_after_capture", outcome["blockers"])
        self.assertIn("local_exact_store_has_no_pending_refresh_after_capture", outcome["blockers"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(
            outcome["evidence"]["local_exact_store_usage_decision"],
            "refresh_derived_history_from_local_alpaca_opra_store_before_waiting_for_forward_capture",
        )
        self.assertTrue(outcome["evidence"]["local_exact_store_refresh_can_advance_history_depth"])
        self.assertEqual(outcome["evidence"]["local_exact_available_shared_quote_dates"], 3)
        self.assertFalse(outcome["evidence"]["local_exact_store_matches_proof_window"])

    def test_build_exact_capture_progress_outcome_blocks_mixed_source_after_capture(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "exact_capture_progress_contract": {
                "status": "awaiting_guarded_capture_to_advance_history",
                "target_trade_date": "2026-05-21",
                "current_shared_quote_dates": 1,
                "expected_shared_quote_dates_after_next_capture": 2,
                "remaining_shared_quote_dates_after_success": 98,
            },
            "next_execution_contract": {"not_before_utc": "2026-05-21T20:20:00Z"},
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "remaining_shared_quote_dates": 98,
            },
            "proof_source_isolation_contract": {
                "status": "proof_source_isolation_blocked",
                "blockers": ["top_level_shared_dates_match_proof_source_shared_dates"],
            },
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "exact_capture_import_health": {"batch_rejected_rows": 0},
        }

        outcome = build_exact_capture_progress_outcome(previous, current)

        self.assertEqual(outcome["status"], "exact_capture_progress_partial_with_import_blockers")
        self.assertIn("proof_source_isolation_contract_clean_after_capture", outcome["blockers"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(
            outcome["evidence"]["proof_source_isolation_blockers"],
            ["top_level_shared_dates_match_proof_source_shared_dates"],
        )
        self.assertEqual(outcome["next_action"], "repair_capture_import_blockers_before_replay_claims")

    def test_build_exact_capture_progress_outcome_waits_before_guard(self):
        outcome = build_exact_capture_progress_outcome(
            None,
            {
                "generated_at": "2026-05-21T16:00:00Z",
                "provider": "alpaca:sip:opra",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "remaining_shared_quote_dates": 99,
                },
                "exact_capture_progress_contract": {
                    "target_trade_date": "2026-05-21",
                    "current_shared_quote_dates": 1,
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "remaining_shared_quote_dates_after_success": 98,
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                },
                "next_execution_contract": {"not_before_utc": "2026-05-21T20:20:00Z"},
                "derived_refresh": {
                    "refreshed_at_utc": "2026-05-21T16:00:00Z",
                    "market_data_commands_run": False,
                },
            },
        )

        self.assertEqual(outcome["status"], "waiting_until_not_before")
        self.assertEqual(outcome["contract_source"], "current_report")
        self.assertFalse(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], ["waiting_until_not_before:2026-05-21T20:20:00Z"])

    def test_build_exact_replay_unlock_contract_waits_for_diagnostic_history(self):
        contract = build_exact_replay_unlock_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "verification_gate": {
                    "gates": {
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                    }
                },
                "readiness": {"status": "partial"},
                "diagnostic_replay": {
                    "status": "skipped",
                    "next_action": "accumulate_replay_simulation_shared_opra_dates",
                },
                "replay": {"error": "Selected dates: 1."},
                "exact_history_acquisition_plan": {
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                    },
                    "unlock_milestones": {
                        "diagnostic_replay": {
                            "unlock_trade_date": "2026-09-24",
                            "not_before_user_local": "2026-09-24T14:20:00-06:00",
                            "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-09-24",
                        },
                        "full_exact_replay": {
                            "unlock_trade_date": "2026-10-12",
                            "not_before_user_local": "2026-10-12T14:20:00-06:00",
                            "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-10-12",
                        },
                    },
                },
                "post_fresh_scan_research_backlog": {
                    "unlock_status": "locked_until_exact_replay_can_measure_filter_changes",
                    "activation_blockers": ["enough_exact_shared_quote_dates"],
                },
            }
        )

        self.assertEqual(contract["status"], "waiting_for_diagnostic_replay_history")
        self.assertFalse(contract["diagnostic_replay_unlocked"])
        self.assertFalse(contract["full_exact_replay_unlocked"])
        self.assertEqual(contract["diagnostic_remaining_shared_quote_dates"], 87)
        self.assertEqual(contract["full_remaining_shared_quote_dates"], 99)
        self.assertEqual(contract["diagnostic_unlock_trade_date"], "2026-09-24")
        self.assertEqual(contract["full_unlock_trade_date"], "2026-10-12")
        self.assertIn("diagnostic_replay_waiting_for_exact_opra_history_depth", contract["blockers"])
        self.assertEqual(contract["next_action"], "continue_forward_daily_alpaca_opra_capture")
        self.assertEqual(
            contract["immediate_next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(contract["readiness_checklist_status"], "waiting_for_exact_opra_history_depth")
        self.assertFalse(contract["ready_to_run_full_exact_replay"])
        self.assertIn("full_exact_replay_history_depth_available", contract["readiness_checklist_blockers"])
        self.assertIn("do_not_tune_production_filters", contract["prohibited_actions_before_full_unlock"])

    def test_build_exact_replay_smoke_probe_plan_available_after_two_exact_opra_dates(self):
        plan = build_exact_replay_smoke_probe_plan(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
            }
        )

        self.assertEqual(plan["status"], "available_non_verifying_exact_replay_smoke_probe")
        self.assertFalse(plan["used_for_goal_verification"])
        self.assertFalse(plan["counts_for_exact_replay_profitability_gate"])
        self.assertEqual(
            plan["non_verification_policy"],
            "smoke_probe_never_satisfies_exact_replay_profitability_gate",
        )
        self.assertEqual(plan["smoke_min_shared_quote_dates"], 2)
        self.assertEqual(
            plan["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan --min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json",
        )
        self.assertEqual(plan["command_role"], "non_verifying_exact_replay_wiring_probe")
        self.assertEqual(plan["blockers"], [])
        self.assertIn(
            "exact_replay_unlock_contract.exact_replay_profitability_verified remains false",
            plan["material_progress_if"],
        )
        self.assertFalse(plan["latest_observation"]["used_for_goal_verification"])

    def test_build_exact_replay_smoke_zero_trade_diagnostic_marks_calendar_runway_shortfall(self):
        diagnostic = build_exact_replay_smoke_zero_trade_diagnostic(
            {
                "proof_window": {
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
                "replay": {
                    "total_days": 0,
                    "candidate_trade_count": 0,
                    "priced_trade_count": 0,
                    "unpriced_trade_count": 0,
                    "post_entry_filtered_trade_count": 0,
                    "total_trades": 0,
                    "quote_coverage_pct": 0.0,
                    "replay_calendar": {
                        "selected_date_count": 2,
                        "shared_quote_date_count": 2,
                        "start_date": "2026-05-20",
                        "end_date": "2026-05-21",
                    },
                },
            }
        )

        self.assertEqual(
            diagnostic["primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertEqual(diagnostic["minimum_selected_dates_for_first_entry"], 58)
        self.assertEqual(diagnostic["selected_dates_shortfall_to_first_entry"], 56)
        self.assertEqual(diagnostic["diagnostic_replay_required_shared_quote_dates"], 88)
        self.assertEqual(diagnostic["selected_dates_shortfall_to_diagnostic_replay"], 86)
        self.assertIn("smoke_probe_replay_days_zero", diagnostic["blockers"])
        self.assertIn("smoke_probe_selected_dates_below_first_entry_runway", diagnostic["blockers"])

    def test_build_exact_replay_smoke_probe_observation_marks_zero_trades_non_verifying(self):
        observation = build_exact_replay_smoke_probe_observation(
            {
                "generated_at": "2026-05-22T02:37:19Z",
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 2,
                },
                "replay": {
                    "error": None,
                    "total_days": 0,
                    "candidate_trade_count": 0,
                    "total_trades": 0,
                    "profit_factor": 0.0,
                    "total_return_pct": None,
                    "replay_calendar": {
                        "selected_date_count": 2,
                        "shared_quote_date_count": 2,
                    },
                },
                "exact_replay_unlock_contract": {
                    "exact_replay_profitability_verified": False,
                },
            },
            min_shared_quote_dates=2,
            command=(
                "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan "
                "--min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json"
            ),
            observed_at_utc=datetime(2026, 5, 22, 2, 40, tzinfo=UTC),
        )

        self.assertEqual(observation["status"], "zero_trades_insufficient_replay_calendar_runway")
        self.assertTrue(observation["material_progress"])
        self.assertFalse(observation["goal_requirement_advanced"])
        self.assertFalse(observation["used_for_goal_verification"])
        self.assertFalse(observation["counts_for_exact_replay_profitability_gate"])
        self.assertFalse(observation["exact_replay_profitability_verified"])
        self.assertIn("smoke_probe_zero_trades", observation["blockers"])
        self.assertIn("smoke_probe_selected_dates_below_first_entry_runway", observation["blockers"])
        self.assertEqual(
            observation["zero_trade_primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertEqual(observation["selected_dates_shortfall_to_first_entry"], 56)
        self.assertEqual(
            observation["non_verification_policy"],
            "smoke_probe_never_satisfies_exact_replay_profitability_gate",
        )

    def test_write_and_load_exact_replay_smoke_probe_observation_keeps_non_verifying_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            observation = build_exact_replay_smoke_probe_observation(
                {
                    "generated_at": "2026-05-22T02:37:19Z",
                    "provider": "alpaca:sip:opra",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_window": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "current_shared_quote_dates": 2,
                        "required_shared_quote_dates": 2,
                    },
                    "replay": {
                        "error": None,
                        "total_days": 0,
                        "candidate_trade_count": 0,
                        "total_trades": 0,
                        "profit_factor": 0.0,
                        "total_return_pct": None,
                    },
                },
                min_shared_quote_dates=2,
                command="python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan --min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json",
                observed_at_utc=datetime(2026, 5, 22, 2, 40, tzinfo=UTC),
            )

            artifacts = write_exact_replay_smoke_probe_observation(observation, Path(tmp))
            loaded = load_latest_exact_replay_smoke_probe_observation(Path(tmp))

            self.assertTrue(Path(artifacts["json"]).exists())
            self.assertTrue(Path(artifacts["latest_json"]).exists())
            self.assertTrue(loaded["present"])
            self.assertEqual(loaded["status"], "zero_trades_insufficient_replay_calendar_runway")
            self.assertEqual(loaded["replay_total_trades"], 0)
            self.assertEqual(loaded["replay_total_days"], 0)
            self.assertEqual(
                loaded["zero_trade_primary_cause"],
                "insufficient_selected_quote_dates_for_replay_start_index",
            )
            self.assertFalse(loaded["used_for_goal_verification"])
            self.assertFalse(loaded["counts_for_exact_replay_profitability_gate"])

    def test_build_exact_replay_smoke_probe_plan_loads_latest_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            observation = build_exact_replay_smoke_probe_observation(
                {
                    "generated_at": "2026-05-22T02:37:19Z",
                    "provider": "alpaca:sip:opra",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_window": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "current_shared_quote_dates": 2,
                        "required_shared_quote_dates": 2,
                    },
                    "replay": {
                        "error": None,
                        "total_days": 0,
                        "candidate_trade_count": 0,
                        "total_trades": 0,
                        "profit_factor": 0.0,
                    },
                },
                min_shared_quote_dates=2,
                command="python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan --min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json",
                observed_at_utc=datetime(2026, 5, 22, 2, 40, tzinfo=UTC),
            )
            write_exact_replay_smoke_probe_observation(observation, Path(tmp))

            plan = build_exact_replay_smoke_probe_plan(
                {
                    "provider": "alpaca:sip:opra",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_window": {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "current_shared_quote_dates": 2,
                        "required_shared_quote_dates": 100,
                    },
                },
                output_dir=Path(tmp),
            )

            self.assertEqual(
                plan["latest_observation_status"],
                "zero_trades_insufficient_replay_calendar_runway",
            )
            self.assertEqual(plan["latest_observation_replay_total_trades"], 0)
            self.assertEqual(plan["latest_observation_replay_total_days"], 0)
            self.assertEqual(
                plan["latest_observation_zero_trade_primary_cause"],
                "insufficient_selected_quote_dates_for_replay_start_index",
            )
            self.assertFalse(plan["latest_observation_used_for_goal_verification"])
            self.assertEqual(
                plan["last_manual_probe_observation"]["status"],
                "zero_trades_insufficient_replay_calendar_runway",
            )

    def test_build_exact_replay_runway_progress_contract_tracks_first_entry_shortfall(self):
        contract = build_exact_replay_runway_progress_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                    "next_missing_capture_trade_date": "2026-05-22",
                },
                "exact_history_acquisition_plan": {
                    "next_capture_trade_date": "2026-05-22",
                    "next_capture_command": (
                        "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
                    ),
                    "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
                },
                "exact_replay_smoke_probe_plan": {
                    "latest_observation_status": "zero_trades_insufficient_replay_calendar_runway",
                    "latest_observation_zero_trade_primary_cause": (
                        "insufficient_selected_quote_dates_for_replay_start_index"
                    ),
                    "latest_observation_selected_dates_shortfall_to_first_entry": 56,
                    "latest_observation_selected_dates_shortfall_to_diagnostic_replay": 86,
                },
            }
        )

        self.assertEqual(contract["status"], "waiting_for_first_replay_entry_runway")
        self.assertEqual(contract["current_shared_quote_dates"], 2)
        self.assertEqual(contract["minimum_selected_dates_for_first_entry"], 58)
        self.assertEqual(contract["diagnostic_required_shared_quote_dates"], 88)
        self.assertEqual(contract["full_required_shared_quote_dates"], 100)
        self.assertEqual(contract["shortfall_to_first_entry"], 56)
        self.assertEqual(contract["shortfall_to_diagnostic_replay"], 86)
        self.assertEqual(contract["shortfall_to_full_exact_replay"], 98)
        self.assertEqual(contract["expected_after_next_capture"]["shared_quote_dates"], 3)
        self.assertEqual(contract["expected_after_next_capture"]["shortfall_to_first_entry"], 55)
        self.assertFalse(contract["first_entry_unlocked_after_next_capture"])
        self.assertEqual(
            contract["latest_smoke_zero_trade_primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertEqual(
            contract["next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
        )
        self.assertEqual(
            contract["no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertIn("first_replay_entry_shared_quote_dates:2/58", contract["blockers"])

    def test_build_exact_replay_runway_progress_contract_transitions_by_history_depth(self):
        base = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "exact_history_acquisition_plan": {
                "next_capture_command": (
                    "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
                ),
            },
        }

        first_entry_ready = build_exact_replay_runway_progress_contract(
            {
                **base,
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 58,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
            }
        )
        diagnostic_ready = build_exact_replay_runway_progress_contract(
            {
                **base,
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 88,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
            }
        )
        full_ready = build_exact_replay_runway_progress_contract(
            {
                **base,
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
            }
        )

        self.assertEqual(first_entry_ready["status"], "waiting_for_diagnostic_replay_runway")
        self.assertTrue(first_entry_ready["first_entry_unlocked"])
        self.assertFalse(first_entry_ready["diagnostic_replay_unlocked"])
        self.assertEqual(diagnostic_ready["status"], "waiting_for_full_exact_replay_runway")
        self.assertTrue(diagnostic_ready["diagnostic_replay_unlocked"])
        self.assertFalse(diagnostic_ready["full_exact_replay_unlocked"])
        self.assertEqual(full_ready["status"], "full_exact_replay_runway_ready")
        self.assertTrue(full_ready["full_exact_replay_unlocked"])
        self.assertEqual(full_ready["shortfall_to_full_exact_replay"], 0)
        self.assertEqual(full_ready["next_action"], "run_full_exact_replay_profitability_gate")

    def test_build_next_profitability_evidence_sequence_orders_fresh_scan_capture_and_replay(self):
        runway = {
            "status": "waiting_for_first_replay_entry_runway",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "current_shared_quote_dates": 2,
            "shortfall_to_first_entry": 56,
            "shortfall_to_diagnostic_replay": 86,
            "shortfall_to_full_exact_replay": 98,
            "expected_after_next_capture": {
                "shared_quote_dates": 3,
                "shortfall_to_first_entry": 55,
                "shortfall_to_diagnostic_replay": 85,
                "shortfall_to_full_exact_replay": 97,
            },
            "full_exact_replay_unlocked": False,
            "blockers": ["first_replay_entry_shared_quote_dates:2/58"],
            "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        }
        sequence = build_next_profitability_evidence_sequence(
            {
                "provider": "alpaca:sip:opra",
                "verification_gate": {"verified": False},
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "next_missing_capture_trade_date": "2026-05-22",
                },
                "exact_replay_runway_progress": runway,
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "next_capture_trade_date": "2026-05-22",
                    "next_capture_command": (
                        "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
                    ),
                    "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
                },
                "raw_drop_reason_evidence_contract": {
                    "status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
                    "target_goal_requirement": "live_scan_has_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "post_run_success_statuses": [
                        "raw_drop_reasons_recorded_zero_candidate_reviewable"
                    ],
                    "post_run_fields_to_compare": [
                        "raw_drop_reason_evidence_status",
                        "scan_drop_reason_count",
                    ],
                    "material_progress_if": ["scan.scan_drop_reason_count > 0"],
                    "post_run_still_blocked_if": ["scan_drop_reason_count is null or <= 0"],
                    "no_mutation_guard": (
                        "production_filters_preserved_until_exact_alpaca_opra_replay_unlock"
                    ),
                },
                "guarded_command_decision": {
                    "status": "waiting_until_next_guarded_event",
                    "safe_to_execute_now": False,
                },
            }
        )

        self.assertEqual(sequence["status"], "waiting_for_next_profitability_evidence_event")
        self.assertEqual(sequence["event_count"], 3)
        self.assertEqual(sequence["events"][0]["event_kind"], "fresh_scan_raw_drop_reason_audit")
        self.assertFalse(sequence["events"][0]["counts_for_exact_profitability_proof"])
        self.assertEqual(sequence["events"][1]["event_kind"], "exact_opra_forward_capture")
        self.assertTrue(sequence["events"][1]["counts_for_exact_profitability_proof"])
        self.assertEqual(sequence["events"][1]["expected_shared_quote_dates_after_run"], 3)
        self.assertEqual(
            sequence["events"][1]["expected_runway_shortfalls_after_run"]["full_exact_replay"],
            97,
        )
        self.assertEqual(sequence["events"][2]["event_kind"], "full_exact_replay_profitability_gate")
        self.assertEqual(sequence["events"][2]["status"], "locked_until_full_exact_replay_runway_ready")
        self.assertEqual(sequence["next_event_kind"], "fresh_scan_raw_drop_reason_audit")
        self.assertEqual(
            sequence["next_event_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            sequence["next_event_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )

    def test_build_profitability_evidence_scorecard_records_blockers_and_scoring_rules(self):
        scorecard = build_profitability_evidence_scorecard(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {
                    "verified": False,
                    "gates": {"exact_replay_completed": False},
                    "replay_total_trades": 0,
                    "replay_profit_factor": None,
                    "replay_total_return_pct": None,
                },
                "scan": {
                    "candidate_count": 0,
                    "scan_drop_reason_audit_status": None,
                    "scan_drop_reason_count": 0,
                },
                "alpaca_opra_data_usage_audit": {
                    "status": "using_alpaca_opra_daily_snapshot_waiting_for_history_depth",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_window_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "blockers": [],
                },
                "exact_replay_runway_progress": {
                    "status": "waiting_for_first_replay_entry_runway",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "full_required_shared_quote_dates": 100,
                    "shortfall_to_first_entry": 56,
                    "shortfall_to_diagnostic_replay": 86,
                    "shortfall_to_full_exact_replay": 98,
                    "blockers": ["first_replay_entry_shared_quote_dates:2/58"],
                },
                "next_profitability_evidence_sequence": {
                    "next_event_kind": "fresh_scan_raw_drop_reason_audit",
                    "next_event_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "next_event_not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "next_event_no_mutation_guard": (
                        "production_filters_preserved_until_exact_alpaca_opra_replay_unlock"
                    ),
                },
                "guarded_command_decision": {
                    "status": "waiting_until_next_guarded_event",
                    "action": "wait_until_not_before",
                    "safe_to_execute_now": False,
                    "next_command_when_allowed": (
                        "python scripts/run_ai_commodity_opra_progress.py --skip-capture"
                    ),
                    "next_not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "reason": "waiting_until_not_before:2026-05-22T08:10:00-06:00",
                },
                "exact_replay_smoke_probe_plan": {
                    "latest_observation_status": "zero_trades_insufficient_replay_calendar_runway",
                    "latest_observation_observed_at_utc": "2026-05-22T03:54:11Z",
                    "latest_observation_replay_total_trades": 0,
                    "latest_observation_zero_trade_primary_cause": (
                        "insufficient_selected_quote_dates_for_replay_start_index"
                    ),
                    "latest_observation_selected_dates_shortfall_to_first_entry": 56,
                    "latest_observation_selected_dates_shortfall_to_diagnostic_replay": 86,
                    "latest_observation": {
                        "material_progress": True,
                        "material_progress_reason": "replay_path_wiring_cleared",
                        "replay_error": None,
                        "observed_at_utc": "2026-05-22T03:54:11Z",
                    },
                },
                "raw_drop_reason_evidence_contract": {
                    "status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
                },
            }
        )

        self.assertEqual(scorecard["status"], "recording_progress_waiting_for_exact_history_depth")
        self.assertEqual(scorecard["passed_requirement_count"], 2)
        self.assertEqual(scorecard["total_requirement_count"], 9)
        self.assertEqual(scorecard["current_shared_quote_dates"], 2)
        self.assertIn("alpaca_opra_daily_snapshot_shared_quote_dates:2/100", scorecard["blockers"])
        self.assertIn("first_replay_entry_runway_not_ready", scorecard["blockers"])
        self.assertIn("live_scan_zero_candidates_without_raw_drop_reasons", scorecard["blockers"])
        self.assertEqual(scorecard["next_evidence_event_kind"], "fresh_scan_raw_drop_reason_audit")
        self.assertEqual(scorecard["next_evidence_event_readiness"]["status"], "waiting_until_not_before")
        self.assertTrue(scorecard["next_evidence_event_readiness"]["command_matches_guarded_command"])
        self.assertFalse(scorecard["next_evidence_event_readiness"]["safe_to_execute_now"])
        self.assertEqual(
            scorecard["next_evidence_event_readiness"]["guarded_command_decision_action"],
            "wait_until_not_before",
        )
        self.assertEqual(
            scorecard["next_evidence_event_readiness"]["post_event_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["readback_projection_shell"],
            "powershell",
        )
        self.assertIn(
            "$r = python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
            scorecard["post_event_readback_packet"]["readback_projection_command"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status = $r.profitability_evidence_scorecard_delta_status",
            scorecard["post_event_readback_packet"]["readback_projection_command"],
        )
        self.assertIn(
            (
                "profitability_evidence_scorecard_delta_baseline_comparison_status = "
                "$r.profitability_evidence_scorecard_delta_baseline_comparison_status"
            ),
            scorecard["post_event_readback_packet"]["readback_projection_command"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status is not null",
            scorecard["post_event_readback_packet"]["readback_projection_success_criteria"],
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["baseline_compare_policy"],
            "compare_projection_after_guarded_event_against_baseline_snapshot",
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["baseline_snapshot"][
                "alpaca_opra_data_usage_proof_window_shared_quote_dates"
            ],
            2,
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["baseline_snapshot"][
                "profitability_evidence_scorecard_passed_requirement_count"
            ],
            2,
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["baseline_snapshot"][
                "guarded_command_decision_next_command_when_allowed"
            ],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertIn(
            "profitability_evidence_scorecard_status",
            scorecard["post_event_readback_packet"]["baseline_snapshot_fields"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_status",
            scorecard["post_event_readback_packet"]["readback_fields"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_assertion_results",
            scorecard["post_event_readback_packet"]["readback_field_groups"]["scorecard_delta"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_condition_results",
            scorecard["post_event_readback_packet"]["readback_fields"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_condition_results",
            scorecard["post_event_readback_packet"]["readback_projection_command"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_detected is not null",
            scorecard["post_event_readback_packet"]["readback_projection_success_criteria"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_baseline_comparison_no_progress_detected",
            scorecard["post_event_readback_packet"]["readback_field_groups"]["scorecard_delta"],
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["baseline_comparison_assertions"][0],
            {
                "field": "raw_drop_reason_evidence_requirement_satisfied_by",
                "baseline": None,
                "material_progress_if": "after in requirement_success_reasons",
                "goal_requirement": "live_scan_has_candidate_or_raw_drop_reasons",
            },
        )
        self.assertIn(
            "raw_drop_reason_evidence_requirement_satisfied_by",
            scorecard["post_event_readback_packet"]["readback_fields"],
        )
        self.assertIn(
            "raw_drop_reason_evidence_requirement_satisfied_by",
            scorecard["post_event_readback_packet"]["readback_field_groups"][
                "fresh_scan_or_drop_reasons"
            ],
        )
        self.assertIn(
            "raw_drop_reason_evidence_requirement_satisfied_by is null",
            scorecard["post_event_readback_packet"]["baseline_no_progress_conditions"],
        )
        self.assertIn(
            "raw_drop_reason_evidence_status not in post_run_success_statuses",
            scorecard["post_event_readback_packet"]["baseline_no_progress_conditions"],
        )
        self.assertEqual(scorecard["post_event_readback_packet"]["status"], "waiting_until_not_before")
        self.assertIn(
            "alpaca_opra_data_usage_proof_window_shared_quote_dates",
            scorecard["post_event_readback_packet"]["readback_fields"],
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status",
            scorecard["post_event_readback_packet"]["readback_fields"],
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["readback_field_groups"]["guard"],
            [
                "guarded_command_decision_status",
                "guarded_command_decision_action",
                "guarded_command_decision_safe_to_execute_now",
                "guarded_command_decision_command",
                "guarded_command_decision_next_command_when_allowed",
            ],
        )
        self.assertEqual(
            scorecard["post_event_readback_packet"]["no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertFalse(
            scorecard["non_verifying_replay_wiring_probe"]["counts_for_exact_replay_profitability_gate"]
        )
        self.assertEqual(
            scorecard["non_verifying_replay_wiring_probe"]["zero_trade_primary_cause"],
            "insufficient_selected_quote_dates_for_replay_start_index",
        )
        self.assertEqual(
            scorecard["post_event_scoring_rules"]["exact_opra_forward_capture"]["fields_to_compare"],
            [
                "alpaca_opra_data_usage_proof_window_shared_quote_dates",
                "exact_replay_runway_shortfall_to_first_entry",
                "exact_replay_runway_shortfall_to_diagnostic_replay",
                "exact_replay_runway_shortfall_to_full_exact_replay",
            ],
        )

    def test_build_profitability_evidence_scorecard_requires_verifiable_live_candidate(self):
        base_report = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "verification_gate": {
                "verified": False,
                "gates": {
                    "exact_replay_completed": False,
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
                "replay_total_trades": 0,
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
            },
            "scan": {
                "candidate_count": 1,
                "candidate_symbols": ["CCJ"],
                "scan_drop_reason_audit_status": None,
                "scan_drop_reason_count": 0,
            },
            "alpaca_opra_data_usage_audit": {
                "status": "using_alpaca_opra_daily_snapshot_waiting_for_history_depth",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "blockers": [],
            },
            "exact_replay_runway_progress": {
                "status": "waiting_for_first_replay_entry_runway",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "full_required_shared_quote_dates": 100,
                "shortfall_to_first_entry": 56,
                "shortfall_to_diagnostic_replay": 86,
                "shortfall_to_full_exact_replay": 98,
            },
            "raw_drop_reason_evidence_contract": {
                "status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
            },
        }

        scorecard = build_profitability_evidence_scorecard(base_report)
        live_row = next(
            row
            for row in scorecard["rows"]
            if row["requirement"] == "live_scan_candidate_or_raw_drop_reasons"
        )

        self.assertFalse(live_row["passed"])
        self.assertEqual(live_row["blocker"], "live_scan_candidate_not_inside_exact_proof_universe")
        self.assertEqual(live_row["actual"]["proof_eligible_candidate_count"], 1)
        self.assertEqual(live_row["actual"]["raw_candidate_count"], 1)
        self.assertTrue(live_row["actual"]["live_scan_has_candidate_gate"])
        self.assertFalse(live_row["actual"]["live_scan_candidate_inside_exact_proof_gate"])

        verified_report = {
            **base_report,
            "verification_gate": {
                **base_report["verification_gate"],
                "gates": {
                    **base_report["verification_gate"]["gates"],
                    "live_scan_candidate_inside_exact_proof_universe": True,
                },
            },
        }
        verified_scorecard = build_profitability_evidence_scorecard(verified_report)
        verified_live_row = next(
            row
            for row in verified_scorecard["rows"]
            if row["requirement"] == "live_scan_candidate_or_raw_drop_reasons"
        )

        self.assertTrue(verified_live_row["passed"])
        self.assertIsNone(verified_live_row["blocker"])
        self.assertTrue(verified_live_row["actual"]["live_scan_candidate_inside_exact_proof_gate"])

    def test_build_profitability_evidence_scorecard_rejects_custom_proof_scope(self):
        scorecard = build_profitability_evidence_scorecard(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {
                    "verified": False,
                    "gates": {
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                        "exact_replay_profit_factor_positive": True,
                        "exact_replay_total_return_positive": True,
                        "live_scan_has_candidate": True,
                        "live_scan_candidate_inside_exact_proof_universe": True,
                        "capture_scope_full_scan_universe": False,
                        "proof_scan_universe_aligned": True,
                    },
                    "replay_total_trades": 12,
                    "replay_profit_factor": 1.25,
                    "replay_total_return_pct": 8.4,
                },
                "scan": {
                    "candidate_count": 1,
                    "candidate_symbols": ["FCX"],
                    "proof_eligible_candidate_count": 1,
                    "proof_eligible_candidate_symbols": ["FCX"],
                },
                "capture": {"scope": "custom_symbols", "symbol_count": 9},
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                },
                "alpaca_opra_data_usage_audit": {
                    "status": "using_alpaca_opra_daily_snapshot",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_window_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "blockers": [],
                },
                "exact_replay_runway_progress": {
                    "status": "full_exact_replay_runway_ready",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 100,
                    "full_required_shared_quote_dates": 100,
                    "shortfall_to_first_entry": 0,
                    "shortfall_to_diagnostic_replay": 0,
                    "shortfall_to_full_exact_replay": 0,
                },
            }
        )

        scope_row = next(
            row for row in scorecard["rows"] if row["requirement"] == "full_scan_universe_proof_scope"
        )

        self.assertNotEqual(scorecard["status"], "verified_profitable")
        self.assertFalse(scope_row["passed"])
        self.assertEqual(scope_row["actual"]["capture_scope"], "custom_symbols")
        self.assertIn("full_scan_universe_proof_scope_not_satisfied", scorecard["blockers"])

    def test_build_profitability_evidence_scorecard_delta_records_material_progress(self):
        previous = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "non_verifying_replay_wiring_probe": {
                    "status": "zero_trades_insufficient_replay_calendar_runway",
                    "observed_at_utc": "2026-05-22T02:40:00Z",
                    "material_progress": True,
                    "replay_error": None,
                },
                "blockers": [
                    "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    "first_replay_entry_runway_not_ready",
                    "live_scan_zero_candidates_without_raw_drop_reasons",
                ],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    },
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": False,
                        "blocker": "live_scan_zero_candidates_without_raw_drop_reasons",
                    },
                ],
            }
        }
        current = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 3,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 3,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "non_verifying_replay_wiring_probe": {
                    "status": "zero_trades_insufficient_replay_calendar_runway",
                    "observed_at_utc": "2026-05-22T03:54:11Z",
                    "material_progress": True,
                    "replay_error": None,
                },
                "blockers": [
                    "alpaca_opra_daily_snapshot_shared_quote_dates:3/100",
                    "first_replay_entry_runway_not_ready",
                ],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:3/100",
                    },
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": True,
                        "blocker": None,
                    },
                ],
            }
        }

        delta = build_profitability_evidence_scorecard_delta(previous, current)

        self.assertEqual(delta["status"], "improved")
        self.assertTrue(delta["material_progress"])
        self.assertTrue(delta["evidence_progress"])
        self.assertTrue(delta["material_evidence_progress"])
        self.assertFalse(delta["profit_improved"])
        self.assertIn("alpaca_opra_shared_quote_dates_increased", delta["evidence_progress_reasons"])
        self.assertEqual(delta["passed_requirement_count_before"], 2)
        self.assertEqual(delta["passed_requirement_count_after"], 3)
        self.assertEqual(delta["passed_requirement_count_delta"], 1)
        self.assertEqual(delta["current_shared_quote_dates_delta"], 1)
        self.assertIn("live_scan_zero_candidates_without_raw_drop_reasons", delta["blockers_removed"])
        self.assertIn("alpaca_opra_daily_snapshot_shared_quote_dates:3/100", delta["blockers_added"])
        self.assertTrue(delta["auxiliary_progress"])
        self.assertIn("non_verifying_replay_wiring_probe_refreshed", delta["auxiliary_progress_reasons"])
        self.assertEqual(
            delta["requirement_row_changes"][0]["requirement"],
            "live_scan_candidate_or_raw_drop_reasons",
        )
        self.assertEqual(
            delta["post_event_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )

    def test_build_profitability_evidence_scorecard_delta_splits_shared_date_evidence_from_profit(self):
        previous = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "verified": False,
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "blockers": [
                    "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    "exact_replay_profitability_not_verified",
                ],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    },
                    {
                        "requirement": "full_exact_replay_profitability",
                        "passed": False,
                        "actual": {
                            "completed": False,
                            "total_trades": 0,
                            "profit_factor": 0.8,
                            "total_return_pct": -4.0,
                        },
                        "blocker": "exact_replay_profitability_not_verified",
                    },
                ],
            }
        }
        current = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "verified": False,
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 3,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "blockers": [
                    "alpaca_opra_daily_snapshot_shared_quote_dates:3/100",
                    "exact_replay_profitability_not_verified",
                ],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:3/100",
                    },
                    {
                        "requirement": "full_exact_replay_profitability",
                        "passed": False,
                        "actual": {
                            "completed": False,
                            "total_trades": 0,
                            "profit_factor": 0.9,
                            "total_return_pct": -2.0,
                        },
                        "blocker": "exact_replay_profitability_not_verified",
                    },
                ],
            }
        }

        delta = build_profitability_evidence_scorecard_delta(previous, current)

        self.assertEqual(delta["status"], "improved")
        self.assertTrue(delta["material_progress"])
        self.assertTrue(delta["evidence_progress"])
        self.assertTrue(delta["material_evidence_progress"])
        self.assertIn("alpaca_opra_shared_quote_dates_increased", delta["evidence_progress_reasons"])
        self.assertFalse(delta["profit_improved"])
        self.assertFalse(delta["profitability_metrics_same_window"])
        self.assertEqual(delta["current_shared_quote_dates_delta"], 1)
        self.assertEqual(delta["passed_requirement_count_delta"], 0)

    def test_build_profitability_evidence_scorecard_delta_scores_prior_readback_baseline(self):
        previous = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "fresh_scan_raw_drop_reason_audit",
                "blockers": ["first_replay_entry_runway_not_ready"],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    }
                ],
                "post_event_readback_packet": {
                    "next_event_kind": "fresh_scan_raw_drop_reason_audit",
                    "baseline_compare_policy": (
                        "compare_projection_after_guarded_event_against_baseline_snapshot"
                    ),
                    "baseline_snapshot": {
                        "scan_candidate_count": 0,
                        "scan_drop_reason_count": 0,
                    },
                    "baseline_comparison_assertions": [
                        {
                            "field": "scan_drop_reason_count",
                            "baseline": 0,
                            "material_progress_if": "after > 0",
                            "goal_requirement": "live_scan_candidate_or_raw_drop_reasons",
                        }
                    ],
                    "baseline_no_progress_conditions": [
                        "scan_candidate_count <= baseline and scan_drop_reason_count is null_or_zero"
                    ],
                },
            }
        }
        current = {
            "scan_drop_reason_count": 3,
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "blockers": ["first_replay_entry_runway_not_ready"],
                "rows": [
                    {
                        "requirement": "required_exact_history_depth",
                        "passed": False,
                        "blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
                    }
                ],
            },
        }

        delta = build_profitability_evidence_scorecard_delta(previous, current)

        self.assertEqual(delta["status"], "improved")
        self.assertTrue(delta["material_progress"])
        self.assertEqual(delta["passed_requirement_count_delta"], 0)
        self.assertEqual(delta["current_shared_quote_dates_delta"], 0)
        self.assertTrue(delta["baseline_comparison_material_progress"])
        self.assertEqual(delta["baseline_comparison_status"], "material_progress")
        self.assertEqual(
            delta["baseline_comparison_evaluation"]["event_kind"],
            "fresh_scan_raw_drop_reason_audit",
        )
        self.assertEqual(
            delta["baseline_comparison_assertion_results"][0]["field"],
            "scan_drop_reason_count",
        )
        self.assertEqual(delta["baseline_comparison_assertion_results"][0]["after"], 3)
        self.assertTrue(delta["baseline_comparison_assertion_results"][0]["passed"])
        self.assertEqual(
            delta["baseline_comparison_no_progress_conditions"],
            [
                "scan_candidate_count <= baseline and scan_drop_reason_count is null_or_zero"
            ],
        )

    def test_build_profitability_evidence_scorecard_delta_scores_requirement_success_reason(self):
        previous = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "fresh_scan_raw_drop_reason_audit",
                "blockers": ["live_scan_zero_candidates_without_raw_drop_reasons"],
                "rows": [
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": False,
                        "blocker": "live_scan_zero_candidates_without_raw_drop_reasons",
                    }
                ],
                "post_event_readback_packet": {
                    "next_event_kind": "fresh_scan_raw_drop_reason_audit",
                    "baseline_snapshot": {
                        "raw_drop_reason_evidence_requirement_satisfied_by": None,
                    },
                    "baseline_comparison_assertions": [
                        {
                            "field": "raw_drop_reason_evidence_requirement_satisfied_by",
                            "baseline": None,
                            "material_progress_if": "after in requirement_success_reasons",
                            "goal_requirement": "live_scan_candidate_or_raw_drop_reasons",
                        }
                    ],
                    "baseline_no_progress_conditions": [
                        "raw_drop_reason_evidence_requirement_satisfied_by is null"
                    ],
                },
            }
        }
        current = {
            "raw_drop_reason_evidence_requirement_satisfied_by": "live_candidate_verified",
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "exact_opra_forward_capture",
                "blockers": ["first_replay_entry_runway_not_ready"],
                "rows": [
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": True,
                        "blocker": None,
                    }
                ],
            },
        }

        delta = build_profitability_evidence_scorecard_delta(previous, current)

        self.assertEqual(delta["status"], "improved")
        self.assertTrue(delta["baseline_comparison_material_progress"])
        self.assertEqual(delta["baseline_comparison_status"], "material_progress")
        self.assertEqual(
            delta["baseline_comparison_assertion_results"][0]["after"],
            "live_candidate_verified",
        )
        self.assertTrue(delta["baseline_comparison_assertion_results"][0]["passed"])

    def test_build_profitability_evidence_scorecard_delta_evaluates_no_progress_conditions(self):
        previous = {
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "fresh_scan_raw_drop_reason_audit",
                "blockers": ["live_scan_zero_candidates_without_raw_drop_reasons"],
                "rows": [
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": False,
                        "blocker": "live_scan_zero_candidates_without_raw_drop_reasons",
                    }
                ],
                "post_event_readback_packet": {
                    "next_event_kind": "fresh_scan_raw_drop_reason_audit",
                    "baseline_snapshot": {
                        "scan_candidate_count": 0,
                        "raw_drop_reason_evidence_requirement_satisfied_by": None,
                    },
                    "baseline_comparison_assertions": [
                        {
                            "field": "raw_drop_reason_evidence_requirement_satisfied_by",
                            "baseline": None,
                            "material_progress_if": "after in requirement_success_reasons",
                            "goal_requirement": "live_scan_candidate_or_raw_drop_reasons",
                        }
                    ],
                    "baseline_no_progress_conditions": [
                        "raw_drop_reason_evidence_requirement_satisfied_by is null",
                        "scan_candidate_count > 0 but live candidate proof-universe gates are not both true",
                        "raw_drop_reason_evidence_status not in post_run_success_statuses",
                    ],
                },
            }
        }
        current = {
            "scan_candidate_count": 1,
            "raw_drop_reason_evidence_status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
            "raw_drop_reason_evidence_requirement_satisfied_by": None,
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                }
            },
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "replay_runway_status": "waiting_for_first_replay_entry_runway",
                "next_evidence_event_kind": "fresh_scan_raw_drop_reason_audit",
                "blockers": ["live_scan_candidate_not_inside_exact_proof_universe"],
                "rows": [
                    {
                        "requirement": "live_scan_candidate_or_raw_drop_reasons",
                        "passed": False,
                        "blocker": "live_scan_candidate_not_inside_exact_proof_universe",
                    }
                ],
            },
        }

        delta = build_profitability_evidence_scorecard_delta(previous, current)

        self.assertEqual(delta["baseline_comparison_status"], "no_material_progress")
        self.assertFalse(delta["baseline_comparison_material_progress"])
        self.assertTrue(delta["baseline_comparison_no_progress_detected"])
        matched_conditions = {
            result["condition"]
            for result in delta["baseline_comparison_no_progress_condition_results"]
            if result["matched"] is True
        }
        self.assertIn(
            "raw_drop_reason_evidence_requirement_satisfied_by is null",
            matched_conditions,
        )
        self.assertIn(
            "scan_candidate_count > 0 but live candidate proof-universe gates are not both true",
            matched_conditions,
        )
        self.assertIn(
            "raw_drop_reason_evidence_status not in post_run_success_statuses",
            matched_conditions,
        )
        candidate_gate_result = next(
            result
            for result in delta["baseline_comparison_no_progress_condition_results"]
            if result["condition"]
            == "scan_candidate_count > 0 but live candidate proof-universe gates are not both true"
        )
        self.assertEqual(candidate_gate_result["current"]["scan_candidate_count"], 1.0)
        self.assertFalse(candidate_gate_result["current"]["live_scan_candidate_inside_exact_proof_gate"])

    def test_compact_summary_and_markdown_include_exact_replay_runway_progress(self):
        report = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "diagnostic_required_shared_quote_dates": 88,
                "next_missing_capture_trade_date": "2026-05-22",
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "trusted_only": True,
                "proof_source_shared_quote_dates": {"count": 2},
                "all_required_symbols_have_proof_source_data": True,
            },
            "exact_history_acquisition_plan": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "diagnostic_required_shared_quote_dates": 88,
                "next_capture_command": (
                    "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22"
                ),
                "next_capture_not_before_user_local": "2026-05-22T14:20:00-06:00",
            },
            "exact_replay_smoke_probe_plan": {
                "latest_observation_status": "zero_trades_insufficient_replay_calendar_runway",
                "latest_observation_zero_trade_primary_cause": (
                    "insufficient_selected_quote_dates_for_replay_start_index"
                ),
            },
            "raw_drop_reason_evidence_contract": {
                "status": "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_user_local": "2026-05-22T08:10:00-06:00",
                "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
            },
            "guarded_command_decision": {
                "status": "waiting_until_next_guarded_event",
                "action": "wait_until_not_before",
                "safe_to_execute_now": False,
                "next_command_when_allowed": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "next_not_before_user_local": "2026-05-22T08:10:00-06:00",
            },
        }

        summary = build_compact_progress_summary(report)
        markdown = render_markdown(report)

        self.assertEqual(summary["exact_replay_runway_status"], "waiting_for_first_replay_entry_runway")
        self.assertEqual(summary["exact_replay_runway_shortfall_to_first_entry"], 56)
        self.assertEqual(
            summary["exact_replay_runway_expected_after_next_capture"]["shared_quote_dates"],
            3,
        )
        self.assertEqual(
            summary["next_profitability_evidence_next_event_kind"],
            "fresh_scan_raw_drop_reason_audit",
        )
        self.assertEqual(
            summary["next_profitability_evidence_next_event_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_status"],
            "recording_progress_waiting_for_exact_history_depth",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_next_evidence_event_kind"],
            "fresh_scan_raw_drop_reason_audit",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_next_evidence_event_readiness"]["status"],
            "waiting_until_not_before",
        )
        self.assertTrue(summary["profitability_evidence_scorecard_next_evidence_event_command_matches_guard"])
        self.assertFalse(summary["profitability_evidence_scorecard_next_evidence_event_safe_to_execute_now"])
        self.assertEqual(
            summary["profitability_evidence_scorecard_next_evidence_event_guarded_action"],
            "wait_until_not_before",
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status",
            summary["profitability_evidence_scorecard_readback_fields"],
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_readback_projection_shell"],
            "powershell",
        )
        self.assertIn(
            "ConvertTo-Json -Depth 6",
            summary["profitability_evidence_scorecard_readback_projection_command"],
        )
        self.assertIn(
            "guarded_command_decision_status is not null",
            summary["profitability_evidence_scorecard_readback_projection_success_criteria"],
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_readback_baseline_snapshot"][
                "alpaca_opra_data_usage_proof_window_shared_quote_dates"
            ],
            2,
        )
        self.assertIn(
            "profitability_evidence_scorecard_status",
            summary["profitability_evidence_scorecard_readback_baseline_snapshot_fields"],
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_readback_baseline_compare_policy"],
            "compare_projection_after_guarded_event_against_baseline_snapshot",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_readback_baseline_comparison_assertions"][0][
                "field"
            ],
            "raw_drop_reason_evidence_requirement_satisfied_by",
        )
        self.assertIn(
            "raw_drop_reason_evidence_requirement_satisfied_by is null",
            summary["profitability_evidence_scorecard_readback_baseline_no_progress_conditions"],
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_post_event_readback_packet"]["status"],
            "waiting_until_not_before",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_delta_status"],
            "baseline_no_previous_scorecard",
        )
        self.assertEqual(
            summary["profitability_evidence_scorecard_delta_baseline_comparison_status"],
            "no_previous_scorecard_baseline",
        )
        self.assertFalse(
            summary[
                "profitability_evidence_scorecard_delta_baseline_comparison_material_progress"
            ]
        )
        self.assertEqual(summary["profitability_evidence_scorecard_delta_current_shared_quote_dates_after"], 2)
        self.assertIn("## Exact Replay Runway Progress", markdown)
        self.assertIn("Shortfall to first replay entry: `56`", markdown)
        self.assertIn("## Next Profitability Evidence Sequence", markdown)
        self.assertIn("Next event kind: `fresh_scan_raw_drop_reason_audit`", markdown)
        self.assertIn("## Profitability Evidence Scorecard", markdown)
        self.assertIn("Status: `recording_progress_waiting_for_exact_history_depth`", markdown)
        self.assertIn("Next evidence event readiness:", markdown)
        self.assertIn("Post-event readback packet:", markdown)
        self.assertIn("Non-verifying replay wiring probe:", markdown)
        self.assertIn("## Profitability Evidence Scorecard Delta", markdown)
        self.assertIn("Status: `baseline_no_previous_scorecard`", markdown)
        self.assertIn("Baseline comparison status: `no_previous_scorecard_baseline`", markdown)
        self.assertIn("Auxiliary progress:", markdown)
        self.assertIn(
            "Latest smoke zero-trade cause: `insufficient_selected_quote_dates_for_replay_start_index`",
            markdown,
        )

    def test_build_exact_replay_smoke_probe_plan_waits_for_two_exact_opra_dates(self):
        plan = build_exact_replay_smoke_probe_plan(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                },
            }
        )

        self.assertEqual(plan["status"], "waiting_for_at_least_two_exact_opra_dates")
        self.assertIsNone(plan["command"])
        self.assertIn("exact_opra_shared_dates_below_smoke_probe_minimum", plan["blockers"])
        self.assertFalse(plan["used_for_goal_verification"])

    def test_render_markdown_includes_non_verifying_exact_replay_smoke_probe_plan(self):
        markdown = render_markdown(
            {
                "generated_at": "2026-05-21T20:30:00Z",
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "verification_gate": {
                    "status": "not_verified",
                    "verified": False,
                    "gates": {
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                    },
                },
                "readiness": {"status": "partial"},
                "replay": {},
                "diagnostic_replay": {"status": "skipped"},
                "scan": {"candidate_count": 0},
                "exact_history_acquisition_plan": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
            }
        )

        self.assertIn("## Exact Replay Smoke Probe Plan", markdown)
        self.assertIn("Status: `available_non_verifying_exact_replay_smoke_probe`", markdown)
        self.assertIn("Used for goal verification: `False`", markdown)
        self.assertIn("Non-verification policy: `smoke_probe_never_satisfies_exact_replay_profitability_gate`", markdown)
        self.assertIn("--min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json", markdown)

    def test_build_compact_progress_summary_includes_exact_replay_smoke_probe_fields(self):
        summary = build_compact_progress_summary(
            {
                "generated_at": "2026-05-21T20:30:00Z",
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "verification_gate": {
                    "status": "not_verified",
                    "verified": False,
                    "gates": {
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                    },
                },
                "readiness": {"status": "partial"},
                "replay": {},
                "diagnostic_replay": {"status": "skipped"},
                "scan": {"candidate_count": 0},
                "exact_history_acquisition_plan": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                },
            }
        )

        self.assertEqual(
            summary["exact_replay_smoke_probe_status"],
            "available_non_verifying_exact_replay_smoke_probe",
        )
        self.assertEqual(
            summary["exact_replay_smoke_probe_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan --min-shared-quote-dates 2 --no-write --record-smoke-probe-observation --json",
        )
        self.assertFalse(summary["exact_replay_smoke_probe_used_for_goal_verification"])
        self.assertFalse(summary["exact_replay_smoke_probe_counts_for_exact_profitability_gate"])

    def test_build_exact_replay_readiness_checklist_separates_pre_replay_and_profitability_blockers(self):
        checklist = build_exact_replay_readiness_checklist(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "exact_history_acquisition_plan": {
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                    },
                },
                "verification_gate": {
                    "gates": {
                        "enough_exact_shared_quote_dates": True,
                        "readiness_ready_for_exact_replay": True,
                        "exact_replay_completed": False,
                        "exact_replay_has_trades": False,
                        "exact_replay_profit_factor_positive": False,
                        "exact_replay_total_return_positive": False,
                    }
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": "not run yet"},
            }
        )

        self.assertEqual(checklist["status"], "ready_to_run_full_exact_replay")
        self.assertTrue(checklist["ready_to_run_full_exact_replay"])
        self.assertEqual(checklist["pre_replay_blockers"], [])
        self.assertIn("exact_replay_completed", checklist["replay_blockers"])
        self.assertEqual(checklist["next_command"], "python scripts/run_ai_commodity_opra_progress.py")
        checks = {check["name"]: check for check in checklist["checks"]}
        self.assertTrue(checks["proof_source_isolation_clean"]["passed"])
        self.assertTrue(checks["capture_continuity_ok"]["passed"])

    def test_build_exact_replay_unlock_contract_allows_diagnostic_before_full_replay(self):
        contract = build_exact_replay_unlock_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 88,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "verification_gate": {
                    "gates": {
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                    }
                },
                "readiness": {"status": "partial"},
                "diagnostic_replay": {"status": "not_run"},
                "exact_history_acquisition_plan": {
                    "unlock_milestones": {
                        "diagnostic_replay": {"unlock_trade_date": "2026-09-24"},
                        "full_exact_replay": {"unlock_trade_date": "2026-10-12"},
                    },
                },
            }
        )

        self.assertEqual(contract["status"], "diagnostic_replay_unlocked_full_replay_pending")
        self.assertTrue(contract["diagnostic_replay_unlocked"])
        self.assertFalse(contract["full_exact_replay_unlocked"])
        self.assertEqual(contract["diagnostic_remaining_shared_quote_dates"], 0)
        self.assertEqual(contract["full_remaining_shared_quote_dates"], 12)
        self.assertNotIn("diagnostic_replay_waiting_for_exact_opra_history_depth", contract["blockers"])
        self.assertIn("full_exact_replay_waiting_for_exact_opra_history_depth", contract["blockers"])
        self.assertEqual(contract["next_action"], "run_diagnostic_replay_and_continue_forward_capture")

    def test_build_exact_replay_unlock_contract_marks_profitable_replay_verified(self):
        contract = build_exact_replay_unlock_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "diagnostic_required_shared_quote_dates": 88,
                },
                "verification_gate": {
                    "replay_profit_factor": 1.18,
                    "replay_total_return_pct": 4.2,
                    "replay_total_trades": 12,
                    "gates": {
                        "enough_exact_shared_quote_dates": True,
                        "readiness_ready_for_exact_replay": True,
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                        "exact_replay_profit_factor_positive": True,
                        "exact_replay_total_return_positive": True,
                    },
                },
                "exact_history_acquisition_plan": {
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                    },
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"profit_factor": 1.18, "total_return_pct": 4.2, "total_trades": 12},
            }
        )

        self.assertEqual(contract["status"], "exact_replay_profitability_verified")
        self.assertTrue(contract["diagnostic_replay_unlocked"])
        self.assertTrue(contract["full_exact_replay_unlocked"])
        self.assertTrue(contract["exact_replay_profitability_verified"])
        self.assertEqual(contract["diagnostic_remaining_shared_quote_dates"], 0)
        self.assertEqual(contract["full_remaining_shared_quote_dates"], 0)
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(contract["next_action"], "evaluate_goal_completion_verification_contract")
        self.assertEqual(contract["readiness_checklist_status"], "exact_replay_profitability_verified")
        self.assertTrue(contract["readiness_checklist"]["exact_replay_profitability_verified"])

    def test_refresh_derived_fields_from_latest_preserves_market_evidence(self):
        report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "alpaca_enabled": True,
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "current_target_trade_date": "2026-05-20",
                "current_target_captured": True,
                "next_missing_capture_trade_date": "2026-05-21",
            },
            "automation_health": {
                "healthy": True,
                "status": "ACTIVE",
                "rrule": "FREQ=DAILY;BYHOUR=14;BYMINUTE=20;BYSECOND=0",
            },
            "capture": {
                "status": "skipped_existing_shared_date",
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "total_quote_rows": 11836,
                "available_required_underlying_count": 24,
                "required_underlying_count": 24,
                "missing_required_underlyings": [],
            },
            "replay": {
                "error": "Imported historical validation has insufficient trusted benchmark quote dates before replay. Selected dates: 1."
            },
            "diagnostic_replay": {
                "status": "skipped",
                "blockers": ["insufficient_replay_simulation_quote_dates"],
            },
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 24,
                "scan_universe_count": 24,
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                    "next_fresh_scan": {
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "window_end_user_local": "2026-05-21T14:00:00-06:00",
                        "status": "scheduled_future",
                        "can_attempt_scan_now": False,
                    },
                },
                "fresh_scan_retest_plan": {
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                    "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "window_end_user_local": "2026-05-21T14:00:00-06:00",
                    "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                },
                "scan_funnel": {"drop_counts": {"option_liquidity": 9}},
                "drop_diagnostics": [{"drop_key": "option_liquidity", "count": 9}],
            },
            "proof_source_audit": {
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "excluded_trusted_source_labels": [],
                "per_source_shared_quote_dates": [],
            },
        }

        refreshed = refresh_derived_fields_from_latest(
            report,
            reference_now=datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
        )

        self.assertEqual(refreshed["generated_at"], "2026-05-21T10:37:15Z")
        self.assertEqual(refreshed["scan"]["candidate_count"], 0)
        next_scan = refreshed["scan"]["quote_freshness_context"]["next_fresh_scan"]
        self.assertEqual(next_scan["scan_calendar"], "us_equity_market_days")
        self.assertEqual(next_scan["holiday_calendar_source"], "NYSE/Nasdaq US equity market holiday rules")
        self.assertTrue(next_scan["scheduled_trade_date_is_market_day"])
        self.assertEqual(next_scan["scheduled_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(next_scan["window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertFalse(refreshed["derived_refresh"]["market_data_commands_run"])
        self.assertTrue(refreshed["derived_refresh"]["scan_preserved_from_latest"])
        self.assertTrue(refreshed["derived_refresh"]["scan_timing_refreshed"])
        self.assertFalse(refreshed["derived_refresh"]["automation_health_refreshed"])
        self.assertEqual(refreshed["next_execution_runbook_card"]["recommended_action"], "wait_until_not_before")
        self.assertEqual(
            refreshed["next_execution_runbook_card"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        audit = refreshed["exact_history_backfill_capability_audit"]
        self.assertFalse(audit["historical_option_quote_endpoint_found"])
        self.assertFalse(audit["snapshot_updated_since_is_backfill_capability"])
        self.assertIn("no_historical_option_quote_bbo_endpoint", audit["acceleration_blockers"])
        self.assertFalse(audit["can_accelerate_exact_history"])
        docs = {item["label"]: item for item in audit["docs_reviewed"]}
        self.assertIn("optionlatestquotes", docs["Alpaca latest option quotes"]["url"])
        self.assertFalse(refreshed["goal_completion_audit"]["may_mark_goal_complete"])
        self.assertEqual(refreshed["verification_status"], "not_verified")
        self.assertFalse(refreshed["verified"])
        self.assertEqual(refreshed["goal_completion_status"], "not_complete")
        self.assertFalse(refreshed["goal_completion_may_mark_goal_complete"])
        self.assertIn(
            "has_required_exact_alpaca_opra_history_depth",
            refreshed["goal_completion_failed_requirements"],
        )
        contract = refreshed["goal_completion_verification_contract"]
        self.assertEqual(contract["status"], "blocked")
        self.assertFalse(contract["completion_claim_allowed"])
        self.assertEqual(
            contract["derived_refresh_status"],
            "derived_fields_refreshed_from_latest_without_market_data",
        )
        self.assertEqual(contract["record_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertEqual(contract["derived_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertFalse(contract["market_data_commands_run_in_current_refresh"])
        iteration_row = {
            item["requirement"]: item
            for item in contract["requirements"]
        }["iteration_record_is_current"]
        self.assertEqual(
            iteration_row["current_evidence"]["record_refreshed_at_utc"],
            "2026-05-21T10:45:00Z",
        )
        requirement_rows = {item["requirement"]: item for item in contract["requirements"]}
        replay_row = requirement_rows["exact_replay_is_profitable"]
        self.assertEqual(replay_row["evidence_command_role"], "exact_replay_profitability_measurement")
        self.assertEqual(
            replay_row["blocked_until_requirement"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertIsNotNone(replay_row["blocked_until_not_before_user_local"])
        evidence_requirements = {
            item["requirement"]: item for item in refreshed["goal_completion_evidence_plan"]["requirements"]
        }
        self.assertEqual(
            evidence_requirements["exact_replay_is_profitable"]["blocked_until_not_before_user_local"],
            replay_row["blocked_until_not_before_user_local"],
        )

    def test_refresh_derived_fields_from_latest_can_refresh_automation_health_without_market_data(self):
        report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": False, "blocker": "stale_prompt"},
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
            },
            "capture": {
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
            "replay": {"error": "Selected dates: 1."},
            "diagnostic_replay": {"status": "skipped"},
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 24,
                "scan_universe_count": 24,
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {"status": "stale_quote_blocked"},
            },
        }

        with patch(
            "scripts.run_ai_commodity_opra_progress.load_capture_automation_health",
            return_value={
                "healthy": True,
                "prompt_mentions_run_next_execution_command_guard": True,
            },
        ):
            refreshed = refresh_derived_fields_from_latest(
                report,
                reference_now=datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
                refresh_automation_health=True,
            )

        self.assertEqual(refreshed["automation_health"]["healthy"], True)
        self.assertTrue(refreshed["automation_health"]["prompt_mentions_run_next_execution_command_guard"])
        self.assertTrue(refreshed["derived_refresh"]["automation_health_refreshed"])
        self.assertFalse(refreshed["derived_refresh"]["market_data_commands_run"])

    def test_refresh_derived_fields_from_latest_updates_previous_event_local_store_evidence(self):
        report = {
            "generated_at": "2026-05-21T20:20:51Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
            },
            "automation_health": {"healthy": True},
            "capture": {
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
            "replay": {"error": "Selected dates: 2."},
            "diagnostic_replay": {"status": "skipped"},
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 24,
                "scan_universe_count": 24,
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "trusted_only": True,
                "proof_source_shared_quote_dates": {
                    "count": 2,
                    "first": "2026-05-20",
                    "last": "2026-05-21",
                },
                "proof_source_store_inventory": {"quote_dates": {"count": 2}},
                "proof_source_required_symbol_coverage": {
                    "available_required_symbol_count": 24,
                    "required_symbol_count": 24,
                    "missing_required_symbols": [],
                },
            },
            "exact_capture_progress_outcome": {
                "status": "exact_capture_progress_verified",
                "blockers": [],
            },
            "last_execution_review": {
                "status": "passed",
                "previous_selected_step": "post_close_full_universe_capture",
                "checks": [
                    {"name": "capture_target_complete_true", "passed": True},
                    {"name": "shared_quote_dates_increase_or_target_was_already_complete", "passed": True},
                ],
                "blockers": [],
            },
            "previous_proof_event_outcome": {
                "status": "material_progress",
                "event_kind": "exact_opra_history_capture",
                "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                "checks": [
                    {"name": "shared_quote_dates_increased", "passed": True},
                    {"name": "remaining_shared_quote_dates_decreased", "passed": True},
                ],
                "blockers": [],
                "outcome_detail": {"shared_quote_dates_after": 2},
            },
        }

        refreshed = refresh_derived_fields_from_latest(
            report,
            reference_now=datetime(2026, 5, 21, 20, 30, tzinfo=UTC),
        )

        previous = refreshed["previous_proof_event_outcome"]
        checks = {check["name"]: check for check in previous["checks"]}
        self.assertTrue(checks["local_exact_store_matches_proof_window_after_capture"]["passed"])
        self.assertTrue(checks["local_exact_store_has_no_pending_refresh_after_capture"]["passed"])
        self.assertEqual(
            previous["outcome_detail"]["local_exact_store_usage_decision_after"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(previous["outcome_detail"]["local_exact_store_refresh_can_advance_history_depth_after"])
        self.assertEqual(previous["outcome_detail"]["local_exact_available_shared_quote_dates_after"], 2)
        self.assertTrue(previous["outcome_detail"]["local_exact_store_matches_proof_window_after"])
        self.assertEqual(
            refreshed["previous_proof_event_local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(
            refreshed["previous_proof_event_local_exact_store_refresh_can_advance_history_depth"]
        )
        self.assertEqual(refreshed["previous_proof_event_local_exact_available_shared_quote_dates"], 2)
        self.assertTrue(refreshed["previous_proof_event_local_exact_store_matches_proof_window"])
        last_checks = {check["name"]: check for check in refreshed["last_execution_review"]["checks"]}
        self.assertTrue(last_checks["local_exact_store_matches_proof_window_after_capture"]["passed"])
        self.assertTrue(last_checks["local_exact_store_has_no_pending_refresh_after_capture"]["passed"])
        self.assertEqual(
            refreshed["last_execution_review"]["local_exact_store_usage_decision_after"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(
            refreshed["last_execution_review"]["local_exact_store_refresh_can_advance_history_depth_after"]
        )
        self.assertEqual(refreshed["last_execution_review"]["local_exact_available_shared_quote_dates_after"], 2)
        self.assertTrue(refreshed["last_execution_review"]["local_exact_store_matches_proof_window_after"])
        self.assertEqual(
            refreshed["last_execution_local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(refreshed["last_execution_local_exact_store_refresh_can_advance_history_depth"])
        self.assertEqual(refreshed["last_execution_local_exact_available_shared_quote_dates"], 2)
        self.assertTrue(refreshed["last_execution_local_exact_store_matches_proof_window"])
        self.assertEqual(refreshed["last_execution_status"], "passed")
        self.assertEqual(refreshed["last_execution_previous_step"], "post_close_full_universe_capture")
        self.assertEqual(refreshed["last_execution_blockers"], [])
        self.assertIn(
            "capture_target_complete_true",
            [check["name"] for check in refreshed["last_execution_checks"]],
        )

    def test_refresh_derived_fields_from_latest_reaudits_local_historical_store_without_market_data(self):
        report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "db_path": "ignored-test.db",
            "symbols": ["FCX", "SLV"],
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "current_target_trade_date": "2026-05-21",
            },
            "automation_health": {"healthy": True},
            "capture": {
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 2,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
            "replay": {"error": "Selected dates: 1."},
            "diagnostic_replay": {"status": "skipped"},
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 2,
                "scan_universe_count": 2,
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "scan": {"candidate_count": 0, "candidate_symbols": []},
            "proof_source_audit": {
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "per_source_shared_quote_dates": [],
            },
        }
        store = _FakeStore(
            {
                "FCX": ["2026-05-20", "2026-05-21"],
                "SLV": ["2026-05-20", "2026-05-21"],
            },
            source_labels=["alpaca_opra_daily_snapshot"],
            source_dates_by_symbol={
                "alpaca_opra_daily_snapshot": {
                    "FCX": ["2026-05-20", "2026-05-21"],
                    "SLV": ["2026-05-20", "2026-05-21"],
                },
            },
        )

        with patch("scripts.run_ai_commodity_opra_progress.HistoricalOptionsStore", return_value=store):
            refreshed = refresh_derived_fields_from_latest(
                report,
                reference_now=datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
            )

        self.assertTrue(refreshed["derived_refresh"]["historical_store_refreshed"])
        self.assertIsNone(refreshed["derived_refresh"]["historical_store_refresh_error"])
        self.assertEqual(refreshed["derived_refresh"]["historical_store_shared_quote_dates_before"], 1)
        self.assertEqual(refreshed["derived_refresh"]["historical_store_shared_quote_dates_after"], 2)
        self.assertTrue(refreshed["derived_refresh"]["historical_store_shared_quote_dates_changed"])
        self.assertEqual(
            refreshed["derived_refresh"]["next_blocker_before"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertEqual(
            refreshed["derived_refresh"]["next_blocker_after"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
        )
        self.assertEqual(
            refreshed["derived_refresh"]["raw_next_blocker_after"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:2/100",
        )
        self.assertTrue(refreshed["derived_refresh"]["next_blocker_changed"])
        self.assertTrue(
            refreshed["derived_refresh"]["preserved_evidence_stale_after_historical_store_refresh"]
        )
        self.assertEqual(
            refreshed["derived_refresh"]["preserved_evidence_stale_fields"],
            ["source_quality", "readiness", "replay", "diagnostic_replay"],
        )
        self.assertEqual(
            refreshed["derived_refresh"]["preserved_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(
            refreshed["derived_refresh"]["preserved_evidence_refresh_reason"],
            "local_alpaca_opra_shared_quote_dates_changed_since_latest_market_data_run",
        )
        self.assertFalse(refreshed["derived_refresh"]["market_data_commands_run"])
        self.assertEqual(refreshed["shared_quote_dates_after"]["count"], 2)
        self.assertEqual(refreshed["proof_source_audit"]["proof_source_shared_quote_dates"]["count"], 2)
        self.assertTrue(refreshed["proof_source_audit"]["all_required_symbols_have_proof_source_data"])
        self.assertEqual(refreshed["proof_window"]["current_shared_quote_dates"], 2)
        self.assertEqual(refreshed["proof_window"]["remaining_shared_quote_dates"], 98)
        self.assertEqual(refreshed["next_blocker"], "alpaca_opra_daily_snapshot_shared_quote_dates:2/100")
        self.assertEqual(refreshed["quote_date_counts"], {"FCX": 2, "SLV": 2})

    def test_refresh_derived_fields_marks_full_history_depth_change_as_stale_preserved_evidence(self):
        start = datetime(2026, 1, 2, tzinfo=UTC).date()
        dates = [(start + timedelta(days=offset)).isoformat() for offset in range(100)]
        report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:99/100",
            "db_path": "ignored-test.db",
            "symbols": ["FCX", "SLV"],
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 99,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 1,
                "current_target_trade_date": "2026-05-21",
            },
            "automation_health": {"healthy": True},
            "capture": {
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 2,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
            "replay": {"error": "Selected dates: 99."},
            "diagnostic_replay": {"status": "skipped"},
            "scan_proof_universe_alignment": {
                "status": "scan_universe_aligned_with_exact_proof_universe",
                "proof_universe_count": 2,
                "scan_universe_count": 2,
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
            },
            "scan": {"candidate_count": 0, "candidate_symbols": []},
        }
        store = _FakeStore(
            {"FCX": dates, "SLV": dates},
            source_labels=["alpaca_opra_daily_snapshot"],
            source_dates_by_symbol={
                "alpaca_opra_daily_snapshot": {"FCX": dates, "SLV": dates},
            },
        )

        with patch("scripts.run_ai_commodity_opra_progress.HistoricalOptionsStore", return_value=store):
            refreshed = refresh_derived_fields_from_latest(
                report,
                reference_now=datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
            )

        self.assertEqual(refreshed["proof_window"]["current_shared_quote_dates"], 100)
        self.assertEqual(refreshed["proof_window"]["remaining_shared_quote_dates"], 0)
        self.assertEqual(refreshed["derived_refresh"]["historical_store_shared_quote_dates_before"], 99)
        self.assertEqual(refreshed["derived_refresh"]["historical_store_shared_quote_dates_after"], 100)
        self.assertTrue(refreshed["derived_refresh"]["historical_store_shared_quote_dates_changed"])
        self.assertEqual(refreshed["derived_refresh"]["raw_next_blocker_after"], "replay_error:Selected dates: 99.")
        self.assertEqual(
            refreshed["next_blocker"],
            "preserved_readiness_replay_stale_after_historical_store_refresh",
        )
        self.assertEqual(
            refreshed["derived_refresh"]["next_blocker_after"],
            "preserved_readiness_replay_stale_after_historical_store_refresh",
        )
        self.assertTrue(refreshed["derived_refresh"]["preserved_evidence_stale_after_historical_store_refresh"])
        self.assertEqual(
            refreshed["derived_refresh"]["preserved_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(refreshed["lane_next_step"]["phase"], "preserved_evidence_refresh")
        self.assertEqual(
            refreshed["lane_next_step"]["priority_action"],
            "refresh_readiness_replay_after_historical_store_change",
        )
        self.assertEqual(refreshed["lane_next_step"]["next_timed_event_kind"], None)
        self.assertEqual(refreshed["lane_iteration_plan"]["steps"][0]["step"], "preserved_evidence_refresh")
        self.assertEqual(refreshed["lane_iteration_plan"]["steps"][0]["status"], "due_now")
        self.assertEqual(
            refreshed["lane_iteration_plan"]["steps"][0]["command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture", "--skip-scan"],
        )
        self.assertEqual(refreshed["next_execution_contract"]["status"], "ready_to_run")
        self.assertEqual(refreshed["next_execution_contract"]["selected_step"], "preserved_evidence_refresh")
        self.assertTrue(refreshed["next_execution_contract"]["actionable_now"])
        self.assertEqual(refreshed["next_execution_contract"]["blockers"], [])
        payload = build_next_execution_cli_payload(
            refreshed,
            payload_source="derived_latest_refresh",
            reference_now=datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
        )
        self.assertEqual(payload["next_execution_recommended_action"], "run_next_execution_command")
        self.assertTrue(payload["run_next_execution_command"])
        self.assertEqual(
            payload["run_next_execution_command_display"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(payload["next_execution"]["selected_step"], "preserved_evidence_refresh")
        self.assertEqual(payload["next_execution_runbook_card"]["guard_status"], "ready_to_run_guarded_command")
        self.assertEqual(
            payload["next_execution_runbook_card"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertTrue(payload["derived_refresh_preserved_evidence_stale_after_historical_store_refresh"])
        self.assertEqual(
            payload["derived_refresh_preserved_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )

    def test_fresh_scan_due_now_stays_ahead_of_preserved_evidence_refresh(self):
        report = {
            "generated_at": "2026-05-21T14:15:00Z",
            "provider": "alpaca:sip:opra",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 100,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 0,
            },
            "preserved_evidence_refresh": {
                "stale_after_historical_store_refresh": True,
                "stale_fields": ["source_quality", "readiness", "replay", "diagnostic_replay"],
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
                "command_args": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture", "--skip-scan"],
                "reason": "local_alpaca_opra_shared_quote_dates_changed_since_latest_market_data_run",
            },
            "automation_health": {"healthy": True},
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_scheduled_capture": {"scheduled_utc": "2026-05-21T20:20:00Z"},
            },
            "verification_gate": {
                "verified": False,
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_automation_healthy": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "alpaca_opra_source_quality_usable": True,
                    "enough_exact_shared_quote_dates": True,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "live_scan_has_candidate": False,
                },
                "blockers": ["live_scan_candidates:0"],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 99."},
            "diagnostic_replay": {"status": "skipped"},
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                    "next_fresh_scan": {
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                        "reference_utc": "2026-05-21T14:15:00Z",
                        "reference_user_local": "2026-05-21T08:15:00-06:00",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "window_end_user_local": "2026-05-21T14:00:00-06:00",
                        "can_attempt_scan_now": True,
                        "status": "fresh_scan_due_window",
                    },
                },
            },
        }

        lane_next = build_lane_next_step_summary(report)
        planned = {**report, "lane_next_step": lane_next}
        plan = build_lane_iteration_plan(planned)
        contract = build_next_execution_contract({**planned, "lane_iteration_plan": plan})

        self.assertEqual(lane_next["phase"], "fresh_scan_due_preserved_evidence_stale")
        self.assertEqual(lane_next["next_timed_event_kind"], "fresh_opra_scan")
        self.assertEqual(plan["steps"][0]["step"], "fresh_opra_live_scan")
        self.assertEqual(plan["steps"][0]["status"], "due_now")
        self.assertEqual(plan["steps"][0]["scheduled_utc"], "2026-05-21T14:15:00Z")
        self.assertEqual(plan["steps"][1]["step"], "preserved_evidence_refresh")
        self.assertEqual(contract["status"], "ready_to_run")
        self.assertEqual(contract["selected_step"], "fresh_opra_live_scan")
        self.assertTrue(contract["matches_next_timed_event"])
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(
            contract["command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        payload = build_next_execution_cli_payload(
            {**planned, "lane_iteration_plan": plan, "next_execution_contract": contract},
            payload_source="current_run",
            reference_now=datetime(2026, 5, 21, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(payload["next_execution_recommended_action"], "run_next_execution_command")
        self.assertTrue(payload["run_next_execution_command"])
        self.assertEqual(
            payload["run_next_execution_command_display"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(payload["next_execution"]["selected_step"], "fresh_opra_live_scan")
        self.assertEqual(payload["next_execution_runbook_card"]["guard_status"], "ready_to_run_guarded_command")
        self.assertEqual(
            payload["next_execution_runbook_card"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )

    def test_main_from_latest_refreshes_local_store_before_printing_next_execution_payload(self):
        latest_report = {"generated_at": "2026-05-21T10:37:15Z"}
        refreshed_report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "derived_refresh": {"historical_store_refreshed": True},
        }
        reference_now = datetime(2026, 5, 21, 12, 5, tzinfo=UTC)
        output = io.StringIO()

        with patch.object(
            sys,
            "argv",
            [
                "run_ai_commodity_opra_progress.py",
                "--next-execution",
                "--from-latest",
                "--output-dir",
                "ignored-output-dir",
            ],
        ), patch("sys.stdout", output), patch(
            "scripts.run_ai_commodity_opra_progress._utc_now",
            return_value=reference_now,
        ), patch(
            "scripts.run_ai_commodity_opra_progress.load_previous_progress_report",
            return_value=latest_report,
        ) as load_mock, patch(
            "scripts.run_ai_commodity_opra_progress.refresh_derived_fields_from_latest",
            return_value=refreshed_report,
        ) as refresh_mock, patch(
            "scripts.run_ai_commodity_opra_progress.build_next_execution_cli_payload",
            return_value={"payload_source": "latest_artifact", "historical_store_refreshed": True},
        ) as payload_mock:
            result = main()

        self.assertEqual(result, 0)
        load_mock.assert_called_once()
        refresh_mock.assert_called_once_with(
            latest_report,
            reference_now=reference_now,
            refresh_automation_health=True,
        )
        payload_mock.assert_called_once_with(
            refreshed_report,
            payload_source="latest_artifact",
            reference_now=reference_now,
        )
        self.assertEqual(
            json.loads(output.getvalue()),
            {"payload_source": "latest_artifact", "historical_store_refreshed": True},
        )

    def test_main_refresh_derived_from_latest_enforces_strict_gate(self):
        latest_report = {"generated_at": "2026-05-21T10:37:15Z"}
        refreshed_report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "verification_gate": {"status": "not_verified", "verified": False},
            "goal_completion_verification_contract": {
                "completion_claim_allowed": False,
                "unproven_requirements": ["exact_replay_is_profitable"],
            },
        }
        output = io.StringIO()

        with patch.object(
            sys,
            "argv",
            [
                "run_ai_commodity_opra_progress.py",
                "--refresh-derived-from-latest",
                "--no-write",
                "--strict-gate",
                "--json",
                "--output-dir",
                "ignored-output-dir",
            ],
        ), patch("sys.stdout", output), patch(
            "scripts.run_ai_commodity_opra_progress.load_previous_progress_report",
            return_value=latest_report,
        ), patch(
            "scripts.run_ai_commodity_opra_progress.refresh_derived_fields_from_latest",
            return_value=refreshed_report,
        ):
            result = main()

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 2)
        self.assertEqual(payload["strict_accuracy_gate"]["status"], "failed")
        self.assertFalse(payload["strict_accuracy_gate"]["passed"])

    def test_main_from_latest_enforces_strict_gate_exit_code(self):
        latest_report = {"generated_at": "2026-05-21T10:37:15Z"}
        refreshed_report = {
            "generated_at": "2026-05-21T10:37:15Z",
            "verification_gate": {"status": "not_verified", "verified": False},
            "goal_completion_verification_contract": {
                "completion_claim_allowed": False,
                "unproven_requirements": ["live_scan_has_verifiable_candidate"],
            },
        }
        output = io.StringIO()

        with patch.object(
            sys,
            "argv",
            [
                "run_ai_commodity_opra_progress.py",
                "--next-execution",
                "--from-latest",
                "--strict-gate",
                "--output-dir",
                "ignored-output-dir",
            ],
        ), patch("sys.stdout", output), patch(
            "scripts.run_ai_commodity_opra_progress.load_previous_progress_report",
            return_value=latest_report,
        ), patch(
            "scripts.run_ai_commodity_opra_progress.refresh_derived_fields_from_latest",
            return_value=refreshed_report,
        ), patch(
            "scripts.run_ai_commodity_opra_progress.build_next_execution_cli_payload",
            return_value={"payload_source": "latest_artifact"},
        ):
            result = main()

        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue()), {"payload_source": "latest_artifact"})

    def test_run_progress_no_write_disables_capture_and_import(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "scripts.run_ai_commodity_opra_progress.build_alpaca_opra_daily_snapshot",
        ) as build_snapshot, patch(
            "scripts.run_ai_commodity_opra_progress.write_snapshot_csv",
        ) as write_csv:
            report = run_progress(
                symbols=["SPY"],
                min_shared_quote_dates=2,
                db_path=Path(tmpdir) / "history.db",
                output_dir=Path(tmpdir) / "progress",
                capture_output_dir=Path(tmpdir) / "captures",
                readiness_output_dir=Path(tmpdir) / "readiness",
                lane_lab_output_dir=Path(tmpdir) / "lane_lab",
                force_capture=True,
                skip_replay=True,
                skip_scan=True,
                target_date="2026-05-21",
                write=False,
            )

        self.assertEqual(report["capture"]["status"], "skipped_no_write")
        self.assertEqual(report["capture"]["write_guard"], "no_write_disables_capture_and_import")
        build_snapshot.assert_not_called()
        write_csv.assert_not_called()

    def test_run_progress_no_write_disables_primary_replay_artifacts(self):
        replay_calls = []

        def fake_run_historical_backtest(**kwargs):
            replay_calls.append(kwargs)
            return {
                "error": None,
                "total_trades": 1,
                "profit_factor": 1.1,
                "total_return_pct": 1.0,
            }

        fake_wfo = SimpleNamespace(
            DTE_MIN=1,
            DTE_MAX=60,
            STRATEGY_PROFILE={"targets": {"dte_optimal": 25}},
            STRATEGY_PROFILES={
                "equity": {"targets": {"dte_optimal": 25}},
                "index": {"targets": {"dte_optimal": 21}},
            },
            REPLAY_PLAYBOOKS={
                "ai_commodity_infra_observation": {
                    "id": "ai_commodity_infra_observation",
                    "target_dte": 25,
                }
            },
            run_historical_backtest=fake_run_historical_backtest,
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {"wfo_optimizer": fake_wfo}):
            run_progress(
                symbols=["SPY"],
                min_shared_quote_dates=2,
                db_path=Path(tmpdir) / "history.db",
                output_dir=Path(tmpdir) / "progress",
                capture_output_dir=Path(tmpdir) / "captures",
                readiness_output_dir=Path(tmpdir) / "readiness",
                lane_lab_output_dir=Path(tmpdir) / "lane_lab",
                skip_capture=True,
                skip_scan=True,
                target_date="2026-05-21",
                write=False,
            )

        self.assertEqual(len(replay_calls), 1)
        self.assertIn("save_result", replay_calls[0])
        self.assertIs(replay_calls[0]["save_result"], False)

    def test_build_strict_accuracy_gate_fails_when_completion_contract_is_unproven(self):
        report = {
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100"],
            },
            "goal_completion_audit": {
                "status": "not_complete",
                "may_mark_goal_complete": False,
                "failed_requirements": ["has_required_exact_alpaca_opra_history_depth"],
                "blockers": ["insufficient_exact_alpaca_opra_shared_quote_dates"],
            },
            "goal_completion_verification_contract": {
                "completion_claim_allowed": False,
                "unproven_requirements": ["has_required_exact_alpaca_opra_history_depth"],
                "next_evidence_action": "continue_forward_capture",
                "next_evidence_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture",
            },
        }

        gate = build_strict_accuracy_gate(report)

        self.assertEqual(gate["status"], "failed")
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["unproven_requirements"], ["has_required_exact_alpaca_opra_history_depth"])
        self.assertIn("shared_quote_dates:1/100", gate["blockers"])

    def test_build_strict_accuracy_gate_passes_only_when_completion_contract_allows_claim(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 100,
                "required_shared_quote_dates": 100,
            },
            "verification_gate": {"status": "verified_profitable", "verified": True, "blockers": []},
            "goal_completion_audit": {
                "status": "complete",
                "may_mark_goal_complete": True,
                "failed_requirements": [],
                "blockers": [],
            },
            "goal_completion_verification_contract": {
                "completion_claim_allowed": True,
                "unproven_requirements": [],
            },
        }

        gate = build_strict_accuracy_gate(report)

        self.assertEqual(gate["status"], "passed")
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["blockers"], [])

    def test_build_strict_accuracy_gate_blocks_lowered_history_threshold_below_default_floor(self):
        report = self._verified_profitable_goal_report()
        report["proof_window"] = {
            "current_shared_quote_dates": 2,
            "required_shared_quote_dates": 2,
        }

        gate = build_strict_accuracy_gate(report)

        self.assertEqual(gate["status"], "failed")
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["completion_claim_allowed"])
        self.assertIn("has_required_exact_alpaca_opra_history_depth", gate["unproven_requirements"])
        self.assertIn("exact_history_depth_floor_not_satisfied", gate["blockers"])
        self.assertEqual(gate["exact_history_depth_floor"]["current_shared_quote_dates"], 2)
        self.assertEqual(gate["exact_history_depth_floor"]["requested_required_shared_quote_dates"], 2)
        self.assertEqual(gate["exact_history_depth_floor"]["default_required_shared_quote_dates_floor"], 100)
        self.assertEqual(gate["exact_history_depth_floor"]["effective_goal_required_shared_quote_dates"], 100)
        self.assertFalse(gate["exact_history_depth_floor"]["exact_history_depth_floor_satisfied"])

    def test_build_exact_history_acquisition_plan_tracks_alpaca_opra_capture_blocker(self):
        report = {
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "current_target_trade_date": "2026-05-21",
                "current_target_captured": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-18",
                "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
                "capture_calendar": "us_equity_market_days",
                "approx_market_days_to_target": 99,
                "approx_diagnostic_ready_date_if_one_capture_per_market_day": "2026-09-24",
                "approx_completion_date_if_one_capture_per_market_day": "2026-10-12",
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "next_scheduled_capture": {"scheduled_utc": "2026-05-21T20:20:00Z"},
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "fresh_or_not_age_limited",
                    "next_fresh_scan": {
                        "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                        "window_end_user_local": "2026-05-21T14:00:00-06:00",
                        "scan_calendar": "us_equity_market_days",
                        "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                        "scheduled_trade_date_is_market_day": True,
                    }
                },
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["FCX"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "gate_sensitivity": {"production_filters_preserved": True},
                "blocker_examples": [{"symbol": "FCX", "drop_key": "option_liquidity"}],
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "post_close_full_universe_capture",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T20:20:00Z",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-21",
                        ],
                    }
                ]
            },
            "proof_source_audit": {
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "excluded_trusted_source_labels": ["thetadata_free_eod"],
                "per_source_shared_quote_dates": [
                    {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "used_for_exact_profitability_proof": True,
                        "shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                        "required_symbol_coverage": {
                            "required_symbol_count": 24,
                            "available_required_symbol_count": 24,
                            "missing_required_symbols": [],
                        },
                    },
                    {
                        "source_label": "thetadata_free_eod",
                        "used_for_exact_profitability_proof": False,
                        "shared_quote_dates": {"count": 1, "first": "2026-05-15", "last": "2026-05-15"},
                    },
                ],
            },
            "source_quality": {
                "total_quote_rows": 11836,
                "available_required_underlying_count": 24,
                "required_underlying_count": 24,
                "missing_required_underlyings": [],
            },
        }

        plan = build_exact_history_acquisition_plan(report)

        self.assertEqual(plan["status"], "forward_capture_required")
        self.assertEqual(plan["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(plan["current_shared_quote_dates"], 1)
        self.assertEqual(plan["required_shared_quote_dates"], 100)
        self.assertEqual(plan["remaining_shared_quote_dates"], 99)
        self.assertEqual(plan["next_capture_trade_date"], "2026-05-21")
        self.assertEqual(plan["next_capture_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(
            plan["next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(plan["diagnostic_required_shared_quote_dates"], 88)
        self.assertEqual(len(plan["forward_capture_queue"]), 5)
        self.assertEqual(plan["forward_capture_queue"][0]["trade_date"], "2026-05-21")
        self.assertEqual(
            plan["forward_capture_queue"][0]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(plan["forward_capture_queue"][0]["not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(plan["forward_capture_queue"][0]["expected_shared_quote_dates_after_capture"], 2)
        self.assertFalse(plan["forward_capture_queue"][0]["diagnostic_replay_unlocked_after_capture"])
        self.assertEqual(plan["forward_capture_queue"][1]["trade_date"], "2026-05-22")
        self.assertEqual(plan["forward_capture_queue"][2]["trade_date"], "2026-05-26")
        self.assertEqual(plan["forward_capture_queue"][4]["expected_shared_quote_dates_after_capture"], 6)
        self.assertEqual(
            plan["capture_continuity_contract"]["status"],
            "on_track_no_missed_capture_dates",
        )
        self.assertEqual(plan["capture_continuity_contract"]["missed_capture_trade_dates"], [])
        self.assertEqual(
            plan["capture_continuity_contract"]["missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertEqual(
            plan["capture_continuity_contract"]["next_action"],
            "continue_guarded_forward_capture_queue",
        )
        self.assertEqual(
            plan["unlock_milestones"]["diagnostic_replay"],
            {
                "name": "diagnostic_replay",
                "status": "pending_forward_capture",
                "required_shared_quote_dates": 88,
                "current_shared_quote_dates": 1,
                "remaining_market_day_captures": 87,
                "unlock_trade_date": "2026-09-24",
                "not_before_utc": "2026-09-24T20:20:00Z",
                "not_before_user_local": "2026-09-24T14:20:00-06:00",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-09-24",
                "expected_shared_quote_dates_after_capture": 88,
                "capture_calendar": "us_equity_market_days",
                "scheduled_trade_date_is_market_day": True,
            },
        )
        self.assertEqual(plan["unlock_milestones"]["full_exact_replay"]["unlock_trade_date"], "2026-10-12")
        self.assertEqual(plan["unlock_milestones"]["full_exact_replay"]["remaining_market_day_captures"], 99)
        self.assertEqual(
            plan["unlock_milestones"]["full_exact_replay"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-10-12",
        )
        self.assertEqual(plan["exact_history_backfill_status"], "forward_daily_snapshot_capture_required")
        self.assertFalse(plan["can_accelerate_exact_history_with_existing_sources"])
        self.assertEqual(
            plan["backfill_capability_audit"]["status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        self.assertEqual(
            plan["exact_history_backfill_missing_capability"],
            "historical_option_quote_bbo_method_for_contracts",
        )
        self.assertEqual(
            plan["exact_history_backfill_capability_next_action"],
            "continue_forward_daily_alpaca_opra_snapshot_capture",
        )
        self.assertFalse(plan["backfill_capability_audit"]["snapshot_updated_since_is_backfill_capability"])
        self.assertIn(
            "option_snapshots_are_latest_state_not_as_of_date_history",
            plan["backfill_capability_audit"]["acceleration_blockers"],
        )
        self.assertEqual(
            plan["exact_proof_policy"],
            "only_alpaca_opra_daily_snapshot_shared_dates_count_for_exact_bid_ask_profitability",
        )
        self.assertTrue(plan["backfill_feasibility"][0]["counts_for_exact_profitability_proof"])
        self.assertFalse(plan["research_only_sources"][0]["counts_for_exact_profitability_proof"])
        self.assertEqual(plan["research_only_sources"][2]["source_labels"], ["thetadata_free_eod"])
        self.assertEqual(
            plan["source_coverage"]["exact_proof_source"]["required_symbol_coverage"][
                "available_required_symbol_count"
            ],
            24,
        )

    def test_build_exact_history_acquisition_plan_blocks_fake_backfill_for_missed_capture_dates(self):
        plan = build_exact_history_acquisition_plan(
            {
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 99,
                    "latest_shared_quote_date": "2026-05-15",
                    "current_target_trade_date": "2026-05-20",
                    "current_target_captured": False,
                    "next_missing_capture_trade_date": "2026-05-20",
                    "missed_capture_trade_dates_since_latest_shared": ["2026-05-18", "2026-05-19"],
                    "capture_calendar": "us_equity_market_days",
                },
                "capture_action": {
                    "status": "intervention_required_missed_capture_dates",
                    "next_action": "record_missed_capture_dates_keep_goal_incomplete_and_resume_forward_capture",
                    "next_scheduled_capture": {"scheduled_utc": "2026-05-20T20:20:00Z"},
                },
                "lane_iteration_plan": {
                    "steps": [
                        {
                            "step": "post_close_full_universe_capture",
                            "not_before_utc": "2026-05-20T20:20:00Z",
                            "command": [
                                "python",
                                "scripts/run_ai_commodity_opra_progress.py",
                                "--force-capture",
                                "--target-date",
                                "2026-05-20",
                            ],
                        }
                    ]
                },
            }
        )

        contract = plan["capture_continuity_contract"]
        self.assertEqual(contract["status"], "intervention_required_missed_capture_dates")
        self.assertEqual(contract["missed_capture_trade_dates"], ["2026-05-18", "2026-05-19"])
        self.assertFalse(contract["missed_capture_dates_recoverable"])
        self.assertEqual(
            contract["missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertIn("alpaca_historical_option_bars", contract["prohibited_recovery_sources"])
        self.assertEqual(
            contract["recovery_action"],
            "do_not_count_missed_dates_resume_forward_capture_from_next_missing_trade_date",
        )
        self.assertEqual(
            contract["next_action"],
            "record_missed_capture_dates_keep_goal_incomplete_and_resume_forward_capture",
        )
        self.assertEqual(
            contract["resume_forward_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-20",
        )

    def test_build_next_proof_event_checkpoint_self_grades_fresh_scan(self):
        checkpoint = build_next_proof_event_checkpoint(
            {
                "verification_gate": {"status": "not_verified", "verified": False},
                "next_execution_contract": {
                    "selected_step": "fresh_opra_live_scan",
                    "not_before_utc": "2026-05-21T14:10:00Z",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                },
                "next_execution_runbook_card": {
                    "selected_step": "fresh_opra_live_scan",
                    "guard_status": "clock_guard_active",
                    "recommended_action": "wait_until_not_before",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-21T14:10:00Z",
                    "not_before_user_local": "2026-05-21T08:10:00-06:00",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "window_end_user_local": "2026-05-21T14:00:00-06:00",
                    "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                },
                "goal_completion_evidence_plan": {
                    "missing_evidence": [
                        "has_required_exact_alpaca_opra_history_depth",
                        "live_scan_has_verifiable_candidate",
                    ],
                    "next_requirement_to_unblock": "live_scan_has_verifiable_candidate",
                },
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "remaining_shared_quote_dates": 99,
                },
                "fresh_scan_iteration_decision": {
                    "status": "waiting_for_fresh_opra_scan",
                    "candidate_count": 0,
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 9}],
                },
                "scan": {
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "waiting_for_fresh_scan_execution",
                    "next_action": "wait_until_not_before_then_run_next_execution_command",
                    "next_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "blockers": [],
                    "profitability_gate_effect": "live_scan_is_entry_evidence_only_exact_bid_ask_replay_still_required",
                },
            }
        )

        self.assertEqual(checkpoint["status"], "waiting_until_next_proof_event")
        self.assertEqual(checkpoint["event_kind"], "fresh_opra_live_candidate_scan")
        self.assertEqual(checkpoint["target_goal_requirement"], "live_scan_has_verifiable_candidate")
        self.assertEqual(checkpoint["command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(checkpoint["not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(checkpoint["window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertIn("scan.candidate_count > 0", checkpoint["material_progress_if"])
        self.assertIn("scan.candidate_symbols", checkpoint["fields_to_compare_after_run"])
        self.assertIn("fresh_scan_post_run_evaluation.status", checkpoint["fields_to_compare_after_run"])
        self.assertIn("fresh_scan_post_run_evaluation.next_command", checkpoint["fields_to_compare_after_run"])
        self.assertIn(
            "quote_freshness_cleared_and_candidates_still_zero",
            checkpoint["no_progress_blockers_to_record"],
        )
        self.assertEqual(
            checkpoint["next_after_success"],
            "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
        )
        self.assertEqual(checkpoint["current_evidence"]["exact_history_remaining_shared_quote_dates"], 99)
        self.assertEqual(checkpoint["current_evidence"]["fresh_scan_top_drop_counts"][0]["drop_key"], "option_liquidity")
        self.assertEqual(checkpoint["current_evidence"]["fresh_scan_post_run_status"], "waiting_for_fresh_scan_execution")
        self.assertEqual(
            checkpoint["current_evidence"]["fresh_scan_post_run_next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )

    def test_build_next_proof_event_checkpoint_self_grades_post_close_capture_isolation(self):
        checkpoint = build_next_proof_event_checkpoint(
            {
                "verification_gate": {"status": "not_verified", "verified": False},
                "next_execution_contract": {
                    "selected_step": "post_close_full_universe_capture",
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "command": [
                        "python",
                        "scripts/run_ai_commodity_opra_progress.py",
                        "--force-capture",
                        "--target-date",
                        "2026-05-21",
                    ],
                },
                "next_execution_runbook_card": {
                    "selected_step": "post_close_full_universe_capture",
                    "guard_status": "clock_guard_active",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                },
                "goal_completion_evidence_plan": {
                    "next_requirement_to_unblock": "has_required_exact_alpaca_opra_history_depth",
                },
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "remaining_shared_quote_dates": 99,
                    "local_exact_store_usage_decision": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                    "local_exact_store_refresh_can_advance_history_depth": False,
                    "backfill_capability_audit": {
                        "local_exact_store_usage_decision": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                        "local_exact_store_refresh_can_advance_history_depth": False,
                        "local_exact_available_shared_quote_dates": 1,
                        "local_exact_store_matches_proof_window": True,
                    },
                },
            }
        )

        self.assertEqual(checkpoint["status"], "waiting_until_next_proof_event")
        self.assertEqual(checkpoint["event_kind"], "exact_opra_history_capture")
        self.assertEqual(checkpoint["target_goal_requirement"], "has_required_exact_alpaca_opra_history_depth")
        self.assertIn("proof_window.current_shared_quote_dates increases", checkpoint["material_progress_if"])
        self.assertIn(
            "proof_source_isolation_contract.status stays isolated_to_alpaca_opra_proof_source",
            checkpoint["material_progress_if"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_trade_dates stays empty",
            checkpoint["material_progress_if"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window true",
            checkpoint["material_progress_if"],
        )
        self.assertIn("proof_source_isolation_contract.status", checkpoint["fields_to_compare_after_run"])
        self.assertIn("proof_source_isolation_contract.blockers", checkpoint["fields_to_compare_after_run"])
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_available_shared_quote_dates",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_matches_proof_window",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.status",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_policy",
            checkpoint["fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_source_isolation_contract_blocked_after_capture",
            checkpoint["no_progress_blockers_to_record"],
        )
        self.assertIn(
            "capture_continuity_missed_capture_trade_dates_nonempty",
            checkpoint["no_progress_blockers_to_record"],
        )
        self.assertIn(
            "local_exact_store_mismatch_with_proof_window_after_capture",
            checkpoint["no_progress_blockers_to_record"],
        )
        self.assertEqual(
            checkpoint["current_evidence"]["exact_history_local_exact_store_usage_decision"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(
            checkpoint["current_evidence"]["exact_history_local_exact_store_refresh_can_advance_history_depth"]
        )
        self.assertEqual(checkpoint["current_evidence"]["exact_history_local_exact_available_shared_quote_dates"], 1)
        self.assertTrue(checkpoint["current_evidence"]["exact_history_local_exact_store_matches_proof_window"])
        self.assertEqual(
            checkpoint["next_after_success"],
            "rerun_progress_report_and_continue_daily_exact_capture_runway",
        )

    def test_build_auxiliary_proof_event_queue_surfaces_fresh_scan_measurement_before_capture(self):
        report = {
            "generated_at": "2026-05-21T20:20:51Z",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
            },
            "goal_completion_evidence_plan": {
                "missing_evidence": [
                    "live_scan_has_verifiable_candidate",
                    "has_required_exact_alpaca_opra_history_depth",
                ],
                "next_requirement_to_unblock": "has_required_exact_alpaca_opra_history_depth",
            },
            "next_execution_contract": {
                "selected_step": "post_close_full_universe_capture",
                "not_before_utc": "2026-05-22T20:20:00Z",
                "not_before_user_local": "2026-05-22T14:20:00-06:00",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-22",
                ],
            },
            "next_execution_runbook_card": {
                "selected_step": "post_close_full_universe_capture",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
                "not_before_utc": "2026-05-22T20:20:00Z",
                "not_before_user_local": "2026-05-22T14:20:00-06:00",
            },
            "guarded_capture_runbook_packet": {
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
                "not_before_utc": "2026-05-22T20:20:00Z",
                "not_before_user_local": "2026-05-22T14:20:00-06:00",
            },
            "live_candidate_recovery_plan": {
                "candidate_count": 0,
                "read_only_recovery_distance_measurement_plan": {
                    "status": "distance_measurement_gaps_present",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "command_role": "read_only_distance_measurement_no_filter_mutation",
                    "run_guard": "run_only_when_fresh_opra_scan_window_is_allowed_or_returned_by_next_execution_guard",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "fresh_scan_window_status": "fresh_scan_future",
                    "fresh_scan_can_run_now": False,
                    "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
                    "distance_measured_count": 6,
                    "partial_distance_measurement_count": 3,
                    "distance_measurement_gap_count": 3,
                    "distance_measurement_missing_field_count": 9,
                    "gaps": [
                        {"symbol": "AA", "missing_fields": ["momentum_signal_distance_pct", "price", "sma20"]},
                        {"symbol": "BHP", "missing_fields": ["momentum_signal_distance_pct", "price", "sma20"]},
                        {"symbol": "CEG", "missing_fields": ["momentum_signal_distance_pct", "price", "sma20"]},
                    ],
                    "gap_symbols_by_drop": {"momentum": ["AA", "BHP", "CEG"]},
                    "required_fields_by_drop": {
                        "momentum": [
                            "momentum_signal_distance_pct",
                            "price",
                            "sma20",
                        ],
                    },
                    "material_progress_if": [
                        "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count decreases",
                        "live_candidate_recovery_plan.read_only_recovery_distance_measured_count increases",
                    ],
                    "evidence_fields": [
                        "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gaps",
                        "scan.drop_diagnostics",
                    ],
                    "blocked_mutations": [
                        "production_filter_changes",
                        "deferred_variant_materialization",
                        "variant_promotion",
                        "profitability_claims",
                    ],
                },
            },
        }

        queue = build_auxiliary_proof_event_queue(report)

        self.assertEqual(len(queue), 1)
        event = queue[0]
        self.assertEqual(event["event_kind"], "read_only_distance_measurement_fresh_scan")
        self.assertEqual(event["status"], "waiting_until_auxiliary_proof_event")
        self.assertEqual(event["target_goal_requirement"], "live_scan_has_verifiable_candidate")
        self.assertEqual(event["command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(event["not_before_user_local"], "2026-05-22T08:10:00-06:00")
        self.assertEqual(event["window_end_user_local"], "2026-05-22T14:00:00-06:00")
        self.assertTrue(event["precedes_primary_next_execution"])
        self.assertEqual(event["minutes_before_primary_next_execution"], 370.0)
        self.assertEqual(event["reference_utc"], "2026-05-21T20:20:51Z")
        self.assertEqual(event["gap_symbols_by_drop"], {"momentum": ["AA", "BHP", "CEG"]})
        self.assertEqual(event["distance_measured_count"], 6)
        self.assertEqual(event["partial_distance_measurement_count"], 3)
        self.assertEqual(event["distance_measurement_gap_count"], 3)
        self.assertEqual(event["distance_measurement_missing_field_count"], 9)
        self.assertEqual(
            event["distance_measurement_missing_fields_by_symbol"],
            {
                "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
            },
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            event["material_progress_if"],
        )
        self.assertIn("scan.scan_drop_reason_count > 0", event["material_progress_if"])
        self.assertIn(
            "distance_measurement_missing_field_count decreases",
            event["material_progress_if"],
        )
        self.assertIn(
            "distance_measurement_missing_fields_by_symbol fills one or more fields",
            event["material_progress_if"],
        )
        self.assertIn(
            "distance_measurement_missing_fields_by_symbol_unchanged",
            event["no_progress_blockers_to_record"],
        )
        self.assertIn(
            "scan_drop_reason_audit_status_not_raw_drop_reasons_recorded",
            event["no_progress_blockers_to_record"],
        )
        self.assertIn("scan.scan_drop_reason_audit_status", event["fields_to_compare_after_run"])
        self.assertIn("scan.scan_drop_reason_examples_by_symbol", event["fields_to_compare_after_run"])
        self.assertIn("scan.candidate_count > 0", event["material_progress_if"])
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count",
            event["fields_to_compare_after_run"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_partial_distance_measurement_count",
            event["fields_to_compare_after_run"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gaps[*].missing_fields",
            event["fields_to_compare_after_run"],
        )
        self.assertIn("production_filter_changes", event["blocked_mutations"])
        guard = build_run_auxiliary_proof_event_guard_summary(queue)
        self.assertFalse(guard["run_auxiliary_proof_event_command"])
        self.assertEqual(guard["status"], "waiting_until_auxiliary_proof_event")
        self.assertEqual(
            guard["reason"],
            "waiting_until_not_before:2026-05-22T08:10:00-06:00",
        )
        self.assertEqual(
            guard["guarded_command_to_run_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(guard["distance_measurement_missing_field_count"], 9)
        self.assertEqual(
            guard["distance_measurement_missing_fields_by_symbol"]["AA"],
            ["momentum_signal_distance_pct", "price", "sma20"],
        )
        payload_report = {
            **report,
            "automation_health": {"healthy": True, "status": "ACTIVE", "kind": "heartbeat"},
            "proof_window": {
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
            },
            "capture_action": {"status": "waiting_for_next_market_close"},
            "capture": {"status": "skipped_by_request"},
            "readiness": {"status": "waiting_for_history_depth"},
            "source_quality": {},
            "replay": {"total_trades": 0},
            "diagnostic_replay": {},
            "scan": {"candidate_count": 0},
            "lane_next_step": {"phase": "capture_wait", "safe_to_tune_filters": False},
            "lane_iteration_plan": {"status": "active", "steps": []},
            "next_execution_preflight": {
                "status": "waiting_until_not_before",
                "failed_checks": [],
                "non_clock_blockers": [],
            },
            "goal_completion_audit": {
                "status": "not_complete",
                "complete": False,
                "may_mark_goal_complete": False,
                "requirements": [],
                "failed_requirements": [
                    "has_required_exact_alpaca_opra_history_depth",
                    "live_scan_has_verifiable_candidate",
                ],
            },
            "goal_completion_verification_contract": {
                "status": "not_complete",
                "completion_claim_allowed": False,
            },
            "exact_history_acquisition_plan": {
                "status": "forward_capture_required",
                "remaining_shared_quote_dates": 98,
                "capture_continuity_contract": {
                    "status": "on_track_no_missed_capture_dates",
                    "missed_capture_trade_dates": [],
                    "missed_capture_policy": (
                        "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                    ),
                },
            },
            "exact_capture_import_health": {},
            "exact_capture_post_run_evaluation": {},
            "exact_capture_progress_contract": {},
            "exact_profitability_blocker_review": {},
            "fresh_scan_iteration_decision": {},
            "fresh_scan_post_run_evaluation": {},
            "post_fresh_scan_research_backlog": {},
            "exact_replay_unlock_contract": {},
            "next_proof_event_checkpoint": {},
            "lane_next_step_plan": {},
        }

        payload = build_next_execution_cli_payload(
            payload_report,
            reference_now=datetime(2026, 5, 21, 20, 20, 51, tzinfo=UTC),
        )
        self.assertEqual(payload["auxiliary_proof_event_count"], 1)
        self.assertEqual(
            payload["goal_completion_primary_next_requirement_to_unblock"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            payload["goal_completion_earliest_evidence_opportunity_source"],
            "auxiliary_evidence_opportunity",
        )
        self.assertEqual(
            payload["goal_completion_earliest_evidence_opportunity_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            payload["goal_completion_earliest_evidence_opportunity_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["auxiliary_first_proof_event_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertTrue(payload["auxiliary_first_proof_event_precedes_primary_next_execution"])
        self.assertEqual(payload["auxiliary_first_proof_event_distance_measured_count"], 6)
        self.assertEqual(payload["auxiliary_first_proof_event_partial_distance_measurement_count"], 3)
        self.assertEqual(payload["auxiliary_first_proof_event_distance_measurement_gap_count"], 3)
        self.assertEqual(payload["auxiliary_first_proof_event_distance_measurement_missing_field_count"], 9)
        self.assertEqual(payload["live_candidate_recovery_read_only_distance_measurement_missing_field_count"], 9)
        self.assertEqual(
            payload["live_candidate_recovery_read_only_distance_measurement_missing_fields_by_symbol"]["AA"],
            ["momentum_signal_distance_pct", "price", "sma20"],
        )
        self.assertFalse(payload["run_auxiliary_proof_event_command"])
        self.assertEqual(
            payload["run_auxiliary_proof_event_command_reason"],
            "waiting_until_not_before:2026-05-22T08:10:00-06:00",
        )
        self.assertEqual(payload["guarded_command_decision_status"], "waiting_until_next_guarded_event")
        self.assertEqual(payload["guarded_command_decision_action"], "wait_until_not_before")
        self.assertEqual(payload["guarded_command_decision_source"], "auxiliary_proof_event")
        self.assertFalse(payload["guarded_command_decision_safe_to_execute_now"])
        self.assertIsNone(payload["guarded_command_decision_command"])
        self.assertEqual(
            payload["guarded_command_decision_next_command_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["guarded_command_decision_next_command_role_when_allowed"],
            "read_only_distance_measurement_no_filter_mutation",
        )
        self.assertEqual(
            payload["guarded_command_decision_next_no_mutation_guard_when_allowed"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertEqual(
            payload["capture_continuity_contract"]["status"],
            "on_track_no_missed_capture_dates",
        )
        self.assertEqual(
            payload["run_auxiliary_proof_event_guarded_command_to_run_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["raw_drop_reason_evidence_status"],
            "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
        )
        self.assertIsNone(payload["raw_drop_reason_evidence_requirement_satisfied_by"])
        self.assertFalse(payload["raw_drop_reason_evidence_safe_to_tune_filters"])
        self.assertIn(
            "scan.scan_drop_reason_audit_status",
            payload["raw_drop_reason_evidence_required_fields"],
        )

        summary = build_compact_progress_summary(payload_report)
        self.assertEqual(summary["auxiliary_proof_event_count"], 1)
        self.assertEqual(
            summary["goal_completion_primary_next_requirement_to_unblock"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            summary["goal_completion_earliest_evidence_opportunity_source"],
            "auxiliary_evidence_opportunity",
        )
        self.assertEqual(
            summary["goal_completion_earliest_evidence_opportunity_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            summary["guarded_command_decision_next_command_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            summary["guarded_command_decision_next_command_role_when_allowed"],
            "read_only_distance_measurement_no_filter_mutation",
        )
        self.assertEqual(summary["auxiliary_first_proof_event_distance_measurement_missing_field_count"], 9)
        self.assertEqual(
            summary["auxiliary_first_proof_event_kind"],
            "read_only_distance_measurement_fresh_scan",
        )
        self.assertFalse(summary["run_auxiliary_proof_event_command"])
        self.assertEqual(
            summary["raw_drop_reason_evidence_status"],
            "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
        )
        self.assertIsNone(summary["raw_drop_reason_evidence_requirement_satisfied_by"])
        self.assertIn(
            "scan_drop_reason_count_zero_or_missing",
            summary["raw_drop_reason_evidence_blockers"],
        )
        self.assertEqual(
            summary["capture_continuity_contract"]["status"],
            "on_track_no_missed_capture_dates",
        )

        markdown = render_markdown(payload_report)
        self.assertIn("## Raw Drop Reason Evidence Contract", markdown)
        self.assertIn("## Auxiliary Proof Events", markdown)
        self.assertIn("## Capture Debt And Continuity", markdown)
        self.assertIn("Next command when allowed: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn("Next command role when allowed: `read_only_distance_measurement_no_filter_mutation`", markdown)
        self.assertIn("Earliest evidence opportunity source", markdown)
        self.assertIn("`read_only_distance_measurement_fresh_scan`", markdown)

    def test_build_raw_drop_reason_evidence_contract_waits_for_guarded_fresh_scan(self):
        contract = build_raw_drop_reason_evidence_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                    }
                },
                "scan": {
                    "candidate_count": 0,
                    "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "branch": "structural_blocker_branch",
                    "top_drop_counts": [{"drop_key": "momentum", "count": 12}],
                },
                "live_candidate_recovery_plan": {
                    "dominant_drop_key": "momentum",
                    "top_drop_counts": [{"drop_key": "momentum", "count": 12}],
                    "read_only_review_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                },
                "auxiliary_proof_event_queue": [
                    {
                        "status": "waiting_until_auxiliary_proof_event",
                        "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                        "command_role": "read_only_distance_measurement_no_filter_mutation",
                        "not_before_utc": "2026-05-22T14:10:00Z",
                        "not_before_user_local": "2026-05-22T08:10:00-06:00",
                        "window_end_utc": "2026-05-22T20:00:00Z",
                        "window_end_user_local": "2026-05-22T14:00:00-06:00",
                        "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
                        "material_progress_if": ["scan.scan_drop_reason_count > 0"],
                        "no_progress_blockers_to_record": ["scan_drop_reason_count_zero_or_missing"],
                    }
                ],
            }
        )

        self.assertEqual(
            contract["status"],
            "waiting_until_next_fresh_scan_to_record_raw_drop_reasons",
        )
        self.assertEqual(contract["dominant_drop_key"], "momentum")
        self.assertEqual(
            contract["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertFalse(contract["safe_to_tune_filters"])
        self.assertIn("scan.scan_drop_reason_audit_status", contract["required_evidence_fields"])
        self.assertIn("scan_drop_reason_count_zero_or_missing", contract["blockers"])
        self.assertIn("scan.scan_drop_reason_count > 0", contract["material_progress_if"])
        self.assertEqual(
            contract["post_run_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertIn("raw_drop_reason_evidence_status", contract["post_run_fields_to_compare"])
        self.assertIn("scan_drop_reason_count", contract["post_run_fields_to_compare"])
        self.assertIn(
            "raw_drop_reasons_recorded_zero_candidate_reviewable",
            contract["post_run_success_statuses"],
        )
        self.assertIn(
            "scan_drop_reason_count is null or <= 0",
            contract["post_run_still_blocked_if"],
        )

    def test_build_raw_drop_reason_evidence_contract_marks_raw_reasons_reviewable(self):
        contract = build_raw_drop_reason_evidence_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                    }
                },
                "scan": {
                    "candidate_count": 0,
                    "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                    "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                    "scan_drop_reason_count": 4,
                    "scan_drop_reason_symbols_by_drop": {"momentum": ["CCJ"]},
                    "scan_drop_reason_examples_by_symbol": {"CCJ": {"symbol": "CCJ"}},
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "branch": "structural_blocker_branch",
                    "top_drop_counts": [{"drop_key": "momentum", "count": 4}],
                },
            }
        )

        self.assertEqual(
            contract["status"],
            "raw_drop_reasons_recorded_zero_candidate_reviewable",
        )
        self.assertTrue(contract["raw_scan_drop_reasons_recorded"])
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(
            contract["next_action"],
            "review_raw_scan_drop_reasons_without_relaxing_production_filters",
        )
        self.assertTrue(contract["scan_drop_reason_examples_by_symbol_available"])
        self.assertEqual(contract["post_run_audit_card"]["status"], "satisfied")

    def test_build_raw_drop_reason_evidence_contract_clears_blockers_when_live_candidate_verified(self):
        contract = build_raw_drop_reason_evidence_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": True,
                        "live_scan_candidate_inside_exact_proof_universe": True,
                    }
                },
                "scan": {
                    "candidate_count": 1,
                    "candidate_symbols": ["CCJ"],
                    "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                },
                "fresh_scan_iteration_decision": {
                    "status": "candidate_evidence_found",
                    "branch": "live_candidate_branch",
                    "candidate_symbols": ["CCJ"],
                },
            }
        )

        self.assertEqual(contract["status"], "not_needed_live_candidate_verified")
        self.assertEqual(contract["requirement_satisfied_by"], "live_candidate_verified")
        self.assertEqual(contract["candidate_symbols"], ["CCJ"])
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(contract["post_run_audit_card"]["status"], "satisfied")
        self.assertIn("not_needed_live_candidate_verified", contract["post_run_success_statuses"])
        self.assertEqual(
            contract["next_action"],
            "preserve_candidate_and_wait_for_exact_replay_profitability_gate",
        )

    def test_auxiliary_proof_event_uses_derived_refresh_clock_when_window_opens(self):
        report = {
            "generated_at": "2026-05-21T20:20:51Z",
            "derived_refresh": {"refreshed_at_utc": "2026-05-22T14:15:00Z"},
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                },
            },
            "goal_completion_evidence_plan": {
                "missing_evidence": ["live_scan_has_verifiable_candidate"],
            },
            "next_execution_runbook_card": {
                "selected_step": "post_close_full_universe_capture",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22",
                "not_before_utc": "2026-05-22T20:20:00Z",
                "not_before_user_local": "2026-05-22T14:20:00-06:00",
            },
            "live_candidate_recovery_plan": {
                "candidate_count": 0,
                "read_only_recovery_distance_measurement_plan": {
                    "status": "distance_measurement_gaps_present",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "fresh_scan_can_run_now": False,
                    "distance_measured_count": 6,
                    "distance_measurement_gap_count": 3,
                },
            },
        }

        event = build_auxiliary_proof_event_queue(report)[0]

        self.assertEqual(event["reference_utc"], "2026-05-22T14:15:00Z")
        self.assertEqual(event["status"], "ready_to_run_auxiliary_proof_event")
        self.assertEqual(event["recommended_action"], "run_auxiliary_proof_event_command")
        self.assertEqual(
            event["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        guard = build_run_auxiliary_proof_event_guard_summary([event])
        self.assertTrue(guard["run_auxiliary_proof_event_command"])
        self.assertEqual(guard["status"], "ready_to_run_auxiliary_proof_event")
        self.assertEqual(guard["reason"], "ready_to_run_auxiliary_proof_event")
        self.assertEqual(
            guard["allowed_command_now"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        payload = build_next_execution_cli_payload(
            {
                **report,
                "auxiliary_proof_event_queue": [event],
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 98,
                },
                "scan": {"candidate_count": 0},
            },
            reference_now=datetime(2026, 5, 22, 14, 15, tzinfo=UTC),
        )

        self.assertTrue(payload["run_auxiliary_proof_event_command"])
        self.assertEqual(payload["guarded_command_decision_status"], "ready_to_run_auxiliary_proof_event")
        self.assertEqual(payload["guarded_command_decision_action"], "run_auxiliary_proof_event_command")
        self.assertEqual(payload["guarded_command_decision_source"], "auxiliary_proof_event")
        self.assertTrue(payload["guarded_command_decision_safe_to_execute_now"])
        self.assertEqual(
            payload["guarded_command_decision_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["guarded_command_decision_next_command_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["guarded_command_decision_next_command_role_when_allowed"],
            "read_only_distance_measurement_no_filter_mutation",
        )
        self.assertEqual(
            payload["guarded_command_decision_next_no_mutation_guard_when_allowed"],
            None,
        )

    def test_live_candidate_distance_measurement_plan_uses_derived_refresh_clock(self):
        plan = build_live_candidate_recovery_plan(
            {
                "generated_at": "2026-05-21T20:20:51Z",
                "derived_refresh": {"refreshed_at_utc": "2026-05-22T14:15:00Z"},
                "provider": "alpaca:sip:opra",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                        "proof_scan_universe_aligned": True,
                    }
                },
                "scan": {
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "fresh_scan_zero_candidates_after_fresh_quotes",
                    "candidate_count": 0,
                    "candidate_symbols": [],
                    "freshness_cleared": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_trusted_only": True,
                    "proof_scan_universe_aligned": True,
                    "top_drop_counts": [{"drop_key": "momentum", "count": 3}],
                    "zero_candidate_structural_review": {
                        "dominant_drop_key": "momentum",
                        "dominant_drop_count": 3,
                        "allowed_read_only_actions": ["rank_nearest_zero_candidate_blocker_symbols"],
                        "nearest_examples_by_drop": {"momentum": [{"symbol": "AA", "ret5": 0.38}]},
                    },
                },
                "exact_replay_unlock_contract": {
                    "readiness_checklist": {
                        "ready_to_run_full_exact_replay": False,
                        "exact_replay_profitability_verified": False,
                    },
                },
            }
        )

        measurement = plan["read_only_recovery_distance_measurement_plan"]

        self.assertEqual(measurement["not_before_user_local"], "2026-05-22T08:10:00-06:00")
        self.assertEqual(measurement["window_end_user_local"], "2026-05-22T14:00:00-06:00")
        self.assertEqual(measurement["fresh_scan_window_status"], "fresh_scan_due_window")
        self.assertTrue(measurement["fresh_scan_can_run_now"])
        self.assertEqual(measurement["distance_measurement_missing_field_count"], 3)
        self.assertEqual(
            measurement["distance_measurement_missing_fields_by_symbol"],
            {"AA": ["momentum_signal_distance_pct", "price", "sma20"]},
        )

    def test_build_previous_auxiliary_proof_event_outcome_keeps_clock_guard_when_not_due(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "waiting_until_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                }
            ]
        }
        current = {"generated_at": "2026-05-22T13:00:00Z"}

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "not_due_yet")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertFalse(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], ["waiting_until_not_before:2026-05-22T14:10:00Z"])

    def test_build_previous_auxiliary_proof_event_outcome_waits_for_post_event_market_data(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                }
            ]
        }
        current = {
            "generated_at": "2026-05-21T20:20:51Z",
            "derived_refresh": {
                "refreshed_at_utc": "2026-05-22T14:15:00Z",
                "market_data_commands_run": False,
            },
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "ready_to_run_auxiliary_proof_event")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertFalse(outcome["material_progress"])
        self.assertEqual(
            outcome["blockers"],
            ["auxiliary_proof_event_due_but_current_report_has_no_post_event_market_data"],
        )
        self.assertEqual(outcome["outcome_detail"]["market_data_generated_at"], "2026-05-21T20:20:51Z")
        self.assertEqual(outcome["outcome_detail"]["derived_refresh_refreshed_at_utc"], "2026-05-22T14:15:00Z")

    def test_build_previous_auxiliary_proof_event_outcome_marks_distance_progress(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                    "partial_distance_measurement_count": 3,
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                    "gap_symbols_by_drop": {"momentum": ["AA", "BHP", "CEG"]},
                }
            ],
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-22T14:20:00Z",
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                }
            },
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "fresh_quotes"},
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measured_count": 8,
                "read_only_recovery_distance_measurement_gap_count": 2,
                "read_only_recovery_distance_measurement_plan": {
                    "gap_symbols_by_drop": {"momentum": ["BHP", "CEG"]},
                },
                "read_only_recovery_distance_measurement_gaps": [
                    {"symbol": "BHP", "missing_fields": ["sma20"]},
                    {"symbol": "CEG", "missing_fields": ["sma20"]},
                ],
            },
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "material_progress")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_gap_count_before"], 3)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_gap_count_after"], 2)
        self.assertEqual(outcome["outcome_detail"]["distance_measured_count_before"], 6)
        self.assertEqual(outcome["outcome_detail"]["distance_measured_count_after"], 8)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_missing_field_count_before"], 9)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_missing_field_count_after"], 2)
        self.assertEqual(
            outcome["outcome_detail"]["filled_missing_fields_by_symbol"]["AA"],
            ["momentum_signal_distance_pct", "price", "sma20"],
        )
        self.assertEqual(
            outcome["outcome_detail"]["filled_missing_fields_by_symbol"]["BHP"],
            ["momentum_signal_distance_pct", "price"],
        )
        self.assertEqual(outcome["outcome_detail"]["still_missing_fields_by_symbol"]["BHP"], ["sma20"])
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertTrue(checks["distance_measurement_gap_count_decreased"]["passed"])
        self.assertTrue(checks["distance_measured_count_increased"]["passed"])
        self.assertTrue(checks["distance_measurement_missing_field_count_decreased"]["passed"])
        self.assertTrue(checks["distance_measurement_missing_fields_filled"]["passed"])

    def test_build_previous_auxiliary_proof_event_outcome_marks_missing_field_progress(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                    "gap_symbols_by_drop": {"momentum": ["AA", "BHP", "CEG"]},
                }
            ],
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-22T14:20:00Z",
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                }
            },
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "fresh_quotes"},
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measured_count": 6,
                "read_only_recovery_distance_measurement_gap_count": 3,
                "read_only_recovery_distance_measurement_gaps": [
                    {"symbol": "AA", "missing_fields": ["sma20"]},
                    {"symbol": "BHP", "missing_fields": ["sma20"]},
                    {"symbol": "CEG", "missing_fields": ["sma20"]},
                ],
            },
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "material_progress")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_gap_count_before"], 3)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_gap_count_after"], 3)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_missing_field_count_before"], 9)
        self.assertEqual(outcome["outcome_detail"]["distance_measurement_missing_field_count_after"], 3)
        self.assertEqual(
            outcome["outcome_detail"]["filled_missing_fields_by_symbol"]["AA"],
            ["momentum_signal_distance_pct", "price"],
        )
        self.assertEqual(outcome["outcome_detail"]["still_missing_fields_by_symbol"]["AA"], ["sma20"])
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertFalse(checks["distance_measurement_gap_count_decreased"]["passed"])
        self.assertTrue(checks["distance_measurement_missing_field_count_decreased"]["passed"])
        self.assertTrue(checks["distance_measurement_missing_fields_filled"]["passed"])

    def test_build_previous_auxiliary_proof_event_outcome_marks_raw_drop_reason_audit_progress(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                    "partial_distance_measurement_count": 3,
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                }
            ],
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-22T14:20:00Z",
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                }
            },
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "fresh_quotes"},
                "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                "scan_drop_reason_count": 12,
                "scan_drop_reason_symbols_by_drop": {"momentum": ["AA", "BHP", "CEG"]},
                "scan_drop_reason_derived_fields_by_drop": {
                    "momentum": ["momentum_signal_distance_pct", "price", "sma20"]
                },
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measured_count": 6,
                "read_only_recovery_partial_distance_measurement_count": 3,
                "read_only_recovery_distance_measurement_gap_count": 3,
                "read_only_recovery_distance_measurement_plan": {
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                },
            },
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "material_progress")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(
            outcome["outcome_detail"]["scan_drop_reason_audit_status_before"],
            "waiting_for_next_scan_result_with_raw_drop_reasons",
        )
        self.assertEqual(
            outcome["outcome_detail"]["scan_drop_reason_audit_status_after"],
            "raw_drop_reasons_recorded",
        )
        self.assertEqual(outcome["outcome_detail"]["scan_drop_reason_count_after"], 12)
        self.assertEqual(
            outcome["outcome_detail"]["scan_drop_reason_symbols_by_drop_after"],
            {"momentum": ["AA", "BHP", "CEG"]},
        )
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertTrue(checks["scan_drop_reason_audit_recorded"]["passed"])
        self.assertTrue(checks["scan_drop_reason_count_positive"]["passed"])
        self.assertFalse(checks["distance_measurement_gap_count_decreased"]["passed"])

    def test_build_previous_auxiliary_proof_event_outcome_marks_goal_requirement_unblocked(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                    "no_mutation_guard": "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
                }
            ],
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-22T14:20:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": True,
                },
                "live_scan_candidate_symbols": ["FCX"],
            },
            "scan": {
                "candidate_count": 1,
                "candidate_symbols": ["FCX"],
                "quote_freshness_context": {"status": "fresh_quotes"},
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measured_count": 6,
                "read_only_recovery_distance_measurement_gap_count": 3,
            },
            "fresh_scan_post_run_evaluation": {
                "status": "fresh_scan_candidate_verified_for_exact_proof",
                "candidate_count": 1,
                "candidate_symbols": ["FCX"],
                "blockers": [],
            },
            "auxiliary_proof_event_queue": [],
            "previous_auxiliary_proof_event_outcome": {},
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)
        current["previous_auxiliary_proof_event_outcome"] = outcome

        self.assertEqual(outcome["status"], "goal_requirement_unblocked")
        self.assertTrue(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(outcome["outcome_detail"]["candidate_symbols_after"], ["FCX"])
        summary = build_compact_progress_summary(current)
        self.assertEqual(summary["previous_auxiliary_proof_event_status"], "goal_requirement_unblocked")
        self.assertTrue(summary["previous_auxiliary_proof_event_advanced_goal_requirement"])
        payload = build_next_execution_cli_payload(
            current,
            reference_now=datetime(2026, 5, 22, 14, 20, tzinfo=UTC),
        )
        self.assertEqual(payload["previous_auxiliary_proof_event_status"], "goal_requirement_unblocked")
        markdown = render_markdown(current)
        self.assertIn("## Previous Auxiliary Proof Event Outcome", markdown)
        self.assertIn("`goal_requirement_unblocked`", markdown)

    def test_build_previous_auxiliary_proof_event_outcome_records_no_progress_blockers(self):
        previous = {
            "auxiliary_proof_event_queue": [
                {
                    "event_kind": "read_only_distance_measurement_fresh_scan",
                    "status": "ready_to_run_auxiliary_proof_event",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "not_before_utc": "2026-05-22T14:10:00Z",
                    "not_before_user_local": "2026-05-22T08:10:00-06:00",
                    "window_end_utc": "2026-05-22T20:00:00Z",
                    "window_end_user_local": "2026-05-22T14:00:00-06:00",
                    "distance_measurement_gap_count": 3,
                    "distance_measured_count": 6,
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                }
            ],
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-22T14:20:00Z",
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                }
            },
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "stale_quote_blocked"},
            },
            "live_candidate_recovery_plan": {
                "read_only_recovery_distance_measured_count": 6,
                "read_only_recovery_distance_measurement_gap_count": 3,
                "read_only_recovery_distance_measurement_plan": {
                    "distance_measurement_missing_field_count": 9,
                    "distance_measurement_missing_fields_by_symbol": {
                        "AA": ["momentum_signal_distance_pct", "price", "sma20"],
                        "BHP": ["momentum_signal_distance_pct", "price", "sma20"],
                        "CEG": ["momentum_signal_distance_pct", "price", "sma20"],
                    },
                },
            },
        }

        outcome = build_previous_auxiliary_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "no_material_progress")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertFalse(outcome["material_progress"])
        self.assertIn("distance_measurement_gap_count_unchanged", outcome["blockers"])
        self.assertIn("distance_measured_count_not_increased", outcome["blockers"])
        self.assertIn("distance_measurement_missing_fields_by_symbol_unchanged", outcome["blockers"])
        self.assertIn("fresh_scan_candidate_count_still_zero", outcome["blockers"])
        self.assertIn("quote_freshness_still_stale_inside_fresh_window", outcome["blockers"])

    def test_build_previous_proof_event_outcome_marks_live_candidate_requirement_unblocked(self):
        previous = {
            "generated_at": "2026-05-21T07:30:00Z",
            "next_proof_event_checkpoint": {
                "status": "waiting_until_next_proof_event",
                "event_kind": "fresh_opra_live_candidate_scan",
                "selected_step": "fresh_opra_live_scan",
                "target_goal_requirement": "live_scan_has_verifiable_candidate",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
            },
            "scan": {"candidate_count": 0},
        }
        current = {
            "generated_at": "2026-05-21T14:20:00Z",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": True,
                },
                "live_scan_candidate_symbols": ["FCX"],
            },
            "scan": {
                "candidate_count": 1,
                "candidate_symbols": ["FCX"],
                "quote_freshness_context": {"status": "fresh_quotes"},
                "fresh_scan_retest_plan": {"primary_probe_quote_age_excess_hours": 0.0},
            },
            "fresh_scan_post_run_evaluation": {
                "status": "fresh_scan_candidate_verified_for_exact_proof",
                "next_action": "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
                "next_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "blockers": [],
                "profitability_gate_effect": "live_scan_is_entry_evidence_only_exact_bid_ask_replay_still_required",
            },
        }

        outcome = build_previous_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "goal_requirement_unblocked")
        self.assertEqual(outcome["event_kind"], "fresh_opra_live_candidate_scan")
        self.assertEqual(outcome["target_goal_requirement"], "live_scan_has_verifiable_candidate")
        self.assertTrue(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], [])
        self.assertEqual(outcome["outcome_detail"]["candidate_count_before"], 0)
        self.assertEqual(outcome["outcome_detail"]["candidate_count_after"], 1)
        self.assertEqual(outcome["outcome_detail"]["candidate_symbols_after"], ["FCX"])
        self.assertEqual(
            outcome["outcome_detail"]["fresh_scan_post_run_status_after"],
            "fresh_scan_candidate_verified_for_exact_proof",
        )
        self.assertEqual(
            outcome["outcome_detail"]["fresh_scan_post_run_next_command_after"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(outcome["outcome_detail"]["fresh_scan_post_run_blockers_after"], [])
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertTrue(checks["live_scan_candidate_count_above_zero"]["passed"])
        self.assertTrue(checks["live_scan_has_candidate_gate_true"]["passed"])
        self.assertTrue(checks["live_scan_candidate_inside_exact_proof_gate_true"]["passed"])

    def test_build_previous_proof_event_outcome_records_capture_isolation_blocker(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "next_proof_event_checkpoint": {
                "status": "waiting_until_next_proof_event",
                "event_kind": "exact_opra_history_capture",
                "selected_step": "post_close_full_universe_capture",
                "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "not_before_utc": "2026-05-21T20:20:00Z",
                "not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "proof_window": {"current_shared_quote_dates": 1, "remaining_shared_quote_dates": 99},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                },
            },
            "proof_window": {"current_shared_quote_dates": 2, "remaining_shared_quote_dates": 98},
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "proof_source_isolation_contract": {
                "status": "proof_source_isolation_blocked",
                "blockers": ["top_level_shared_dates_match_proof_source_shared_dates"],
            },
            "exact_capture_progress_outcome": {
                "status": "exact_capture_progress_partial_with_import_blockers",
                "blockers": ["proof_source_isolation_contract_clean_after_capture"],
            },
        }

        outcome = build_previous_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "material_progress")
        self.assertEqual(outcome["event_kind"], "exact_opra_history_capture")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertTrue(outcome["material_progress"])
        self.assertIn("proof_source_isolation_contract_blocked_after_capture", outcome["blockers"])
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertFalse(checks["proof_source_isolation_contract_clean_after_capture"]["passed"])
        self.assertEqual(
            outcome["outcome_detail"]["proof_source_isolation_blockers_after"],
            ["top_level_shared_dates_match_proof_source_shared_dates"],
        )
        self.assertEqual(
            outcome["outcome_detail"]["exact_capture_progress_outcome_status_after"],
            "exact_capture_progress_partial_with_import_blockers",
        )

    def test_build_previous_proof_event_outcome_records_local_store_mismatch_blocker(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "next_proof_event_checkpoint": {
                "status": "waiting_until_next_proof_event",
                "event_kind": "exact_opra_history_capture",
                "selected_step": "post_close_full_universe_capture",
                "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "not_before_utc": "2026-05-21T20:20:00Z",
                "not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "proof_window": {"current_shared_quote_dates": 1, "remaining_shared_quote_dates": 99},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                },
            },
            "proof_window": {"current_shared_quote_dates": 2, "remaining_shared_quote_dates": 98},
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "proof_source_isolation_contract": {
                "status": "isolated_to_alpaca_opra_proof_source",
                "blockers": [],
            },
            "exact_capture_progress_outcome": {
                "status": "exact_capture_progress_partial_with_import_blockers",
                "blockers": [
                    "local_exact_store_matches_proof_window_after_capture",
                    "local_exact_store_has_no_pending_refresh_after_capture",
                ],
                "checks": [
                    {
                        "name": "local_exact_store_matches_proof_window_after_capture",
                        "passed": False,
                        "actual": False,
                        "expected": True,
                    },
                    {
                        "name": "local_exact_store_has_no_pending_refresh_after_capture",
                        "passed": False,
                        "actual": True,
                        "expected": False,
                    },
                ],
                "evidence": {
                    "local_exact_store_usage_decision": (
                        "refresh_derived_history_from_local_alpaca_opra_store_before_waiting_for_forward_capture"
                    ),
                    "local_exact_store_refresh_can_advance_history_depth": True,
                    "local_exact_available_shared_quote_dates": 3,
                    "local_exact_store_matches_proof_window": False,
                },
            },
        }

        outcome = build_previous_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "material_progress")
        self.assertIn(
            "exact_capture_progress:local_exact_store_matches_proof_window_after_capture",
            outcome["blockers"],
        )
        self.assertIn(
            "exact_capture_progress:local_exact_store_has_no_pending_refresh_after_capture",
            outcome["blockers"],
        )
        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertFalse(checks["local_exact_store_matches_proof_window_after_capture"]["passed"])
        self.assertFalse(checks["local_exact_store_has_no_pending_refresh_after_capture"]["passed"])
        self.assertEqual(
            outcome["outcome_detail"]["local_exact_store_usage_decision_after"],
            "refresh_derived_history_from_local_alpaca_opra_store_before_waiting_for_forward_capture",
        )
        self.assertTrue(outcome["outcome_detail"]["local_exact_store_refresh_can_advance_history_depth_after"])
        self.assertEqual(outcome["outcome_detail"]["local_exact_available_shared_quote_dates_after"], 3)
        self.assertFalse(outcome["outcome_detail"]["local_exact_store_matches_proof_window_after"])

    def test_build_previous_proof_event_outcome_uses_backfill_audit_for_local_store_checks(self):
        previous = {
            "generated_at": "2026-05-21T16:00:00Z",
            "next_proof_event_checkpoint": {
                "status": "waiting_until_next_proof_event",
                "event_kind": "exact_opra_history_capture",
                "selected_step": "post_close_full_universe_capture",
                "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "not_before_utc": "2026-05-21T20:20:00Z",
                "not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "proof_window": {"current_shared_quote_dates": 1, "remaining_shared_quote_dates": 99},
        }
        current = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                },
            },
            "proof_window": {"current_shared_quote_dates": 2, "remaining_shared_quote_dates": 98},
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "proof_source_isolation_contract": {
                "status": "isolated_to_alpaca_opra_proof_source",
                "blockers": [],
            },
            "exact_history_backfill_capability_audit": {
                "local_exact_store_usage_decision": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                "local_exact_store_refresh_can_advance_history_depth": False,
                "local_exact_available_shared_quote_dates": 2,
                "local_exact_store_matches_proof_window": True,
            },
            "exact_capture_progress_outcome": {
                "status": "exact_capture_progress_verified",
                "blockers": [],
            },
        }

        outcome = build_previous_proof_event_outcome(previous, current)

        checks = {check["name"]: check for check in outcome["checks"]}
        self.assertTrue(checks["local_exact_store_matches_proof_window_after_capture"]["passed"])
        self.assertTrue(checks["local_exact_store_has_no_pending_refresh_after_capture"]["passed"])
        self.assertEqual(
            outcome["outcome_detail"]["local_exact_store_usage_decision_after"],
            "current_artifact_counts_all_local_alpaca_opra_shared_dates",
        )
        self.assertFalse(outcome["outcome_detail"]["local_exact_store_refresh_can_advance_history_depth_after"])
        self.assertEqual(outcome["outcome_detail"]["local_exact_available_shared_quote_dates_after"], 2)
        self.assertTrue(outcome["outcome_detail"]["local_exact_store_matches_proof_window_after"])

    def test_flat_payloads_expose_previous_proof_event_local_store_evidence(self):
        report = {
            "generated_at": "2026-05-21T20:20:51Z",
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "alpaca_enabled": True,
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {},
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
            },
            "automation_health": {"healthy": True},
            "scan": {"candidate_count": 0, "candidate_symbols": []},
            "capture": {},
            "readiness": {},
            "replay": {},
            "diagnostic_replay": {},
            "last_execution_review": {
                "status": "passed",
                "previous_selected_step": "post_close_full_universe_capture",
                "checks": [
                    {"name": "local_exact_store_matches_proof_window_after_capture", "passed": True},
                    {"name": "local_exact_store_has_no_pending_refresh_after_capture", "passed": True},
                ],
                "blockers": [],
                "local_exact_store_usage_decision_after": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                "local_exact_store_refresh_can_advance_history_depth_after": False,
                "local_exact_available_shared_quote_dates_after": 2,
                "local_exact_store_matches_proof_window_after": True,
            },
            "previous_proof_event_outcome": {
                "status": "material_progress",
                "event_kind": "exact_opra_history_capture",
                "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                "advanced_goal_requirement": False,
                "material_progress": True,
                "blockers": [],
                "checks": [
                    {"name": "local_exact_store_matches_proof_window_after_capture", "passed": True},
                    {"name": "local_exact_store_has_no_pending_refresh_after_capture", "passed": True},
                ],
                "outcome_detail": {
                    "local_exact_store_usage_decision_after": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                    "local_exact_store_refresh_can_advance_history_depth_after": False,
                    "local_exact_available_shared_quote_dates_after": 2,
                    "local_exact_store_matches_proof_window_after": True,
                },
            },
        }

        summary = build_compact_progress_summary(report)
        payload = build_next_execution_cli_payload(report)

        for flattened in (summary, payload):
            self.assertEqual(
                flattened["last_execution_local_exact_store_usage_decision"],
                "current_artifact_counts_all_local_alpaca_opra_shared_dates",
            )
            self.assertFalse(
                flattened["last_execution_local_exact_store_refresh_can_advance_history_depth"]
            )
            self.assertEqual(flattened["last_execution_local_exact_available_shared_quote_dates"], 2)
            self.assertTrue(flattened["last_execution_local_exact_store_matches_proof_window"])
            self.assertEqual(
                flattened["previous_proof_event_local_exact_store_usage_decision"],
                "current_artifact_counts_all_local_alpaca_opra_shared_dates",
            )
            self.assertFalse(
                flattened["previous_proof_event_local_exact_store_refresh_can_advance_history_depth"]
            )
            self.assertEqual(
                flattened["previous_proof_event_local_exact_available_shared_quote_dates"],
                2,
            )
            self.assertTrue(flattened["previous_proof_event_local_exact_store_matches_proof_window"])

    def test_render_markdown_exposes_previous_proof_event_local_store_evidence(self):
        markdown = render_markdown(
            {
                "generated_at": "2026-05-21T20:20:51Z",
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 98,
                },
                "automation_health": {"healthy": True},
                "scan": {"candidate_count": 0, "candidate_symbols": []},
                "capture": {},
                "readiness": {},
                "replay": {},
                "diagnostic_replay": {},
                "previous_proof_event_outcome": {
                    "status": "material_progress",
                    "event_kind": "exact_opra_history_capture",
                    "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                    "advanced_goal_requirement": False,
                    "material_progress": True,
                    "checks": [
                        {"name": "local_exact_store_matches_proof_window_after_capture", "passed": True},
                    ],
                    "blockers": [],
                    "outcome_detail": {
                        "local_exact_store_usage_decision_after": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                        "local_exact_store_refresh_can_advance_history_depth_after": False,
                        "local_exact_available_shared_quote_dates_after": 2,
                        "local_exact_store_matches_proof_window_after": True,
                    },
                },
            }
        )

        self.assertIn("## Previous Proof Event Outcome", markdown)
        self.assertIn(
            "Local exact store usage decision after event: `current_artifact_counts_all_local_alpaca_opra_shared_dates`",
            markdown,
        )
        self.assertIn("Local exact store can advance history depth after event: `False`", markdown)
        self.assertIn("Local exact store dates after event: `2`", markdown)
        self.assertIn("Local exact store matches proof window after event: `True`", markdown)

    def test_render_markdown_exposes_last_execution_local_store_evidence(self):
        markdown = render_markdown(
            {
                "generated_at": "2026-05-21T20:20:51Z",
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "verification_gate": {"status": "not_verified", "verified": False, "gates": {}},
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 2,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 98,
                },
                "automation_health": {"healthy": True},
                "scan": {"candidate_count": 0, "candidate_symbols": []},
                "capture": {},
                "readiness": {},
                "replay": {},
                "diagnostic_replay": {},
                "last_execution_review": {
                    "status": "passed",
                    "previous_selected_step": "post_close_full_universe_capture",
                    "checks": [
                        {"name": "local_exact_store_matches_proof_window_after_capture", "passed": True},
                    ],
                    "blockers": [],
                    "local_exact_store_usage_decision_after": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                    "local_exact_store_refresh_can_advance_history_depth_after": False,
                    "local_exact_available_shared_quote_dates_after": 2,
                    "local_exact_store_matches_proof_window_after": True,
                },
            }
        )

        self.assertIn("## Last Execution Review", markdown)
        self.assertIn(
            "Local exact store usage decision after last execution: `current_artifact_counts_all_local_alpaca_opra_shared_dates`",
            markdown,
        )
        self.assertIn("Local exact store can advance history depth after last execution: `False`", markdown)
        self.assertIn("Local exact store dates after last execution: `2`", markdown)
        self.assertIn("Local exact store matches proof window after last execution: `True`", markdown)

    def test_build_previous_proof_event_outcome_keeps_clock_guard_when_not_due(self):
        previous = {
            "next_proof_event_checkpoint": {
                "event_kind": "fresh_opra_live_candidate_scan",
                "selected_step": "fresh_opra_live_scan",
                "target_goal_requirement": "live_scan_has_verifiable_candidate",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
            }
        }
        current = {"generated_at": "2026-05-21T10:00:00Z"}

        outcome = build_previous_proof_event_outcome(previous, current)

        self.assertEqual(outcome["status"], "not_due_yet")
        self.assertFalse(outcome["advanced_goal_requirement"])
        self.assertFalse(outcome["material_progress"])
        self.assertEqual(outcome["blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])

    def test_build_fresh_scan_iteration_decision_waits_for_fresh_opra_window(self):
        report = {
            "lane_next_step": {
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
            },
            "goal_completion_audit": {
                "failed_requirements": ["live_scan_has_verifiable_candidate"],
            },
            "exact_history_acquisition_plan": {
                "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "next_fresh_scan": {
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                    },
                },
                "fresh_scan_retest_plan": {
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "primary_probe_symbol": "FCX",
                    "primary_probe_quote_age_excess_hours": 3.4,
                    "quote_age_only_blocker_symbols": ["FCX"],
                    "structural_liquidity_blocker_symbols": ["ALB"],
                },
                "scan_funnel": {"drop_counts": {"option_liquidity": 8, "ev_floor": 3}},
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 8,
                        "example_symbols": ["FCX", "ALB"],
                        "next_diagnostic_action": "after_fresh_quotes_recheck_quote_age_then_structural_spread_distance",
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
            },
            "last_execution_review": {
                "previous_selected_step": "fresh_opra_live_scan",
                "status": "not_due_yet",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
        }

        decision = build_fresh_scan_iteration_decision(report)

        self.assertEqual(decision["status"], "waiting_for_fresh_opra_scan")
        self.assertEqual(decision["branch"], "clock_guard_branch")
        self.assertEqual(decision["next_action"], "run_fresh_opra_scan_at_not_before_time")
        self.assertFalse(decision["safe_to_tune_filters"])
        self.assertEqual(decision["primary_probe_symbol"], "FCX")
        self.assertEqual(decision["quote_age_only_blocker_symbols"], ["FCX"])
        self.assertEqual(decision["structural_liquidity_blocker_symbols"], ["ALB"])
        self.assertEqual(
            decision["top_drop_counts"],
            [{"drop_key": "option_liquidity", "count": 8}, {"drop_key": "ev_floor", "count": 3}],
        )
        self.assertEqual(decision["zero_candidate_diagnostic_plan"][0]["example_symbols"], ["FCX", "ALB"])
        self.assertEqual(
            decision["zero_candidate_diagnostic_plan"][0]["production_filter_action"],
            "preserve_filters_until_exact_replay_unlock",
        )
        self.assertEqual(
            decision["post_run_playbook"][0]["next_action"],
            "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
        )
        self.assertEqual(
            decision["post_run_playbook"][1]["diagnostic_drop_keys"],
            ["option_liquidity"],
        )
        self.assertEqual(
            decision["post_run_playbook"][2]["filter_policy"],
            "treat_as_data_freshness_issue_not_filter_issue",
        )
        self.assertEqual(decision["post_run_playbook_status"], "pending_fresh_scan_execution")
        self.assertIsNone(decision["selected_post_run_condition"])
        self.assertIsNone(decision["selected_post_run_next_action"])
        self.assertIsNone(decision["selected_fresh_scan_outcome"])
        self.assertEqual(
            decision["fresh_scan_outcome_matrix"][0]["condition"],
            "fresh_scan_candidate_count_above_zero",
        )
        self.assertEqual(
            decision["fresh_scan_outcome_matrix"][0]["goal_requirement_effect"],
            "can_unblock_if_candidate_is_inside_exact_proof_universe",
        )
        self.assertEqual(
            decision["fresh_scan_outcome_matrix"][0]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            decision["fresh_scan_outcome_matrix"][0]["next_not_before_user_local"],
            "2026-05-21T14:20:00-06:00",
        )
        self.assertEqual(
            decision["fresh_scan_outcome_matrix"][1]["diagnostic_drop_keys"],
            ["option_liquidity"],
        )
        self.assertEqual(decision["blocked_goal_requirements"], ["live_scan_has_verifiable_candidate"])

    def test_build_fresh_scan_iteration_decision_branches_after_zero_candidate_fresh_scan(self):
        report = {
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                "scan_funnel": {"drop_counts": {"tech_score": 4, "option_liquidity": 7}},
            },
            "last_execution_review": {
                "previous_selected_step": "fresh_opra_live_scan",
                "status": "failed",
                "blockers": ["fresh_scan_candidate_count_above_zero"],
            },
        }

        decision = build_fresh_scan_iteration_decision(report)

        self.assertEqual(decision["status"], "fresh_scan_zero_candidates_structural_review")
        self.assertEqual(decision["branch"], "structural_blocker_branch")
        self.assertEqual(decision["next_action"], "rank_remaining_drop_counts_without_relaxing_production_filters")
        self.assertEqual(decision["last_fresh_scan_review_status"], "failed")
        self.assertEqual(decision["last_fresh_scan_review_blockers"], ["fresh_scan_candidate_count_above_zero"])
        self.assertEqual(
            decision["top_drop_counts"],
            [{"drop_key": "option_liquidity", "count": 7}, {"drop_key": "tech_score", "count": 4}],
        )
        self.assertEqual(
            decision["post_run_playbook"][1]["diagnostic_drop_keys"],
            ["option_liquidity", "tech_score"],
        )
        self.assertEqual(decision["post_run_playbook_status"], "selected")
        self.assertEqual(decision["selected_post_run_condition"], "quote_freshness_cleared_and_candidates_still_zero")
        self.assertEqual(
            decision["selected_post_run_next_action"],
            "review_raw_scan_drop_reasons_without_relaxing_production_filters",
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome_effect"],
            "remains_blocked_records_raw_scan_drop_reasons",
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome"]["evidence_fields"],
            [
                "scan.quote_freshness_context.status",
                "scan.candidate_count",
                "scan.scan_drop_reason_audit_status",
                "scan.scan_drop_reason_count",
                "scan.scan_drop_reason_symbols_by_drop",
                "scan.scan_drop_reason_examples_by_symbol",
                "fresh_scan_iteration_decision.top_drop_counts",
                "fresh_scan_iteration_decision.zero_candidate_diagnostic_plan",
            ],
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status == raw_drop_reasons_recorded",
            decision["selected_fresh_scan_outcome"]["material_progress_if"],
        )
        self.assertIn(
            "scan_drop_reason_count_zero_or_missing",
            decision["selected_fresh_scan_outcome"]["no_progress_blockers_if"],
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome_next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )

    def test_build_fresh_scan_iteration_decision_does_not_rewait_after_failed_stale_scan(self):
        report = {
            "lane_next_step": {
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "next_fresh_scan": {
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                    },
                },
                "fresh_scan_retest_plan": {
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "primary_probe_symbol": "FCX",
                    "primary_probe_quote_age_excess_hours": 1.4,
                },
                "scan_funnel": {"drop_counts": {"option_liquidity": 9}},
            },
            "last_execution_review": {
                "previous_selected_step": "fresh_opra_live_scan",
                "status": "failed",
                "blockers": [
                    "quote_freshness_status_not_stale_quote_sensitive_or_blocked",
                    "primary_probe_quote_age_excess_hours_at_or_below_zero",
                ],
            },
        }

        decision = build_fresh_scan_iteration_decision(report)

        self.assertEqual(decision["status"], "fresh_scan_data_freshness_still_blocked")
        self.assertEqual(decision["branch"], "data_freshness_branch")
        self.assertEqual(decision["next_action"], "rerun_fresh_opra_scan_inside_window_or_inspect_feed_timing")
        self.assertEqual(decision["last_fresh_scan_review_status"], "failed")
        self.assertEqual(
            decision["last_fresh_scan_review_blockers"],
            [
                "quote_freshness_status_not_stale_quote_sensitive_or_blocked",
                "primary_probe_quote_age_excess_hours_at_or_below_zero",
            ],
        )
        self.assertEqual(decision["post_run_playbook_status"], "selected")
        self.assertEqual(decision["selected_post_run_condition"], "quote_freshness_still_stale_inside_fresh_window")
        self.assertEqual(
            decision["selected_post_run_next_action"],
            "inspect_alpaca_opra_feed_timing_or_rerun_inside_window_before_filter_changes",
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome_effect"],
            "remains_blocked_as_data_freshness_issue",
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome_next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )

    def test_build_fresh_scan_iteration_decision_preserves_filters_when_candidate_appears(self):
        report = {
            "scan": {
                "candidate_count": 1,
                "candidate_symbols": ["FCX"],
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
            },
            "scan_proof_universe_alignment": {
                "candidate_symbols": ["FCX"],
            },
        }

        decision = build_fresh_scan_iteration_decision(report)

        self.assertEqual(decision["status"], "candidate_evidence_found")
        self.assertEqual(decision["branch"], "live_candidate_branch")
        self.assertEqual(decision["next_action"], "preserve_filters_and_wait_for_exact_replay_profitability_gate")
        self.assertEqual(decision["candidate_symbols"], ["FCX"])
        self.assertFalse(decision["safe_to_tune_filters"])
        self.assertEqual(decision["post_run_playbook_status"], "selected")
        self.assertEqual(decision["selected_post_run_condition"], "fresh_scan_candidate_count_above_zero")
        self.assertEqual(
            decision["selected_post_run_next_action"],
            "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
        )
        self.assertEqual(
            decision["selected_fresh_scan_outcome_effect"],
            "can_unblock_if_candidate_is_inside_exact_proof_universe",
        )
        self.assertIn(
            "verification_gate.gates.live_scan_candidate_inside_exact_proof_universe",
            decision["selected_fresh_scan_outcome"]["evidence_fields"],
        )

    def test_build_fresh_scan_post_run_evaluation_verifies_candidate_against_alpaca_proof_source(self):
        report = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "remaining_shared_quote_dates": 99,
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "trusted_only": True,
                "all_required_symbols_have_proof_source_data": True,
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "proof_source_required_symbol_coverage": {
                    "available_required_symbol_count": 24,
                    "required_symbol_count": 24,
                },
            },
            "exact_history_acquisition_plan": {
                "remaining_shared_quote_dates": 99,
                "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": True,
                    "live_scan_candidate_inside_exact_proof_universe": True,
                    "proof_scan_universe_aligned": True,
                },
                "live_scan_candidate_symbols": ["FCX"],
            },
            "scan_proof_universe_alignment": {
                "candidate_symbols": ["FCX"],
                "candidate_symbols_outside_exact_proof": [],
            },
            "scan": {
                "candidate_count": 1,
                "candidate_symbols": ["FCX"],
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
            },
            "goal_completion_audit": {"may_mark_goal_complete": False},
        }

        evaluation = build_fresh_scan_post_run_evaluation(report)

        self.assertEqual(evaluation["status"], "fresh_scan_candidate_verified_for_exact_proof")
        self.assertEqual(
            evaluation["next_action"],
            "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
        )
        self.assertEqual(
            evaluation["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(evaluation["next_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(evaluation["candidate_symbols"], ["FCX"])
        self.assertEqual(evaluation["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertTrue(evaluation["proof_source_trusted_only"])
        self.assertEqual(evaluation["remaining_exact_shared_quote_dates"], 99)
        self.assertEqual(evaluation["blockers"], [])
        self.assertFalse(evaluation["safe_to_tune_filters"])
        self.assertEqual(
            evaluation["profitability_gate_effect"],
            "live_scan_is_entry_evidence_only_exact_bid_ask_replay_still_required",
        )
        checks = {check["name"]: check for check in evaluation["checks"]}
        self.assertTrue(checks["provider_is_alpaca_sip_opra"]["passed"])
        self.assertTrue(checks["proof_source_is_alpaca_opra_daily_snapshot"]["passed"])
        self.assertTrue(checks["proof_source_trusted_only"]["passed"])
        self.assertTrue(checks["all_required_symbols_have_proof_source_data"]["passed"])
        self.assertTrue(checks["live_scan_candidate_inside_exact_proof_gate_true"]["passed"])

    def test_build_fresh_scan_post_run_evaluation_keeps_filters_locked_after_zero_candidate_fresh_scan(self):
        report = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "remaining_shared_quote_dates": 99,
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "trusted_only": True,
                "all_required_symbols_have_proof_source_data": True,
                "proof_source_shared_quote_dates": {"count": 1},
            },
            "verification_gate": {
                "gates": {
                    "live_scan_has_candidate": False,
                    "live_scan_candidate_inside_exact_proof_universe": False,
                    "proof_scan_universe_aligned": True,
                },
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                "scan_drop_reason_count": 2,
                "scan_drop_reason_symbols_by_drop": {
                    "option_liquidity": ["FCX"],
                    "tech_score": ["CCJ"],
                },
                "scan_drop_reason_examples_by_symbol": {
                    "FCX": {"symbol": "FCX", "drop_key": "option_liquidity"},
                    "CCJ": {"symbol": "CCJ", "drop_key": "tech_score"},
                },
                "scan_funnel": {"drop_counts": {"option_liquidity": 7, "tech_score": 3}},
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 7,
                        "example_symbols": ["FCX", "ALB"],
                        "representative_examples": [
                            {
                                "symbol": "FCX",
                                "liquidity_reasons": ["wide_bid_ask_spread"],
                            }
                        ],
                        "next_diagnostic_action": "compare_fresh_quote_spread_distance_before_any_liquidity_filter_change",
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    },
                    {
                        "drop_key": "tech_score",
                        "count": 3,
                        "example_symbols": ["CCJ"],
                        "representative_examples": [
                            {"symbol": "CARR", "tech_score": 36.4, "min_tech_score": 65.0, "tech_score_shortfall": 28.6},
                            {"symbol": "CCJ", "tech_score": 59.8, "min_tech_score": 65.0, "tech_score_shortfall": 5.2},
                        ],
                        "next_diagnostic_action": "rank_symbols_by_tech_score_shortfall_and_exact_replay_pnl_after_unlock",
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    },
                ],
            },
            "goal_completion_audit": {"may_mark_goal_complete": False},
        }

        evaluation = build_fresh_scan_post_run_evaluation(report)

        self.assertEqual(evaluation["status"], "fresh_scan_zero_candidates_after_fresh_quotes")
        self.assertEqual(evaluation["blockers"], ["fresh_scan_candidate_count_above_zero"])
        self.assertEqual(
            evaluation["next_action"],
            "review_raw_scan_drop_reasons_without_relaxing_production_filters",
        )
        self.assertEqual(
            evaluation["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            evaluation["selected_fresh_scan_condition"],
            "quote_freshness_cleared_and_candidates_still_zero",
        )
        self.assertEqual(
            evaluation["top_drop_counts"],
            [{"drop_key": "option_liquidity", "count": 7}, {"drop_key": "tech_score", "count": 3}],
        )
        self.assertFalse(evaluation["safe_to_tune_filters"])
        self.assertEqual(evaluation["scan_drop_reason_audit_status"], "raw_drop_reasons_recorded")
        self.assertEqual(evaluation["scan_drop_reason_count"], 2)
        self.assertTrue(evaluation["raw_scan_drop_reasons_required"])
        self.assertTrue(evaluation["raw_scan_drop_reasons_recorded"])
        self.assertTrue(evaluation["scan_drop_reason_examples_by_symbol_available"])
        self.assertEqual(
            evaluation["production_filter_policy"],
            "do_not_tune_until_exact_alpaca_opra_replay_profitability_gate_passes",
        )
        checks = {check["name"]: check for check in evaluation["checks"]}
        self.assertTrue(checks["raw_scan_drop_reason_audit_recorded_when_zero_candidate"]["passed"])
        self.assertTrue(checks["raw_scan_drop_reason_count_above_zero_when_zero_candidate"]["passed"])
        structural_review = evaluation["zero_candidate_structural_review"]
        self.assertEqual(structural_review["status"], "ready_after_fresh_quotes_zero_candidates")
        self.assertEqual(
            structural_review["next_action"],
            "review_zero_candidate_diagnostic_plan_without_relaxing_production_filters",
        )
        self.assertFalse(structural_review["safe_to_tune_filters"])
        self.assertFalse(structural_review["allowed_now"])
        self.assertTrue(structural_review["read_only_review_allowed_now"])
        self.assertIn(
            "rank_nearest_zero_candidate_blocker_symbols",
            structural_review["allowed_read_only_actions"],
        )
        self.assertIn("production_filter_changes", structural_review["blocked_mutations"])
        self.assertTrue(structural_review["quote_freshness_cleared"])
        self.assertEqual(structural_review["dominant_drop_key"], "option_liquidity")
        self.assertEqual(structural_review["dominant_drop_count"], 7)
        self.assertEqual(
            structural_review["drop_counts"],
            [{"drop_key": "option_liquidity", "count": 7}, {"drop_key": "tech_score", "count": 3}],
        )
        self.assertEqual(structural_review["diagnostic_drop_keys"], ["option_liquidity", "tech_score"])
        self.assertEqual(structural_review["example_symbols_by_drop"]["option_liquidity"], ["FCX", "ALB"])
        self.assertEqual(
            structural_review["next_diagnostic_actions"]["option_liquidity"],
            "compare_fresh_quote_spread_distance_before_any_liquidity_filter_change",
        )
        self.assertEqual(
            structural_review["production_filter_actions"]["tech_score"],
            "preserve_filters_until_exact_replay_unlock",
        )
        self.assertEqual(
            structural_review["dominant_representative_examples"],
            [{"symbol": "FCX", "liquidity_reasons": ["wide_bid_ask_spread"]}],
        )
        self.assertEqual(
            structural_review["nearest_examples_by_drop"]["option_liquidity"],
            [{"symbol": "FCX", "liquidity_reasons": ["wide_bid_ask_spread"]}],
        )
        self.assertEqual(structural_review["nearest_examples_by_drop"]["tech_score"][0]["symbol"], "CCJ")
        self.assertEqual(structural_review["nearest_examples_by_drop"]["tech_score"][0]["tech_score_shortfall"], 5.2)
        self.assertEqual(
            structural_review["dominant_nearest_examples"],
            [{"symbol": "FCX", "liquidity_reasons": ["wide_bid_ask_spread"]}],
        )
        self.assertEqual(
            structural_review["blocked_until"],
            "exact_alpaca_opra_replay_ready_and_profitability_gate_can_measure_filter_changes",
        )

    def test_build_live_candidate_recovery_plan_locks_filters_after_zero_candidate_fresh_scan(self):
        plan = build_live_candidate_recovery_plan(
            {
                "provider": "alpaca:sip:opra",
                "generated_at": "2026-05-21T21:30:00Z",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                        "proof_scan_universe_aligned": True,
                    }
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "fresh_scan_zero_candidates_after_fresh_quotes",
                    "candidate_count": 0,
                    "candidate_symbols": [],
                    "freshness_cleared": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_trusted_only": True,
                    "proof_scan_universe_aligned": True,
                    "top_drop_counts": [{"drop_key": "tech_score", "count": 9}],
                    "zero_candidate_structural_review": {
                        "dominant_drop_key": "tech_score",
                        "dominant_drop_count": 9,
                        "allowed_read_only_actions": ["rank_nearest_zero_candidate_blocker_symbols"],
                        "blocked_mutations": ["production_filter_changes", "variant_promotion"],
                        "nearest_examples_by_drop": {
                            "tech_score": [{"symbol": "CCJ", "tech_score_shortfall": 5.2}]
                        },
                    },
                },
                "fresh_scan_iteration_decision": {
                    "top_drop_counts": [{"drop_key": "tech_score", "count": 9}],
                },
                "scan": {
                    "quote_freshness_context": {
                        "next_fresh_scan": {
                            "scheduled_utc": "2026-05-22T14:10:00Z",
                            "scheduled_user_local": "2026-05-22T08:10:00-06:00",
                            "window_end_utc": "2026-05-22T20:00:00Z",
                            "window_end_user_local": "2026-05-22T14:00:00-06:00",
                            "scan_calendar": "us_equity_market_days",
                            "scheduled_trade_date_is_market_day": True,
                            "status": "fresh_scan_future",
                            "can_attempt_scan_now": False,
                        }
                    }
                },
                "exact_replay_unlock_contract": {
                    "readiness_checklist": {
                        "status": "waiting_for_exact_opra_history_depth",
                        "ready_to_run_full_exact_replay": False,
                        "exact_replay_profitability_verified": False,
                        "next_command": (
                            "python scripts/run_ai_commodity_opra_progress.py "
                            "--force-capture --target-date 2026-05-21"
                        ),
                        "blockers": ["full_exact_replay_history_depth_available"],
                    },
                },
                "post_fresh_scan_research_backlog": {
                    "unlock_status": "locked_until_exact_replay_can_measure_filter_changes",
                    "activation_blockers": ["enough_exact_shared_quote_dates"],
                    "deferred_variant_promotion_review": {"status": "promotion_blocked"},
                },
            }
        )

        self.assertEqual(plan["status"], "zero_candidates_waiting_for_exact_replay_unlock")
        self.assertEqual(plan["target_goal_requirement"], "live_scan_has_verifiable_candidate")
        capture_command = "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21"
        self.assertEqual(
            plan["next_command"],
            capture_command,
        )
        self.assertEqual(plan["next_command_role"], "history_unlock_before_filter_mutation")
        self.assertEqual(plan["history_unlock_command"], capture_command)
        self.assertEqual(
            plan["live_candidate_scan_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            plan["read_only_review_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        command_roles = {item["role"]: item for item in plan["command_roles"]}
        self.assertTrue(command_roles["history_unlock_before_filter_mutation"]["applies_now"])
        self.assertFalse(command_roles["fresh_live_scan_evidence"]["applies_now"])
        self.assertTrue(command_roles["read_only_zero_candidate_review"]["applies_now"])
        self.assertFalse(plan["safe_to_tune_production_filters"])
        self.assertIn("live_scan_has_candidate", plan["blockers"])
        self.assertIn("exact_replay_ready_to_measure_filter_changes", plan["blockers"])
        self.assertEqual(plan["dominant_drop_key"], "tech_score")
        self.assertEqual(plan["top_drop_counts"], [{"drop_key": "tech_score", "count": 9}])
        self.assertIn("rank_nearest_zero_candidate_blocker_symbols", plan["read_only_actions_allowed_now"])
        self.assertEqual(plan["blocked_mutations"], ["production_filter_changes", "variant_promotion"])
        self.assertEqual(plan["deferred_variant_promotion_status"], "promotion_blocked")
        self.assertEqual(plan["read_only_recovery_queue_count"], 1)
        self.assertEqual(plan["first_read_only_review"]["symbol"], "CCJ")
        self.assertEqual(plan["first_read_only_review"]["drop_key"], "tech_score")
        self.assertEqual(plan["first_read_only_review"]["distance_to_current_filter"], 5.2)
        self.assertTrue(plan["first_read_only_review"]["exact_replay_required_before_mutation"])
        self.assertEqual(plan["read_only_recovery_summary_status"], "queued_read_only_reviews")
        self.assertEqual(plan["first_read_only_review_by_drop"][0]["symbol"], "CCJ")
        self.assertEqual(
            plan["read_only_recovery_priority_order"][0],
            {
                "rank": 1,
                "drop_key": "tech_score",
                "symbol": "CCJ",
                "distance_to_current_filter": 5.2,
                "distance_measurement_status": "measured",
                "missing_distance_evidence_fields": [],
                "read_only_review_action": "review_commodity_tech_threshold_distance_after_exact_replay_unlock",
                "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                "exact_replay_required_before_mutation": True,
            },
        )
        self.assertEqual(plan["read_only_recovery_symbols_to_watch"], ["CCJ"])
        self.assertEqual(
            plan["read_only_recovery_watchlist"],
            [
                {
                    "symbol": "CCJ",
                    "drop_keys": ["tech_score"],
                    "review_count": 1,
                    "lowest_distance_to_current_filter": 5.2,
                    "distance_measurement_status": "measured",
                    "distance_measurement_missing_fields": [],
                    "distance_measurement_sources_missing": [],
                    "first_read_only_review_action": (
                        "review_commodity_tech_threshold_distance_after_exact_replay_unlock"
                    ),
                    "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    "exact_replay_required_before_mutation": True,
                }
            ],
        )
        self.assertEqual(plan["read_only_recovery_distance_measured_count"], 1)
        self.assertEqual(plan["read_only_recovery_distance_measurement_gap_count"], 0)
        self.assertEqual(plan["read_only_recovery_distance_measurement_gaps"], [])
        measurement_plan = plan["read_only_recovery_distance_measurement_plan"]
        self.assertEqual(measurement_plan["status"], "all_watchlist_distances_measured")
        self.assertEqual(
            measurement_plan["next_action"],
            "compare_read_only_watchlist_distance_deltas_after_next_fresh_scan",
        )
        self.assertEqual(measurement_plan["distance_measured_count"], 1)
        self.assertEqual(measurement_plan["distance_measurement_gap_count"], 0)
        self.assertEqual(measurement_plan["distance_measurement_missing_field_count"], 0)
        self.assertIn(
            "read_only_watchlist_distance_deltas show material narrowing",
            measurement_plan["material_progress_if"],
        )
        self.assertEqual(
            plan["read_only_recovery_next_review_steps"][0]["step"],
            "read_only_review_tech_score_CCJ",
        )
        self.assertIn(
            "future_fresh_alpaca_opra_scan.candidate_count > 0",
            plan["read_only_recovery_material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_queue",
            plan["read_only_recovery_evidence_fields"],
        )
        self.assertEqual(
            plan["read_only_recovery_policy"],
            "record_near_miss_filter_distance_only_no_production_filter_changes_until_exact_replay_unlock",
        )

    def test_build_live_candidate_recovery_plan_reports_momentum_distance_measurement_gap(self):
        plan = build_live_candidate_recovery_plan(
            {
                "clock_reference_utc": "2026-05-22T13:00:00Z",
                "provider": "alpaca:sip:opra",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                        "proof_scan_universe_aligned": True,
                    }
                },
                "scan": {
                    "scan_drop_reason_audit_status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                    "scan_drop_reason_count": None,
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "fresh_scan_zero_candidates_after_fresh_quotes",
                    "candidate_count": 0,
                    "candidate_symbols": [],
                    "freshness_cleared": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_trusted_only": True,
                    "proof_scan_universe_aligned": True,
                    "top_drop_counts": [{"drop_key": "momentum", "count": 3}],
                    "zero_candidate_structural_review": {
                        "dominant_drop_key": "momentum",
                        "dominant_drop_count": 3,
                        "allowed_read_only_actions": ["rank_nearest_zero_candidate_blocker_symbols"],
                        "nearest_examples_by_drop": {
                            "momentum": [{"symbol": "AA", "ret5": 0.38}]
                        },
                    },
                },
                "exact_replay_unlock_contract": {
                    "readiness_checklist": {
                        "ready_to_run_full_exact_replay": False,
                        "exact_replay_profitability_verified": False,
                    },
                },
            }
        )

        self.assertEqual(plan["read_only_recovery_distance_measured_count"], 0)
        self.assertEqual(plan["read_only_recovery_partial_distance_measurement_count"], 1)
        self.assertEqual(plan["read_only_recovery_distance_measurement_gap_count"], 1)
        gap = plan["read_only_recovery_distance_measurement_gaps"][0]
        self.assertEqual(gap["symbol"], "AA")
        self.assertEqual(gap["drop_keys"], ["momentum"])
        self.assertEqual(gap["partial_distance_to_current_filter"], 0.12)
        self.assertEqual(gap["partial_distance_measurement_status"], "partial_distance_missing_trend_context")
        self.assertEqual(gap["partial_distance_fields"]["momentum_threshold_distance_pct"], 0.12)
        self.assertEqual(gap["partial_distance_fields"]["call_entry_momentum_pct"], 0.5)
        self.assertEqual(gap["partial_distance_fields"]["put_entry_momentum_pct"], 0.5)
        self.assertIn("momentum_signal_distance_pct", gap["missing_fields"])
        self.assertIn("price", gap["missing_fields"])
        self.assertIn("sma20", gap["missing_fields"])
        self.assertNotIn("call_entry_momentum_pct", gap["missing_fields"])
        self.assertNotIn("put_entry_momentum_pct", gap["missing_fields"])
        self.assertEqual(gap["next_action"], "rerun_fresh_opra_scan_with_momentum_signal_context")
        self.assertEqual(
            plan["read_only_recovery_watchlist"][0]["distance_measurement_status"],
            "partial_distance_missing_trend_context",
        )
        self.assertEqual(
            plan["read_only_recovery_watchlist"][0]["lowest_partial_distance_to_current_filter"],
            0.12,
        )
        self.assertEqual(
            plan["read_only_recovery_next_review_steps"][0]["missing_distance_evidence_fields"],
            [
                "momentum_signal_distance_pct",
                "price",
                "sma20",
            ],
        )
        self.assertEqual(
            plan["read_only_recovery_next_review_steps"][0]["partial_distance_to_current_filter"],
            0.12,
        )
        self.assertIn(
            "watchlist_distance_measurement_gap_count decreases",
            plan["read_only_recovery_material_progress_if"],
        )
        self.assertIn(
            "partial_momentum_threshold_distances_recorded_without_filter_mutation",
            plan["read_only_recovery_material_progress_if"],
        )
        self.assertEqual(
            plan["scan_drop_reason_audit"],
            {
                "status": "waiting_for_next_scan_result_with_raw_drop_reasons",
                "count": None,
                "symbols_by_drop": {},
                "detail_fields_by_drop": {},
                "derived_fields_by_drop": {},
                "examples_by_symbol_available": False,
            },
        )
        self.assertEqual(
            plan["scan_drop_reason_audit_blockers"],
            [
                "scan_drop_reason_audit_status_not_raw_drop_reasons_recorded",
                "scan_drop_reason_count_zero_or_missing",
            ],
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            plan["read_only_recovery_material_progress_if"],
        )
        self.assertIn("scan.scan_drop_reason_count > 0", plan["read_only_recovery_material_progress_if"])
        self.assertIn("scan.scan_drop_reason_examples_by_symbol", plan["read_only_recovery_evidence_fields"])
        measurement_plan = plan["read_only_recovery_distance_measurement_plan"]
        self.assertEqual(measurement_plan["status"], "distance_measurement_gaps_present")
        self.assertEqual(
            measurement_plan["next_action"],
            "rerun_fresh_opra_scan_to_fill_missing_momentum_trend_context",
        )
        self.assertEqual(measurement_plan["partial_distance_measurement_count"], 1)
        self.assertEqual(measurement_plan["distance_measurement_missing_field_count"], 3)
        self.assertEqual(
            measurement_plan["distance_measurement_missing_fields_by_symbol"],
            {"AA": ["momentum_signal_distance_pct", "price", "sma20"]},
        )
        gap_resolution = measurement_plan["distance_measurement_gap_resolution_plan"]
        self.assertEqual(
            gap_resolution["status"],
            "fresh_scan_required_current_scan_schema_ready",
        )
        self.assertTrue(gap_resolution["fresh_scan_required"])
        self.assertFalse(gap_resolution["current_report_can_be_repaired_without_fresh_scan"])
        self.assertEqual(
            gap_resolution["by_drop"]["momentum"]["status"],
            "fresh_scan_required_current_scan_schema_ready",
        )
        self.assertEqual(gap_resolution["by_drop"]["momentum"]["symbols"], ["AA"])
        self.assertEqual(gap_resolution["by_drop"]["momentum"]["unknown_fields"], [])
        self.assertEqual(
            gap_resolution["by_drop"]["momentum"]["next_action"],
            "rerun_fresh_opra_scan_with_current_momentum_context_schema",
        )
        self.assertIn(
            "Alpaca-backed underlying history",
            gap_resolution["by_drop"]["momentum"]["field_sources"]["price"],
        )
        self.assertIn(
            "derived by the progress runner",
            gap_resolution["by_drop"]["momentum"]["field_sources"]["momentum_signal_distance_pct"],
        )
        self.assertEqual(
            measurement_plan["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            measurement_plan["run_guard"],
            "run_only_when_fresh_opra_scan_window_is_allowed_or_returned_by_next_execution_guard",
        )
        self.assertEqual(measurement_plan["not_before_user_local"], "2026-05-22T08:10:00-06:00")
        self.assertEqual(measurement_plan["window_end_user_local"], "2026-05-22T14:00:00-06:00")
        self.assertEqual(measurement_plan["fresh_scan_window_status"], "fresh_scan_future")
        self.assertFalse(measurement_plan["fresh_scan_can_run_now"])
        self.assertEqual(measurement_plan["scan_calendar"], "us_equity_market_days")
        self.assertTrue(measurement_plan["scheduled_trade_date_is_market_day"])
        self.assertEqual(measurement_plan["gap_symbols_by_drop"], {"momentum": ["AA"]})
        self.assertIn(
            "momentum_signal_distance_pct",
            measurement_plan["required_fields_by_drop"]["momentum"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gap_count decreases",
            measurement_plan["material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_partial_distance_measurement_count increases",
            measurement_plan["material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_missing_field_count decreases",
            measurement_plan["material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_missing_fields_by_symbol fills one or more fields",
            measurement_plan["material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_distance_measurement_gaps[*].missing_fields",
            measurement_plan["evidence_fields"],
        )
        self.assertIn("production_filter_changes", measurement_plan["blocked_mutations"])

    def test_build_live_candidate_recovery_plan_fills_momentum_distance_from_scan_drop_audit(self):
        plan = build_live_candidate_recovery_plan(
            {
                "provider": "alpaca:sip:opra",
                "verification_gate": {
                    "gates": {
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                        "proof_scan_universe_aligned": True,
                    }
                },
                "scan": {
                    "scan_drop_reason_audit_status": "raw_drop_reasons_recorded",
                    "scan_drop_reason_count": 1,
                    "scan_drop_reason_symbols_by_drop": {"momentum": ["AA"]},
                    "scan_drop_reason_detail_fields_by_drop": {"momentum": ["ret5", "price", "sma20"]},
                    "scan_drop_reason_derived_fields_by_drop": {
                        "momentum": ["momentum_signal_distance_pct"]
                    },
                    "scan_drop_reason_examples_by_symbol": {
                        "AA": {
                            "symbol": "AA",
                            "drop_key": "momentum",
                            "ret5": 0.38,
                            "price": 101.0,
                            "sma20": 100.0,
                        }
                    }
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "fresh_scan_zero_candidates_after_fresh_quotes",
                    "candidate_count": 0,
                    "candidate_symbols": [],
                    "freshness_cleared": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_trusted_only": True,
                    "proof_scan_universe_aligned": True,
                    "top_drop_counts": [{"drop_key": "momentum", "count": 1}],
                    "zero_candidate_structural_review": {
                        "dominant_drop_key": "momentum",
                        "dominant_drop_count": 1,
                        "allowed_read_only_actions": ["rank_nearest_zero_candidate_blocker_symbols"],
                        "nearest_examples_by_drop": {
                            "momentum": [{"symbol": "AA", "ret5": 0.38}]
                        },
                    },
                },
                "exact_replay_unlock_contract": {
                    "readiness_checklist": {
                        "ready_to_run_full_exact_replay": False,
                        "exact_replay_profitability_verified": False,
                    },
                },
            }
        )

        review = plan["first_read_only_review"]
        self.assertEqual(review["symbol"], "AA")
        self.assertEqual(review["drop_key"], "momentum")
        self.assertEqual(review["distance_measurement_status"], "measured")
        self.assertEqual(review["distance_to_current_filter"], 0.12)
        self.assertEqual(review["distance_evidence_source"], "scan_drop_reason_examples_by_symbol")
        self.assertEqual(review["missing_distance_evidence_fields"], [])
        self.assertEqual(review["nearest_example"]["price"], 101.0)
        self.assertEqual(review["nearest_example"]["sma20"], 100.0)
        self.assertEqual(review["nearest_example"]["momentum_signal_distance_pct"], 0.12)
        self.assertIn("price", review["nearest_example"]["distance_evidence_added_fields"])
        self.assertIn("sma20", review["nearest_example"]["distance_evidence_added_fields"])
        self.assertEqual(plan["read_only_recovery_distance_measured_count"], 1)
        self.assertEqual(plan["read_only_recovery_partial_distance_measurement_count"], 0)
        self.assertEqual(plan["read_only_recovery_distance_measurement_gap_count"], 0)
        self.assertEqual(plan["read_only_recovery_distance_measurement_gaps"], [])
        self.assertEqual(plan["scan_drop_reason_audit"]["status"], "raw_drop_reasons_recorded")
        self.assertEqual(plan["scan_drop_reason_audit"]["count"], 1)
        self.assertEqual(plan["scan_drop_reason_audit"]["symbols_by_drop"], {"momentum": ["AA"]})
        self.assertTrue(plan["scan_drop_reason_audit"]["examples_by_symbol_available"])
        self.assertEqual(plan["scan_drop_reason_audit_blockers"], [])
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            plan["read_only_recovery_material_progress_if"],
        )
        self.assertIn("scan.scan_drop_reason_count > 0", plan["read_only_recovery_material_progress_if"])
        self.assertIn("scan.scan_drop_reason_examples_by_symbol", plan["read_only_recovery_evidence_fields"])
        self.assertEqual(
            plan["read_only_recovery_watchlist"][0]["lowest_distance_to_current_filter"],
            0.12,
        )
        self.assertEqual(
            plan["read_only_recovery_distance_measurement_plan"]["status"],
            "all_watchlist_distances_measured",
        )
        self.assertEqual(
            plan["read_only_recovery_distance_measurement_plan"][
                "distance_measurement_missing_fields_by_symbol"
            ],
            {},
        )

    def test_build_fresh_scan_post_run_evaluation_uses_fresh_scan_not_before_while_waiting(self):
        report = {
            "provider": "alpaca:sip:opra",
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "remaining_shared_quote_dates": 99,
            },
            "proof_source_audit": {
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "trusted_only": True,
                "all_required_symbols_have_proof_source_data": True,
            },
            "exact_history_acquisition_plan": {
                "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
            },
            "next_execution_contract": {
                "selected_step": "fresh_opra_live_scan",
                "command_display": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
            },
            "next_execution_preflight": {
                "next_action": "wait_until_not_before_then_run_next_execution_command",
            },
            "lane_next_step": {
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
            },
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "next_fresh_scan": {"scheduled_utc": "2026-05-21T14:10:00Z"},
                },
                "fresh_scan_retest_plan": {"scheduled_utc": "2026-05-21T14:10:00Z"},
            },
            "last_execution_review": {
                "previous_selected_step": "fresh_opra_live_scan",
                "status": "not_due_yet",
            },
        }

        evaluation = build_fresh_scan_post_run_evaluation(report)

        self.assertEqual(evaluation["status"], "waiting_for_fresh_scan_execution")
        self.assertEqual(
            evaluation["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(evaluation["next_not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(
            evaluation["zero_candidate_structural_review"]["status"],
            "blocked_until_quote_freshness_clears",
        )

    def test_build_post_fresh_scan_research_backlog_queues_locked_hypotheses(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "goal_completion_audit": {
                    "failed_requirements": [
                        "has_required_exact_alpaca_opra_history_depth",
                        "live_scan_has_verifiable_candidate",
                    ]
                },
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 99,
                    "remaining_market_day_capture_count": 99,
                    "diagnostic_required_shared_quote_dates": 88,
                    "capture_calendar": "us_equity_market_days",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "forward_capture_queue": [
                        {
                            "trade_date": "2026-05-21",
                            "not_before_user_local": "2026-05-21T14:20:00-06:00",
                            "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                            "expected_shared_quote_dates_after_capture": 2,
                        }
                    ],
                    "unlock_milestones": {
                        "diagnostic_replay": {
                            "required_shared_quote_dates": 88,
                            "remaining_market_day_captures": 87,
                            "unlock_trade_date": "2026-09-24",
                            "not_before_user_local": "2026-09-24T14:20:00-06:00",
                        },
                        "full_exact_replay": {
                            "required_shared_quote_dates": 100,
                            "remaining_market_day_captures": 99,
                            "unlock_trade_date": "2026-10-12",
                            "not_before_user_local": "2026-10-12T14:20:00-06:00",
                        },
                    },
                    "can_accelerate_exact_history_with_existing_sources": False,
                    "backfill_capability_audit": {
                        "status": "forward_capture_required_for_exact_bid_ask_history",
                        "local_exact_store_usage_decision": "current_artifact_counts_all_local_alpaca_opra_shared_dates",
                        "local_exact_store_refresh_can_advance_history_depth": False,
                        "local_exact_available_shared_quote_dates": 1,
                        "local_exact_store_matches_proof_window": True,
                    },
                },
                "commodity_research_lab": {
                    "status": "commodity_research_only",
                    "positive_bar_only_lanes": [],
                    "total_bar_fallback_trades": 9,
                    "total_exact_bid_ask_trades": 0,
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "selected_post_run_condition": "quote_freshness_cleared_and_candidates_still_zero",
                    "selected_post_run_next_action": "review_zero_candidate_diagnostic_plan_without_relaxing_production_filters",
                    "top_drop_counts": [
                        {"drop_key": "option_liquidity", "count": 9},
                        {"drop_key": "tech_score", "count": 8},
                    ],
                    "zero_candidate_diagnostic_plan": [
                        {
                            "drop_key": "option_liquidity",
                            "example_symbols": ["AA", "ALB"],
                            "representative_examples": [
                                {
                                    "symbol": "AA",
                                    "liquidity_reasons": [
                                        "wide_leg_spread",
                                        "wide_spread_entry_slippage",
                                    ],
                                    "worst_leg_spread_excess_pct": 6.4,
                                }
                            ],
                            "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                        }
                    ],
                },
            }
        )

        self.assertEqual(backlog["status"], "queued_until_exact_replay_unlock")
        self.assertFalse(backlog["safe_to_tune_filters_now"])
        self.assertEqual(backlog["unlock_status"], "locked_until_exact_replay_can_measure_filter_changes")
        self.assertEqual(
            backlog["activation_blockers"],
            [
                "enough_exact_shared_quote_dates",
                "readiness_ready_for_exact_replay",
                "exact_replay_completed",
                "exact_replay_has_trades",
            ],
        )
        self.assertEqual(backlog["remaining_exact_shared_quote_dates"], 99)
        unlock_runway = backlog["variant_unlock_runway"]
        self.assertEqual(unlock_runway["status"], "locked_until_exact_opra_history_and_replay_gates_pass")
        self.assertEqual(unlock_runway["current_primary_gate"], "enough_exact_shared_quote_dates")
        self.assertEqual(unlock_runway["next_capture_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(unlock_runway["diagnostic_unlock_trade_date"], "2026-09-24")
        self.assertEqual(unlock_runway["full_replay_unlock_trade_date"], "2026-10-12")
        self.assertEqual(
            unlock_runway["history_depth_runway"]["next_capture_effect"],
            "increments_exact_history_depth_but_replay_remains_locked",
        )
        self.assertEqual(unlock_runway["history_depth_runway"]["current_shared_quote_dates"], 1)
        self.assertEqual(unlock_runway["history_depth_runway"]["required_shared_quote_dates"], 100)
        self.assertEqual(unlock_runway["history_depth_runway"]["remaining_shared_quote_dates_after_next_capture"], 98)
        self.assertEqual(unlock_runway["history_depth_runway"]["diagnostic_remaining_after_next_capture"], 86)
        self.assertEqual(
            unlock_runway["gate_unlocks"][0]["unlock_source"],
            "exact_profitability_history_depth_runway",
        )
        self.assertEqual(unlock_runway["gate_unlocks"][0]["next_capture_trade_date"], "2026-05-21")
        self.assertEqual(backlog["bar_only_promotion_policy"], "research_only_never_satisfies_exact_alpaca_opra_profitability_gate")
        self.assertEqual(len(backlog["hypotheses"]), 2)
        self.assertEqual(backlog["deferred_test_count"], 2)
        self.assertEqual(backlog["deferred_variant_run_recipe_count"], 4)
        self.assertEqual(
            backlog["deferred_variant_recipe_audit"]["status"],
            "queued_locked_with_verified_opra_recipe_contracts",
        )
        self.assertEqual(backlog["deferred_variant_recipe_audit"]["recipe_count"], 4)
        self.assertEqual(backlog["deferred_variant_recipe_audit"]["locked_recipe_count"], 4)
        self.assertEqual(backlog["deferred_variant_recipe_audit"]["ready_to_run_count"], 0)
        self.assertTrue(backlog["deferred_variant_recipe_audit"]["all_recipes_opra_backed"])
        self.assertTrue(backlog["deferred_variant_recipe_audit"]["all_recipes_guarded"])
        self.assertFalse(backlog["deferred_variant_recipe_audit"]["safe_to_run_now"])
        self.assertEqual(backlog["deferred_variant_recipe_audit"]["failed_recipe_count"], 0)
        self.assertEqual(
            backlog["deferred_variant_execution_plan"]["status"],
            "locked_until_activation_gates_pass",
        )
        self.assertEqual(
            backlog["deferred_variant_execution_plan"]["activation_unlock_plan"]["history_depth_runway"][
                "full_replay_unlock_trade_date"
            ],
            "2026-10-12",
        )
        self.assertEqual(backlog["deferred_variant_execution_plan"]["ordered_sweep_count"], 4)
        self.assertFalse(backlog["deferred_variant_execution_plan"]["safe_to_start_now"])
        self.assertIn(
            "scripts/run_research_variant_cycle.py",
            backlog["deferred_variant_execution_plan"]["first_sweep_command"],
        )
        self.assertIn(
            "verification_gate.replay_profit_factor",
            backlog["deferred_variant_execution_plan"]["proof_fields_to_compare_after_each_sweep"],
        )
        self.assertIn(
            "provider_is_alpaca_sip_opra",
            [check["name"] for check in backlog["deferred_variant_recipe_audit"]["recipes"][0]["checks"]],
        )
        self.assertEqual(
            backlog["deferred_variant_recipe_audit"]["recipes"][0]["activation_ready_not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0][
                "activation_ready_not_before_user_local"
            ],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(backlog["deferred_test_queue"][0]["drop_key"], "option_liquidity")
        self.assertEqual(backlog["deferred_test_queue"][0]["status"], "queued_locked")
        self.assertEqual(backlog["deferred_test_queue"][0]["variant_run_recipe_count"], 2)
        self.assertIn("enough_exact_shared_quote_dates", backlog["deferred_test_queue"][0]["blocked_by"])
        self.assertEqual(backlog["deferred_test_queue"][0]["first_blocking_gate"], "enough_exact_shared_quote_dates")
        self.assertEqual(
            backlog["deferred_test_queue"][0]["blocked_by_goal_requirements"],
            ["has_required_exact_alpaca_opra_history_depth", "exact_replay_is_profitable"],
        )
        self.assertEqual(backlog["deferred_test_queue"][0]["activation_ready_trade_date"], "2026-10-12")
        self.assertEqual(
            backlog["deferred_test_queue"][0]["activation_ready_not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            backlog["deferred_test_queue"][0]["next_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            backlog["deferred_test_queue"][0]["activation_unlock_plan"]["history_depth_runway"][
                "remaining_shared_quote_dates_after_next_capture"
            ],
            98,
        )
        self.assertIn("verification_gate.replay_profit_factor", backlog["deferred_test_queue"][0]["compare_fields"])
        self.assertEqual(backlog["deferred_test_queue"][0]["representative_examples"][0]["symbol"], "AA")
        self.assertEqual(
            backlog["deferred_test_queue"][0]["variant_blueprint"]["research_variant_support"],
            "ai_commodity_option_filter_override_supported",
        )
        self.assertEqual(
            backlog["deferred_test_queue"][0]["variant_blueprint"]["variant_config_key"],
            "ai_commodity_option_filter_overrides",
        )
        self.assertEqual(
            backlog["deferred_test_queue"][0]["variant_blueprint"]["draft_variants"][0]["id"],
            "liquidity_leg12_slippage15",
        )
        self.assertIn(
            "variant_replay_uses_proof_source_alpaca_opra_daily_snapshot",
            backlog["deferred_test_queue"][0]["variant_blueprint"]["minimum_promotion_evidence"],
        )
        first_recipe = backlog["deferred_test_queue"][0]["variant_run_recipes"][0]
        self.assertTrue(
            first_recipe["variant_config_path"].endswith(
                "ai_commodity_infra_option_liquidity_liquidity_leg12_slippage15.json"
            )
        )
        self.assertEqual(
            first_recipe["variant_config"]["ai_commodity_option_filter_overrides"][
                "liquidity_spread_max_pct"
            ],
            12.0,
        )
        self.assertEqual(first_recipe["variant_config"]["provider"], "alpaca:sip:opra")
        self.assertEqual(first_recipe["variant_config"]["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(first_recipe["variant_config_write_status"], "not_written_by_progress_report")
        self.assertEqual(first_recipe["write_guard"], "write_only_after_activation_gates_pass")
        self.assertEqual(first_recipe["activation_status"], "locked_until_activation_gates_pass")
        self.assertEqual(first_recipe["first_blocking_gate"], "enough_exact_shared_quote_dates")
        self.assertEqual(
            first_recipe["blocked_by_goal_requirements"],
            ["has_required_exact_alpaca_opra_history_depth", "exact_replay_is_profitable"],
        )
        self.assertEqual(first_recipe["activation_ready_trade_date"], "2026-10-12")
        self.assertEqual(
            first_recipe["activation_ready_not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            first_recipe["next_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(first_recipe["replay_command_when_unlocked"], "python scripts/run_ai_commodity_opra_progress.py")
        self.assertIn("scripts/run_research_variant_cycle.py", first_recipe["run_command"])
        self.assertIn("--truth-lane historical_imported_daily", first_recipe["run_command"])
        self.assertIn("enough_exact_shared_quote_dates", first_recipe["blocked_by"])
        self.assertEqual(
            first_recipe["activation_unlock_plan"]["replay_unlock_contract"]["full_unlock_trade_date"],
            "2026-10-12",
        )
        self.assertIn(
            "use exact Alpaca OPRA replay metrics only",
            backlog["deferred_test_queue"][0]["guardrails"],
        )
        self.assertEqual(
            backlog["hypotheses"][0]["hypothesis"],
            "separate_quote_age_from_structural_spread_and_depth_blockers",
        )
        self.assertEqual(backlog["hypotheses"][0]["example_symbols"], ["AA", "ALB"])
        self.assertFalse(backlog["hypotheses"][0]["allowed_now"])
        self.assertEqual(
            backlog["hypotheses"][1]["exact_replay_test"],
            "sweep_tech_score_floor_in_exact_alpaca_opra_replay_after_history_ready",
        )
        self.assertEqual(
            backlog["next_action"],
            "review_zero_candidate_diagnostic_plan_without_relaxing_production_filters",
        )

    def test_build_post_fresh_scan_research_backlog_marks_momentum_playbook_variants_supported(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "goal_completion_audit": {"failed_requirements": ["exact_replay_is_profitable"]},
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "remaining_shared_quote_dates": 99,
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "momentum", "count": 7}],
                    "zero_candidate_diagnostic_plan": [
                        {
                            "drop_key": "momentum",
                            "example_symbols": ["BHP", "CEG"],
                            "representative_examples": [{"symbol": "BHP", "ret5": -7.9947}],
                        }
                    ],
                },
            }
        )

        queue_item = backlog["deferred_test_queue"][0]
        self.assertEqual(queue_item["drop_key"], "momentum")
        self.assertEqual(backlog["deferred_variant_run_recipe_count"], 2)
        self.assertEqual(backlog["deferred_variant_recipe_audit"]["recipe_count"], 2)
        self.assertTrue(backlog["deferred_variant_recipe_audit"]["all_recipes_opra_backed"])
        self.assertEqual(queue_item["variant_run_recipe_count"], 2)
        self.assertEqual(
            queue_item["variant_blueprint"]["research_variant_support"],
            "profile_and_replay_playbook_override_supported",
        )
        self.assertEqual(
            queue_item["variant_blueprint"]["variant_config_key"],
            "profile_overrides_or_playbook_overrides",
        )
        self.assertEqual(
            queue_item["variant_blueprint"]["draft_variants"][1]["playbook_overrides"][
                "ai_commodity_infra_observation"
            ]["entry_signal_id"],
            "bullish_mean_reversion",
        )
        second_recipe = queue_item["variant_run_recipes"][1]
        self.assertEqual(
            second_recipe["variant_config"]["playbook_overrides"]["ai_commodity_infra_observation"][
                "entry_signal_id"
            ],
            "bullish_mean_reversion",
        )
        self.assertIn("--truth-lane historical_imported_daily", second_recipe["run_command"])
        self.assertEqual(second_recipe["variant_config"]["lane_id"], "ai_commodity_infra_observation")

    def test_materialize_deferred_variant_configs_refuses_locked_recipes(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "remaining_shared_quote_dates": 99,
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = materialize_deferred_variant_configs(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
            )
            self.assertEqual(result["status"], "blocked_by_activation_gates_or_recipe_audit")
            self.assertFalse(result["safe_to_materialize"])
            self.assertEqual(result["written_count"], 0)
            self.assertEqual(result["skipped_count"], 2)
            self.assertIn("enough_exact_shared_quote_dates", result["activation_blockers"])
            self.assertFalse((Path(tmp) / "data" / "ai-commodity-infra" / "variant-configs").exists())

    def test_materialize_deferred_variant_configs_writes_only_after_opra_recipe_audit_is_ready(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        self.assertEqual(
            backlog["deferred_variant_recipe_audit"]["status"],
            "ready_with_verified_opra_recipe_contracts",
        )
        self.assertTrue(backlog["deferred_variant_recipe_audit"]["safe_to_run_now"])
        self.assertEqual(
            backlog["deferred_variant_execution_plan"]["status"],
            "ready_to_materialize_configs_and_run_exact_opra_sweeps",
        )
        self.assertEqual(backlog["deferred_variant_execution_plan"]["ordered_sweep_count"], 2)
        self.assertTrue(backlog["deferred_variant_execution_plan"]["safe_to_start_now"])

        with tempfile.TemporaryDirectory() as tmp:
            result = materialize_deferred_variant_configs(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
            )
            self.assertEqual(result["status"], "materialized")
            self.assertTrue(result["safe_to_materialize"])
            self.assertEqual(result["written_count"], 2)
            first_path = Path(result["materialized_configs"][0]["variant_config_path"])
            self.assertTrue(first_path.exists())
            config = json.loads(first_path.read_text(encoding="utf8"))
            self.assertEqual(config["provider"], "alpaca:sip:opra")
            self.assertEqual(config["proof_source_label"], "alpaca_opra_daily_snapshot")
            self.assertEqual(config["lane_id"], "ai_commodity_infra_observation")
            self.assertEqual(config["ai_commodity_option_filter_overrides"]["liquidity_spread_max_pct"], 12.0)

    def test_run_deferred_variant_sweeps_refuses_locked_recipes(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "forward_capture_required",
                    "remaining_shared_quote_dates": 99,
                },
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = run_deferred_variant_sweeps(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
                dry_run=True,
            )

        self.assertEqual(result["status"], "blocked_by_activation_gates_or_recipe_audit")
        self.assertFalse(result["safe_to_run"])
        self.assertEqual(result["executed_count"], 0)
        self.assertEqual(result["skipped_count"], 2)
        self.assertIn("enough_exact_shared_quote_dates", result["activation_blockers"])
        self.assertEqual(result["materialization"]["written_count"], 0)

    def test_run_deferred_variant_sweeps_dry_run_lists_ordered_opra_commands_after_gates_pass(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = run_deferred_variant_sweeps(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
                dry_run=True,
            )

        self.assertEqual(result["status"], "dry_run_ready_to_run_exact_opra_sweeps")
        self.assertTrue(result["safe_to_run"])
        self.assertEqual(result["planned_sweep_count"], 2)
        self.assertEqual(result["executed_count"], 0)
        self.assertEqual(result["materialization"]["status"], "dry_run_ready_to_materialize")
        self.assertEqual(result["planned_sweeps"][0]["variant_id"], "liquidity_leg12_slippage15")
        self.assertIn("scripts/run_research_variant_cycle.py", result["planned_sweeps"][0]["run_command_args"])
        self.assertIn("--truth-lane", result["planned_sweeps"][0]["run_command_args"])

    def test_run_deferred_variant_sweeps_executes_ordered_commands_after_materialization(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.run_ai_commodity_opra_progress.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(
                    args=["python"],
                    returncode=0,
                    stdout="ok",
                    stderr="",
                )
                result = run_deferred_variant_sweeps(
                    {"post_fresh_scan_research_backlog": backlog},
                    root=Path(tmp),
                    max_sweeps=1,
                )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["executed_count"], 1)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(result["failed_count"], 0)
        run.assert_called_once()
        called_args = run.call_args.args[0]
        self.assertIn("scripts/run_research_variant_cycle.py", called_args)
        self.assertIn("--variant-config", called_args)

    def test_collect_deferred_variant_results_ranks_promotable_exact_opra_result(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        first_sweep = backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "research_runs" / f"20260521_{first_sweep['run_slug']}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "historical_imported_daily",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 95.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps(
                    {
                        "provider": "alpaca:sip:opra",
                        "proof_source_label": "alpaca_opra_daily_snapshot",
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps(
                    {
                        "variant_live_scan": {
                            "candidate_count": 1,
                            "candidate_symbols": ["FCX"],
                            "live_scan_candidate_inside_exact_proof_universe": True,
                        },
                        "result": {
                            "total_trades": 14,
                            "profit_factor": 1.22,
                            "total_return_pct": 4.8,
                        }
                    }
                ),
                encoding="utf8",
            )

            result = collect_deferred_variant_results(
                {
                    "verification_gate": {
                        "replay_total_trades": 12,
                        "replay_profit_factor": 1.08,
                        "replay_total_return_pct": 2.3,
                        "gates": {
                            "alpaca_sip_opra_provider": True,
                            "alpaca_opra_source_filtered": True,
                            "exact_replay_completed": True,
                            "exact_replay_has_trades": True,
                        },
                    },
                    "post_fresh_scan_research_backlog": backlog,
                },
                root=Path(tmp),
            )

        self.assertEqual(result["status"], "promotable_variant_candidates_found")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["missing_result_count"], 1)
        self.assertEqual(result["promotable_count"], 1)
        self.assertEqual(result["best_candidate"]["variant_id"], first_sweep["variant_id"])
        self.assertEqual(result["best_candidate"]["profit_factor"], 1.22)
        self.assertEqual(result["best_candidate"]["failed_checks"], [])
        self.assertTrue(result["best_candidate"]["live_scan_evidence"]["passed"])
        self.assertEqual(result["best_candidate"]["baseline"]["profit_factor"], 1.08)

    def test_collect_deferred_variant_results_requires_baseline_and_live_scan_before_promotion(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        first_sweep = backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "research_runs" / f"20260521_{first_sweep['run_slug']}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "historical_imported_daily",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 95.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps(
                    {
                        "provider": "alpaca:sip:opra",
                        "proof_source_label": "alpaca_opra_daily_snapshot",
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps(
                    {
                        "result": {
                            "total_trades": 14,
                            "profit_factor": 1.22,
                            "total_return_pct": 4.8,
                        }
                    }
                ),
                encoding="utf8",
            )

            result = collect_deferred_variant_results(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
            )

        self.assertEqual(result["status"], "variant_results_collected_no_promotable_candidate")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["promotable_count"], 0)
        self.assertIsNone(result["best_candidate"])
        self.assertIn(
            "baseline_exact_alpaca_opra_replay_recorded_before_variant",
            result["ranked_results"][0]["failed_checks"],
        )
        self.assertIn(
            "live_scan_candidate_inside_exact_proof_universe_after_variant",
            result["ranked_results"][0]["failed_checks"],
        )

    def test_collect_deferred_variant_results_blocks_duplicate_sweep_artifacts(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        first_sweep = dict(backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0])
        duplicate_sweep = {
            **first_sweep,
            "sequence": 2,
            "variant_id": "duplicate_sweep",
        }
        backlog["deferred_variant_execution_plan"]["ordered_sweeps"] = [first_sweep, duplicate_sweep]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "research_runs" / f"20260521_{first_sweep['run_slug']}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "historical_imported_daily",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 95.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps(
                    {
                        "provider": "alpaca:sip:opra",
                        "proof_source_label": "alpaca_opra_daily_snapshot",
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps(
                    {
                        "variant_live_scan": {
                            "candidate_count": 1,
                            "candidate_symbols": ["FCX"],
                            "live_scan_candidate_inside_exact_proof_universe": True,
                        },
                        "result": {
                            "total_trades": 14,
                            "profit_factor": 1.22,
                            "total_return_pct": 4.8,
                        },
                    }
                ),
                encoding="utf8",
            )

            report = {
                "verification_gate": {
                    "replay_total_trades": 12,
                    "replay_profit_factor": 1.08,
                    "replay_total_return_pct": 2.3,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                    },
                },
                "post_fresh_scan_research_backlog": backlog,
            }
            result = collect_deferred_variant_results(report, root=Path(tmp))
            promotion = build_deferred_variant_promotion_review(
                {**report, "post_fresh_scan_research_backlog": {**backlog, "deferred_variant_result_collection": result}},
                root=Path(tmp),
            )

        self.assertEqual(result["status"], "variant_results_collected_with_duplicate_evidence")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["missing_result_count"], 1)
        self.assertEqual(result["duplicate_result_count"], 1)
        self.assertIsNone(result["best_candidate"])
        self.assertIn("unique_run_slug", result["ranked_results"][1]["failed_checks"])
        self.assertIn("unique_research_run_dir", result["ranked_results"][1]["failed_checks"])
        self.assertFalse(promotion["promotion_allowed"])
        self.assertIn("deferred_variant_results_are_unique", promotion["blockers"])

    def test_collect_deferred_variant_results_blocks_duplicate_run_dirs_for_slug(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        first_sweep = backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0]

        def _write_run(root: Path, prefix: str) -> None:
            run_dir = root / "research_runs" / f"{prefix}_{first_sweep['run_slug']}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "historical_imported_daily",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 95.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps(
                    {
                        "provider": "alpaca:sip:opra",
                        "proof_source_label": "alpaca_opra_daily_snapshot",
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps(
                    {
                        "variant_live_scan": {
                            "candidate_count": 1,
                            "candidate_symbols": ["FCX"],
                            "live_scan_candidate_inside_exact_proof_universe": True,
                        },
                        "result": {
                            "total_trades": 14,
                            "profit_factor": 1.22,
                            "total_return_pct": 4.8,
                        },
                    }
                ),
                encoding="utf8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run(root, "20260521")
            _write_run(root, "20260522")
            result = collect_deferred_variant_results(
                {
                    "verification_gate": {
                        "replay_total_trades": 12,
                        "replay_profit_factor": 1.08,
                        "replay_total_return_pct": 2.3,
                        "gates": {
                            "alpaca_sip_opra_provider": True,
                            "alpaca_opra_source_filtered": True,
                            "exact_replay_completed": True,
                            "exact_replay_has_trades": True,
                        },
                    },
                    "post_fresh_scan_research_backlog": backlog,
                },
                root=root,
            )

        self.assertEqual(result["status"], "variant_results_collected_with_duplicate_evidence")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["duplicate_result_count"], 1)
        self.assertIn("unique_research_run_dir", result["ranked_results"][0]["failed_checks"])

    def test_collect_deferred_variant_results_blocks_collapsed_duplicate_evidence(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        sweeps = backlog["deferred_variant_execution_plan"]["ordered_sweeps"][:2]

        def _write_run(root: Path, run_slug: str, run_at: str) -> None:
            run_dir = root / "research_runs" / f"20260521_{run_slug}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "historical_imported_daily",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 95.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps(
                    {
                        "provider": "alpaca:sip:opra",
                        "proof_source_label": "alpaca_opra_daily_snapshot",
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps(
                    {
                        "variant_live_scan": {
                            "candidate_count": 1,
                            "candidate_symbols": ["FCX"],
                            "live_scan_candidate_inside_exact_proof_universe": True,
                        },
                        "result": {
                            "run_at": run_at,
                            "run_at_utc": run_at,
                            "observed_at_utc": run_at,
                            "total_trades": 14,
                            "profit_factor": 1.22,
                            "total_return_pct": 4.8,
                        },
                    }
                ),
                encoding="utf8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run(root, sweeps[0]["run_slug"], "2026-05-21T10:00:00Z")
            _write_run(root, sweeps[1]["run_slug"], "2026-05-21T10:05:00Z")
            report = {
                "verification_gate": {
                    "replay_total_trades": 12,
                    "replay_profit_factor": 1.08,
                    "replay_total_return_pct": 2.3,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                    },
                },
                "post_fresh_scan_research_backlog": backlog,
            }
            result = collect_deferred_variant_results(report, root=root)
            promotion = build_deferred_variant_promotion_review(
                {**report, "post_fresh_scan_research_backlog": {**backlog, "deferred_variant_result_collection": result}},
                root=root,
            )

        self.assertEqual(result["status"], "variant_results_collected_with_duplicate_evidence")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["missing_result_count"], 1)
        self.assertEqual(result["duplicate_result_count"], 1)
        self.assertIsNone(result["best_candidate"])
        self.assertIn("unique_variant_evidence", result["ranked_results"][1]["failed_checks"])
        self.assertFalse(promotion["promotion_allowed"])
        self.assertIn("deferred_variant_results_are_unique", promotion["blockers"])

    def test_collect_deferred_variant_results_blocks_missing_and_non_opra_results(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )
        first_sweep = backlog["deferred_variant_execution_plan"]["ordered_sweeps"][0]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "research_runs" / f"20260521_{first_sweep['run_slug']}"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "truth_lane": "synthetic_research",
                        "playbooks": ["ai_commodity_infra_observation"],
                        "require_quote_coverage": 0.0,
                    }
                ),
                encoding="utf8",
            )
            (run_dir / "variant_config.json").write_text(
                json.dumps({"provider": "synthetic", "proof_source_label": "bar_fallback"}),
                encoding="utf8",
            )
            (run_dir / "primary_report.json").write_text(
                json.dumps({"result": {"total_trades": 0, "profit_factor": 0.8, "total_return_pct": -1.0}}),
                encoding="utf8",
            )

            result = collect_deferred_variant_results(
                {"post_fresh_scan_research_backlog": backlog},
                root=Path(tmp),
            )

        self.assertEqual(result["status"], "variant_results_collected_no_promotable_candidate")
        self.assertIsNone(result["best_candidate"])
        self.assertEqual(result["promotable_count"], 0)
        self.assertIn(
            "variant_config_provider_is_alpaca_sip_opra",
            result["ranked_results"][0]["failed_checks"],
        )
        self.assertIn("truth_lane_is_historical_imported_daily", result["ranked_results"][0]["failed_checks"])

    def test_attach_deferred_variant_result_collection_records_missing_sweeps_without_mutating_backlog(self):
        backlog = build_post_fresh_scan_research_backlog(
            {
                "exact_history_acquisition_plan": {
                    "status": "ready",
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 0,
                },
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12},
                "fresh_scan_iteration_decision": {
                    "status": "fresh_scan_zero_candidates_structural_review",
                    "top_drop_counts": [{"drop_key": "option_liquidity", "count": 7}],
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            enriched = attach_deferred_variant_result_collection(
                {
                    "provider": "alpaca:sip:opra",
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                    "verification_gate": {
                        "verified": False,
                        "gates": {
                            "alpaca_sip_opra_provider": True,
                            "alpaca_opra_source_filtered": True,
                        },
                    },
                    "post_fresh_scan_research_backlog": backlog,
                },
                root=Path(tmp),
            )

        collection = enriched["post_fresh_scan_research_backlog"]["deferred_variant_result_collection"]
        self.assertEqual(collection["status"], "no_variant_results_collected")
        self.assertEqual(collection["result_count"], 0)
        self.assertEqual(collection["missing_result_count"], 2)
        self.assertEqual(collection["promotable_count"], 0)
        self.assertIsNone(collection["best_candidate"])
        self.assertEqual(collection["next_action"], "run_ordered_exact_opra_variant_sweeps_after_activation")
        promotion = enriched["post_fresh_scan_research_backlog"]["deferred_variant_promotion_review"]
        self.assertEqual(promotion["status"], "promotion_blocked")
        self.assertFalse(promotion["promotion_allowed"])
        self.assertIn("completed_variant_results_collected", promotion["blockers"])
        self.assertIn("promotable_variant_candidate_present", promotion["blockers"])
        self.assertNotIn("deferred_variant_result_collection", backlog)

        summary = build_compact_progress_summary(enriched)
        payload = build_next_execution_cli_payload(
            enriched,
            reference_now=datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_result_collection_status"],
            "no_variant_results_collected",
        )
        self.assertEqual(summary["post_fresh_scan_research_backlog_deferred_variant_missing_result_count"], 2)
        self.assertEqual(summary["post_fresh_scan_research_backlog_deferred_variant_promotable_count"], 0)
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_promotion_status"],
            "promotion_blocked",
        )
        self.assertFalse(summary["post_fresh_scan_research_backlog_deferred_variant_promotion_allowed"])
        self.assertEqual(
            summary["exact_profitability_blocker_status"],
            "blocked_waiting_for_exact_opra_history_or_replay",
        )
        self.assertEqual(
            summary["exact_profitability_current_primary_blocker"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(summary["exact_profitability_ordered_unblock_plan"][0]["status"], "passed")
        self.assertIn("exact_replay_completed", summary["exact_profitability_blockers"])
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_result_collection_status"],
            "no_variant_results_collected",
        )
        self.assertEqual(payload["post_fresh_scan_research_backlog_deferred_variant_missing_result_count"], 2)
        self.assertEqual(payload["post_fresh_scan_research_backlog_deferred_variant_promotable_count"], 0)
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_promotion_status"],
            "promotion_blocked",
        )
        self.assertFalse(payload["post_fresh_scan_research_backlog_deferred_variant_promotion_allowed"])
        self.assertEqual(
            payload["exact_profitability_blocker_status"],
            "blocked_waiting_for_exact_opra_history_or_replay",
        )
        self.assertEqual(
            payload["exact_profitability_current_primary_blocker"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(payload["exact_profitability_ordered_unblock_plan"][0]["status"], "passed")
        self.assertIn("exact_replay_completed", payload["exact_profitability_blockers"])

    def test_build_deferred_variant_promotion_review_allows_only_clean_exact_opra_candidate(self):
        backlog = {
            "activation_blockers": [],
            "deferred_variant_execution_plan": {"activation_blockers": []},
            "deferred_variant_result_collection": {
                "status": "promotable_variant_candidates_found",
                "result_count": 1,
                "missing_result_count": 0,
                "promotable_count": 1,
                "best_candidate": {
                    "variant_id": "liquidity_leg12_slippage15",
                    "failed_checks": [],
                    "profit_factor": 1.22,
                    "total_return_pct": 4.8,
                },
            },
        }

        review = build_deferred_variant_promotion_review(
            {
                "verification_gate": {
                    "replay_total_trades": 12,
                    "replay_profit_factor": 1.08,
                    "replay_total_return_pct": 2.3,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                    },
                },
                "post_fresh_scan_research_backlog": backlog,
            }
        )

        self.assertEqual(review["status"], "promotion_allowed")
        self.assertTrue(review["promotion_allowed"])
        self.assertEqual(review["blockers"], [])
        self.assertEqual(review["best_candidate"]["variant_id"], "liquidity_leg12_slippage15")

    def test_build_exact_profitability_blocker_review_prioritizes_history_before_variants(self):
        review = build_exact_profitability_blocker_review(
            {
                "verification_gate": {
                    "verified": False,
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "replay_total_trades": None,
                    "replay_profit_factor": None,
                    "replay_total_return_pct": None,
                    "live_scan_candidate_count": 0,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                        "exact_replay_has_trades": False,
                        "exact_replay_profit_factor_positive": False,
                        "exact_replay_total_return_positive": False,
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                    },
                },
                "exact_history_acquisition_plan": {
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 99,
                    "remaining_market_day_capture_count": 99,
                    "diagnostic_required_shared_quote_dates": 88,
                    "capture_calendar": "us_equity_market_days",
                    "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "next_capture_trade_date": "2026-05-21",
                    "next_capture_not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "forward_capture_queue": [
                        {
                            "trade_date": "2026-05-21",
                            "not_before_user_local": "2026-05-21T14:20:00-06:00",
                            "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                            "expected_shared_quote_dates_after_capture": 2,
                        }
                    ],
                    "unlock_milestones": {
                        "diagnostic_replay": {
                            "required_shared_quote_dates": 88,
                            "remaining_market_day_captures": 87,
                            "unlock_trade_date": "2026-09-24",
                            "not_before_user_local": "2026-09-24T14:20:00-06:00",
                        },
                        "full_exact_replay": {
                            "required_shared_quote_dates": 100,
                            "remaining_market_day_captures": 99,
                            "unlock_trade_date": "2026-10-12",
                            "not_before_user_local": "2026-10-12T14:20:00-06:00",
                        },
                    },
                    "can_accelerate_exact_history_with_existing_sources": False,
                    "backfill_capability_audit": {
                        "status": "forward_capture_required_for_exact_bid_ask_history"
                    },
                },
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "post_fresh_scan_research_backlog": {
                    "deferred_variant_promotion_review": {
                        "status": "promotion_blocked",
                        "blockers": ["activation_gates_passed_before_promotion"],
                    }
                },
                "goal_completion_evidence_plan": {
                    "requirements": [
                        {
                            "requirement": "live_scan_has_verifiable_candidate",
                            "passed": False,
                            "next_action": "run_read_only_fresh_opra_scan_to_record_raw_drop_reasons_or_live_candidate",
                            "evidence_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                            "evidence_command_role": "fresh_live_candidate_scan_evidence",
                            "not_before_user_local": "2026-05-22T08:10:00-06:00",
                            "window_end_user_local": "2026-05-22T14:00:00-06:00",
                            "material_progress_if": [
                                "live_scan_has_candidate true",
                                "live_scan_candidate_inside_exact_proof_universe true",
                                "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
                                "scan.scan_drop_reason_count > 0",
                            ],
                        }
                    ],
                    "first_auxiliary_evidence_opportunity": {
                        "target_goal_requirement": "live_scan_has_verifiable_candidate",
                        "next_action": "run_read_only_fresh_opra_scan_to_record_raw_drop_reasons_or_live_candidate",
                        "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                        "command_role": "fresh_live_candidate_scan_evidence",
                        "not_before_user_local": "2026-05-22T08:10:00-06:00",
                        "window_end_user_local": "2026-05-22T14:00:00-06:00",
                        "material_progress_if": [
                            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
                            "scan.scan_drop_reason_count > 0",
                        ],
                        "blockers": [
                            "scan_drop_reason_audit_status_not_raw_drop_reasons_recorded",
                            "scan_drop_reason_count_zero_or_missing",
                        ],
                    },
                },
            }
        )

        self.assertEqual(review["status"], "blocked_waiting_for_exact_opra_history_or_replay")
        self.assertEqual(review["primary_path_status"], "waiting_for_exact_opra_history_or_replay")
        self.assertEqual(review["current_primary_blocker"], "has_required_exact_alpaca_opra_history_depth")
        self.assertIn("has_required_exact_alpaca_opra_history_depth", review["blockers"])
        self.assertNotIn("exact_profitability_uses_isolated_alpaca_opra_proof_source", review["blockers"])
        self.assertEqual(review["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(review["proof_source_isolation_blockers"], [])
        runway = review["history_depth_runway"]
        self.assertEqual(runway["status"], "forward_capture_required")
        self.assertEqual(runway["current_shared_quote_dates"], 1)
        self.assertEqual(runway["required_shared_quote_dates"], 100)
        self.assertEqual(runway["remaining_market_day_capture_count"], 99)
        self.assertEqual(runway["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(runway["remaining_shared_quote_dates_after_next_capture"], 98)
        self.assertTrue(runway["next_capture_advances_history_depth"])
        self.assertEqual(runway["diagnostic_unlock_trade_date"], "2026-09-24")
        self.assertEqual(runway["diagnostic_remaining_after_next_capture"], 86)
        self.assertFalse(runway["diagnostic_replay_unlocks_after_next_capture"])
        self.assertEqual(runway["full_replay_unlock_trade_date"], "2026-10-12")
        self.assertEqual(runway["full_replay_remaining_after_next_capture"], 98)
        self.assertFalse(runway["full_exact_replay_unlocks_after_next_capture"])
        self.assertEqual(
            runway["next_capture_effect"],
            "increments_exact_history_depth_but_replay_remains_locked",
        )
        self.assertFalse(runway["can_accelerate_exact_history_with_existing_sources"])
        self.assertEqual(
            runway["backfill_capability_status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        phases = {item["phase"]: item for item in review["ordered_unblock_plan"]}
        self.assertEqual(phases["source_and_proof_isolation"]["status"], "passed")
        self.assertIsNone(phases["source_and_proof_isolation"]["next_command"])
        self.assertEqual(phases["exact_opra_history_depth"]["status"], "blocked")
        self.assertEqual(
            phases["exact_opra_history_depth"]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            phases["exact_opra_history_depth"]["next_command_role"],
            "guarded_forward_alpaca_opra_capture",
        )
        self.assertEqual(
            phases["exact_opra_history_depth"]["not_before_user_local"],
            "2026-05-21T14:20:00-06:00",
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates increases",
            phases["exact_opra_history_depth"]["material_progress_if"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision",
            phases["exact_opra_history_depth"]["evidence_fields"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_refresh_can_advance_history_depth",
            phases["exact_opra_history_depth"]["evidence_fields"],
        )
        self.assertIn(
            "exact_history_backfill_capability_audit.local_exact_store_usage_decision == current_artifact_counts_all_local_alpaca_opra_shared_dates",
            phases["exact_opra_history_depth"]["material_progress_if"],
        )
        self.assertEqual(
            phases["exact_replay_profitability"]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertEqual(
            phases["exact_replay_profitability"]["next_command_role"],
            "exact_replay_profitability_measurement",
        )
        self.assertEqual(
            phases["exact_replay_profitability"]["not_before_user_local"],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["next_action"],
            "run_read_only_fresh_opra_scan_to_record_raw_drop_reasons_or_live_candidate",
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["next_command_role"],
            "fresh_live_candidate_scan_evidence",
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["not_before_user_local"],
            "2026-05-22T08:10:00-06:00",
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["window_end_user_local"],
            "2026-05-22T14:00:00-06:00",
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status",
            phases["live_candidate_confirmation"]["evidence_fields"],
        )
        self.assertIn(
            "scan.scan_drop_reason_count",
            phases["live_candidate_confirmation"]["evidence_fields"],
        )
        self.assertIn(
            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
            phases["live_candidate_confirmation"]["material_progress_if"],
        )
        self.assertIn(
            "scan.scan_drop_reason_count > 0",
            phases["live_candidate_confirmation"]["material_progress_if"],
        )
        self.assertEqual(
            phases["live_candidate_confirmation"]["auxiliary_evidence_opportunity"]["target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            phases["goal_completion_contract"]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            phases["source_and_proof_isolation"]["evidence_fields"],
        )
        self.assertEqual(
            review["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )

    def test_build_exact_profitability_blocker_review_prioritizes_source_isolation_before_history(self):
        review = build_exact_profitability_blocker_review(
            {
                "verification_gate": {
                    "verified": False,
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "enough_exact_shared_quote_dates": False,
                        "readiness_ready_for_exact_replay": False,
                        "exact_replay_completed": False,
                        "exact_replay_has_trades": False,
                        "exact_replay_profit_factor_positive": False,
                        "exact_replay_total_return_positive": False,
                        "live_scan_has_candidate": False,
                        "live_scan_candidate_inside_exact_proof_universe": False,
                    },
                },
                "proof_source_isolation_contract": {
                    **self._clean_proof_source_isolation_contract(),
                    "status": "proof_source_isolation_blocked",
                    "blockers": ["non_proof_shared_dates_are_excluded"],
                    "next_action": "repair_proof_source_isolation_before_profitability_claims",
                },
                "exact_history_acquisition_plan": {
                    "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "next_capture_command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                },
            }
        )

        self.assertEqual(review["status"], "blocked_by_source_or_completion_contract")
        self.assertEqual(review["primary_path_status"], "source_or_proof_contract_blocked")
        self.assertEqual(
            review["current_primary_blocker"],
            "exact_profitability_uses_isolated_alpaca_opra_proof_source",
        )
        self.assertIn(
            "exact_profitability_uses_isolated_alpaca_opra_proof_source",
            review["blockers"],
        )
        self.assertEqual(review["proof_source_isolation_blockers"], ["non_proof_shared_dates_are_excluded"])
        phases = {item["phase"]: item for item in review["ordered_unblock_plan"]}
        self.assertEqual(phases["source_and_proof_isolation"]["status"], "blocked")
        self.assertEqual(
            phases["source_and_proof_isolation"]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --refresh-derived-from-latest --json",
        )
        self.assertEqual(
            phases["source_and_proof_isolation"]["next_command_role"],
            "refresh_source_and_completion_contract",
        )
        self.assertEqual(review["next_command"], "python scripts/run_ai_commodity_opra_progress.py --refresh-derived-from-latest --json")

    def test_build_exact_profitability_blocker_review_marks_verified_path_ready(self):
        review = build_exact_profitability_blocker_review(
            {
                "verification_gate": {
                    "verified": True,
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                    "replay_total_trades": 18,
                    "replay_profit_factor": 1.31,
                    "replay_total_return_pct": 6.4,
                    "live_scan_candidate_count": 1,
                    "gates": {
                        "alpaca_sip_opra_provider": True,
                        "alpaca_opra_source_filtered": True,
                        "enough_exact_shared_quote_dates": True,
                        "readiness_ready_for_exact_replay": True,
                        "exact_replay_completed": True,
                        "exact_replay_has_trades": True,
                        "exact_replay_profit_factor_positive": True,
                        "exact_replay_total_return_positive": True,
                        "live_scan_has_candidate": True,
                        "live_scan_candidate_inside_exact_proof_universe": True,
                    },
                },
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "post_fresh_scan_research_backlog": {},
            }
        )

        self.assertEqual(review["status"], "verified_profitability_ready_for_goal_completion_audit")
        self.assertEqual(review["primary_path_status"], "complete_current_baseline_exact_opra_profitable")
        self.assertIsNone(review["current_primary_blocker"])
        self.assertEqual(review["blockers"], [])
        self.assertEqual(review["ordered_unblock_plan"][-1]["status"], "passed")
        self.assertIsNone(review["ordered_unblock_plan"][-1]["next_command"])
        self.assertEqual(review["next_action"], "review_goal_completion_audit_for_completion")

    def test_build_progress_delta_classifies_unchanged_waiting_for_capture(self):
        previous = {
            "generated_at": "2026-05-21T03:00:00Z",
            "shared_quote_dates_after": {"count": 1},
            "proof_window": {"remaining_shared_quote_dates": 99},
            "scan": {"candidate_count": 0},
            "replay": {"error": "Selected dates: 1."},
            "automation_health": {"healthy": True},
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "total_quote_rows": 6946,
                "available_required_underlying_count": 9,
                "min_executable_quote_pct": 100.0,
                "total_missing_bid_ask_rows": 0,
                "total_crossed_quote_rows": 0,
            },
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {"enough_exact_shared_quote_dates": False},
            },
        }
        current = {
            **previous,
            "generated_at": "2026-05-21T03:30:00Z",
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
            },
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "unchanged_waiting_for_next_capture")
        self.assertEqual(delta["no_progress_reason"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(delta["improvement_flags"], [])
        self.assertEqual(delta["regression_flags"], [])

    def test_build_progress_delta_ignores_tiny_scan_sensitivity_noise(self):
        previous = {
            "generated_at": "2026-05-21T04:07:20Z",
            "shared_quote_dates_after": {"count": 1},
            "proof_window": {"remaining_shared_quote_dates": 99},
            "scan": {
                "candidate_count": 0,
                "gate_sensitivity": {
                    "closest_option_liquidity": {
                        "symbol": "FCX",
                        "combined_gate_distance": 3.19,
                    },
                },
            },
            "replay": {"error": "Selected dates: 1."},
            "automation_health": {"healthy": True},
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "total_quote_rows": 6946,
                "available_required_underlying_count": 9,
                "min_executable_quote_pct": 100.0,
                "total_missing_bid_ask_rows": 0,
                "total_crossed_quote_rows": 0,
            },
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {"enough_exact_shared_quote_dates": False},
            },
        }
        current = {
            **previous,
            "generated_at": "2026-05-21T04:12:20Z",
            "scan": {
                "candidate_count": 0,
                "gate_sensitivity": {
                    "closest_option_liquidity": {
                        "symbol": "FCX",
                        "combined_gate_distance": 3.27,
                    },
                },
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
            },
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["scan_liquidity_gate_distance_delta"], 0.08)
        self.assertEqual(delta["run_classification"], "unchanged_waiting_for_next_capture")
        self.assertEqual(delta["no_progress_reason"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(delta["improvement_flags"], [])
        self.assertEqual(delta["regression_flags"], [])
        self.assertEqual(delta["non_material_flags"], ["scan_liquidity_gate_distance_delta_below_materiality"])

    def test_build_progress_delta_classifies_waiting_for_fresh_scan_before_capture(self):
        previous = {
            "generated_at": "2026-05-21T05:00:00Z",
            "shared_quote_dates_after": {"count": 1},
            "proof_window": {"remaining_shared_quote_dates": 99},
            "scan": {"candidate_count": 0},
            "replay": {"error": "Selected dates: 1."},
            "automation_health": {"healthy": True},
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "total_quote_rows": 6946,
                "available_required_underlying_count": 9,
                "min_executable_quote_pct": 100.0,
                "total_missing_bid_ask_rows": 0,
                "total_crossed_quote_rows": 0,
            },
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "gates": {"enough_exact_shared_quote_dates": False},
            },
        }
        current = {
            **previous,
            "generated_at": "2026-05-21T05:05:00Z",
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
            },
            "lane_next_step": {
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
        }

        delta = build_progress_delta(previous, current)

        self.assertEqual(delta["run_classification"], "unchanged_waiting_for_fresh_opra_scan")
        self.assertEqual(
            delta["no_progress_reason"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertEqual(delta["improvement_flags"], [])
        self.assertEqual(delta["regression_flags"], [])

    def test_build_diagnostic_replay_summary_marks_exploratory_replay_unverified(self):
        summary = build_diagnostic_replay_summary(
            {
                "truth_source": "historical_imported_daily",
                "total_days": 2,
                "candidate_trade_count": 2,
                "total_trades": 2,
                "profit_factor": 1.4,
                "total_return_pct": 3.2,
                "quote_coverage_pct": 100.0,
                "required_imported_calendar_dates": 1,
            },
            current_shared_quote_dates=1,
            required_shared_quote_dates=100,
            diagnostic_min_imported_calendar_dates=1,
        )

        self.assertEqual(summary["status"], "diagnostic_completed")
        self.assertTrue(summary["diagnostic_only"])
        self.assertFalse(summary["can_verify_profitability"])
        self.assertEqual(summary["current_shared_quote_dates"], 1)
        self.assertEqual(summary["required_shared_quote_dates_for_verification"], 100)
        self.assertEqual(summary["diagnostic_min_imported_calendar_dates"], 1)
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["next_action"], "compare_diagnostic_metrics_after_more_opra_captures")
        self.assertEqual(
            summary["verification_note"],
            "diagnostic_replay_does_not_satisfy_full_shared_quote_date_gate",
        )

    def test_build_diagnostic_replay_summary_records_skips(self):
        summary = build_diagnostic_replay_summary(
            None,
            current_shared_quote_dates=0,
            required_shared_quote_dates=100,
            skipped_reason="no_alpaca_opra_shared_quote_dates",
        )

        self.assertEqual(summary["status"], "skipped")
        self.assertEqual(summary["skipped_reason"], "no_alpaca_opra_shared_quote_dates")
        self.assertEqual(summary["blockers"], ["no_alpaca_opra_shared_quote_dates"])
        self.assertEqual(summary["next_action"], "capture_first_alpaca_opra_shared_quote_date")
        self.assertIsNone(summary["diagnostic_min_imported_calendar_dates"])

    def test_diagnostic_replay_blockers_explain_zero_day_replay(self):
        blockers, next_action = diagnostic_replay_blockers(
            {
                "total_days": 0,
                "candidate_trade_count": 0,
                "total_trades": 0,
                "unpriced_trade_count": 0,
                "post_entry_filtered_trade_count": 0,
                "quote_coverage_pct": 0.0,
            }
        )

        self.assertEqual(
            blockers,
            [
                "diagnostic_replay_days:0",
                "diagnostic_candidate_trades:0",
                "diagnostic_trades:0",
            ],
        )
        self.assertEqual(next_action, "accumulate_replay_simulation_shared_opra_dates")

    def test_diagnostic_replay_summary_skips_until_replay_runway_exists(self):
        summary = build_diagnostic_replay_summary(
            None,
            current_shared_quote_dates=1,
            required_shared_quote_dates=100,
            diagnostic_min_imported_calendar_dates=88,
            skipped_reason="insufficient_replay_simulation_quote_dates",
        )

        self.assertEqual(summary["status"], "skipped")
        self.assertEqual(summary["blockers"], ["insufficient_replay_simulation_quote_dates"])
        self.assertEqual(summary["next_action"], "accumulate_replay_simulation_shared_opra_dates")
        self.assertEqual(summary["diagnostic_min_imported_calendar_dates"], 88)

    def test_build_source_quality_summary_reports_usable_quotes_waiting_for_depth(self):
        summary = build_source_quality_summary(
            {
                "snapshot_kind": "daily_eod",
                "source_labels_required": ["alpaca_opra_daily_snapshot"],
                "required_underlyings": ["FCX", "SLV"],
                "missing_required_underlyings": [],
                "low_executable_required_underlyings": [],
                "shared_required_quote_dates": {"count": 1},
                "minimums": {"min_shared_quote_dates": 100},
                "summary": {
                    "quote_count": 30,
                    "batch_count": 1,
                    "earliest_quote_at_utc": "2026-05-20T18:43:01Z",
                    "latest_quote_at_utc": "2026-05-20T19:59:59Z",
                    "latest_imported_at_utc": "2026-05-21T01:38:48Z",
                },
                "required_underlying_health": {
                    "FCX": {
                        "quote_rows": 10,
                        "contract_count": 10,
                        "quote_date_count": 1,
                        "executable_quote_pct": 100.0,
                        "missing_bid_ask_rows": 0,
                        "crossed_quote_rows": 0,
                        "underlying_price_pct": 100.0,
                    },
                    "SLV": {
                        "quote_rows": 20,
                        "contract_count": 20,
                        "quote_date_count": 1,
                        "executable_quote_pct": 95.5,
                        "missing_bid_ask_rows": 1,
                        "crossed_quote_rows": 0,
                        "underlying_price_pct": 100.0,
                    },
                },
            }
        )

        self.assertEqual(summary["status"], "usable_quotes_waiting_for_history_depth")
        self.assertEqual(summary["source_labels_required"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(summary["total_quote_rows"], 30)
        self.assertEqual(summary["required_underlying_count"], 2)
        self.assertEqual(summary["available_required_underlying_count"], 2)
        self.assertEqual(summary["min_executable_quote_pct"], 95.5)
        self.assertEqual(summary["total_missing_bid_ask_rows"], 1)
        self.assertEqual(summary["lowest_quote_row_symbols"][0]["symbol"], "FCX")

    def test_build_source_quality_summary_reports_missing_required_underlyings(self):
        summary = build_source_quality_summary(
            {
                "required_underlyings": ["FCX", "SLV"],
                "missing_required_underlyings": ["SLV"],
                "low_executable_required_underlyings": [],
                "shared_required_quote_dates": {"count": 1},
                "minimums": {"min_shared_quote_dates": 100},
                "required_underlying_health": {"FCX": {"quote_rows": 10}},
            }
        )

        self.assertEqual(summary["status"], "missing_required_underlyings")
        self.assertEqual(summary["available_required_underlying_count"], 1)
        self.assertEqual(summary["missing_required_underlyings"], ["SLV"])

    def test_scan_proof_universe_alignment_flags_scan_symbols_without_exact_proof(self):
        alignment = build_scan_proof_universe_alignment(
            proof_symbols=["FCX", "SLV"],
            scan_symbols=["FCX", "SLV", "ALB", "AA"],
            scan={
                "candidate_count": 1,
                "candidate_symbols": ["ALB"],
                "blocker_symbols": ["FCX", "AA"],
            },
        )

        self.assertEqual(alignment["status"], "scan_universe_exceeds_exact_proof_universe")
        self.assertEqual(alignment["proof_universe_count"], 2)
        self.assertEqual(alignment["scan_universe_count"], 4)
        self.assertEqual(alignment["scan_symbols_without_exact_proof"], ["ALB", "AA"])
        self.assertEqual(alignment["candidate_symbols_outside_exact_proof"], ["ALB"])
        self.assertFalse(alignment["live_scan_candidates_all_inside_exact_proof"])
        self.assertEqual(alignment["blocker_symbols_outside_exact_proof"], ["AA"])

    def test_scan_proof_universe_alignment_accepts_candidate_inside_exact_proof(self):
        alignment = build_scan_proof_universe_alignment(
            proof_symbols=["FCX", "SLV"],
            scan_symbols=["FCX", "SLV"],
            scan={"candidate_count": 1, "candidate_symbols": ["FCX"], "blocker_symbols": []},
        )

        self.assertEqual(alignment["status"], "scan_universe_aligned_with_exact_proof_universe")
        self.assertTrue(alignment["live_scan_candidates_all_inside_exact_proof"])
        self.assertEqual(alignment["candidate_symbols_outside_exact_proof"], [])

    def test_build_compact_progress_summary_includes_verification_and_capture_action(self):
        summary = build_compact_progress_summary(
            {
                "provider": "alpaca:sip:opra",
                "verification_gate": {
                    "status": "not_verified",
                    "verified": False,
                    "blockers": ["shared_quote_dates:1/100"],
                    "gates": {
                        "capture_scope_full_scan_universe": True,
                        "capture_target_complete": True,
                        "proof_scan_universe_aligned": True,
                    },
                },
                "lane_next_step": {
                    "phase": "capture_wait",
                    "priority_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "primary_blocker": "shared_quote_dates:1/100",
                    "safe_to_tune_filters": False,
                    "next_timed_event": {
                        "timing_status": "fresh_scan_future",
                        "hours_until_scheduled": 7.95,
                        "scan_calendar": "us_equity_market_days",
                        "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                        "scheduled_trade_date_is_market_day": True,
                    },
                },
                "lane_iteration_plan": {
                    "status": "active",
                    "priority_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "safe_to_tune_filters": False,
                    "steps": [
                        {
                            "step": "post_close_full_universe_capture",
                            "status": "scheduled",
                            "action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                            "scheduled_utc": "2026-05-21T20:20:00Z",
                            "actionable_now": False,
                            "not_before_utc": "2026-05-21T20:20:00Z",
                            "premature_run_guard": "target_date_capturable_guard",
                            "target_trade_date": "2026-05-21",
                            "command": [
                                "python",
                                "scripts/run_ai_commodity_opra_progress.py",
                                "--force-capture",
                                "--target-date",
                                "2026-05-21",
                            ],
                        },
                        {
                            "step": "filter_tuning",
                            "status": "locked",
                            "action": "hold_filters_until_exact_replay_is_ready",
                        },
                    ],
                },
                "next_execution_contract": {
                    "status": "waiting_until_not_before",
                    "selected_step": "post_close_full_universe_capture",
                    "matches_next_timed_event": True,
                    "actionable_now": False,
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "command": [
                        "python",
                        "scripts/run_ai_commodity_opra_progress.py",
                        "--force-capture",
                        "--target-date",
                        "2026-05-21",
                    ],
                    "blockers": ["waiting_until_not_before:2026-05-21T20:20:00Z"],
                },
                "next_execution_runbook_card": {
                    "summary": "wait_until_the_not_before_time_then_rerun_the_probe_or_command",
                    "guard_status": "clock_guard_active",
                    "recommended_action": "wait_until_not_before",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "window_end_user_local": None,
                    "success_criteria": [
                        "capture_target_complete_true",
                        "shared_quote_dates_increase_or_target_was_already_complete",
                    ],
                },
                "next_execution_runbook_snapshot": {
                    "clock_status": "waiting_until_not_before",
                    "recommended_action": "wait_until_not_before",
                    "wait_minutes": 120.0,
                },
                "last_execution_review": {
                    "status": "not_due_yet",
                    "previous_selected_step": "fresh_opra_live_scan",
                    "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
                    "checks": [],
                    "previous_runbook_guard_status": "clock_guard_active",
                    "previous_runbook_recommended_action": "wait_until_not_before",
                    "previous_runbook_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                    "previous_runbook_not_before_user_local": "2026-05-21T08:10:00-06:00",
                    "previous_runbook_window_end_user_local": "2026-05-21T14:00:00-06:00",
                    "previous_runbook_success_criteria": ["fresh_scan_candidate_count_above_zero"],
                    "previous_runbook_command_matches_contract": True,
                    "ran_from_runbook_card": False,
                    "ran_from_runbook_card_inference": "previous_runbook_card_waiting_until_not_before",
                },
                "previous_proof_event_outcome": {
                    "status": "not_due_yet",
                    "event_kind": "fresh_opra_live_candidate_scan",
                    "target_goal_requirement": "live_scan_has_verifiable_candidate",
                    "advanced_goal_requirement": False,
                    "material_progress": False,
                    "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
                    "checks": [],
                },
                "progress_delta": {
                    "verification_gates_still_blocked": ["enough_exact_shared_quote_dates"],
                    "run_classification": "unchanged_waiting_for_next_capture",
                    "no_progress_reason": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "non_material_flags": ["scan_liquidity_gate_distance_delta_below_materiality"],
                    "scan_ev_shortfall_delta": -2.0,
                    "scan_candidate_heuristic_ev_delta": 2.0,
                    "scan_liquidity_gate_distance_delta": -5.0,
                },
                "source_quality": {
                    "status": "usable_quotes_waiting_for_history_depth",
                    "total_quote_rows": 6946,
                    "min_executable_quote_pct": 100.0,
                },
                "capture": {
                    "status": "skipped_existing_shared_date",
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "capture_action": {
                    "status": "waiting_for_next_market_close",
                    "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "next_scheduled_capture": {
                        "timing_status": "scheduled_future",
                        "scheduled_utc": "2026-05-21T20:20:00Z",
                    },
                },
                "shared_quote_dates_after": {"count": 1},
                "proof_window": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 99,
                    "current_target_trade_date": "2026-05-21",
                    "current_target_captured": False,
                    "next_missing_capture_trade_date": "2026-05-21",
                    "diagnostic_ready": False,
                    "diagnostic_remaining_shared_quote_dates": 87,
                    "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-18",
                    "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
                    "remaining_market_day_capture_count": 99,
                    "diagnostic_remaining_market_day_capture_count": 87,
                    "full_replay_remaining_market_day_capture_count": 99,
                    "legacy_weekday_fields_are_market_day_aware": True,
                },
                "readiness": {"status": "partial"},
                "replay": {"error": "Selected dates: 1."},
                "diagnostic_replay": {
                    "status": "skipped",
                    "total_trades": 0,
                    "blockers": ["insufficient_replay_simulation_quote_dates"],
                    "next_action": "accumulate_replay_simulation_shared_opra_dates",
                    "profit_factor": None,
                    "total_return_pct": None,
                    "quote_coverage_pct": None,
                    "can_verify_profitability": False,
                },
                "automation_health": {
                    "covers_fresh_opra_scan": True,
                    "covers_post_close_capture": True,
                    "schedule_exact_required_times": True,
                    "unexpected_intraday_times": [],
                    "scheduled_intraday_times": ["08:10:00", "14:20:00"],
                },
                "proof_source_audit": {
                    "trusted_only": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                    "all_trusted_shared_quote_dates": {"count": 2, "first": "2026-05-15", "last": "2026-05-20"},
                    "excluded_trusted_shared_quote_dates": {"count": 1, "first": "2026-05-15", "last": "2026-05-15"},
                    "excluded_trusted_source_labels": ["thetadata_free_eod"],
                    "all_required_symbols_have_proof_source_data": True,
                    "non_proof_alpaca_like_source_labels": [],
                    "store_inventory": {
                        "source_labels_with_quotes_in_scope": [
                            "alpaca_opra_daily_snapshot",
                            "thetadata_free_eod",
                        ],
                    },
                    "per_source_shared_quote_dates": [
                        {
                            "source_label": "alpaca_opra_daily_snapshot",
                            "used_for_exact_profitability_proof": True,
                            "shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                            "required_symbol_coverage": {
                                "required_symbol_count": 24,
                                "available_required_symbol_count": 24,
                                "missing_required_symbols": [],
                                "min_symbol_quote_date_count": 1,
                                "max_symbol_quote_date_count": 1,
                            },
                        }
                    ],
                },
                "commodity_research_lab": {
                    "status": "commodity_research_only",
                    "run_at_utc": "2026-05-21T06:00:10Z",
                    "total_bar_fallback_trades": 9,
                    "total_exact_bid_ask_trades": 0,
                    "positive_bar_only_lanes": [],
                    "next_action": "do_not_promote_bar_only_research_accumulate_exact_alpaca_opra_bid_ask_dates",
                },
                "scan": {
                    "candidate_count": 0,
                    "historical_scan_ready_count": 24,
                    "historical_scan_required_count": 24,
                    "quote_freshness_context": {
                        "next_fresh_scan": {
                            "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                            "window_end_user_local": "2026-05-21T14:00:00-06:00",
                            "scan_calendar": "us_equity_market_days",
                            "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                            "scheduled_trade_date_is_market_day": True,
                        }
                    },
                    "scan_funnel": {"drop_counts": {"option_liquidity": 9}},
                    "drop_diagnostics": [
                        {
                            "drop_key": "option_liquidity",
                            "count": 9,
                            "example_symbols": ["FCX", "ALB"],
                            "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                        }
                    ],
                    "fresh_scan_retest_plan": {
                        "status": "scheduled",
                        "next_action": "wait_until_fresh_opra_scan_window",
                        "primary_probe_symbol": "FCX",
                        "quote_age_only_blocker_symbols": ["FCX"],
                        "structural_liquidity_blocker_symbols": ["ALB"],
                    },
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_exceeds_exact_proof_universe",
                    "proof_universe_count": 9,
                    "scan_universe_count": 24,
                    "scan_symbols_without_exact_proof_count": 15,
                    "candidate_symbols_outside_exact_proof": [],
                    "blocker_symbols_outside_exact_proof": ["ALB"],
                    "next_action": "expand_exact_alpaca_opra_capture_to_scan_universe_or_treat_outside_symbols_as_research_only",
                },
                "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "artifacts": {"latest_json": "latest.json"},
            }
        )

        self.assertEqual(summary["verification_status"], "not_verified")
        self.assertFalse(summary["verified"])
        self.assertEqual(summary["verification_blockers"], ["shared_quote_dates:1/100"])
        self.assertEqual(summary["verification_gates_still_blocked"], ["enough_exact_shared_quote_dates"])
        self.assertTrue(summary["gate_capture_scope_full_scan_universe"])
        self.assertTrue(summary["gate_capture_target_complete"])
        self.assertTrue(summary["gate_proof_scan_universe_aligned"])
        self.assertEqual(summary["lane_phase"], "capture_wait")
        self.assertEqual(summary["lane_priority_action"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(summary["lane_primary_blocker"], "shared_quote_dates:1/100")
        self.assertFalse(summary["lane_safe_to_tune_filters"])
        self.assertEqual(summary["lane_next_timed_event_timing_status"], "fresh_scan_future")
        self.assertEqual(summary["lane_next_timed_event_hours_until"], 7.95)
        self.assertEqual(summary["lane_next_timed_event_calendar"], "us_equity_market_days")
        self.assertTrue(summary["lane_next_timed_event_trade_date_is_market_day"])
        self.assertEqual(summary["lane_next_step_plan_status"], "waiting_for_not_before")
        self.assertEqual(
            summary["lane_next_step_plan_immediate_action"],
            "wait_until_not_before_then_rerun_next_execution_guard",
        )
        self.assertEqual(
            summary["lane_next_step_plan_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["lane_next_step_plan_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertIn("target_date_capturable_guard preserved", summary["lane_next_step_plan_pre_run_checks"])
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            summary["lane_next_step_plan_pre_run_checks"],
        )
        self.assertIn("capture.target_capture_complete true", summary["lane_next_step_plan_after_run_checks"])
        self.assertIn(
            "proof_source_isolation_contract.blockers empty",
            summary["lane_next_step_plan_after_run_checks"],
        )
        self.assertIn(
            "capture.missing_target_date_symbols_after",
            summary["lane_next_step_plan_evidence_to_record_after_run"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            summary["lane_next_step_plan_evidence_to_record_after_run"],
        )
        self.assertIn(
            "capture_target_complete_false",
            summary["lane_next_step_plan_failure_signals_to_watch"],
        )
        self.assertEqual(
            summary["lane_next_step_plan_post_run_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            summary["lane_next_step_plan_post_run_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(
            summary["lane_next_step_plan_post_run_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertIn(
            "exact_replay_unlock_contract.full_exact_replay_unlocked",
            summary["lane_next_step_plan_post_run_profitability_gate_fields"],
        )
        self.assertEqual(
            summary["lane_next_step_plan_post_run_profitability_handoff"][0]["step"],
            "readback_next_execution_after_capture",
        )
        self.assertEqual(
            summary["exact_capture_post_run_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertIn(
            summary["exact_capture_post_run_evidence_contract_status"],
            {"waiting_for_guarded_capture_run", "post_capture_progress_blocked"},
        )
        self.assertIn(
            summary["exact_capture_post_run_next_capture_evidence_state"],
            {
                "next_capture_target_waiting_until_not_before",
                "next_capture_target_pending_guarded_capture",
                "next_capture_target_due_now",
            },
        )
        self.assertIs(summary["exact_capture_post_run_next_capture_target_observed"], False)
        self.assertIs(summary["exact_capture_post_run_stale_success_guard_for_next_target"], False)
        self.assertEqual(
            summary["exact_capture_post_run_evidence_contract_next_capture_evidence_state"],
            summary["exact_capture_post_run_next_capture_evidence_state"],
        )
        self.assertIn(
            "next_execution_runbook_card.run_next_execution_command true",
            summary["exact_capture_post_run_required_before_run"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            summary["exact_capture_post_run_fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates >= 2",
            summary["exact_capture_post_run_material_progress_if"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates < 2",
            summary["exact_capture_post_run_failure_signals_after_run"],
        )
        self.assertIn(
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
            summary["exact_capture_post_run_post_run_commands"],
        )
        self.assertEqual(
            summary["lane_next_step_plan_success_branch"],
            "if_shared_dates_increment_then_continue_daily_capture_runway",
        )
        self.assertEqual(
            summary["lane_next_step_plan_filter_policy"],
            "locked_until_exact_alpaca_opra_replay_profitability_gate_can_measure_changes",
        )
        self.assertEqual(
            summary["lane_next_step_plan_history_acceleration_status"],
            "forward_daily_snapshot_capture_required",
        )
        self.assertIn(
            "no_historical_option_quote_bbo_endpoint",
            summary["lane_next_step_plan_history_backfill_blockers"],
        )
        self.assertFalse(summary["lane_next_step_plan_snapshot_updated_since_is_backfill_capability"])
        self.assertEqual(summary["iteration_plan_status"], "active")
        self.assertEqual(
            summary["iteration_plan_priority_action"],
            "wait_until_next_missing_date_is_capturable:2026-05-21",
        )
        self.assertFalse(summary["iteration_plan_safe_to_tune_filters"])
        self.assertEqual(
            summary["iteration_plan_steps"],
            [
                {
                    "step": "post_close_full_universe_capture",
                    "status": "scheduled",
                    "action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "scheduled_utc": "2026-05-21T20:20:00Z",
                    "actionable_now": False,
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "premature_run_guard": "target_date_capturable_guard",
                    "command": [
                        "python",
                        "scripts/run_ai_commodity_opra_progress.py",
                        "--force-capture",
                        "--target-date",
                        "2026-05-21",
                    ],
                },
                {
                    "step": "filter_tuning",
                    "status": "locked",
                    "action": "hold_filters_until_exact_replay_is_ready",
                    "scheduled_utc": None,
                    "actionable_now": None,
                    "not_before_utc": None,
                    "premature_run_guard": None,
                    "command": None,
                },
            ],
        )
        self.assertEqual(summary["next_execution_status"], "waiting_until_not_before")
        self.assertEqual(summary["next_execution_selected_step"], "post_close_full_universe_capture")
        self.assertTrue(summary["next_execution_matches_next_timed_event"])
        self.assertFalse(summary["next_execution_actionable_now"])
        self.assertEqual(summary["next_execution_not_before_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(summary["next_execution_runbook_guard_status"], "clock_guard_active")
        self.assertEqual(summary["next_execution_runbook_summary"], "wait_until_the_not_before_time_then_rerun_the_probe_or_command")
        self.assertEqual(summary["next_execution_runbook_recommended_action"], "wait_until_not_before")
        self.assertEqual(
            summary["next_execution_runbook_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["next_execution_runbook_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(
            summary["next_execution_runbook_success_criteria"],
            [
                "capture_target_complete_true",
                "shared_quote_dates_increase_or_target_was_already_complete",
            ],
        )
        self.assertEqual(summary["run_next_execution_guard_summary_status"], "waiting_until_not_before")
        self.assertEqual(
            summary["run_next_execution_guard_summary_reason"],
            "waiting_until_not_before:2026-05-21T14:20:00-06:00",
        )
        self.assertFalse(summary["run_next_execution_command"])
        self.assertEqual(summary["run_next_execution_command_required_action"], "wait_until_not_before")
        self.assertEqual(
            summary["run_next_execution_guarded_command_to_run_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["goal_completion_evidence_plan_status"], "not_complete")
        self.assertEqual(
            summary["goal_completion_next_requirement_to_unblock"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            summary["goal_completion_next_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertTrue(summary["goal_completion_proof_source_isolation_requirement_passed"])
        self.assertEqual(
            summary["goal_completion_proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(summary["goal_completion_proof_source_isolation_blockers"], [])
        self.assertIn("exact_replay_is_profitable", summary["goal_completion_missing_evidence"])
        self.assertEqual(summary["exact_history_acquisition_status"], "forward_capture_required")
        self.assertEqual(summary["exact_history_backfill_status"], "forward_daily_snapshot_capture_required")
        self.assertEqual(summary["exact_history_next_capture_trade_date"], "2026-05-21")
        self.assertEqual(
            summary["exact_history_next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["exact_history_next_capture_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertFalse(summary["exact_history_can_accelerate_with_existing_sources"])
        self.assertEqual(summary["exact_replay_unlock_status"], "waiting_for_diagnostic_replay_history")
        self.assertEqual(summary["exact_replay_unlock_diagnostic_remaining_shared_quote_dates"], 87)
        self.assertEqual(summary["exact_replay_unlock_full_remaining_shared_quote_dates"], 99)
        self.assertEqual(summary["exact_replay_unlock_diagnostic_trade_date"], "2026-09-24")
        self.assertEqual(summary["exact_replay_unlock_full_trade_date"], "2026-10-12")
        self.assertEqual(
            summary["exact_replay_unlock_immediate_next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            summary["exact_replay_unlock_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertEqual(
            summary["exact_replay_readiness_checklist_status"],
            "waiting_for_exact_opra_history_depth",
        )
        self.assertFalse(summary["exact_replay_ready_to_run_full_exact_replay"])
        self.assertIn(
            "full_exact_replay_history_depth_available",
            summary["exact_replay_readiness_checklist_blockers"],
        )
        self.assertIn(
            "diagnostic_replay_waiting_for_exact_opra_history_depth",
            summary["exact_replay_unlock_blockers"],
        )
        self.assertEqual(
            summary["exact_replay_unlock_next_action"],
            "continue_forward_daily_alpaca_opra_capture",
        )
        self.assertEqual(
            summary["exact_history_backfill_capability_status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        self.assertEqual(
            summary["exact_history_backfill_missing_capability"],
            "historical_option_quote_bbo_method_for_contracts",
        )
        self.assertFalse(summary["exact_history_backfill_can_accelerate"])
        self.assertEqual(
            summary["exact_history_backfill_next_action"],
            "continue_forward_daily_alpaca_opra_snapshot_capture",
        )
        self.assertEqual(summary["exact_capture_progress_status"], "awaiting_guarded_capture_to_advance_history")
        self.assertEqual(summary["exact_capture_progress_target_trade_date"], "2026-05-21")
        self.assertEqual(
            summary["exact_capture_progress_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["exact_capture_progress_expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(summary["exact_capture_progress_remaining_shared_quote_dates_after_success"], 98)
        self.assertEqual(
            summary["exact_capture_progress_proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(summary["exact_capture_progress_proof_source_isolation_blockers"], [])
        self.assertIn(
            "proof_window.current_shared_quote_dates == 2",
            summary["exact_capture_progress_material_progress_if"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            summary["exact_capture_progress_material_progress_if"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            summary["exact_capture_progress_fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            summary["exact_capture_progress_fields_to_compare_after_run"],
        )
        self.assertEqual(summary["exact_capture_progress_blockers"], [])
        self.assertEqual(summary["exact_capture_progress_next_action"], "run_guarded_capture_after_not_before")
        self.assertEqual(summary["next_proof_event_status"], "waiting_until_next_proof_event")
        self.assertEqual(summary["next_proof_event_kind"], "exact_opra_history_capture")
        self.assertEqual(
            summary["next_proof_event_target_goal_requirement"],
            "has_required_exact_alpaca_opra_history_depth",
        )
        self.assertEqual(
            summary["next_proof_event_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(summary["next_proof_event_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertIn(
            "proof_window.current_shared_quote_dates increases",
            summary["next_proof_event_material_progress_if"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status stays isolated_to_alpaca_opra_proof_source",
            summary["next_proof_event_material_progress_if"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.remaining_shared_quote_dates",
            summary["next_proof_event_fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            summary["next_proof_event_fields_to_compare_after_run"],
        )
        self.assertIn(
            "missing_target_date_symbols_after",
            summary["next_proof_event_no_progress_blockers_to_record"],
        )
        self.assertIn(
            "proof_source_isolation_contract_blocked_after_capture",
            summary["next_proof_event_no_progress_blockers_to_record"],
        )
        self.assertEqual(summary["next_execution_runbook_snapshot"]["wait_minutes"], 120.0)
        self.assertEqual(
            summary["next_execution_command"],
            [
                "python",
                "scripts/run_ai_commodity_opra_progress.py",
                "--force-capture",
                "--target-date",
                "2026-05-21",
            ],
        )
        self.assertEqual(summary["next_execution_blockers"], ["waiting_until_not_before:2026-05-21T20:20:00Z"])
        self.assertEqual(summary["last_execution_status"], "not_due_yet")
        self.assertEqual(summary["last_execution_previous_step"], "fresh_opra_live_scan")
        self.assertEqual(summary["last_execution_blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])
        self.assertEqual(summary["last_execution_previous_runbook_guard_status"], "clock_guard_active")
        self.assertEqual(summary["last_execution_previous_runbook_recommended_action"], "wait_until_not_before")
        self.assertEqual(
            summary["last_execution_previous_runbook_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(summary["last_execution_previous_runbook_not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(summary["last_execution_previous_runbook_window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(summary["last_execution_previous_runbook_success_criteria"], ["fresh_scan_candidate_count_above_zero"])
        self.assertTrue(summary["last_execution_previous_runbook_command_matches_contract"])
        self.assertFalse(summary["last_execution_ran_from_runbook_card"])
        self.assertEqual(summary["last_execution_ran_from_runbook_card_inference"], "previous_runbook_card_waiting_until_not_before")
        self.assertEqual(summary["previous_proof_event_status"], "not_due_yet")
        self.assertEqual(summary["previous_proof_event_kind"], "fresh_opra_live_candidate_scan")
        self.assertEqual(summary["previous_proof_event_target_goal_requirement"], "live_scan_has_verifiable_candidate")
        self.assertFalse(summary["previous_proof_event_advanced_goal_requirement"])
        self.assertFalse(summary["previous_proof_event_material_progress"])
        self.assertEqual(summary["previous_proof_event_blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])
        self.assertEqual(summary["last_execution_checks"], [])
        self.assertEqual(summary["run_classification"], "unchanged_waiting_for_next_capture")
        self.assertEqual(summary["no_progress_reason"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(summary["non_material_flags"], ["scan_liquidity_gate_distance_delta_below_materiality"])
        self.assertEqual(summary["scan_ev_shortfall_delta"], -2.0)
        self.assertEqual(summary["scan_candidate_heuristic_ev_delta"], 2.0)
        self.assertEqual(summary["scan_liquidity_gate_distance_delta"], -5.0)
        self.assertEqual(summary["source_quality_status"], "usable_quotes_waiting_for_history_depth")
        self.assertEqual(summary["source_quality_quote_rows"], 6946)
        self.assertEqual(summary["capture_action_status"], "waiting_for_next_market_close")
        self.assertEqual(summary["capture_timing_status"], "scheduled_future")
        self.assertEqual(summary["capture_next_scheduled_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(summary["capture_scope"], "ai_commodity_scan_universe")
        self.assertEqual(summary["capture_symbol_count"], 24)
        self.assertTrue(summary["capture_target_complete"])
        self.assertEqual(summary["capture_missing_target_symbols_after"], [])
        self.assertFalse(summary["diagnostic_ready"])
        self.assertEqual(summary["diagnostic_remaining_shared_quote_dates"], 87)
        self.assertEqual(summary["remaining_market_day_capture_count"], 99)
        self.assertEqual(summary["diagnostic_remaining_market_day_capture_count"], 87)
        self.assertEqual(summary["full_replay_remaining_market_day_capture_count"], 99)
        self.assertTrue(summary["legacy_weekday_fields_are_market_day_aware"])
        self.assertEqual(summary["approx_diagnostic_ready_date"], "2026-09-18")
        self.assertEqual(summary["diagnostic_replay_status"], "skipped")
        self.assertEqual(summary["diagnostic_replay_total_trades"], 0)
        self.assertEqual(summary["diagnostic_replay_blockers"], ["insufficient_replay_simulation_quote_dates"])
        self.assertEqual(summary["diagnostic_replay_next_action"], "accumulate_replay_simulation_shared_opra_dates")
        self.assertIsNone(summary["diagnostic_replay_profit_factor"])
        self.assertFalse(summary["diagnostic_replay_can_verify_profitability"])
        self.assertEqual(summary["fresh_scan_retest_status"], "scheduled")
        self.assertEqual(summary["scan_historical_data_ready_count"], 24)
        self.assertEqual(summary["scan_historical_data_required_count"], 24)
        self.assertEqual(summary["scan_candidate_count"], 0)
        self.assertIsNone(summary["scan_candidate_symbols"])
        self.assertEqual(summary["scan_drop_diagnostics"][0]["drop_key"], "option_liquidity")
        self.assertEqual(summary["scan_drop_diagnostics"][0]["example_symbols"], ["FCX", "ALB"])
        self.assertEqual(summary["scan_fresh_scan_calendar"], "us_equity_market_days")
        self.assertEqual(
            summary["scan_fresh_scan_holiday_calendar_source"],
            "NYSE/Nasdaq US equity market holiday rules",
        )
        self.assertTrue(summary["scan_fresh_scan_trade_date_is_market_day"])
        self.assertEqual(summary["scan_next_fresh_scan_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(summary["scan_fresh_scan_window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(summary["fresh_scan_retest_next_action"], "wait_until_fresh_opra_scan_window")
        self.assertEqual(summary["fresh_scan_retest_primary_probe_symbol"], "FCX")
        self.assertEqual(summary["fresh_scan_retest_quote_age_only_blocker_symbols"], ["FCX"])
        self.assertEqual(summary["fresh_scan_retest_structural_liquidity_blocker_symbols"], ["ALB"])
        self.assertEqual(summary["fresh_scan_decision_status"], "fresh_scan_zero_candidates_structural_review")
        self.assertEqual(summary["fresh_scan_decision_branch"], "structural_blocker_branch")
        self.assertEqual(
            summary["fresh_scan_decision_next_action"],
            "rank_remaining_drop_counts_without_relaxing_production_filters",
        )
        self.assertFalse(summary["fresh_scan_decision_safe_to_tune_filters"])
        self.assertEqual(
            summary["fresh_scan_decision_selected_outcome_effect"],
            "remains_blocked_records_raw_scan_drop_reasons",
        )
        self.assertEqual(
            summary["fresh_scan_decision_selected_outcome_next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertIn("live_candidate_recovery_plan", summary)
        self.assertIn("live_candidate_recovery_status", summary)
        self.assertEqual(
            summary["live_candidate_recovery_next_command_role"],
            "history_unlock_before_filter_mutation",
        )
        self.assertEqual(
            summary["live_candidate_recovery_history_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            summary["live_candidate_recovery_scan_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            summary["live_candidate_recovery_read_only_review_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        summary_command_roles = {
            item["role"]: item for item in summary["live_candidate_recovery_command_roles"]
        }
        self.assertTrue(summary_command_roles["history_unlock_before_filter_mutation"]["applies_now"])
        self.assertFalse(summary_command_roles["fresh_live_scan_evidence"]["applies_now"])
        self.assertFalse(summary["live_candidate_recovery_safe_to_tune_production_filters"])
        self.assertIn("live_scan_has_candidate", summary["live_candidate_recovery_blockers"])
        self.assertEqual(summary["live_candidate_recovery_dominant_drop_key"], "option_liquidity")
        self.assertGreater(summary["live_candidate_recovery_read_only_recovery_queue_count"], 0)
        self.assertEqual(
            summary["live_candidate_recovery_first_read_only_review"]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            summary["live_candidate_recovery_first_read_only_review_by_drop"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            summary["live_candidate_recovery_read_only_recovery_priority_order"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            summary["live_candidate_recovery_read_only_recovery_watchlist"][0]["symbol"],
            "FCX",
        )
        self.assertIn(
            "future_fresh_alpaca_opra_scan.candidate_count > 0",
            summary["live_candidate_recovery_read_only_recovery_material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_queue",
            summary["live_candidate_recovery_read_only_recovery_evidence_fields"],
        )
        self.assertEqual(summary["live_candidate_recovery_read_only_symbols_to_watch"], ["FCX", "ALB"])
        self.assertEqual(
            summary["live_candidate_recovery_read_only_next_review_steps"][0]["step"],
            "read_only_review_option_liquidity_FCX",
        )
        self.assertEqual(
            summary["fresh_scan_decision_outcome_matrix"][0]["condition"],
            "fresh_scan_candidate_count_above_zero",
        )
        self.assertEqual(
            summary["fresh_scan_decision_outcome_matrix"][1]["target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(summary["post_fresh_scan_research_backlog_status"], "queued_until_exact_replay_unlock")
        self.assertEqual(summary["post_fresh_scan_research_backlog_hypothesis_count"], 1)
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_unlock_status"],
            "locked_until_exact_replay_can_measure_filter_changes",
        )
        self.assertIn(
            "enough_exact_shared_quote_dates",
            summary["post_fresh_scan_research_backlog_activation_blockers"],
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_variant_unlock_runway"]["history_depth_runway"][
                "current_shared_quote_dates"
            ],
            1,
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_variant_unlock_runway"]["history_depth_runway"][
                "full_replay_unlock_trade_date"
            ],
            "2026-10-12",
        )
        self.assertEqual(summary["post_fresh_scan_research_backlog_deferred_test_count"], 1)
        self.assertEqual(summary["post_fresh_scan_research_backlog_deferred_variant_run_recipe_count"], 2)
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_recipe_audit_status"],
            "queued_locked_with_verified_opra_recipe_contracts",
        )
        self.assertTrue(summary["post_fresh_scan_research_backlog_deferred_variant_recipes_opra_backed"])
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_config_materialization_command"],
            "python scripts/run_ai_commodity_opra_progress.py --materialize-deferred-variant-configs",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_execution_plan_status"],
            "locked_until_activation_gates_pass",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_activation_unlock_plan"][
                "current_primary_gate"
            ],
            "enough_exact_shared_quote_dates",
        )
        self.assertEqual(summary["post_fresh_scan_research_backlog_deferred_variant_ordered_sweep_count"], 2)
        self.assertIn(
            "scripts/run_research_variant_cycle.py",
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_command"],
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep"]["variant_id"],
            "liquidity_leg12_slippage15",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_run_guard"],
            "do_not_run_until_all_activation_gates_pass",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_status"],
            "locked_until_activation_gates_pass",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_first_blocking_gate"],
            "enough_exact_shared_quote_dates",
        )
        self.assertEqual(
            summary[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_blocked_by_goal_requirements"
            ],
            ["has_required_exact_alpaca_opra_history_depth", "exact_replay_is_profitable"],
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_ready_trade_date"],
            "2026-10-12",
        )
        self.assertEqual(
            summary[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_ready_not_before_user_local"
            ],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_first_sweep_next_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            summary[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_next_unlock_not_before_user_local"
            ],
            "2026-05-21T14:20:00-06:00",
        )
        self.assertEqual(
            summary[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_replay_command_when_unlocked"
            ],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_variant_result_collection_command"],
            "python scripts/run_ai_commodity_opra_progress.py --collect-deferred-variant-results",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_test_queue"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_test_queue"][0]["status"],
            "queued_locked",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_test_queue"][0]["variant_run_recipe_count"],
            2,
        )
        self.assertIn(
            "proof_source_label == alpaca_opra_daily_snapshot",
            summary["post_fresh_scan_research_backlog_deferred_test_queue"][0]["guardrails"],
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_deferred_test_queue"][0]["variant_blueprint"][
                "research_variant_support"
            ],
            "ai_commodity_option_filter_override_supported",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_hypotheses"][0]["hypothesis"],
            "separate_quote_age_from_structural_spread_and_depth_blockers",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_filter_policy"],
            "locked_until_exact_alpaca_opra_replay_is_ready",
        )
        self.assertEqual(
            summary["post_fresh_scan_research_backlog_bar_only_policy"],
            "research_only_never_satisfies_exact_alpaca_opra_profitability_gate",
        )
        self.assertTrue(summary["automation_covers_fresh_opra_scan"])
        self.assertTrue(summary["automation_covers_post_close_capture"])
        self.assertTrue(summary["automation_schedule_exact_required_times"])
        self.assertEqual(summary["automation_unexpected_intraday_times"], [])
        self.assertEqual(summary["automation_scheduled_intraday_times"], ["08:10:00", "14:20:00"])
        self.assertEqual(summary["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(summary["proof_source_shared_quote_dates"]["count"], 1)
        self.assertEqual(summary["all_trusted_shared_quote_dates"]["count"], 2)
        self.assertEqual(summary["excluded_trusted_shared_quote_dates"]["count"], 1)
        self.assertEqual(summary["excluded_trusted_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(summary["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(
            summary["proof_source_isolation_exact_profitability_proof_source_labels"],
            ["alpaca_opra_daily_snapshot"],
        )
        self.assertEqual(summary["proof_source_isolation_research_only_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(
            summary["proof_source_isolation_non_proof_sources_with_quotes_in_scope"],
            ["thetadata_free_eod"],
        )
        self.assertEqual(summary["proof_source_isolation_non_proof_sources_with_shared_dates"], [])
        self.assertTrue(summary["proof_source_isolation_top_level_shared_dates_match_proof_source"])
        self.assertEqual(summary["proof_source_isolation_blockers"], [])
        self.assertEqual(summary["proof_source_isolation_next_action"], "continue_using_alpaca_opra_proof_source")
        self.assertEqual(
            summary["proof_source_per_source_shared_quote_dates"][0]["required_symbol_coverage"]["available_required_symbol_count"],
            24,
        )
        self.assertEqual(summary["commodity_research_lab_status"], "commodity_research_only")
        self.assertEqual(summary["commodity_research_lab_total_bar_fallback_trades"], 9)
        self.assertEqual(summary["commodity_research_lab_total_exact_bid_ask_trades"], 0)
        self.assertEqual(summary["commodity_research_lab_positive_bar_only_lanes"], [])
        self.assertEqual(
            summary["commodity_research_lab_next_action"],
            "do_not_promote_bar_only_research_accumulate_exact_alpaca_opra_bid_ask_dates",
        )
        self.assertEqual(summary["scan_proof_alignment_status"], "scan_universe_exceeds_exact_proof_universe")
        self.assertEqual(summary["scan_proof_universe_count"], 9)
        self.assertEqual(summary["scan_proof_scan_universe_count"], 24)
        self.assertEqual(summary["scan_proof_symbols_without_exact_proof_count"], 15)
        self.assertEqual(summary["scan_proof_candidate_symbols_outside_exact_proof"], [])
        self.assertEqual(summary["scan_proof_blocker_symbols_outside_exact_proof"], ["ALB"])
        self.assertEqual(
            summary["scan_proof_next_action"],
            "expand_exact_alpaca_opra_capture_to_scan_universe_or_treat_outside_symbols_as_research_only",
        )

    def test_write_progress_report_appends_compact_history_entry(self):
        report = {
            "generated_at": "2026-05-21T03:45:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100"],
                "source_quality_status": "usable_quotes_waiting_for_history_depth",
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
                "live_scan_candidate_count": 0,
            },
            "automation_health": {"healthy": True, "status": "ACTIVE", "kind": "heartbeat"},
            "lane_next_step": {
                "phase": "capture_wait",
                "priority_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "primary_blocker": "shared_quote_dates:1/100",
                "safe_to_tune_filters": False,
            },
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "source_labels_required": ["alpaca_opra_daily_snapshot"],
                "total_quote_rows": 6946,
                "available_required_underlying_count": 9,
                "required_underlying_count": 9,
                "min_executable_quote_pct": 100.0,
                "total_missing_bid_ask_rows": 0,
                "total_crossed_quote_rows": 0,
                "lowest_quote_row_symbols": [],
            },
                "progress_delta": {
                    "previous_report_found": True,
                    "run_classification": "unchanged_waiting_for_next_capture",
                    "no_progress_reason": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "non_material_flags": ["scan_liquidity_gate_distance_delta_below_materiality"],
                    "verification_gates_still_blocked": ["enough_exact_shared_quote_dates"],
                "scan_ev_shortfall_delta": 0.0,
                "scan_candidate_heuristic_ev_delta": 0.0,
                "scan_liquidity_gate_distance_delta": 0.0,
                "improvement_flags": [],
                "regression_flags": [],
            },
            "capture": {
                "status": "skipped_existing_shared_date",
                "target_date": "2026-05-20",
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "next_scheduled_capture": {
                    "timing_status": "scheduled_future",
                    "scheduled_utc": "2026-05-21T20:20:00Z",
                },
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "diagnostic_required_shared_quote_dates": 88,
                "diagnostic_remaining_shared_quote_dates": 87,
                "diagnostic_ready": False,
                "capture_cadence": "one shared exact OPRA date per market-day capture",
                "current_target_trade_date": "2026-05-21",
                "current_target_captured": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "capture_health_status": "capture_due_for_current_target",
                "missed_capture_trade_date_count": 0,
                "missed_capture_trade_dates_since_latest_shared": [],
                "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-18",
                "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
            },
            "shared_quote_dates_after": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
            "readiness": {
                "status": "partial",
                "blocker": "thin_required_history",
                "shared_required_quote_dates": {"count": 1},
                "minimums": {"min_shared_quote_dates": 100},
            },
            "replay": {"error": "Selected dates: 1."},
            "diagnostic_replay": {
                "status": "diagnostic_error",
                "error": "No trades selected.",
                "total_trades": 0,
                "blockers": ["diagnostic_replay_error:No trades selected."],
                "next_action": "fix_or_wait_out_diagnostic_replay_error",
                "profit_factor": 0.0,
                "quote_coverage_pct": 0.0,
                "can_verify_profitability": False,
            },
            "scan": {
                "candidate_count": 0,
                "returned_count": 0,
                "scan_funnel": {"drop_counts": {"option_liquidity": 9, "tech_score": 8}},
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["AA", "ALB"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "fresh_scan_retest_plan": {
                    "status": "scheduled",
                    "next_action": "wait_until_fresh_opra_scan_window",
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "primary_probe_symbol": "FCX",
                    "primary_probe_reasons": ["stale_leg_quote"],
                    "primary_probe_quote_age_excess_hours": 1.85,
                    "quote_age_only_blocker_symbols": ["FCX"],
                    "structural_liquidity_blocker_symbols": ["ALB"],
                    "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                    "if_still_zero_candidates": ["rank_remaining_drop_counts"],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_progress_report(report, Path(tmp))
            history_path = Path(artifacts["history_jsonl"])
            entries = [json.loads(line) for line in history_path.read_text(encoding="utf8").splitlines()]
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            latest_md = Path(artifacts["latest_markdown"]).read_text(encoding="utf8")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["generated_at"], "2026-05-21T03:45:00Z")
        self.assertEqual(entries[0]["verification_status"], "not_verified")
        self.assertEqual(entries[0]["lane_phase"], "capture_wait")
        self.assertEqual(entries[0]["lane_primary_blocker"], "shared_quote_dates:1/100")
        self.assertEqual(entries[0]["run_classification"], "unchanged_waiting_for_next_capture")
        self.assertEqual(entries[0]["no_progress_reason"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(entries[0]["non_material_flags"], ["scan_liquidity_gate_distance_delta_below_materiality"])
        self.assertEqual(entries[0]["iteration_ledger_status"], "unchanged_waiting_for_next_capture")
        self.assertEqual(entries[0]["iteration_ledger_improvements"], [])
        self.assertEqual(entries[0]["iteration_ledger_regressions"], [])
        self.assertIn("alpaca_opra_daily_snapshot_shared_quote_dates:1/100", entries[0]["iteration_ledger_active_blockers"])
        self.assertEqual(
            entries[0]["iteration_ledger_filter_policy"],
            "locked_until_exact_alpaca_opra_replay_is_ready",
        )
        self.assertEqual(
            entries[0]["iteration_ledger_next_evidence_action"],
            "wait_until_next_missing_date_is_capturable:2026-05-21",
        )
        self.assertEqual(entries[0]["iteration_ledger_shared_quote_dates"]["current"], 1)
        self.assertEqual(
            entries[0]["iteration_ledger_capture_runway"]["approx_exact_replay_ready_date"],
            "2026-10-06",
        )
        self.assertEqual(entries[0]["iteration_ledger_capture_debt"]["status"], "blocked_until_forward_captures")
        self.assertEqual(entries[0]["iteration_ledger_capture_debt"]["forward_capture_queue"][0]["trade_date"], "2026-05-21")
        self.assertEqual(
            entries[0]["iteration_ledger_capture_debt"]["unlock_milestones"]["diagnostic_replay"][
                "unlock_trade_date"
            ],
            "2026-09-24",
        )
        self.assertEqual(entries[0]["capture_debt"]["status"], "blocked_until_forward_captures")
        self.assertEqual(entries[0]["capture_debt"]["remaining_shared_quote_dates"], 99)
        self.assertEqual(
            entries[0]["capture_continuity_contract"]["status"],
            "on_track_no_missed_capture_dates",
        )
        self.assertEqual(entries[0]["capture_continuity_contract"]["missed_capture_trade_dates"], [])
        self.assertEqual(
            entries[0]["capture_continuity_contract"]["missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertEqual(
            entries[0]["iteration_ledger_unlock_conditions"]["diagnostic_replay"]["remaining_shared_quote_dates"],
            87,
        )
        self.assertEqual(
            entries[0]["iteration_ledger_unlock_conditions"]["filter_tuning"]["status"],
            "locked_until_exact_replay_is_ready",
        )
        self.assertEqual(entries[0]["fresh_scan_decision_status"], "fresh_scan_zero_candidates_structural_review")
        self.assertEqual(entries[0]["fresh_scan_decision_branch"], "structural_blocker_branch")
        self.assertEqual(
            entries[0]["fresh_scan_decision_next_action"],
            "rank_remaining_drop_counts_without_relaxing_production_filters",
        )
        self.assertFalse(entries[0]["fresh_scan_decision_safe_to_tune_filters"])
        self.assertEqual(entries[0]["source_quality_status"], "usable_quotes_waiting_for_history_depth")
        self.assertEqual(entries[0]["capture_next_scheduled_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(entries[0]["diagnostic_replay_status"], "diagnostic_error")
        self.assertEqual(entries[0]["diagnostic_replay_error"], "No trades selected.")
        self.assertEqual(entries[0]["diagnostic_replay_blockers"], ["diagnostic_replay_error:No trades selected."])
        self.assertEqual(entries[0]["diagnostic_replay_next_action"], "fix_or_wait_out_diagnostic_replay_error")
        self.assertFalse(entries[0]["diagnostic_replay_can_verify_profitability"])
        self.assertEqual(entries[0]["artifacts"]["latest_json"], artifacts["latest_json"])
        self.assertEqual(entries[0]["artifacts"]["history_jsonl"], artifacts["history_jsonl"])
        self.assertEqual(latest["artifacts"], artifacts)
        self.assertEqual(latest["verification_status"], entries[0]["verification_status"])
        self.assertEqual(latest["verified"], entries[0]["verified"])
        self.assertEqual(latest["capture_debt"], entries[0]["capture_debt"])
        self.assertEqual(latest["capture_continuity_contract"], entries[0]["capture_continuity_contract"])
        self.assertEqual(latest["goal_completion_status"], entries[0]["goal_completion_status"])
        self.assertEqual(
            latest["goal_completion_failed_requirements"],
            entries[0]["goal_completion_failed_requirements"],
        )
        self.assertEqual(
            latest["goal_completion_may_mark_goal_complete"],
            entries[0]["goal_completion_may_mark_goal_complete"],
        )
        self.assertEqual(latest["progress_history_summary"]["status"], "summarized")
        self.assertEqual(latest["progress_history_summary"]["entry_count_including_current"], 1)
        self.assertFalse(latest["progress_history_summary"]["previous_entry_found"])
        self.assertEqual(latest["progress_history_summary"]["latest_generated_at"], "2026-05-21T03:45:00Z")
        self.assertEqual(
            latest["progress_history_summary"]["latest_history_written_at"],
            entries[0]["history_written_at"],
        )
        self.assertIsNone(latest["progress_history_summary"]["previous_history_written_at"])
        self.assertEqual(
            latest["progress_history_summary"]["latest_next_blocker"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertEqual(latest["progress_history_summary"]["same_next_blocker_streak"], 1)
        self.assertIn("## Progress History Trend", latest_md)
        self.assertIn("## Capture Debt And Continuity", latest_md)
        self.assertIn("Missed capture policy:", latest_md)
        self.assertIn("Latest history written at:", latest_md)
        self.assertIn("Latest blocker: `alpaca_opra_daily_snapshot_shared_quote_dates:1/100`", latest_md)

    def test_load_capture_automation_health_reports_active_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            automation_dir = codex_home / "automations" / "ai-commodity-opra-capture"
            automation_dir.mkdir(parents=True)
            (automation_dir / "automation.toml").write_text(
                '\n'.join(
                    [
                        'id = "ai-commodity-opra-capture"',
                        'kind = "heartbeat"',
                        'name = "AI Commodity OPRA Capture"',
                        'prompt = "Run `python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest` first, then follow guarded_command_decision and guarded_command_decision_next_command_when_allowed. Run the returned command only when run_next_execution_command is true; if run_next_execution_command is false, run run_auxiliary_proof_event_command_display only when run_auxiliary_proof_event_command is true and preserve run_auxiliary_proof_event_no_mutation_guard. Follow lane_iteration_plan command recipes, inspect iteration_ledger, lane_next_step_plan, next_execution_runbook_card, auxiliary_proof_event_queue, run_auxiliary_proof_event_guard_summary, previous_auxiliary_proof_event_outcome, goal_completion_audit, goal_completion_verification_contract, proof_source_isolation_contract, exact_capture_progress_contract, capture_continuity_contract, exact_replay_unlock_contract, exact_profitability_blocker_review, exact_profitability_history_depth_runway, deferred_variant_execution_plan, deferred_variant_promotion_review, fresh_scan_iteration_decision, fresh_scan_post_run_evaluation, exact_capture_post_run_evaluation, exact_history_backfill_capability_audit, zero_candidate_diagnostic_plan, profitability_evidence_scorecard_post_event_readback_packet, profitability_evidence_scorecard_readback_projection_command, profitability_evidence_scorecard_delta_baseline_comparison_no_progress_condition_results, profitability_evidence_scorecard_delta_baseline_comparison_no_progress_detected, and post_run_playbook. Treat scan.scan_drop_reason_audit_status plus scan.scan_drop_reason_count as the raw drop-reason audit guard, inspect local_exact_store_usage_decision and local_exact_store_refresh_can_advance_history_depth before waiting for another capture, respect not-before times, preserve target_date_capturable_guard, and require snapshot_updated_since_is_backfill_capability before using updated_since as historical BBO backfill."',
                        'status = "ACTIVE"',
                        'rrule = "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,14;BYMINUTE=10,20;BYSECOND=0;BYSETPOS=1,4"',
                        'target_thread_id = "thread-1"',
                    ]
                ),
                encoding="utf8",
            )

            health = load_capture_automation_health(codex_home=codex_home)

        self.assertTrue(health["present"])
        self.assertTrue(health["healthy"])
        self.assertEqual(health["status"], "ACTIVE")
        self.assertEqual(health["kind"], "heartbeat")
        self.assertTrue(health["target_thread_id_present"])
        self.assertTrue(health["prompt_mentions_progress_runner"])
        self.assertTrue(health["prompt_mentions_next_execution_probe"])
        self.assertTrue(health["prompt_mentions_lane_iteration_plan"])
        self.assertTrue(health["prompt_mentions_iteration_ledger"])
        self.assertTrue(health["prompt_mentions_lane_next_step_plan"])
        self.assertTrue(health["prompt_mentions_goal_completion_audit"])
        self.assertTrue(health["prompt_mentions_goal_completion_verification_contract"])
        self.assertTrue(health["prompt_mentions_fresh_scan_iteration_decision"])
        self.assertTrue(health["prompt_mentions_fresh_scan_post_run_evaluation"])
        self.assertTrue(health["prompt_mentions_exact_capture_post_run_evaluation"])
        self.assertTrue(health["prompt_mentions_exact_capture_progress_contract"])
        self.assertTrue(health["prompt_mentions_capture_continuity_contract"])
        self.assertTrue(health["prompt_mentions_exact_replay_unlock_contract"])
        self.assertTrue(health["prompt_mentions_exact_profitability_blocker_review"])
        self.assertTrue(health["prompt_mentions_exact_profitability_history_depth_runway"])
        self.assertTrue(health["prompt_mentions_proof_source_isolation_contract"])
        self.assertTrue(health["prompt_mentions_exact_history_backfill_capability_audit"])
        self.assertTrue(health["prompt_mentions_deferred_variant_execution_plan"])
        self.assertTrue(health["prompt_mentions_deferred_variant_promotion_review"])
        self.assertTrue(health["prompt_mentions_zero_candidate_diagnostic_plan"])
        self.assertTrue(health["prompt_mentions_post_run_playbook"])
        self.assertTrue(health["prompt_mentions_auxiliary_proof_event_queue"])
        self.assertTrue(health["prompt_mentions_run_auxiliary_proof_event_guard"])
        self.assertTrue(health["prompt_mentions_previous_auxiliary_proof_event_outcome"])
        self.assertTrue(health["prompt_mentions_guarded_command_decision"])
        self.assertTrue(health["prompt_mentions_guarded_command_when_allowed"])
        self.assertTrue(health["prompt_mentions_next_execution_runbook_card"])
        self.assertTrue(health["prompt_mentions_run_next_execution_command_guard"])
        self.assertTrue(health["prompt_mentions_profitability_scorecard_readback_packet"])
        self.assertTrue(health["prompt_mentions_profitability_scorecard_readback_projection"])
        self.assertTrue(health["prompt_mentions_profitability_scorecard_no_progress_condition_results"])
        self.assertTrue(health["prompt_mentions_profitability_scorecard_no_progress_detected"])
        self.assertTrue(health["prompt_mentions_not_before_guard"])
        self.assertTrue(health["prompt_mentions_target_date_guard"])
        self.assertTrue(health["prompt_mentions_snapshot_updated_since_backfill_guard"])
        self.assertTrue(health["prompt_mentions_raw_drop_reason_audit_guard"])
        self.assertTrue(health["prompt_mentions_local_exact_store_guard"])
        self.assertEqual(health["scheduled_intraday_times"], ["08:10:00", "14:20:00"])
        self.assertTrue(health["covers_fresh_opra_scan"])
        self.assertTrue(health["covers_post_close_capture"])
        self.assertTrue(health["schedule_exact_required_times"])
        self.assertEqual(health["unexpected_intraday_times"], [])
        self.assertNotIn("blocker", health)

    def test_automation_schedule_coverage_applies_bysetpos_to_intraday_times(self):
        coverage = automation_schedule_coverage(
            "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,14;BYMINUTE=10,20;BYSECOND=0;BYSETPOS=1,4"
        )

        self.assertEqual(coverage["scheduled_intraday_times"], ["08:10:00", "14:20:00"])
        self.assertTrue(coverage["covers_fresh_opra_scan"])
        self.assertTrue(coverage["covers_post_close_capture"])
        self.assertTrue(coverage["schedule_exact_required_times"])
        self.assertEqual(coverage["unexpected_intraday_times"], [])

    def test_automation_schedule_coverage_flags_extra_intraday_times(self):
        coverage = automation_schedule_coverage(
            "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,14;BYMINUTE=10,20;BYSECOND=0"
        )

        self.assertEqual(
            coverage["scheduled_intraday_times"],
            ["08:10:00", "08:20:00", "14:10:00", "14:20:00"],
        )
        self.assertTrue(coverage["covers_fresh_opra_scan"])
        self.assertTrue(coverage["covers_post_close_capture"])
        self.assertFalse(coverage["schedule_exact_required_times"])
        self.assertEqual(coverage["unexpected_intraday_times"], ["08:20:00", "14:10:00"])

    def test_load_capture_automation_health_blocks_extra_intraday_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            automation_dir = codex_home / "automations" / "ai-commodity-opra-capture"
            automation_dir.mkdir(parents=True)
            (automation_dir / "automation.toml").write_text(
                '\n'.join(
                    [
                        'kind = "heartbeat"',
                        'prompt = "Run `python scripts/run_ai_commodity_opra_progress.py` from the repository root."',
                        'status = "ACTIVE"',
                        'rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,14;BYMINUTE=10,20;BYSECOND=0"',
                        'target_thread_id = "thread-1"',
                    ]
                ),
                encoding="utf8",
            )

            health = load_capture_automation_health(codex_home=codex_home)

        self.assertFalse(health["healthy"])
        self.assertTrue(health["covers_fresh_opra_scan"])
        self.assertTrue(health["covers_post_close_capture"])
        self.assertFalse(health["schedule_exact_required_times"])
        self.assertEqual(health["unexpected_intraday_times"], ["08:20:00", "14:10:00"])
        self.assertIn("schedule_has_unexpected_intraday_times", health["blocker"])

    def test_load_capture_automation_health_blocks_missing_fresh_scan_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            automation_dir = codex_home / "automations" / "ai-commodity-opra-capture"
            automation_dir.mkdir(parents=True)
            (automation_dir / "automation.toml").write_text(
                '\n'.join(
                    [
                        'kind = "heartbeat"',
                        'prompt = "Run `python scripts/run_ai_commodity_opra_progress.py` from the repository root."',
                        'status = "ACTIVE"',
                        'rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=20;BYSECOND=0"',
                        'target_thread_id = "thread-1"',
                    ]
                ),
                encoding="utf8",
            )

            health = load_capture_automation_health(codex_home=codex_home)

        self.assertFalse(health["healthy"])
        self.assertFalse(health["covers_fresh_opra_scan"])
        self.assertTrue(health["covers_post_close_capture"])
        self.assertIn("schedule_missing_fresh_opra_scan", health["blocker"])

    def test_load_capture_automation_health_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = load_capture_automation_health(codex_home=Path(tmp))

        self.assertFalse(health["present"])
        self.assertFalse(health["healthy"])
        self.assertEqual(health["blocker"], "automation_toml_missing")

    def test_load_capture_automation_health_reports_paused_or_wrong_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            automation_dir = codex_home / "automations" / "ai-commodity-opra-capture"
            automation_dir.mkdir(parents=True)
            (automation_dir / "automation.toml").write_text(
                '\n'.join(
                    [
                        'kind = "heartbeat"',
                        'prompt = "Run another command."',
                        'status = "PAUSED"',
                        'rrule = "FREQ=WEEKLY;BYDAY=MO"',
                    ]
                ),
                encoding="utf8",
            )

            health = load_capture_automation_health(codex_home=codex_home)

        self.assertTrue(health["present"])
        self.assertFalse(health["healthy"])
        self.assertIn("automation_not_active", health["blocker"])
        self.assertIn("prompt_missing_progress_runner", health["blocker"])
        self.assertIn("prompt_missing_next_execution_probe", health["blocker"])
        self.assertIn("prompt_missing_lane_iteration_plan", health["blocker"])
        self.assertIn("prompt_missing_iteration_ledger", health["blocker"])
        self.assertIn("prompt_missing_lane_next_step_plan", health["blocker"])
        self.assertIn("prompt_missing_goal_completion_audit", health["blocker"])
        self.assertIn("prompt_missing_goal_completion_verification_contract", health["blocker"])
        self.assertIn("prompt_missing_fresh_scan_iteration_decision", health["blocker"])
        self.assertIn("prompt_missing_fresh_scan_post_run_evaluation", health["blocker"])
        self.assertIn("prompt_missing_exact_capture_post_run_evaluation", health["blocker"])
        self.assertIn("prompt_missing_exact_capture_progress_contract", health["blocker"])
        self.assertIn("prompt_missing_capture_continuity_contract", health["blocker"])
        self.assertIn("prompt_missing_exact_replay_unlock_contract", health["blocker"])
        self.assertIn("prompt_missing_exact_profitability_blocker_review", health["blocker"])
        self.assertIn("prompt_missing_exact_profitability_history_depth_runway", health["blocker"])
        self.assertIn("prompt_missing_proof_source_isolation_contract", health["blocker"])
        self.assertIn("prompt_missing_exact_history_backfill_capability_audit", health["blocker"])
        self.assertIn("prompt_missing_deferred_variant_execution_plan", health["blocker"])
        self.assertIn("prompt_missing_deferred_variant_promotion_review", health["blocker"])
        self.assertIn("prompt_missing_zero_candidate_diagnostic_plan", health["blocker"])
        self.assertIn("prompt_missing_post_run_playbook", health["blocker"])
        self.assertIn("prompt_missing_auxiliary_proof_event_queue", health["blocker"])
        self.assertIn("prompt_missing_run_auxiliary_proof_event_guard", health["blocker"])
        self.assertIn("prompt_missing_next_execution_runbook_card", health["blocker"])
        self.assertIn("prompt_missing_run_next_execution_command_guard", health["blocker"])
        self.assertIn("prompt_missing_profitability_scorecard_readback_packet", health["blocker"])
        self.assertIn("prompt_missing_profitability_scorecard_readback_projection", health["blocker"])
        self.assertIn(
            "prompt_missing_profitability_scorecard_no_progress_condition_results",
            health["blocker"],
        )
        self.assertIn("prompt_missing_profitability_scorecard_no_progress_detected", health["blocker"])
        self.assertIn("prompt_missing_not_before_guard", health["blocker"])
        self.assertIn("prompt_missing_target_date_capturable_guard", health["blocker"])
        self.assertIn("prompt_missing_snapshot_updated_since_backfill_guard", health["blocker"])
        self.assertIn("prompt_missing_raw_drop_reason_audit_guard", health["blocker"])
        self.assertIn("prompt_missing_local_exact_store_guard", health["blocker"])

    def test_capture_status_distinguishes_duplicate_only_imports(self):
        rows = [{"contract_symbol": "FCX260619C00055000"}]

        self.assertEqual(
            capture_status_from_import(rows, {"imported_rows": 0, "duplicate_rows": 1}),
            "duplicate_capture_no_new_rows",
        )
        self.assertEqual(
            capture_status_from_import(rows, {"imported_rows": 1, "duplicate_rows": 0}),
            "captured",
        )
        self.assertEqual(capture_status_from_import([], None), "no_rows_captured")

    def test_symbols_missing_target_date_returns_only_incomplete_symbols(self):
        store = _FakeStore(
            {
                "FCX": ["2026-05-20"],
                "SLV": ["2026-05-19", "2026-05-20"],
                "VRT": ["2026-05-19"],
            }
        )

        missing = symbols_missing_target_date(store, ["FCX", "SLV", "VRT"], __import__("datetime").date(2026, 5, 20))

        self.assertEqual(missing, ["VRT"])

    def test_next_blocker_prioritizes_shared_quote_depth(self):
        readiness = {
            "status": "partial",
            "blocker": "thin_required_history",
            "shared_required_quote_dates": {"count": 2},
        }

        self.assertEqual(
            next_blocker(readiness=readiness, replay={"error": "too few dates"}, scan=None, min_shared_quote_dates=100),
            "shared_quote_dates:2/100",
        )

    def test_next_blocker_uses_source_filtered_quote_depth_when_provided(self):
        readiness = {
            "status": "ready_for_exact_replay",
            "shared_required_quote_dates": {"count": 100},
        }

        self.assertEqual(
            next_blocker(
                readiness=readiness,
                replay={},
                scan=None,
                min_shared_quote_dates=100,
                source_shared_quote_count=1,
                source_label="alpaca_opra_daily_snapshot",
            ),
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )

    def test_next_blocker_reports_zero_candidate_scan_after_readiness(self):
        readiness = {
            "status": "ready_for_exact_replay",
            "shared_required_quote_dates": {"count": 100},
        }
        scan = {
            "candidate_count": 0,
            "scan_funnel": {"drop_counts": {"momentum": 3, "option_liquidity": 9}},
        }

        self.assertEqual(
            next_blocker(readiness=readiness, replay={}, scan=scan, min_shared_quote_dates=100),
            "scan_zero_candidates:option_liquidity",
        )

    def test_build_proof_window_counts_remaining_capture_dates(self):
        window = build_proof_window(
            shared_dates=["2026-05-15", "2026-05-20"],
            min_shared_quote_dates=100,
            target_date=__import__("datetime").date(2026, 5, 20),
        )

        self.assertEqual(window["current_shared_quote_dates"], 2)
        self.assertEqual(window["remaining_shared_quote_dates"], 98)
        self.assertEqual(window["progress_pct"], 2.0)
        self.assertEqual(window["approx_weekdays_to_target"], 98)
        self.assertTrue(window["legacy_weekday_fields_are_market_day_aware"])
        self.assertFalse(window["diagnostic_ready"])
        self.assertEqual(window["diagnostic_required_shared_quote_dates"], 88)
        self.assertEqual(window["diagnostic_remaining_shared_quote_dates"], 86)
        self.assertEqual(window["diagnostic_requirement_basis"], "first_replay_simulation_day")
        self.assertEqual(window["diagnostic_replay_start_index"], 57)
        self.assertEqual(window["diagnostic_replay_exit_buffer_days"], 5)
        self.assertEqual(window["diagnostic_replay_max_dte"], 25)
        self.assertEqual(window["diagnostic_replay_min_simulation_shared_quote_dates"], 88)
        self.assertEqual(window["capture_calendar"], "us_equity_market_days")
        self.assertEqual(window["approx_market_days_to_target"], 98)
        self.assertEqual(window["remaining_market_day_capture_count"], 98)
        self.assertEqual(window["diagnostic_remaining_market_day_capture_count"], 86)
        self.assertEqual(window["full_replay_remaining_market_day_capture_count"], 98)
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_weekday"], "2026-09-23")
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_market_day"], "2026-09-23")
        self.assertEqual(window["current_target_trade_date"], "2026-05-20")
        self.assertTrue(window["current_target_captured"])
        self.assertEqual(window["next_missing_capture_trade_date"], "2026-05-21")
        self.assertEqual(window["missed_capture_trade_date_count"], 0)
        self.assertEqual(window["capture_health_status"], "on_track_current_target_captured")
        self.assertGreater(window["approx_completion_date_if_one_capture_per_weekday"], "2026-05-20")

    def test_build_proof_source_audit_excludes_non_alpaca_trusted_dates(self):
        symbols = ["FCX", "SLV"]
        store = _FakeStore(
            {
                "FCX": ["2026-05-15", "2026-05-20"],
                "SLV": ["2026-05-15", "2026-05-20"],
            },
            source_labels=["alpaca_opra_daily_snapshot", "thetadata_free_eod"],
            source_dates_by_symbol={
                "alpaca_opra_daily_snapshot": {
                    "FCX": ["2026-05-20"],
                    "SLV": ["2026-05-20"],
                },
                "thetadata_free_eod": {
                    "FCX": ["2026-05-15"],
                    "SLV": ["2026-05-15"],
                },
            },
        )

        audit = build_proof_source_audit(store, symbols)

        self.assertTrue(audit["trusted_only"])
        self.assertEqual(audit["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(audit["proof_source_shared_quote_dates"]["count"], 1)
        self.assertEqual(audit["proof_source_shared_quote_dates"]["first"], "2026-05-20")
        self.assertTrue(audit["all_required_symbols_have_proof_source_data"])
        self.assertEqual(
            audit["proof_source_required_symbol_coverage"]["available_required_symbol_count"],
            2,
        )
        self.assertTrue(audit["proof_source_required_symbol_coverage"]["trusted_only"])
        self.assertEqual(audit["all_trusted_shared_quote_dates"]["count"], 2)
        self.assertEqual(audit["excluded_trusted_shared_quote_dates"]["count"], 1)
        self.assertEqual(audit["excluded_trusted_shared_quote_dates"]["first"], "2026-05-15")
        self.assertEqual(audit["excluded_trusted_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(audit["alpaca_like_source_labels_seen"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["non_proof_alpaca_like_source_labels"], [])
        self.assertEqual(
            audit["decision"],
            "only_alpaca_opra_daily_snapshot_counts_for_exact_profitability_proof",
        )
        per_source = {entry["source_label"]: entry for entry in audit["per_source_shared_quote_dates"]}
        self.assertTrue(per_source["alpaca_opra_daily_snapshot"]["used_for_exact_profitability_proof"])
        self.assertFalse(per_source["thetadata_free_eod"]["used_for_exact_profitability_proof"])
        self.assertEqual(
            per_source["alpaca_opra_daily_snapshot"]["required_symbol_coverage"]["available_required_symbol_count"],
            2,
        )
        self.assertEqual(
            per_source["alpaca_opra_daily_snapshot"]["required_symbol_coverage"]["union_quote_dates"]["first"],
            "2026-05-20",
        )
        self.assertEqual(
            per_source["thetadata_free_eod"]["required_symbol_coverage"]["symbol_quote_date_counts"],
            {"FCX": 1, "SLV": 1},
        )

    def test_build_proof_source_audit_ignores_unrelated_global_alpaca_like_sources(self):
        symbols = ["FCX", "SLV"]
        store = _ScopedInventoryFakeStore(
            {
                "FCX": ["2026-05-20"],
                "SLV": ["2026-05-20"],
            },
            source_labels=["alpaca_opra_daily_snapshot", "alpaca_latest_snapshot"],
            source_dates_by_symbol={
                "alpaca_opra_daily_snapshot": {
                    "FCX": ["2026-05-20"],
                    "SLV": ["2026-05-20"],
                },
                "alpaca_latest_snapshot": {
                    "SPY": ["2026-05-20"],
                },
            },
        )

        audit = build_proof_source_audit(store, symbols)
        contract = build_proof_source_isolation_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "shared_quote_dates_after": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "proof_source_audit": audit,
            }
        )

        self.assertEqual(audit["store_inventory"]["source_labels_seen"], ["alpaca_opra_daily_snapshot", "alpaca_latest_snapshot"])
        self.assertEqual(audit["store_inventory"]["source_labels_with_quotes_in_scope"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["source_labels_seen"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["alpaca_like_source_labels_seen"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["non_proof_alpaca_like_source_labels"], [])
        self.assertEqual(contract["status"], "isolated_to_alpaca_opra_proof_source")
        self.assertNotIn("no_non_proof_alpaca_like_source_labels", contract["blockers"])

    def test_build_proof_source_audit_records_non_proof_partial_coverage(self):
        symbols = ["FCX", "CCJ"]
        store = _FakeStore(
            {
                "FCX": ["2026-05-15", "2026-05-20", "2026-05-21"],
                "CCJ": ["2026-05-20", "2026-05-21"],
            },
            source_labels=["alpaca_opra_daily_snapshot", "thetadata_free_eod"],
            source_dates_by_symbol={
                "alpaca_opra_daily_snapshot": {
                    "FCX": ["2026-05-20", "2026-05-21"],
                    "CCJ": ["2026-05-20", "2026-05-21"],
                },
                "thetadata_free_eod": {
                    "FCX": ["2026-05-15"],
                    "CCJ": [],
                },
            },
        )

        audit = build_proof_source_audit(store, symbols)

        self.assertEqual(audit["proof_source_shared_quote_dates"]["count"], 2)
        self.assertEqual(audit["all_trusted_shared_quote_dates"]["count"], 2)
        self.assertEqual(audit["excluded_trusted_shared_quote_dates"]["count"], 0)
        self.assertEqual(audit["excluded_trusted_source_labels"], [])
        self.assertEqual(audit["non_proof_partial_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(audit["non_proof_partial_quote_dates"]["count"], 1)
        self.assertEqual(audit["non_proof_partial_quote_dates"]["first"], "2026-05-15")
        partial_coverage = {
            item["source_label"]: item for item in audit["non_proof_source_quote_coverage"]
        }["thetadata_free_eod"]
        self.assertEqual(
            partial_coverage["coverage_type"],
            "partial_required_symbol_coverage_without_full_shared_date",
        )
        self.assertEqual(partial_coverage["available_required_symbol_count"], 1)
        self.assertEqual(partial_coverage["required_symbol_count"], 2)

        contract = build_proof_source_isolation_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "shared_quote_dates_after": {"count": 2, "first": "2026-05-20", "last": "2026-05-21"},
                "proof_source_audit": audit,
            }
        )

        self.assertEqual(contract["status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(contract["non_proof_partial_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(contract["non_proof_partial_quote_dates"]["first"], "2026-05-15")

    def test_build_proof_source_isolation_contract_allows_non_proof_inventory_only_as_research(self):
        contract = build_proof_source_isolation_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "shared_quote_dates_after": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "proof_source_audit": {
                    "trusted_only": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                    "all_trusted_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                    "excluded_trusted_shared_quote_dates": {"count": 0, "first": None, "last": None},
                    "excluded_trusted_source_labels": [],
                    "all_required_symbols_have_proof_source_data": True,
                    "non_proof_alpaca_like_source_labels": [],
                    "store_inventory": {
                        "source_labels_with_quotes_in_scope": [
                            "alpaca_opra_daily_snapshot",
                            "thetadata_free_eod",
                        ]
                    },
                    "per_source_shared_quote_dates": [
                        {
                            "source_label": "alpaca_opra_daily_snapshot",
                            "used_for_exact_profitability_proof": True,
                            "shared_quote_dates": {"count": 1},
                        },
                        {
                            "source_label": "thetadata_free_eod",
                            "used_for_exact_profitability_proof": False,
                            "shared_quote_dates": {"count": 0},
                        },
                    ],
                },
            }
        )

        self.assertEqual(contract["status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(contract["exact_profitability_proof_source_labels"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(contract["non_proof_sources_with_quotes_in_scope"], ["thetadata_free_eod"])
        self.assertEqual(contract["research_only_source_labels"], ["thetadata_free_eod"])
        self.assertEqual(contract["non_proof_sources_with_shared_dates"], [])
        self.assertTrue(contract["top_level_shared_dates_match_proof_source"])
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(contract["next_action"], "continue_using_alpaca_opra_proof_source")

    def test_build_proof_source_isolation_contract_blocks_non_proof_alpaca_like_or_mismatched_counts(self):
        contract = build_proof_source_isolation_contract(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "shared_quote_dates_after": {"count": 2},
                "proof_source_audit": {
                    "trusted_only": True,
                    "proof_source_label": "alpaca_opra_daily_snapshot",
                    "proof_source_shared_quote_dates": {"count": 1},
                    "all_trusted_shared_quote_dates": {"count": 2},
                    "excluded_trusted_shared_quote_dates": {"count": 1},
                    "excluded_trusted_source_labels": [],
                    "all_required_symbols_have_proof_source_data": True,
                    "non_proof_alpaca_like_source_labels": ["alpaca_latest_snapshot"],
                    "per_source_shared_quote_dates": [
                        {
                            "source_label": "alpaca_opra_daily_snapshot",
                            "used_for_exact_profitability_proof": True,
                            "shared_quote_dates": {"count": 1},
                        },
                        {
                            "source_label": "thetadata_free_eod",
                            "used_for_exact_profitability_proof": False,
                            "shared_quote_dates": {"count": 1},
                        },
                    ],
                },
            }
        )

        self.assertEqual(contract["status"], "proof_source_isolation_blocked")
        self.assertIn("top_level_shared_dates_match_proof_source_shared_dates", contract["blockers"])
        self.assertIn("non_proof_shared_dates_are_excluded", contract["blockers"])
        self.assertIn("no_non_proof_alpaca_like_source_labels", contract["blockers"])
        self.assertEqual(contract["next_action"], "repair_proof_source_isolation_before_profitability_claims")

    def test_build_proof_window_starts_completion_clock_on_uncaptured_target_date(self):
        window = build_proof_window(
            shared_dates=["2026-05-15"],
            min_shared_quote_dates=3,
            target_date=__import__("datetime").date(2026, 5, 20),
        )

        self.assertEqual(window["remaining_shared_quote_dates"], 2)
        self.assertFalse(window["diagnostic_ready"])
        self.assertEqual(window["diagnostic_required_shared_quote_dates"], 3)
        self.assertEqual(window["diagnostic_remaining_shared_quote_dates"], 2)
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_weekday"], "2026-05-21")
        self.assertEqual(window["next_missing_capture_trade_date"], "2026-05-20")
        self.assertEqual(window["missed_capture_trade_dates_since_latest_shared"], ["2026-05-18", "2026-05-19"])
        self.assertEqual(window["capture_health_status"], "missed_prior_capture_dates")
        self.assertEqual(window["approx_completion_date_if_one_capture_per_weekday"], "2026-05-21")

    def test_build_proof_window_skips_weekends_and_market_holidays_for_next_missing_capture_date(self):
        window = build_proof_window(
            shared_dates=["2026-05-22"],
            min_shared_quote_dates=2,
            target_date=__import__("datetime").date(2026, 5, 22),
        )

        self.assertEqual(window["next_missing_capture_trade_date"], "2026-05-26")
        self.assertFalse(window["diagnostic_ready"])
        self.assertEqual(window["diagnostic_remaining_shared_quote_dates"], 1)
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_weekday"], "2026-05-26")
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_market_day"], "2026-05-26")
        self.assertEqual(window["approx_completion_date_if_one_capture_per_weekday"], "2026-05-26")
        self.assertEqual(window["approx_completion_date_if_one_capture_per_market_day"], "2026-05-26")

    def test_build_proof_window_marks_current_target_due_when_no_prior_miss(self):
        window = build_proof_window(
            shared_dates=[],
            min_shared_quote_dates=2,
            target_date=__import__("datetime").date(2026, 5, 20),
        )

        self.assertFalse(window["current_target_captured"])
        self.assertFalse(window["diagnostic_ready"])
        self.assertEqual(window["diagnostic_remaining_shared_quote_dates"], 2)
        self.assertEqual(window["approx_diagnostic_ready_date_if_one_capture_per_weekday"], "2026-05-21")
        self.assertEqual(window["missed_capture_trade_date_count"], 0)
        self.assertEqual(window["capture_health_status"], "capture_due_for_current_target")

    def test_diagnostic_replay_requirement_matches_replay_loop_runway(self):
        self.assertEqual(replay_simulation_min_shared_quote_dates(), 88)
        self.assertEqual(replay_simulation_min_shared_quote_dates(max_dte=21), 84)
        self.assertEqual(diagnostic_replay_required_shared_quote_dates(100), 88)
        self.assertEqual(diagnostic_replay_required_shared_quote_dates(50, max_dte=21), 50)

    def test_diagnostic_replay_max_dte_uses_ai_commodity_playbook_target(self):
        fake_wfo = SimpleNamespace(
            DTE_MIN=1,
            DTE_MAX=60,
            STRATEGY_PROFILE={"targets": {"dte_optimal": 25}},
            STRATEGY_PROFILES={
                "equity": {"targets": {"dte_optimal": 25}},
                "index": {"targets": {"dte_optimal": 21}},
            },
            REPLAY_PLAYBOOKS={
                "ai_commodity_infra_observation": {
                    "id": "ai_commodity_infra_observation",
                }
            },
        )

        max_dte = diagnostic_replay_max_dte_from_wfo(fake_wfo)

        self.assertEqual(max_dte, 35)
        self.assertEqual(replay_simulation_min_shared_quote_dates(max_dte=max_dte), 98)

    def test_build_verified_profitability_gate_reports_current_blockers(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "usable_quotes_waiting_for_history_depth"},
                "readiness": {"status": "partial", "blocker": "thin_required_history"},
                "replay": {"error": "Selected dates: 1."},
                "scan": {"candidate_count": 0},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                    "candidate_symbols": [],
                    "live_scan_candidates_all_inside_exact_proof": False,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertEqual(gate["status"], "not_verified")
        self.assertTrue(gate["gates"]["alpaca_sip_opra_provider"])
        self.assertTrue(gate["gates"]["alpaca_opra_source_filtered"])
        self.assertTrue(gate["gates"]["alpaca_opra_source_quality_usable"])
        self.assertTrue(gate["gates"]["capture_scope_full_scan_universe"])
        self.assertTrue(gate["gates"]["capture_target_complete"])
        self.assertTrue(gate["gates"]["proof_scan_universe_aligned"])
        self.assertFalse(gate["gates"]["enough_exact_shared_quote_dates"])
        self.assertEqual(gate["source_quality_status"], "usable_quotes_waiting_for_history_depth")
        self.assertIn("shared_quote_dates:1/100", gate["blockers"])
        self.assertIn("readiness:thin_required_history", gate["blockers"])
        self.assertIn("replay_error:Selected dates: 1.", gate["blockers"])
        self.assertIn("live_scan_candidates:0", gate["blockers"])

    def test_build_verified_profitability_gate_passes_when_all_evidence_is_positive(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "source_quality_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {"candidate_count": 1, "candidate_symbols": ["FCX"]},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                    "candidate_symbols": ["FCX"],
                    "candidate_symbols_outside_exact_proof": [],
                    "live_scan_candidates_all_inside_exact_proof": True,
                },
            }
        )

        self.assertTrue(gate["verified"])
        self.assertEqual(gate["status"], "verified_profitable")
        self.assertEqual(gate["blockers"], [])

    def test_build_verified_profitability_gate_uses_proof_eligible_candidates(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "source_quality_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {
                    "candidate_count": 1,
                    "candidate_symbols": ["FCX"],
                    "raw_candidate_count": 1,
                    "proof_eligible_candidate_count": 0,
                    "proof_eligible_candidate_symbols": [],
                },
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                    "candidate_symbols": ["FCX"],
                    "proof_eligible_candidate_count": 0,
                    "proof_eligible_candidate_symbols": [],
                    "candidate_symbols_outside_exact_proof": [],
                    "live_scan_candidates_all_inside_exact_proof": False,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["live_scan_has_candidate"])
        self.assertEqual(gate["live_scan_candidate_count"], 0)
        self.assertEqual(gate["raw_live_scan_candidate_count"], 1)
        self.assertIn("live_scan_candidates:0", gate["blockers"])

    def test_build_verified_profitability_gate_rejects_live_candidate_outside_exact_proof_universe(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "source_quality_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {"candidate_count": 1, "candidate_symbols": ["ALB"]},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_exceeds_exact_proof_universe",
                    "proof_universe_count": 23,
                    "scan_universe_count": 24,
                    "candidate_symbols": ["ALB"],
                    "candidate_symbols_outside_exact_proof": ["ALB"],
                    "live_scan_candidates_all_inside_exact_proof": False,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["live_scan_candidate_inside_exact_proof_universe"])
        self.assertIn("live_scan_candidate_outside_exact_proof_universe:['ALB']", gate["blockers"])

    def test_build_verified_profitability_gate_rejects_missing_scan_proof_alignment(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "source_quality_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {"candidate_count": 1, "candidate_symbols": ["FCX"]},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["live_scan_candidate_inside_exact_proof_universe"])
        self.assertIn(
            "live_scan_candidate_inside_exact_proof_universe_missing_scan_proof_universe_alignment",
            gate["blockers"],
        )

    def test_build_verified_profitability_gate_rejects_core_only_capture_scope(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "source_quality_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {"candidate_count": 1, "candidate_symbols": ["FCX"]},
                "capture": {
                    "scope": "custom_symbols",
                    "symbol_count": 9,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                    "candidate_symbols": ["FCX"],
                    "candidate_symbols_outside_exact_proof": [],
                    "live_scan_candidates_all_inside_exact_proof": True,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["capture_scope_full_scan_universe"])
        self.assertIn("capture_scope_not_full_scan_universe:custom_symbols:9/24", gate["blockers"])

    def test_build_verified_profitability_gate_blocks_bad_source_quality(self):
        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "automation_health": {"healthy": True},
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "source_quality": {"status": "missing_required_underlyings"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {
                    "error": None,
                    "total_trades": 12,
                    "profit_factor": 1.25,
                    "total_return_pct": 8.4,
                },
                "scan": {"candidate_count": 1, "candidate_symbols": ["FCX"]},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "symbol_count": 24,
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "proof_universe_count": 24,
                    "scan_universe_count": 24,
                    "candidate_symbols": ["FCX"],
                    "candidate_symbols_outside_exact_proof": [],
                    "live_scan_candidates_all_inside_exact_proof": True,
                },
            }
        )

        self.assertFalse(gate["verified"])
        self.assertFalse(gate["gates"]["alpaca_opra_source_quality_usable"])
        self.assertIn("source_quality:missing_required_underlyings", gate["blockers"])

    def test_build_lane_next_step_prioritizes_capture_wait_before_tuning(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "diagnostic_ready": False,
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "next_scheduled_capture": {"scheduled_utc": "2026-05-21T20:20:00Z"},
            },
            "verification_gate": {
                "verified": False,
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_automation_healthy": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "alpaca_opra_source_quality_usable": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "live_scan_has_candidate": False,
                },
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 1.", "total_trades": 0},
            "diagnostic_replay": {
                "blockers": ["diagnostic_replay_days:0"],
                "next_action": "accumulate_replay_simulation_shared_opra_dates",
            },
            "scan": {"candidate_count": 0},
        }

        summary = build_lane_next_step_summary(report)

        self.assertEqual(summary["phase"], "capture_wait")
        self.assertEqual(summary["priority_action"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertEqual(summary["primary_blocker"], "shared_quote_dates:1/100")
        self.assertEqual(summary["next_scheduled_capture_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(
            summary["diagnostic_replay_next_action"],
            "accumulate_replay_simulation_shared_opra_dates",
        )
        self.assertFalse(summary["diagnostic_ready"])
        self.assertFalse(summary["safe_to_tune_filters"])
        self.assertIn("enough_exact_shared_quote_dates", summary["blocked_gates"])
        self.assertTrue(any("Production filters" in item for item in summary["rationale"]))

    def test_build_lane_next_step_plan_waits_for_guarded_capture_and_records_branches(self):
        plan = build_lane_next_step_plan(
            {
                "provider": "alpaca:sip:opra",
                "verification_gate": {
                    "status": "not_verified",
                    "verified": False,
                    "gates": {
                        "capture_scope_full_scan_universe": True,
                        "proof_scan_universe_aligned": True,
                    },
                },
                "proof_source_audit": {"proof_source_label": "alpaca_opra_daily_snapshot"},
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "automation_health": {"healthy": True},
                "capture": {"target_capture_complete": True},
                "proof_window": {
                    "source_label": "alpaca_opra_daily_snapshot",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "remaining_shared_quote_dates": 99,
                    "next_missing_capture_trade_date": "2026-05-21",
                },
                "lane_next_step": {
                    "phase": "capture_wait",
                    "priority_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                    "safe_to_tune_filters": False,
                },
                "next_execution_contract": {
                    "selected_step": "post_close_full_universe_capture",
                    "command_display": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "blockers": ["waiting_until_not_before:2026-05-21T20:20:00Z"],
                    "success_criteria": [
                        "capture_target_complete_true",
                        "shared_quote_dates_increase_or_target_was_already_complete",
                    ],
                },
                "next_execution_runbook_card": {
                    "guard_status": "clock_guard_active",
                    "selected_step": "post_close_full_universe_capture",
                    "recommended_action": "wait_until_not_before",
                    "run_next_execution_command": False,
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "success_criteria": [
                        "capture_target_complete_true",
                        "shared_quote_dates_increase_or_target_was_already_complete",
                    ],
                    "blockers": ["waiting_until_not_before:2026-05-21T20:20:00Z"],
                },
                "goal_completion_evidence_plan": {
                    "next_requirement_to_unblock": "has_required_exact_alpaca_opra_history_depth",
                    "missing_evidence": [
                        "has_required_exact_alpaca_opra_history_depth",
                        "exact_replay_is_profitable",
                    ],
                    "earliest_evidence_opportunity": {
                        "source": "auxiliary_evidence_opportunity",
                        "target_goal_requirement": "live_scan_has_verifiable_candidate",
                        "next_action": "run_read_only_fresh_opra_scan_to_record_raw_drop_reasons_or_live_candidate",
                        "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                        "command_role": "fresh_live_candidate_scan_evidence",
                        "not_before_utc": "2026-05-21T14:10:00Z",
                        "not_before_user_local": "2026-05-21T08:10:00-06:00",
                        "window_end_user_local": "2026-05-21T14:00:00-06:00",
                        "precedes_primary_next_evidence": True,
                        "minutes_before_primary_next_evidence": 370.0,
                        "material_progress_if": [
                            "scan.scan_drop_reason_audit_status becomes raw_drop_reasons_recorded",
                            "scan.scan_drop_reason_count > 0",
                        ],
                        "blockers": [
                            "scan_drop_reason_audit_status_not_raw_drop_reasons_recorded",
                        ],
                    },
                },
                "next_proof_event_checkpoint": {
                    "selected_step": "post_close_full_universe_capture",
                    "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                },
                "exact_capture_post_run_evaluation": {
                    "next_capture_trade_date": "2026-05-21",
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "post_capture_evidence_refresh_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
                    "post_capture_replay_command_when_unlocked": "python scripts/run_ai_commodity_opra_progress.py",
                    "post_capture_profitability_gate_fields": [
                        "exact_replay_unlock_contract.full_exact_replay_unlocked",
                    ],
                    "post_capture_profitability_handoff": [
                        {
                            "step": "readback_next_execution_after_capture",
                            "command": "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
                        },
                    ],
                    "failure_signals_after_next_capture": [
                        "shared_quote_dates_count_did_not_increment_after_new_target_capture",
                        "capture_target_complete_false",
                    ],
                },
                "exact_history_acquisition_plan": {
                    "exact_history_acceleration_status": "forward_daily_snapshot_capture_required",
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                        "missed_capture_dates_recoverable": None,
                        "next_action": "continue_guarded_forward_capture_queue",
                    },
                },
                "exact_history_backfill_capability_audit": {
                    "status": "forward_capture_required_for_exact_bid_ask_history",
                    "can_accelerate_exact_history": False,
                    "missing_capability": "historical_option_quote_bbo_method_for_contracts",
                    "snapshot_updated_since_is_backfill_capability": False,
                    "acceleration_blockers": [
                        "no_historical_option_quote_bbo_endpoint",
                        "option_snapshots_are_latest_state_not_as_of_date_history",
                    ],
                },
                "fresh_scan_post_run_evaluation": {
                    "status": "fresh_scan_zero_candidates_after_fresh_quotes",
                    "zero_candidate_structural_review": {
                        "status": "ready_after_fresh_quotes_zero_candidates",
                        "dominant_drop_key": "tech_score",
                    },
                },
            }
        )

        self.assertEqual(plan["status"], "waiting_for_not_before")
        self.assertEqual(plan["immediate_action"], "wait_until_not_before_then_rerun_next_execution_guard")
        self.assertEqual(plan["selected_step"], "post_close_full_universe_capture")
        self.assertEqual(plan["target_goal_requirement"], "has_required_exact_alpaca_opra_history_depth")
        self.assertEqual(
            plan["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(plan["not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertFalse(plan["run_next_execution_command"])
        self.assertEqual(plan["earliest_guarded_evidence_source"], "auxiliary_evidence_opportunity")
        self.assertEqual(
            plan["earliest_guarded_evidence_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(
            plan["earliest_guarded_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            plan["earliest_guarded_evidence_not_before_user_local"],
            "2026-05-21T08:10:00-06:00",
        )
        self.assertEqual(
            plan["earliest_guarded_evidence_window_end_user_local"],
            "2026-05-21T14:00:00-06:00",
        )
        self.assertTrue(plan["earliest_guarded_evidence_precedes_primary_next_evidence"])
        self.assertEqual(plan["earliest_guarded_evidence_minutes_before_primary_next_evidence"], 370.0)
        self.assertEqual(
            plan["earliest_guarded_evidence_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertIn(
            "scan.scan_drop_reason_count > 0",
            plan["earliest_guarded_evidence_material_progress_if"],
        )
        self.assertIn("provider == alpaca:sip:opra", plan["pre_run_checks"])
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            plan["pre_run_checks"],
        )
        self.assertIn("proof_source_isolation_contract.blockers empty", plan["pre_run_checks"])
        self.assertIn("target_date_capturable_guard preserved", plan["pre_run_checks"])
        self.assertIn("command target date == 2026-05-21", plan["pre_run_checks"])
        self.assertIn("verification_gate.gates.capture_scope_full_scan_universe true", plan["pre_run_checks"])
        self.assertIn("proof_window.current_shared_quote_dates == 2", plan["after_run_checks"])
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            plan["after_run_checks"],
        )
        self.assertIn("proof_source_isolation_contract.blockers empty", plan["after_run_checks"])
        self.assertIn("capture.missing_target_date_symbols_after empty", plan["after_run_checks"])
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_trade_dates empty",
            plan["after_run_checks"],
        )
        self.assertIn("proof_window.current_shared_quote_dates", plan["evidence_to_record_after_run"])
        self.assertIn("proof_source_isolation_contract.status", plan["evidence_to_record_after_run"])
        self.assertIn("proof_source_isolation_contract.blockers", plan["evidence_to_record_after_run"])
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.status",
            plan["evidence_to_record_after_run"],
        )
        self.assertIn(
            "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_policy",
            plan["evidence_to_record_after_run"],
        )
        self.assertIn("exact_capture_post_run_evaluation.blockers", plan["evidence_to_record_after_run"])
        self.assertIn(
            "exact_capture_post_run_evaluation.post_capture_profitability_handoff",
            plan["evidence_to_record_after_run"],
        )
        self.assertIn("exact_replay_unlock_contract.status", plan["evidence_to_record_after_run"])
        self.assertEqual(
            plan["post_run_readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertEqual(
            plan["post_run_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(
            plan["post_run_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertIn(
            "exact_replay_unlock_contract.full_exact_replay_unlocked",
            plan["post_run_profitability_gate_fields"],
        )
        self.assertEqual(
            plan["post_run_profitability_handoff"][0]["step"],
            "readback_next_execution_after_capture",
        )
        self.assertEqual(
            plan["failure_signals_to_watch"],
            [
                "shared_quote_dates_count_did_not_increment_after_new_target_capture",
                "capture_target_complete_false",
                (
                    "exact_history_acquisition_plan.capture_continuity_contract.status "
                    "== intervention_required_missed_capture_dates"
                ),
                "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_trade_dates nonempty",
                "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_policy missing_or_changed",
                "exact_history_acquisition_plan.capture_continuity_contract.missed_capture_dates_recoverable true",
            ],
        )
        self.assertEqual(plan["success_branch"], "if_shared_dates_increment_then_continue_daily_capture_runway")
        self.assertEqual(plan["failure_branch"], "repair_capture_import_or_target_date_coverage_before_replay")
        self.assertEqual(plan["history_acceleration_status"], "forward_daily_snapshot_capture_required")
        self.assertEqual(
            plan["history_backfill_capability_status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        self.assertFalse(plan["history_backfill_can_accelerate"])
        self.assertEqual(
            plan["history_backfill_missing_capability"],
            "historical_option_quote_bbo_method_for_contracts",
        )
        self.assertIn("no_historical_option_quote_bbo_endpoint", plan["history_backfill_blockers"])
        self.assertFalse(plan["snapshot_updated_since_is_backfill_capability"])
        self.assertEqual(plan["expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(plan["next_capture_trade_date"], "2026-05-21")
        self.assertEqual(plan["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertEqual(plan["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(plan["capture_continuity_status"], "on_track_no_missed_capture_dates")
        self.assertEqual(plan["capture_continuity_missed_capture_trade_dates"], [])
        self.assertEqual(
            plan["capture_continuity_missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertEqual(plan["proof_source_isolation_blockers"], [])
        self.assertTrue(plan["capture_scope_full_scan_universe"])
        self.assertTrue(plan["proof_scan_universe_aligned"])
        self.assertTrue(plan["capture_target_complete"])
        self.assertTrue(plan["automation_healthy"])
        self.assertEqual(plan["zero_candidate_review_status"], "ready_after_fresh_quotes_zero_candidates")
        self.assertEqual(plan["zero_candidate_dominant_drop_key"], "tech_score")
        self.assertEqual(
            plan["filter_policy"],
            "locked_until_exact_alpaca_opra_replay_profitability_gate_can_measure_changes",
        )
        self.assertFalse(plan["safe_to_tune_filters"])
        self.assertIn("waiting_until_not_before:2026-05-21T20:20:00Z", plan["blockers"])
        self.assertIn("exact_replay_is_profitable", plan["blockers"])

    def test_build_guarded_capture_runbook_packet_keeps_capture_guard_and_evidence_together(self):
        packet = build_guarded_capture_runbook_packet(
            {
                "provider": "alpaca:sip:opra",
                "verification_gate": {"verified": False},
                "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
                "next_execution_contract": {
                    "selected_step": "post_close_full_universe_capture",
                    "command": [
                        "python",
                        "scripts/run_ai_commodity_opra_progress.py",
                        "--force-capture",
                        "--target-date",
                        "2026-05-21",
                    ],
                    "command_display": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_utc": "2026-05-21T20:20:00Z",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "blockers": ["waiting_until_not_before:2026-05-21T20:20:00Z"],
                },
                "next_execution_runbook_card": {
                    "guard_status": "clock_guard_active",
                    "selected_step": "post_close_full_universe_capture",
                    "run_next_execution_command": False,
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "blockers": ["waiting_until_not_before:2026-05-21T20:20:00Z"],
                },
                "next_execution_preflight": {
                    "status": "ready_after_clock",
                    "failed_checks": [],
                    "non_clock_blockers": [],
                },
                "lane_next_step_plan": {
                    "selected_step": "post_close_full_universe_capture",
                    "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "command_cwd": str(ROOT),
                    "not_before_user_local": "2026-05-21T14:20:00-06:00",
                    "run_next_execution_command": False,
                    "guard_status": "clock_guard_active",
                    "pre_run_checks": [
                        "provider == alpaca:sip:opra",
                        "target_date_capturable_guard preserved",
                    ],
                    "after_run_checks": ["capture.target_capture_complete true"],
                    "evidence_to_record_after_run": ["proof_window.current_shared_quote_dates"],
                    "failure_signals_to_watch": ["capture_target_complete_false"],
                    "post_run_readback_command": "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
                    "post_run_evidence_refresh_command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
                    "post_run_replay_command_when_unlocked": "python scripts/run_ai_commodity_opra_progress.py",
                    "post_run_profitability_gate_fields": [
                        "exact_replay_unlock_contract.full_exact_replay_unlocked",
                    ],
                    "success_branch": "if_shared_dates_increment_then_continue_daily_capture_runway",
                    "failure_branch": "repair_capture_import_or_target_date_coverage_before_replay",
                    "blockers": [
                        "waiting_until_not_before:2026-05-21T20:20:00Z",
                        "exact_replay_is_profitable",
                    ],
                },
                "exact_capture_progress_contract": {
                    "status": "awaiting_guarded_capture_to_advance_history",
                    "target_trade_date": "2026-05-21",
                    "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                    "current_shared_quote_dates": 1,
                    "required_shared_quote_dates": 100,
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "remaining_shared_quote_dates_after_success": 98,
                    "material_progress_if": ["proof_window.current_shared_quote_dates == 2"],
                    "fields_to_compare_after_run": ["proof_source_isolation_contract.status"],
                    "failure_signals_after_run": ["proof_window.current_shared_quote_dates < 2"],
                    "blockers": [],
                },
                "exact_capture_post_run_evaluation": {
                    "next_capture_trade_date": "2026-05-21",
                    "expected_shared_quote_dates_after_next_capture": 2,
                    "next_capture_evidence_state": "next_capture_target_waiting_until_not_before",
                    "next_capture_target_observed": False,
                    "next_capture_pending_reason": "waiting_until_not_before:2026-05-21T14:20:00-06:00",
                    "latest_capture_evidence_status": "waiting_for_guarded_capture_run",
                    "stale_success_guard_for_next_target": False,
                    "post_capture_evidence_contract": {
                        "status": "waiting_for_guarded_capture_run",
                        "target_goal_requirement": "has_required_exact_alpaca_opra_history_depth",
                        "required_before_run": [
                            "next_execution_runbook_card.run_next_execution_command true",
                        ],
                        "fields_to_compare_after_run": ["capture.missing_target_date_symbols_after"],
                        "material_progress_if": ["capture.target_capture_complete true"],
                        "failure_signals_after_run": ["capture.target_capture_complete false"],
                        "post_run_commands": [
                            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
                            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
                            "python scripts/run_ai_commodity_opra_progress.py",
                        ],
                    },
                },
                "exact_history_acquisition_plan": {
                    "capture_continuity_contract": {
                        "status": "on_track_no_missed_capture_dates",
                        "missed_capture_trade_dates": [],
                        "missed_capture_policy": (
                            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                        ),
                    }
                },
            }
        )

        self.assertEqual(packet["status"], "waiting_until_not_before")
        self.assertEqual(packet["next_action"], "wait_until_not_before_then_rerun_next_execution_guard")
        self.assertEqual(
            packet["run_guard"],
            "execute_only_when_next_execution_probe_returns_run_next_execution_command_true",
        )
        self.assertFalse(packet["run_next_execution_command"])
        self.assertEqual(
            packet["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(packet["target_trade_date"], "2026-05-21")
        self.assertEqual(packet["not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertIn("next_execution_runbook_card.run_next_execution_command true", packet["pre_run_checks"])
        self.assertIn("proof_source_isolation_contract.status", packet["after_run_checks"])
        self.assertIn("capture.target_capture_complete true", packet["material_progress_if"])
        self.assertIn("proof_window.current_shared_quote_dates < 2", packet["failure_signals_after_run"])
        self.assertIn(
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
            packet["post_run_commands"],
        )
        self.assertEqual(packet["next_capture_evidence_state"], "next_capture_target_waiting_until_not_before")
        self.assertFalse(packet["stale_success_guard_for_next_target"])
        self.assertIn("exact_replay_is_profitable", packet["blocked_by"])
        self.assertEqual(packet["capture_continuity_status"], "on_track_no_missed_capture_dates")

    def test_build_lane_next_step_repairs_full_universe_alignment_before_waiting(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "diagnostic_ready": False,
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
            },
            "verification_gate": {
                "verified": False,
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_automation_healthy": True,
                    "capture_scope_full_scan_universe": False,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "alpaca_opra_source_quality_usable": True,
                    "enough_exact_shared_quote_dates": False,
                },
                "blockers": [
                    "capture_scope_not_full_scan_universe:custom_symbols:9/24",
                    "shared_quote_dates:1/100",
                ],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 1.", "total_trades": 0},
            "diagnostic_replay": {"next_action": "accumulate_replay_simulation_shared_opra_dates"},
            "scan": {"candidate_count": 0},
        }

        summary = build_lane_next_step_summary(report)

        self.assertEqual(summary["phase"], "proof_universe_alignment")
        self.assertEqual(summary["priority_action"], "repair_full_scan_universe_capture_and_proof_alignment")
        self.assertEqual(
            summary["primary_blocker"],
            "capture_scope_not_full_scan_universe:custom_symbols:9/24",
        )
        self.assertFalse(summary["safe_to_tune_filters"])
        self.assertTrue(any("Full-universe capture/proof alignment" in item for item in summary["rationale"]))

    def test_build_lane_next_step_orders_fresh_scan_before_later_capture(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "diagnostic_ready": False,
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "next_scheduled_capture": {
                    "scheduled_local": "2026-05-21T14:20:00-06:00",
                    "scheduled_utc": "2026-05-21T20:20:00Z",
                    "hours_until_scheduled": 15.0,
                },
            },
            "verification_gate": {
                "verified": False,
                "gates": {"enough_exact_shared_quote_dates": False},
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 1.", "total_trades": 0},
            "diagnostic_replay": {"next_action": "accumulate_replay_simulation_shared_opra_dates"},
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {
                    "status": "stale_quote_sensitive",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                    "next_fresh_scan": {
                        "scheduled_local": "2026-05-21T10:10:00-04:00",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "hours_until_scheduled": 9.0,
                        "scan_calendar": "us_equity_market_days",
                        "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                        "scheduled_trade_date_is_market_day": True,
                    },
                },
            },
        }

        summary = build_lane_next_step_summary(report)

        self.assertEqual(summary["phase"], "fresh_scan_wait")
        self.assertEqual(
            summary["priority_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertEqual(summary["primary_blocker"], "shared_quote_dates:1/100")
        self.assertEqual(summary["next_timed_event_kind"], "fresh_opra_scan")
        self.assertEqual(summary["next_timed_event_calendar"], "us_equity_market_days")
        self.assertTrue(summary["next_timed_event_trade_date_is_market_day"])
        self.assertEqual(
            summary["next_timed_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertEqual(summary["next_timed_event_utc"], "2026-05-21T14:10:00Z")
        self.assertTrue(any("fresh OPRA scan window" in item for item in summary["rationale"]))

    def test_build_lane_iteration_plan_orders_scan_capture_replay_and_locks_tuning(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "diagnostic_required_shared_quote_dates": 88,
                "next_missing_capture_trade_date": "2026-05-21",
            },
            "capture": {"scope": "ai_commodity_scan_universe", "symbol_count": 24},
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "next_scheduled_capture": {
                    "scheduled_local": "2026-05-21T14:20:00-06:00",
                    "scheduled_utc": "2026-05-21T20:20:00Z",
                    "timing_status": "scheduled_future",
                },
            },
            "verification_gate": {
                "verified": False,
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "live_scan_has_candidate": False,
                },
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 1.", "total_trades": 0},
            "diagnostic_replay": {"next_action": "accumulate_replay_simulation_shared_opra_dates"},
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {
                    "status": "stale_quote_blocked",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                    "next_fresh_scan": {
                        "scheduled_local": "2026-05-21T10:10:00-04:00",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "status": "fresh_scan_future",
                        "can_attempt_scan_now": False,
                        "scan_calendar": "us_equity_market_days",
                        "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                        "scheduled_trade_date_is_market_day": True,
                    },
                },
                "fresh_scan_retest_plan": {
                    "primary_probe_symbol": "FCX",
                    "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                },
            },
        }
        report["lane_next_step"] = build_lane_next_step_summary(report)

        plan = build_lane_iteration_plan(report)

        self.assertEqual(plan["status"], "active")
        self.assertEqual(
            plan["priority_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertFalse(plan["safe_to_tune_filters"])
        steps = plan["steps"]
        self.assertEqual(
            [step["step"] for step in steps],
            [
                "fresh_opra_live_scan",
                "post_close_full_universe_capture",
                "diagnostic_replay_checkpoint",
                "full_exact_replay_profitability_gate",
                "filter_tuning",
            ],
        )
        self.assertEqual(steps[0]["status"], "scheduled")
        self.assertEqual(steps[0]["scheduled_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(steps[0]["scan_calendar"], "us_equity_market_days")
        self.assertTrue(steps[0]["scheduled_trade_date_is_market_day"])
        self.assertEqual(steps[0]["primary_probe_symbol"], "FCX")
        self.assertFalse(steps[0]["actionable_now"])
        self.assertEqual(steps[0]["not_before_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(steps[0]["command"], ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"])
        self.assertTrue(steps[0]["command_cwd"].endswith("options-chatbot"))
        self.assertEqual(steps[1]["status"], "scheduled")
        self.assertEqual(steps[1]["target_trade_date"], "2026-05-21")
        self.assertEqual(steps[1]["expected_symbol_count"], 24)
        self.assertTrue(steps[1]["counts_for_exact_replay_history"])
        self.assertFalse(steps[1]["actionable_now"])
        self.assertEqual(steps[1]["not_before_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(steps[1]["premature_run_guard"], "target_date_capturable_guard")
        self.assertEqual(
            steps[1]["command"],
            [
                "python",
                "scripts/run_ai_commodity_opra_progress.py",
                "--force-capture",
                "--target-date",
                "2026-05-21",
            ],
        )
        self.assertEqual(steps[2]["status"], "blocked_until_shared_quote_dates")
        self.assertEqual(steps[2]["remaining_shared_quote_dates"], 87)
        self.assertFalse(steps[2]["actionable_now"])
        self.assertEqual(steps[2]["command"], ["python", "scripts/run_ai_commodity_opra_progress.py"])
        self.assertEqual(steps[3]["remaining_shared_quote_dates"], 99)
        self.assertFalse(steps[3]["actionable_now"])
        self.assertEqual(steps[3]["command"], ["python", "scripts/run_ai_commodity_opra_progress.py"])
        self.assertEqual(steps[4]["status"], "locked")
        self.assertFalse(steps[4]["actionable_now"])
        self.assertIn("enough_exact_shared_quote_dates", steps[4]["locked_by"])
        self.assertNotIn("command", steps[4])

    def test_build_next_execution_contract_selects_next_timed_plan_step(self):
        report = {
            "generated_at": "2026-05-21T07:20:30Z",
            "automation_health": {"healthy": True},
            "lane_next_step": {
                "next_timed_event": {
                    "kind": "fresh_opra_scan",
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                }
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "fresh_opra_live_scan",
                        "status": "scheduled",
                        "action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T14:10:00Z",
                        "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                        "command_cwd": str(ROOT),
                        "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                    },
                    {
                        "step": "post_close_full_universe_capture",
                        "status": "scheduled",
                        "scheduled_utc": "2026-05-21T20:20:00Z",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-21",
                        ],
                    },
                ]
            },
        }

        contract = build_next_execution_contract(report)

        self.assertEqual(contract["status"], "waiting_until_not_before")
        self.assertEqual(contract["selected_step"], "fresh_opra_live_scan")
        self.assertTrue(contract["automation_healthy"])
        self.assertTrue(contract["matches_next_timed_event"])
        self.assertFalse(contract["actionable_now"])
        self.assertEqual(contract["not_before_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(contract["not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(contract["window_end_utc"], "2026-05-21T20:00:00Z")
        self.assertEqual(contract["window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(contract["runbook_timezone"], "America/Denver")
        self.assertEqual(
            contract["command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertEqual(
            contract["command_display"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(contract["blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])

    def test_build_next_execution_preflight_ready_after_clock_when_only_waiting(self):
        report = {
            "generated_at": "2026-05-21T13:24:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "lane_next_step": {
                "next_timed_event": {
                    "kind": "fresh_opra_scan",
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                }
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "fresh_opra_live_scan",
                        "status": "scheduled",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T14:10:00Z",
                        "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                        "command_cwd": str(ROOT),
                    }
                ]
            },
        }
        contract = build_next_execution_contract(report)

        preflight = build_next_execution_preflight(
            {**report, "next_execution_contract": contract},
            reference_now=datetime(2026, 5, 21, 13, 24, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "ready_after_clock")
        self.assertTrue(preflight["clock_only_blocked"])
        self.assertEqual(preflight["failed_checks"], [])
        self.assertEqual(preflight["non_clock_blockers"], [])
        self.assertEqual(preflight["next_action"], "wait_until_not_before_then_run_next_execution_command")
        self.assertEqual(
            preflight["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertTrue(preflight["proof_source_isolation_required"])
        self.assertEqual(preflight["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(preflight["proof_source_isolation_blockers"], [])

    def test_build_next_execution_preflight_blocks_non_alpaca_provider(self):
        report = {
            "generated_at": "2026-05-21T14:15:00Z",
            "provider": "yahoo_fallback_delayed",
            "alpaca_enabled": False,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "next_execution_contract": {
                "status": "ready_to_run",
                "selected_step": "fresh_opra_live_scan",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "command_cwd": str(ROOT),
                "blockers": [],
            },
        }

        preflight = build_next_execution_preflight(
            report,
            reference_now=datetime(2026, 5, 21, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "blocked")
        self.assertIn("provider_is_alpaca_sip_opra", preflight["failed_checks"])
        self.assertIn("alpaca_enabled", preflight["failed_checks"])

    def test_build_next_execution_preflight_blocks_proof_source_isolation(self):
        report = {
            "generated_at": "2026-05-21T14:15:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "proof_source_isolation_contract": {
                **self._clean_proof_source_isolation_contract(),
                "status": "proof_source_isolation_blocked",
                "blockers": ["non_proof_shared_dates_are_excluded"],
            },
            "next_execution_contract": {
                "status": "ready_to_run",
                "selected_step": "fresh_opra_live_scan",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "command_cwd": str(ROOT),
                "blockers": [],
            },
        }

        preflight = build_next_execution_preflight(
            report,
            reference_now=datetime(2026, 5, 21, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "blocked")
        self.assertTrue(preflight["proof_source_isolation_required"])
        self.assertEqual(preflight["proof_source_isolation_status"], "proof_source_isolation_blocked")
        self.assertEqual(preflight["proof_source_isolation_blockers"], ["non_proof_shared_dates_are_excluded"])
        self.assertIn("proof_source_isolation_contract_clean", preflight["failed_checks"])
        self.assertEqual(preflight["next_action"], "resolve_preflight_blockers_before_command")

    def test_build_next_execution_preflight_blocks_missed_capture_continuity(self):
        report = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "verification_gate": {
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "proof_scan_universe_aligned": True,
                }
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "missed_capture_trade_dates_since_latest_shared": ["2026-05-18"],
            },
            "exact_history_acquisition_plan": {
                "next_capture_trade_date": "2026-05-21",
                "capture_continuity_contract": {
                    "status": "intervention_required_missed_capture_dates",
                    "missed_capture_trade_dates": ["2026-05-18"],
                    "missed_capture_policy": (
                        "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                    ),
                    "missed_capture_dates_recoverable": False,
                },
            },
            "next_execution_contract": {
                "status": "ready_to_run",
                "selected_step": "post_close_full_universe_capture",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-21",
                ],
                "command_cwd": str(ROOT),
                "not_before_utc": "2026-05-21T20:20:00Z",
                "premature_run_guard": "target_date_capturable_guard",
                "blockers": [],
            },
        }

        preflight = build_next_execution_preflight(
            report,
            reference_now=datetime(2026, 5, 21, 20, 25, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "blocked")
        self.assertTrue(preflight["capture_continuity_required"])
        self.assertEqual(preflight["capture_continuity_status"], "intervention_required_missed_capture_dates")
        self.assertEqual(preflight["capture_continuity_missed_capture_trade_dates"], ["2026-05-18"])
        self.assertIn("capture_continuity_status_on_track_or_complete", preflight["failed_checks"])
        self.assertIn("capture_continuity_has_no_missed_dates", preflight["failed_checks"])
        self.assertEqual(preflight["next_action"], "resolve_preflight_blockers_before_command")

    def test_build_next_execution_preflight_blocks_full_universe_regression(self):
        report = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "verification_gate": {
                "gates": {
                    "capture_scope_full_scan_universe": False,
                    "proof_scan_universe_aligned": False,
                }
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "missed_capture_trade_dates_since_latest_shared": [],
            },
            "exact_history_acquisition_plan": {
                "next_capture_trade_date": "2026-05-21",
                "capture_continuity_contract": {
                    "status": "on_track_no_missed_capture_dates",
                    "missed_capture_trade_dates": [],
                    "missed_capture_policy": (
                        "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                    ),
                    "missed_capture_dates_recoverable": None,
                },
            },
            "next_execution_contract": {
                "status": "ready_to_run",
                "selected_step": "post_close_full_universe_capture",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-21",
                ],
                "command_cwd": str(ROOT),
                "not_before_utc": "2026-05-21T20:20:00Z",
                "premature_run_guard": "target_date_capturable_guard",
                "blockers": [],
            },
        }

        preflight = build_next_execution_preflight(
            report,
            reference_now=datetime(2026, 5, 21, 20, 25, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "blocked")
        self.assertTrue(preflight["full_universe_hard_gates_required"])
        self.assertFalse(preflight["capture_scope_full_scan_universe"])
        self.assertFalse(preflight["proof_scan_universe_aligned"])
        self.assertIn("capture_scope_full_scan_universe", preflight["failed_checks"])
        self.assertIn("proof_scan_universe_aligned", preflight["failed_checks"])
        self.assertEqual(preflight["next_action"], "resolve_preflight_blockers_before_command")

    def test_build_next_execution_preflight_blocks_capture_target_date_mismatch(self):
        report = {
            "generated_at": "2026-05-21T20:25:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "proof_source_label": "alpaca_opra_daily_snapshot",
            "automation_health": {"healthy": True},
            "proof_source_isolation_contract": self._clean_proof_source_isolation_contract(),
            "verification_gate": {
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "proof_scan_universe_aligned": True,
                }
            },
            "proof_window": {
                "source_label": "alpaca_opra_daily_snapshot",
                "missed_capture_trade_dates_since_latest_shared": [],
            },
            "exact_history_acquisition_plan": {
                "next_capture_trade_date": "2026-05-21",
                "capture_continuity_contract": {
                    "status": "on_track_no_missed_capture_dates",
                    "missed_capture_trade_dates": [],
                    "missed_capture_policy": (
                        "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots"
                    ),
                    "missed_capture_dates_recoverable": None,
                },
            },
            "next_execution_contract": {
                "status": "ready_to_run",
                "selected_step": "post_close_full_universe_capture",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-20",
                ],
                "command_cwd": str(ROOT),
                "not_before_utc": "2026-05-21T20:20:00Z",
                "premature_run_guard": "target_date_capturable_guard",
                "blockers": [],
            },
        }

        preflight = build_next_execution_preflight(
            report,
            reference_now=datetime(2026, 5, 21, 20, 25, tzinfo=UTC),
        )

        self.assertEqual(preflight["status"], "blocked")
        self.assertTrue(preflight["capture_command_contract_required"])
        self.assertEqual(preflight["target_date_capturable_guard"], "target_date_capturable_guard")
        self.assertTrue(preflight["capture_command_uses_force_capture"])
        self.assertEqual(preflight["capture_command_target_date"], "2026-05-20")
        self.assertEqual(preflight["expected_capture_target_date"], "2026-05-21")
        self.assertIn("capture_command_target_date_matches_next_capture", preflight["failed_checks"])
        self.assertEqual(preflight["next_action"], "resolve_preflight_blockers_before_command")

    def test_build_next_execution_contract_blocks_event_plan_mismatch(self):
        report = {
            "generated_at": "2026-05-21T14:15:00Z",
            "automation_health": {"healthy": True},
            "lane_next_step": {
                "next_timed_event": {
                    "kind": "fresh_opra_scan",
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                }
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "post_close_full_universe_capture",
                        "status": "scheduled",
                        "scheduled_utc": "2026-05-21T20:20:00Z",
                        "actionable_now": False,
                    }
                ]
            },
        }

        contract = build_next_execution_contract(report)

        self.assertEqual(contract["status"], "blocked")
        self.assertEqual(contract["selected_step"], "post_close_full_universe_capture")
        self.assertFalse(contract["matches_next_timed_event"])
        self.assertIn(
            "step_event_mismatch:post_close_full_universe_capture:2026-05-21T20:20:00Z:2026-05-21T14:10:00Z",
            contract["blockers"],
        )

    def test_build_next_execution_cli_payload_keeps_command_contract_and_blockers_together(self):
        report = {
            "generated_at": "2026-05-21T07:30:00Z",
            "provider": "alpaca:sip:opra",
            "next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
            "progress_history_summary": {
                "status": "summarized",
                "entry_count_including_current": 4,
                "latest_history_written_at": "2026-05-21T10:45:00Z",
                "latest_next_blocker": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "same_next_blocker_streak": 4,
                "shared_quote_dates_delta_from_previous_entry": 0,
                "remaining_quote_dates_delta_from_previous_entry": 0,
            },
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:1/100", "live_scan_candidates:0"],
            },
            "lane_next_step": {
                "phase": "fresh_scan_wait",
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
                "next_timed_event_calendar": "us_equity_market_days",
                "next_timed_event_holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                "next_timed_event_trade_date_is_market_day": True,
            },
            "automation_health": {
                "healthy": True,
                "prompt_mentions_lane_next_step_plan": True,
                "prompt_mentions_next_execution_runbook_card": True,
                "prompt_mentions_run_next_execution_command_guard": True,
                "prompt_mentions_proof_source_isolation_contract": True,
                "prompt_mentions_capture_continuity_contract": True,
                "scheduled_intraday_times": ["08:10:00", "14:20:00"],
            },
            "derived_refresh": {
                "status": "derived_fields_refreshed_from_latest_without_market_data",
                "refreshed_at_utc": "2026-05-21T10:45:00Z",
                "market_data_commands_run": False,
                "automation_health_refreshed": True,
                "historical_store_refreshed": True,
                "historical_store_refresh_error": None,
                "historical_store_shared_quote_dates_before": 1,
                "historical_store_shared_quote_dates_after": 1,
                "historical_store_shared_quote_dates_changed": False,
                "preserved_evidence_stale_after_historical_store_refresh": False,
                "preserved_evidence_stale_fields": [],
                "preserved_evidence_refresh_command": None,
                "preserved_evidence_refresh_reason": None,
                "next_blocker_before": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "raw_next_blocker_after": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "next_blocker_after": "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
                "next_blocker_changed": False,
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "last_execution_review": {
                "status": "not_due_yet",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "goal_completion_audit": {
                "status": "not_complete",
                "complete": False,
                "failed_requirements": [
                    "has_required_exact_alpaca_opra_history_depth",
                    "live_scan_has_verifiable_candidate",
                ],
                "may_mark_goal_complete": False,
                "next_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "fresh_scan_iteration_decision": {
                "status": "waiting_for_fresh_opra_scan",
                "branch": "clock_guard_branch",
                "next_action": "run_fresh_opra_scan_at_not_before_time",
                "safe_to_tune_filters": False,
                "top_drop_counts": [{"drop_key": "option_liquidity", "count": 9}],
                "zero_candidate_diagnostic_plan": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["FCX"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "post_run_playbook": [
                    {
                        "condition": "fresh_scan_candidate_count_above_zero",
                        "next_action": "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
                    },
                    {
                        "condition": "quote_freshness_cleared_and_candidates_still_zero",
                        "diagnostic_drop_keys": ["option_liquidity"],
                    },
                ],
                "post_run_playbook_status": "pending_fresh_scan_execution",
                "selected_post_run_condition": None,
                "selected_post_run_next_action": None,
            },
            "iteration_ledger": {
                "status": "unchanged_waiting_for_fresh_opra_scan",
                "improvements": ["proof_source_isolation_contract_clean"],
                "regressions": [],
                "non_material_flags": ["scan_liquidity_gate_distance_delta_below_materiality"],
                "active_blockers": ["has_required_exact_alpaca_opra_history_depth"],
                "shared_quote_dates": {
                    "current": 1,
                    "required": 100,
                    "remaining": 99,
                    "diagnostic_required": 88,
                    "diagnostic_remaining": 87,
                },
                "capture_runway": {
                    "next_missing_capture_trade_date": "2026-05-21",
                    "approx_diagnostic_ready_date": "2026-09-18",
                    "approx_exact_replay_ready_date": "2026-10-06",
                },
                "unlock_conditions": {
                    "diagnostic_replay": {
                        "status": "blocked_until_shared_quote_dates",
                        "remaining_shared_quote_dates": 87,
                    },
                    "full_exact_replay": {
                        "status": "blocked_until_shared_quote_dates",
                        "remaining_shared_quote_dates": 99,
                    },
                    "filter_tuning": {"status": "locked_until_exact_replay_is_ready"},
                },
            },
            "proof_window": {
                "current_shared_quote_dates": 1,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 99,
                "current_target_trade_date": "2026-05-21",
                "current_target_captured": False,
                "next_missing_capture_trade_date": "2026-05-21",
                "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-18",
                "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
                "capture_calendar": "us_equity_market_days",
                "approx_market_days_to_target": 99,
                "approx_diagnostic_ready_date_if_one_capture_per_market_day": "2026-09-24",
                "approx_completion_date_if_one_capture_per_market_day": "2026-10-12",
            },
            "proof_source_audit": {
                "trusted_only": True,
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "proof_source_required_symbol_coverage": {
                    "trusted_only": True,
                    "required_symbol_count": 24,
                    "available_required_symbol_count": 24,
                    "missing_required_symbols": [],
                },
                "all_required_symbols_have_proof_source_data": True,
                "all_trusted_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "excluded_trusted_shared_quote_dates": {"count": 0, "first": None, "last": None},
                "excluded_trusted_source_labels": [],
                "alpaca_like_source_labels_seen": ["alpaca_opra_daily_snapshot"],
                "non_proof_alpaca_like_source_labels": [],
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "next_scheduled_capture": {"scheduled_utc": "2026-05-21T20:20:00Z"},
            },
            "scan": {
                "candidate_count": 0,
                "candidate_symbols": [],
                "quote_freshness_context": {
                    "status": "fresh_or_not_age_limited",
                    "next_fresh_scan": {
                        "scheduled_user_local": "2026-05-21T08:10:00-06:00",
                        "window_end_user_local": "2026-05-21T14:00:00-06:00",
                        "scan_calendar": "us_equity_market_days",
                        "holiday_calendar_source": "NYSE/Nasdaq US equity market holiday rules",
                        "scheduled_trade_date_is_market_day": True,
                    }
                },
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["FCX"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "gate_sensitivity": {"production_filters_preserved": True},
                "blocker_examples": [{"symbol": "FCX", "drop_key": "option_liquidity"}],
            },
            "lane_iteration_plan": {
                "steps": [
                    {
                        "step": "post_close_full_universe_capture",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T20:20:00Z",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-21",
                        ],
                    }
                ]
            },
        }

        payload = build_next_execution_cli_payload(
            report,
            payload_source="latest_artifact",
            reference_now=datetime(2026, 5, 21, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(payload["payload_source"], "latest_artifact")
        self.assertEqual(payload["provider"], "alpaca:sip:opra")
        self.assertEqual(payload["read_at_utc"], "2026-05-21T14:15:00Z")
        self.assertEqual(payload["read_at_user_local"], "2026-05-21T08:15:00-06:00")
        self.assertEqual(payload["read_at_runbook_timezone"], "America/Denver")
        self.assertEqual(payload["report_age_minutes"], 405.0)
        self.assertEqual(payload["verification_status"], "not_verified")
        self.assertFalse(payload["verified"])
        self.assertEqual(payload["verification_blockers"], ["shared_quote_dates:1/100", "live_scan_candidates:0"])
        self.assertEqual(payload["iteration_ledger_status"], "unchanged_waiting_for_fresh_opra_scan")
        self.assertEqual(payload["iteration_ledger_improvements"], ["proof_source_isolation_contract_clean"])
        self.assertEqual(payload["iteration_ledger_regressions"], [])
        self.assertEqual(
            payload["iteration_ledger_non_material_flags"],
            ["scan_liquidity_gate_distance_delta_below_materiality"],
        )
        self.assertEqual(payload["iteration_ledger_active_blockers"], ["has_required_exact_alpaca_opra_history_depth"])
        self.assertEqual(payload["iteration_ledger_capture_runway"]["next_missing_capture_trade_date"], "2026-05-21")
        self.assertEqual(payload["iteration_ledger_unlock_conditions"]["full_exact_replay"]["remaining_shared_quote_dates"], 99)
        self.assertEqual(payload["goal_completion_status"], "not_complete")
        self.assertFalse(payload["goal_completion_complete"])
        self.assertEqual(
            payload["goal_completion_failed_requirements"],
            ["has_required_exact_alpaca_opra_history_depth", "live_scan_has_verifiable_candidate"],
        )
        self.assertFalse(payload["goal_completion_may_mark_goal_complete"])
        self.assertEqual(
            payload["goal_completion_next_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )
        self.assertTrue(payload["goal_completion_proof_source_isolation_requirement_passed"])
        self.assertEqual(
            payload["goal_completion_proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(payload["goal_completion_proof_source_isolation_blockers"], [])
        self.assertEqual(payload["goal_completion_next_requirement_to_unblock"], "live_scan_has_verifiable_candidate")
        self.assertEqual(payload["goal_completion_next_evidence_command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(payload["goal_completion_market_data_evidence_generated_at"], "2026-05-21T07:30:00Z")
        self.assertEqual(payload["goal_completion_record_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertEqual(payload["goal_completion_derived_refreshed_at_utc"], "2026-05-21T10:45:00Z")
        self.assertFalse(payload["goal_completion_market_data_commands_run_in_current_refresh"])
        self.assertTrue(payload["goal_completion_automation_health_refreshed_in_current_refresh"])
        self.assertTrue(payload["derived_refresh_historical_store_refreshed"])
        self.assertIsNone(payload["derived_refresh_historical_store_refresh_error"])
        self.assertEqual(payload["derived_refresh_historical_store_shared_quote_dates_before"], 1)
        self.assertEqual(payload["derived_refresh_historical_store_shared_quote_dates_after"], 1)
        self.assertFalse(payload["derived_refresh_historical_store_shared_quote_dates_changed"])
        self.assertFalse(payload["derived_refresh_preserved_evidence_stale_after_historical_store_refresh"])
        self.assertEqual(payload["derived_refresh_preserved_evidence_stale_fields"], [])
        self.assertIsNone(payload["derived_refresh_preserved_evidence_refresh_command"])
        self.assertIsNone(payload["derived_refresh_preserved_evidence_refresh_reason"])
        self.assertEqual(
            payload["derived_refresh_next_blocker_before"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertEqual(
            payload["derived_refresh_raw_next_blocker_after"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertEqual(
            payload["derived_refresh_next_blocker_after"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertFalse(payload["derived_refresh_next_blocker_changed"])
        self.assertEqual(
            payload["goal_completion_missing_evidence"],
            ["has_required_exact_alpaca_opra_history_depth", "live_scan_has_verifiable_candidate"],
        )
        self.assertEqual(payload["exact_history_acquisition_status"], "forward_capture_required")
        self.assertEqual(payload["exact_history_backfill_status"], "forward_daily_snapshot_capture_required")
        self.assertEqual(payload["exact_history_next_capture_trade_date"], "2026-05-21")
        self.assertEqual(
            payload["exact_history_next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(payload["exact_history_next_capture_not_before_user_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(payload["exact_history_forward_capture_queue"][0]["trade_date"], "2026-05-21")
        self.assertEqual(payload["exact_history_forward_capture_queue"][1]["trade_date"], "2026-05-22")
        self.assertEqual(payload["exact_history_forward_capture_queue"][2]["trade_date"], "2026-05-26")
        self.assertEqual(
            payload["exact_history_forward_capture_queue"][0]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(payload["exact_history_forward_capture_queue_summary"][0]["rank"], 1)
        self.assertEqual(payload["exact_history_forward_capture_queue_summary"][0]["trade_date"], "2026-05-21")
        self.assertEqual(
            payload["exact_history_forward_capture_queue_summary"][0]["not_before_user_local"],
            "2026-05-21T14:20:00-06:00",
        )
        self.assertEqual(
            payload["exact_history_forward_capture_queue_summary"][0]["expected_shared_quote_dates_after_capture"],
            2,
        )
        self.assertEqual(
            payload["exact_history_unlock_milestones"]["diagnostic_replay"]["unlock_trade_date"],
            "2026-09-24",
        )
        self.assertEqual(
            payload["exact_history_unlock_milestones"]["full_exact_replay"]["unlock_trade_date"],
            "2026-10-12",
        )
        self.assertEqual(
            payload["exact_history_unlock_milestones"]["diagnostic_replay"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-09-24",
        )
        self.assertFalse(payload["exact_history_can_accelerate_with_existing_sources"])
        self.assertEqual(payload["exact_replay_unlock_status"], "waiting_for_diagnostic_replay_history")
        self.assertEqual(payload["exact_replay_unlock_diagnostic_remaining_shared_quote_dates"], 87)
        self.assertEqual(payload["exact_replay_unlock_full_remaining_shared_quote_dates"], 99)
        self.assertEqual(payload["exact_replay_unlock_diagnostic_trade_date"], "2026-09-24")
        self.assertEqual(payload["exact_replay_unlock_full_trade_date"], "2026-10-12")
        self.assertEqual(
            payload["exact_replay_unlock_immediate_next_capture_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            payload["exact_replay_unlock_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertEqual(
            payload["exact_replay_readiness_checklist_status"],
            "waiting_for_exact_opra_history_depth",
        )
        self.assertFalse(payload["exact_replay_ready_to_run_full_exact_replay"])
        self.assertIn(
            "full_exact_replay_history_depth_available",
            payload["exact_replay_readiness_checklist_blockers"],
        )
        self.assertIn(
            "diagnostic_replay_waiting_for_exact_opra_history_depth",
            payload["exact_replay_unlock_blockers"],
        )
        self.assertEqual(
            payload["exact_replay_unlock_next_action"],
            "continue_forward_daily_alpaca_opra_capture",
        )
        self.assertEqual(
            payload["exact_history_backfill_capability_status"],
            "forward_capture_required_for_exact_bid_ask_history",
        )
        self.assertEqual(
            payload["exact_history_backfill_missing_capability"],
            "historical_option_quote_bbo_method_for_contracts",
        )
        self.assertFalse(payload["exact_history_backfill_can_accelerate"])
        self.assertEqual(
            payload["exact_history_backfill_next_action"],
            "continue_forward_daily_alpaca_opra_snapshot_capture",
        )
        self.assertEqual(payload["exact_capture_progress_status"], "awaiting_guarded_capture_to_advance_history")
        self.assertEqual(payload["exact_capture_progress_target_trade_date"], "2026-05-21")
        self.assertEqual(
            payload["exact_capture_progress_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(payload["exact_capture_progress_expected_shared_quote_dates_after_next_capture"], 2)
        self.assertEqual(payload["exact_capture_progress_remaining_shared_quote_dates_after_success"], 98)
        self.assertEqual(
            payload["exact_capture_progress_proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(payload["exact_capture_progress_proof_source_isolation_blockers"], [])
        self.assertIn(
            "proof_window.current_shared_quote_dates == 2",
            payload["exact_capture_progress_material_progress_if"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status == isolated_to_alpaca_opra_proof_source",
            payload["exact_capture_progress_material_progress_if"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            payload["exact_capture_progress_fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_source_isolation_contract.status",
            payload["exact_capture_progress_fields_to_compare_after_run"],
        )
        self.assertEqual(payload["exact_capture_progress_blockers"], [])
        self.assertEqual(payload["exact_capture_progress_next_action"], "run_guarded_capture_after_not_before")
        self.assertEqual(
            payload["exact_capture_post_run_evidence_refresh_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan",
        )
        self.assertEqual(
            payload["exact_capture_post_run_replay_command_when_unlocked"],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertIn(
            payload["exact_capture_post_run_evidence_contract_status"],
            {"waiting_for_guarded_capture_run", "post_capture_progress_blocked"},
        )
        self.assertIn(
            payload["exact_capture_post_run_next_capture_evidence_state"],
            {
                "next_capture_target_waiting_until_not_before",
                "next_capture_target_pending_guarded_capture",
                "next_capture_target_due_now",
            },
        )
        self.assertIs(payload["exact_capture_post_run_next_capture_target_observed"], False)
        self.assertIs(payload["exact_capture_post_run_stale_success_guard_for_next_target"], False)
        self.assertEqual(
            payload["exact_capture_post_run_evidence_contract_next_capture_evidence_state"],
            payload["exact_capture_post_run_next_capture_evidence_state"],
        )
        self.assertIn(
            "next_execution_runbook_card.run_next_execution_command true",
            payload["exact_capture_post_run_required_before_run"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates",
            payload["exact_capture_post_run_fields_to_compare_after_run"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates >= 2",
            payload["exact_capture_post_run_material_progress_if"],
        )
        self.assertIn(
            "proof_window.current_shared_quote_dates < 2",
            payload["exact_capture_post_run_failure_signals_after_run"],
        )
        self.assertIn(
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
            payload["exact_capture_post_run_post_run_commands"],
        )
        self.assertIn(
            "exact_replay_unlock_contract.full_exact_replay_unlocked",
            payload["exact_capture_post_run_profitability_gate_fields"],
        )
        self.assertEqual(
            payload["exact_capture_post_run_profitability_handoff"][0]["step"],
            "readback_next_execution_after_capture",
        )
        self.assertEqual(payload["proof_source_label"], "alpaca_opra_daily_snapshot")
        self.assertTrue(payload["proof_source_trusted_only"])
        self.assertEqual(payload["proof_source_shared_quote_dates"]["count"], 1)
        self.assertEqual(payload["shared_quote_dates"]["count"], 1)
        self.assertTrue(payload["proof_source_all_required_symbols_available"])
        self.assertEqual(payload["proof_source_required_symbol_coverage"]["available_required_symbol_count"], 24)
        self.assertEqual(payload["proof_source_alpaca_like_source_labels_seen"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(payload["proof_source_non_proof_alpaca_like_source_labels"], [])
        self.assertEqual(payload["proof_source_isolation_status"], "isolated_to_alpaca_opra_proof_source")
        self.assertEqual(
            payload["proof_source_isolation_exact_profitability_proof_source_labels"],
            ["alpaca_opra_daily_snapshot"],
        )
        self.assertEqual(payload["proof_source_isolation_research_only_source_labels"], [])
        self.assertEqual(payload["proof_source_isolation_blockers"], [])
        self.assertEqual(payload["proof_source_isolation_next_action"], "continue_using_alpaca_opra_proof_source")
        self.assertEqual(payload["capture_calendar"], "us_equity_market_days")
        self.assertEqual(payload["remaining_market_day_capture_count"], 99)
        self.assertEqual(payload["diagnostic_remaining_market_day_capture_count"], 87)
        self.assertEqual(payload["full_replay_remaining_market_day_capture_count"], 99)
        self.assertTrue(payload["legacy_weekday_fields_are_market_day_aware"])
        self.assertEqual(payload["approx_market_days_to_target"], 99)
        self.assertEqual(payload["approx_diagnostic_ready_date"], "2026-09-18")
        self.assertEqual(payload["approx_diagnostic_ready_date_market_day"], "2026-09-24")
        self.assertEqual(payload["approx_completion_date_market_day"], "2026-10-12")
        self.assertEqual(payload["scan_fresh_scan_calendar"], "us_equity_market_days")
        self.assertEqual(
            payload["scan_fresh_scan_holiday_calendar_source"],
            "NYSE/Nasdaq US equity market holiday rules",
        )
        self.assertTrue(payload["scan_fresh_scan_trade_date_is_market_day"])
        self.assertEqual(payload["scan_next_fresh_scan_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(payload["scan_fresh_scan_window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(payload["scan_candidate_count"], 0)
        self.assertEqual(payload["scan_candidate_symbols"], [])
        self.assertEqual(payload["scan_quote_freshness_status"], "fresh_or_not_age_limited")
        self.assertEqual(payload["scan_drop_diagnostics"][0]["drop_key"], "option_liquidity")
        self.assertTrue(payload["scan_gate_sensitivity"]["production_filters_preserved"])
        self.assertEqual(payload["scan_blocker_examples"][0]["symbol"], "FCX")
        self.assertEqual(payload["next_proof_event_status"], "waiting_until_next_proof_event")
        self.assertEqual(payload["next_proof_event_kind"], "fresh_opra_live_candidate_scan")
        self.assertEqual(
            payload["next_proof_event_target_goal_requirement"],
            "live_scan_has_verifiable_candidate",
        )
        self.assertEqual(payload["next_proof_event_command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertIn("scan.candidate_count > 0", payload["next_proof_event_material_progress_if"])
        self.assertIn("scan.candidate_symbols", payload["next_proof_event_fields_to_compare_after_run"])
        self.assertIn(
            "quote_freshness_cleared_and_candidates_still_zero",
            payload["next_proof_event_no_progress_blockers_to_record"],
        )
        self.assertEqual(payload["fresh_scan_decision_status"], "waiting_for_fresh_opra_scan")
        self.assertEqual(payload["fresh_scan_decision_branch"], "clock_guard_branch")
        self.assertEqual(payload["fresh_scan_decision_next_action"], "run_fresh_opra_scan_at_not_before_time")
        self.assertFalse(payload["fresh_scan_decision_safe_to_tune_filters"])
        self.assertEqual(payload["fresh_scan_decision_top_drop_counts"], [{"drop_key": "option_liquidity", "count": 9}])
        self.assertEqual(
            payload["fresh_scan_decision_zero_candidate_diagnostic_plan"][0]["production_filter_action"],
            "preserve_filters_until_exact_replay_unlock",
        )
        self.assertEqual(
            payload["fresh_scan_decision_post_run_playbook"][0]["next_action"],
            "preserve_filters_and_accumulate_exact_alpaca_opra_replay_history",
        )
        self.assertEqual(payload["fresh_scan_decision_post_run_playbook_status"], "pending_fresh_scan_execution")
        self.assertIsNone(payload["fresh_scan_decision_selected_post_run_condition"])
        self.assertIsNone(payload["fresh_scan_decision_selected_post_run_next_action"])
        self.assertEqual(
            payload["fresh_scan_decision_outcome_matrix"][0]["goal_requirement_effect"],
            "can_unblock_if_candidate_is_inside_exact_proof_universe",
        )
        self.assertEqual(
            payload["fresh_scan_decision_outcome_matrix"][0]["next_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertIsNone(payload["fresh_scan_decision_selected_outcome"])
        self.assertIsNone(payload["fresh_scan_decision_selected_outcome_effect"])
        self.assertIsNone(payload["fresh_scan_decision_selected_outcome_next_command"])
        self.assertIn("live_candidate_recovery_plan", payload)
        self.assertIn("live_candidate_recovery_status", payload)
        self.assertEqual(
            payload["live_candidate_recovery_next_command_role"],
            "repair_proof_source_or_universe_alignment",
        )
        self.assertEqual(
            payload["live_candidate_recovery_history_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            payload["live_candidate_recovery_scan_evidence_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["live_candidate_recovery_read_only_review_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        payload_command_roles = {
            item["role"]: item for item in payload["live_candidate_recovery_command_roles"]
        }
        self.assertTrue(payload_command_roles["history_unlock_before_filter_mutation"]["applies_now"])
        self.assertFalse(payload_command_roles["fresh_live_scan_evidence"]["applies_now"])
        self.assertTrue(payload_command_roles["read_only_zero_candidate_review"]["applies_now"])
        self.assertFalse(payload["live_candidate_recovery_safe_to_tune_production_filters"])
        self.assertIn("live_scan_has_candidate", payload["live_candidate_recovery_blockers"])
        self.assertEqual(payload["live_candidate_recovery_dominant_drop_key"], "option_liquidity")
        self.assertGreater(payload["live_candidate_recovery_read_only_recovery_queue_count"], 0)
        self.assertEqual(
            payload["live_candidate_recovery_first_read_only_review"]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            payload["live_candidate_recovery_first_read_only_review_by_drop"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            payload["live_candidate_recovery_read_only_recovery_priority_order"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            payload["live_candidate_recovery_read_only_recovery_watchlist"][0]["symbol"],
            "FCX",
        )
        self.assertIn(
            "future_fresh_alpaca_opra_scan.candidate_count > 0",
            payload["live_candidate_recovery_read_only_recovery_material_progress_if"],
        )
        self.assertIn(
            "live_candidate_recovery_plan.read_only_recovery_queue",
            payload["live_candidate_recovery_read_only_recovery_evidence_fields"],
        )
        self.assertEqual(payload["live_candidate_recovery_read_only_symbols_to_watch"], ["FCX"])
        self.assertEqual(
            payload["live_candidate_recovery_read_only_next_review_steps"][0]["step"],
            "read_only_review_option_liquidity_FCX",
        )
        self.assertEqual(payload["post_fresh_scan_research_backlog_status"], "waiting_for_fresh_scan_outcome")
        self.assertEqual(payload["post_fresh_scan_research_backlog_hypothesis_count"], 1)
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_unlock_status"],
            "locked_until_exact_replay_can_measure_filter_changes",
        )
        self.assertIn(
            "readiness_ready_for_exact_replay",
            payload["post_fresh_scan_research_backlog_activation_blockers"],
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_variant_unlock_runway"]["history_depth_runway"][
                "current_shared_quote_dates"
            ],
            1,
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_variant_unlock_runway"]["history_depth_runway"][
                "full_replay_unlock_trade_date"
            ],
            "2026-10-12",
        )
        self.assertEqual(payload["post_fresh_scan_research_backlog_deferred_test_count"], 1)
        self.assertEqual(payload["post_fresh_scan_research_backlog_deferred_variant_run_recipe_count"], 2)
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_recipe_audit_status"],
            "queued_locked_with_verified_opra_recipe_contracts",
        )
        self.assertTrue(payload["post_fresh_scan_research_backlog_deferred_variant_recipes_opra_backed"])
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_config_materialization_command"],
            "python scripts/run_ai_commodity_opra_progress.py --materialize-deferred-variant-configs",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_execution_plan_status"],
            "locked_until_activation_gates_pass",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_activation_unlock_plan"][
                "current_primary_gate"
            ],
            "enough_exact_shared_quote_dates",
        )
        self.assertEqual(payload["post_fresh_scan_research_backlog_deferred_variant_ordered_sweep_count"], 2)
        self.assertIn(
            "scripts/run_research_variant_cycle.py",
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_command"],
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep"]["variant_id"],
            "liquidity_leg12_slippage15",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_run_guard"],
            "do_not_run_until_all_activation_gates_pass",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_status"],
            "locked_until_activation_gates_pass",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_first_blocking_gate"],
            "enough_exact_shared_quote_dates",
        )
        self.assertEqual(
            payload[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_blocked_by_goal_requirements"
            ],
            ["has_required_exact_alpaca_opra_history_depth", "exact_replay_is_profitable"],
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_ready_trade_date"],
            "2026-10-12",
        )
        self.assertEqual(
            payload[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_activation_ready_not_before_user_local"
            ],
            "2026-10-12T14:20:00-06:00",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_first_sweep_next_unlock_command"],
            "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
        )
        self.assertEqual(
            payload[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_next_unlock_not_before_user_local"
            ],
            "2026-05-21T14:20:00-06:00",
        )
        self.assertEqual(
            payload[
                "post_fresh_scan_research_backlog_deferred_variant_first_sweep_replay_command_when_unlocked"
            ],
            "python scripts/run_ai_commodity_opra_progress.py",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_variant_result_collection_command"],
            "python scripts/run_ai_commodity_opra_progress.py --collect-deferred-variant-results",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["drop_key"],
            "option_liquidity",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["status"],
            "queued_locked",
        )
        self.assertIn(
            "verification_gate.replay_profit_factor",
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["compare_fields"],
        )
        self.assertIn(
            "scripts/run_research_variant_cycle.py",
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["variant_run_recipes"][0][
                "run_command"
            ],
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["variant_blueprint"][
                "research_variant_support"
            ],
            "ai_commodity_option_filter_override_supported",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_deferred_test_queue"][0]["variant_blueprint"][
                "current_thresholds"
            ]["liquidity_spread_max_pct"],
            8.0,
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_hypotheses"][0]["hypothesis"],
            "separate_quote_age_from_structural_spread_and_depth_blockers",
        )
        self.assertEqual(
            payload["post_fresh_scan_research_backlog_next_action"],
            "run_fresh_opra_scan_at_not_before_time",
        )
        self.assertTrue(payload["automation_healthy"])
        self.assertTrue(payload["automation_prompt_mentions_lane_next_step_plan"])
        self.assertTrue(payload["automation_prompt_mentions_next_execution_runbook_card"])
        self.assertTrue(payload["automation_prompt_mentions_run_next_execution_command_guard"])
        self.assertTrue(payload["automation_prompt_mentions_proof_source_isolation_contract"])
        self.assertTrue(payload["automation_prompt_mentions_capture_continuity_contract"])
        self.assertEqual(payload["automation_scheduled_intraday_times"], ["08:10:00", "14:20:00"])
        self.assertEqual(payload["iteration_ledger_status"], "unchanged_waiting_for_fresh_opra_scan")
        self.assertEqual(payload["iteration_ledger_shared_quote_dates"]["remaining"], 99)
        self.assertEqual(payload["progress_history_summary"]["status"], "summarized")
        self.assertEqual(payload["progress_history_summary"]["same_next_blocker_streak"], 4)
        self.assertEqual(
            payload["progress_history_summary"]["latest_next_blocker"],
            "alpaca_opra_daily_snapshot_shared_quote_dates:1/100",
        )
        self.assertEqual(
            payload["iteration_ledger_capture_runway"]["approx_exact_replay_ready_date"],
            "2026-10-06",
        )
        self.assertEqual(
            payload["iteration_ledger_unlock_conditions"]["diagnostic_replay"]["remaining_shared_quote_dates"],
            87,
        )
        self.assertEqual(
            payload["iteration_ledger_unlock_conditions"]["filter_tuning"]["status"],
            "locked_until_exact_replay_is_ready",
        )
        self.assertEqual(payload["lane_phase"], "fresh_scan_wait")
        self.assertEqual(payload["next_timed_event_kind"], "fresh_opra_scan")
        self.assertEqual(payload["next_timed_event_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(payload["next_timed_event_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(payload["next_timed_event_calendar"], "us_equity_market_days")
        self.assertTrue(payload["next_timed_event_trade_date_is_market_day"])
        self.assertEqual(payload["next_execution_status"], "waiting_until_not_before")
        self.assertEqual(payload["next_execution_selected_step"], "fresh_opra_live_scan")
        self.assertEqual(payload["next_execution_actionable_now"], False)
        self.assertEqual(
            payload["next_execution_command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertEqual(payload["next_execution_command_display"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(payload["next_execution_blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])
        self.assertEqual(payload["next_execution_clock_status"], "waiting_until_not_before")
        self.assertFalse(payload["next_execution_due_by_clock"])
        self.assertIsNone(payload["next_execution_not_before_utc"])
        self.assertIsNone(payload["next_execution_not_before_user_local"])
        self.assertIsNone(payload["next_execution_window_end_utc"])
        self.assertIsNone(payload["next_execution_window_end_user_local"])
        self.assertEqual(payload["next_execution_runbook_timezone"], "America/Denver")
        self.assertIsNone(payload["next_execution_minutes_until_not_before"])
        self.assertIsNone(payload["next_execution_wait_minutes"])
        self.assertFalse(payload["next_execution_only_waiting_on_clock"])
        self.assertFalse(payload["next_execution_effective_actionable_now"])
        self.assertEqual(payload["next_execution_recommended_action"], "wait_until_not_before")
        self.assertIsNone(payload["next_execution_recommended_command"])
        self.assertEqual(payload["next_execution_preflight_status"], "ready_after_clock")
        self.assertEqual(payload["next_execution_preflight_failed_checks"], [])
        self.assertEqual(payload["next_execution_preflight_non_clock_blockers"], [])
        self.assertTrue(payload["next_execution_preflight_proof_source_isolation_required"])
        self.assertEqual(
            payload["next_execution_preflight_proof_source_isolation_status"],
            "isolated_to_alpaca_opra_proof_source",
        )
        self.assertEqual(payload["next_execution_preflight_proof_source_isolation_blockers"], [])
        self.assertFalse(payload["next_execution_preflight_capture_continuity_required"])
        self.assertFalse(payload["next_execution_preflight_full_universe_hard_gates_required"])
        self.assertFalse(payload["next_execution_preflight_capture_command_contract_required"])
        self.assertFalse(payload["run_next_execution_command"])
        self.assertEqual(
            payload["run_next_execution_command_reason"],
            "waiting_until_not_before:2026-05-21T14:10:00Z",
        )
        self.assertEqual(
            payload["run_next_execution_command_blockers"],
            ["waiting_until_not_before:2026-05-21T14:10:00Z"],
        )
        self.assertEqual(payload["run_next_execution_command_required_action"], "wait_until_not_before")
        self.assertIsNone(payload["run_next_execution_command_args"])
        self.assertIsNone(payload["run_next_execution_command_display"])
        self.assertEqual(payload["run_next_execution_guard_summary_status"], "waiting_until_not_before")
        self.assertEqual(
            payload["run_next_execution_guard_summary_reason"],
            "waiting_until_not_before:2026-05-21T14:10:00Z",
        )
        self.assertIsNone(payload["run_next_execution_guard_allowed_command_now"])
        self.assertEqual(
            payload["run_next_execution_guarded_command_to_run_when_allowed"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["run_next_execution_guard_summary"]["required_action"],
            "wait_until_not_before",
        )
        self.assertEqual(payload["next_execution_runbook_card"]["guard_status"], "clock_guard_active")
        self.assertEqual(payload["next_execution_runbook_guard_status"], "clock_guard_active")
        self.assertFalse(payload["next_execution_runbook_card"]["run_next_execution_command"])
        self.assertEqual(
            payload["next_execution_runbook_card"]["command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(
            payload["next_execution_runbook_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(payload["next_execution_runbook_recommended_action"], "wait_until_not_before")
        self.assertEqual(payload["next_execution_runbook_card"]["recommended_action"], "wait_until_not_before")
        self.assertEqual(payload["next_execution"]["selected_step"], "fresh_opra_live_scan")
        self.assertEqual(
            payload["next_execution"]["command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertEqual(payload["last_execution_review"]["status"], "not_due_yet")
        self.assertEqual(payload["last_execution_status"], "not_due_yet")

    def test_build_next_execution_cli_payload_marks_latest_wait_contract_due_by_clock(self):
        report = {
            "generated_at": "2026-05-21T07:30:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {"status": "not_verified", "verified": False, "blockers": []},
            "lane_next_step": {
                "phase": "fresh_scan_wait",
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "window_end_utc": "2026-05-21T20:00:00Z",
            },
            "profitability_evidence_scorecard": {
                "status": "recording_progress_waiting_for_exact_history_depth",
                "passed_requirement_count": 2,
                "total_requirement_count": 8,
                "post_event_scoring_rules": {
                    "fresh_scan_raw_drop_reason_audit": {
                        "fields_to_compare": ["scan_drop_reason_count"]
                    }
                },
                "post_event_readback_packet": {
                    "status": "waiting_until_not_before",
                "readback_command": (
                    "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
                ),
                "readback_projection_shell": "powershell",
                "readback_projection_command": (
                    "$r = python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest | "
                    "ConvertFrom-Json; [pscustomobject]@{ profitability_evidence_scorecard_delta_status = "
                    "$r.profitability_evidence_scorecard_delta_status } | ConvertTo-Json -Depth 6"
                ),
                "readback_projection_success_criteria": [
                    "projection exits with code 0",
                    "profitability_evidence_scorecard_delta_status is not null",
                ],
                "readback_fields": [
                    "alpaca_opra_data_usage_proof_window_shared_quote_dates",
                    "profitability_evidence_scorecard_delta_status",
                    ],
                    "readback_field_groups": {
                        "scorecard_delta": ["profitability_evidence_scorecard_delta_status"]
                    },
                    "progress_success_rules": {
                        "fresh_scan_raw_drop_reason_audit": {
                            "fields_to_compare": ["scan_drop_reason_count"]
                        }
                    },
                    "no_mutation_guard": (
                        "production_filters_preserved_until_exact_alpaca_opra_replay_unlock"
                    ),
                },
                "post_event_readback_command": (
                    "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest"
                ),
            },
            "last_execution_review": {"status": "not_due_yet"},
        }

        payload = build_next_execution_cli_payload(
            report,
            payload_source="latest_artifact",
            reference_now=datetime(2026, 5, 21, 14, 15, tzinfo=UTC),
        )

        self.assertTrue(payload["next_execution_due_by_clock"])
        self.assertEqual(payload["last_execution_status"], "not_due_yet")
        self.assertEqual(payload["next_execution_status"], "waiting_until_not_before")
        self.assertEqual(payload["next_execution_selected_step"], "fresh_opra_live_scan")
        self.assertEqual(
            payload["next_execution_command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertEqual(payload["next_execution_command_display"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(payload["next_execution_blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])
        self.assertFalse(payload["next_execution_expired_by_clock"])
        self.assertEqual(payload["next_execution_not_before_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(payload["next_execution_not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(payload["next_execution_window_end_utc"], "2026-05-21T20:00:00Z")
        self.assertEqual(payload["next_execution_window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(payload["next_execution_minutes_until_not_before"], -5.0)
        self.assertEqual(payload["next_execution_wait_minutes"], 0.0)
        self.assertEqual(payload["next_execution_minutes_until_window_end"], 345.0)
        self.assertEqual(payload["next_execution_window_minutes_remaining"], 345.0)
        self.assertTrue(payload["next_execution_only_waiting_on_clock"])
        self.assertEqual(payload["next_execution_clock_status"], "ready_by_clock")
        self.assertTrue(payload["next_execution_effective_actionable_now"])
        self.assertEqual(
            payload["profitability_evidence_scorecard_post_event_readback_packet"]["readback_command"],
            "python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest",
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status",
            payload["profitability_evidence_scorecard_readback_fields"],
        )
        self.assertEqual(
            payload["profitability_evidence_scorecard_readback_projection_shell"],
            "powershell",
        )
        self.assertIn(
            "profitability_evidence_scorecard_delta_status",
            payload["profitability_evidence_scorecard_readback_projection_command"],
        )
        self.assertIn(
            "projection exits with code 0",
            payload["profitability_evidence_scorecard_readback_projection_success_criteria"],
        )
        self.assertEqual(
            payload["profitability_evidence_scorecard_delta_baseline_comparison_status"],
            "no_previous_scorecard_baseline",
        )
        self.assertFalse(
            payload[
                "profitability_evidence_scorecard_delta_baseline_comparison_material_progress"
            ]
        )
        self.assertEqual(
            payload["profitability_evidence_scorecard_readback_no_mutation_guard"],
            "production_filters_preserved_until_exact_alpaca_opra_replay_unlock",
        )
        self.assertEqual(payload["next_execution_recommended_action"], "run_next_execution_command")
        self.assertEqual(
            payload["next_execution_recommended_command"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertTrue(payload["run_next_execution_command"])
        self.assertEqual(payload["run_next_execution_command_reason"], "ready_to_run_guarded_command")
        self.assertEqual(payload["run_next_execution_command_blockers"], [])
        self.assertIsNone(payload["run_next_execution_command_required_action"])
        self.assertEqual(
            payload["run_next_execution_command_args"],
            ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
        )
        self.assertEqual(
            payload["run_next_execution_command_display"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(payload["guarded_command_decision_status"], "ready_to_run_primary_next_execution")
        self.assertEqual(payload["guarded_command_decision_action"], "run_next_execution_command")
        self.assertEqual(payload["guarded_command_decision_source"], "primary_next_execution")
        self.assertTrue(payload["guarded_command_decision_safe_to_execute_now"])
        self.assertEqual(
            payload["guarded_command_decision_command"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertEqual(payload["run_next_execution_guard_summary_status"], "ready_to_run_guarded_command")
        self.assertEqual(payload["run_next_execution_guard_summary_reason"], "ready_to_run_guarded_command")
        self.assertEqual(
            payload["run_next_execution_guard_allowed_command_now"],
            "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
        )
        self.assertIsNone(payload["run_next_execution_guarded_command_to_run_when_allowed"])
        self.assertIsNone(payload["run_next_execution_guard_summary"]["required_action"])
        self.assertEqual(payload["next_execution_runbook_card"]["guard_status"], "ready_to_run_guarded_command")
        self.assertTrue(payload["next_execution_runbook_card"]["run_next_execution_command"])
        self.assertEqual(
            payload["next_execution_runbook_card"]["summary"],
            "run_the_guarded_next_execution_command",
        )
        self.assertEqual(payload["next_execution_runbook_card"]["not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(payload["next_execution_runbook_card"]["window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(payload["next_execution_runbook_card"]["wait_minutes"], 0.0)
        self.assertEqual(payload["next_execution_runbook_card"]["window_minutes_remaining"], 345.0)

    def test_build_next_execution_cli_payload_expires_stale_fresh_scan_window(self):
        report = {
            "generated_at": "2026-05-21T07:30:00Z",
            "provider": "alpaca:sip:opra",
            "verification_gate": {"status": "not_verified", "verified": False, "blockers": []},
            "lane_next_step": {
                "phase": "fresh_scan_wait",
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "window_end_utc": "2026-05-21T20:00:00Z",
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
            },
            "last_execution_review": {"status": "not_due_yet"},
        }

        payload = build_next_execution_cli_payload(
            report,
            payload_source="latest_artifact",
            reference_now=datetime(2026, 5, 21, 20, 20, tzinfo=UTC),
        )

        self.assertTrue(payload["next_execution_due_by_clock"])
        self.assertTrue(payload["next_execution_expired_by_clock"])
        self.assertEqual(payload["next_execution_minutes_until_not_before"], -370.0)
        self.assertEqual(payload["next_execution_wait_minutes"], 0.0)
        self.assertEqual(payload["next_execution_minutes_until_window_end"], -20.0)
        self.assertEqual(payload["next_execution_window_minutes_remaining"], 0.0)
        self.assertTrue(payload["next_execution_only_waiting_on_clock"])
        self.assertEqual(payload["next_execution_clock_status"], "expired_by_clock")
        self.assertFalse(payload["next_execution_effective_actionable_now"])
        self.assertEqual(payload["next_execution_recommended_action"], "run_progress_report")
        self.assertIsNone(payload["next_execution_recommended_command"])
        self.assertFalse(payload["run_next_execution_command"])
        self.assertEqual(
            payload["run_next_execution_command_reason"],
            "fresh_scan_window_expired_rerun_progress_report",
        )
        self.assertEqual(
            payload["run_next_execution_command_blockers"],
            ["waiting_until_not_before:2026-05-21T14:10:00Z"],
        )
        self.assertEqual(payload["run_next_execution_command_required_action"], "run_progress_report")
        self.assertIsNone(payload["run_next_execution_command_args"])
        self.assertIsNone(payload["run_next_execution_command_display"])
        self.assertEqual(payload["run_next_execution_guard_summary_status"], "progress_report_refresh_required")
        self.assertEqual(
            payload["run_next_execution_guard_summary_reason"],
            "fresh_scan_window_expired_rerun_progress_report",
        )
        self.assertIsNone(payload["run_next_execution_guard_allowed_command_now"])
        self.assertIsNone(payload["run_next_execution_guarded_command_to_run_when_allowed"])
        self.assertEqual(
            payload["run_next_execution_guard_summary"]["required_action"],
            "run_progress_report",
        )
        self.assertEqual(payload["next_execution_runbook_card"]["guard_status"], "fresh_scan_window_expired")
        self.assertFalse(payload["next_execution_runbook_card"]["run_next_execution_command"])
        self.assertEqual(
            payload["next_execution_runbook_card"]["summary"],
            "rerun_the_progress_report_before_using_a_stale_command",
        )
        self.assertEqual(payload["next_execution_runbook_card"]["window_minutes_remaining"], 0.0)

    def test_build_last_execution_review_waits_until_previous_not_before_time(self):
        previous = {
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
            },
            "next_execution_runbook_card": {
                "guard_status": "clock_guard_active",
                "recommended_action": "wait_until_not_before",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
                "window_end_user_local": "2026-05-21T14:00:00-06:00",
                "success_criteria": ["fresh_scan_candidate_count_above_zero"],
            }
        }
        current = {"generated_at": "2026-05-21T07:30:00Z"}

        review = build_last_execution_review(previous, current)

        self.assertEqual(review["status"], "not_due_yet")
        self.assertEqual(review["previous_selected_step"], "fresh_opra_live_scan")
        self.assertEqual(review["not_before_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(review["checks"], [])
        self.assertEqual(review["blockers"], ["waiting_until_not_before:2026-05-21T14:10:00Z"])
        self.assertEqual(review["previous_runbook_guard_status"], "clock_guard_active")
        self.assertEqual(review["previous_runbook_recommended_action"], "wait_until_not_before")
        self.assertEqual(review["previous_runbook_command"], "python scripts/run_ai_commodity_opra_progress.py --skip-capture")
        self.assertEqual(review["previous_runbook_not_before_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(review["previous_runbook_window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(review["previous_runbook_success_criteria"], ["fresh_scan_candidate_count_above_zero"])
        self.assertTrue(review["previous_runbook_command_matches_contract"])
        self.assertFalse(review["ran_from_runbook_card"])
        self.assertEqual(review["ran_from_runbook_card_inference"], "previous_runbook_card_waiting_until_not_before")

    def test_build_last_execution_review_evaluates_fresh_scan_success_criteria(self):
        previous = {
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "success_criteria": [
                    "fresh_scan_candidate_count_above_zero",
                    "quote_freshness_status_not_stale_quote_sensitive_or_blocked",
                    "primary_probe_quote_age_excess_hours_at_or_below_zero",
                ],
            },
            "next_execution_runbook_card": {
                "guard_status": "ready_to_run_guarded_command",
                "recommended_action": "run_next_execution_command",
                "command": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "not_before_user_local": "2026-05-21T08:10:00-06:00",
                "window_end_user_local": "2026-05-21T14:00:00-06:00",
                "success_criteria": [
                    "fresh_scan_candidate_count_above_zero",
                    "quote_freshness_status_not_stale_quote_sensitive_or_blocked",
                    "primary_probe_quote_age_excess_hours_at_or_below_zero",
                ],
            }
        }
        current = {
            "generated_at": "2026-05-21T14:15:00Z",
            "scan": {
                "candidate_count": 1,
                "quote_freshness_context": {"status": "fresh_or_not_age_limited"},
                "fresh_scan_retest_plan": {"primary_probe_quote_age_excess_hours": 0.0},
            },
        }

        review = build_last_execution_review(previous, current)

        self.assertEqual(review["status"], "passed")
        self.assertEqual(review["previous_selected_step"], "fresh_opra_live_scan")
        self.assertEqual(review["blockers"], [])
        self.assertTrue(all(check["passed"] for check in review["checks"]))
        self.assertEqual(review["previous_runbook_guard_status"], "ready_to_run_guarded_command")
        self.assertTrue(review["previous_runbook_command_matches_contract"])
        self.assertTrue(review["ran_from_runbook_card"])
        self.assertEqual(
            review["ran_from_runbook_card_inference"],
            "previous_runbook_command_matches_contract_and_due_window_reached",
        )

    def test_build_last_execution_review_evaluates_capture_success_criteria(self):
        previous = {
            "shared_quote_dates_after": {"count": 1},
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "post_close_full_universe_capture",
                "not_before_utc": "2026-05-21T20:20:00Z",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-21",
                ],
            },
            "next_execution_runbook_card": {
                "guard_status": "ready_to_run_guarded_command",
                "recommended_action": "run_next_execution_command",
                "command": "python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21",
                "not_before_user_local": "2026-05-21T14:20:00-06:00",
                "window_end_user_local": None,
                "success_criteria": [
                    "capture_target_complete_true",
                    "shared_quote_dates_increase_or_target_was_already_complete",
                    "full_universe_hard_gates_remain_true",
                ],
            },
        }
        current = {
            "generated_at": "2026-05-21T20:30:00Z",
            "shared_quote_dates_after": {"count": 2},
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
            },
            "verification_gate": {
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                }
            },
        }

        review = build_last_execution_review(previous, current)

        self.assertEqual(review["status"], "passed")
        self.assertEqual(review["previous_selected_step"], "post_close_full_universe_capture")
        self.assertEqual(review["blockers"], [])
        self.assertTrue(all(check["passed"] for check in review["checks"]))
        check_names = {check["name"] for check in review["checks"]}
        self.assertIn("local_exact_store_matches_proof_window_after_capture", check_names)
        self.assertIn("local_exact_store_has_no_pending_refresh_after_capture", check_names)
        self.assertTrue(review["previous_runbook_command_matches_contract"])
        self.assertTrue(review["ran_from_runbook_card"])

    def test_build_last_execution_review_blocks_capture_when_local_store_outpaces_proof_window(self):
        previous = {
            "shared_quote_dates_after": {"count": 1},
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "post_close_full_universe_capture",
                "not_before_utc": "2026-05-21T20:20:00Z",
                "command": [
                    "python",
                    "scripts/run_ai_commodity_opra_progress.py",
                    "--force-capture",
                    "--target-date",
                    "2026-05-21",
                ],
            },
        }
        current = {
            "generated_at": "2026-05-21T20:30:00Z",
            "shared_quote_dates_after": {"count": 2},
            "proof_window": {"current_shared_quote_dates": 2, "required_shared_quote_dates": 100},
            "proof_source_audit": {
                "proof_source_shared_quote_dates": {"count": 3},
                "proof_source_store_inventory": {"quote_dates": {"count": 3}},
                "proof_source_required_symbol_coverage": {
                    "available_required_symbol_count": 24,
                    "required_symbol_count": 24,
                    "missing_required_symbols": [],
                },
            },
            "capture": {
                "status": "captured",
                "target_capture_complete": True,
            },
            "verification_gate": {
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                }
            },
        }

        review = build_last_execution_review(previous, current)

        self.assertEqual(review["status"], "failed")
        self.assertIn("local_exact_store_matches_proof_window_after_capture", review["blockers"])
        self.assertIn("local_exact_store_has_no_pending_refresh_after_capture", review["blockers"])
        checks = {check["name"]: check for check in review["checks"]}
        self.assertFalse(checks["local_exact_store_matches_proof_window_after_capture"]["passed"])
        self.assertFalse(checks["local_exact_store_has_no_pending_refresh_after_capture"]["passed"])

    def test_build_last_execution_review_reports_failed_fresh_scan_criteria(self):
        previous = {
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
            }
        }
        current = {
            "generated_at": "2026-05-21T14:15:00Z",
            "scan": {
                "candidate_count": 0,
                "quote_freshness_context": {"status": "stale_quote_blocked"},
                "fresh_scan_retest_plan": {"primary_probe_quote_age_excess_hours": 1.2},
            },
        }

        review = build_last_execution_review(previous, current)

        self.assertEqual(review["status"], "failed")
        self.assertEqual(
            review["blockers"],
            [
                "fresh_scan_candidate_count_above_zero",
                "quote_freshness_status_not_stale_quote_sensitive_or_blocked",
                "primary_probe_quote_age_excess_hours_at_or_below_zero",
            ],
        )
        self.assertFalse(review["previous_runbook_command_matches_contract"])
        self.assertFalse(review["ran_from_runbook_card"])
        self.assertEqual(review["ran_from_runbook_card_inference"], "no_previous_runbook_card")

    def test_build_lane_next_step_promotes_diagnostic_checkpoint_before_full_history(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "diagnostic_ready": True,
            },
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-22",
                "can_attempt_capture_now": False,
                "next_scheduled_capture": {"scheduled_utc": "2026-05-22T20:20:00Z"},
            },
            "verification_gate": {
                "verified": False,
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_automation_healthy": True,
                    "alpaca_opra_source_quality_usable": True,
                    "enough_exact_shared_quote_dates": False,
                    "readiness_ready_for_exact_replay": False,
                    "exact_replay_completed": False,
                    "live_scan_has_candidate": False,
                },
                "blockers": ["shared_quote_dates:2/100", "live_scan_candidates:0"],
            },
            "readiness": {"status": "partial", "blocker": "thin_required_history"},
            "replay": {"error": "Selected dates: 2.", "total_trades": 0},
            "diagnostic_replay": {
                "blockers": ["diagnostic_candidate_trades:0", "diagnostic_trades:0"],
                "next_action": "inspect_replay_signal_filters_after_next_capture",
            },
            "scan": {"candidate_count": 0},
        }

        summary = build_lane_next_step_summary(report)

        self.assertEqual(summary["phase"], "diagnostic_replay_checkpoint")
        self.assertEqual(summary["priority_action"], "inspect_replay_signal_filters_after_next_capture")
        self.assertEqual(summary["primary_blocker"], "diagnostic_candidate_trades:0")
        self.assertTrue(summary["diagnostic_ready"])
        self.assertFalse(summary["safe_to_tune_filters"])
        self.assertTrue(any("Diagnostic replay has enough" in item for item in summary["rationale"]))

    def test_build_lane_next_step_allows_tuning_after_exact_replay_exists(self):
        report = {
            "proof_window": {
                "current_shared_quote_dates": 100,
                "required_shared_quote_dates": 100,
            },
            "capture_action": {"status": "complete"},
            "verification_gate": {
                "verified": False,
                "gates": {
                    "alpaca_sip_opra_provider": True,
                    "alpaca_opra_source_filtered": True,
                    "capture_automation_healthy": True,
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": True,
                    "alpaca_opra_source_quality_usable": True,
                    "enough_exact_shared_quote_dates": True,
                    "readiness_ready_for_exact_replay": True,
                    "exact_replay_completed": True,
                    "exact_replay_has_trades": True,
                    "exact_replay_profit_factor_positive": False,
                    "exact_replay_total_return_positive": False,
                    "live_scan_has_candidate": True,
                },
                "blockers": ["profit_factor:0.8", "total_return_pct:-1.2"],
            },
            "readiness": {"status": "ready_for_exact_replay"},
            "replay": {"error": None, "total_trades": 12, "profit_factor": 0.8, "total_return_pct": -1.2},
            "scan": {"candidate_count": 1},
        }

        summary = build_lane_next_step_summary(report)

        self.assertEqual(summary["phase"], "profitability_tuning")
        self.assertEqual(summary["priority_action"], "tune_lane_using_exact_opra_replay_metrics")
        self.assertTrue(summary["safe_to_tune_filters"])

    def test_build_capture_action_summary_waits_for_next_market_close_when_current_target_captured(self):
        action = build_capture_action_summary(
            {
                "generated_at": "2026-05-21T03:15:55Z",
                "proof_window": {
                    "remaining_shared_quote_dates": 99,
                    "current_target_trade_date": "2026-05-20",
                    "current_target_captured": True,
                    "next_missing_capture_trade_date": "2026-05-21",
                    "missed_capture_trade_dates_since_latest_shared": [],
                },
                "capture": {"status": "skipped_existing_shared_date"},
                "automation_health": {
                    "healthy": True,
                    "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=20;BYSECOND=0",
                },
            }
        )

        self.assertEqual(action["status"], "waiting_for_next_market_close")
        self.assertEqual(action["next_action"], "wait_until_next_missing_date_is_capturable:2026-05-21")
        self.assertFalse(action["can_attempt_capture_now"])
        self.assertTrue(action["waiting_on_future_market_day"])
        self.assertEqual(action["capture_calendar"], "us_equity_market_days")
        self.assertEqual(action["holiday_calendar_source"], "NYSE/Nasdaq US equity market holiday rules")
        self.assertTrue(action["next_scheduled_capture"]["trade_date_is_market_day"])
        self.assertEqual(action["next_scheduled_capture"]["capture_calendar"], "us_equity_market_days")
        self.assertEqual(action["next_scheduled_capture"]["scheduled_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(action["next_scheduled_capture"]["timing_status"], "scheduled_future")
        self.assertGreater(action["next_scheduled_capture"]["seconds_until_scheduled"], 0)

    def test_build_capture_action_summary_flags_missed_capture_intervention(self):
        action = build_capture_action_summary(
            {
                "proof_window": {
                    "remaining_shared_quote_dates": 99,
                    "current_target_trade_date": "2026-05-20",
                    "current_target_captured": False,
                    "next_missing_capture_trade_date": "2026-05-20",
                    "missed_capture_trade_dates_since_latest_shared": ["2026-05-18", "2026-05-19"],
                },
                "capture": {"status": "skipped_by_request"},
                "automation_health": {"healthy": True},
            }
        )

        self.assertEqual(action["status"], "intervention_required_missed_capture_dates")
        self.assertEqual(
            action["next_action"],
            "record_missed_capture_dates_keep_goal_incomplete_and_resume_forward_capture",
        )
        self.assertTrue(action["can_attempt_capture_now"])
        self.assertFalse(action["waiting_on_future_market_day"])
        self.assertEqual(
            action["missed_capture_policy"],
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
        )
        self.assertEqual(
            action["missed_capture_recovery_action"],
            "resume_forward_capture_from_next_missing_trade_date_without_counting_missed_dates",
        )
        self.assertFalse(action["missed_capture_dates_recoverable"])

    def test_build_capture_action_summary_flags_incomplete_capture_universe(self):
        action = build_capture_action_summary(
            {
                "proof_window": {
                    "remaining_shared_quote_dates": 99,
                    "current_target_trade_date": "2026-05-20",
                    "current_target_captured": True,
                    "next_missing_capture_trade_date": "2026-05-21",
                    "missed_capture_trade_dates_since_latest_shared": [],
                },
                "capture": {
                    "status": "no_rows_captured",
                    "target_capture_complete": False,
                    "missing_target_date_symbols_after": ["ALB", "MP"],
                },
                "automation_health": {"healthy": True},
            }
        )

        self.assertEqual(action["status"], "capture_incomplete_for_target")
        self.assertEqual(action["next_action"], "recapture_missing_symbols_for_target:2026-05-20:ALB,MP")
        self.assertTrue(action["can_attempt_capture_now"])
        self.assertFalse(action["waiting_on_future_market_day"])
        self.assertFalse(action["capture_target_complete"])
        self.assertEqual(action["capture_missing_target_symbols_after"], ["ALB", "MP"])

    def test_scheduled_capture_time_for_trade_date_uses_rrule_time(self):
        scheduled = scheduled_capture_time_for_trade_date(
            "2026-05-21",
            rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=20;BYSECOND=0",
            timezone_name="America/Denver",
        )

        self.assertIsNotNone(scheduled)
        self.assertEqual(scheduled["timezone"], "America/Denver")
        self.assertEqual(scheduled["trade_date"], "2026-05-21")
        self.assertTrue(scheduled["trade_date_is_market_day"])
        self.assertEqual(scheduled["capture_calendar"], "us_equity_market_days")
        self.assertEqual(scheduled["scheduled_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(scheduled["scheduled_utc"], "2026-05-21T20:20:00Z")
        self.assertEqual(scheduled["selected_time_policy"], "latest_intraday_time")

    def test_scheduled_capture_time_for_trade_date_blocks_market_holidays(self):
        scheduled = scheduled_capture_time_for_trade_date(
            "2026-05-25",
            rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=20;BYSECOND=0",
            timezone_name="America/Denver",
        )

        self.assertEqual(scheduled["trade_date"], "2026-05-25")
        self.assertEqual(scheduled["capture_calendar"], "us_equity_market_days")
        self.assertFalse(scheduled["trade_date_is_market_day"])
        self.assertEqual(scheduled["schedule_blocker"], "target_trade_date_is_not_us_equity_market_day")
        self.assertNotIn("scheduled_utc", scheduled)

    def test_scheduled_capture_time_for_trade_date_uses_latest_time_from_combined_rrule(self):
        scheduled = scheduled_capture_time_for_trade_date(
            "2026-05-21",
            rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,14;BYMINUTE=10,20;BYSECOND=0",
            timezone_name="America/Denver",
        )

        self.assertIsNotNone(scheduled)
        self.assertEqual(scheduled["scheduled_local"], "2026-05-21T14:20:00-06:00")
        self.assertEqual(scheduled["scheduled_utc"], "2026-05-21T20:20:00Z")

    def test_annotate_scheduled_capture_timing_marks_overdue_after_grace_window(self):
        annotated = annotate_scheduled_capture_timing(
            {
                "scheduled_utc": "2026-05-21T20:20:00Z",
                "scheduled_local": "2026-05-21T14:20:00-06:00",
            },
            now_utc=datetime(2026, 5, 21, 23, 0, tzinfo=UTC),
            overdue_grace_minutes=120,
        )

        self.assertEqual(annotated["timing_status"], "scheduled_overdue")
        self.assertLess(annotated["seconds_until_scheduled"], 0)
        self.assertEqual(annotated["hours_until_scheduled"], -2.67)

    def test_next_fresh_scan_time_uses_entry_quote_minute(self):
        scheduled = next_fresh_scan_time(
            now_utc=datetime(2026, 5, 21, 4, 58, tzinfo=UTC),
        )

        self.assertEqual(scheduled["scheduled_local"], "2026-05-21T10:10:00-04:00")
        self.assertEqual(scheduled["scheduled_market_local"], "2026-05-21T10:10:00-04:00")
        self.assertEqual(scheduled["scheduled_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(scheduled["scheduled_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(scheduled["market_timezone"], "America/New_York")
        self.assertEqual(scheduled["user_timezone"], "America/Denver")
        self.assertEqual(scheduled["scan_calendar"], "us_equity_market_days")
        self.assertEqual(scheduled["holiday_calendar_source"], "NYSE/Nasdaq US equity market holiday rules")
        self.assertTrue(scheduled["scheduled_trade_date_is_market_day"])
        self.assertEqual(scheduled["status"], "fresh_scan_future")
        self.assertFalse(scheduled["can_attempt_scan_now"])
        self.assertEqual(scheduled["window_end_utc"], "2026-05-21T20:00:00Z")
        self.assertEqual(scheduled["window_end_user_local"], "2026-05-21T14:00:00-06:00")
        self.assertEqual(scheduled["entry_quote_minute_et"], 610)

    def test_next_fresh_scan_time_marks_open_window_due(self):
        scheduled = next_fresh_scan_time(
            now_utc=datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(scheduled["scheduled_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(scheduled["window_end_utc"], "2026-05-21T20:00:00Z")
        self.assertEqual(scheduled["scheduled_user_local"], "2026-05-21T08:10:00-06:00")
        self.assertEqual(scheduled["status"], "fresh_scan_due_window")
        self.assertTrue(scheduled["can_attempt_scan_now"])
        self.assertEqual(scheduled["seconds_until_scheduled"], 0)

    def test_next_fresh_scan_time_rolls_past_weekend_and_market_holiday(self):
        scheduled = next_fresh_scan_time(
            now_utc=datetime(2026, 5, 22, 21, 0, tzinfo=UTC),
        )

        self.assertEqual(scheduled["scheduled_local"], "2026-05-26T10:10:00-04:00")
        self.assertEqual(scheduled["scheduled_user_local"], "2026-05-26T08:10:00-06:00")
        self.assertEqual(scheduled["scheduled_utc"], "2026-05-26T14:10:00Z")
        self.assertEqual(scheduled["scan_calendar"], "us_equity_market_days")
        self.assertTrue(scheduled["scheduled_trade_date_is_market_day"])
        self.assertEqual(scheduled["status"], "fresh_scan_future")

    def test_render_markdown_includes_key_progress_fields(self):
        report = {
            "generated_at": "2026-05-21T01:00:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "next_blocker": "shared_quote_dates:2/100",
            "capture_action": {
                "status": "waiting_for_next_market_close",
                "next_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "can_attempt_capture_now": False,
                "waiting_on_future_market_day": True,
                "next_scheduled_capture": {
                    "timing_status": "scheduled_future",
                    "hours_until_scheduled": 17.07,
                    "scheduled_local": "2026-05-21T14:20:00-06:00",
                    "scheduled_utc": "2026-05-21T20:20:00Z",
                },
            },
            "verification_gate": {
                "status": "not_verified",
                "verified": False,
                "blockers": ["shared_quote_dates:2/100"],
                "gates": {
                    "capture_scope_full_scan_universe": True,
                    "capture_target_complete": True,
                    "proof_scan_universe_aligned": False,
                },
                "source_quality_status": "usable_quotes_waiting_for_history_depth",
                "replay_profit_factor": None,
                "replay_total_return_pct": None,
                "live_scan_candidate_count": 0,
            },
            "automation_health": {
                "healthy": True,
                "status": "ACTIVE",
                "kind": "heartbeat",
                "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=20;BYSECOND=0",
                "scheduled_intraday_times": ["08:10:00", "14:20:00"],
                "covers_fresh_opra_scan": True,
                "covers_post_close_capture": True,
                "schedule_exact_required_times": True,
                "prompt_mentions_proof_source_isolation_contract": True,
                "prompt_mentions_capture_continuity_contract": True,
                "unexpected_intraday_times": [],
            },
            "proof_source_audit": {
                "decision": "only_alpaca_opra_daily_snapshot_counts_for_exact_profitability_proof",
                "trusted_only": True,
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "source_labels_seen": ["alpaca_opra_daily_snapshot", "thetadata_free_eod"],
                "alpaca_like_source_labels_seen": ["alpaca_opra_daily_snapshot"],
                "non_proof_alpaca_like_source_labels": [],
                "proof_source_shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                "all_required_symbols_have_proof_source_data": True,
                "all_trusted_shared_quote_dates": {"count": 2, "first": "2026-05-15", "last": "2026-05-20"},
                "excluded_trusted_shared_quote_dates": {"count": 1, "first": "2026-05-15", "last": "2026-05-15"},
                "excluded_trusted_source_labels": ["thetadata_free_eod"],
                "per_source_shared_quote_dates": [
                    {
                        "source_label": "alpaca_opra_daily_snapshot",
                        "used_for_exact_profitability_proof": True,
                        "shared_quote_dates": {"count": 1, "first": "2026-05-20", "last": "2026-05-20"},
                    },
                    {
                        "source_label": "thetadata_free_eod",
                        "used_for_exact_profitability_proof": False,
                        "shared_quote_dates": {"count": 1, "first": "2026-05-15", "last": "2026-05-15"},
                    },
                ],
            },
            "commodity_research_lab": {
                "status": "commodity_research_only",
                "used_for_verification": False,
                "verification_note": "research_lab_never_satisfies_exact_alpaca_opra_bid_ask_profitability_gate",
                "run_at_utc": "2026-05-21T06:00:10Z",
                "date_from": "2026-05-01",
                "date_to": "2026-05-20",
                "option_research_fallback": "alpaca_opra_historical_bars_no_bidask",
                "promotion_trade_basis": "exact_bid_ask only",
                "total_bar_fallback_trades": 9,
                "total_exact_bid_ask_trades": 0,
                "positive_bar_only_lanes": [],
                "next_action": "do_not_promote_bar_only_research_accumulate_exact_alpaca_opra_bid_ask_dates",
                "lane_summaries": [
                    {
                        "lane": "bullish",
                        "all_trade_count": 6,
                        "bar_fallback_count": 6,
                        "exact_bid_ask_trade_count": 0,
                        "all_profit_factor": 0.0,
                        "all_avg_pnl_pct": -74.83,
                    }
                ],
            },
            "scan_proof_universe_alignment": {
                "status": "scan_universe_exceeds_exact_proof_universe",
                "proof_universe_count": 9,
                "scan_universe_count": 24,
                "scan_symbols_without_exact_proof": ["ALB", "AA"],
                "candidate_symbols": [],
                "candidate_symbols_outside_exact_proof": [],
                "live_scan_candidates_all_inside_exact_proof": False,
                "blocker_symbols_outside_exact_proof": ["ALB", "AA"],
                "next_action": "expand_exact_alpaca_opra_capture_to_scan_universe_or_treat_outside_symbols_as_research_only",
            },
            "source_quality": {
                "status": "usable_quotes_waiting_for_history_depth",
                "source_labels_required": ["alpaca_opra_daily_snapshot"],
                "total_quote_rows": 30,
                "available_required_underlying_count": 2,
                "required_underlying_count": 2,
                "min_executable_quote_pct": 95.5,
                "total_missing_bid_ask_rows": 1,
                "total_crossed_quote_rows": 0,
                "lowest_quote_row_symbols": [{"symbol": "FCX", "quote_rows": 10}],
            },
            "lane_next_step": {
                "phase": "capture_wait",
                "priority_action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                "primary_blocker": "shared_quote_dates:2/100",
                "safe_to_tune_filters": False,
                "next_timed_event_kind": "fresh_opra_scan",
                "next_timed_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                "next_timed_event_local": "2026-05-21T10:10:00-04:00",
                "next_timed_event_utc": "2026-05-21T14:10:00Z",
                "diagnostic_replay_next_action": "accumulate_replay_simulation_shared_opra_dates",
                "rationale": ["Full verification is blocked until the exact Alpaca OPRA shared-date gate passes."],
            },
            "lane_iteration_plan": {
                "status": "active",
                "priority_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                "safe_to_tune_filters": False,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "diagnostic_required_shared_quote_dates": 88,
                "steps": [
                    {
                        "step": "fresh_opra_live_scan",
                        "status": "scheduled",
                        "action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T14:10:00Z",
                        "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                    },
                    {
                        "step": "post_close_full_universe_capture",
                        "status": "scheduled",
                        "action": "wait_until_next_missing_date_is_capturable:2026-05-21",
                        "scheduled_utc": "2026-05-21T20:20:00Z",
                        "actionable_now": False,
                        "not_before_utc": "2026-05-21T20:20:00Z",
                        "premature_run_guard": "target_date_capturable_guard",
                        "command": [
                            "python",
                            "scripts/run_ai_commodity_opra_progress.py",
                            "--force-capture",
                            "--target-date",
                            "2026-05-21",
                        ],
                    },
                    {
                        "step": "filter_tuning",
                        "status": "locked",
                        "action": "hold_filters_until_exact_replay_is_ready",
                    },
                ],
            },
            "next_execution_contract": {
                "status": "waiting_until_not_before",
                "selected_step": "fresh_opra_live_scan",
                "matches_next_timed_event": True,
                "actionable_now": False,
                "not_before_utc": "2026-05-21T14:10:00Z",
                "command_display": "python scripts/run_ai_commodity_opra_progress.py --skip-capture",
                "premature_run_guard": None,
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "last_execution_review": {
                "status": "not_due_yet",
                "previous_selected_step": "fresh_opra_live_scan",
                "not_before_utc": "2026-05-21T14:10:00Z",
                "command": ["python", "scripts/run_ai_commodity_opra_progress.py", "--skip-capture"],
                "checks": [],
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
            },
            "previous_proof_event_outcome": {
                "status": "not_due_yet",
                "event_kind": "fresh_opra_live_candidate_scan",
                "target_goal_requirement": "live_scan_has_verifiable_candidate",
                "advanced_goal_requirement": False,
                "material_progress": False,
                "checks": [],
                "blockers": ["waiting_until_not_before:2026-05-21T14:10:00Z"],
                "outcome_detail": {},
            },
                "progress_delta": {
                    "previous_report_found": True,
                    "run_classification": "improved",
                    "no_progress_reason": None,
                    "non_material_flags": [],
                    "scan_materiality_thresholds": {"scan_liquidity_gate_distance_delta_abs_min": 0.25},
                    "shared_quote_dates_delta": 1.0,
                "remaining_shared_quote_dates_delta": -1.0,
                "scan_candidate_count_delta": 0.0,
                "scan_ev_shortfall_delta": -2.0,
                "scan_candidate_heuristic_ev_delta": 2.0,
                "scan_liquidity_gate_distance_delta": -5.0,
                "next_blocker_before": "shared_quote_dates:1/100",
                "next_blocker_after": "shared_quote_dates:2/100",
                "verification_status_before": "not_verified",
                "verification_status_after": "not_verified",
                "verification_gates_newly_passed": ["enough_exact_shared_quote_dates"],
                "verification_gates_regressed": [],
                "verification_gates_still_blocked": ["exact_replay_completed"],
                "source_quality_status_before": "missing_required_underlyings",
                "source_quality_status_after": "usable_quotes_waiting_for_history_depth",
                "source_quality_total_quote_rows_delta": 20.0,
                "source_quality_min_executable_pct_delta": 15.5,
                "source_quality_missing_bid_ask_rows_delta": -2.0,
                "proof_source_label_before": "thetadata_free_eod",
                "proof_source_label_after": "alpaca_opra_daily_snapshot",
                "proof_source_label_changed": True,
                "proof_source_trusted_only_before": False,
                "proof_source_trusted_only_after": True,
                "proof_source_trusted_only_changed": True,
                "proof_source_all_required_symbols_available_before": False,
                "proof_source_all_required_symbols_available_after": True,
                "proof_source_all_required_symbols_available_changed": True,
                "improvement_flags": [
                    "source_filtered_shared_quote_dates_increased",
                    "proof_source_switched_to_alpaca_opra_daily_snapshot",
                ],
                "regression_flags": [],
            },
            "proof_window": {
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates": 100,
                "remaining_shared_quote_dates": 98,
                "diagnostic_required_shared_quote_dates": 88,
                "diagnostic_remaining_shared_quote_dates": 86,
                "diagnostic_ready": False,
                "diagnostic_requirement_basis": "first_replay_simulation_day",
                "diagnostic_replay_start_index": 57,
                "diagnostic_replay_exit_buffer_days": 5,
                "diagnostic_replay_max_dte": 25,
                "diagnostic_replay_min_simulation_shared_quote_dates": 88,
                "approx_diagnostic_ready_date_if_one_capture_per_weekday": "2026-09-17",
                "next_missing_capture_trade_date": "2026-05-21",
                "capture_health_status": "on_track_current_target_captured",
                "approx_completion_date_if_one_capture_per_weekday": "2026-10-06",
            },
            "capture": {
                "status": "skipped_existing_shared_date",
                "target_date": "2026-05-20",
                "scope": "ai_commodity_scan_universe",
                "symbol_count": 24,
                "target_capture_complete": True,
                "missing_target_date_symbols_after": [],
            },
            "readiness": {
                "status": "partial",
                "blocker": "thin_required_history",
                "shared_required_quote_dates": {"count": 2},
                "minimums": {"min_shared_quote_dates": 100},
            },
            "replay": {"error": "Selected dates: 2"},
            "diagnostic_replay": {
                "status": "skipped",
                "diagnostic_only": True,
                "can_verify_profitability": False,
                "current_shared_quote_dates": 2,
                "required_shared_quote_dates_for_verification": 100,
                "diagnostic_min_imported_calendar_dates": 88,
                "blockers": ["insufficient_replay_simulation_quote_dates"],
                "next_action": "accumulate_replay_simulation_shared_opra_dates",
                "total_trades": 0,
                "profit_factor": 0.0,
                "total_return_pct": None,
                "quote_coverage_pct": 0.0,
                "verification_note": "diagnostic_replay_does_not_satisfy_full_shared_quote_date_gate",
            },
            "scan": {
                "candidate_count": 0,
                "returned_count": 0,
                "scan_funnel": {"drop_counts": {"option_liquidity": 9, "tech_score": 8}},
                "drop_diagnostics": [
                    {
                        "drop_key": "option_liquidity",
                        "count": 9,
                        "example_symbols": ["AA", "ALB"],
                        "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                    }
                ],
                "fresh_scan_retest_plan": {
                    "status": "scheduled",
                    "next_action": "wait_until_fresh_opra_scan_window",
                    "scheduled_utc": "2026-05-21T14:10:00Z",
                    "window_end_utc": "2026-05-21T20:00:00Z",
                    "primary_probe_symbol": "FCX",
                    "primary_probe_reasons": ["stale_leg_quote"],
                    "primary_probe_quote_age_excess_hours": 1.85,
                    "quote_age_only_blocker_symbols": ["FCX"],
                    "structural_liquidity_blocker_symbols": ["ALB"],
                    "success_criteria": ["fresh_scan_candidate_count_above_zero"],
                    "if_still_zero_candidates": ["rank_remaining_drop_counts"],
                },
            },
        }

        markdown = render_markdown(report)

        self.assertIn("alpaca:sip:opra", markdown)
        self.assertIn("shared_quote_dates:2/100", markdown)
        self.assertIn("Remaining capture dates: `98`", markdown)
        self.assertIn("Diagnostic replay window: `2` / `88` shared dates", markdown)
        self.assertIn("Remaining diagnostic capture dates: `86`", markdown)
        self.assertIn("Diagnostic replay basis: `first_replay_simulation_day`", markdown)
        self.assertIn("Diagnostic replay runway: `start_index=57, max_dte=25, exit_buffer=5`", markdown)
        self.assertIn("Approx diagnostic ready date (legacy alias, market-day aware): `2026-09-17`", markdown)
        self.assertIn("Next missing capture date: `2026-05-21`", markdown)
        self.assertIn("Capture health: `on_track_current_target_captured`", markdown)
        self.assertIn("## Verification Gate", markdown)
        self.assertIn("Verified: `False`", markdown)
        self.assertIn("## Exact Profitability Blocker Review", markdown)
        self.assertIn("Current primary blocker:", markdown)
        self.assertIn("History runway:", markdown)
        self.assertIn("Next history capture:", markdown)
        self.assertIn("### Exact Profitability Ordered Unblock Plan", markdown)
        self.assertIn("command `python scripts/run_ai_commodity_opra_progress.py", markdown)
        self.assertIn("role `guarded_forward_alpaca_opra_capture`", markdown)
        self.assertIn("## Full Universe Hard Gates", markdown)
        self.assertIn("Capture scope full scan universe: `True`", markdown)
        self.assertIn("Capture target complete: `True`", markdown)
        self.assertIn("Proof/scan universe aligned: `False`", markdown)
        self.assertIn("Proof universe count: `9`", markdown)
        self.assertIn("Scan universe count: `24`", markdown)
        self.assertIn("Scan symbols without exact proof: `['ALB', 'AA']`", markdown)
        self.assertIn("## Lane Next Step", markdown)
        self.assertIn("Phase: `capture_wait`", markdown)
        self.assertIn("Priority action: `wait_until_next_missing_date_is_capturable:2026-05-21`", markdown)
        self.assertIn("Next timed event: `fresh_opra_scan`", markdown)
        self.assertIn(
            "Next timed action: `rerun_live_scan_during_fresh_opra_window_before_filter_changes`",
            markdown,
        )
        self.assertIn("Next timed event UTC: `2026-05-21T14:10:00Z`", markdown)
        self.assertIn("Safe to tune filters: `False`", markdown)
        self.assertIn("## Lane Next Step Plan", markdown)
        self.assertIn("Filter policy: `locked_until_exact_alpaca_opra_replay_profitability_gate_can_measure_changes`", markdown)
        self.assertIn("Post-run evidence refresh command:", markdown)
        self.assertIn("Post-run replay command when unlocked:", markdown)
        self.assertIn("Post-run profitability handoff:", markdown)
        self.assertIn("## Run-Next Guard Summary", markdown)
        self.assertIn("Run command now: `False`", markdown)
        self.assertIn("Reason: `waiting_until_not_before:2026-05-21T08:10:00-06:00`", markdown)
        self.assertIn("Command when allowed: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn("## Next Execution Contract", markdown)
        self.assertIn("Selected step: `fresh_opra_live_scan`", markdown)
        self.assertIn("Matches next timed event: `True`", markdown)
        self.assertIn("Actionable now: `False`", markdown)
        self.assertIn("Command: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn("Blockers: `['waiting_until_not_before:2026-05-21T14:10:00Z']`", markdown)
        self.assertIn("## Next Execution Preflight", markdown)
        self.assertIn("Clock-only blocked:", markdown)
        self.assertIn("Proof-source isolation required:", markdown)
        self.assertIn("Proof-source isolation status:", markdown)
        self.assertIn("Capture continuity required:", markdown)
        self.assertIn("Full universe hard gates required:", markdown)
        self.assertIn("Capture scope full scan universe:", markdown)
        self.assertIn("Proof/scan universe aligned:", markdown)
        self.assertIn("Capture command contract required:", markdown)
        self.assertIn("Capture command target date:", markdown)
        self.assertIn("Expected capture target date:", markdown)
        self.assertIn("Failed checks:", markdown)
        self.assertIn("## Exact Capture Post-Run Evaluation", markdown)
        self.assertIn("Post-capture evidence refresh command:", markdown)
        self.assertIn("Post-capture replay command when unlocked:", markdown)
        self.assertIn("Post-capture profitability handoff:", markdown)
        self.assertIn("Next capture evidence state:", markdown)
        self.assertIn("Stale success guard for next target:", markdown)
        self.assertIn("### Post-Capture Evidence Contract", markdown)
        self.assertIn("Next capture target observed:", markdown)
        self.assertIn("Required before run:", markdown)
        self.assertIn("Fields to compare after run:", markdown)
        self.assertIn("Material progress if:", markdown)
        self.assertIn("proof_window.current_shared_quote_dates >=", markdown)
        self.assertIn("Readiness checklist status:", markdown)
        self.assertIn("Ready to run full exact replay:", markdown)
        self.assertIn("Readiness checklist next command:", markdown)
        self.assertIn("## Last Execution Review", markdown)
        self.assertIn("Previous step: `fresh_opra_live_scan`", markdown)
        self.assertIn("Previous not-before UTC: `2026-05-21T14:10:00Z`", markdown)
        self.assertIn("Checks: `[]`", markdown)
        self.assertIn("## Previous Proof Event Outcome", markdown)
        self.assertIn("Event kind: `fresh_opra_live_candidate_scan`", markdown)
        self.assertIn("Target requirement: `live_scan_has_verifiable_candidate`", markdown)
        self.assertIn("Advanced goal requirement: `False`", markdown)
        self.assertIn("Material progress: `False`", markdown)
        self.assertIn("## Lane Iteration Plan", markdown)
        self.assertIn("Status: `active`", markdown)
        self.assertIn("Shared dates: `2` / `100`", markdown)
        self.assertIn("Diagnostic required shared dates: `88`", markdown)
        self.assertIn(
            "fresh_opra_live_scan: `scheduled` actionable now `False` action `rerun_live_scan_during_fresh_opra_window_before_filter_changes` scheduled UTC `2026-05-21T14:10:00Z`",
            markdown,
        )
        self.assertIn("not before UTC `2026-05-21T14:10:00Z`", markdown)
        self.assertIn("command `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn(
            "post_close_full_universe_capture: `scheduled` actionable now `False` action `wait_until_next_missing_date_is_capturable:2026-05-21` scheduled UTC `2026-05-21T20:20:00Z`",
            markdown,
        )
        self.assertIn("not before UTC `2026-05-21T20:20:00Z`", markdown)
        self.assertIn(
            "command `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21`",
            markdown,
        )
        self.assertIn(
            "filter_tuning: `locked` actionable now `None` action `hold_filters_until_exact_replay_is_ready`",
            markdown,
        )
        self.assertIn("Source quality status: `usable_quotes_waiting_for_history_depth`", markdown)
        self.assertIn("shared_quote_dates:2/100", markdown)
        self.assertIn("## Automation", markdown)
        self.assertIn("Schedule exact required times: `True`", markdown)
        self.assertIn("Prompt mentions proof-source isolation contract: `True`", markdown)
        self.assertIn("Prompt mentions capture continuity contract: `True`", markdown)
        self.assertIn("Unexpected intraday times: `[]`", markdown)
        self.assertIn("## Source Quality", markdown)
        self.assertIn("Source labels: `['alpaca_opra_daily_snapshot']`", markdown)
        self.assertIn("Min executable quote pct: `95.5`", markdown)
        self.assertIn("Healthy: `True`", markdown)
        self.assertIn("## Proof Source Audit", markdown)
        self.assertIn("only_alpaca_opra_daily_snapshot_counts_for_exact_profitability_proof", markdown)
        self.assertIn("Excluded trusted source labels: `['thetadata_free_eod']`", markdown)
        self.assertIn("## Proof Source Isolation Contract", markdown)
        self.assertIn("Status: `isolated_to_alpaca_opra_proof_source`", markdown)
        self.assertIn("Exact proof source labels: `['alpaca_opra_daily_snapshot']`", markdown)
        self.assertIn("Research-only source labels: `['thetadata_free_eod']`", markdown)
        self.assertIn("Non-proof sources with shared dates: `['thetadata_free_eod']`", markdown)
        self.assertIn("Top-level shared dates match proof source: `True`", markdown)
        self.assertIn("Next action: `continue_using_alpaca_opra_proof_source`", markdown)
        self.assertIn("## Exact Capture Import Health", markdown)
        self.assertIn("Success criteria for next capture:", markdown)
        self.assertIn("Failure signals after next capture:", markdown)
        self.assertIn("## Exact History Acquisition Plan", markdown)
        self.assertIn("Status: `forward_capture_required`", markdown)
        self.assertIn("Proof source label: `alpaca_opra_daily_snapshot`", markdown)
        self.assertIn("Shared dates: `2` / `100`", markdown)
        self.assertIn("Remaining shared dates: `98`", markdown)
        self.assertIn("Next capture trade date: `2026-05-21`", markdown)
        self.assertIn("Next capture not-before runbook local: `2026-05-21T14:20:00-06:00`", markdown)
        self.assertIn(
            "Next capture command: `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-21`",
            markdown,
        )
        self.assertIn("Capture continuity status:", markdown)
        self.assertIn("Missed capture dates:", markdown)
        self.assertIn(
            "missed_historical_opra_bbo_dates_cannot_be_backfilled_from_bars_trades_or_latest_snapshots",
            markdown,
        )
        self.assertIn("Continuity next action:", markdown)
        self.assertIn("### Forward Capture Queue Summary", markdown)
        self.assertIn(
            "1. `2026-05-21` not before `2026-05-21T14:20:00-06:00`",
            markdown,
        )
        self.assertIn("Forward capture queue:", markdown)
        self.assertIn("'trade_date': '2026-05-21'", markdown)
        self.assertIn("--target-date 2026-05-22", markdown)
        self.assertIn("Unlock milestones:", markdown)
        self.assertIn("'unlock_trade_date': '2026-09-23'", markdown)
        self.assertIn("--target-date 2026-10-09", markdown)
        self.assertIn("Backfill status: `forward_daily_snapshot_capture_required`", markdown)
        self.assertIn("Can accelerate with existing sources: `False`", markdown)
        self.assertIn("## Exact History Backfill Capability Audit", markdown)
        self.assertIn("Status: `forward_capture_required_for_exact_bid_ask_history`", markdown)
        self.assertIn("Can accelerate exact history: `False`", markdown)
        self.assertIn("Acceleration decision:", markdown)
        self.assertIn("do_not_accelerate_exact_history_from_alpaca_historical_bars_or_trades", markdown)
        self.assertIn("Official endpoint review checked at: `2026-05-22`", markdown)
        self.assertIn("Missing capability: `historical_option_quote_bbo_method_for_contracts`", markdown)
        self.assertIn("Historical option quote endpoint found: `False`", markdown)
        self.assertIn("Historical bars exact-proof eligible: `False`", markdown)
        self.assertIn("Historical trades exact-proof eligible: `False`", markdown)
        self.assertIn("Latest quote/snapshot forward capture eligible: `True`", markdown)
        self.assertIn("Official endpoint review:", markdown)
        self.assertIn("latest_option_quotes", markdown)
        self.assertIn("optionlatestquotes", markdown)
        self.assertIn("Official reference index review:", markdown)
        self.assertIn("official_reference_index_lists_no_historical_option_quote_bbo_endpoint", markdown)
        self.assertIn("official_alpaca_rest_reference_index_lists_historical_bars_and_trades", markdown)
        self.assertIn("Next action: `continue_forward_daily_alpaca_opra_snapshot_capture`", markdown)
        self.assertIn("## Commodity Research Lab", markdown)
        self.assertIn("Status: `commodity_research_only`", markdown)
        self.assertIn("Total bar-only trades: `9`", markdown)
        self.assertIn("Total exact bid/ask trades: `0`", markdown)
        self.assertIn("## Scan Proof Universe Alignment", markdown)
        self.assertIn("Proof universe count: `9`", markdown)
        self.assertIn("Scan universe count: `24`", markdown)
        self.assertIn("Blocker symbols outside exact proof: `['ALB', 'AA']`", markdown)
        self.assertIn("## Progress Delta", markdown)
        self.assertIn("Run classification: `improved`", markdown)
        self.assertIn("Shared quote dates delta: `1.0`", markdown)
        self.assertIn("Scan EV shortfall delta: `-2.0`", markdown)
        self.assertIn("Scan liquidity gate distance delta: `-5.0`", markdown)
        self.assertIn("Verification gates newly passed: `['enough_exact_shared_quote_dates']`", markdown)
        self.assertIn("Verification gates still blocked: `['exact_replay_completed']`", markdown)
        self.assertIn("Source quality status after: `usable_quotes_waiting_for_history_depth`", markdown)
        self.assertIn("Source quality quote rows delta: `20.0`", markdown)
        self.assertIn("Source quality missing bid/ask rows delta: `-2.0`", markdown)
        self.assertIn("Proof source label before/after: `thetadata_free_eod` / `alpaca_opra_daily_snapshot`", markdown)
        self.assertIn("Proof source trusted only before/after: `False` / `True`", markdown)
        self.assertIn("Proof source required symbols before/after: `False` / `True`", markdown)
        self.assertIn("source_filtered_shared_quote_dates_increased", markdown)
        self.assertIn("proof_source_switched_to_alpaca_opra_daily_snapshot", markdown)
        self.assertIn("Non-material flags: `[]`", markdown)
        self.assertIn("Scan materiality thresholds:", markdown)
        self.assertIn("Read-only watchlist distance deltas:", markdown)
        self.assertIn("Read-only watchlist material improvement count:", markdown)
        self.assertIn("Read-only watchlist symbols added:", markdown)
        self.assertIn("## Iteration Ledger", markdown)
        self.assertIn("Evidence basis: `alpaca_opra_current_report_vs_previous_latest`", markdown)
        self.assertIn("Proof source: `alpaca_opra_daily_snapshot`", markdown)
        self.assertIn("Proof source integrity:", markdown)
        self.assertIn("'all_required_symbols_available': True", markdown)
        self.assertIn("Capture debt:", markdown)
        self.assertIn("Material deltas:", markdown)
        self.assertIn("Read-only watchlist progress:", markdown)
        self.assertIn("'remaining_shared_quote_dates': 98", markdown)
        self.assertIn("Filter policy: `locked_until_exact_alpaca_opra_replay_is_ready`", markdown)
        self.assertIn(
            "Next evidence action: `wait_until_next_missing_date_is_capturable:2026-05-21`",
            markdown,
        )
        self.assertIn("Next execution status: `waiting_until_not_before`", markdown)
        self.assertIn("Next not-before UTC: `2026-05-21T14:10:00Z`", markdown)
        self.assertIn("Next command: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn("## Goal Completion Audit", markdown)
        self.assertIn("### Goal Completion Requirement Ladder", markdown)
        self.assertIn("has_required_exact_alpaca_opra_history_depth", markdown)
        self.assertIn("## Goal Completion Evidence Plan", markdown)
        self.assertIn("Next evidence command role:", markdown)
        self.assertIn("role `fresh_live_candidate_scan_evidence`", markdown)
        self.assertIn("blocked until `has_required_exact_alpaca_opra_history_depth`", markdown)
        self.assertIn("## Goal Completion Verification Contract", markdown)
        self.assertIn("### Goal Completion Verification Requirements", markdown)
        self.assertNotIn("- Requirements: `[{'requirement':", markdown)
        self.assertIn("## Next Proof Event Checkpoint", markdown)
        self.assertIn("Event kind: `fresh_opra_live_candidate_scan`", markdown)
        self.assertIn("Target requirement: `live_scan_has_verifiable_candidate`", markdown)
        self.assertIn("Command: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`", markdown)
        self.assertIn("Not before runbook local: `2026-05-21T08:10:00-06:00`", markdown)
        self.assertIn("Material progress if: `['scan.candidate_count > 0'", markdown)
        self.assertIn("Fields to compare after run: `['scan.candidate_count'", markdown)
        self.assertIn("## Fresh Scan Iteration Decision", markdown)
        self.assertIn("Status: `fresh_scan_zero_candidates_structural_review`", markdown)
        self.assertIn("Branch: `structural_blocker_branch`", markdown)
        self.assertIn(
            "Next action: `rank_remaining_drop_counts_without_relaxing_production_filters`",
            markdown,
        )
        self.assertIn("Safe to tune filters: `False`", markdown)
        self.assertIn("Fresh scan outcome matrix:", markdown)
        self.assertIn("can_unblock_if_candidate_is_inside_exact_proof_universe", markdown)
        self.assertIn("Selected outcome effect: `remains_blocked_records_raw_scan_drop_reasons`", markdown)
        self.assertIn(
            "Selected outcome next command: `python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest`",
            markdown,
        )
        self.assertIn("## Live Candidate Recovery Plan", markdown)
        self.assertIn("Target requirement: `live_scan_has_verifiable_candidate`", markdown)
        self.assertIn("Next command role:", markdown)
        self.assertIn("History unlock command:", markdown)
        self.assertIn(
            "Live candidate scan evidence command: `python scripts/run_ai_commodity_opra_progress.py --skip-capture`",
            markdown,
        )
        self.assertIn(
            "Read-only review command: `python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest`",
            markdown,
        )
        self.assertIn("Command roles:", markdown)
        self.assertIn("Safe to tune production filters: `False`", markdown)
        self.assertIn("Read-only recovery queue count:", markdown)
        self.assertIn("First read-only review:", markdown)
        self.assertIn("Read-only recovery priority order:", markdown)
        self.assertIn("Read-only recovery watchlist:", markdown)
        self.assertIn("Read-only material progress if:", markdown)
        self.assertIn("future_fresh_alpaca_opra_scan.candidate_count > 0", markdown)
        self.assertIn("Read-only evidence fields:", markdown)
        self.assertIn("## Post Fresh Scan Research Backlog", markdown)
        self.assertIn("Production filter policy: `locked_until_exact_alpaca_opra_replay_is_ready`", markdown)
        self.assertIn("Safe to tune filters now: `False`", markdown)
        self.assertIn("Variant unlock status:", markdown)
        self.assertIn("Variant current primary gate:", markdown)
        self.assertIn("Variant history runway:", markdown)
        self.assertIn("Variant next capture:", markdown)
        self.assertIn("Variant diagnostic unlock:", markdown)
        self.assertIn("Variant full replay unlock:", markdown)
        self.assertIn("### Deferred Variant Gate Unlock Map", markdown)
        self.assertIn("Deferred variant recipe audit status:", markdown)
        self.assertIn("Deferred variant execution status:", markdown)
        self.assertIn("Deferred variant ordered sweep count:", markdown)
        self.assertIn("Deferred test queue summary:", markdown)
        self.assertIn("activation_ready_not_before_user_local", markdown)
        self.assertIn("first_blocking_gate", markdown)
        self.assertNotIn("Deferred variant execution plan: `", markdown)
        self.assertNotIn("Deferred test queue: `", markdown)
        self.assertIn("research_only_never_satisfies_exact_alpaca_opra_profitability_gate", markdown)
        self.assertIn("separate_quote_age_from_structural_spread_and_depth_blockers", markdown)
        self.assertIn("skipped_existing_shared_date", markdown)
        self.assertIn("Action status: `waiting_for_next_market_close`", markdown)
        self.assertIn("Can attempt capture now: `False`", markdown)
        self.assertIn("Scheduled timing status: `scheduled_future`", markdown)
        self.assertIn("Hours until scheduled capture: `17.07`", markdown)
        self.assertIn("Next scheduled capture UTC: `2026-05-21T20:20:00Z`", markdown)
        self.assertIn("Capture scope: `ai_commodity_scan_universe`", markdown)
        self.assertIn("Capture symbol count: `24`", markdown)
        self.assertIn("Capture target complete: `True`", markdown)
        self.assertIn("Missing target symbols after capture: `[]`", markdown)
        self.assertIn("## Diagnostic Replay", markdown)
        self.assertIn("Status: `skipped`", markdown)
        self.assertIn("Can verify profitability: `False`", markdown)
        self.assertIn("Current shared dates: `2` / `100`", markdown)
        self.assertIn("Diagnostic min calendar dates: `88`", markdown)
        self.assertIn("Blockers: `['insufficient_replay_simulation_quote_dates']`", markdown)
        self.assertIn("Next action: `accumulate_replay_simulation_shared_opra_dates`", markdown)
        self.assertIn("Total trades: `0`", markdown)
        self.assertIn("## Fresh Scan Retest Plan", markdown)
        self.assertIn("Primary probe: `FCX` reasons `['stale_leg_quote']`", markdown)
        self.assertIn("Quote-age-only blocker symbols: `['FCX']`", markdown)

    def test_render_markdown_includes_scan_sensitivity(self):
        report = {
            "generated_at": "2026-05-21T01:00:00Z",
            "provider": "alpaca:sip:opra",
            "alpaca_enabled": True,
            "next_blocker": "scan_zero_candidates:option_liquidity",
            "proof_window": {},
            "capture": {},
            "automation_health": {},
            "progress_delta": {},
            "readiness": {},
            "replay": {},
            "scan": {
                "candidate_count": 0,
                "returned_count": 0,
                "gate_sensitivity": {
                    "production_filters_preserved": True,
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                    "closest_ev_floor": {
                        "symbol": "FCX",
                        "min_heuristic_ev_needed_to_admit": 2.4555,
                    },
                    "closest_option_liquidity": {
                        "symbol": "ALB",
                        "liquidity_spread_max_needed_to_admit": 10.99,
                        "spread_liquidity_slippage_max_needed_to_admit": 11.21,
                        "quote_age_max_needed_to_admit": 8.9,
                    },
                },
                "quote_freshness_context": {
                    "status": "stale_quote_sensitive",
                    "liquidity_example_count": 2,
                    "stale_quote_example_count": 2,
                    "max_quote_age_excess_hours": 0.9,
                    "next_fresh_scan": {
                        "scheduled_local": "2026-05-21T10:10:00-04:00",
                        "scheduled_utc": "2026-05-21T14:10:00Z",
                        "window_end_utc": "2026-05-21T20:00:00Z",
                        "status": "fresh_scan_future",
                        "can_attempt_scan_now": False,
                    },
                },
            },
        }

        markdown = render_markdown(report)

        self.assertIn("## Scan Sensitivity", markdown)
        self.assertIn("Production filters preserved: `True`", markdown)
        self.assertIn(
            "Recommended action: `rerun_live_scan_during_fresh_opra_window_before_filter_changes`",
            markdown,
        )
        self.assertIn("Quote freshness status: `stale_quote_sensitive`", markdown)
        self.assertIn("Stale quote examples: `2` / `2`", markdown)
        self.assertIn("Max quote-age excess hours: `0.9`", markdown)
        self.assertIn("Fresh scan window status: `fresh_scan_future`", markdown)
        self.assertIn("Fresh scan can run now: `False`", markdown)
        self.assertIn("Next fresh scan market local: `2026-05-21T10:10:00-04:00`", markdown)
        self.assertIn("Next fresh scan runbook local: `None`", markdown)
        self.assertIn("Next fresh scan UTC: `2026-05-21T14:10:00Z`", markdown)
        self.assertIn("Fresh scan window end UTC: `2026-05-21T20:00:00Z`", markdown)
        self.assertIn("Closest EV gate: `FCX` needs min heuristic EV <= `2.4555`", markdown)
        self.assertIn("Closest liquidity/freshness gate: `ALB` needs leg spread max >= `10.99`", markdown)
        self.assertIn("quote age max >= `8.9`", markdown)

    def test_scan_summary_compacts_actionable_blocker_examples(self):
        summary = _scan_summary(
            {
                "candidate_count": 0,
                "returned_count": 0,
                "scan_drop_reasons": {
                    "FCX": {
                        "drop_key": "ev_floor",
                        "details": {
                            "candidate_heuristic_ev_pct": 3.6,
                            "min_heuristic_ev": 5.0,
                            "direction_score": 68.9,
                            "quality_score": 67.4,
                        },
                    },
                    "ETN": {
                        "drop_key": "option_liquidity",
                        "details": {
                            "liquidity": {
                                "reasons": ["wide_leg_spread"],
                                "worst_leg_bid_ask_spread_pct": 16.51,
                                "spread_bid_ask_pct_of_mid": 9.86,
                                "min_leg_volume": 7,
                                "min_leg_open_interest": 1022,
                            },
                            "liquidity_filters": {
                                "liquidity_spread_max_pct": 8.0,
                                "spread_liquidity_slippage_max_pct": 10.0,
                                "min_option_volume": 1,
                                "min_option_open_interest": 50,
                                "max_option_quote_age_hours": 8.0,
                            },
                        },
                    },
                    "VRT": {
                        "drop_key": "tech_score",
                        "details": {
                            "tech_score": 54.2,
                            "min_tech_score": 60.0,
                        },
                    },
                    "CCJ": {
                        "drop_key": "momentum",
                        "details": {
                            "ret5": -1.7,
                            "ret20": 0.4,
                            "price": 102.0,
                            "sma20": 100.0,
                            "sma50": 98.0,
                            "call_entry_momentum_pct": 0.5,
                            "put_entry_momentum_pct": 0.5,
                            "direction_score": 44.0,
                            "quality_score": 58.0,
                        },
                    },
                },
                "scan_funnel": {
                    "drop_counts": {
                        "option_liquidity": 7,
                        "tech_score": 5,
                        "momentum": 4,
                        "ev_floor": 2,
                    }
                },
                "playbook": {},
            }
        )

        self.assertEqual(summary["blocker_examples"][0]["symbol"], "FCX")
        self.assertEqual(summary["blocker_examples"][0]["drop_key"], "ev_floor")
        self.assertEqual(summary["blocker_examples"][0]["candidate_heuristic_ev_pct"], 3.6)
        self.assertEqual(summary["blocker_examples"][0]["heuristic_ev_shortfall_pct"], 1.4)
        self.assertEqual(summary["scan_drop_reason_audit_status"], "raw_drop_reasons_recorded")
        self.assertEqual(summary["scan_drop_reason_count"], 4)
        self.assertEqual(summary["scan_drop_reasons"]["CCJ"]["details"]["price"], 102.0)
        self.assertEqual(summary["scan_drop_reasons"]["CCJ"]["details"]["sma20"], 100.0)
        self.assertEqual(summary["scan_drop_reason_symbols_by_drop"]["momentum"], ["CCJ"])
        self.assertIn("price", summary["scan_drop_reason_detail_fields_by_drop"]["momentum"])
        self.assertIn("sma20", summary["scan_drop_reason_detail_fields_by_drop"]["momentum"])
        self.assertEqual(
            summary["scan_drop_reason_examples_by_symbol"]["CCJ"]["momentum_signal_distance_pct"],
            1.9608,
        )
        self.assertIn(
            "momentum_signal_distance_pct",
            summary["scan_drop_reason_derived_fields_by_drop"]["momentum"],
        )
        self.assertEqual(summary["blocker_examples"][1]["liquidity_reasons"], ["wide_leg_spread"])
        self.assertEqual(summary["blocker_examples"][1]["worst_leg_spread_excess_pct"], 8.51)
        self.assertEqual(summary["blocker_examples"][1]["spread_slippage_excess_pct"], 0.0)
        self.assertEqual(summary["blocker_examples"][1]["min_leg_volume_shortfall"], 0.0)
        self.assertEqual(summary["blocker_examples"][1]["min_leg_open_interest_shortfall"], 0.0)
        sensitivity = summary["gate_sensitivity"]
        self.assertTrue(sensitivity["production_filters_preserved"])
        self.assertEqual(
            sensitivity["recommended_action"],
            "hold_filters_until_exact_alpaca_opra_replay_is_ready",
        )
        self.assertEqual(sensitivity["closest_ev_floor"]["symbol"], "FCX")
        self.assertEqual(sensitivity["closest_ev_floor"]["min_heuristic_ev_needed_to_admit"], 3.6)
        self.assertEqual(sensitivity["closest_option_liquidity"]["symbol"], "ETN")
        self.assertEqual(sensitivity["closest_option_liquidity"]["combined_gate_distance"], 8.51)
        self.assertEqual(sensitivity["closest_option_liquidity"]["liquidity_spread_max_needed_to_admit"], 16.51)
        self.assertEqual(summary["quote_freshness_context"]["status"], "fresh_or_not_age_limited")
        self.assertEqual(
            [item["drop_key"] for item in summary["drop_diagnostics"]],
            ["option_liquidity", "tech_score", "momentum", "ev_floor"],
        )
        self.assertEqual(summary["drop_diagnostics"][0]["example_symbols"], ["ETN"])
        self.assertEqual(
            summary["drop_diagnostics"][0]["next_diagnostic_action"],
            "after_fresh_quotes_recheck_quote_age_then_structural_spread_distance",
        )
        self.assertEqual(summary["drop_diagnostics"][1]["representative_examples"][0]["symbol"], "VRT")
        self.assertEqual(summary["drop_diagnostics"][1]["representative_examples"][0]["tech_score_shortfall"], 5.8)
        momentum_examples = {
            item["drop_key"]: item for item in summary["drop_diagnostics"]
        }["momentum"]["representative_examples"]
        self.assertEqual(momentum_examples[0]["symbol"], "CCJ")
        self.assertEqual(momentum_examples[0]["bearish_momentum_shortfall_pct"], 0.0)
        self.assertEqual(momentum_examples[0]["bearish_trend_gap_pct"], 1.9608)
        self.assertEqual(momentum_examples[0]["momentum_signal_distance_pct"], 1.9608)
        self.assertEqual(
            momentum_examples[0]["momentum_distance_basis"],
            "nearest_call_or_put_ret5_and_sma20_signal_gap",
        )

    def test_scan_summary_splits_raw_and_proof_eligible_candidates(self):
        summary = _scan_summary(
            {
                "candidate_count": 4,
                "returned_count": 4,
                "picks": [
                    {"ticker": "FCX", "guardrail_decision": "blocked", "proof_eligible": True},
                    {"ticker": "CCJ", "status": "research_only", "proof_eligible": True},
                    {
                        "ticker": "PWR",
                        "guardrail_decision": "clear",
                        "candidate_execution_label": "executable_opra_paper_candidate",
                    },
                    {
                        "ticker": "NUE",
                        "guardrail_decision": "clear",
                        "proof_eligible": True,
                        "source_label": "alpaca_opra_daily_snapshot",
                    },
                ],
                "ranked_picks": [
                    {"ticker": "FCX", "guardrail_decision": "blocked", "proof_eligible": True},
                    {"ticker": "CCJ", "status": "research_only", "proof_eligible": True},
                    {
                        "ticker": "PWR",
                        "guardrail_decision": "clear",
                        "candidate_execution_label": "executable_opra_paper_candidate",
                    },
                    {
                        "ticker": "NUE",
                        "guardrail_decision": "clear",
                        "proof_eligible": True,
                        "source_label": "alpaca_opra_daily_snapshot",
                    },
                ],
                "candidate_audit_picks": [
                    {"ticker": "FCX", "guardrail_decision": "blocked", "proof_eligible": True},
                    {"ticker": "CCJ", "status": "research_only", "proof_eligible": True},
                    {
                        "ticker": "PWR",
                        "guardrail_decision": "clear",
                        "candidate_execution_label": "executable_opra_paper_candidate",
                    },
                    {
                        "ticker": "NUE",
                        "guardrail_decision": "clear",
                        "proof_eligible": True,
                        "source_label": "alpaca_opra_daily_snapshot",
                    },
                ],
                "playbook": {},
            }
        )

        self.assertEqual(summary["candidate_count"], 4)
        self.assertEqual(summary["raw_candidate_count"], 4)
        self.assertEqual(summary["candidate_symbols"], ["CCJ", "FCX", "NUE", "PWR"])
        self.assertEqual(summary["proof_eligible_candidate_count"], 2)
        self.assertEqual(summary["proof_eligible_candidate_symbols"], ["NUE", "PWR"])

    def test_scan_summary_requires_proof_grade_label_or_source_for_clear_candidates(self):
        summary = _scan_summary(
            {
                "candidate_count": 1,
                "returned_count": 1,
                "picks": [{"ticker": "FCX", "guardrail_decision": "clear"}],
                "playbook": {},
            }
        )
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["proof_eligible_candidate_count"], 0)
        self.assertEqual(summary["proof_eligible_candidate_symbols"], [])

        gate = build_verified_profitability_gate(
            {
                "provider": "alpaca:sip:opra",
                "proof_source_label": "alpaca_opra_daily_snapshot",
                "proof_window": {
                    "current_shared_quote_dates": 100,
                    "required_shared_quote_dates": 100,
                },
                "automation_health": {"healthy": True},
                "capture": {
                    "scope": "ai_commodity_scan_universe",
                    "target_capture_complete": True,
                    "missing_target_date_symbols_after": [],
                },
                "source_quality": {"status": "usable_quotes_ready"},
                "readiness": {"status": "ready_for_exact_replay"},
                "replay": {"error": None, "total_trades": 12, "profit_factor": 1.2, "total_return_pct": 3.0},
                "scan": summary,
                "scan_proof_universe_alignment": {
                    "status": "scan_universe_aligned_with_exact_proof_universe",
                    "candidate_symbols_outside_exact_proof": [],
                },
            }
        )
        self.assertFalse(gate["verified"])
        self.assertIn("live_scan_candidates:0", gate["blockers"])

    def test_scan_summary_ranks_nearest_zero_candidate_examples_without_changing_filters(self):
        summary = _scan_summary(
            {
                "candidate_count": 0,
                "returned_count": 0,
                "scan_drop_reasons": {
                    "AA": {
                        "drop_key": "option_liquidity",
                        "details": {
                            "liquidity": {
                                "reasons": ["wide_leg_spread", "wide_spread_entry_slippage"],
                                "worst_leg_bid_ask_spread_pct": 14.0,
                                "spread_bid_ask_pct_of_mid": 14.0,
                                "min_leg_volume": 8,
                                "min_leg_open_interest": 500,
                            },
                            "liquidity_filters": {
                                "liquidity_spread_max_pct": 8.0,
                                "spread_liquidity_slippage_max_pct": 10.0,
                                "min_option_volume": 1,
                                "min_option_open_interest": 50,
                                "max_option_quote_age_hours": 8.0,
                            },
                        },
                    },
                    "FCX": {
                        "drop_key": "option_liquidity",
                        "details": {
                            "liquidity": {
                                "reasons": ["wide_leg_spread"],
                                "worst_leg_bid_ask_spread_pct": 9.5,
                                "spread_bid_ask_pct_of_mid": 9.8,
                                "min_leg_volume": 3,
                                "min_leg_open_interest": 200,
                            },
                            "liquidity_filters": {
                                "liquidity_spread_max_pct": 8.0,
                                "spread_liquidity_slippage_max_pct": 10.0,
                                "min_option_volume": 1,
                                "min_option_open_interest": 50,
                                "max_option_quote_age_hours": 8.0,
                            },
                        },
                    },
                    "CARR": {
                        "drop_key": "tech_score",
                        "details": {
                            "tech_score": 36.4,
                            "min_tech_score": 65.0,
                        },
                    },
                    "CCJ": {
                        "drop_key": "tech_score",
                        "details": {
                            "tech_score": 59.8,
                            "min_tech_score": 65.0,
                        },
                    },
                    "BHP": {
                        "drop_key": "momentum",
                        "details": {
                            "ret5": -0.2,
                            "price": 101.0,
                            "sma20": 100.0,
                            "call_entry_momentum_pct": 0.5,
                            "put_entry_momentum_pct": 0.5,
                        },
                    },
                    "CEG": {
                        "drop_key": "momentum",
                        "details": {
                            "ret5": -0.8,
                            "price": 100.5,
                            "sma20": 100.0,
                            "call_entry_momentum_pct": 0.5,
                            "put_entry_momentum_pct": 0.5,
                        },
                    },
                },
                "scan_funnel": {
                    "drop_counts": {
                        "option_liquidity": 2,
                        "tech_score": 2,
                        "momentum": 2,
                    }
                },
                "playbook": {},
            }
        )

        diagnostics = {item["drop_key"]: item for item in summary["drop_diagnostics"]}
        self.assertTrue(summary["gate_sensitivity"]["production_filters_preserved"])
        self.assertEqual(
            diagnostics["option_liquidity"]["representative_examples"][0]["symbol"],
            "AA",
        )
        self.assertEqual(diagnostics["option_liquidity"]["nearest_examples"][0]["symbol"], "FCX")
        self.assertEqual(diagnostics["option_liquidity"]["nearest_examples"][0]["worst_leg_spread_excess_pct"], 1.5)
        self.assertEqual(diagnostics["tech_score"]["representative_examples"][0]["symbol"], "CARR")
        self.assertEqual(diagnostics["tech_score"]["nearest_examples"][0]["symbol"], "CCJ")
        self.assertEqual(diagnostics["tech_score"]["nearest_examples"][0]["tech_score_shortfall"], 5.2)
        self.assertEqual(diagnostics["momentum"]["nearest_examples"][0]["symbol"], "CEG")
        self.assertEqual(diagnostics["momentum"]["nearest_examples"][0]["momentum_signal_distance_pct"], 0.4975)
        self.assertEqual(
            diagnostics["tech_score"]["production_filter_action"],
            "preserve_filters_until_exact_replay_unlock",
        )

    def test_scan_summary_marks_stale_quote_sensitive_zero_candidate_scan(self):
        summary = _scan_summary(
            {
                "candidate_count": 0,
                "returned_count": 0,
                "scan_drop_reasons": {
                    "ALB": {
                        "drop_key": "option_liquidity",
                        "details": {
                            "liquidity": {
                                "reasons": ["wide_leg_spread", "stale_leg_quote"],
                                "worst_leg_bid_ask_spread_pct": 10.99,
                                "spread_bid_ask_pct_of_mid": 11.21,
                                "min_leg_volume": 9,
                                "min_leg_open_interest": 899,
                                "max_quote_age_hours": 8.87,
                            },
                            "liquidity_filters": {
                                "liquidity_spread_max_pct": 8.0,
                                "spread_liquidity_slippage_max_pct": 10.0,
                                "min_option_volume": 1,
                                "min_option_open_interest": 50,
                                "max_option_quote_age_hours": 8.0,
                            },
                        },
                    },
                },
                "playbook": {},
            }
        )

        freshness = summary["quote_freshness_context"]
        self.assertEqual(freshness["status"], "stale_quote_sensitive")
        self.assertEqual(freshness["stale_quote_example_count"], 1)
        self.assertEqual(freshness["max_quote_age_excess_hours"], 0.87)
        self.assertEqual(freshness["recommended_action"], "rerun_live_scan_during_fresh_opra_window_before_filter_changes")
        self.assertEqual(
            summary["gate_sensitivity"]["recommended_action"],
            "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
        )

    def test_annotate_scan_quote_freshness_timing_adds_next_fresh_scan(self):
        scan = {
            "quote_freshness_context": {
                "status": "stale_quote_sensitive",
                "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
            },
            "gate_sensitivity": {},
        }

        enriched = annotate_scan_quote_freshness_timing(
            scan,
            now_utc=datetime(2026, 5, 21, 4, 58, tzinfo=UTC),
        )

        next_scan = enriched["quote_freshness_context"]["next_fresh_scan"]
        self.assertEqual(next_scan["scheduled_utc"], "2026-05-21T14:10:00Z")
        self.assertEqual(next_scan["status"], "fresh_scan_future")
        self.assertFalse(next_scan["can_attempt_scan_now"])
        self.assertEqual(enriched["gate_sensitivity"]["next_fresh_scan_utc"], "2026-05-21T14:10:00Z")

    def test_annotate_scan_quote_freshness_timing_marks_active_window(self):
        enriched = annotate_scan_quote_freshness_timing(
            {
                "quote_freshness_context": {
                    "status": "stale_quote_sensitive",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                },
                "gate_sensitivity": {},
            },
            now_utc=datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
        )

        next_scan = enriched["quote_freshness_context"]["next_fresh_scan"]
        self.assertEqual(next_scan["status"], "fresh_scan_due_window")
        self.assertTrue(next_scan["can_attempt_scan_now"])
        self.assertEqual(next_scan["window_end_utc"], "2026-05-21T20:00:00Z")

    def test_annotate_scan_quote_freshness_timing_adds_retest_plan(self):
        enriched = annotate_scan_quote_freshness_timing(
            {
                "quote_freshness_context": {
                    "status": "stale_quote_sensitive",
                    "recommended_action": "rerun_live_scan_during_fresh_opra_window_before_filter_changes",
                },
                "gate_sensitivity": {
                    "closest_option_liquidity": {
                        "symbol": "FCX",
                        "liquidity_reasons": ["stale_leg_quote"],
                        "quote_age_excess_hours": 1.85,
                        "combined_gate_distance": 1.85,
                    },
                },
                "blocker_examples": [
                    {
                        "symbol": "FCX",
                        "drop_key": "option_liquidity",
                        "liquidity_reasons": ["stale_leg_quote"],
                        "worst_leg_spread_excess_pct": 0.0,
                        "spread_slippage_excess_pct": 0.0,
                        "min_leg_volume_shortfall": 0.0,
                        "min_leg_open_interest_shortfall": 0.0,
                        "quote_age_excess_hours": 1.85,
                    },
                    {
                        "symbol": "ALB",
                        "drop_key": "option_liquidity",
                        "liquidity_reasons": ["wide_leg_spread", "stale_leg_quote"],
                        "worst_leg_spread_excess_pct": 2.0,
                        "spread_slippage_excess_pct": 1.0,
                        "min_leg_volume_shortfall": 0.0,
                        "min_leg_open_interest_shortfall": 0.0,
                        "quote_age_excess_hours": 1.85,
                    },
                ],
            },
            now_utc=datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
        )

        plan = enriched["fresh_scan_retest_plan"]
        self.assertEqual(plan["status"], "active_window")
        self.assertEqual(plan["next_action"], "run_fresh_opra_scan_now")
        self.assertEqual(plan["scan_calendar"], "us_equity_market_days")
        self.assertTrue(plan["scheduled_trade_date_is_market_day"])
        self.assertEqual(plan["primary_probe_symbol"], "FCX")
        self.assertEqual(plan["primary_probe_reasons"], ["stale_leg_quote"])
        self.assertEqual(plan["quote_age_only_blocker_symbols"], ["FCX"])
        self.assertEqual(plan["structural_liquidity_blocker_symbols"], ["ALB"])
        self.assertIn("fresh_scan_candidate_count_above_zero", plan["success_criteria"])


if __name__ == "__main__":
    unittest.main()
