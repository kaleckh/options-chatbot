# Regular Options Refreeze / Filter-Family Research Contract

This generated contract pre-registers the safe path for considering future refreeze or filter-family research while Fable CLI access is unavailable. It is not a refreeze, not scanner-policy approval, and not profitability evidence.

## Summary

- Status: `refreeze_filter_family_research_contract_ready`.
- Activation: `not_activated_operator_approval_required`.
- Fresh Fable readback available: `false`.
- Current policy preserved: `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906` with conditions hash `3b10d0306800e1a203480b80e4fafda03d5e1b6443d8d294cbf8ff7f20324967`.
- Current evidence bar preserved: `regular_options_filtered_forward_evidence_bar_v1`.
- Projection status: `bar_unreachable_without_state_change`.
- Stationarity status: `post_freeze_zero_within_historical_variation`.
- Forward rows: matched `0`, completed `0` / `30`.

## Allowed Research Questions

### `production_gate_drop_key_family_hypotheses`

- Basis: Use Phase 2 drop decomposition to propose falsifiable families around momentum, option_liquidity, and history_or_liquidity drops.
- Allowed output: `design_only_hypothesis_family_packet`.

### `scanner_materializer_timing_alignment_hypothesis`

- Basis: Use parity diagnostics, including the SPY 2026-06-16 scheduled-session versus materializer-entry-window divergence, as a research question only.
- Allowed output: `design_only_timing_alignment_packet`.

### `filter_family_refreeze_candidate_design`

- Basis: Only after operator approval, define candidate families and split rules before any code evaluates them.
- Allowed output: `separate_approval_required_preregistered_design`.

## Prerequisites

- `explicit_operator_approval_for_this_contract_or_a_successor_contract`
- `fresh_Fable_or_operator_review_when_CLI_is_available_again`
- `all_input_artifacts_loaded_and_hash_recorded`
- `candidate_family_definitions_written_before_any_family_evaluation`
- `selection_windows_exclude_consumed_audit_windows_and_protected_holdout`
- `current_forward_evidence_bar_contract_remains_unchanged`
- `current_frozen_policy_remains_active_until_a_separate_approved_refreeze`
- `all outputs label historical rows as research_only_not_forward_proof`

## Current Drop Evidence

- Scheduled Phase 2 drops: `2398`.
- Aggregate drop counts: `history_or_liquidity=304, momentum=1710, option_liquidity=384`.
- Returned picks: `0`.
- Returned-pick survival over recorded drops: `0.0`.

## Failure Criteria

- `proposal_reuses_consumed_2026_02_through_2026_05_audit_window_for_selection`
- `proposal_reuses_consumed_2022_01_through_2024_05_oos_window_for_selection_or_threshold_choice`
- `proposal_changes_current_policy_without_separate_approval`
- `proposal_changes_or_lowers_forward_evidence_bar`
- `proposal_imports_quotes_or_mutates_evidence`
- `proposal_consumes_protected_holdout`
- `proposal_claims_accepted_profitability_without_forward_exact_bar_evaluation`

## Boundary

This contract does not change scanner policy, filters, thresholds, proof bars, cohorts, quotes, evidence stores, protected holdout, live validation, auto-track, broker behavior, accepted profitability, or promotion.

## Prohibited Actions

- `do_not_change_current_frozen_policy_from_this_contract`
- `do_not_change_scanner_policy_from_this_contract`
- `do_not_change_filters_or_thresholds_from_this_contract`
- `do_not_change_proof_bars_from_this_contract`
- `do_not_append_cohort_rows_from_this_contract`
- `do_not_import_quotes_from_this_contract`
- `do_not_mutate_evidence_stores_from_this_contract`
- `do_not_consume_protected_holdout_from_this_contract`
- `do_not_enable_live_validation_from_this_contract`
- `do_not_enable_auto_track_from_this_contract`
- `do_not_submit_broker_orders_from_this_contract`
- `do_not_promote_any_lane_from_this_contract`
- `do_not_treat_historical_rows_or_diagnostics_as_forward_proof`
