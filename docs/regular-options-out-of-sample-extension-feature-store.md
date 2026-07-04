# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `40048765`.
- Shared quote dates: `1044` from `2022-01-03` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 1109 | 6581056 | 195931 | 100.0 | 97.6 | 157719 | 8.4068 | 0.0 |
| `QQQ` | 1106 | 6161529 | 187907 | 100.0 | 97.77 | 137505 | 8.3809 | 0.0 |
| `IWM` | 1099 | 5248594 | 97062 | 100.0 | 97.64 | 124021 | 10.1933 | 0.0 |
| `AAPL` | 1107 | 2018896 | 25959 | 100.0 | 94.06 | 119901 | 22.8738 | 0.0 |
| `GOOGL` | 1103 | 2376814 | 42754 | 100.0 | 93.02 | 166020 | 29.7904 | 0.0 |
| `UNH` | 1107 | 2613430 | 28257 | 100.0 | 96.22 | 98852 | 34.8995 | 0.0 |
| `LLY` | 1067 | 2059402 | 32703 | 100.0 | 95.44 | 93963 | 25.3404 | 0.0 |
| `JNJ` | 1109 | 2619622 | 18947 | 100.0 | 82.62 | 455398 | 54.9552 | 0.0 |
| `XOM` | 1108 | 2026778 | 21052 | 100.0 | 90.82 | 185975 | 39.2459 | 0.0 |
| `CVX` | 1107 | 1763044 | 20648 | 100.0 | 79.05 | 369341 | 61.448 | 0.0 |
| `COP` | 1107 | 2070429 | 22140 | 100.0 | 88.48 | 238469 | 49.7718 | 0.0 |
| `NEM` | 1109 | 1691621 | 19005 | 100.0 | 87.75 | 207295 | 48.8492 | 0.0 |
| `DIA` | 1101 | 2817550 | 48232 | 100.0 | 95.99 | 113050 | 18.5611 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
