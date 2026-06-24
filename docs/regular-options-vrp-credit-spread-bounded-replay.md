# Regular Options VRP Credit Spread Bounded Replay

This generated report is read-only. It gates a bounded VRP put-credit-spread replay behind preregistration, the completed structure harness, existing trusted quote data, and protected-holdout checks.

## Summary

- Status: `blocked_vrp_credit_spread_bounded_replay_gate`.
- Concept: `low_mid_vix_index_put_credit_spread_vrp_v1`.
- Historical replay performed: `false`.
- Accepted profitability: `false`.
- Quotes imported: `false`.
- Protected holdout consumed: `false`.

## Replay Gate Blockers

- `missing_index_credit_spread_quote_surface`
- `missing_point_in_time_vix_bucket`
- `missing_preregistered_candidate_geometry`

## Metrics

- Total denominator rows: `0`.
- Exact closed or settled rows: `0`.
- Net USD total: `0`.
- Point PF: `None`.
- Quote coverage: `0.0`.

## Forbidden Actions

- `do_not_create_broker_orders`
- `do_not_prepare_orders`
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
