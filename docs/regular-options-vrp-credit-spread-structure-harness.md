# Regular Options VRP Credit Spread Structure Harness

This generated report is read-only. It implements deterministic structure math and readiness classification only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.

## Summary

- Status: `blocked_vrp_credit_spread_structure_harness`.
- Concept: `low_mid_vix_index_put_credit_spread_vrp_v1`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Quotes imported: `false`.
- Protected holdout consumed: `false`.

## Remaining Blockers

- `missing_index_credit_spread_quote_surface`

## Blocker Burndown

| Blocker | Status | Note |
| --- | --- | --- |
| `missing_assignment_expiration_classifier` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_credit_spread_side_aware_exit_pricing_engine` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_credit_spread_side_aware_pricing_engine` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_full_denominator_status_mapping` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_index_credit_spread_quote_surface` | `unresolved` | Requires existing point-in-time input or quote-surface artifact; harness does not import data. |
| `missing_margin_max_loss_convention` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_net_usd_pnl_after_costs` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_proof_boundary_labeling` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |
| `missing_protected_holdout_guard` | `resolved_by_harness` | Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic. |

## Denominator Statuses

- `no_candidate`
- `candidate_unpriced`
- `zero_bid_untradable`
- `entry_priced_exit_missing`
- `exact_closed`
- `expired_settled`
- `missing_required_quote`
- `rejected_liquidity`
- `protected_holdout_blocked`
- `malformed_candidate`

## Forbidden Actions

- `do_not_create_broker_orders`
- `do_not_prepare_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_run_or_change_production_scanners`
- `do_not_change_scanner_policy`
- `do_not_change_production_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort_rows`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_claim_accepted_profitability`
