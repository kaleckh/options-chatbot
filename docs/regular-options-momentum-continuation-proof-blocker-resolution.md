# Regular Options Momentum Continuation Proof-Blocker Resolution

This report is generated from `scripts/build_regular_options_momentum_continuation_proof_blocker_resolution.py`. It is a read-only resolver inside the already-approved momentum-continuation research harness. It uses existing local artifacts and read-only trusted quote lookups only; it does not import quotes, mutate evidence stores, append forward rows, change scanner policy, or promote anything.

## Summary

- Status: `momentum_continuation_blocked_incomplete_exit_policy_lifecycle`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Source denominator rows: `1291`.
- Reconstructed denominator rows: `1291`.
- Proof rows before resolution: `0`.
- Proof rows after resolution: `264`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.

## Resolution Counts

- Point-in-time inputs resolved: `1291`.
- Point-in-time VIX buckets resolved: `1291`.
- Point-in-time market-regime input rows resolved: `1291`.
- Point-in-time breadth confirmations resolved: `1031`.
- Point-in-time SPY momentum confirmations resolved: `181`.
- Point-in-time QQQ momentum confirmations resolved: `797`.
- Side-aware quotes resolved: `875`.
- Proof-qualified candidate rows: `264`.
- Strict research metrics: `{"avg_pnl_usd": 234.1, "bootstrap_pf_lower_bound_5pct": 1.71, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 158.22, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:entry_date", "cluster_count": 90, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.08, "pf_point": 2.86, "pf_ub_95pct": 3.99, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": 108.39, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:market_week", "cluster_count": 28, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.71, "pf_point": 2.86, "pf_ub_95pct": 4.63, "statistical_confidence": "confident_positive"}, "ticker_week": {"avg_net_lb_5pct": 111.2, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:ticker_week", "cluster_count": 103, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.73, "pf_point": 2.86, "pf_ub_95pct": 4.69, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 33310.0, "gross_win_usd": 95112.6, "loss_count": 90, "net_pnl_usd": 61802.6, "priced_row_count": 264, "profit_factor": 2.8554, "row_count": 264, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 174, "win_rate_pct": 65.91}`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 104.99, "bootstrap_pf_lower_bound_5pct": 0.98, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 40.4, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:entry_date", "cluster_count": 158, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.16, "pf_point": 1.49, "pf_ub_95pct": 1.91, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": -4.24, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:market_week", "cluster_count": 41, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.98, "pf_point": 1.49, "pf_ub_95pct": 2.2, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": 4.2, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:ticker_week", "cluster_count": 216, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.02, "pf_point": 1.49, "pf_ub_95pct": 2.16, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 187875.0, "gross_win_usd": 279739.0, "loss_count": 370, "net_pnl_usd": 91864.0, "priced_row_count": 875, "profit_factor": 1.489, "row_count": 875, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 505, "win_rate_pct": 57.71}`.

## Blocker Counts

| Blocker | Rows |
| --- | ---: |
| `duplicate_within_research_harness` | 461 |
| `entry_missing_leg_quote` | 227 |
| `exit_missing_leg_quote` | 21 |
| `exit_value_negative` | 23 |
| `missing_policy_exit_date` | 395 |
| `rejected_no_breadth_confirmation` | 260 |
| `rejected_no_qqq_momentum_confirmation` | 283 |
| `rejected_no_spy_momentum_confirmation` | 214 |
| `rejected_not_call_debit_spread` | 290 |
| `rejected_outside_preregistered_universe` | 277 |

## Final Blockers

- `missing_policy_exit_date`
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
