# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `10926420`.
- Shared quote dates: `453` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 453 | 1531373 | 37579 | 100.0 | 98.89 | 17013 | 5.4941 | 0.0 |
| `QQQ` | 455 | 1517039 | 38188 | 100.0 | 99.07 | 14037 | 5.7976 | 0.0 |
| `IWM` | 453 | 1153747 | 26898 | 100.0 | 99.99 | 171 | 4.4187 | 0.0 |
| `AAPL` | 453 | 551924 | 8463 | 100.0 | 98.35 | 9081 | 18.5515 | 0.0 |
| `GOOGL` | 453 | 613651 | 10722 | 100.0 | 97.13 | 17600 | 22.5843 | 0.0 |
| `UNH` | 453 | 1119090 | 8232 | 100.0 | 99.53 | 5244 | 30.8998 | 0.0 |
| `LLY` | 453 | 532380 | 10341 | 100.0 | 99.98 | 113 | 15.0233 | 0.0 |
| `JNJ` | 453 | 1298462 | 5518 | 100.0 | 95.56 | 57702 | 28.5407 | 0.0 |
| `XOM` | 453 | 497155 | 6553 | 100.0 | 95.31 | 23309 | 31.8791 | 0.0 |
| `CVX` | 453 | 427112 | 5645 | 100.0 | 89.23 | 45999 | 42.4664 | 0.0 |
| `COP` | 453 | 518722 | 6752 | 100.0 | 92.97 | 36444 | 43.0044 | 0.0 |
| `NEM` | 453 | 436986 | 6213 | 100.0 | 93.25 | 29492 | 40.4446 | 0.0 |
| `DIA` | 453 | 728779 | 11286 | 100.0 | 99.82 | 1278 | 12.0324 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
