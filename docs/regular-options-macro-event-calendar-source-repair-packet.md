# Regular Options Macro-Event Calendar Source Repair Packet

- Status: `macro_event_calendar_source_repair_packet_ready_for_operator_import_decision`
- Source family: `scheduled_macro_event_calendar_v1`
- Current macro-event calendar status: `blocked_macro_event_calendar_source_missing`
- Current event count: `0`
- Future import executed: `false`
- Accepted profitability: `false`

This is a read-only source-repair packet. It does not import macro-event rows, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.

## Future Approval Question

Approve a future non-live, non-broker, tokened macro-event calendar source import/materialization from an operator-supplied official macro-event CSV into a generated point-in-time macro-event calendar artifact only, with no protected-holdout consumption and no replay until coverage and known-at gates pass.

## Downstream Branches

- `macro_event_long_strangle`: event blockers `['macro_event_calendar_source_missing']`; remaining non-event blockers `[]`
- `post_event_iv_crush_iron_condor`: event blockers `['future_replay_requires_point_in_time_macro_event_calendar']`; remaining non-event blockers `['iv_event_premium_proxy_missing']`
- `direct_vix_source_repair`: event blockers `[]`; remaining non-event blockers `[]`

## Future Commands

```powershell
npm run options:source-import:macro-event-calendar -- --source-file data/import-staging/macro_events/macro_event_calendar.csv --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family scheduled_macro_event_calendar_v1 --required-categories cpi,fomc_minutes,fomc_rate_decision,nonfarm_payrolls,pce,scheduled_fed_chair_testimony --approval-token APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT --no-replay --json
npm run options:research:macro-event-long-strangle-replay-readiness -- --json
npm run options:research:post-event-iv-crush-replay-readiness -- --json
```
