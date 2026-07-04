# Regular Options Point-in-Time VIX Bucket

This report is generated from `scripts/build_regular_options_point_in_time_vix_bucket.py`. It is a read-only point-in-time VIX low/mid bucket validator for future regular-options research. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, consume protected holdout, or promote any lane.

## Summary

- Status: `blocked_point_in_time_vix_bucket_validation`.
- Point-in-time VIX low/mid bucket available: `false`.
- Source rows: `505`.
- Requested dates: `1044`.
- Covered dates: `505`.
- Coverage: `48.3716`.
- Late known-at rows: `0`.
- Leakage rejects: `0`.
- Threshold source: `direct_vix_daily_close_import_policy_v1`.

## Join Rule

For daily close VIX, bucket_date_et candidate entries may use only rows whose known_at_utc is before bucket_date_et in ET. Intraday rows require known_at_utc <= candidate_entry_timestamp_utc when that timestamp is supplied.

## Blockers

- `vix_bucket_date_coverage_incomplete`

## Rejected Rows

- None.

## Forbidden Actions

- `broker_orders`
- `broker_order_preparation`
- `live_validation`
- `auto_track`
- `production_scanner_changes`
- `strategy_logic_changes`
- `stop_changes`
- `sizing_changes`
- `proof_bar_changes`
- `quote_import`
- `options_history_db_mutation`
- `forward_or_evidence_store_mutation`
- `protected_holdout_consumption`
- `promotion`
- `historical_option_replay`
- `treating_vix_buckets_as_profitability_proof`
