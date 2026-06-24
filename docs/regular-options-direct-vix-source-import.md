# Regular Options Direct VIX Source Import

- Status: `direct_vix_source_import_materialized`.
- Source rows written: `true`.
- Source rows: `505`.
- Downstream VIX bucket status: `point_in_time_vix_bucket_ready`.
- Downstream coverage: `100.0`.

This import writes generated VIX source rows and the frozen VIX bucket policy only. It does not run replay, import option quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Blockers

- None.
