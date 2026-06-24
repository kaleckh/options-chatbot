# Regular Options Preregistered Playbook Readiness Selector

This report is generated from `scripts/build_regular_options_preregistered_playbook_readiness_selector.py`. It is a read-only selector across completed preregistered design artifacts. It does not implement scanner or playbook logic, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `candidate_selected_for_research_only_implementation_approval`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.
- Forward strict completed rows: `0` / `30`.
- Cohort log status: `missing`.

## Selected Candidate

- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Status: `candidate_for_research_only_implementation_approval`.
- Rationale: `Breadth-confirmed index/QQQ momentum continuation debit spread` is the lowest-complexity valid preregistered design and uses the simplest defined-risk spread proof path.

## Recommended Operator Approval Question

Do you approve one research-only implementation/replay harness for `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1` only, writing derived research artifacts only, with no live validation, no auto-track, no broker orders, no quote import, no evidence-store mutation, no protected-holdout consumption, no scanner release, no stop/sizing/proof-bar changes, and no promotion?

## Inventory

| Rank | Concept | Structure | Readiness | Blockers |
| --- | --- | --- | --- | --- |
| 1 | `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1` | `defined_risk_call_debit_spreads_only` | `candidate_for_research_only_implementation_approval` | - |
| 2 | `low_mid_vix_macro_event_long_strangle_v1` | `defined_risk_long_straddles_or_strangles_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 3 | `low_mid_vix_index_skew_broken_wing_put_fly_v1` | `defined_risk_broken_wing_put_butterflies_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 4 | `low_mid_vix_index_pmcc_diagonal_income_v1` | `defined_risk_pmcc_style_call_diagonals_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 5 | `post_event_iv_crush_index_iron_condor_v1` | `defined_risk_short_iron_condors_or_iron_butterflies_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 6 | `index_flow_extreme_mean_reversion_ratio_backspread_v1` | `defined_risk_ratio_spreads_or_backspreads_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 7 | `index_constituent_dispersion_proxy_defined_risk_hybrid_v1` | `defined_risk_index_constituent_debit_credit_hybrid_pairs_only` | `requires_readiness_audit_before_approval` | `no_structure_specific_readiness_audit_yet` |
| 8 | `low_mid_vix_index_put_credit_spread_vrp_v1` | `defined_risk_put_credit_spreads_only` | `blocked_by_known_readiness_audit` | `missing_credit_spread_side_aware_pricing_engine`, `missing_credit_spread_side_aware_exit_pricing_engine`, `missing_full_denominator_status_mapping`, `missing_assignment_expiration_classifier`, `missing_margin_max_loss_convention`, `missing_point_in_time_vix_bucket`, `missing_index_credit_spread_quote_surface`, `missing_protected_holdout_guard` |
| 9 | `low_mid_vix_index_calendar_term_structure_dislocation_v1` | `defined_risk_calendar_or_diagonal_debit_spreads_only` | `blocked_by_known_readiness_audit` | `missing_calendar_diagonal_side_aware_pricing_engine`, `missing_calendar_diagonal_exit_or_expiry_engine`, `missing_full_denominator_status_mapping`, `missing_front_leg_assignment_expiration_classifier`, `missing_roll_or_expiry_policy`, `missing_point_in_time_term_structure_inputs`, `missing_index_calendar_quote_surface`, `missing_strict_new_dedupe` |

## Forbidden Actions

- `do_not_implement_scanner_or_playbook_logic`
- `do_not_run_historical_replay`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
