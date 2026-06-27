from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_options_oracle_profit_loop_packet as packet
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class OptionsOracleProfitLoopPacketTests(unittest.TestCase):
    def _paths(self, tmp: Path) -> dict[str, Path]:
        paths = {
            "frontier_path": tmp / "frontier.json",
            "momentum_edge_path": tmp / "momentum.json",
            "momentum_continuation_replay_path": tmp / "momentum-replay.json",
            "momentum_continuation_proof_resolution_path": tmp / "momentum-resolution.json",
            "momentum_continuation_bounded_replay_path": tmp / "momentum-bounded-replay.json",
            "preregistered_vrp_playbook_path": tmp / "vrp-playbook.json",
            "vrp_replay_readiness_path": tmp / "vrp-readiness.json",
            "vrp_structure_harness_path": tmp / "vrp-structure-harness.json",
            "vrp_bounded_replay_path": tmp / "vrp-bounded-replay.json",
            "preregistered_term_structure_playbook_path": tmp / "term-structure.json",
            "term_structure_replay_readiness_path": tmp / "term-readiness.json",
            "term_structure_harness_path": tmp / "term-structure-harness.json",
            "term_structure_bounded_replay_path": tmp / "term-bounded-replay.json",
            "preregistered_skew_broken_wing_playbook_path": tmp / "skew-broken-wing.json",
            "preregistered_macro_event_long_strangle_playbook_path": tmp / "macro-event-long-strangle.json",
            "macro_event_calendar_path": tmp / "macro-event-calendar.json",
            "point_in_time_vix_bucket_path": tmp / "vix-bucket.json",
            "macro_event_long_strangle_replay_readiness_path": tmp / "macro-event-long-strangle-readiness.json",
            "candidate_generation_13_symbol_surface_audit_path": tmp / "13-symbol-surface-audit.json",
            "candidate_generation_13_symbol_frozen_source_surface_path": tmp / "13-symbol-frozen-source-surface.json",
            "candidate_generation_13_symbol_frozen_entrypoint_path": tmp / "13-symbol-frozen-entrypoint.json",
            "candidate_generation_13_symbol_frozen_engine_path": tmp / "13-symbol-frozen-engine.json",
            "preregistered_post_event_iv_crush_iron_condor_playbook_path": tmp / "post-event-iv-crush-iron-condor.json",
            "post_event_iv_crush_replay_readiness_path": tmp / "post-event-iv-crush-readiness.json",
            "preregistered_flow_extreme_ratio_backspread_playbook_path": tmp / "flow-extreme-ratio-backspread.json",
            "flow_extreme_volume_oi_source_rows_path": tmp / "flow-extreme-volume-oi-source-rows.json",
            "point_in_time_flow_extreme_input_path": tmp / "flow-extreme-input.json",
            "multi_leg_side_aware_pricing_capability_path": tmp / "multi-leg-pricing-capability.json",
            "base_clean_stack_identity_ledger_path": tmp / "base-clean-stack-identity-ledger.json",
            "flow_extreme_denominator_dedupe_bridge_path": tmp / "flow-extreme-denominator-dedupe-bridge.json",
            "flow_extreme_ratio_backspread_replay_readiness_path": tmp / "flow-extreme-ratio-backspread-readiness.json",
            "preregistered_dispersion_proxy_hybrid_playbook_path": tmp / "dispersion-proxy-hybrid.json",
            "point_in_time_dispersion_concentration_proxy_path": tmp / "dispersion-concentration-proxy.json",
            "preregistered_pmcc_diagonal_playbook_path": tmp / "pmcc-diagonal.json",
            "pmcc_diagonal_replay_readiness_path": tmp / "pmcc-diagonal-readiness.json",
            "source_repair_59_symbol_path": tmp / "source-repair-59-symbol.json",
            "source_repair_59_symbol_resume_path": tmp / "source-repair-59-symbol-resume.json",
            "direct_vix_source_repair_packet_path": tmp / "direct-vix-source-repair-packet.json",
            "macro_event_calendar_source_repair_packet_path": tmp / "macro-event-calendar-source-repair-packet.json",
            "flow_extreme_source_repair_packet_path": tmp / "flow-extreme-source-repair-packet.json",
            "underlying_daily_source_acquisition_path": tmp / "underlying-daily-source-acquisition.json",
            "underlying_daily_source_import_path": tmp / "underlying-daily-source-import.json",
            "goal_loop_path": tmp / "goal.json",
            "next_steps_path": tmp / "NEXT_STEPS.md",
            "decisions_path": tmp / "DECISIONS.md",
            "project_context_path": tmp / "PROJECT_CONTEXT.md",
        }
        _write_json(
            paths["frontier_path"],
            {
                "report_id": "regular_options_countable_throughput_frontier",
                "status": "current_historical_surface_exhausted_under_current_prohibitions",
                "candidate_count": 44,
                "raw_count_candidate_count": 11,
                "countable_throughput_candidate_found": False,
                "current_historical_surface_exhausted_under_current_prohibitions": True,
                "decision_counts": {
                    "blocked_below_strict_new_count": 33,
                    "blocked_execution_quality": 2,
                    "rejected_negative_or_flat_edge": 9,
                },
                "base_clean_stack_exact_rows": 157,
                "target_exact_rows": 200,
                "strict_new_gap_required": 43,
            },
        )
        _write_json(
            paths["momentum_edge_path"],
            {
                "report_id": "regular_options_current_regime_momentum_edge",
                "status": "raw_count_available_but_not_countable_profitable_edge",
                "decision_counts": {"raw_count_target_met_but_not_countable_edge": 2},
                "countable_momentum_edge_candidate_count": 0,
            },
        )
        _write_json(
            paths["goal_loop_path"],
            {
                "report_id": "options_goal_loop",
                "current_decision_state": "underpowered_forward_evidence",
                "next_safe_action": "continue_paper_shadow_only",
                "forward_evidence_accounting": {"state": "log_missing_blocker"},
            },
        )
        _write_json(
            paths["source_repair_59_symbol_path"],
            {
                "report_id": "regular_options_59_symbol_thetadata_opra_import_repair",
                "status": "blocked_thetaterminal_source_unavailable",
                "approval_token_valid": True,
                "blockers": ["thetaterminal_source_unavailable"],
                "theta_terminal": {
                    "status": "unavailable",
                    "available": False,
                    "url": "http://127.0.0.1:25503/v2/system/status",
                },
                "shared_trusted_imported_quote_dates": {
                    "count": 260,
                    "first": "2025-05-22",
                    "last": "2026-06-04",
                },
                "missing_symbol_date_count": 11565,
                "import_attempted": False,
                "imported_rows": 0,
                "quotes_imported": False,
                "accepted_profitability": False,
                "historical_simulated_forward_status": "blocked_historical_simulated_forward_audit",
            },
        )
        _write_json(
            paths["source_repair_59_symbol_resume_path"],
            {
                "report_id": "regular_options_59_symbol_thetadata_opra_import_repair_resume",
                "status": "blocked_thetaterminal_source_unavailable_retry",
                "resume_missing_only": True,
                "provider_recheck": True,
                "approval_token_valid": True,
                "blockers": ["thetaterminal_source_unavailable"],
                "theta_terminal": {
                    "status": "unavailable",
                    "available": False,
                    "url": "http://127.0.0.1:25503/v2/system/status",
                },
                "shared_trusted_imported_quote_dates": {
                    "count": 260,
                    "first": "2025-05-22",
                    "last": "2026-06-04",
                },
                "post_import_shared_trusted_imported_quote_dates": {
                    "count": 260,
                    "first": "2025-05-22",
                    "last": "2026-06-04",
                },
                "missing_symbol_date_count": 11565,
                "import_attempted": False,
                "imported_rows": 0,
                "quotes_imported": False,
                "protected_holdout_overlap_rows": 0,
                "outside_universe_import_rows": 0,
                "split_audit_gate": {
                    "train_months_covered": 0,
                    "audit_months_covered": 0,
                    "latest_audit_exact_trades": 0,
                    "cleared": False,
                },
            },
        )
        _write_json(
            paths["direct_vix_source_repair_packet_path"],
            {
                "report_id": "regular_options_direct_vix_source_repair_packet",
                "status": "direct_vix_source_repair_packet_ready_for_operator_import_decision",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "source_family": "direct_vix_daily_close",
                "blockers": [],
                "point_in_time_vix_bucket_status": "blocked_point_in_time_vix_source_missing",
                "vix_source_rows_count": 0,
                "vix_coverage_pct": 0.0,
                "current_forward_rows": 0,
                "target_forward_rows": 30,
                "known_at_policy": {
                    "policy_id": "vix_prior_regular_session_close_known_next_session_v1",
                    "same_day_vix_close_for_same_day_entry_allowed": False,
                },
                "bucket_policy": {
                    "policy_id": "vix_prior_close_fixed_buckets_v1",
                    "low_mid": "prior_vix_close <= 25",
                },
                "fixture_validation": {
                    "known_at_safe": True,
                    "same_day_vix_close_safe_for_same_day_entry": False,
                    "weekend_gap_case_present": True,
                    "protected_holdout_overlap_rows": 0,
                    "leakage_reject_count": 0,
                },
                "future_import_manifest_template": {
                    "source_file": "data/import-staging/vix/cboe_vix_daily_history.csv",
                    "source_family": "direct_vix_daily_close",
                    "required_approval_token": "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
                    "write_target": "generated point-in-time VIX source artifact only",
                },
                "future_import_command": "npm run options:source-import:direct-vix -- --source-file data/import-staging/vix/cboe_vix_daily_history.csv --approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json",
                "downstream_vix_bucket_materialization_command": "npm run options:research:point-in-time-vix-bucket -- --source-family direct_vix_daily_close --as-of-date 2026-06-04 --json",
                "future_import_command_executed": False,
                "downstream_vix_bucket_command_executed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "vix_blocked_branch_implications": [
                    {
                        "branch": "momentum_continuation",
                        "current_blocker": "missing_point_in_time_vix_bucket",
                        "would_clear_vix_blocker_if_future_source_passes": True,
                    },
                    {
                        "branch": "pmcc_diagonal",
                        "current_blocker": "point_in_time_vix_bucket_blocked",
                        "would_clear_vix_blocker_if_future_source_passes": True,
                    },
                ],
            },
        )
        _write_json(
            paths["underlying_daily_source_acquisition_path"],
            {
                "report_id": "regular_options_underlying_daily_source_acquisition_packet",
                "status": "blocked_underlying_daily_source_acquisition_missing",
                "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
                "candidate_file_count": 0,
                "ready_candidate_count": 0,
                "selected_ready_source_file": None,
                "blockers": ["trusted_source_csv_missing"],
                "candidate_blocker_counts": {},
                "future_import_command": "npm run options:source-import:underlying-daily-history -- --source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv --approval-token APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT --no-replay --json",
                "source_rows_written": False,
                "source_import_command_executed": False,
            },
        )
        _write_json(
            paths["underlying_daily_source_import_path"],
            {
                "report_id": "regular_options_underlying_daily_history_source_import",
                "status": "blocked_underlying_daily_history_source_import",
                "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
                "source_row_count": 0,
                "source_rows_written": False,
                "source_rows_path": "data/profitability-lab/regular-options-point-in-time-underlying-daily-history/source_rows.jsonl",
                "blockers": ["fixture_source_file_requires_non_default_source_rows_path"],
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
            },
        )
        _write_json(
            paths["macro_event_calendar_source_repair_packet_path"],
            {
                "report_id": "regular_options_macro_event_calendar_source_repair_packet",
                "status": "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "source_family": "scheduled_macro_event_calendar_v1",
                "blockers": [],
                "macro_event_calendar_status": "blocked_macro_event_calendar_source_missing",
                "event_count": 0,
                "covered_categories": [],
                "missing_required_categories": [
                    "cpi",
                    "fomc_minutes",
                    "fomc_rate_decision",
                    "nonfarm_payrolls",
                    "pce",
                    "scheduled_fed_chair_testimony",
                ],
                "current_forward_rows": 0,
                "target_forward_rows": 30,
                "known_at_policy": {
                    "policy_id": "scheduled_macro_event_known_before_candidate_decision_v1",
                    "forbidden_candidate_inputs": ["actual", "surprise", "market_reaction", "pnl"],
                },
                "tradable_after_policy": {
                    "policy_id": "scheduled_macro_event_tradable_after_release_window_v1",
                    "after_market": "next regular session no earlier than 09:30 America/New_York",
                },
                "fixture_validation": {
                    "known_at_safe": True,
                    "leakage_reject_count": 0,
                    "protected_holdout_overlap_rows": 0,
                    "all_required_categories_present": True,
                    "before_market_case_present": True,
                    "during_market_case_present": True,
                    "after_market_case_present": True,
                },
                "future_import_manifest_template": {
                    "source_file": "data/import-staging/macro_events/macro_event_calendar.csv",
                    "source_family": "scheduled_macro_event_calendar_v1",
                    "required_approval_token": "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT",
                    "write_target": "generated point-in-time macro-event calendar source artifact only",
                },
                "future_import_command": "npm run options:source-import:macro-event-calendar -- --source-file data/import-staging/macro_events/macro_event_calendar.csv --approval-token APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT --no-replay --json",
                "downstream_readiness_commands": {
                    "macro_event_long_strangle": "npm run options:research:macro-event-long-strangle-replay-readiness -- --json",
                    "post_event_iv_crush_iron_condor": "npm run options:research:post-event-iv-crush-replay-readiness -- --json",
                },
                "future_import_command_executed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "downstream_branch_implications": [
                    {
                        "branch": "macro_event_long_strangle",
                        "event_calendar_blockers": ["macro_event_calendar_source_missing"],
                        "would_clear_event_calendar_blocker_if_future_source_passes": True,
                    },
                    {
                        "branch": "post_event_iv_crush_iron_condor",
                        "event_calendar_blockers": ["future_replay_requires_point_in_time_macro_event_calendar"],
                        "would_clear_event_calendar_blocker_if_future_source_passes": True,
                    },
                ],
            },
        )
        _write_json(
            paths["flow_extreme_source_repair_packet_path"],
            {
                "report_id": "regular_options_flow_extreme_source_repair_packet",
                "status": "flow_extreme_source_repair_packet_ready_for_operator_import_decision",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "source_family": "trusted_option_volume_open_interest_daily_v1",
                "blockers": [],
                "point_in_time_flow_extreme_input_status": "blocked_point_in_time_flow_extreme_input",
                "flow_extreme_volume_oi_source_rows_status": "blocked_flow_extreme_volume_oi_source_rows",
                "covered_month_count": 0,
                "date_coverage_pct": 0.0,
                "flow_extreme_ratio_backspread_replay_readiness_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
                "current_forward_rows": 0,
                "target_forward_rows": 30,
                "known_at_policy": {
                    "policy_id": "trusted_flow_prior_source_date_known_before_candidate_v1",
                    "same_day_aggregate_volume_oi_allowed_for_same_day_entry": False,
                },
                "threshold_policy": {
                    "policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
                    "flow_extreme_rule": "flow_extreme=true only when prior-day flow percentile >= 95.0 using strictly prior source rows only",
                    "realized_pnl_used": False,
                    "outcome_tuned": False,
                    "plain_bid_ask_used_as_flow": False,
                },
                "fixture_validation": {
                    "known_at_safe": True,
                    "underlyings_covered": ["SPY", "QQQ"],
                    "late_known_at_reject_count": 1,
                    "missing_value_reject_count": 1,
                    "protected_holdout_overlap_rows": 0,
                    "leakage_reject_count": 0,
                },
                "future_import_manifest_template": {
                    "source_file": "data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv",
                    "source_family": "trusted_option_volume_open_interest_daily_v1",
                    "required_approval_token": "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT",
                    "write_target": "generated point-in-time flow-extreme source artifact only",
                },
                "future_import_command": "npm run options:source-import:flow-extreme-volume-oi -- --source-file data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv --approval-token APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT --no-replay --json",
                "downstream_readiness_commands": {
                    "point_in_time_flow_extreme_input": "npm run options:research:point-in-time-flow-extreme-input -- --no-write --json",
                    "flow_extreme_ratio_backspread_replay_readiness": "npm run options:research:flow-extreme-ratio-backspread-replay-readiness -- --json",
                },
                "future_import_command_executed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "downstream_branch_implications": [
                    {
                        "branch": "flow_extreme_ratio_backspread",
                        "would_clear_flow_blocker_if_future_source_passes": True,
                    },
                ],
            },
        )
        _write_json(
            paths["momentum_continuation_replay_path"],
            {
                "report_id": "regular_options_momentum_continuation_research_replay",
                "status": "implemented_research_replay_no_proof_qualified_rows",
                "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
                "accepted_profitability": False,
                "research_only_replay_harness_implemented": True,
                "historical_replay_performed": True,
                "lane_implementation_performed": False,
                "denominator": {
                    "row_count": 1291,
                    "status_counts": {"missing_point_in_time_vix_bucket": 415},
                    "top_blockers": [{"reason": "missing_point_in_time_vix_bucket", "row_count": 1291}],
                },
                "proof_qualified": {
                    "row_count": 0,
                    "metrics": {"row_count": 0, "net_pnl_usd": None, "profit_factor": None},
                },
                "diagnostic_only_existing_marks": {
                    "metrics": {"row_count": 896, "net_pnl_usd": -58847.66, "profit_factor": 0.7543},
                },
            },
        )
        _write_json(
            paths["momentum_continuation_proof_resolution_path"],
            {
                "report_id": "regular_options_momentum_continuation_proof_blocker_resolution",
                "status": "momentum_continuation_blocked_missing_local_proof_inputs",
                "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
                "accepted_profitability": False,
                "source_denominator_rows": 1291,
                "reconstructed_denominator_rows": 1291,
                "proof_qualified_rows_before_resolution": 0,
                "proof_qualified_rows_after_resolution": 0,
                "historical_rows_are_forward_proof": False,
                "resolution_counts": {
                    "side_aware_quotes_resolved": 783,
                    "point_in_time_inputs_resolved": 0,
                    "proof_qualified_candidate_rows": 0,
                    "blocker_counts": {"missing_point_in_time_vix_bucket": 1291},
                },
                "strict_research_metrics": {"row_count": 0, "net_pnl_usd": None, "profit_factor": None},
                "side_aware_diagnostic_metrics": {"row_count": 783, "net_pnl_usd": 157441.2, "profit_factor": 2.2985},
                "blockers": ["missing_point_in_time_vix_bucket", "strict_rows_below_30_after_resolution"],
            },
        )
        _write_json(
            paths["momentum_continuation_bounded_replay_path"],
            {
                "report_id": "regular_options_momentum_continuation_bounded_replay",
                "status": "blocked_momentum_continuation_bounded_replay",
                "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
                "accepted_profitability": False,
                "replay_gate_blockers": [
                    "missing_point_in_time_spy_momentum_confirmation",
                    "missing_point_in_time_qqq_momentum_confirmation",
                    "strict_rows_below_30_after_resolution",
                ],
            },
        )
        _write_json(
            paths["preregistered_vrp_playbook_path"],
            {
                "report_id": "regular_options_preregistered_vrp_credit_spread_playbook",
                "status": "preregistered_design_only",
                "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
                "structure": "defined_risk_put_credit_spreads_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
            },
        )
        _write_json(
            paths["vrp_replay_readiness_path"],
            {
                "report_id": "regular_options_vrp_credit_spread_replay_readiness",
                "status": "blocked_vrp_credit_spread_replay_readiness",
                "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
                "accepted_profitability": False,
                "blockers": [
                    "missing_credit_spread_side_aware_pricing_engine",
                    "missing_index_credit_spread_quote_surface",
                ],
            },
        )
        _write_json(
            paths["vrp_structure_harness_path"],
            {
                "report_id": "regular_options_vrp_credit_spread_structure_harness",
                "status": "blocked_by_missing_quote_surface",
                "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
                "blocker_burndown": [
                    {"blocker": "missing_credit_spread_side_aware_pricing_engine", "status": "resolved_by_harness"},
                    {"blocker": "missing_index_credit_spread_quote_surface", "status": "unresolved"},
                ],
            },
        )
        _write_json(
            paths["vrp_bounded_replay_path"],
            {
                "report_id": "regular_options_vrp_credit_spread_bounded_replay",
                "status": "blocked_vrp_credit_spread_bounded_replay_gate",
                "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
                "accepted_profitability": False,
                "replay_gate_blockers": ["missing_index_credit_spread_quote_surface"],
            },
        )
        _write_json(
            paths["preregistered_term_structure_playbook_path"],
            {
                "report_id": "regular_options_preregistered_term_structure_calendar_playbook",
                "status": "preregistered_design_only",
                "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
                "structure": "defined_risk_calendar_or_diagonal_debit_spreads_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["term_structure_replay_readiness_path"],
            {
                "report_id": "regular_options_term_structure_calendar_replay_readiness",
                "status": "blocked_term_structure_calendar_replay_readiness",
                "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "blockers": ["missing_calendar_diagonal_side_aware_pricing_engine"],
                "allowed_next_step": "send readiness back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["term_structure_harness_path"],
            {
                "report_id": "regular_options_term_structure_calendar_structure_harness",
                "status": "blocked_by_missing_inputs_or_quotes",
                "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
                "candidate_geometry_ready": True,
                "strict_new_dedupe_ready": True,
                "blocker_burndown": [
                    {"blocker": "missing_calendar_diagonal_side_aware_pricing_engine", "status": "satisfied_by_harness"},
                    {"blocker": "missing_strict_new_dedupe", "status": "satisfied_by_harness"},
                    {"blocker": "missing_index_calendar_quote_surface", "status": "unresolved"},
                    {"blocker": "missing_point_in_time_term_structure_inputs", "status": "unresolved"},
                ],
            },
        )
        _write_json(
            paths["term_structure_bounded_replay_path"],
            {
                "report_id": "regular_options_term_structure_calendar_bounded_replay",
                "status": "blocked_term_structure_calendar_bounded_replay",
                "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
                "accepted_profitability": False,
                "replay_gate_blockers": [
                    "missing_index_calendar_quote_surface",
                    "missing_point_in_time_term_structure_inputs",
                ],
            },
        )
        _write_json(
            paths["preregistered_skew_broken_wing_playbook_path"],
            {
                "report_id": "regular_options_preregistered_skew_broken_wing_playbook",
                "status": "preregistered_design_only",
                "concept_id": "low_mid_vix_index_skew_broken_wing_put_fly_v1",
                "structure": "defined_risk_broken_wing_put_butterflies_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["preregistered_macro_event_long_strangle_playbook_path"],
            {
                "report_id": "regular_options_preregistered_macro_event_long_strangle_playbook",
                "status": "preregistered_design_only",
                "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
                "structure": "defined_risk_long_straddles_or_strangles_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["macro_event_long_strangle_replay_readiness_path"],
            {
                "report_id": "regular_options_macro_event_long_strangle_replay_readiness",
                "status": "blocked_macro_event_long_strangle_replay_readiness",
                "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "blockers": ["missing_point_in_time_macro_event_calendar", "missing_point_in_time_vix_bucket"],
                "smallest_next_blocker_clearing_slice": {
                    "blocker": "missing_point_in_time_macro_event_calendar",
                    "smallest_future_codex_slice": "Build a read-only point-in-time macro-event calendar artifact.",
                },
                "allowed_next_step": "send readiness back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["macro_event_calendar_path"],
            {
                "report_id": "regular_options_macro_event_calendar",
                "status": "blocked_macro_event_calendar_source_missing",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "event_calendar_implemented": True,
                "source_rows_proof_eligible": False,
                "event_count": 0,
                "covered_categories": [],
                "missing_categories": [
                    "fomc_rate_decision",
                    "fomc_minutes",
                    "cpi",
                    "pce",
                    "nonfarm_payrolls",
                    "scheduled_fed_chair_testimony",
                ],
                "blockers": ["macro_event_calendar_source_missing"],
            },
        )
        _write_json(
            paths["point_in_time_vix_bucket_path"],
            {
                "report_id": "regular_options_point_in_time_vix_bucket",
                "status": "blocked_point_in_time_vix_source_missing",
                "point_in_time_vix_low_mid_bucket_available": False,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "source_status": "missing",
                "source_rows_count": 0,
                "requested_date_count": 505,
                "covered_date_count": 0,
                "coverage_pct": 0,
                "late_known_at_count": 0,
                "leakage_reject_count": 0,
                "bucket_threshold_source": None,
                "blockers": ["point_in_time_vix_source_missing", "missing_vix_bucket_threshold_policy"],
            },
        )
        _write_json(
            paths["candidate_generation_13_symbol_surface_audit_path"],
            {
                "report_id": "regular_options_13_symbol_candidate_generation_surface_audit",
                "status": "blocked_13_symbol_candidate_generation_surface_audit",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "quote_history_vs_candidate_generation": {
                    "quote_surface_months_available_count": 24,
                    "candidate_generation_months_covered_count": 8,
                    "selected_trade_depth_months_covered_count": 8,
                    "distinction": "quote-history coverage does not prove pick/no-pick candidate-generation coverage",
                },
                "candidate_generation_surface": {
                    "frozen_universe_exact_13_symbols": False,
                    "non_13_symbol_selected_row_count": 90,
                    "outside_allowed_universe": ["NFLX", "WMT"],
                },
                "runner_support": {"status": "missing_no_write_runner_support"},
                "cvx_scope": {"cvx_scope_enforced": True, "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1"},
                "blockers": [
                    "candidate_generation_months_8_below_requested_24",
                    "existing_candidate_generation_surface_not_frozen_13_symbol",
                    "non_13_symbol_selected_rows_present",
                    "missing_no_write_runner_support",
                ],
            },
        )
        _write_json(
            paths["candidate_generation_13_symbol_frozen_source_surface_path"],
            {
                "report_id": "regular_options_13_symbol_frozen_candidate_generation_source_surface",
                "status": "blocked_13_symbol_frozen_candidate_generation_source_surface",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "read_only": True,
                "no_write": True,
                "posthoc_filtering_allowed_as_proof": False,
                "source_artifact_universe_exact_13_symbols": False,
                "calendar_coverage": {
                    "calendar_months_requested_count": 24,
                    "calendar_months_covered_count": 0,
                    "zero_selection_months": [],
                },
                "selected_trade_summary": {"selected_rows_in_window": 0},
                "blockers": [
                    "candidate_generation_months_0_below_requested_24",
                    "missing_daily_candidate_generation_diagnostics",
                    "source_artifact_universe_not_13_symbol",
                ],
            },
        )
        _write_json(
            paths["candidate_generation_13_symbol_frozen_entrypoint_path"],
            {
                "report_id": "regular_options_13_symbol_frozen_candidate_generation_entrypoint",
                "status": "blocked_frozen_13_symbol_candidate_generation_entrypoint",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "read_only": True,
                "no_write": True,
                "daily_candidate_generation_row_count": 6916,
                "selected_candidate_row_count": 0,
                "coverage": {
                    "requested_month_count": 24,
                    "candidate_generation_months_covered_count": 0,
                    "blocked_months": ["2024-06"],
                },
                "daily_status_counts": {"blocked_missing_daily_candidate_generation_diagnostics": 6916},
                "blockers": [
                    "candidate_generation_months_0_below_requested_24",
                    "missing_daily_candidate_generation_diagnostics",
                    "source_artifact_universe_not_13_symbol",
                ],
            },
        )
        _write_json(
            paths["candidate_generation_13_symbol_frozen_engine_path"],
            {
                "report_id": "regular_options_13_symbol_frozen_candidate_generation_engine",
                "status": "blocked_frozen_13_symbol_candidate_generation_engine",
                "decision": "blocked_frozen_candidate_generation_entrypoint_incomplete",
                "accepted_profitability": False,
                "read_only": True,
                "no_write": True,
                "daily_candidate_generation_row_count": 6916,
                "selected_candidate_row_count": 0,
                "coverage": {
                    "requested_month_count": 24,
                    "candidate_generation_months_covered_count": 0,
                    "train_months_covered": 0,
                    "audit_months_covered": 0,
                    "latest_audit_exact_trades": 0,
                    "latest_four_strict_new_candidates": 0,
                },
                "reusable_entrypoint_discovery": {
                    "available": True,
                    "basis": "frozen_entrypoint_artifact",
                },
                "audit_consumed_generated_surface": False,
                "historical_simulated_forward_audit_command": None,
                "blockers": [
                    "blocked_daily_candidate_generation_coverage",
                    "blocked_latest_audit_rows_below_30",
                    "blocked_train_or_audit_month_coverage",
                    "missing_daily_candidate_generation_diagnostics",
                ],
            },
        )
        _write_json(
            paths["preregistered_post_event_iv_crush_iron_condor_playbook_path"],
            {
                "report_id": "regular_options_preregistered_post_event_iv_crush_iron_condor_playbook",
                "status": "preregistered_design_only",
                "concept_id": "post_event_iv_crush_index_iron_condor_v1",
                "structure": "defined_risk_short_iron_condors_or_iron_butterflies_only",
                "accepted_profitability": False,
                "generated_at_utc": "2026-06-23T05:51:48Z",
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "event_calendar_implemented_in_this_slice": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["post_event_iv_crush_replay_readiness_path"],
            {
                "report_id": "regular_options_post_event_iv_crush_replay_readiness",
                "status": "blocked_post_event_iv_crush_replay_readiness",
                "concept_id": "post_event_iv_crush_index_iron_condor_v1",
                "structure": "defined_risk_short_iron_condors_or_iron_butterflies_only",
                "generated_at_utc": "2026-06-23T05:52:48Z",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "replay_performed": False,
                "lane_implementation_performed": False,
                "event_calendar_implemented_in_this_slice": False,
                "broker_order_allowed": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "scanner_policy_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "historical_rows_are_forward_proof": False,
                "undefined_or_uncapped_short_premium_risk_allowed": False,
                "blockers": [
                    "macro_event_calendar_source_missing",
                    "iv_event_premium_proxy_missing",
                    "missing_index_iron_condor_quote_surface",
                ],
                "smallest_next_blocker_clearing_slice": "iv_event_premium_proxy_missing",
                "allowed_next_step": "send readiness back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["preregistered_flow_extreme_ratio_backspread_playbook_path"],
            {
                "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
                "status": "preregistered_design_only",
                "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
                "structure": "defined_risk_ratio_spreads_or_backspreads_only",
                "accepted_profitability": False,
                "generated_at_utc": "2026-06-23T05:51:48Z",
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_risk_allowed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["point_in_time_flow_extreme_input_path"],
            {
                "report_id": "regular_options_point_in_time_flow_extreme_input",
                "status": "blocked_point_in_time_flow_extreme_input",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "read_only": True,
                "no_write": True,
                "coverage": {"covered_month_count": 0, "date_coverage_pct": 0.0},
                "source_inventory": {"status": "missing_flow_source_rows"},
                "proxy_basis": [],
                "blockers": [
                    "missing_point_in_time_flow_extreme_source",
                    "missing_required_flow_fields",
                    "insufficient_month_coverage",
                    "insufficient_date_coverage",
                ],
            },
        )
        _write_json(
            paths["flow_extreme_volume_oi_source_rows_path"],
            {
                "report_id": "regular_options_flow_extreme_volume_oi_source_rows",
                "status": "blocked_flow_extreme_volume_oi_source_rows",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "source_row_count": 0,
                "write_source_rows_allowed": False,
                "aggregate_source_summary": {"usable_aggregate_row_count": 0},
                "coverage": {"covered_month_count": 0, "date_coverage_pct": 0.0},
                "threshold_policy": {
                    "flow_input_basis": "volume_open_interest",
                    "plain_bid_ask_used_as_flow": False,
                    "quote_depth_fabricated": False,
                },
                "blockers": [
                    "missing_trusted_volume_open_interest_source_rows",
                    "trusted_rows_have_null_volume_open_interest",
                ],
            },
        )
        _write_json(
            paths["multi_leg_side_aware_pricing_capability_path"],
            {
                "report_id": "regular_options_multi_leg_side_aware_pricing_capability",
                "status": "multi_leg_side_aware_pricing_capability_available",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "source_inventory": {"status": "loaded", "read_only_mode": True},
                "quote_resolution_counts": {"fixture_count": 1, "resolved_fixture_count": 1},
                "pricing_capability_blockers": [],
                "structure_support": {
                    "ratio_backspread_bounded": {
                        "status": "available",
                        "denominator_mapping_status": "ready",
                    }
                },
            },
        )
        _write_json(
            paths["base_clean_stack_identity_ledger_path"],
            {
                "report_id": "regular_options_base_clean_stack_identity_ledger",
                "status": "blocked_base_clean_stack_identity_ledger",
                "accepted_profitability": False,
                "proof_row_count": 0,
                "historical_rows_are_forward_proof": False,
                "expected_base_clean_stack_exact_rows": 157,
                "ledger_row_count": 0,
                "unique_identity_count": 0,
                "duplicate_identity_count": 0,
                "missing_identity_field_row_count": 0,
                "future_or_outcome_field_dependency_count": 0,
                "protected_holdout_overlap_count": 0,
                "blockers": ["base_clean_stack_row_source_missing"],
            },
        )
        _write_json(
            paths["flow_extreme_ratio_backspread_replay_readiness_path"],
            {
                "report_id": "regular_options_flow_extreme_ratio_backspread_replay_readiness",
                "status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
                "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
                "structure": "defined_risk_ratio_spreads_or_backspreads_only",
                "generated_at_utc": "2026-06-23T18:39:02Z",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "replay_performed": False,
                "lane_implementation_performed": False,
                "broker_order_allowed": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "undefined_risk_allowed": False,
                "naked_ratio_spreads_allowed": False,
                "blockers": [
                    "missing_point_in_time_flow_extreme_input",
                    "missing_point_in_time_vix_bucket",
                    "missing_strict_new_dedupe",
                ],
                "smallest_next_blocker_clearing_slice": "missing_point_in_time_flow_extreme_input",
                "allowed_next_step": "send readiness back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["flow_extreme_denominator_dedupe_bridge_path"],
            {
                "report_id": "regular_options_flow_extreme_denominator_dedupe_bridge",
                "status": "blocked_flow_extreme_denominator_dedupe_bridge",
                "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
                "structure": "ratio_backspread_bounded",
                "accepted_profitability": False,
                "proof_row_count": 0,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "full_denominator_mapping_status": "ready",
                "strict_new_dedupe_status": "blocked",
                "base_identity_ledger_status": "blocked",
                "base_identity_hash_count": 0,
                "bridge_blockers": [
                    "base_stack_identity_ledger_missing",
                    "strict_new_row_level_identity_ledger_missing",
                ],
                "identity_fields": ["concept_id", "structure", "underlying", "signal_date"],
                "denominator_status_contract": ["candidate_not_generated_missing_flow_input"],
            },
        )
        _write_json(
            paths["preregistered_dispersion_proxy_hybrid_playbook_path"],
            {
                "report_id": "regular_options_preregistered_dispersion_proxy_hybrid_playbook",
                "status": "preregistered_design_only",
                "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
                "structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_or_uncapped_pair_risk_allowed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["point_in_time_dispersion_concentration_proxy_path"],
            {
                "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                "status": "blocked_point_in_time_dispersion_concentration_proxy",
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "read_only": True,
                "no_write": True,
                "coverage": {
                    "covered_month_count": 0,
                    "date_coverage_pct": 0.0,
                },
                "source_inventory": {
                    "status": "missing_proxy_source_rows",
                },
                "blockers": [
                    "missing_point_in_time_dispersion_proxy_source",
                    "missing_required_return_fields",
                    "insufficient_month_coverage",
                    "insufficient_date_coverage",
                ],
            },
        )
        _write_json(
            paths["preregistered_pmcc_diagonal_playbook_path"],
            {
                "report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
                "generated_at_utc": "2026-06-23T06:00:00Z",
                "status": "preregistered_design_only",
                "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
                "structure": "defined_risk_pmcc_style_call_diagonals_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_or_uncapped_short_call_risk_allowed": False,
                "allowed_next_step": "send back to GPT-5.5 Pro",
            },
        )
        _write_json(
            paths["pmcc_diagonal_replay_readiness_path"],
            {
                "report_id": "regular_options_pmcc_diagonal_replay_readiness",
                "generated_at_utc": "2026-06-23T07:00:00Z",
                "status": "blocked_pmcc_diagonal_replay_readiness",
                "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
                "structure": "defined_risk_pmcc_style_call_diagonals_only",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "replay_performed": False,
                "lane_implementation_performed": False,
                "broker_order_allowed": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "scanner_policy_changed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "historical_rows_are_forward_proof": False,
                "undefined_or_uncapped_short_call_risk_allowed": False,
                "blockers": ["missing_point_in_time_trend_or_regime_inputs", "point_in_time_vix_bucket_blocked"],
                "smallest_next_blocker_clearing_slice": "missing_point_in_time_trend_or_regime_inputs",
                "allowed_next_step": "park PMCC or choose next",
            },
        )
        _write_text(paths["next_steps_path"], "Next actions require branch choice.")
        _write_text(paths["decisions_path"], "Proof bars cannot be relaxed.")
        _write_text(paths["project_context_path"], "Regular options only.")
        return paths

    def test_packet_prompt_requires_continue_or_stop_decision(self) -> None:
        with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
            report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **self._paths(Path(tmp_dir)))

        self.assertEqual(report["status"], "ready_for_same_session_gpt55_guidance")
        self.assertIn("continue_loop", report["prompt"])
        self.assertIn("stop_exception", report["prompt"])
        self.assertIn("latest approximately four months", report["prompt"])
        self.assertIn("0/30", report["prompt"])
        self.assertIn("new option structures", report["prompt"])
        self.assertIn("volatility risk premium", report["prompt"])
        self.assertIn("term-structure calendar/diagonal", report["prompt"])
        self.assertIn("low_mid_vix_index_calendar_term_structure_dislocation_v1", report["prompt"])
        self.assertIn("approved momentum-continuation research replay", report["prompt"])
        self.assertIn("implemented_research_replay_no_proof_qualified_rows", report["prompt"])
        self.assertIn("proof-blocker resolution", report["prompt"])
        self.assertIn("momentum_continuation_blocked_missing_local_proof_inputs", report["prompt"])
        self.assertIn("157441.2", report["prompt"])
        self.assertIn("-58847.66", report["prompt"])
        self.assertIn("missing_point_in_time_vix_bucket", report["prompt"])
        self.assertIn("blocked_term_structure_calendar_bounded_replay", report["prompt"])
        self.assertIn("missing_index_calendar_quote_surface", report["prompt"])
        self.assertIn("missing_point_in_time_term_structure_inputs", report["prompt"])
        self.assertIn("low_mid_vix_index_skew_broken_wing_put_fly_v1", report["prompt"])
        self.assertIn("defined_risk_broken_wing_put_butterflies_only", report["prompt"])
        self.assertIn("low_mid_vix_macro_event_long_strangle_v1", report["prompt"])
        self.assertIn("defined_risk_long_straddles_or_strangles_only", report["prompt"])
        self.assertIn("blocked_macro_event_long_strangle_replay_readiness", report["prompt"])
        self.assertIn("missing_point_in_time_macro_event_calendar", report["prompt"])
        self.assertIn("blocked_macro_event_calendar_source_missing", report["prompt"])
        self.assertIn("macro_event_calendar_source_missing", report["prompt"])
        self.assertIn("blocked_point_in_time_vix_source_missing", report["prompt"])
        self.assertIn("point_in_time_vix_source_missing", report["prompt"])
        self.assertIn("missing_vix_bucket_threshold_policy", report["prompt"])
        self.assertIn("blocked_13_symbol_candidate_generation_surface_audit", report["prompt"])
        self.assertIn("quote-history coverage does not prove pick/no-pick candidate-generation coverage", report["prompt"])
        self.assertIn("candidate_generation_months_8_below_requested_24", report["prompt"])
        self.assertIn("non_13_symbol_selected_row_count", report["prompt"])
        self.assertIn("missing_no_write_runner_support", report["prompt"])
        self.assertIn("blocked_13_symbol_frozen_candidate_generation_source_surface", report["prompt"])
        self.assertIn("blocked_frozen_13_symbol_candidate_generation_entrypoint", report["prompt"])
        self.assertIn("blocked_missing_daily_candidate_generation_diagnostics", report["prompt"])
        self.assertIn("posthoc_filtering_allowed_as_proof", report["prompt"])
        self.assertIn("blocked_frozen_13_symbol_candidate_generation_engine", report["prompt"])
        self.assertIn("blocked_frozen_candidate_generation_entrypoint_incomplete", report["prompt"])
        self.assertIn("6916", report["prompt"])
        self.assertIn("Do not repeat the 13-symbol source-surface/no-write/denominator/engine branch", report["prompt"])
        self.assertIn("post_event_iv_crush_index_iron_condor_v1", report["prompt"])
        self.assertIn("defined_risk_short_iron_condors_or_iron_butterflies_only", report["prompt"])
        self.assertIn("blocked_post_event_iv_crush_replay_readiness", report["prompt"])
        self.assertIn("iv_event_premium_proxy_missing", report["prompt"])
        self.assertIn("missing_index_iron_condor_quote_surface", report["prompt"])
        self.assertIn("index_flow_extreme_mean_reversion_ratio_backspread_v1", report["prompt"])
        self.assertIn("defined_risk_ratio_spreads_or_backspreads_only", report["prompt"])
        self.assertIn("blocked_flow_extreme_volume_oi_source_rows", report["prompt"])
        self.assertIn("trusted_rows_have_null_volume_open_interest", report["prompt"])
        self.assertIn("blocked_point_in_time_flow_extreme_input", report["prompt"])
        self.assertIn("missing_point_in_time_flow_extreme_source", report["prompt"])
        self.assertIn("multi_leg_side_aware_pricing_capability_available", report["prompt"])
        self.assertIn("ratio_backspread_bounded", report["prompt"])
        self.assertIn("blocked_base_clean_stack_identity_ledger", report["prompt"])
        self.assertIn("base_clean_stack_row_source_missing", report["prompt"])
        self.assertIn("blocked_flow_extreme_denominator_dedupe_bridge", report["prompt"])
        self.assertIn("base_stack_identity_ledger_missing", report["prompt"])
        self.assertIn("blocked_flow_extreme_ratio_backspread_replay_readiness", report["prompt"])
        self.assertIn("missing_point_in_time_flow_extreme_input", report["prompt"])
        self.assertIn("packet_ingestion", report["prompt"])
        self.assertIn("index_constituent_dispersion_proxy_defined_risk_hybrid_v1", report["prompt"])
        self.assertIn("defined_risk_index_constituent_debit_credit_hybrid_pairs_only", report["prompt"])
        self.assertIn("blocked_point_in_time_dispersion_concentration_proxy", report["prompt"])
        self.assertIn("missing_point_in_time_dispersion_proxy_source", report["prompt"])
        self.assertIn("low_mid_vix_index_pmcc_diagonal_income_v1", report["prompt"])
        self.assertIn("defined_risk_pmcc_style_call_diagonals_only", report["prompt"])
        self.assertIn("blocked_pmcc_diagonal_replay_readiness", report["prompt"])
        self.assertIn("missing_point_in_time_trend_or_regime_inputs", report["prompt"])
        self.assertIn("blocked_thetaterminal_source_unavailable", report["prompt"])
        self.assertIn("thetaterminal_source_unavailable", report["prompt"])
        self.assertIn("11565", report["prompt"])
        self.assertIn("do not treat that as an operator-approval blocker", report["prompt"])
        self.assertIn("blocked_thetaterminal_source_unavailable_retry", report["prompt"])
        self.assertIn("do not select another 59-symbol ThetaTerminal retry", report["prompt"])
        self.assertIn("outside_universe_import_rows", report["prompt"])
        self.assertIn("direct_vix_source_repair_packet_ready_for_operator_import_decision", report["prompt"])
        self.assertIn("direct_vix_daily_close", report["prompt"])
        self.assertIn("vix_prior_close_fixed_buckets_v1", report["prompt"])
        self.assertIn("APPROVE_DIRECT_VIX_SOURCE_IMPORT", report["prompt"])
        self.assertIn("do not rerun the same VIX packet", report["prompt"])
        self.assertIn("operator-supplied official daily VIX CSV", report["prompt"])
        self.assertIn("macro_event_calendar_source_repair_packet_ready_for_operator_import_decision", report["prompt"])
        self.assertIn("scheduled_macro_event_calendar_v1", report["prompt"])
        self.assertIn("APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT", report["prompt"])
        self.assertIn("do not rerun the same macro-event source packet", report["prompt"])
        self.assertIn("operator-supplied official macro-event calendar CSV", report["prompt"])
        self.assertIn("new_causal_playbook_generation", report["prompt"])
        self.assertIn("pre_approved_by_user_for_loop_continuation", report["prompt"])
        self.assertEqual(
            report["operator_approval_posture"]["read_only_research_only_work"],
            "pre_approved_by_user_for_loop_continuation",
        )
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_term_structure_calendar_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["momentum_continuation_replay_status"],
            "implemented_research_replay_no_proof_qualified_rows",
        )
        self.assertEqual(report["current_evidence_summary"]["momentum_continuation_replay_proof_rows"], 0)
        self.assertEqual(
            report["current_evidence_summary"]["momentum_continuation_proof_resolution_status"],
            "momentum_continuation_blocked_missing_local_proof_inputs",
        )
        self.assertEqual(report["current_evidence_summary"]["momentum_continuation_proof_resolution_side_aware_rows"], 783)
        self.assertEqual(
            report["current_evidence_summary"]["momentum_continuation_bounded_replay_blockers"],
            [
                "missing_point_in_time_spy_momentum_confirmation",
                "missing_point_in_time_qqq_momentum_confirmation",
                "strict_rows_below_30_after_resolution",
            ],
        )
        self.assertEqual(
            report["current_evidence_summary"]["term_structure_calendar_replay_readiness_status"],
            "blocked_term_structure_calendar_bounded_replay",
        )
        self.assertEqual(
            report["current_evidence_summary"]["term_structure_calendar_replay_readiness_blockers"],
            ["missing_index_calendar_quote_surface", "missing_point_in_time_term_structure_inputs"],
        )
        self.assertEqual(
            report["current_evidence_summary"]["term_structure_calendar_legacy_replay_readiness_status"],
            "blocked_term_structure_calendar_replay_readiness",
        )
        self.assertEqual(
            report["current_evidence_summary"]["vrp_credit_spread_replay_readiness_blockers"],
            ["missing_index_credit_spread_quote_surface"],
        )
        self.assertEqual(
            report["current_evidence_summary"]["vrp_credit_spread_legacy_replay_readiness_status"],
            "blocked_vrp_credit_spread_replay_readiness",
        )
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_skew_broken_wing_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_macro_event_long_strangle_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_long_strangle_replay_readiness_status"],
            "blocked_macro_event_long_strangle_replay_readiness",
        )
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_calendar_status"],
            "blocked_macro_event_calendar_source_missing",
        )
        self.assertEqual(
            report["current_evidence_summary"]["point_in_time_vix_bucket_status"],
            "blocked_point_in_time_vix_source_missing",
        )
        self.assertFalse(report["current_evidence_summary"]["point_in_time_vix_bucket_available"])
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_surface_audit_status"],
            "blocked_13_symbol_candidate_generation_surface_audit",
        )
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_quote_months"], 24)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_candidate_months"], 8)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_non_13_rows"], 90)
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_runner_status"],
            "missing_no_write_runner_support",
        )
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_source_surface_status"],
            "blocked_13_symbol_frozen_candidate_generation_source_surface",
        )
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_source_surface_months_covered"], 0)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_source_surface_selected_rows"], 0)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_source_surface_zero_pick_months"], 0)
        self.assertIn(
            "source_artifact_universe_not_13_symbol",
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_source_surface_blockers"],
        )
        source_surface_meta = report["source_artifacts"]["candidate_generation_13_symbol_frozen_source_surface"]
        self.assertEqual(source_surface_meta["status"], "loaded")
        engine_meta = report["source_artifacts"]["candidate_generation_13_symbol_frozen_engine"]
        self.assertEqual(engine_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_status"],
            "blocked_frozen_13_symbol_candidate_generation_engine",
        )
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_decision"],
            "blocked_frozen_candidate_generation_entrypoint_incomplete",
        )
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_entrypoint_status"],
            "blocked_frozen_13_symbol_candidate_generation_entrypoint",
        )
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_entrypoint_daily_rows"], 6916)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_entrypoint_selected_candidates"], 0)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_daily_rows"], 6916)
        self.assertEqual(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_selected_rows"], 0)
        self.assertEqual(
            report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_coverage"][
                "requested_month_count"
            ],
            24,
        )
        self.assertTrue(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_entrypoint_available"])
        self.assertFalse(report["current_evidence_summary"]["candidate_generation_13_symbol_frozen_engine_audit_consumed"])
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_post_event_iv_crush_iron_condor_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["post_event_iv_crush_replay_readiness_status"],
            "blocked_post_event_iv_crush_replay_readiness",
        )
        self.assertEqual(
            report["current_evidence_summary"]["post_event_iv_crush_replay_readiness_reason_codes"],
            [],
        )
        self.assertIn(
            "missing_index_iron_condor_quote_surface",
            report["current_evidence_summary"]["post_event_iv_crush_replay_readiness_blockers"],
        )
        post_event_readiness_meta = report["source_artifacts"]["post_event_iv_crush_replay_readiness"]
        self.assertEqual(post_event_readiness_meta["validated_status"], "blocked_post_event_iv_crush_replay_readiness")
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_flow_extreme_ratio_backspread_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["point_in_time_flow_extreme_input_status"],
            "blocked_point_in_time_flow_extreme_input",
        )
        self.assertEqual(report["current_evidence_summary"]["point_in_time_flow_extreme_input_covered_months"], 0)
        self.assertEqual(report["current_evidence_summary"]["point_in_time_flow_extreme_input_date_coverage_pct"], 0.0)
        self.assertEqual(
            report["current_evidence_summary"]["point_in_time_flow_extreme_input_source_inventory_status"],
            "missing_flow_source_rows",
        )
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_volume_oi_source_rows_status"],
            "blocked_flow_extreme_volume_oi_source_rows",
        )
        self.assertEqual(report["current_evidence_summary"]["flow_extreme_volume_oi_source_row_count"], 0)
        self.assertEqual(report["current_evidence_summary"]["flow_extreme_volume_oi_usable_aggregate_row_count"], 0)
        self.assertIn(
            "trusted_rows_have_null_volume_open_interest",
            report["current_evidence_summary"]["flow_extreme_volume_oi_blockers"],
        )
        volume_oi_meta = report["source_artifacts"]["flow_extreme_volume_oi_source_rows"]
        self.assertEqual(volume_oi_meta["status"], "loaded")
        self.assertIn(
            "missing_required_flow_fields",
            report["current_evidence_summary"]["point_in_time_flow_extreme_input_blockers"],
        )
        flow_input_meta = report["source_artifacts"]["point_in_time_flow_extreme_input"]
        self.assertEqual(flow_input_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_status"],
            "blocked_flow_extreme_ratio_backspread_replay_readiness",
        )
        self.assertEqual(
            report["current_evidence_summary"]["multi_leg_side_aware_pricing_capability_status"],
            "multi_leg_side_aware_pricing_capability_available",
        )
        self.assertEqual(
            report["current_evidence_summary"]["ratio_backspread_bounded_pricing_status"],
            "available",
        )
        self.assertEqual(report["current_evidence_summary"]["denominator_mapping_status"], "ready")
        self.assertEqual(report["current_evidence_summary"]["pricing_capability_blockers"], [])
        self.assertEqual(
            report["current_evidence_summary"]["base_clean_stack_identity_ledger_status"],
            "blocked_base_clean_stack_identity_ledger",
        )
        self.assertEqual(report["current_evidence_summary"]["base_clean_stack_identity_ledger_expected_rows"], 157)
        self.assertEqual(report["current_evidence_summary"]["base_clean_stack_identity_ledger_row_count"], 0)
        self.assertIn(
            "base_clean_stack_row_source_missing",
            report["current_evidence_summary"]["base_clean_stack_identity_ledger_blockers"],
        )
        base_ledger_meta = report["source_artifacts"]["base_clean_stack_identity_ledger"]
        self.assertEqual(base_ledger_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_denominator_dedupe_bridge_status"],
            "blocked_flow_extreme_denominator_dedupe_bridge",
        )
        self.assertEqual(report["current_evidence_summary"]["flow_extreme_full_denominator_mapping_status"], "ready")
        self.assertEqual(report["current_evidence_summary"]["flow_extreme_strict_new_dedupe_status"], "blocked")
        self.assertIn(
            "base_stack_identity_ledger_missing",
            report["current_evidence_summary"]["flow_extreme_denominator_dedupe_bridge_blockers"],
        )
        self.assertTrue(report["current_evidence_summary"]["flow_readiness_full_denominator_blocker_cleared"])
        self.assertFalse(report["current_evidence_summary"]["flow_readiness_strict_new_dedupe_blocker_cleared"])
        bridge_meta = report["source_artifacts"]["flow_extreme_denominator_dedupe_bridge"]
        self.assertEqual(bridge_meta["status"], "loaded")
        pricing_meta = report["source_artifacts"]["multi_leg_side_aware_pricing_capability"]
        self.assertEqual(pricing_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_raw_status"],
            "blocked_flow_extreme_ratio_backspread_replay_readiness",
        )
        self.assertEqual(report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_reason_codes"], [])
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_blockers"][0],
            "missing_point_in_time_flow_extreme_input",
        )
        flow_meta = report["source_artifacts"]["flow_extreme_ratio_backspread_replay_readiness"]
        self.assertEqual(flow_meta["status"], "loaded")
        self.assertEqual(
            flow_meta["validated_status"],
            "blocked_flow_extreme_ratio_backspread_replay_readiness",
        )
        self.assertEqual(flow_meta["validation_reason_codes"], [])
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_dispersion_proxy_hybrid_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["point_in_time_dispersion_concentration_proxy_status"],
            "blocked_point_in_time_dispersion_concentration_proxy",
        )
        self.assertEqual(report["current_evidence_summary"]["point_in_time_dispersion_concentration_proxy_covered_months"], 0)
        self.assertEqual(report["current_evidence_summary"]["point_in_time_dispersion_concentration_proxy_date_coverage_pct"], 0.0)
        self.assertEqual(
            report["current_evidence_summary"]["point_in_time_dispersion_concentration_proxy_source_inventory_status"],
            "missing_proxy_source_rows",
        )
        self.assertIn(
            "missing_required_return_fields",
            report["current_evidence_summary"]["point_in_time_dispersion_concentration_proxy_blockers"],
        )
        dispersion_proxy_meta = report["source_artifacts"]["point_in_time_dispersion_concentration_proxy"]
        self.assertEqual(dispersion_proxy_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["preregistered_pmcc_diagonal_status"],
            "preregistered_design_only",
        )
        self.assertEqual(
            report["current_evidence_summary"]["pmcc_diagonal_replay_readiness_status"],
            "blocked_pmcc_diagonal_replay_readiness",
        )
        self.assertEqual(report["current_evidence_summary"]["pmcc_diagonal_replay_readiness_reason_codes"], [])
        self.assertEqual(
            report["current_evidence_summary"]["pmcc_diagonal_replay_readiness_smallest_next_blocker"],
            "missing_point_in_time_trend_or_regime_inputs",
        )
        self.assertIn(
            "point_in_time_vix_bucket_blocked",
            report["current_evidence_summary"]["pmcc_diagonal_replay_readiness_blockers"],
        )
        pmcc_meta = report["source_artifacts"]["pmcc_diagonal_replay_readiness"]
        self.assertEqual(pmcc_meta["status"], "loaded")
        self.assertEqual(pmcc_meta["validated_status"], "blocked_pmcc_diagonal_replay_readiness")
        source_repair_meta = report["source_artifacts"]["source_repair_59_symbol_thetadata_opra"]
        self.assertEqual(source_repair_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["source_repair_59_symbol_status"],
            "blocked_thetaterminal_source_unavailable",
        )
        self.assertTrue(report["current_evidence_summary"]["source_repair_59_symbol_approval_token_valid"])
        self.assertFalse(report["current_evidence_summary"]["source_repair_59_symbol_import_attempted"])
        self.assertFalse(report["current_evidence_summary"]["source_repair_59_symbol_quotes_imported"])
        self.assertEqual(report["current_evidence_summary"]["source_repair_59_symbol_missing_symbol_date_count"], 11565)
        source_repair_resume_meta = report["source_artifacts"]["source_repair_59_symbol_thetadata_opra_resume"]
        self.assertEqual(source_repair_resume_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["source_repair_59_symbol_resume_status"],
            "blocked_thetaterminal_source_unavailable_retry",
        )
        self.assertTrue(report["current_evidence_summary"]["source_repair_59_symbol_resume_approval_token_valid"])
        self.assertFalse(report["current_evidence_summary"]["source_repair_59_symbol_resume_import_attempted"])
        self.assertFalse(report["current_evidence_summary"]["source_repair_59_symbol_resume_quotes_imported"])
        self.assertEqual(report["current_evidence_summary"]["source_repair_59_symbol_resume_missing_symbol_date_count"], 11565)
        self.assertEqual(report["current_evidence_summary"]["source_repair_59_symbol_resume_protected_holdout_overlap_rows"], 0)
        self.assertEqual(report["current_evidence_summary"]["source_repair_59_symbol_resume_outside_universe_import_rows"], 0)
        direct_vix_meta = report["source_artifacts"]["direct_vix_source_repair_packet"]
        self.assertEqual(direct_vix_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["direct_vix_source_repair_packet_status"],
            "direct_vix_source_repair_packet_ready_for_operator_import_decision",
        )
        self.assertEqual(report["current_evidence_summary"]["direct_vix_source_family"], "direct_vix_daily_close")
        self.assertEqual(
            report["current_evidence_summary"]["direct_vix_source_baseline"]["point_in_time_vix_bucket_status"],
            "blocked_point_in_time_vix_source_missing",
        )
        self.assertEqual(report["current_evidence_summary"]["direct_vix_source_baseline"]["vix_source_rows_count"], 0)
        self.assertEqual(report["current_evidence_summary"]["direct_vix_source_baseline"]["vix_coverage_pct"], 0.0)
        self.assertFalse(report["current_evidence_summary"]["direct_vix_future_import_command_executed"])
        self.assertFalse(report["current_evidence_summary"]["direct_vix_downstream_vix_bucket_command_executed"])
        self.assertFalse(report["current_evidence_summary"]["direct_vix_quotes_imported"])
        self.assertFalse(report["current_evidence_summary"]["direct_vix_evidence_stores_mutated"])
        self.assertFalse(report["current_evidence_summary"]["direct_vix_protected_holdout_consumed"])
        self.assertTrue(report["current_evidence_summary"]["direct_vix_fixture_validation"]["known_at_safe"])
        self.assertEqual(
            report["current_evidence_summary"]["direct_vix_future_import_manifest_template"][
                "required_approval_token"
            ],
            "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
        )
        self.assertTrue(
            report["current_evidence_summary"]["direct_vix_branch_implications"][0][
                "would_clear_vix_blocker_if_future_source_passes"
            ]
        )
        momentum_implication = next(
            item
            for item in report["current_evidence_summary"]["direct_vix_branch_implications"]
            if item["branch"] == "momentum_continuation"
        )
        self.assertEqual(
            momentum_implication["remaining_non_vix_blockers"],
            [
                "missing_point_in_time_spy_momentum_confirmation",
                "missing_point_in_time_qqq_momentum_confirmation",
                "strict_rows_below_30_after_resolution",
            ],
        )
        macro_packet_meta = report["source_artifacts"]["macro_event_calendar_source_repair_packet"]
        self.assertEqual(macro_packet_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_calendar_source_repair_packet_status"],
            "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision",
        )
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_calendar_source_family"],
            "scheduled_macro_event_calendar_v1",
        )
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_calendar_source_baseline"][
                "macro_event_calendar_status"
            ],
            "blocked_macro_event_calendar_source_missing",
        )
        self.assertEqual(report["current_evidence_summary"]["macro_event_calendar_source_baseline"]["event_count"], 0)
        self.assertFalse(report["current_evidence_summary"]["macro_event_calendar_future_import_command_executed"])
        self.assertFalse(report["current_evidence_summary"]["macro_event_calendar_quotes_imported"])
        self.assertFalse(report["current_evidence_summary"]["macro_event_calendar_evidence_stores_mutated"])
        self.assertFalse(report["current_evidence_summary"]["macro_event_calendar_protected_holdout_consumed"])
        self.assertTrue(report["current_evidence_summary"]["macro_event_calendar_fixture_validation"]["known_at_safe"])
        self.assertEqual(
            report["current_evidence_summary"]["macro_event_calendar_future_import_manifest_template"][
                "required_approval_token"
            ],
            "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT",
        )
        self.assertTrue(
            report["current_evidence_summary"]["macro_event_calendar_branch_implications"][0][
                "would_clear_event_calendar_blocker_if_future_source_passes"
            ]
        )
        flow_packet_meta = report["source_artifacts"]["flow_extreme_source_repair_packet"]
        self.assertEqual(flow_packet_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_source_repair_packet_status"],
            "flow_extreme_source_repair_packet_ready_for_operator_import_decision",
        )
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_source_family"],
            "trusted_option_volume_open_interest_daily_v1",
        )
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_source_baseline"][
                "point_in_time_flow_extreme_input_status"
            ],
            "blocked_point_in_time_flow_extreme_input",
        )
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_source_baseline"][
                "flow_extreme_volume_oi_source_rows_status"
            ],
            "blocked_flow_extreme_volume_oi_source_rows",
        )
        self.assertFalse(report["current_evidence_summary"]["flow_extreme_future_import_command_executed"])
        self.assertFalse(report["current_evidence_summary"]["flow_extreme_quotes_imported"])
        self.assertFalse(report["current_evidence_summary"]["flow_extreme_evidence_stores_mutated"])
        self.assertFalse(report["current_evidence_summary"]["flow_extreme_protected_holdout_consumed"])
        self.assertTrue(report["current_evidence_summary"]["flow_extreme_fixture_validation"]["known_at_safe"])
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_future_import_manifest_template"][
                "required_approval_token"
            ],
            "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT",
        )
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_branch_implications"][0]["branch"],
            "flow_extreme_ratio_backspread",
        )
        underlying_acquisition_meta = report["source_artifacts"]["underlying_daily_source_acquisition"]
        self.assertEqual(underlying_acquisition_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["underlying_daily_source_acquisition_status"],
            "blocked_underlying_daily_source_acquisition_missing",
        )
        self.assertEqual(
            report["current_evidence_summary"]["underlying_daily_source_acquisition_blockers"],
            ["trusted_source_csv_missing"],
        )
        self.assertEqual(report["current_evidence_summary"]["underlying_daily_source_acquisition_candidate_file_count"], 0)
        self.assertEqual(report["current_evidence_summary"]["underlying_daily_source_acquisition_ready_candidate_count"], 0)
        self.assertIn(
            "APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT",
            report["current_evidence_summary"]["underlying_daily_source_acquisition_future_import_command"],
        )
        underlying_import_meta = report["source_artifacts"]["underlying_daily_source_import"]
        self.assertEqual(underlying_import_meta["status"], "loaded")
        self.assertEqual(
            report["current_evidence_summary"]["underlying_daily_source_import_status"],
            "blocked_underlying_daily_history_source_import",
        )
        self.assertFalse(report["current_evidence_summary"]["underlying_daily_source_import_source_rows_written"])
        self.assertIn("blocked_underlying_daily_source_acquisition_missing", report["prompt"])
        self.assertIn("market_data.db:daily_history", report["prompt"])
        self.assertIn("strategic reviewer and next-slice selector", report["prompt"])
        self.assertIn("Current Fact Table:", report["prompt"])
        self.assertIn("Evidence precedence:", report["prompt"])
        self.assertIn("Only real approved forward-cohort rows", report["prompt"])
        self.assertIn("source-row writes", report["prompt"])
        self.assertIn("default source_rows materialization", report["prompt"])
        self.assertIn("cohort-log append", report["prompt"])
        self.assertIn("VIX is cleared", report["prompt"])
        self.assertIn("Underlying daily OHLCV is a first-class blocker", report["prompt"])
        self.assertIn("Do not select another packet-only source plan", report["prompt"])
        self.assertIn("Approved non-live source materialization may be recommended", report["prompt"])
        self.assertIn("candidate_file_count=0", report["prompt"])
        self.assertIn("ready_candidate_count=0", report["prompt"])
        self.assertIn("selected_ready_source_file=null", report["prompt"])
        self.assertIn("bullish_pullback_layer4_forward_protocol", report["prompt"])
        self.assertIn("Re-emitting 6,916 blocked rows", report["prompt"])
        self.assertIn("priced_exact_rows", report["prompt"])
        self.assertIn("strict_new_exact_completed_rows", report["prompt"])
        self.assertIn("side-aware entry/exit", report["prompt"])
        self.assertIn("Required JSON-like output shape:", report["prompt"])
        self.assertNotIn("Output JSON-like structure:", report["prompt"])
        self.assertEqual(report["prompt"].count("Required JSON-like output shape:"), 1)
        self.assertIn("blocker_map", report["gpt55_required_output_schema"])
        self.assertIn("ranked_next_tasks", report["gpt55_required_output_schema"])
        self.assertIn("stale_blockers_ignored", report["gpt55_required_output_schema"])
        self.assertIn("loop_control_fallback", report["gpt55_required_output_schema"])
        self.assertIn("approval_required_for_selected_task", report["gpt55_required_output_schema"]["next_codex_task"])
        self.assertIn("safe_read_only_fallback_if_approval_missing", report["gpt55_required_output_schema"]["next_codex_task"])
        self.assertIn("source-row writes or default source_rows materialization", report["operator_approval_posture"]["still_requires_separate_explicit_approval"])
        self.assertIn("cohort-log append", report["operator_approval_posture"]["still_requires_separate_explicit_approval"])
        self.assertIn("Forward proof blocker", report["prompt"])
        self.assertIn("Do not select trusted_flow_volume_oi_source_repair_packet_v1 again", report["prompt"])
        self.assertEqual(report["profitability_target"]["minimum_profitable_strict_completed_rows"], 30)
        self.assertTrue(report["edge_discovery_requirements"]["stop_is_exceptional"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["quotes_imported"])

    def test_missing_frontier_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
            paths = self._paths(Path(tmp_dir))
            paths["frontier_path"].unlink()
            report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

        self.assertEqual(report["status"], "blocked_missing_required_artifact")
        self.assertIn("frontier", report["missing_required_artifacts"])

    def test_missing_flow_readiness_surfaces_named_status(self) -> None:
        with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
            paths = self._paths(Path(tmp_dir))
            paths["flow_extreme_ratio_backspread_replay_readiness_path"].unlink()
            report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

        self.assertEqual(report["status"], "ready_for_same_session_gpt55_guidance")
        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_status"],
            "missing_flow_extreme_ratio_backspread_replay_readiness_artifact",
        )
        self.assertIn(
            "missing_flow_extreme_ratio_backspread_replay_readiness_artifact",
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_reason_codes"],
        )
        self.assertIn("missing_flow_extreme_ratio_backspread_replay_readiness_artifact", report["prompt"])

    def test_malformed_flow_readiness_surfaces_named_status(self) -> None:
        with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
            paths = self._paths(Path(tmp_dir))
            paths["flow_extreme_ratio_backspread_replay_readiness_path"].write_text("{ not json", encoding="utf8")
            report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

        self.assertEqual(
            report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_status"],
            "malformed_flow_extreme_ratio_backspread_replay_readiness_artifact",
        )
        self.assertIn(
            "malformed_flow_extreme_ratio_backspread_replay_readiness_artifact",
            report["source_artifacts"]["flow_extreme_ratio_backspread_replay_readiness"]["validation_reason_codes"],
        )

    def test_flow_readiness_validation_rejects_invalid_stale_or_unsafe_artifacts(self) -> None:
        cases = [
            (
                "wrong_report_id",
                {"report_id": "wrong_report"},
                "invalid_flow_extreme_ratio_backspread_replay_readiness_report_id",
            ),
            (
                "wrong_concept_id",
                {"concept_id": "wrong_concept"},
                "invalid_flow_extreme_ratio_backspread_replay_readiness_concept_id",
            ),
            (
                "wrong_structure",
                {"structure": "wrong_structure"},
                "invalid_flow_extreme_ratio_backspread_replay_readiness_structure",
            ),
            (
                "stale_artifact",
                {"generated_at_utc": "2026-06-23T05:00:00Z"},
                "stale_flow_extreme_ratio_backspread_replay_readiness_artifact",
            ),
            (
                "unsafe_flags",
                {"broker_order_allowed": True},
                "unsafe_flow_extreme_ratio_backspread_replay_readiness_flags",
            ),
        ]
        for name, patch, expected_status in cases:
            with self.subTest(name=name):
                with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
                    paths = self._paths(Path(tmp_dir))
                    readiness_path = paths["flow_extreme_ratio_backspread_replay_readiness_path"]
                    payload = json.loads(readiness_path.read_text(encoding="utf8"))
                    payload.update(patch)
                    _write_json(readiness_path, payload)
                    report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

                self.assertEqual(
                    report["current_evidence_summary"]["flow_extreme_ratio_backspread_replay_readiness_status"],
                    expected_status,
                )
                self.assertIn(
                    expected_status,
                    report["source_artifacts"]["flow_extreme_ratio_backspread_replay_readiness"][
                        "validation_reason_codes"
                    ],
                )

    def test_pmcc_readiness_validation_surfaces_named_packet_status(self) -> None:
        cases = [
            (
                "missing",
                None,
                "missing_pmcc_diagonal_replay_readiness_artifact",
            ),
            (
                "wrong_report_id",
                {"report_id": "wrong_report"},
                "invalid_pmcc_diagonal_replay_readiness_report_id",
            ),
            (
                "wrong_concept_id",
                {"concept_id": "wrong_concept"},
                "invalid_pmcc_diagonal_replay_readiness_concept_id",
            ),
            (
                "wrong_structure",
                {"structure": "wrong_structure"},
                "invalid_pmcc_diagonal_replay_readiness_structure",
            ),
            (
                "stale_artifact",
                {"generated_at_utc": "2026-06-23T05:00:00Z"},
                "stale_pmcc_diagonal_replay_readiness_artifact",
            ),
            (
                "unsafe_flags",
                {"broker_order_allowed": True},
                "unsafe_pmcc_diagonal_replay_readiness_flags",
            ),
        ]
        for name, patch, expected_status in cases:
            with self.subTest(name=name):
                with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
                    paths = self._paths(Path(tmp_dir))
                    readiness_path = paths["pmcc_diagonal_replay_readiness_path"]
                    if patch is None:
                        readiness_path.unlink()
                    else:
                        payload = json.loads(readiness_path.read_text(encoding="utf8"))
                        payload.update(patch)
                        _write_json(readiness_path, payload)
                    report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

                self.assertEqual(
                    report["current_evidence_summary"]["pmcc_diagonal_replay_readiness_status"],
                    expected_status,
                )
                self.assertIn(
                    expected_status,
                    report["source_artifacts"]["pmcc_diagonal_replay_readiness"]["validation_reason_codes"],
                )

    def test_post_event_iv_crush_readiness_validation_surfaces_named_packet_status(self) -> None:
        cases = [
            (
                "missing_artifact",
                None,
                "missing_post_event_iv_crush_replay_readiness_artifact",
            ),
            (
                "wrong_report_id",
                {"report_id": "wrong_report"},
                "invalid_post_event_iv_crush_replay_readiness_report_id",
            ),
            (
                "wrong_concept_id",
                {"concept_id": "wrong_concept"},
                "invalid_post_event_iv_crush_replay_readiness_concept_id",
            ),
            (
                "wrong_structure",
                {"structure": "wrong_structure"},
                "invalid_post_event_iv_crush_replay_readiness_structure",
            ),
            (
                "stale_artifact",
                {"generated_at_utc": "2026-06-23T05:00:00Z"},
                "stale_post_event_iv_crush_replay_readiness_artifact",
            ),
            (
                "unsafe_flags",
                {"broker_order_allowed": True},
                "unsafe_post_event_iv_crush_replay_readiness_flags",
            ),
        ]
        for name, patch, expected_status in cases:
            with self.subTest(name=name):
                with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
                    paths = self._paths(Path(tmp_dir))
                    readiness_path = paths["post_event_iv_crush_replay_readiness_path"]
                    if patch is None:
                        readiness_path.unlink()
                    else:
                        payload = json.loads(readiness_path.read_text(encoding="utf8"))
                        payload.update(patch)
                        _write_json(readiness_path, payload)
                    report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **paths)

                self.assertEqual(
                    report["current_evidence_summary"]["post_event_iv_crush_replay_readiness_status"],
                    expected_status,
                )
                self.assertIn(
                    expected_status,
                    report["source_artifacts"]["post_event_iv_crush_replay_readiness"]["validation_reason_codes"],
                )

    def test_write_outputs_writes_prompt_and_json(self) -> None:
        with WorkspaceTempDir(prefix="oracle-loop-packet") as tmp_dir:
            tmp = Path(tmp_dir)
            report = packet.build_packet(generated_at_utc="2026-06-22T00:00:00Z", **self._paths(tmp))
            artifacts = packet.write_outputs(report, output_json=tmp / "out.json", output_md=tmp / "out.md")

            self.assertTrue((tmp / "out.json").exists())
            self.assertTrue((tmp / "out.md").exists())
            self.assertEqual(artifacts["json"], str((tmp / "out.json").resolve()).replace("\\", "/"))
            self.assertIn("Options Oracle Profit Loop Packet", (tmp / "out.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
