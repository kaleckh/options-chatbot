# Paid Options Data Import Checklist

Use this when a paid historical options dataset arrives. The goal is to prove whether the options lane has real edge with executable historical prices, without mutating live tracked positions.

## What To Buy Or Export

Minimum useful coverage for the current lanes:

- Required symbols: `SPY`, `QQQ`, `DIA`, `XLK`, `GOOGL`, `NVDA`
- Quote fields: bid, ask, last or mark, contract symbol, expiration, strike, call/put, quote date/time
- Preferred window: at least 2024 through current date; more history is better
- Daily end-of-day is enough for first replay; intraday snapshots around entry and close are better
- Expired contracts must be included

## Canonical Destination

Import paid data into:

```text
data/options-validation/options_history.db
```

Do not put raw paid provider data under `data/profitability-lab`. That folder is for derived audit and research artifacts.

## Existing Import Paths

Daily Parquet manifest:

```powershell
python scripts\import_historical_options_snapshots.py --manifest path\to\manifest.json --json
```

CSV snapshot file:

```powershell
python scripts\import_historical_options_snapshots.py --input path\to\quotes.csv --source vendor_symbol_range --format csv --json
```

Provider-specific adapters should normalize into the existing `option_quote_snapshots` schema rather than creating a parallel store.

## Required Validation

After import, run:

```powershell
python scripts\audit_paid_data_readiness.py --force
python scripts\summarize_profitability_research.py
```

The readiness audit should reach `ready_for_exact_replay` before we make profitability claims from the paid dataset.

## Current Baseline Before Paid Data

As of the latest audit, the local historical store has trusted daily data for `SPY` and `QQQ`, but is missing `DIA`, `GOOGL`, `NVDA`, and `XLK`. That is why the broader tracked-winner lane is not historically proven yet.

## Do Not Do

- Do not auto-track positions from data import tests.
- Do not overwrite or delete existing tracked positions.
- Do not count nearest-listed contracts as promotion proof.
- Do not treat a dataset as useful until bid/ask coverage and required-symbol coverage pass.
