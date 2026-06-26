# Regular Options Underlying Daily Source Acquisition

Read-only intake preflight for trusted point-in-time 13-symbol underlying daily OHLCV/adjusted-close CSVs.

- Status: `blocked_underlying_daily_source_acquisition_missing`
- Candidate files: `0`
- Ready candidates: `0`
- Requested feature dates: `494`
- Source rows written: `false`
- Import command executed: `false`
- Blockers: `["trusted_source_csv_missing"]`

## Future Import Command

Run only after source materialization approval:

```bash
npm run options:source-import:underlying-daily-history -- --source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv --approval-token APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT --no-replay --json
```

## Candidate Files

- No staged CSV files were found.
