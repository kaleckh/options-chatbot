# Regular Options Underlying Daily History Source Import

- Status: `blocked_underlying_daily_history_source_import`.
- Source family: `point_in_time_underlying_daily_ohlcv_adjusted_v1`.
- Source family binding matched: `true`.
- Approval token valid: `true`.
- Source rows written: `false`.
- Source rows: `0`.
- Historical replay performed: `false`.
- Accepted profitability: `false`.

This import writes generated point-in-time underlying daily source rows only after the exact token, source family, parser, validator, coverage, prior-bar, and no-replay gates pass. It does not run replay, import option quotes, mutate trusted evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Blockers

- `underlying_source_csv_rows_rejected`
- `underlying_source_coverage_not_ready`

## Next Command

```powershell
npm run options:research:point-in-time-market-regime-inputs -- --no-write --json
```
