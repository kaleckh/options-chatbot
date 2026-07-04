# Regular Options Local Quote Structure Capability Matrix

This generated report is read-only. It inventories which option structures can be constructed and completed from existing trusted OPRA/NBBO bid/ask rows at fixed entry and exit buckets. It is not replay, not P&L proof, not candidate-generation proof, and not promotion.

## Summary

- Status: `local_quote_surface_only_structures_exhausted_under_current_data`.
- Matrix id: `local_opra_nbbo_structure_capability_matrix_v1`.
- Read-only DB open: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Replay-feasible structures: `0`.
- Local quote-surface-only exhausted: `true`.

## Structure Summary

| Structure | Feasible | Full Window | Latest Four | Train Months | Latest Months | Smallest Blocker |
|---|---:|---:|---:|---:|---:|---|
| `long_single_leg_calls_puts` | `false` | `10116` | `6544` | `6` | `4` | `insufficient_train_months` |
| `same_expiration_same_type_verticals` | `false` | `27428` | `20358` | `4` | `4` | `insufficient_train_months` |
| `same_expiration_same_type_butterflies` | `false` | `8708` | `5691` | `2` | `4` | `insufficient_train_months` |
| `same_expiration_same_type_condors` | `false` | `8532` | `5548` | `3` | `4` | `insufficient_train_months` |
| `straddles_strangles` | `false` | `4` | `4` | `0` | `2` | `insufficient_full_window_rows` |
| `iron_flies_iron_condors` | `false` | `0` | `0` | `0` | `0` | `insufficient_full_window_rows` |
| `same_type_calendars_diagonals` | `false` | `3124` | `1901` | `2` | `2` | `insufficient_train_months` |
| `bounded_ratio_backspread_shapes` | `false` | `8963` | `5799` | `3` | `4` | `insufficient_train_months` |

## Next Replay Candidate

`null`

## Blockers

- `insufficient_full_window_rows`
- `insufficient_latest_four_months`
- `insufficient_latest_four_rows`
- `insufficient_train_months`

## Boundary

Capability rows are bid/ask availability diagnostics only; they are not replay P&L, not candidate-generation proof, not forward proof, and not accepted profitability.

## Forbidden Actions

- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_append_forward_paper_shadow_cohort`
- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_change_production_scanner_policy`
- `do_not_change_production_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_treat_historical_rows_as_forward_proof`
- `do_not_treat_capability_rows_as_profitability_proof`
- `do_not_treat_quote_coverage_as_candidate_generation_proof`
- `do_not_use_midpoint_stale_eod_display_last_model_manual_or_synthetic_marks_as_fill_or_pnl_evidence`
- `do_not_reclassify_zero_bid_or_untradable_rows_as_missing_data`
- `do_not_optimize_structure_or_bucket_choice_on_pnl`
