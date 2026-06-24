# Regular Options Term-Structure Calendar Structure Harness

This generated report is read-only. It implements structure-specific calendar/diagonal formulas and blocker mapping only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.

- Status: `blocked_term_structure_calendar_structure_harness`.
- Concept: `low_mid_vix_index_calendar_term_structure_dislocation_v1`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.

## Remaining Blockers

- `missing_index_calendar_quote_surface`
- `missing_point_in_time_term_structure_inputs`
- `missing_preregistered_calendar_diagonal_geometry`
- `missing_strict_new_dedupe`

## Blocker Burndown

| Blocker | Status | Note |
| --- | --- | --- |
| `missing_calendar_diagonal_exit_or_expiry_engine` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_calendar_diagonal_side_aware_pricing_engine` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_front_leg_assignment_expiration_classifier` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_full_denominator_status_mapping` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_index_calendar_quote_surface` | `unresolved` | Required before any bounded replay; no data import or policy change was performed. |
| `missing_net_usd_pnl_after_costs` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_point_in_time_term_structure_inputs` | `unresolved` | Required before any bounded replay; no data import or policy change was performed. |
| `missing_preregistered_calendar_diagonal_geometry` | `unresolved` | Required before any bounded replay; no data import or policy change was performed. |
| `missing_proof_boundary_labeling` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_protected_holdout_guard` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_roll_or_expiry_policy` | `satisfied_by_harness` | Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic. |
| `missing_strict_new_dedupe` | `unresolved` | Required before any bounded replay; no data import or policy change was performed. |

## Forbidden Actions

- `do_not_run_full_historical_replay`
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
