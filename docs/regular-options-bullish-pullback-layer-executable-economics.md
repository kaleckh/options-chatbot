# Regular Options Bullish-Pullback Layer Executable Economics

Status: `executable_economics_recomputed_profitable_but_preflight_blocked`.

This is a read-only side-aware executable-economics falsification report. It does not import quotes, mutate evidence stores, create trades, submit broker orders, change scanner policy, change stops/sizing/proof bars, enable live validation, enable auto-track, consume protected holdout, append forward cohort rows, or promote a lane.

## Selected Harness

- Layer: `layer_4_clean_exact`.
- Variant: `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1`.
- Source run: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`.
- Source metrics: `{"candidate_trade_count": 129, "exact_trade_count": 129, "profit_factor": 2.2, "quote_coverage_pct": 100.0, "stress_5pct_per_side_profit_factor": 1.67, "unpriced_trade_count": 0}`.

## Result

- Harness decision: `profitable_but_preflight_blocked`.
- Row counts: `{"missing_required_quote_rows": 3, "resolved_side_aware_rows": 126, "selected_rows": 129, "source_mark_mismatch_rows": 129, "tradable_executable_rows": 120, "zero_or_untradable_rows": 6}`.
- Side-aware executable metrics: `{"avg_net_usd": 380.08, "bootstrap": {"avg_net_lb_5pct": 235.07, "avg_net_point": 380.08, "branch_id": "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1:side_aware_executable", "draws": 10000, "n_trades": 120, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.27, "pf_point": 3.74, "pf_ub_95pct": 6.76, "statistical_confidence": "confident_positive"}, "gross_loss_usd": 16637.2, "gross_win_usd": 62247.2, "largest_winner_pct_of_net_profit": 10.16, "leave_one_out_pf_lower_bound": 3.463, "loss_trade_count": 37, "net_usd_total": 45610.0, "profit_factor": 3.7414, "row_count": 120, "top_three_winners_pct_of_net_profit": 28.36, "win_rate_pct": 69.2, "win_trade_count": 83}`.
- Dependency checks: `{"entry_date": {"dependency_gate_passed": true, "single_group_dependency": false, "top_group": "2025-10-21", "top_group_net_profit": 4632.4, "top_group_pct_of_net_profit": 10.16}, "exit_month": {"dependency_gate_passed": true, "single_group_dependency": false, "top_group": "2025-11", "top_group_net_profit": 19588.8, "top_group_pct_of_net_profit": 42.95}, "ticker": {"dependency_gate_passed": true, "single_group_dependency": false, "top_group": "LLY", "top_group_net_profit": 16187.0, "top_group_pct_of_net_profit": 35.49}}`.

## Blockers

- `missing_required_quotes`
- `source_mark_mismatch_rows`
- `zero_or_untradable_rows`

## Denominator Views

- `full_selected_fail_closed`: `{"missing_required_quote_rows": 3, "resolved_side_aware_rows": 126, "row_status_counts": {"executable_priced": 120, "missing_required_side_aware_price": 3, "zero_or_untradable": 6}, "selected_rows": 129, "source_mark_mismatch_rows": 129, "tradable_executable_rows": 120, "zero_or_untradable_rows": 6}`.
- `resolved_side_aware_only`: `{"note": "Rows with side-aware entry and exit prices; includes rows that may still be zero/untradable.", "row_count": 126}`.
- `source_mark_comparison`: `{"side_aware_executable_metrics": {"avg_net_usd": 380.08, "bootstrap": {"avg_net_lb_5pct": 235.07, "avg_net_point": 380.08, "branch_id": "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1:side_aware_executable", "draws": 10000, "n_trades": 120, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.27, "pf_point": 3.74, "pf_ub_95pct": 6.76, "statistical_confidence": "confident_positive"}, "gross_loss_usd": 16637.2, "gross_win_usd": 62247.2, "largest_winner_pct_of_net_profit": 10.16, "leave_one_out_pf_lower_bound": 3.463, "loss_trade_count": 37, "net_usd_total": 45610.0, "profit_factor": 3.7414, "row_count": 120, "top_three_winners_pct_of_net_profit": 28.36, "win_rate_pct": 69.2, "win_trade_count": 83}, "source_mark_metrics": {"avg_net_usd": 122.31, "bootstrap": {"avg_net_lb_5pct": 8.59, "avg_net_point": 122.31, "branch_id": "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1:source_marks", "draws": 10000, "n_trades": 129, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 1.03, "pf_point": 1.58, "pf_ub_95pct": 2.49, "statistical_confidence": "confident_positive"}, "gross_loss_usd": 27301.35, "gross_win_usd": 43078.9, "largest_winner_pct_of_net_profit": 17.49, "leave_one_out_pf_lower_bound": 1.4768, "loss_trade_count": 49, "net_usd_total": 15777.55, "profit_factor": 1.5779, "row_count": 129, "top_three_winners_pct_of_net_profit": 45.88, "win_rate_pct": 62.0, "win_trade_count": 80}, "source_mark_mismatch_rows": 129, "source_marks_are_diagnostic_only": true}`.
- `tradable_executable_only`: `{"avg_net_usd": 380.08, "bootstrap": {"avg_net_lb_5pct": 235.07, "avg_net_point": 380.08, "branch_id": "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1:side_aware_executable", "draws": 10000, "n_trades": 120, "no_loss_sample": false, "pf_defined_draws": 10000, "pf_lb_5pct": 2.27, "pf_point": 3.74, "pf_ub_95pct": 6.76, "statistical_confidence": "confident_positive"}, "gross_loss_usd": 16637.2, "gross_win_usd": 62247.2, "largest_winner_pct_of_net_profit": 10.16, "leave_one_out_pf_lower_bound": 3.463, "loss_trade_count": 37, "net_usd_total": 45610.0, "profit_factor": 3.7414, "row_count": 120, "top_three_winners_pct_of_net_profit": 28.36, "win_rate_pct": 69.2, "win_trade_count": 83}`.

## Non-Goals

- `do_not_create_trades_from_bullish_pullback_layer_executable_economics`
- `do_not_submit_broker_orders_from_bullish_pullback_layer_executable_economics`
- `do_not_enable_live_validation_from_bullish_pullback_layer_executable_economics`
- `do_not_enable_auto_track_from_bullish_pullback_layer_executable_economics`
- `do_not_change_scanner_policy_from_bullish_pullback_layer_executable_economics`
- `do_not_change_strategy_logic_from_bullish_pullback_layer_executable_economics`
- `do_not_change_stops_from_bullish_pullback_layer_executable_economics`
- `do_not_change_sizing_from_bullish_pullback_layer_executable_economics`
- `do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_executable_economics`
- `do_not_mutate_evidence_databases_from_bullish_pullback_layer_executable_economics`
- `do_not_import_quotes_from_bullish_pullback_layer_executable_economics`
- `do_not_append_forward_cohort_rows_from_bullish_pullback_layer_executable_economics`
- `do_not_consume_protected_holdout_from_bullish_pullback_layer_executable_economics`