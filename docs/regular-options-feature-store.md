# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `10438296`.
- Shared quote dates: `434` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 434 | 1473875 | 37005 | 100.0 | 98.85 | 17013 | 5.6351 | 0.0 |
| `QQQ` | 436 | 1472309 | 37486 | 100.0 | 99.05 | 14021 | 5.9058 | 0.0 |
| `IWM` | 434 | 1096025 | 26364 | 100.0 | 99.98 | 171 | 4.555 | 0.0 |
| `AAPL` | 434 | 521236 | 8199 | 100.0 | 98.37 | 8475 | 18.971 | 0.0 |
| `GOOGL` | 434 | 583635 | 10474 | 100.0 | 97.13 | 16753 | 22.9225 | 0.0 |
| `UNH` | 434 | 1095556 | 7868 | 100.0 | 99.57 | 4740 | 31.1006 | 0.0 |
| `LLY` | 434 | 499900 | 9893 | 100.0 | 99.98 | 79 | 15.316 | 0.0 |
| `JNJ` | 434 | 1261222 | 5230 | 100.0 | 96.19 | 48018 | 27.4109 | 0.0 |
| `XOM` | 434 | 463387 | 6275 | 100.0 | 95.65 | 20152 | 31.6256 | 0.0 |
| `CVX` | 434 | 392308 | 5371 | 100.0 | 89.81 | 39994 | 41.8308 | 0.0 |
| `COP` | 434 | 484492 | 6454 | 100.0 | 93.14 | 33239 | 43.4017 | 0.0 |
| `NEM` | 434 | 412262 | 5947 | 100.0 | 93.77 | 25692 | 40.2916 | 0.0 |
| `DIA` | 434 | 682089 | 10824 | 100.0 | 99.83 | 1167 | 11.7679 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
