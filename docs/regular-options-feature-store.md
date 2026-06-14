# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `9923740`.
- Shared quote dates: `412` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 412 | 1417623 | 36245 | 100.0 | 98.8 | 17013 | 5.7859 | 0.0 |
| `QQQ` | 414 | 1431233 | 36868 | 100.0 | 99.02 | 14021 | 6.04 | 0.0 |
| `IWM` | 412 | 1043357 | 25804 | 100.0 | 99.98 | 168 | 4.6971 | 0.0 |
| `AAPL` | 412 | 487552 | 7813 | 100.0 | 98.38 | 7915 | 19.5681 | 0.0 |
| `GOOGL` | 412 | 548467 | 10172 | 100.0 | 97.19 | 15430 | 23.2763 | 0.0 |
| `UNH` | 412 | 1069334 | 7540 | 100.0 | 99.6 | 4330 | 31.4643 | 0.0 |
| `LLY` | 412 | 464816 | 9437 | 100.0 | 99.98 | 77 | 15.8305 | 0.0 |
| `JNJ` | 412 | 1223618 | 4694 | 100.0 | 96.75 | 39761 | 26.4813 | 0.0 |
| `XOM` | 412 | 422759 | 5859 | 100.0 | 96.12 | 16407 | 31.1211 | 0.0 |
| `CVX` | 412 | 351288 | 4971 | 100.0 | 90.36 | 33864 | 40.9745 | 0.0 |
| `COP` | 412 | 443080 | 6018 | 100.0 | 93.59 | 28399 | 43.2308 | 0.0 |
| `NEM` | 412 | 384416 | 5651 | 100.0 | 94.59 | 20780 | 39.7056 | 0.0 |
| `DIA` | 412 | 636197 | 10264 | 100.0 | 99.85 | 968 | 11.396 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
