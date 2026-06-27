# Regular Options Direct VIX Source Repair Packet

- Status: `direct_vix_source_repair_packet_superseded_by_materialized_vix`
- Source family: `direct_vix_daily_close`
- Current VIX bucket status: `point_in_time_vix_bucket_ready`
- VIX source rows: `505`
- VIX coverage: `100.0`
- Future import executed: `false`
- Downstream VIX bucket command executed: `false`
- Accepted profitability: `false`

This is a read-only source-repair packet. It does not import VIX rows, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.

## Superseded Source Boundary

No direct VIX source-import approval question is current because the point-in-time VIX bucket is already ready. The future command below remains provenance for the materialization boundary only; do not rerun direct VIX import unless a future artifact becomes missing, stale, malformed, or policy-incompatible.

## VIX-Blocked Branches

- `momentum_continuation`: VIX blockers `[]`; remaining non-VIX blockers `['bootstrap_pf_lower_bound_not_above_1_after_resolution', 'duplicate_within_research_harness', 'entry_missing_leg_quote', 'exit_missing_leg_quote', 'exit_value_negative', 'exit_zero_or_nonpositive_bid_ask', 'missing_net_usd_pnl', 'missing_point_in_time_breadth_confirmation', 'missing_point_in_time_qqq_momentum_confirmation', 'missing_point_in_time_spy_momentum_confirmation', 'net_usd_not_positive_after_resolution', 'rejected_not_call_debit_spread', 'rejected_outside_preregistered_universe', 'strict_rows_below_30_after_resolution']`
- `pmcc_diagonal`: VIX blockers `[]`; remaining non-VIX blockers `['missing_point_in_time_trend_or_regime_inputs', 'missing_trusted_pmcc_diagonal_quote_surface']`
- `macro_event_long_strangle`: VIX blockers `[]`; remaining non-VIX blockers `['macro_event_calendar_source_missing']`
- `vrp_credit_spread`: VIX blockers `[]`; remaining non-VIX blockers `['missing_index_credit_spread_quote_surface']`
- `flow_extreme_ratio_backspread`: VIX blockers `[]`; remaining non-VIX blockers `['missing_point_in_time_flow_extreme_input']`
- `dispersion_proxy_hybrid`: VIX blockers `[]`; remaining non-VIX blockers `['missing_dispersion_or_concentration_proxy_inputs']`

## Future Commands

```powershell
npm run options:source-import:direct-vix -- --source-file data/import-staging/vix/cboe_vix_daily_history.csv --lookback-start-date 2023-05-22 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family direct_vix_daily_close --approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json
npm run options:research:point-in-time-vix-bucket -- --source-family direct_vix_daily_close --as-of-date 2026-06-04 --json
```
