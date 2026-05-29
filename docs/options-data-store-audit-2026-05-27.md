# Options Data Store Audit - 2026-05-27

## Verdict

The quote data is centralized enough to keep using `data/options-validation/options_history.db` as the source of truth. The main problem is not a missing central DB; it is that raw import artifacts, run outputs, and forward-tracking logs live in different places and need clear roles.

## Current Layout

- Quote source of truth: `data/options-validation/options_history.db`
- Forward-tracking source of truth: `data/options-validation/forward_tracking_authoritative.db`
- Raw import artifacts: `data/options-validation/*/imports` and `data/options-validation/thetadata-nbbo`
- Backtest run artifacts: `data/options-validation/runs`
- Robustness/profitability artifacts: `data/profitability-lab`
- Lane universes: `data/options-lanes/universes`
- Forward-tracking logs: `data/forward-tracking`

## Live DB Snapshot

- quote rows: 26,146,760
- import batches: 1,737
- DB size after index cleanup: about 13.15 GB
- quote date range: 2024-01-02 to 2026-05-22
- distinct underlyings: 82
- distinct contracts: 774,722

Trusted quote rows:

- ThetaData OPRA/NBBO 1m intraday: 7,276,952 rows, 60 underlyings, 252 quote dates
- ThetaData daily EOD: 2,183,212 rows, 60 underlyings, 125 quote dates
- Alpaca daily snapshots: 90,285 rows, 82 underlyings, 3 quote dates

Research quote rows are also present but are separated by `data_trust='research'` in `import_batches`.

## Changes Made

Added schema/index support in `historical_options_store.py` and applied the same indexes to the live DB:

- `idx_option_quotes_source_batch_snapshot_date`
- `idx_import_batches_source_trust_kind`

Added reusable audit script:

```powershell
python .\scripts\audit_options_data_store.py --json
```

## Policy

Use `options_history.db` for quote lookup. Treat CSV/parquet files as raw import artifacts only. Treat run JSON and profitability JSON as reproducibility artifacts, not source quote data.

Forward tracking should use `forward_tracking_authoritative.db` as the canonical state store. JSONL/text files under `data/forward-tracking` should remain append-only logs unless a later migration explicitly promotes one.
