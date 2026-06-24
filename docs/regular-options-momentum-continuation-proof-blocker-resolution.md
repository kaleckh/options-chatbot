# Regular Options Momentum Continuation Proof-Blocker Resolution

This report is generated from `scripts/build_regular_options_momentum_continuation_proof_blocker_resolution.py`. It is a read-only resolver inside the already-approved momentum-continuation research harness. It uses existing local artifacts and read-only trusted quote lookups only; it does not import quotes, mutate evidence stores, append forward rows, change scanner policy, or promote anything.

## Summary

- Status: `momentum_continuation_blocked_missing_local_proof_inputs`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Source denominator rows: `1291`.
- Reconstructed denominator rows: `1291`.
- Proof rows before resolution: `0`.
- Proof rows after resolution: `0`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.

## Resolution Counts

- Point-in-time inputs resolved: `0`.
- Point-in-time VIX buckets resolved: `1291`.
- Point-in-time market-regime input rows resolved: `0`.
- Point-in-time breadth confirmations resolved: `0`.
- Point-in-time SPY momentum confirmations resolved: `0`.
- Point-in-time QQQ momentum confirmations resolved: `0`.
- Side-aware quotes resolved: `783`.
- Proof-qualified candidate rows: `0`.
- Strict research metrics: `{"avg_pnl_usd": null, "bootstrap_pf_lower_bound_5pct": null, "gross_loss_usd": 0, "gross_win_usd": 0, "loss_count": 0, "net_pnl_usd": null, "priced_row_count": 0, "profit_factor": null, "row_count": 0, "stress_pf": null, "win_count": 0, "win_rate_pct": null}`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 201.07, "bootstrap_pf_lower_bound_5pct": null, "gross_loss_usd": 121252.6, "gross_win_usd": 278693.8, "loss_count": 281, "net_pnl_usd": 157441.2, "priced_row_count": 783, "profit_factor": 2.2985, "row_count": 783, "stress_pf": 2.2985, "win_count": 502, "win_rate_pct": 64.11}`.

## Blocker Counts

| Blocker | Rows |
| --- | ---: |
| `duplicate_within_research_harness` | 461 |
| `entry_missing_leg_quote` | 227 |
| `exit_missing_leg_quote` | 413 |
| `exit_value_negative` | 6 |
| `exit_zero_or_nonpositive_bid_ask` | 95 |
| `missing_net_usd_pnl` | 395 |
| `missing_point_in_time_breadth_confirmation` | 1291 |
| `missing_point_in_time_qqq_momentum_confirmation` | 1080 |
| `missing_point_in_time_spy_momentum_confirmation` | 395 |
| `rejected_not_call_debit_spread` | 290 |
| `rejected_outside_preregistered_universe` | 277 |

## Final Blockers

- `bootstrap_pf_lower_bound_not_above_1_after_resolution`
- `duplicate_within_research_harness`
- `entry_missing_leg_quote`
- `exit_missing_leg_quote`
- `exit_value_negative`
- `exit_zero_or_nonpositive_bid_ask`
- `missing_net_usd_pnl`
- `missing_point_in_time_breadth_confirmation`
- `missing_point_in_time_qqq_momentum_confirmation`
- `missing_point_in_time_spy_momentum_confirmation`
- `net_usd_not_positive_after_resolution`
- `rejected_not_call_debit_spread`
- `rejected_outside_preregistered_universe`
- `strict_rows_below_30_after_resolution`

## Forbidden Actions

- `do_not_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_release_scanner`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
