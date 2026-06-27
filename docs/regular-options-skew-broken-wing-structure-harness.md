# Regular Options Skew Broken-Wing Structure Harness

This generated report is read-only. It implements structure-specific broken-wing put-fly formulas and blocker mapping only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.

## Summary

- Status: `blocked_skew_broken_wing_structure_harness`.
- Concept: `low_mid_vix_index_skew_broken_wing_put_fly_v1`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.

## Remaining Blockers

- `missing_index_broken_wing_quote_surface`
- `missing_point_in_time_downside_skew_inputs`

## Blocker Burndown

| Blocker | Status | Note |
| --- | --- | --- |
| `missing_assignment_expiration_classifier` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_broken_wing_geometry_validator` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_full_denominator_status_mapping` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_index_broken_wing_quote_surface` | `unresolved` | Required before bounded replay; this harness does not import data or mutate evidence. |
| `missing_max_loss_margin_convention` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_point_in_time_downside_skew_inputs` | `unresolved` | Required before bounded replay; this harness does not import data or mutate evidence. |
| `missing_proof_boundary_labeling` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_protected_holdout_guard` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_strict_new_identity` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_three_leg_broken_wing_side_aware_entry_pricing` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |
| `missing_three_leg_broken_wing_side_aware_exit_pricing` | `satisfied_by_harness` | Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic. |

## Denominator Statuses

- `no_candidate`
- `rejected_skew_input`
- `rejected_geometry`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_priced`
- `open_waiting_policy_exit`
- `exact_exit_priced`
- `assignment_or_expiration_blocked`
- `missing_exit`
- `protected_holdout_blocked`
- `malformed_candidate`
- `duplicate_strict_new_identity`
- `replay_gate_blocked`

## Forbidden Actions

- `do_not_run_bounded_historical_replay`
- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_run_or_change_production_scanners`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort_rows`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_claim_accepted_profitability`
