# Regular Options Momentum Continuation Bounded Replay

This generated report is read-only. It gates the bounded momentum-continuation replay behind the preregistered design inventory, the prior research replay, the proof-blocker resolution audit, strict-new accounting, and protected-holdout checks.

## Summary

- Status: `blocked_momentum_continuation_bounded_replay`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Historical replay performed in this gate: `false`.
- Existing proof-blocker resolution consumed: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Strict exact rows: `340`.
- Quote coverage: `0.9802`.

## Replay Gate Blockers

- `bootstrap_pf_lower_bound_not_above_1_after_resolution`
- `preregistered_stress_test_not_implemented`

## Metrics

- Total denominator rows: `1291`.
- Exact completed rows: `340`.
- Side-aware diagnostic rows: `973`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 53.96, "bootstrap_pf_lower_bound_5pct": 0.84, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": -8.22, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:entry_date", "cluster_count": 158, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.97, "pf_point": 1.23, "pf_ub_95pct": 1.55, "statistical_confidence": "underpowered"}, "market_week": {"avg_net_lb_5pct": -44.44, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:market_week", "cluster_count": 41, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.84, "pf_point": 1.23, "pf_ub_95pct": 1.79, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": -40.92, "avg_net_point": 53.96, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:side_aware_net_pnl_usd_diagnostic:ticker_week", "cluster_count": 224, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 973, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.85, "pf_point": 1.23, "pf_ub_95pct": 1.76, "statistical_confidence": "underpowered"}}, "gross_loss_usd": 227502.4, "gross_win_usd": 280003.6, "loss_count": 464, "net_pnl_usd": 52501.2, "priced_row_count": 973, "profit_factor": 1.2308, "row_count": 973, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 509, "win_rate_pct": 52.31}`.
- Strict research metrics: `{"avg_pnl_usd": 93.52, "bootstrap_pf_lower_bound_5pct": 0.92, "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters", "bootstrap_sensitivity": {"entry_date": {"avg_net_lb_5pct": 27.25, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:entry_date", "cluster_count": 92, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.13, "pf_point": 1.5, "pf_ub_95pct": 1.98, "statistical_confidence": "confident_positive"}, "market_week": {"avg_net_lb_5pct": -13.54, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:market_week", "cluster_count": 28, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.94, "pf_point": 1.5, "pf_ub_95pct": 2.33, "statistical_confidence": "underpowered"}, "ticker_week": {"avg_net_lb_5pct": -18.47, "avg_net_point": 93.52, "branch_id": "regular_options_momentum_continuation_proof_blocker_resolution:proof_net_pnl_usd:ticker_week", "cluster_count": 112, "draws": 10000, "method": "cluster_block_bootstrap", "n_trades": 340, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 0.92, "pf_point": 1.5, "pf_ub_95pct": 2.43, "statistical_confidence": "underpowered"}}, "gross_loss_usd": 63486.8, "gross_win_usd": 95282.8, "loss_count": 163, "net_pnl_usd": 31796.0, "priced_row_count": 340, "profit_factor": 1.5008, "row_count": 340, "stress_pf": null, "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks", "win_count": 177, "win_rate_pct": 52.06}`.
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
