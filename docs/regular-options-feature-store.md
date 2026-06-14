# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `9476398`.
- Shared quote dates: `393` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 393 | 1365095 | 35743 | 100.0 | 98.75 | 17013 | 5.9016 | 0.0 |
| `QQQ` | 395 | 1390409 | 36288 | 100.0 | 98.99 | 14021 | 6.1763 | 0.0 |
| `IWM` | 393 | 995897 | 25370 | 100.0 | 99.98 | 168 | 4.8374 | 0.0 |
| `AAPL` | 393 | 460322 | 7531 | 100.0 | 98.49 | 6964 | 19.645 | 0.0 |
| `GOOGL` | 393 | 516309 | 9866 | 100.0 | 97.62 | 12303 | 22.654 | 0.0 |
| `UNH` | 393 | 1040690 | 7226 | 100.0 | 99.67 | 3392 | 31.6165 | 0.0 |
| `LLY` | 393 | 433666 | 9079 | 100.0 | 99.99 | 52 | 16.1205 | 0.0 |
| `JNJ` | 393 | 1202142 | 4490 | 100.0 | 97.16 | 34081 | 25.7505 | 0.0 |
| `XOM` | 393 | 388347 | 5487 | 100.0 | 96.81 | 12407 | 30.2149 | 0.0 |
| `CVX` | 393 | 318598 | 4589 | 100.0 | 91.34 | 27591 | 39.5309 | 0.0 |
| `COP` | 393 | 409774 | 5668 | 100.0 | 94.27 | 23493 | 42.4702 | 0.0 |
| `NEM` | 393 | 360350 | 5409 | 100.0 | 95.65 | 15671 | 38.4049 | 0.0 |
| `DIA` | 393 | 594799 | 9834 | 100.0 | 99.89 | 649 | 10.2724 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
