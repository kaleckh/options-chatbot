# Regular Options Flow-Extreme Denominator/Dedupe Bridge

This generated artifact is a read-only bridge for the flow-extreme ratio/backspread branch. It defines the full denominator status contract and strict-new opportunity identity hashing without running replay or counting fixture rows as proof.

## Summary

- Status: `flow_extreme_denominator_dedupe_bridge_ready`.
- Full denominator mapping: `ready`.
- Strict-new dedupe: `ready`.
- Proof rows: `0`.
- Accepted profitability: `false`.
- Fixture source proof eligible: `false`.

## Identity Fields

- `concept_id`
- `structure`
- `underlying`
- `signal_date`
- `planned_entry_timestamp`
- `option_rights`
- `expirations`
- `strikes`
- `leg_sides`
- `leg_ratios`
- `entry_policy`
- `exit_policy`
- `candidate_source_id`

## Denominator Status Contract

- `candidate_not_generated_missing_flow_input`
- `candidate_not_generated_missing_vix_bucket`
- `candidate_rejected_missing_required_flow_fields`
- `candidate_rejected_missing_vix_bucket`
- `candidate_rejected_unbounded_or_undefined_risk`
- `candidate_rejected_missing_leg_quote`
- `candidate_rejected_zero_bid_or_untradable`
- `candidate_rejected_crossed_or_stale_quote`
- `candidate_duplicate_existing_base_stack`
- `candidate_duplicate_within_research_harness`
- `candidate_protected_holdout_overlap`
- `priced_fixture_not_proof_eligible`
- `readiness_candidate_priced_not_replayed`
- `no_pick_explicit`
- `blocked_source_missing`

## Candidate Fixture Results

| Case | Status | Blockers |
| --- | --- | --- |
| `flow_ratio_bridge_clean_fixture` | `readiness_candidate_priced_not_replayed` | - |

## Bridge Blockers

- None.

## Forbidden Actions

- `do_not_run_replay`
- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_fixture_rows_as_profitability_or_forward_proof`
