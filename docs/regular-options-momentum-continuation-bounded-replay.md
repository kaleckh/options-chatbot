# Regular Options Momentum Continuation Bounded Replay

This generated report is read-only. It gates the bounded momentum-continuation replay behind the preregistered design inventory, the prior research replay, the proof-blocker resolution audit, strict-new accounting, and protected-holdout checks.

## Summary

- Status: `blocked_momentum_continuation_bounded_replay`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Historical replay performed in this gate: `false`.
- Existing proof-blocker resolution consumed: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Strict exact rows: `248`.
- Quote coverage: `0.711`.

## Replay Gate Blockers

- `eligible_quote_coverage_below_90_pct`
- `preregistered_stress_test_not_implemented`

## Metrics

- Total denominator rows: `1291`.
- Exact completed rows: `248`.
- Side-aware diagnostic rows: `783`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 201.37, "bootstrap_pf_lower_bound_5pct": 1.47, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 134.09, "avg_net_point": 201.37, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:entry_date", "cluster_count": 151, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 783, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.74, "pf_point": 2.3, "pf_ub_95pct": 3.02, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": 88.78, "avg_net_point": 201.37, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:market_week", "cluster_count": 41, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 783, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.47, "pf_point": 2.3, "pf_ub_95pct": 3.58, "statistical_confidence": "confident_positive"}, "ticker_week": {"avg_net_lb_5pct": 95.01, "avg_net_point": 201.37, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:ticker_week", "cluster_count": 196, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 783, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.51, "pf_point": 2.3, "pf_ub_95pct": 3.55, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 121317.6, "gross_win_usd": 278993.8, "loss_count": 281, "net_pnl_usd": 157676.2, "priced_row_count": 783, "profit_factor": 2.2997, "row_count": 783, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 502, "win_rate_pct": 64.11}`.
- Strict research metrics: `{"avg_pnl_usd": 288.8, "bootstrap_pf_lower_bound_5pct": 2.24, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 208.23, "avg_net_point": 288.8, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:entry_date", "cluster_count": 87, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 248, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.88, "pf_point": 4.08, "pf_ub_95pct": 5.94, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": 151.43, "avg_net_point": 288.8, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:market_week", "cluster_count": 27, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 248, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.24, "pf_point": 4.08, "pf_ub_95pct": 7.7, "statistical_confidence": "confident_positive"}, "ticker_week": {"avg_net_lb_5pct": 158.4, "avg_net_point": 288.8, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:ticker_week", "cluster_count": 94, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 248, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.36, "pf_point": 4.08, "pf_ub_95pct": 7.34, "statistical_confidence": "confident_positive"}}, "gross_loss_usd": 23242.0, "gross_win_usd": 94864.2, "loss_count": 75, "net_pnl_usd": 71622.2, "priced_row_count": 248, "profit_factor": 4.0816, "row_count": 248, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 173, "win_rate_pct": 69.76}`.
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
