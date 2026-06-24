# Regular Options Flow-Extreme Source Repair Packet

- Status: `flow_extreme_source_repair_packet_ready_for_operator_import_decision`
- Source family: `trusted_option_volume_open_interest_daily_v1`
- Current flow input status: `blocked_point_in_time_flow_extreme_input`
- Future import executed: `false`
- Accepted profitability: `false`

This is a read-only source-repair packet. It does not import flow rows, write real source_rows.jsonl, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.

## Future Commands

```powershell
npm run options:source-import:flow-extreme-volume-oi -- --source-file data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv --lookback-start-date 2023-06-01 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --underlyings SPY,QQQ --source-family trusted_option_volume_open_interest_daily_v1 --approval-token APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT --no-replay --json
npm run options:research:point-in-time-flow-extreme-input -- --no-write --json
npm run options:research:flow-extreme-ratio-backspread-replay-readiness -- --json
```
