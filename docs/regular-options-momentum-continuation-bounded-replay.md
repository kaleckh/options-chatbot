# Regular Options Momentum Continuation Bounded Replay

This generated report is read-only. It gates the bounded momentum-continuation replay behind the preregistered design inventory, the prior research replay, the proof-blocker resolution audit, strict-new accounting, and protected-holdout checks.

## Summary

- Status: `blocked_momentum_continuation_bounded_replay`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Historical replay performed in this gate: `false`.
- Existing proof-blocker resolution consumed: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Strict exact rows: `264`.
- Quote coverage: `0.7649`.

## Replay Gate Blockers

- `eligible_quote_coverage_below_90_pct`
- `preregistered_stress_test_not_implemented`

## Metrics

- Total denominator rows: `1291`.
- Exact completed rows: `264`.
- Side-aware diagnostic rows: `875`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 104.99, "bootstrap_pf_lower_bound_5pct": 0.98, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 40.4, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:entry_date", "cluster_count": 158, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.16, "pf_point": 1.49, "pf_ub_95pct": 1.91, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": -4.24, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:market_week", "cluster_count": 41, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.98, "pf_point": 1.49, "pf_ub_95pct": 2.2, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": 4.2, "avg_net_point": 104.99, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:ticker_week", "cluster_count": 216, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 875, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.02, "pf_point": 1.49, "pf_ub_95pct": 2.16, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 187875.0, "gross_win_usd": 279739.0, "loss_count": 370, "net_pnl_usd": 91864.0, "priced_row_count": 875, "profit_factor": 1.489, "row_count": 875, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 505, "win_rate_pct": 57.71}`.
- Strict research metrics: `{"avg_pnl_usd": 234.1, "bootstrap_pf_lower_bound_5pct": 1.71, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 158.22, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:entry_date", "cluster_count": 90, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.08, "pf_point": 2.86, "pf_ub_95pct": 3.99, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": 108.39, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:market_week", "cluster_count": 28, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.71, "pf_point": 2.86, "pf_ub_95pct": 4.63, "statistical_confidence": "confident_positive"}, "ticker_week": {"avg_net_lb_5pct": 111.2, "avg_net_point": 234.1, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:ticker_week", "cluster_count": 103, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 264, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.73, "pf_point": 2.86, "pf_ub_95pct": 4.69, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 33310.0, "gross_win_usd": 95112.6, "loss_count": 90, "net_pnl_usd": 61802.6, "priced_row_count": 264, "profit_factor": 2.8554, "row_count": 264, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 174, "win_rate_pct": 65.91}`.
- Old-mark diagnostic metrics: `{"avg_pnl_usd": -65.68, "gross_loss_usd": 239470.75, "gross_win_usd": 180623.09, "loss_count": 427, "net_pnl_usd": -58847.66, "priced_row_count": 896, "profit_factor": 0.7543, "row_count": 896, "win_count": 469, "win_rate_pct": 52.34}`.

Historical positive diagnostics are not accepted profitability. They are only evidence for the next GPT-5.5 Pro branch decision because strict point-in-time inputs and forward proof remain missing.

## Next Oracle Instruction

Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time breadth/momentum input surface or explicit approved data repair changes the blocker. Select the next materially different, falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows.

## Forbidden Actions

- `do_not_return_or_reimplement_momentum_research_replay`
- `do_not_return_or_reimplement_momentum_proof_blocker_resolution`
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
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
