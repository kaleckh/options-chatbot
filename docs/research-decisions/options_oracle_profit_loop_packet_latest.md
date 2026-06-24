# Options Oracle Profit Loop Packet

This artifact is the reusable same-session GPT-5.5 Pro handoff for the regular-options profitability loop.

## Status

- Status: `ready_for_same_session_gpt55_guidance`.
- Frontier status: `current_historical_surface_exhausted_under_current_prohibitions`.
- Countable throughput candidate found: `False`.
- Raw count candidates: `11`.
- Decision counts: `{"blocked_below_strict_new_count": 33, "blocked_execution_quality": 2, "rejected_negative_or_flat_edge": 9}`.

## Continuation Branches

- `fresh_forward_paper_shadow_collection`: requires approval `true`; Only fresh post-freeze executable rows can become proof-qualified profitability.
- `scoped_source_repair_or_replay`: requires approval `true`; May require quote import, evidence repair, or source-surface mutation; must be explicitly scoped.
- `new_causal_playbook_generation`: requires approval `false`; Read-only preregistration/falsification can continue without live or evidence mutation.
- `new_historical_data_surface_or_longer_lookback`: requires approval `true`; Changes the data surface and can invalidate prior branch-scoped stop verdicts.
- `dashboard_or_operator_visibility`: requires approval `false`; Useful only if it changes execution decisions; not significant by itself unless tied to a proof blocker.

## Prompt

```text
Replace the current 5.5 Pro handoff prompt with this profitability-first blocker-ranking prompt before continuing the loop.

We are running an options-profitability loop. The user's goal is profit: at least 30 profitable strict completed forward-audit trades in the latest approximately 4-month/post-freeze audit window.

Current state:
- We are not forward-audit profitable.
- Strict completed forward proof is currently 0/30.
- Historical rows, dashboard rows, midpoint/stale/EOD/last/model/manual/synthetic/lookahead rows, and old-algorithm picks are not accepted profitability proof.
- Codex can implement, test, inspect the repo, build artifacts, run read-only research, and run non-live/non-broker source-planning tasks.
- The user approves non-live, non-broker research/source-planning work.
- Broker orders, live validation, auto-track, protected-holdout consumption, promotion, production scanner/strategy/stop/sizing/proof-bar changes, and real source/evidence mutation still require exact explicit approval.

Your job:
Do not optimize for documentation completeness. Do not choose the safest artifact by default. Optimize for the shortest honest path to 30 profitable strict completed forward-audit trades.

Before selecting a task, produce a blocker map with these categories:

1. Forward proof blocker
- Why are there 0/30 strict completed forward rows?
- Are current scanners producing real same-day candidates?
- If not, what is the fastest way to increase real candidate throughput without fake rows?

2. Candidate-generation blocker
- Is the current algorithm generating enough eligible candidates?
- If candidate generation is missing/broken, what exact repair unlocks real rows fastest?
- Do not accept quote-depth-only coverage as candidate-generation proof.

3. Data/source blocker
- Which missing point-in-time sources block the most downstream profitable tests?
- Current or recently cleared source blockers include VIX, macro-event calendar, flow volume/OI, dispersion/concentration, trend/regime, and possibly broader OPRA/NBBO coverage. Use the attached current artifacts: if VIX is `point_in_time_vix_bucket_ready`, do not rank VIX as still missing.
- Rank source repairs by downstream unlock value and time-to-test.
- Do not select another packet-only source plan unless it is the highest-leverage blocker to running a real replay or forward audit.

4. Replay/engine blocker
- Which strategies cannot be honestly tested because pricing/replay engine support is missing?
- Consider credit spreads, calendars, diagonals, condors, butterflies, ratio/backspreads, straddles/strangles, PMCC-style diagonals, debit/credit hybrids.
- Rank engine work by ability to unlock countable exact rows.

5. Strategy/edge blocker
- Are we testing enough option edge families?
- Consider volatility risk premium, skew, term structure, event volatility, IV crush, post-event drift, momentum continuation, mean reversion, dispersion proxy, and flow/liquidity effects.
- Do not assume existing directional debit-spread surfaces exhaust the opportunity set.

6. Historical audit blocker
- Can the existing 2-year data be used to produce a strict simulated-forward audit?
- If not, name the exact missing chain: candidate-generation surface, source depth, quote coverage, strict-new dedupe, exact bid/ask pricing, or holdout/proof issue.
- Do not say "collect more data" unless you name the exact file/source/command/threshold.

7. Dashboard/operator blocker
- Only choose dashboard work if it directly changes operator decisions or forward evidence capture.
- Dashboard visibility alone is not a profit upgrade.

Then rank all possible next tasks by:
- expected increase in countable profitable rows,
- chance of unlocking a replay or forward audit,
- time-to-test,
- number of downstream branches unblocked,
- overfit/leakage/data-integrity risk,
- whether it can be done now without live/broker action.

Return exactly one next Codex task.

The selected task must include:
- objective,
- why this is the highest-leverage path to profitability,
- exact files/artifacts allowed,
- exact files/artifacts forbidden,
- implementation steps,
- commands to run,
- acceptance criteria,
- failure criteria,
- what downstream replay/audit becomes possible if it passes,
- what branch should be stopped if it fails.

Hard rules:
- Do not repeat a branch already marked parked unless new source state changed.
- Do not select macro_event_calendar_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select direct_point_in_time_vix_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select trusted_flow_volume_oi_source_repair_packet_v1 again if the attached/current artifact status is flow_extreme_source_repair_packet_ready_for_operator_import_decision; it is already implemented and verified.
- Do not select the 59-symbol ThetaTerminal retry again until provider/source availability changes.
- Do not select historical dashboard/picks visibility unless it directly affects forward capture.
- Do not claim profitability from historical rows alone.
- Do not stop unless you prove no meaningful upgrade remains across forward capture, source repair/materialization, candidate-generation repair, replay engine support, new option structures, and longer/lookback audits.

Output JSON-like structure:
{
  "verdict": "continue|stop_exception",
  "continue_loop": true/false,
  "current_profitability_state": {
    "forward_strict_completed_rows": number,
    "target_rows": 30,
    "accepted_profitability": true/false,
    "main_reason_not_profitable": "string"
  },
  "blocker_map": {
    "forward_proof": [],
    "candidate_generation": [],
    "data_sources": [],
    "replay_engine": [],
    "strategy_edges": [],
    "historical_audit": [],
    "dashboard_operator": []
  },
  "ranked_next_tasks": [
    {
      "rank": 1,
      "task_id": "string",
      "expected_profitability_impact": "string",
      "downstream_unlocks": [],
      "time_to_test": "string",
      "why_not_selected_if_applicable": null
    }
  ],
  "selected_branch_id": "string",
  "next_codex_task": {
    "objective": "string",
    "why_highest_leverage": "string",
    "exact_scope": "string",
    "allowed_files_or_artifacts": [],
    "forbidden_actions": [],
    "implementation_steps": [],
    "commands_to_run": [],
    "acceptance_criteria": [],
    "failure_criteria": [],
    "downstream_enabled_if_passes": [],
    "branch_stop_condition_if_fails": "string"
  },
  "branches_to_stop": [],
  "operator_questions": [],
  "anti_handwave_audit": {
    "exact_next_action_present": true,
    "measurable_threshold_present": true,
    "generic_advice_removed": true
  }
}

Current repo evidence appendix follows. Use this evidence for the blocker map and next-task ranking; do not ignore completed/parked artifacts.

We are continuing the same regular-options profitability loop in the existing GPT-5.5 Pro ChatGPT session.

You are GPT-5.5 Pro acting as strategic reviewer and next-slice selector. Codex will implement and verify. The user wants this loop to continue until GPT-5.5 Pro says there are no significant upgrades left.

Operator approval posture:
{
  "fixture_temp_verification_generated_artifacts": "pre_approved_by_user_for_loop_continuation",
  "questions_to_gpt55": "Do not block on read-only/research-only operator questions; state the assumption as approved and choose the next task.",
  "read_only_research_only_work": "pre_approved_by_user_for_loop_continuation",
  "still_requires_separate_explicit_approval": [
    "broker orders or order preparation",
    "live validation",
    "auto-track enablement",
    "production scanner, strategy, stop, sizing, or proof-bar changes",
    "quote import",
    "protected-holdout consumption",
    "promotion",
    "unsafe evidence-store mutation"
  ]
}

Primary goal:
Make the regular-options workflow profitable under proof-qualified criteria. The practical target is at least 30 profitable strict completed rows in the latest approximately four months / post-freeze forward-style audit window. Profit means executable exact net P&L after fees/slippage, defensible PF/lower-bound/holdout/forward proof, and no unresolved data-quality defects that could flip the result. Do not accept raw overlapping historical count, midpoint/stale/display/EOD/last/model/manual marks, lookahead-only rows, zero-bid/untradable rows, or historical dashboard/replay rows as live proof.

Current proof posture:
- The system is not forward-audit profitable.
- Strict post-freeze forward proof is currently 0/30 completed exact rows.
- The historical current-policy replay panel was removed from the operator dashboard because it could be mistaken for current recommendations or forward-audit performance.
- The latest-four-month simulated audit is hypothesis-generating only unless its row set, data depth, leakage controls, and PF lower-bound satisfy the strict proof contract.

Current frontier result:
{
  "base_clean_stack_exact_rows": 157,
  "candidate_count": 44,
  "countable_throughput_candidate_found": false,
  "current_historical_surface_exhausted_under_current_prohibitions": true,
  "decision_counts": {
    "blocked_below_strict_new_count": 33,
    "blocked_execution_quality": 2,
    "rejected_negative_or_flat_edge": 9
  },
  "raw_count_candidate_count": 11,
  "status": "current_historical_surface_exhausted_under_current_prohibitions",
  "strict_new_gap_required": 43,
  "target_exact_rows": 200
}

Current momentum-edge result:
{
  "countable_momentum_edge_candidate_count": 0,
  "decision_counts": {
    "blocked_below_trade_count_target": 5,
    "raw_count_target_met_but_not_countable_edge": 2,
    "rejected_negative_or_flat_edge": 10
  },
  "status": "raw_count_available_but_not_countable_profitable_edge"
}

Current causal-falsification result, if available:
{
  "branches_to_stop": [
    "raw overlapping count aggregation",
    "tracked-winner count retuning without new causal evidence",
    "clean index/IWM refill as the primary gap closer",
    "existing current-regime momentum-compatible artifact aggregation"
  ],
  "continue_loop": true,
  "hypothesis_status_counts": {
    "falsified_existing_surface": 4,
    "not_falsified_requires_next_oracle_or_operator_selection": 1
  },
  "significant_upgrade_available": true,
  "status": "existing_surface_falsified_new_causal_branch_still_possible"
}

Current preregistered playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation, replay, quote import, evidence mutation, or forward collection requires a separate explicit decision.",
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "lane_implementation_performed": false,
  "status": "preregistered_design_only"
}

Current approved momentum-continuation research replay result, if available:
{
  "accepted_profitability": false,
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "denominator_rows": 1291,
  "denominator_status_counts": {
    "duplicate_within_research_harness": 461,
    "missing_point_in_time_vix_bucket": 415,
    "rejected_not_call_debit_spread": 237,
    "rejected_outside_preregistered_universe": 178
  },
  "diagnostic_only_metrics": {
    "avg_pnl_usd": -65.68,
    "gross_loss_usd": 239470.75,
    "gross_win_usd": 180623.09,
    "loss_count": 427,
    "net_pnl_usd": -58847.66,
    "priced_row_count": 896,
    "profit_factor": 0.7543,
    "row_count": 896,
    "win_count": 469,
    "win_rate_pct": 52.34
  },
  "historical_replay_performed": true,
  "lane_implementation_performed": false,
  "proof_metrics": {
    "avg_pnl_usd": null,
    "gross_loss_usd": 0,
    "gross_win_usd": 0,
    "loss_count": 0,
    "net_pnl_usd": null,
    "priced_row_count": 0,
    "profit_factor": null,
    "row_count": 0,
    "win_count": 0,
    "win_rate_pct": null
  },
  "proof_qualified_rows": 0,
  "research_only_replay_harness_implemented": true,
  "status": "implemented_research_replay_no_proof_qualified_rows",
  "top_blockers": [
    {
      "reason": "missing_point_in_time_breadth_confirmation",
      "row_count": 1291
    },
    {
      "reason": "missing_point_in_time_vix_bucket",
      "row_count": 1291
    },
    {
      "reason": "missing_side_aware_exit_bid_ask",
      "row_count": 1291
    },
    {
      "reason": "missing_point_in_time_qqq_momentum_confirmation",
      "row_count": 1080
    },
    {
      "reason": "spread_diagnostics_marked_diagnostic_only",
      "row_count": 1064
    },
    {
      "reason": "entry_contains_mid_quote_basis",
      "row_count": 896
    },
    {
      "reason": "duplicate_within_research_harness",
      "row_count": 461
    },
    {
      "reason": "missing_net_usd_pnl",
      "row_count": 395
    },
    {
      "reason": "missing_point_in_time_spy_momentum_confirmation",
      "row_count": 395
    },
    {
      "reason": "rejected_not_call_debit_spread",
      "row_count": 290
    },
    {
      "reason": "rejected_outside_preregistered_universe",
      "row_count": 277
    },
    {
      "reason": "missing_side_aware_entry_bid_ask",
      "row_count": 227
    }
  ]
}

Current momentum-continuation proof-blocker resolution result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "bootstrap_pf_lower_bound_not_above_1_after_resolution",
    "duplicate_within_research_harness",
    "entry_missing_leg_quote",
    "exit_missing_leg_quote",
    "exit_value_negative",
    "exit_zero_or_nonpositive_bid_ask",
    "missing_net_usd_pnl",
    "missing_point_in_time_breadth_confirmation",
    "missing_point_in_time_qqq_momentum_confirmation",
    "missing_point_in_time_spy_momentum_confirmation",
    "missing_point_in_time_vix_bucket",
    "net_usd_not_positive_after_resolution",
    "rejected_not_call_debit_spread",
    "rejected_outside_preregistered_universe",
    "strict_rows_below_30_after_resolution"
  ],
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "historical_rows_are_forward_proof": false,
  "proof_qualified_rows_after_resolution": 0,
  "proof_qualified_rows_before_resolution": 0,
  "reconstructed_denominator_rows": 1291,
  "resolution_counts": {
    "blocker_counts": {
      "duplicate_within_research_harness": 461,
      "entry_missing_leg_quote": 227,
      "exit_missing_leg_quote": 413,
      "exit_value_negative": 6,
      "exit_zero_or_nonpositive_bid_ask": 95,
      "missing_net_usd_pnl": 395,
      "missing_point_in_time_breadth_confirmation": 1291,
      "missing_point_in_time_qqq_momentum_confirmation": 1080,
      "missing_point_in_time_spy_momentum_confirmation": 395,
      "missing_point_in_time_vix_bucket": 1291,
      "rejected_not_call_debit_spread": 290,
      "rejected_outside_preregistered_universe": 277
    },
    "full_denominator_fail_closed": 1291,
    "point_in_time_inputs_resolved": 0,
    "proof_qualified_candidate_rows": 0,
    "side_aware_quotes_resolved": 783
  },
  "side_aware_diagnostic_metrics": {
    "avg_pnl_usd": 201.07,
    "bootstrap_pf_lower_bound_5pct": null,
    "gross_loss_usd": 121252.6,
    "gross_win_usd": 278693.8,
    "loss_count": 281,
    "net_pnl_usd": 157441.2,
    "priced_row_count": 783,
    "profit_factor": 2.2985,
    "row_count": 783,
    "stress_pf": 2.2985,
    "win_count": 502,
    "win_rate_pct": 64.11
  },
  "source_denominator_rows": 1291,
  "status": "momentum_continuation_blocked_missing_local_proof_inputs",
  "strict_research_metrics": {
    "avg_pnl_usd": null,
    "bootstrap_pf_lower_bound_5pct": null,
    "gross_loss_usd": 0,
    "gross_win_usd": 0,
    "loss_count": 0,
    "net_pnl_usd": null,
    "priced_row_count": 0,
    "profit_factor": null,
    "row_count": 0,
    "stress_pf": null,
    "win_count": 0,
    "win_rate_pct": null
  }
}

Current momentum-continuation bounded replay gate result, if available:
{
  "accepted_profitability": false,
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "existing_resolution_consumed": true,
  "historical_replay_performed": false,
  "historical_rows_are_forward_proof": false,
  "metrics": {
    "blocker_counts": {
      "duplicate_within_research_harness": 461,
      "entry_missing_leg_quote": 227,
      "exit_missing_leg_quote": 413,
      "exit_value_negative": 6,
      "exit_zero_or_nonpositive_bid_ask": 95,
      "missing_net_usd_pnl": 395,
      "missing_point_in_time_breadth_confirmation": 1291,
      "missing_point_in_time_qqq_momentum_confirmation": 1080,
      "missing_point_in_time_spy_momentum_confirmation": 395,
      "missing_point_in_time_vix_bucket": 1291,
      "rejected_not_call_debit_spread": 290,
      "rejected_outside_preregistered_universe": 277
    },
    "exact_completed_rows": 0,
    "latest_audit_30_row_bar_met": false,
    "minimum_historical_exact_rows": 200,
    "old_mark_diagnostic_metrics": {
      "avg_pnl_usd": -65.68,
      "gross_loss_usd": 239470.75,
      "gross_win_usd": 180623.09,
      "loss_count": 427,
      "net_pnl_usd": -58847.66,
      "priced_row_count": 896,
      "profit_factor": 0.7543,
      "row_count": 896,
      "win_count": 469,
      "win_rate_pct": 52.34
    },
    "point_in_time_inputs_resolved": 0,
    "proof_qualified_rows_after_resolution": 0,
    "quote_coverage": 0.6065,
    "replay_gate_blocker_count": 15,
    "side_aware_diagnostic_metrics": {
      "avg_pnl_usd": 201.07,
      "bootstrap_pf_lower_bound_5pct": null,
      "gross_loss_usd": 121252.6,
      "gross_win_usd": 278693.8,
      "loss_count": 281,
      "net_pnl_usd": 157441.2,
      "priced_row_count": 783,
      "profit_factor": 2.2985,
      "row_count": 783,
      "stress_pf": 2.2985,
      "win_count": 502,
      "win_rate_pct": 64.11
    },
    "side_aware_quotes_resolved": 783,
    "strict_new_exact_completed_rows": 0,
    "strict_research_metrics": {
      "avg_pnl_usd": null,
      "bootstrap_pf_lower_bound_5pct": null,
      "gross_loss_usd": 0,
      "gross_win_usd": 0,
      "loss_count": 0,
      "net_pnl_usd": null,
      "priced_row_count": 0,
      "profit_factor": null,
      "row_count": 0,
      "stress_pf": null,
      "win_count": 0,
      "win_rate_pct": null
    },
    "total_denominator_rows": 1291
  },
  "next_oracle_instruction": "Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time VIX/breadth input surface or explicit approved data repair changes the blocker. Select the next materially different, falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows.",
  "replay_gate_blockers": [
    "bootstrap_pf_lower_bound_not_above_1_after_resolution",
    "duplicate_within_research_harness",
    "entry_missing_leg_quote",
    "exit_missing_leg_quote",
    "exit_value_negative",
    "exit_zero_or_nonpositive_bid_ask",
    "missing_net_usd_pnl",
    "missing_point_in_time_breadth_confirmation",
    "missing_point_in_time_qqq_momentum_confirmation",
    "missing_point_in_time_spy_momentum_confirmation",
    "missing_point_in_time_vix_bucket",
    "net_usd_not_positive_after_resolution",
    "rejected_not_call_debit_spread",
    "rejected_outside_preregistered_universe",
    "strict_rows_below_30_after_resolution"
  ],
  "status": "blocked_momentum_continuation_bounded_replay"
}

Current preregistered VRP credit-spread playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_put_credit_spreads_only"
}

Current VRP credit-spread replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If blocked, GPT-5.5 Pro should decide whether a named blocker needs operator approval or whether another read-only option-structure branch remains.",
  "blockers": [
    "missing_credit_spread_side_aware_pricing_engine",
    "missing_credit_spread_side_aware_exit_pricing_engine",
    "missing_full_denominator_status_mapping",
    "missing_assignment_expiration_classifier",
    "missing_margin_max_loss_convention",
    "missing_index_credit_spread_quote_surface",
    "missing_protected_holdout_guard"
  ],
  "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "blocked_vrp_credit_spread_replay_readiness"
}

Current preregistered term-structure calendar/diagonal playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_calendar_or_diagonal_debit_spreads_only"
}

Current term-structure calendar/diagonal replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If ready, the next step is an exact operator approval question for one research-only implementation/replay harness. If blocked, GPT-5.5 Pro should decide whether a named blocker needs approval or whether another read-only option-structure branch remains.",
  "blockers": [
    "missing_calendar_diagonal_side_aware_pricing_engine",
    "missing_calendar_diagonal_exit_or_expiry_engine",
    "missing_full_denominator_status_mapping",
    "missing_front_leg_assignment_expiration_classifier",
    "missing_roll_or_expiry_policy",
    "missing_point_in_time_term_structure_inputs",
    "missing_index_calendar_quote_surface",
    "missing_strict_new_dedupe"
  ],
  "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "blocked_term_structure_calendar_replay_readiness"
}

Current preregistered skew broken-wing playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_skew_broken_wing_put_fly_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_broken_wing_put_butterflies_only"
}

Current preregistered macro-event long straddle/strangle playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_long_straddles_or_strangles_only"
}

Current macro-event calendar artifact result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "macro_event_calendar_source_missing",
    "missing_required_macro_event_categories"
  ],
  "covered_categories": [],
  "event_calendar_implemented": true,
  "event_count": 0,
  "historical_replay_performed": false,
  "missing_categories": [
    "cpi",
    "fomc_minutes",
    "fomc_rate_decision",
    "nonfarm_payrolls",
    "pce",
    "scheduled_fed_chair_testimony"
  ],
  "source_rows_proof_eligible": false,
  "status": "blocked_macro_event_calendar_source_missing"
}

Current point-in-time VIX bucket artifact result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
  "coverage_pct": 100.0,
  "covered_date_count": 505,
  "historical_replay_performed": false,
  "late_known_at_count": 0,
  "leakage_reject_count": 0,
  "point_in_time_vix_low_mid_bucket_available": true,
  "requested_date_count": 505,
  "source_rows_count": 505,
  "source_status": "loaded",
  "status": "point_in_time_vix_bucket_ready"
}

Current macro-event long straddle/strangle replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this readiness artifact back to GPT-5.5 Pro for continue/stop. A later bounded read-only replay requires a separate Codex task, and still cannot enable live validation, auto-track, broker orders, quote import, evidence mutation, protected-holdout consumption, scanner release, proof-bar changes, or promotion.",
  "blockers": [
    "macro_event_calendar_source_missing"
  ],
  "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "smallest_next_blocker_clearing_slice": {
    "blocker": "macro_event_calendar_source_missing",
    "smallest_future_codex_slice": "Clear exactly this named blocker with a read-only artifact before replay."
  },
  "status": "blocked_macro_event_long_strangle_replay_readiness"
}

Current 13-symbol candidate-generation surface audit result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "existing_candidate_generation_surface_not_frozen_13_symbol",
    "missing_candidate_generation_diagnostics",
    "not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof",
    "quote_depth_only_months_cannot_count",
    "source_artifact_universe_not_13_symbol"
  ],
  "candidate_surface": {
    "frozen_universe_exact_13_symbols": false,
    "non_13_symbol_selected_row_count": 0,
    "outside_allowed_universe": [
      "AA",
      "ABBV",
      "AMD",
      "AMT",
      "AMZN",
      "ARM",
      "BA",
      "BAC",
      "C",
      "CAT",
      "CLF",
      "COIN",
      "COST",
      "DE",
      "DIS",
      "EQR",
      "FCX",
      "GS",
      "JPM",
      "KO",
      "LIN",
      "LMT",
      "MCD",
      "META",
      "MSFT",
      "MSTR",
      "NFLX",
      "NKE",
      "NVDA",
      "OXY",
      "PFE",
      "PG",
      "PLD",
      "PLTR",
      "PM",
      "RTX",
      "SBUX",
      "SLB",
      "SMCI",
      "SPG",
      "T",
      "TSLA",
      "V",
      "WELL",
      "WMT",
      "XLK"
    ]
  },
  "cvx_scope": {
    "cvx_scope_enforced": true,
    "excluded_months": [],
    "excluded_trade_count": 0,
    "minimum_executable_quote_pct": 90.0,
    "observed_executable_quote_pct": 88.66,
    "policy_blocker": null,
    "policy_loaded": true,
    "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
    "rule_status": "active"
  },
  "historical_rows_are_forward_proof": false,
  "quote_vs_candidate_generation": {
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "distinction": "quote-history coverage does not prove pick/no-pick candidate-generation coverage",
    "quote_surface_months_available": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "quote_surface_months_available_count": 24,
    "selected_trade_depth_months_covered": [
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03"
    ],
    "selected_trade_depth_months_covered_count": 8
  },
  "runner_support": {
    "candidate_commands": [
      "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json"
    ],
    "read_only_no_write_runner_available": true,
    "rejected_commands": [],
    "source_artifact_status": "candidate_generation_no_write_runner_ready_with_blockers",
    "status": "read_only_no_write_runner_available",
    "support_manifest": {
      "as_of_date": "2026-06-04",
      "as_of_gated": true,
      "candidate_commands": [
        "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json"
      ],
      "evidence_stores_mutated": false,
      "frozen_universe_exact_13_symbols": true,
      "mutating": false,
      "no_write": true,
      "pre_holdout_as_of": true,
      "production_scanner_changed": false,
      "proof_bars_changed": false,
      "protected_holdout_consumed": false,
      "quotes_imported": false,
      "read_only": true,
      "read_only_no_write_runner_available": true,
      "research_only": true,
      "sizing_changed": false,
      "stops_changed": false,
      "strategy_logic_changed": false,
      "universe_filter": true
    },
    "validation_reason_codes": []
  },
  "status": "blocked_13_symbol_candidate_generation_surface_audit"
}

Current frozen 13-symbol reusable candidate-generation entrypoint result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "missing_daily_candidate_generation_diagnostics",
    "source_artifact_universe_not_13_symbol"
  ],
  "coverage": {
    "blocked_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "zero_selection_months": [],
    "zero_selection_months_explicit": false
  },
  "daily_candidate_generation_row_count": 6916,
  "daily_status_counts": {
    "blocked_missing_daily_candidate_generation_diagnostics": 6916
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "read_only": true,
  "selected_candidate_row_count": 0,
  "status": "blocked_frozen_13_symbol_candidate_generation_entrypoint"
}

Current 13-symbol frozen candidate-generation source-surface materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "missing_daily_candidate_generation_diagnostics",
    "source_artifact_universe_not_13_symbol"
  ],
  "calendar_coverage": {
    "calendar_months_covered": [],
    "calendar_months_covered_count": 0,
    "coverage_basis": "source_surface_not_frozen_13_symbol_or_missing_month_diagnostics",
    "covered_months": [],
    "status": "calendar_coverage_not_proven",
    "unproven_requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "zero_selection_months": [],
    "zero_selection_months_explicit": false
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "posthoc_filtering_allowed_as_proof": null,
  "read_only": true,
  "selected_trade_summary": {
    "selected_entry_months_with_rows": [],
    "selected_rows_in_window": 0
  },
  "source_artifact_universe_exact_13_symbols": null,
  "status": "blocked_13_symbol_frozen_candidate_generation_source_surface"
}

Current frozen 13-symbol candidate-generation engine result, if available:
{
  "accepted_profitability": false,
  "audit_consumed_generated_surface": false,
  "blockers": [
    "blocked_daily_candidate_generation_coverage",
    "blocked_latest_audit_rows_below_30",
    "blocked_train_or_audit_month_coverage",
    "candidate_generation_months_0_below_requested_24",
    "missing_daily_candidate_generation_diagnostics",
    "source_artifact_universe_not_13_symbol"
  ],
  "coverage": {
    "audit_months_covered": 0,
    "blocked_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "latest_audit_exact_trades": 0,
    "latest_four_strict_new_candidates": 0,
    "missing_daily_diagnostics": 24,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "train_months_covered": 0
  },
  "daily_candidate_generation_row_count": 6916,
  "decision": "blocked_frozen_candidate_generation_entrypoint_incomplete",
  "historical_simulated_forward_audit_command": null,
  "legacy_blocker_aliases": [
    "missing_frozen_13_symbol_candidate_generation_engine"
  ],
  "no_write": true,
  "read_only": true,
  "reusable_entrypoint_discovery": {
    "artifact_path": "C:\\Users\\kalec\\options-chatbot\\data\\profitability-lab\\regular-options-13-symbol-frozen-candidate-generation-entrypoint\\latest.json",
    "artifact_status": "blocked_frozen_13_symbol_candidate_generation_entrypoint",
    "available": true,
    "basis": "frozen_entrypoint_artifact",
    "entrypoint": "scripts/regular_options_frozen_candidate_generation_entrypoint.py"
  },
  "selected_candidate_row_count": 0,
  "status": "blocked_frozen_13_symbol_candidate_generation_engine"
}

Interpretation: the reusable frozen entrypoint now exists, but the real latest readback still has 0/24 covered candidate-generation months and 0 selected candidates because every daily row is blocked by missing daily candidate-generation diagnostics. Do not repeat the 13-symbol source-surface/no-write/denominator/engine branch unless a real daily frozen candidate-generation source changes this blocker. Treat quote depth alone as insufficient. Choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current preregistered post-event IV-crush iron-condor playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "post_event_iv_crush_index_iron_condor_v1",
  "event_calendar_implemented_in_this_slice": false,
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_short_iron_condors_or_iron_butterflies_only"
}

Current preregistered flow-extreme ratio/backspread playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk spreads, and promotion.",
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_ratio_spreads_or_backspreads_only",
  "undefined_risk_allowed": false
}

Current flow-extreme volume/open-interest source-row generator result, if available:
{
  "accepted_profitability": false,
  "aggregate_source_summary": {
    "aggregate_row_count": 1635,
    "data_trust": "trusted",
    "date_count": 501,
    "snapshot_kind": "intraday",
    "source_labels": [
      "thetadata_opra_nbbo_1m"
    ],
    "usable_aggregate_row_count": 0
  },
  "blockers": [
    "missing_trusted_volume_open_interest_source_rows",
    "trusted_rows_have_null_volume_open_interest",
    "insufficient_month_coverage",
    "insufficient_date_coverage"
  ],
  "coverage": {
    "covered_date_count": 0,
    "covered_month_count": 0,
    "covered_months": [],
    "date_coverage_pct": 0.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ]
  },
  "evidence_stores_mutated": false,
  "historical_rows_are_forward_proof": false,
  "quotes_imported": false,
  "source_row_count": 0,
  "status": "blocked_flow_extreme_volume_oi_source_rows",
  "threshold_policy": {
    "flow_input_basis": "volume_open_interest",
    "future_outcomes_used": false,
    "known_at_rule": "prior trusted source date strictly before input_date_et",
    "outcome_tuned": false,
    "plain_bid_ask_used_as_flow": false,
    "quote_depth_fabricated": false,
    "realized_pnl_used": false,
    "selected_winners_used": false,
    "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1"
  },
  "write_source_rows_allowed": false
}

Current point-in-time flow-extreme input materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "missing_point_in_time_flow_extreme_source",
    "missing_required_flow_fields",
    "insufficient_month_coverage",
    "insufficient_date_coverage"
  ],
  "coverage": {
    "covered_date_count": 0,
    "covered_month_count": 0,
    "covered_months": [],
    "date_coverage_pct": 0.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "required_underlyings": [
      "QQQ",
      "SPY"
    ]
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "proxy_basis": [],
  "read_only": true,
  "source_inventory": {
    "feature_store": {
      "available_symbols": [
        "QQQ",
        "SPY"
      ],
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-18T06:09:35Z",
      "inventory_status": "feature_store_loaded_for_underlyings",
      "missing_symbols": [],
      "path": "data/profitability-lab/regular-options-feature-store/latest.json",
      "report_id": "regular_options_feature_store",
      "requested_date_count": 494,
      "required": true,
      "status": "loaded",
      "status_value": "feature_store_built"
    },
    "options_history_db": {
      "error": null,
      "exists": true,
      "flow_columns": {
        "ask_size": false,
        "bid_size": false,
        "open_interest": true,
        "quote_depth": false,
        "volume": true
      },
      "path": "data/options-validation/options_history.db",
      "status": "loaded",
      "tables": {
        "import_batches": [
          "id",
          "source_label",
          "dataset_kind",
          "data_trust",
          "input_path",
          "file_hash",
          "imported_at_utc",
          "total_rows",
          "imported_rows",
          "duplicate_rows",
          "rejected_rows",
          "warnings_json"
        ],
        "option_quote_snapshots": [
          "id",
          "as_of_utc",
          "quote_date_et",
          "quote_minute_et",
          "snapshot_kind",
          "underlying",
          "contract_symbol",
          "expiry",
          "option_type",
          "strike",
          "bid",
          "ask",
          "last",
          "iv",
          "underlying_price",
          "volume",
          "open_interest",
          "source_batch_id"
        ],
        "sqlite_sequence": [
          "name",
          "seq"
        ]
      }
    },
    "plain_bid_ask_only_is_not_flow": true,
    "preregistered_playbook": {
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-23T05:51:48Z",
      "path": "data/profitability-lab/regular-options-preregistered-flow-extreme-ratio-backspread-playbook/latest.json",
      "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
      "required": true,
      "status": "loaded",
      "status_value": "preregistered_design_only"
    },
    "schema_declared_flow_basis": {
      "bid_ask_size_imbalance": false,
      "quote_depth_pressure": false,
      "volume_open_interest": true
    },
    "source_rows": {
      "error": null,
      "exists": false,
      "path": "data/profitability-lab/regular-options-point-in-time-flow-extreme-input/source_rows.jsonl",
      "required": false,
      "row_count": 0,
      "status": "missing"
    },
    "status": "missing_flow_source_rows"
  },
  "status": "blocked_point_in_time_flow_extreme_input"
}

Current multi-leg side-aware pricing capability result, if available:
{
  "accepted_profitability": false,
  "fixture_source_not_proof_eligible": true,
  "historical_rows_are_forward_proof": false,
  "pricing_capability_blockers": [],
  "quote_resolution_counts": {
    "blocker_counts": {},
    "fixture_count": 1,
    "resolved_fixture_count": 1,
    "status_counts": {
      "exact_exit_captured": 1
    }
  },
  "source_inventory": {
    "bid_ask_schema_fields": [
      "bid",
      "ask"
    ],
    "contract_symbol_fields": [
      "underlying",
      "contract_symbol",
      "expiry",
      "option_type",
      "strike"
    ],
    "error": null,
    "exists": true,
    "path": "data/options-validation/options_history.db",
    "quote_timestamp_fields": [
      "as_of_utc",
      "quote_date_et",
      "quote_minute_et"
    ],
    "read_only_mode": true,
    "status": "loaded",
    "tables": {
      "import_batches": {
        "columns": [
          "id",
          "source_label",
          "dataset_kind",
          "data_trust",
          "input_path",
          "file_hash",
          "imported_at_utc",
          "total_rows",
          "imported_rows",
          "duplicate_rows",
          "rejected_rows",
          "warnings_json"
        ]
      },
      "option_quote_snapshots": {
        "columns": [
          "id",
          "as_of_utc",
          "quote_date_et",
          "quote_minute_et",
          "snapshot_kind",
          "underlying",
          "contract_symbol",
          "expiry",
          "option_type",
          "strike",
          "bid",
          "ask",
          "last",
          "iv",
          "underlying_price",
          "volume",
          "open_interest",
          "source_batch_id"
        ]
      },
      "sqlite_sequence": {
        "columns": [
          "name",
          "seq"
        ]
      }
    },
    "trusted_source_labels": [
      "alpaca_opra_daily_snapshot",
      "thetadata_opra_nbbo_1m"
    ]
  },
  "status": "multi_leg_side_aware_pricing_capability_available",
  "structure_support": {
    "ratio_backspread_bounded": {
      "blockers": [],
      "denominator_mapping_status": "ready",
      "fixture_count": 1,
      "resolved_fixture_count": 1,
      "status": "available",
      "undefined_or_naked_ratio_risk_allowed": false
    }
  }
}

Current base clean stack row-level identity ledger result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "duplicate_identity_count": 0,
  "expected_base_clean_stack_exact_rows": 157,
  "future_or_outcome_field_dependency_count": 0,
  "historical_rows_are_forward_proof": false,
  "ledger_row_count": 157,
  "missing_identity_field_row_count": 0,
  "proof_row_count": 0,
  "protected_holdout_overlap_count": 0,
  "status": "base_clean_stack_identity_ledger_ready",
  "unique_identity_count": 157
}

Current flow-extreme denominator/dedupe bridge result, if available:
{
  "accepted_profitability": false,
  "base_identity_hash_count": 157,
  "base_identity_ledger_status": "ready",
  "bridge_blockers": [],
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "denominator_status_contract": [
    "candidate_not_generated_missing_flow_input",
    "candidate_not_generated_missing_vix_bucket",
    "candidate_rejected_missing_required_flow_fields",
    "candidate_rejected_missing_vix_bucket",
    "candidate_rejected_unbounded_or_undefined_risk",
    "candidate_rejected_missing_leg_quote",
    "candidate_rejected_zero_bid_or_untradable",
    "candidate_rejected_crossed_or_stale_quote",
    "candidate_duplicate_existing_base_stack",
    "candidate_duplicate_within_research_harness",
    "candidate_protected_holdout_overlap",
    "priced_fixture_not_proof_eligible",
    "readiness_candidate_priced_not_replayed",
    "no_pick_explicit",
    "blocked_source_missing"
  ],
  "fixture_source_not_proof_eligible": true,
  "full_denominator_mapping_status": "ready",
  "historical_rows_are_forward_proof": false,
  "identity_fields": [
    "concept_id",
    "structure",
    "underlying",
    "signal_date",
    "planned_entry_timestamp",
    "option_rights",
    "expirations",
    "strikes",
    "leg_sides",
    "leg_ratios",
    "entry_policy",
    "exit_policy",
    "candidate_source_id"
  ],
  "proof_row_count": 0,
  "status": "flow_extreme_denominator_dedupe_bridge_ready",
  "strict_new_dedupe_status": "ready",
  "structure": "ratio_backspread_bounded"
}

Current flow-extreme ratio/backspread replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.",
  "blockers": [
    "missing_point_in_time_flow_extreme_input"
  ],
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "packet_ingestion": {
    "expected_concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
    "expected_report_id": "regular_options_flow_extreme_ratio_backspread_replay_readiness",
    "expected_structure": "defined_risk_ratio_spreads_or_backspreads_only",
    "generated_at_utc": "2026-06-24T02:40:26Z",
    "playbook_generated_at_utc": "2026-06-23T05:51:48Z",
    "raw_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
    "reason_codes": [],
    "unsafe_flags": [],
    "validated_status": "blocked_flow_extreme_ratio_backspread_replay_readiness"
  },
  "raw_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": "missing_point_in_time_flow_extreme_input",
  "status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
  "structure": "defined_risk_ratio_spreads_or_backspreads_only",
  "undefined_risk_allowed": false
}

Current preregistered dispersion-proxy hybrid playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk pair structures, and promotion.",
  "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only",
  "undefined_or_uncapped_pair_risk_allowed": false
}

Current point-in-time dispersion/concentration proxy materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "missing_point_in_time_dispersion_proxy_source",
    "missing_required_return_fields",
    "insufficient_month_coverage",
    "insufficient_date_coverage"
  ],
  "coverage": {
    "covered_date_count": 0,
    "covered_month_count": 0,
    "covered_months": [],
    "date_coverage_pct": 0.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ]
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "read_only": true,
  "source_inventory": {
    "feature_store": {
      "available_symbols": [
        "AAPL",
        "COP",
        "CVX",
        "DIA",
        "GOOGL",
        "IWM",
        "JNJ",
        "LLY",
        "NEM",
        "QQQ",
        "SPY",
        "UNH",
        "XOM"
      ],
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-18T06:09:35Z",
      "inventory_status": "feature_store_missing_underlying_return_fields",
      "missing_symbols": [],
      "path": "data/profitability-lab/regular-options-feature-store/latest.json",
      "report_id": "regular_options_feature_store",
      "requested_date_count": 494,
      "required": true,
      "return_fields_available": false,
      "status": "loaded",
      "status_value": "feature_store_built",
      "underlying_price_row_count": 0
    },
    "source_rows": {
      "error": null,
      "exists": false,
      "path": "data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/source_rows.jsonl",
      "required": false,
      "row_count": 0,
      "status": "missing"
    },
    "status": "missing_proxy_source_rows"
  },
  "status": "blocked_point_in_time_dispersion_concentration_proxy"
}

Current dispersion-proxy hybrid replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.",
  "blockers": [
    "missing_dispersion_or_concentration_proxy_inputs",
    "point_in_time_vix_bucket_blocked",
    "missing_pair_construction_engine",
    "missing_side_aware_all_leg_pair_pricing",
    "missing_pair_max_loss_or_collateral_convention",
    "missing_full_denominator_mapping",
    "missing_strict_new_dedupe"
  ],
  "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": "missing_dispersion_or_concentration_proxy_inputs",
  "status": "blocked_dispersion_proxy_hybrid_replay_readiness",
  "structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only"
}

Current preregistered PMCC diagonal playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk short calls, and promotion.",
  "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_pmcc_style_call_diagonals_only",
  "undefined_or_uncapped_short_call_risk_allowed": false
}

Current PMCC diagonal replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.",
  "blockers": [
    "missing_point_in_time_trend_or_regime_inputs",
    "missing_trusted_pmcc_diagonal_quote_surface"
  ],
  "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "packet_ingestion": {
    "expected_concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
    "expected_report_id": "regular_options_pmcc_diagonal_replay_readiness",
    "expected_structure": "defined_risk_pmcc_style_call_diagonals_only",
    "generated_at_utc": "2026-06-24T02:40:43Z",
    "playbook_generated_at_utc": "2026-06-23T06:22:04Z",
    "raw_status": "blocked_pmcc_diagonal_replay_readiness",
    "reason_codes": [],
    "unsafe_flags": [],
    "validated_status": "blocked_pmcc_diagonal_replay_readiness"
  },
  "raw_status": "blocked_pmcc_diagonal_replay_readiness",
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": "missing_point_in_time_trend_or_regime_inputs",
  "status": "blocked_pmcc_diagonal_replay_readiness",
  "structure": "defined_risk_pmcc_style_call_diagonals_only",
  "undefined_or_uncapped_short_call_risk_allowed": false
}

Current approved 59-symbol ThetaData OPRA/NBBO source-repair result, if available:
{
  "accepted_profitability": false,
  "approval_token_valid": true,
  "blockers": [
    "thetaterminal_source_unavailable"
  ],
  "historical_simulated_forward_status": "blocked_historical_simulated_forward_audit",
  "import_attempted": false,
  "imported_rows": 0,
  "missing_symbol_date_count": 11565,
  "quotes_imported": false,
  "shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "status": "blocked_thetaterminal_source_unavailable",
  "theta_terminal": {
    "available": false,
    "error": "<urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>",
    "status": "unavailable",
    "url": "http://127.0.0.1:25503/v2/system/status"
  }
}

Interpretation: if the 59-symbol source repair status is blocked_thetaterminal_source_unavailable, do not treat that as an operator-approval blocker or an earned stop. The operator approved non-live/non-broker research continuation. Choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current tokened 59-symbol ThetaData OPRA/NBBO source-repair resume result, if available:
{
  "approval_token_valid": true,
  "blockers": [
    "thetaterminal_source_unavailable"
  ],
  "import_attempted": false,
  "imported_rows": 0,
  "missing_symbol_date_count": 11565,
  "outside_universe_import_rows": 0,
  "post_import_shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "protected_holdout_overlap_rows": 0,
  "provider_recheck": true,
  "quotes_imported": false,
  "resume_missing_only": true,
  "shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "split_audit_gate": {
    "audit_months_covered": 0,
    "cleared": false,
    "latest_audit_exact_trades": 0,
    "reason": "not_run_until_import_clears_shared_date_coverage",
    "train_months_covered": 0
  },
  "status": "blocked_thetaterminal_source_unavailable_retry",
  "theta_terminal": {
    "available": false,
    "error": "<urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>",
    "status": "unavailable",
    "url": "http://127.0.0.1:25503/v2/system/status"
  }
}

Interpretation: if the tokened 59-symbol resume status is blocked_thetaterminal_source_unavailable_retry, do not select another 59-symbol ThetaTerminal retry until provider/source availability changes. The retry already proved token approval, exact universe, no protected-holdout overlap, no outside-universe import, no import attempted, and no coverage improvement under current provider state. Choose the next meaningful non-live/non-broker source family or causal branch unless your stop_exception burden of proof is fully satisfied.

Current direct point-in-time VIX source state:
{
  "current_branch_implications": [
    {
      "branch": "macro_event_long_strangle",
      "remaining_non_vix_blockers": [
        "macro_event_calendar_source_missing"
      ],
      "source_status": "blocked_macro_event_long_strangle_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "flow_extreme_ratio_backspread",
      "remaining_non_vix_blockers": [
        "missing_point_in_time_flow_extreme_input"
      ],
      "source_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "pmcc_diagonal",
      "remaining_non_vix_blockers": [
        "missing_point_in_time_trend_or_regime_inputs",
        "missing_trusted_pmcc_diagonal_quote_surface"
      ],
      "source_status": "blocked_pmcc_diagonal_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "vrp_credit_spread",
      "remaining_non_vix_blockers": [
        "missing_credit_spread_side_aware_pricing_engine",
        "missing_credit_spread_side_aware_exit_pricing_engine",
        "missing_full_denominator_status_mapping",
        "missing_assignment_expiration_classifier",
        "missing_margin_max_loss_convention",
        "missing_index_credit_spread_quote_surface",
        "missing_protected_holdout_guard"
      ],
      "source_status": "blocked_vrp_credit_spread_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "momentum_continuation",
      "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
      "remaining_non_vix_blockers": [],
      "source_status": "blocked_momentum_continuation_bounded_replay",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "dispersion_proxy_hybrid",
      "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
      "remaining_non_vix_blockers": [
        "missing_dispersion_or_concentration_proxy_inputs",
        "missing_pair_construction_engine",
        "missing_side_aware_all_leg_pair_pricing",
        "missing_pair_max_loss_or_collateral_convention",
        "missing_full_denominator_mapping",
        "missing_strict_new_dedupe"
      ],
      "source_status": "blocked_dispersion_proxy_hybrid_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    }
  ],
  "legacy_future_import_command": "npm run options:source-import:direct-vix -- --source-file data/import-staging/vix/cboe_vix_daily_history.csv --lookback-start-date 2023-05-22 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family direct_vix_daily_close --approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json",
  "legacy_future_import_manifest_template": {
    "date_window": {
      "end": "2026-06-04",
      "start": "2023-05-22"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
    "required_fields": [
      "source_date",
      "vix_open",
      "vix_high",
      "vix_low",
      "vix_close",
      "source_name",
      "source_file_hash",
      "source_row_hash",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id"
    ],
    "source_family": "direct_vix_daily_close",
    "source_file": "data/import-staging/vix/cboe_vix_daily_history.csv",
    "write_target": "generated point-in-time VIX source artifact only"
  },
  "legacy_source_repair_packet_status": "direct_vix_source_repair_packet_ready_for_operator_import_decision",
  "source_import": {
    "accepted_profitability": false,
    "downstream_vix_bucket_status": "point_in_time_vix_bucket_ready",
    "downstream_vix_coverage_pct": 100.0,
    "evidence_stores_mutated": false,
    "protected_holdout_consumed": false,
    "quotes_imported": false,
    "source_family": "direct_vix_daily_close",
    "source_row_count": 505,
    "source_rows_path": "data/profitability-lab/regular-options-point-in-time-vix-bucket/source_rows.jsonl",
    "source_rows_written": true,
    "status": "direct_vix_source_import_materialized",
    "threshold_policy_path": "data/contracts/regular-options-vix-bucket-policy.json"
  },
  "vix_bucket": {
    "blockers": [],
    "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
    "coverage_pct": 100.0,
    "covered_date_count": 505,
    "late_known_at_count": 0,
    "leakage_reject_count": 0,
    "requested_date_count": 505,
    "source_rows_count": 505,
    "status": "point_in_time_vix_bucket_ready",
    "threshold_policy": {
      "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
      "frozen_at_utc": "2026-06-04T00:00:00Z",
      "low_max": 15.0,
      "mid_max": 25.0,
      "policy_id": "vix_prior_close_fixed_buckets_v1"
    }
  }
}

Interpretation: when the current VIX state shows `direct_vix_source_import_materialized` and `point_in_time_vix_bucket_ready`, the prior operator-supplied official daily VIX CSV has already been materialized; do not select the direct VIX source plan or VIX source import again; do not rerun the same VIX packet. Branches that still name VIX as a blocker must be refreshed or treated as stale with respect to VIX; rank their remaining non-VIX blockers instead.

Current macro-event calendar source repair packet result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "branch_implications": [
    {
      "branch": "macro_event_long_strangle",
      "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
      "event_calendar_blockers": [
        "macro_event_calendar_source_missing"
      ],
      "remaining_non_event_blockers": [
        "point_in_time_vix_source_missing",
        "missing_vix_bucket_threshold_policy",
        "vix_bucket_date_coverage_incomplete"
      ],
      "status": "blocked_macro_event_long_strangle_replay_readiness",
      "would_clear_event_calendar_blocker_if_future_source_passes": true
    },
    {
      "branch": "post_event_iv_crush_iron_condor",
      "concept_id": "post_event_iv_crush_index_iron_condor_v1",
      "event_calendar_blockers": [
        "future_replay_requires_point_in_time_macro_event_calendar"
      ],
      "remaining_non_event_blockers": [
        "point_in_time_vix_source_missing",
        "iv_event_premium_proxy_missing"
      ],
      "status": "preregistered_design_only",
      "would_clear_event_calendar_blocker_if_future_source_passes": true
    },
    {
      "branch": "direct_vix_source_repair",
      "concept_id": "direct_vix_daily_close",
      "event_calendar_blockers": [],
      "remaining_non_event_blockers": [
        "direct_vix_source_import_materialization_pending"
      ],
      "status": "direct_vix_source_repair_packet_ready_for_operator_import_decision",
      "would_clear_event_calendar_blocker_if_future_source_passes": false
    }
  ],
  "current_macro_event_source_baseline": {
    "covered_categories": [],
    "current_forward_rows": 0,
    "event_count": 0,
    "macro_event_calendar_status": "blocked_macro_event_calendar_source_missing",
    "missing_required_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "target_forward_rows": 30
  },
  "downstream_readiness_commands": {
    "macro_event_long_strangle": "npm run options:research:macro-event-long-strangle-replay-readiness -- --json",
    "post_event_iv_crush_iron_condor": "future_post_event_iv_crush_readiness_audit_not_implemented_yet"
  },
  "evidence_stores_mutated": false,
  "fixture_validation": {
    "after_market_case_present": true,
    "all_required_categories_present": true,
    "before_market_case_present": true,
    "category_counts": {
      "cpi": 1,
      "fomc_minutes": 1,
      "fomc_rate_decision": 1,
      "nonfarm_payrolls": 1,
      "pce": 1,
      "scheduled_fed_chair_testimony": 1
    },
    "covered_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "duplicate_event_id_reject_count": 0,
    "during_market_case_present": true,
    "errors": [],
    "fixture_path": "tests/fixtures/macro_events/macro_event_calendar_sample.csv",
    "holiday_weekend_adjacent_case_present": true,
    "known_at_reject_count": 0,
    "known_at_safe": true,
    "leakage_reject_count": 0,
    "missing_required_categories": [],
    "protected_holdout_overlap_rows": 0,
    "required_fields_present": true,
    "row_count": 6,
    "sample_rows": [
      {
        "event_category": "cpi",
        "event_id": "cpi-2026-02",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-02-12T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-02-12T13:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "52849c991555cdb6e9b2395c3fe8e891e65126c469ab5a61ceebff49b2fd7e5b",
        "source_url_or_file_name": "fixture://macro-events/cpi",
        "tradable_after_et": "2026-02-12T09:30 America/New_York"
      },
      {
        "event_category": "fomc_minutes",
        "event_id": "fomc-minutes-2026-02",
        "event_window_type": "during_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-02-18T14:00 America/New_York",
        "scheduled_event_datetime_utc": "2026-02-18T19:00Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "a5403f4d2fb10e504cb793aba1b09182134543703ca4b1d8deb654b346d1e000",
        "source_url_or_file_name": "fixture://macro-events/fomc-minutes",
        "tradable_after_et": "2026-02-18T14:00 America/New_York"
      },
      {
        "event_category": "fomc_rate_decision",
        "event_id": "fomc-rate-2026-03",
        "event_window_type": "during_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-03-18T14:00 America/New_York",
        "scheduled_event_datetime_utc": "2026-03-18T18:00Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "7c722f1dab5013c3aee98b8843afcaeb35559156b09a651317f5092a7e77a35e",
        "source_url_or_file_name": "fixture://macro-events/fomc-rate",
        "tradable_after_et": "2026-03-18T14:00 America/New_York"
      },
      {
        "event_category": "nonfarm_payrolls",
        "event_id": "nfp-2026-04",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-04-03T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-04-03T12:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "58a333e847821302ccfd01a3518294ce35749dc881101825d5908ba49b3df4eb",
        "source_url_or_file_name": "fixture://macro-events/nfp",
        "tradable_after_et": "2026-04-03T09:30 America/New_York"
      },
      {
        "event_category": "pce",
        "event_id": "pce-2026-05",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-05-29T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-05-29T12:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "df980a9d7cfda234b8906a24dfa99bb7b153c69d6b0772797b69ae960e95da9e",
        "source_url_or_file_name": "fixture://macro-events/pce",
        "tradable_after_et": "2026-05-29T09:30 America/New_York"
      },
      {
        "event_category": "scheduled_fed_chair_testimony",
        "event_id": "fed-chair-2026-05",
        "event_window_type": "after_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-05-22T16:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-05-22T20:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "631e32d316bf45b7cc0cce6c06caaf2eec273a74dbe287f5ba6b02f20bcc9b56",
        "source_url_or_file_name": "fixture://macro-events/fed-chair",
        "tradable_after_et": "2026-05-26T09:30 America/New_York"
      }
    ]
  },
  "future_import_command": "npm run options:source-import:macro-event-calendar -- --source-file data/import-staging/macro_events/macro_event_calendar.csv --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family scheduled_macro_event_calendar_v1 --required-categories cpi,fomc_minutes,fomc_rate_decision,nonfarm_payrolls,pce,scheduled_fed_chair_testimony --approval-token APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT --no-replay --json",
  "future_import_command_executed": false,
  "future_import_manifest_template": {
    "date_window": {
      "as_of": "2026-06-04",
      "end": "2026-05-31",
      "start": "2024-06-01"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT",
    "required_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "required_fields": [
      "event_id",
      "event_category",
      "scheduled_event_datetime_et",
      "event_window_type",
      "source_name",
      "source_url_or_file_name",
      "source_file_hash",
      "source_row_hash",
      "source_published_at_utc",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id",
      "revision_status",
      "proof_exclusion_reason"
    ],
    "source_family": "scheduled_macro_event_calendar_v1",
    "source_file": "data/import-staging/macro_events/macro_event_calendar.csv",
    "write_target": "generated point-in-time macro-event calendar source artifact only"
  },
  "historical_rows_are_forward_proof": false,
  "known_at_policy": {
    "forbidden_candidate_inputs": [
      "actual",
      "actual_value",
      "beat_miss",
      "consensus",
      "forecast",
      "iv_crush",
      "market_reaction",
      "net_pnl",
      "net_pnl_usd",
      "pnl",
      "post_event_drift",
      "post_event_iv",
      "realized_move",
      "realized_vol",
      "revised_value",
      "revision_value",
      "surprise"
    ],
    "policy_id": "scheduled_macro_event_known_before_candidate_decision_v1",
    "rule": "Rows are usable only when source_published_at_utc and known_at_utc are no later than the candidate decision timestamp."
  },
  "protected_holdout_consumed": false,
  "quotes_imported": false,
  "source_family": "scheduled_macro_event_calendar_v1",
  "status": "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision",
  "tradable_after_policy": {
    "after_market": "next regular session no earlier than 09:30 America/New_York",
    "before_market": "same regular session post-open only if schedule was known before entry",
    "during_market": "decisions after the scheduled release timestamp only",
    "policy_id": "scheduled_macro_event_tradable_after_release_window_v1"
  }
}

Interpretation: if the macro-event calendar source repair packet status is macro_event_calendar_source_repair_packet_ready_for_operator_import_decision, do not rerun the same macro-event source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real macro-event source import/materialization still needs the exact tokened source-import slice and an operator-supplied official macro-event calendar CSV. Do not run macro-event or post-event replay until a real point-in-time macro-event source artifact exists. Decide whether the next meaningful slice is that tokened non-live source materialization path, a readiness audit for post-event IV-crush, direct VIX materialization if source is supplied, or another safe fallback.

Current flow-extreme volume/open-interest source repair packet result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "branch_implications": [
    {
      "branch": "flow_extreme_ratio_backspread",
      "flow_blockers": [
        "missing_point_in_time_flow_extreme_input"
      ],
      "remaining_non_flow_blockers": [
        "missing_point_in_time_vix_bucket"
      ],
      "status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
      "would_clear_flow_blocker_if_future_source_passes": true
    },
    {
      "branch": "direct_vix_source_repair",
      "flow_blockers": [],
      "remaining_non_flow_blockers": [
        "direct_vix_source_import_materialization_pending"
      ],
      "status": "direct_vix_source_repair_packet_ready_for_operator_import_decision",
      "would_clear_flow_blocker_if_future_source_passes": false
    }
  ],
  "current_flow_source_baseline": {
    "covered_month_count": 0,
    "current_forward_rows": 0,
    "date_coverage_pct": 0.0,
    "flow_extreme_ratio_backspread_replay_readiness_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
    "flow_extreme_volume_oi_source_rows_status": "blocked_flow_extreme_volume_oi_source_rows",
    "point_in_time_flow_extreme_input_status": "blocked_point_in_time_flow_extreme_input",
    "target_forward_rows": 30
  },
  "downstream_readiness_commands": {
    "flow_extreme_ratio_backspread_replay_readiness": "npm run options:research:flow-extreme-ratio-backspread-replay-readiness -- --json",
    "point_in_time_flow_extreme_input": "npm run options:research:point-in-time-flow-extreme-input -- --no-write --json"
  },
  "evidence_stores_mutated": false,
  "fixture_validation": {
    "duplicate_source_row_hash_reject_count": 0,
    "errors": [],
    "fixture_path": "tests/fixtures/flow/spy_qqq_option_volume_oi_daily_sample.csv",
    "holiday_gap_case_present": true,
    "known_at_safe": true,
    "late_known_at_reject_count": 1,
    "leakage_reject_count": 0,
    "missing_value_reject_count": 1,
    "prior_day_aggregate_safe_for_next_session_entry": true,
    "protected_holdout_overlap_rows": 0,
    "reject_count": 2,
    "rejected_rows": [
      {
        "index": 5,
        "reasons": [
          "missing_or_invalid_total_option_volume"
        ],
        "source_date": "2024-07-05",
        "underlying": "SPY"
      },
      {
        "index": 6,
        "reasons": [
          "known_at_after_tradable_after"
        ],
        "source_date": "2024-07-05",
        "underlying": "QQQ"
      }
    ],
    "required_fields_present": true,
    "row_count": 4,
    "same_day_aggregate_safe_for_same_day_entry": false,
    "sample_rows": [
      {
        "call_open_interest": 4100000.0,
        "call_put_volume_ratio": 1.083333,
        "call_volume": 520000.0,
        "data_trust": "trusted",
        "flow_extreme": false,
        "known_at_utc": "2024-06-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 3900000.0,
        "put_volume": 480000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "e3f724fb5aa7d94168aa03db771b24b87e49e322fffa96a5248c9a0b2b37ca44",
        "source_url_or_file_name": "fixture://flow/spy",
        "strictly_prior_rows_used": 0,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 8000000.0,
        "total_option_volume": 1000000.0,
        "total_option_volume_prior_percentile": null,
        "tradable_after_et": "2024-06-04T09:30 America/New_York",
        "underlying": "SPY",
        "volume_open_interest_ratio": 0.125
      },
      {
        "call_open_interest": 3300000.0,
        "call_put_volume_ratio": 1.162162,
        "call_volume": 430000.0,
        "data_trust": "trusted",
        "flow_extreme": false,
        "known_at_utc": "2024-06-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 2900000.0,
        "put_volume": 370000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "103ba37b0742d11e2fbf8fd1bc4d6fc6e38e65a04c3c622154a412c82e644021",
        "source_url_or_file_name": "fixture://flow/qqq",
        "strictly_prior_rows_used": 0,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 6200000.0,
        "total_option_volume": 800000.0,
        "total_option_volume_prior_percentile": null,
        "tradable_after_et": "2024-06-04T09:30 America/New_York",
        "underlying": "QQQ",
        "volume_open_interest_ratio": 0.129032
      },
      {
        "call_open_interest": 4800000.0,
        "call_put_volume_ratio": 0.5625,
        "call_volume": 900000.0,
        "data_trust": "trusted",
        "flow_extreme": true,
        "known_at_utc": "2024-06-04T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 7200000.0,
        "put_volume": 1600000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-04",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "eca5ed34a5f0cc49e6db608078c808bfa9ae00905b739bbf3047163c1861d298",
        "source_url_or_file_name": "fixture://flow/spy-extreme",
        "strictly_prior_rows_used": 1,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 12000000.0,
        "total_option_volume": 2500000.0,
        "total_option_volume_prior_percentile": 100.0,
        "tradable_after_et": "2024-06-05T09:30 America/New_York",
        "underlying": "SPY",
        "volume_open_interest_ratio": 0.208333
      },
      {
        "call_open_interest": 3400000.0,
        "call_put_volume_ratio": 1.093023,
        "call_volume": 470000.0,
        "data_trust": "trusted",
        "flow_extreme": true,
        "known_at_utc": "2024-07-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 3000000.0,
        "put_volume": 430000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-07-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "51bc2acdaace30a1a140a9146414a3fbaf330edd0e64ff221fc793fca8a6f5d7",
        "source_url_or_file_name": "fixture://flow/qqq-gap",
        "strictly_prior_rows_used": 1,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 6400000.0,
        "total_option_volume": 900000.0,
        "total_option_volume_prior_percentile": 100.0,
        "tradable_after_et": "2024-07-05T09:30 America/New_York",
        "underlying": "QQQ",
        "volume_open_interest_ratio": 0.140625
      }
    ],
    "underlyings_covered": [
      "SPY",
      "QQQ"
    ]
  },
  "future_import_command": "npm run options:source-import:flow-extreme-volume-oi -- --source-file data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv --lookback-start-date 2023-06-01 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --underlyings SPY,QQQ --source-family trusted_option_volume_open_interest_daily_v1 --approval-token APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT --no-replay --json",
  "future_import_command_executed": false,
  "future_import_manifest_template": {
    "date_window": {
      "as_of": "2026-06-04",
      "lookback_start": "2023-06-01",
      "target_end": "2026-05-31",
      "target_start": "2024-06-01"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT",
    "required_fields": [
      "source_date",
      "underlying",
      "total_option_volume",
      "call_volume",
      "put_volume",
      "total_open_interest",
      "call_open_interest",
      "put_open_interest",
      "source_name",
      "source_url_or_file_name",
      "source_file_hash",
      "source_row_hash",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id",
      "data_trust",
      "revision_status",
      "proof_exclusion_reason"
    ],
    "source_family": "trusted_option_volume_open_interest_daily_v1",
    "source_file": "data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv",
    "underlyings": [
      "SPY",
      "QQQ"
    ],
    "write_target": "generated point-in-time flow-extreme source artifact only"
  },
  "historical_rows_are_forward_proof": false,
  "known_at_policy": {
    "policy_id": "trusted_flow_prior_source_date_known_before_candidate_v1",
    "rule": "source_date D aggregate volume/OI is usable only when known_at_utc is no later than candidate decision time and source_date is strictly before input_date_et",
    "same_day_aggregate_volume_oi_allowed_for_same_day_entry": false
  },
  "protected_holdout_consumed": false,
  "quotes_imported": false,
  "source_family": "trusted_option_volume_open_interest_daily_v1",
  "status": "flow_extreme_source_repair_packet_ready_for_operator_import_decision",
  "threshold_policy": {
    "call_put_volume_ratio": "diagnostic_only_unless_separately_preregistered",
    "flow_extreme_rule": "flow_extreme=true only when prior-day flow percentile >= 95.0 using strictly prior source rows only",
    "outcome_tuned": false,
    "plain_bid_ask_used_as_flow": false,
    "policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
    "realized_pnl_used": false,
    "selected_winners_used": false,
    "volume_open_interest_ratio": "diagnostic_only_unless_separately_preregistered"
  }
}

Interpretation: if the flow-extreme source repair packet status is flow_extreme_source_repair_packet_ready_for_operator_import_decision, do not rerun the same flow-source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real SPY/QQQ option volume/open-interest source import/materialization still needs the exact tokened source-import slice and an operator-supplied trusted daily volume/OI CSV. Do not run flow-extreme replay until real point-in-time flow source rows exist. VIX is no longer the flow blocker. Decide whether the next meaningful slice is that tokened non-live flow-source materialization path or another safe fallback.

Current goal-loop state:
{
  "forward_evidence_accounting": {
    "auto_track_allowed": false,
    "broker_order_allowed": false,
    "cohort_append_performed": false,
    "cohort_log_exists": false,
    "cohort_log_malformed_row_count": 0,
    "cohort_log_path": "data/forward-tracking/phase2_regular_options_forward_paper_shadow_cohort.jsonl",
    "cohort_log_row_count": 0,
    "cohort_log_status": "missing",
    "excluded_or_rejected_row_flags": 0,
    "live_entry_allowed": false,
    "minimum_required": 30,
    "post_freeze_strict_exact_completed_rows": 0,
    "promotion_ready": false,
    "state": "log_missing_blocker",
    "strict_reject_counts": {
      "blocked_by_required_contracts": 0,
      "duplicate_completed_selection_id": 0,
      "duplicate_row_id": 0,
      "exact_completed_missing_entry_quote_provenance": 0,
      "exact_completed_missing_exit_quote_provenance": 0,
      "exact_completed_missing_policy_exit_condition": 0,
      "fixture_source_not_proof_eligible": 0,
      "lookahead_claimed_as_exact": 0,
      "market_window_not_open": 0,
      "missing_net_pnl_usd": 0,
      "missing_real_source_provenance": 0,
      "missing_required_schema_fields": 0,
      "missing_source_provenance_fields": 0,
      "non_executable_mark_claimed_as_exact": 0,
      "non_frozen_lane": 0,
      "non_preregistered_symbol": 0,
      "pre_freeze_not_acceptance_eligible": 0,
      "scanner_hash_drift": 0,
      "unknown_denominator_status": 0
    },
    "strict_rows_remaining_to_minimum": 30,
    "strict_usd_pf_lower_bound_5pct": null,
    "total_natural_selections": 0
  },
  "next_safe_action": "continue_paper_shadow_only",
  "state": "underpowered_forward_evidence"
}

Important instruction:
You are not being asked for generic strategy advice or a casual continue/stop vote. Treat stopping as an exceptional claim. Because strict post-freeze forward proof is currently 0/30, you may recommend stopping only if you can prove that no significant upgrade remains after explicitly considering new lanes, new option structures, historical data-depth repair, and forward collection. Ask up to five operator questions that would materially affect the decision, but do not block on read-only/research-only work; the user has already approved that category. For any live/broker/import/mutation/promotion/proof-bar/holdout action, name the needed approval and select a safe read-only fallback unless no such fallback exists.

Return a concrete loop decision. If a significant upgrade remains, return verdict=continue, continue_loop=true, and exactly one next Codex task with files/artifacts/commands/tests/acceptance criteria. If a branch needs operator approval, ask the exact operator question and explain why it is required. If no significant upgrade remains under current approvals, return verdict=stop_exception, continue_loop=false, and provide the burden-of-proof check that earned that stop.

Do not say "collect more data", "try more strategies", "optimize parameters", or "run more backtests" unless you specify the exact data, lane, option structure, date window, command, and pass/fail threshold.

Before any stop_exception, explicitly evaluate whether there is a falsifiable path through:
1. fresh forward paper-shadow collection,
2. scoped source repair or replay,
3. a new historical data surface or longer-lookback audit,
4. a new causal playbook,
5. new option structures beyond the current directional-spread surface.

New option edge families to consider before stopping:
- volatility risk premium,
- skew mispricing,
- term-structure dislocation,
- earnings or macro event volatility,
- post-event IV crush,
- post-event drift,
- trend or momentum continuation,
- mean reversion,
- dispersion-like proxy behavior,
- liquidity or flow effects.

Option structures to consider before stopping:
- vertical spreads,
- calendars,
- diagonals,
- broken-wing butterflies,
- ratio spreads,
- backspreads,
- straddles,
- strangles,
- iron condors,
- iron butterflies,
- synthetic covered calls or PMCC-style diagonals,
- debit/credit hybrids.

For every proposed lane, provide the frozen rule, eligible universe, inclusion/exclusion rules, leakage controls, required data repairs, minimum sample size, profitability thresholds, and the exact result that would falsify it. A lane should not pass because it has an attractive point backtest; it needs an economic mechanism and a falsifiable audit plan.

Allowed branch families:
1. fresh_forward_paper_shadow_collection - requires operator approval and a valid market-data window if rows will be appended.
2. scoped_source_repair_or_replay - requires operator approval before quote import, evidence mutation, or source repair.
3. new_causal_playbook_generation - read-only preregistration/falsification can continue without live/broker/evidence mutation.
4. new_historical_data_surface_or_longer_lookback - requires operator approval if it changes the data surface.
5. dashboard_or_operator_visibility - only significant if tied to a proof blocker or execution decision.

Forbidden unless explicitly approved later:
- broker orders, live validation, auto-track, scanner release, stop/sizing changes, proof-bar relaxation, quote import, evidence DB mutation, protected holdout consumption, promotion.

Required JSON-like output shape:
{
  "anti_handwave_audit": {
    "exact_next_action_present": "boolean",
    "generic_advice_removed": "boolean",
    "measurable_threshold_present": "boolean"
  },
  "assumption_challenges": [
    {
      "assumption": "string",
      "risk": "string",
      "verification": "string"
    }
  ],
  "branches_to_stop": [
    "branch ids or candidate ids to avoid repeating"
  ],
  "burden_of_proof_check": {
    "current_forward_rows": "number",
    "reason": "string",
    "stop_allowed": "boolean",
    "target_profitable_strict_completed_rows": "number"
  },
  "candidate_branches": [
    {
      "branch": "string",
      "expected_value": "string",
      "main_uncertainty": "string",
      "why_not_selected": "string|null"
    }
  ],
  "continue_loop": "boolean",
  "next_codex_task": {
    "acceptance_criteria": [
      "measurable pass/fail criteria"
    ],
    "allowed_files_or_artifacts": [
      "paths or artifact families"
    ],
    "commands_to_run": [
      "exact commands"
    ],
    "exact_scope": "files/modules/artifacts included and excluded",
    "expected_artifacts": [
      "files or readbacks expected after Codex runs"
    ],
    "failure_criteria": [
      "what result rejects or parks this branch"
    ],
    "forbidden_actions": [
      "actions that remain forbidden"
    ],
    "implementation_steps": [
      "ordered steps"
    ],
    "objective": "one concrete implementation or verification task",
    "stop_condition_after_task": "what would make this branch exhausted"
  },
  "operator_questions": [
    {
      "default_if_unanswered": "string",
      "question": "string",
      "why_it_matters": "string"
    }
  ],
  "selected_branch_id": "string|null",
  "significant_upgrade_available": "boolean",
  "verdict": "continue|stop_exception",
  "why_this_is_significant": "short explanation tied to profitability proof"
}

Relevant NEXT_STEPS excerpt:
# Next Steps

Last updated: 2026-06-24

## Active Historical Robust-Search Track

Current read:
- Phase 2 forward proof remains the active forward-audit target and is not profitable yet: `0/30` strict post-freeze completed rows, missing real cohort log, `promotion_ready=false`, and live/auto-track/broker flags false. The passive capture runner is now the preferred forward-only command because it wraps staging, validation, and guarded optional append while reading existing `scan_picks.jsonl` only. The latest real run returned `no_phase2_natural_selections_no_append`: `0` staged rows, no candidate JSONL, and no cohort log. During a valid open market window, the next forward-only attempt is:

```powershell
npm run options:capture:phase2-forward-paper-shadow -- --market-window-confirmed --market-window-status open --json
npm run options:validate:phase2-forward-paper-shadow-candidate -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl
npm run options:append:phase2-forward-paper-shadow -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl --approval-token APPROVE_PHASE2_FORWARD_COHORT_APPEND --market-window-confirmed
npm run options:goal-loop:paper-shadow -- --json
```

Only run the validate/append commands if the capture runner wrote candidate rows from real same-day market-window scan picks and validation reports `append_allowed=true`; never append fixture/test/synthetic rows.
- the forward cohort remains frozen and passive; do not use historical rows as fresh forward promotion proof.
- the no-wait profitability track is to extend trusted historical ThetaData OPRA/NBBO coverage, then run a split-aware robust-search evaluation before nominating any new lane for forward tracking.
- trusted `thetadata_opra_nbbo_1m` intraday coverage for the 13-symbol proof/import set (`SPY`, `QQQ`, `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`, `DIA`) is now `505` shared dates from `2024-05-22` through `2026-06-04`; the 504-date two-year feature-store depth target is met.
- paid-data readiness is still `not_ready` after batch `2147` because `CVX` executable quote coverage is `88.66%`, below the `90%` floor; do not use the 13-symbol surface for a nomination until this clears or the lane explicitly excludes/fails the affected symbol under a preregistered rule.
- `docs/regular-options-cvx-executable-coverage.md` diagnoses the CVX issue as observed zero-bid tradability, not missing provider data: `495,306` trusted rows, `505` dates, `56,191` non-executable rows, `100.0%` of non-executable rows are zero-bid/positive-ask, `0` missing bid/ask rows, `0` crossed quotes, and the current multilane source report contains `3` selected CVX historical trades plus `1` suppressed duplicate.
- `data/contracts/regular-options-source-quality-scope-policy.json` is active and applies the `cvx_zero_bid_tradability_candidate_scope_v1` rule, excluding the `3` matching CVX `bullish_pullback_core` rows from historical nomination metrics without lowering the quote-quality floor.
- ThetaTerminal v3 is reachable at `http://127.0.0.1:25503`; the old-date dry-run for `2024-05-22` returned `20,958` normalized rows with `0` errors.
- batches `2130` through `2146` imported `2024-05-22` through `2025-05-14` for the 13-symbol set with `5,805,236` trusted intraday rows, `0` duplicates, and `0` rejects. Batch `2147` then imported the scoped post-repair exact missing rows for the four coverage-repair variants: `17` trusted intraday rows, `0` duplicates, `0` rejects, `0` dry-run/import errors, and `0` lookahead-only rows.
- `docs/regular-options-feature-store.md` is now the point-in-time feature-store readback: `12,149,436` trusted intraday rows, all `13` symbols available, `505` shared quote dates, and joins require `feature.tradable_after_time <= candidate_entry_time`.
- `docs/regular-options-robust-search-evaluation.md` is now the split-aware historical robust-search report. Current result is `historical_candidates_blocked`: `231` exact rows accepted after `3` CVX source-quality scope exclusions, `0` / `3` candidates ready, regime robustness passed, feature-store gate passed, combined final holdout `28` trades with bootstrap PF lower bound `0.61`, and blockers include final holdout below `30`, final PF-LB below the selection-adjusted bar, paper-shadow/source-quality blockers, and lane-specific unpriced/zero-bid blockers.
- `docs/regular-options-historical-simulated-forward-audit.md` is now the explicit calendar split audit exposed as `npm run options:audit:historical-simulated-forward`. It answers the "two years of data" challenge by separating quote-history depth from candidate-generation proof: the feature store has `505` shared trusted intraday dates through `2026-06-04`, but the current fail-closed frozen 13-symbol source chain proves `0/24` candidate-generation months and `0` selected rows. The requested `20` train months plus latest `4` simulated-forward audit months is therefore blocked (`selected_trade_months_0_below_required_24`, `train_calendar_months_0_below_20`, `audit_calendar_months_0_below_4`, `audit_exact_trades_0_below_30`, `missing_daily_candidate_generation_diagnostics`, and `source_artifact_universe_not_13_symbol`). No latest-four proof-qualified simulated-forward P&L can be claimed from this source chain.
- `docs/regular-options-historical-depth-selected-trades.md` is the earlier read-only selected-trade calendar-depth readback exposed as `npm run options:build:historical-depth-selected-trades`; it showed why the broad source could not answer the `2024-06` through `2026-05` question. The current proof chain should use the fail-closed frozen source-surface materializer instead of counting broad-source selected rows.
- `docs/regular-options-point-in-time-selected-trade-depth.md` and `docs/regular-options-point-in-time-candidate-generation.md` are the read-only point-in-time selected-trade depth and candidate-generation proof reports. The current 13-symbol chain consumes the frozen source surface, which proves `0/24` months and no selected rows; zero-selection months outside a proven candidate-generation source cannot be counted as real no-pick months.
- `docs/regular-options-13-symbol-candidate-generation-no-write.md` is now the read-only no-write/as-of/universe-filter runner-support artifact, exposed as `npm run options:research:13-symbol-no-write-candidate-generation -- --no-write --json`. It proves safe runner controls only; it does not prove candidate-surface coverage or profitability.
- `docs/regular-options-13-symbol-frozen-candidate-generation-entrypoint.md` is now the GPT-5.5-selected read-only reusable frozen daily candidate/no-pick entrypoint, exposed as `npm run options:research:13-symbol-frozen-candidate-generation-entrypoint -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json`. Current result is `blocked_frozen_13_symbol_candidate_generation_entrypoint`: it emits `6,916` frozen lane/symbol/date rows, all blocked by `missing_daily_candidate_generation_diagnostics`; candidate-generation months covered remain `0/24`, selected candidates `0`, and old broad selected rows are not converted into proof.
- `docs/regular-options-13-symbol-frozen-candidate-generation-source-surface.md` is now the read-only frozen 13-symbol source-surface materializer, exposed as `npm run options:research:13-symbol-frozen-candidate-generation-source-surface -- --no-write --json`. Current result is `blocked_13_symbol_frozen_candidate_generation_source_surface`: it consumes the frozen entrypoint, proves `0/24` candidate-generation months and `0` selected rows, and names blockers `candidate_generation_months_0_below_requested_24`, `missing_daily_candidate_generation_diagnostics`, and `source_artifact_universe_not_13_symbol`.
- `docs/regular-options-13-symbol-frozen-candidate-generation-denominator-v2.md` is 

Relevant DECISIONS excerpt:
# Decisions

## 2026-06-24: Frozen 13-Symbol Entrypoint Exists But Daily Candidate Decisions Are Still Missing

GPT-5.5 Pro selected `candidate_generation_repair:frozen_13_symbol_reusable_candidate_generation_entrypoint_v1` after the profitability-first blocker map identified candidate throughput as the highest-leverage blocker. `scripts/regular_options_frozen_candidate_generation_entrypoint.py`, exposed as `npm run options:research:13-symbol-frozen-candidate-generation-entrypoint`, now owns the reusable read-only/no-write frozen daily candidate/no-pick entrypoint.

Latest status is `blocked_frozen_13_symbol_candidate_generation_entrypoint`: the artifact emits `6,916` lane/symbol/date rows across the frozen Phase 2 13-symbol cohort from `2024-06-01` through `2026-05-31`, but all rows are blocked by `missing_daily_candidate_generation_diagnostics`; the source is still not an exact frozen 13-symbol daily decision source, covered months are `0/24`, and selected candidates are `0`. The frozen source-surface materializer now consumes this entrypoint, and the historical simulated-forward audit now defaults to the frozen source surface instead of the old broad selected-trade source. Current audit status remains `blocked_historical_simulated_forward_audit` with `0` selected rows, `0` train months, `0` audit months, and `0/30` exact audit trades.

Durable decision: the reusable entrypoint is implemented, but it does not clear candidate-generation proof. Do not claim historical or forward profitability from old broad selected rows, dashboard rows, or quote-depth-only rows. The next same-session Oracle loop should treat the remaining blocker as real daily candidate-generation/source repair, source materialization, replay-engine work, or another ranked profitability path. No broker orders, live validation, auto-track, quote import, evidence mutation, protected-holdout consumption, production scanner/strategy/stop/sizing/proof-bar change, or promotion occurred.

## 2026-06-24: Direct VIX Source Is Materialized; Macro And Flow Need Trusted Source Files

The direct VIX source repair packet is no longer merely an import-decision artifact. `scripts/import_regular_options_direct_vix_source.py`, exposed as `npm run options:source-import:direct-vix`, materialized official Cboe VIX daily history into `data/profitability-lab/regular-options-point-in-time-vix-bucket/source_rows.jsonl` under the token `APPROVE_DIRECT_VIX_SOURCE_IMPORT`, wrote the frozen VIX bucket policy at `data/contracts/regular-options-vix-bucket-policy.json`, and did not mutate `options_history.db`.

Latest direct VIX readback is `direct_vix_source_import_materialized`; the downstream point-in-time VIX bucket is `point_in_time_vix_bucket_ready` with `505` / `505` requested feature-store dates covered, `100.0%` coverage, `0` late-known-at rows, `0` leakage rejects, and no blockers. VIX should no longer be named as a blocker for macro-event, flow-extreme, PMCC, momentum, dispersion, skew, or VRP readiness unless a future artifact becomes missing, stale, malformed, or policy-incompatible.

`scripts/import_regular_options_macro_event_calendar.py` and `scripts/import_regular_options_flow_extreme_volume_oi.py` now provide exact tokened materialization paths for the next easy source repairs, but they still require trusted input CSVs. Macro-event remains blocked by missing scheduled-event source rows, and flow-extreme remains blocked by missing trusted SPY/QQQ daily option volume/open-interest source rows. These importers do not authorize broker orders, live validation, auto-track, protected-holdout consumption, production scanner/strategy/stop/sizing/proof-bar changes, evidence DB mutation outside their generated source-row artifacts, promotion, or treating historical rows as forward proof.

## 2026-06-24: Flow-Extreme Volume/OI Source Repair Packet Is Ready For Future Import Decision

GPT-5.5 Pro selected `trusted_flow_volume_oi_source_repair_packet_v1` after the macro-event calendar source repair packet reached import-decision state. `scripts/build_regular_options_flow_extreme_source_repair_packet.py`, exposed as `npm run options:source-plan:flow-extreme-volume-oi`, now owns the read-only flow-extreme volume/open-interest source repair packet.

Latest status is `flow_extreme_source_repair_packet_ready_for_operator_import_decision`. The packet reproduces the current flow baseline (`point_in_time_flow_extreme_input_status=blocked_point_in_time_flow_extreme_input`, `flow_extreme_volume_oi_source_rows_status=blocked_flow_extreme_volume_oi_source_rows`, `covered_month_count=0`, `date_coverage_pct=0.0`), defines `trusted_option_volume_open_interest_daily_v1` required fields for SPY/QQQ only, rejects same-day aggregate use for same-day entries, freezes the prior-row percentile policy, validates late-known-at and missing-value fixture rejects, and emits a future tokened import/materialization command using `APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT`.

Durable decision: this task authorizes only a future approval decision, not import. Flow source import/materialization, source-row writes, downstream flow input materialization, replay, and profitability claims remain not run. No evidence store mutation, protected-holdout consumption, live validation, auto-track, broker/order action, scanner/strategy/stop/sizing/proof-bar change, or promotion occurred. The same-session Oracle handoff prompt now starts with the profitability-first blocker-ranking prompt and explicitly forbids repeating the completed VIX, macro-event, flow-source, and ThetaTerminal retry branches unless source state changes.

## 2026-06-24: Macro-Event Calendar Source Repair Packet Is Ready For Future Import Decision

GPT-5.5 Pro selected `macro_event_calendar_source_repair_packet_v1` after the direct VIX source repair packet reached import-decision state. `scripts/build_regular_options_macro_event_calendar_source_repair_packet.py`, exposed as `npm run options:source-plan:macro-event-calendar`, now owns the read-only macro-event source repair packet.

Latest status is `macro_event_calendar_source_repair_packet_ready_for_operator_import_decision`. The packet reproduces the current macro-event baseline (`macro_event_calendar_status=blocked_macro_event_calendar_source_missing`, `event_count=0`, `covered_categories=[]`), defines `scheduled_macro_event_calendar_v1` required fields and frozen categories (`cpi`, `fomc_minutes`, `fomc_rate_decision`, `nonfarm_payrolls`, `pce`, `scheduled_fed_chair_testimony`), validates a fixture with before-market, during-market, after-market, and holiday/weekend-adjacent cases, rejects surprise/outcome/reaction/P&L fields, and emits a future tokened import/materialization command using `APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT`. The packet identifies macro-event long strangle and post-event IV-crush iron condor branches whose event-calendar blocker could clear after a valid future source.

Durable decision: this task authorizes only a future approval decision, not import. Macro-event source import/materialization, source-row writes, replay, and profitability claims remain not run. No evidence store mutation, protected-holdout consumption, live validation, auto-track, broker/order action, scanner/strategy/stop/sizing/proof-bar change, or promotion occurred.

## 2026-06-24: Direct VIX Source Repair Packet Is Ready For Future Import Decision

GPT-5.5 Pro selected `direct_point_in_time_vix_source_repair_packet_v1` after the 59-symbol ThetaTerminal resume retry parked. `scripts/build_regular_options_direct_vix_source_repair_packet.py`, exposed as `npm run options:source-plan:direct-vix`, now owns the read-only VIX source repair packet.

Latest status is `direct_vix_source_repair_packet_ready_for_operator_import_decision`. The packet reproduces the current VIX baseline (`point_in_time_vix_bucket_status=blocked_point_in_time_vix_source_missing`, `vix_source_rows_count=0`, `vix_coverage_pct=0.0`), defines `direct_vix_daily_clos

Relevant PROJECT_CONTEXT excerpt:
# Project Context

This repository is a mixed Next.js and FastAPI options research system. The active regular-options product is a supervised lane family for scanning, replay diagnostics, paper ideas, and tracked-position review. The browser UI is organized as a `Trading Desk` for open/closed positions, Alpaca paper-tracked positions, and an all-tracked-stock rollup, with live scan picks available behind the archive toggle, plus a replay-first `Strategy Lab` for validation and policy editing. FastAPI `python-backend/main.py` remains the app composition root, while profile, predictions, and tools routes are extracted into late-bound route modules so LLM agents can read route ownership without losing test-time monkeypatch behavior. Decorator-free application services now include `python-backend/proof_summary_service.py` for `/api/proof-summary`, `python-backend/replay_profit_service.py` for replay/profit readback assembly, and `python-backend/alpaca_paper_trading.py` for opt-in Alpaca paper order submission from proof-gated scanner-origin creates; proof, replay, scanner policy, broker-paper, and profit-cycle semantics stay in the domain modules named by `docs/replay-profit-contract.md` and `docs/DECISIONS.md`. The Trading Desk now treats open tracked positions, Alpaca paper-tracked rows, and open paper ideas as operator review surfaces, while closed/history-heavy rows load on demand through paged read routes. Closed Trades defaults to `Truth-grade`, the strict production-proof filter for live-production accuracy claims. `Realized P&L` remains available as a broader executable historical-learning slice, but historical current-policy guardrail replay is no longer surfaced in the operator dashboard because it can be mistaken for current recommendations or forward-audit performance.

The proof/evidence contract for those views is versioned at `data/contracts/proof-evidence-contract.json` and explained in `docs/proof-evidence-contract.md`. Backend proof predicates remain authoritative; frontend evidence groups flow from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts` as display/readability wrappers around the same proof classes, quote evidence classes, research/backfill markers, top-level and source-snapshot backfill/migration identity fields, and exit-basis tokens. Compact Trading Desk rows emit read-time `evidence_group` and `quote_evidence_class` diagnostics from the same contract; those labels are not persisted authority and stale frontend labels fail closed by contract version. Read-only audit and research reports use `scripts/quote_evidence_readback.py` for the same quote-class vocabulary, while separately labeling research/backfill row policy and production-proof falsehood. The generated `docs/proof-invariant-table.md`, sourced from `data/contracts/proof-invariant-cases.json`, is the shared backend/frontend regression matrix for raw exact, production proof, Truth-grade, and realized-P&L boundaries.

AI commodity / commodity-infrastructure options is a separate proof-first strategy lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`. The generated isolation owner is `docs/ai-commodity-isolation.md`, backed by `data/contracts/ai-commodity-isolation.json`. Its preferred final proof path is Alpaca SIP/OPRA bid/ask snapshot replay using `alpaca_opra_daily_snapshot` rows in `data/options-validation/options_history.db`.

The lane must not claim profitability from underlying bars, option OHLC bars, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, or in-sample-only sweeps. Final promotion requires point-in-time bid/ask or NBBO replay with realistic costs and validation splits.

Regular-options metric readbacks must now use the same proof posture. WFO simulation charges slippage and per-contract fees, expiry settlement uses expiry-day prices, blank/unknown evidence classes quarantine instead of fail-opening to live evidence, profit factor is nullable for no-loss samples, and PF claims use net USD P&L where available. The fresh forward evidence funnel still has `0` exact realized P&L rows and `0` promotion-ready rows; the current named-gate defect report is `docs/fresh-executable-evidence-defect-report-2026-06-09.md`. QQQ `id=537` now has a fresh executable exact HOLD review and SBUX `id=104` is closed from executable exact side-aware exit evidence, so the remaining fresh-evidence gate is legitimate exact realized exit P&L for QQQ `id=537` or another fresh candidate.

The regular supervised scanner safety contract is now lane-wide and metadata-driven. Regular playbooks default to fresh live validation and `position_tracking_mode=auto_track`; AI Commodity remains separate with scanner/tracked-position tracking disabled. Production scans default to portfolio caps on; caps-off scans are diagnostic unless explicitly allowed. Scanner-origin position and suggested-trade creation requires verified archived forward-scan lineage, a caps-enforced source scan, source `creation_eligible=true`, a current guardrail rerun, and exact-contract proof eligibility. When caps are enforced, existing positions, same-ticker/exact-spread exposure, max concurrent positions, cost-risk, drawdown, daily/weekly loss, sector/regime caps, and correlated-index exposure are hard blockers for auto-track and scanner-origin creation; near-cap notes and sizing reductions may remain cautions. Historical/research rows must use explicit manual modes and remain separated from production proof; control/scout proof labels do not make fresh executable regular rows paper-review-only.
The scanner creation safety contract is versioned at `data/contracts/scanner-creation-safety-contract.json` and explained in `docs/scanner-creation-safety-contract.md`. Scheduled auto-track requires explicit market-open state, an available caps-enforced exposure snapshot, auto-track playbook metadata, source `creation_eligible=true`, no creation blockers, proof eligibility, fresh profitability/promotion artifacts, and a passing regular open-risk governor; unknown market, exposure, lane, proof, or open-risk state is not a creation event. Manual Alpaca paper execution uses the same scanner-origin creation gate, submits exactly `1` contract through the Alpaca paper endpoint when explicitly enabled, and records broker-paper metadata separately from OPRA/NBBO production-proof evidence.
The candidate lifecycle status contract is generated by `scripts/candidate_lifecycle.py` at `data/contracts/candidate-lifecycle-contract.json`, `docs/candidate-lifecycle-contract.md`, and `src/lib/generated/candidateLifecycleContract.ts`. Queue builders, profitability/promotion gates, pending validation, disposition reporting, and fresh-evidence readbacks use this shared status/outcome vocabulary so paper-only, diagnostic, pending, and validation-attempted rows cannot disappear because a new status was added in only one module. Paper/probation lanes use `pending_paper_exact_evidence` for exact evidence collection; they do not enter `pending_live_validation`.
The Phase 2 regular-options forward cohort is preregistered at `data/contracts/forward-cohort-preregistration.json`, with generated doc `docs/forward-cohort-preregistration.md`. Freeze date is `2026-06-14` and eval date is `2026-07-28`. The frozen lanes are `volatility_expansion_observation` and the clean `bullish_pullback_observation` carrier set (`IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`). `scripts/lane_promotion_state.py`, daily all-lanes/starvation checks, audit completeness guards, scheduled scan logging, and pending validation read this contract so every other regular lane is parked outside the cohort with scans and chores disabled until evaluation or an explicit refreeze. The contract does not lower existing proof bars, consume the protected holdout, submit orders, or convert research/backfill rows into production proof.
Phase 2 candidat

```
