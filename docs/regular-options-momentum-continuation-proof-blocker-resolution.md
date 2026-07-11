# Regular Options Momentum Continuation Proof-Blocker Resolution

This report is generated from `scripts/build_regular_options_momentum_continuation_proof_blocker_resolution.py`. It is a read-only resolver inside the already-approved momentum-continuation research harness. It uses existing local artifacts and read-only trusted quote lookups only; it does not import quotes, mutate evidence stores, append forward rows, change scanner policy, or promote anything.

## Summary

- Status: `momentum_continuation_rejected_negative_or_underpowered_after_proof_resolution`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Source denominator rows: `1291`.
- Reconstructed denominator rows: `1291`.
- Proof rows before resolution: `0`.
- Proof rows after resolution: `340`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.

## Resolution Counts

- Point-in-time inputs resolved: `1291`.
- Point-in-time VIX buckets resolved: `1291`.
- Point-in-time market-regime input rows resolved: `1291`.
- Point-in-time breadth confirmations resolved: `1031`.
- Point-in-time SPY momentum confirmations resolved: `181`.
- Point-in-time QQQ momentum confirmations resolved: `797`.
- Side-aware quotes resolved: `973`.
- Proof-qualified candidate rows: `340`.
- Strict research metrics: `{"avg_pnl_usd": 93.52, "bootstrap_pf_lower_bound_5pct": 0.92, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 27.25, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:entry_date", "cluster_count": 92, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.13, "pf_point": 1.5, "pf_ub_95pct": 1.98, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": -13.54, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:market_week", "cluster_count": 28, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.94, "pf_point": 1.5, "pf_ub_95pct": 2.33, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": -18.47, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:ticker_week", "cluster_count": 112, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.92, "pf_point": 1.5, "pf_ub_95pct": 2.43, "statistical_confidence": "underpowered"}}, "gross_loss_usd": 63486.8, "gross_win_usd": 95282.8, "loss_count": 163, "net_pnl_usd": 31796.0, "priced_row_count": 340, "profit_factor": 1.5008, "row_count": 340, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 177, "win_rate_pct": 52.06}`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 53.96, "bootstrap_pf_lower_bound_5pct": 0.84, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": -8.22, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:entry_date", "cluster_count": 158, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.97, "pf_point": 1.23, "pf_ub_95pct": 1.55, "statistical_confidence": "underpowered"}, "market_week": {"avg_net_lb_5pct": -44.44, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:market_week", "cluster_count": 41, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.84, "pf_point": 1.23, "pf_ub_95pct": 1.79, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": -40.92, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:ticker_week", "cluster_count": 224, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.85, "pf_point": 1.23, "pf_ub_95pct": 1.76, "statistical_confidence": "underpowered"}}, "gross_loss_usd": 227502.4, "gross_win_usd": 280003.6, "loss_count": 464, "net_pnl_usd": 52501.2, "priced_row_count": 973, "profit_factor": 1.2308, "row_count": 973, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 509, "win_rate_pct": 52.31}`.

## Blocker Counts

| Blocker | Rows |
| --- | ---: |
| `duplicate_within_research_harness` | 461 |
| `entry_missing_leg_quote` | 227 |
| `exit_missing_leg_quote` | 91 |
| `exit_value_negative` | 23 |
| `missing_policy_exit_date` | 227 |
| `rejected_no_breadth_confirmation` | 260 |
| `rejected_no_qqq_momentum_confirmation` | 283 |
| `rejected_no_spy_momentum_confirmation` | 214 |
| `rejected_not_call_debit_spread` | 290 |
| `rejected_outside_preregistered_universe` | 277 |

## Final Blockers

- `bootstrap_pf_lower_bound_not_above_1_after_resolution`
- `preregistered_stress_test_not_implemented`

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
