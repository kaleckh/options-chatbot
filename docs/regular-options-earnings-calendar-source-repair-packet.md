# Regular Options Earnings Calendar Source Repair Packet

- Status: `earnings_calendar_source_repair_packet_ready_for_operator_import_decision`
- Source family: `point_in_time_equity_earnings_calendar_v1`
- Current earnings calendar status: `point_in_time_earnings_calendar_ready`
- Current missing symbols: `[]`
- Future import executed: `false`
- Accepted profitability: `false`

This is a read-only source-repair packet. It does not import earnings rows, run replay, import quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.

## Future Approval Question

Approve a future non-live, non-broker, tokened earnings-calendar source import/materialization from an operator-supplied point-in-time earnings-calendar CSV into generated source rows only, with no replay and no protected-holdout consumption.

## Source Rule

operator-supplied vendor/export or archive that preserves known_at/source-published timestamps for scheduled earnings dates; current/live calendar lookups are not sufficient for historical point-in-time proof

## Future Commands

```powershell
npm run options:source-import:earnings-calendar -- --source-file data/import-staging/earnings/point_in_time_equity_earnings_calendar.csv --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --required-equity-symbols AAPL,COP,CVX,GOOGL,JNJ,LLY,NEM,UNH,XOM --source-family point_in_time_equity_earnings_calendar_v1 --approval-token APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT --no-replay --json
npm run options:research:point-in-time-earnings-calendar -- --json
npm run options:research:historical-scanner-input-surface-tracker -- --json
npm run options:research:historical-frozen-scanner-replay-adapter -- --json
npm run options:audit:historical-simulated-forward -- --json
```
