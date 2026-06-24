# Regular Options Direct VIX Source Repair Packet

- Status: `direct_vix_source_repair_packet_ready_for_operator_import_decision`
- Source family: `direct_vix_daily_close`
- Current VIX bucket status: `blocked_point_in_time_vix_source_missing`
- VIX source rows: `0`
- VIX coverage: `0.0`
- Future import executed: `false`
- Downstream VIX bucket command executed: `false`
- Accepted profitability: `false`

This is a read-only source-repair packet. It does not import VIX rows, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.

## Future Approval Question

Approve a future non-live, non-broker, tokened direct VIX source import/materialization from an operator-supplied official daily VIX CSV into a generated point-in-time VIX source artifact only, with no protected-holdout consumption and no replay until coverage and known-at gates pass.

## VIX-Blocked Branches

- `momentum_continuation`: VIX blockers `['missing_point_in_time_vix_bucket']`; remaining non-VIX blockers `['bootstrap_pf_lower_bound_not_above_1_after_resolution', 'duplicate_within_research_harness', 'entry_missing_leg_quote', 'exit_missing_leg_quote', 'exit_value_negative', 'exit_zero_or_nonpositive_bid_ask', 'missing_net_usd_pnl', 'missing_point_in_time_breadth_confirmation', 'missing_point_in_time_qqq_momentum_confirmation', 'missing_point_in_time_spy_momentum_confirmation', 'net_usd_not_positive_after_resolution', 'rejected_not_call_debit_spread', 'rejected_outside_preregistered_universe', 'strict_rows_below_30_after_resolution']`
- `pmcc_diagonal`: VIX blockers `['point_in_time_vix_bucket_blocked']`; remaining non-VIX blockers `['missing_point_in_time_trend_or_regime_inputs', 'missing_trusted_pmcc_diagonal_quote_surface']`
- `macro_event_long_strangle`: VIX blockers `['point_in_time_vix_source_missing', 'missing_vix_bucket_threshold_policy', 'vix_bucket_date_coverage_incomplete']`; remaining non-VIX blockers `['macro_event_calendar_source_missing']`
- `vrp_credit_spread`: VIX blockers `['missing_point_in_time_vix_bucket']`; remaining non-VIX blockers `['missing_credit_spread_side_aware_pricing_engine', 'missing_credit_spread_side_aware_exit_pricing_engine', 'missing_full_denominator_status_mapping', 'missing_assignment_expiration_classifier', 'missing_margin_max_loss_convention', 'missing_index_credit_spread_quote_surface', 'missing_protected_holdout_guard']`
- `flow_extreme_ratio_backspread`: VIX blockers `['missing_point_in_time_vix_bucket']`; remaining non-VIX blockers `['missing_point_in_time_flow_extreme_input']`
- `dispersion_proxy_hybrid`: VIX blockers `['point_in_time_vix_bucket_blocked']`; remaining non-VIX blockers `['missing_dispersion_or_concentration_proxy_inputs', 'missing_pair_construction_engine', 'missing_side_aware_all_leg_pair_pricing', 'missing_pair_max_loss_or_collateral_convention', 'missing_full_denominator_mapping', 'missing_strict_new_dedupe']`

## Future Commands

```powershell
npm run options:source-import:direct-vix -- --source-file data/import-staging/vix/cboe_vix_daily_history.csv --lookback-start-date 2023-05-22 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family direct_vix_daily_close --approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json
npm run options:research:point-in-time-vix-bucket -- --source-family direct_vix_daily_close --as-of-date 2026-06-04 --json
```
