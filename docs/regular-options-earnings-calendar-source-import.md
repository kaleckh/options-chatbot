# Regular Options Earnings Calendar Source Import

- Status: `earnings_calendar_source_import_materialized`.
- Source rows written: `true`.
- Source rows: `74`.
- Downstream earnings calendar status: `point_in_time_earnings_calendar_ready`.

This import writes generated earnings-calendar source rows only. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Blockers

- None.
