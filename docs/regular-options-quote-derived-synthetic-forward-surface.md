# Regular Options Quote-Derived Synthetic Forward Surface

This generated report is read-only. It checks whether existing same-minute OPRA/NBBO call-put pairs can provide a research-only synthetic-forward input surface for opening-bucket replays without importing quotes, mutating evidence, creating trades, or changing scanner behavior.

## Summary

- Status: `blocked_quote_derived_synthetic_forward_surface`.
- Surface ready: `false`.
- Read-only DB open: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Requested bucket coverage: `0.0`.
- Train months covered: `0`.
- Latest-four months covered: `0`.

## Opening-Range Baseline

- Baseline status: `blocked_quote_surface_opening_range_reversal_replay`.
- Baseline denominator rows: `1976`.
- Baseline blocked missing underlying rows: `1976`.
- Baseline candidate rows: `0`.
- Baseline latest-four strict rows: `0`.

## Blockers

- `blocked_insufficient_synthetic_forward_coverage`
- `blocked_missing_call_put_pair_surface`

## Bucket Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_call_put_pairs` | `7904` |

## Boundary

synthetic-forward parity values are research signal inputs only, not executable fills, not P&L marks, not proof rows, and not accepted profitability

## Next Replay Command

No replay command emitted because the surface is not ready.

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
- `do_not_treat_quote_coverage_as_candidate_generation_proof`
- `do_not_treat_synthetic_forward_or_midpoint_values_as_executable_fill_or_pnl_evidence`
- `do_not_use_last_trade_eod_display_model_manual_or_stale_marks`
- `do_not_reclassify_zero_bid_or_untradable_rows_as_missing_data`
- `do_not_optimize_surface_formula_or_thresholds_on_pnl`
