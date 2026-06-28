# Regular Options Underlying Daily Source Acquisition

Read-only intake preflight for trusted point-in-time 13-symbol underlying daily OHLCV/adjusted-close CSVs.

- Status: `ready_for_underlying_daily_source_import_approval`
- Candidate files: `1`
- Ready candidates: `1`
- Requested feature dates: `494`
- Source rows written: `false`
- Import command executed: `false`
- Blockers: `[]`

## Future Import Command

Run only after source materialization approval:

```bash
npm run options:source-import:underlying-daily-history -- --source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv --approval-token APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT --no-replay --json
```

## Candidate Files

- `data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv`: ready `true`, rows `7319`, coverage `True`, blockers `[]`
