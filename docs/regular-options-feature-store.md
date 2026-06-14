# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `9001574`.
- Shared quote dates: `374` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 374 | 1311223 | 35141 | 100.0 | 98.7 | 17013 | 6.0733 | 0.0 |
| `QQQ` | 376 | 1344769 | 35770 | 100.0 | 98.96 | 14021 | 6.3461 | 0.0 |
| `IWM` | 374 | 943131 | 24734 | 100.0 | 99.98 | 168 | 5.0166 | 0.0 |
| `AAPL` | 374 | 430250 | 7305 | 100.0 | 98.57 | 6157 | 19.9908 | 0.0 |
| `GOOGL` | 374 | 486139 | 9594 | 100.0 | 97.82 | 10583 | 22.5893 | 0.0 |
| `UNH` | 374 | 1005410 | 6780 | 100.0 | 99.85 | 1481 | 31.4863 | 0.0 |
| `LLY` | 374 | 402404 | 8619 | 100.0 | 99.99 | 29 | 16.4029 | 0.0 |
| `JNJ` | 374 | 1177096 | 4288 | 100.0 | 97.69 | 27154 | 24.8285 | 0.0 |
| `XOM` | 374 | 354943 | 5197 | 100.0 | 97.4 | 9246 | 29.5759 | 0.0 |
| `CVX` | 374 | 285040 | 4337 | 100.0 | 92.5 | 21377 | 37.7145 | 0.0 |
| `COP` | 374 | 374774 | 5304 | 100.0 | 94.8 | 19489 | 42.0436 | 0.0 |
| `NEM` | 374 | 333344 | 5129 | 100.0 | 96.75 | 10833 | 37.283 | 0.0 |
| `DIA` | 374 | 553051 | 9284 | 100.0 | 99.89 | 594 | 10.0259 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
