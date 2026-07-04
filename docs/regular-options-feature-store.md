# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `40400934`.
- Shared quote dates: `1061` from `2022-01-03` to `2026-07-02`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 1126 | 6663145 | 205133 | 100.0 | 97.57 | 162011 | 8.5369 | 0.0 |
| `QQQ` | 1123 | 6238875 | 196628 | 100.0 | 97.74 | 141268 | 8.5292 | 0.0 |
| `IWM` | 1116 | 5285602 | 100843 | 100.0 | 97.61 | 126291 | 10.2786 | 0.0 |
| `AAPL` | 1124 | 2038372 | 27643 | 100.0 | 93.93 | 123663 | 23.2464 | 0.0 |
| `GOOGL` | 1120 | 2404192 | 45058 | 100.0 | 92.91 | 170466 | 30.1952 | 0.0 |
| `UNH` | 1124 | 2628534 | 29212 | 100.0 | 96.14 | 101533 | 35.0506 | 0.0 |
| `LLY` | 1084 | 2084856 | 34476 | 100.0 | 95.27 | 98660 | 25.8125 | 0.0 |
| `JNJ` | 1126 | 2628860 | 19527 | 100.0 | 82.56 | 458381 | 55.0526 | 0.0 |
| `XOM` | 1125 | 2035452 | 21748 | 100.0 | 90.75 | 188186 | 39.376 | 0.0 |
| `CVX` | 1124 | 1771102 | 21106 | 100.0 | 79.01 | 371730 | 61.5155 | 0.0 |
| `COP` | 1124 | 2080477 | 22686 | 100.0 | 88.44 | 240434 | 49.8719 | 0.0 |
| `NEM` | 1126 | 1702169 | 19579 | 100.0 | 87.71 | 209281 | 48.961 | 0.0 |
| `DIA` | 1118 | 2839298 | 49673 | 100.0 | 95.94 | 115334 | 18.6961 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
