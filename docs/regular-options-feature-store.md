# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `11434494`.
- Shared quote dates: `474` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 474 | 1596263 | 38550 | 100.0 | 98.93 | 17013 | 5.3327 | 0.0 |
| `QQQ` | 476 | 1559851 | 38993 | 100.0 | 99.1 | 14037 | 5.6862 | 0.0 |
| `IWM` | 474 | 1208053 | 27380 | 100.0 | 99.99 | 174 | 4.2995 | 0.0 |
| `AAPL` | 474 | 586126 | 8763 | 100.0 | 98.26 | 10174 | 18.4207 | 0.0 |
| `GOOGL` | 474 | 642309 | 10946 | 100.0 | 97.01 | 19227 | 22.5962 | 0.0 |
| `UNH` | 474 | 1145998 | 8532 | 100.0 | 99.53 | 5370 | 30.5066 | 0.0 |
| `LLY` | 474 | 568794 | 10775 | 100.0 | 99.98 | 118 | 14.6888 | 0.0 |
| `JNJ` | 474 | 1331572 | 5744 | 100.0 | 95.11 | 65180 | 29.3392 | 0.0 |
| `XOM` | 474 | 534269 | 6931 | 100.0 | 94.88 | 27330 | 32.35 | 0.0 |
| `CVX` | 474 | 463974 | 5923 | 100.0 | 88.64 | 52729 | 43.2921 | 0.0 |
| `COP` | 474 | 556256 | 7140 | 100.0 | 92.65 | 40865 | 43.0545 | 0.0 |
| `NEM` | 474 | 464566 | 6471 | 100.0 | 92.46 | 35006 | 41.371 | 0.0 |
| `DIA` | 474 | 776463 | 11794 | 100.0 | 99.83 | 1327 | 12.2094 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
