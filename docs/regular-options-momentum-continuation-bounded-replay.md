# Regular Options Momentum Continuation Bounded Replay

This generated report is read-only. It gates the bounded momentum-continuation replay behind the preregistered design, the readiness selector, the prior research replay, the proof-blocker resolution audit, strict-new accounting, and protected-holdout checks.

## Summary

- Status: `blocked_momentum_continuation_bounded_replay`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Historical replay performed in this gate: `false`.
- Existing proof-blocker resolution consumed: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Strict exact rows: `0`.
- Quote coverage: `0.6065`.

## Replay Gate Blockers

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

## Metrics

- Total denominator rows: `1291`.
- Exact completed rows: `0`.
- Side-aware diagnostic rows: `783`.
- Side-aware diagnostic metrics: `{"avg_pnl_usd": 201.07, "bootstrap_pf_lower_bound_5pct": null, "gross_loss_usd": 121252.6, "gross_win_usd": 278693.8, "loss_count": 281, "net_pnl_usd": 157441.2, "priced_row_count": 783, "profit_factor": 2.2985, "row_count": 783, "stress_pf": 2.2985, "win_count": 502, "win_rate_pct": 64.11}`.
- Strict research metrics: `{"avg_pnl_usd": null, "bootstrap_pf_lower_bound_5pct": null, "gross_loss_usd": 0, "gross_win_usd": 0, "loss_count": 0, "net_pnl_usd": null, "priced_row_count": 0, "profit_factor": null, "row_count": 0, "stress_pf": null, "win_count": 0, "win_rate_pct": null}`.
- Old-mark diagnostic metrics: `{"avg_pnl_usd": -65.68, "gross_loss_usd": 239470.75, "gross_win_usd": 180623.09, "loss_count": 427, "net_pnl_usd": -58847.66, "priced_row_count": 896, "profit_factor": 0.7543, "row_count": 896, "win_count": 469, "win_rate_pct": 52.34}`.

Historical positive diagnostics are not accepted profitability. They are only evidence for the next GPT-5.5 Pro branch decision because strict point-in-time inputs and forward proof remain missing.

## Next Oracle Instruction

Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time VIX/breadth input surface or explicit approved data repair changes the blocker. Select the next materially different, falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows.

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
