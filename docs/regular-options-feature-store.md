# Regular Options Feature Store

This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.

## Summary

- Status: `feature_store_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols available: `13` / `13`.
- Quote rows: `12149428`.
- Shared quote dates: `505` from `2024-05-22` to `2026-06-04`.
- Missing required inputs: `[]`.

## Point-In-Time Contract

- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.
- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.
- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.

## Symbol Surface Rows

| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SPY` | 505 | 1672556 | 39573 | 100.0 | 98.98 | 17013 | 5.1562 | 0.0 |
| `QQQ` | 507 | 1625272 | 40118 | 100.0 | 99.14 | 14037 | 5.5378 | 0.0 |
| `IWM` | 505 | 1285052 | 28020 | 100.0 | 99.99 | 188 | 4.1604 | 0.0 |
| `AAPL` | 505 | 634958 | 9078 | 100.0 | 98.35 | 10470 | 17.5224 | 0.0 |
| `GOOGL` | 505 | 685793 | 11220 | 100.0 | 97.04 | 20320 | 22.166 | 0.0 |
| `UNH` | 505 | 1201956 | 9219 | 100.0 | 99.45 | 6658 | 30.1624 | 0.0 |
| `LLY` | 505 | 614112 | 11392 | 100.0 | 99.98 | 124 | 14.3524 | 0.0 |
| `JNJ` | 505 | 1371794 | 6053 | 100.0 | 94.48 | 75761 | 30.4448 | 0.0 |
| `XOM` | 505 | 593069 | 7326 | 100.0 | 94.34 | 33562 | 32.9163 | 0.0 |
| `CVX` | 505 | 495306 | 6198 | 100.0 | 88.66 | 56191 | 43.0953 | 0.0 |
| `COP` | 505 | 614006 | 7565 | 100.0 | 92.11 | 48452 | 43.4652 | 0.0 |
| `NEM` | 505 | 512059 | 6788 | 100.0 | 91.27 | 44683 | 42.6129 | 0.0 |
| `DIA` | 505 | 843495 | 12552 | 100.0 | 99.84 | 1330 | 11.9873 | 0.0 |

## Boundary

This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.
