# Option Executable Coverage Diagnostic

This report is generated from `scripts/diagnose_option_executable_coverage.py`. It is a read-only source-quality diagnostic over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, lower proof bars, synthesize prices, or count historical rows as fresh forward promotion proof.

## Summary

- Status: `coverage_diagnostic_built`.
- Source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Symbols: `["CVX"]`.
- Minimum executable quote floor: `90.0`.
- Candidate report: `C:\Users\kalec\options-chatbot\data\profitability-lab\regular-options-multilane\latest.json`.

| Symbol | Rows | Dates | Exec % | Non-Exec | Zero-Bid Positive-Ask | Zero Share Non-Exec % | Missing | Crossed | Assessment | Selected Trades | Suppressed Duplicates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `CVX` | 495306 | 505 | 88.66 | 56191 | 56191 | 100.0 | 0 | 0 | `zero_bid_tradability_floor_failure` | 3 | 1 |

## CVX Detail

- Recommended action: `treat_as_real_zero_bid_tradability_failure_or_preregister_candidate_scope_exclusion`.
- Underlying-price coverage: `0.0`%.

### Non-Executable Reasons

| Reason | Rows | Share Of Non-Exec % |
|---|---:|---:|
| `zero_bid_positive_ask` | 56191 | 100.0 |

### Option Type

| Type | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `call` | 296868 | 83.89 | 16.11 | 100.0 | 0 | 0 |
| `put` | 198438 | 95.78 | 4.22 | 100.0 | 0 | 0 |

### DTE Bucket

| DTE | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `dte_21_30` | 174414 | 87.77 | 12.23 | 100.0 | 0 | 0 |
| `dte_31_45` | 197370 | 85.83 | 14.17 | 100.0 | 0 | 0 |
| `dte_46_60` | 60123 | 88.55 | 11.45 | 100.0 | 0 | 0 |
| `lt_21` | 63399 | 100.0 | 0.0 | 0.0 | 0 | 0 |

### Abs Moneyness Bucket

| Bucket | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `missing_underlying_price` | 495306 | 88.66 | 11.34 | 100.0 | 0 | 0 |

### Month

| Month | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `2024-05` | 9548 | 85.98 | 14.02 | 100.0 | 0 | 0 |
| `2024-06` | 22932 | 81.22 | 18.78 | 100.0 | 0 | 0 |
| `2024-07` | 24626 | 78.61 | 21.39 | 100.0 | 0 | 0 |
| `2024-08` | 24598 | 87.49 | 12.51 | 100.0 | 0 | 0 |
| `2024-09` | 20972 | 88.88 | 11.12 | 100.0 | 0 | 0 |
| `2024-10` | 39774 | 88.19 | 11.81 | 100.0 | 0 | 0 |
| `2024-11` | 35826 | 81.66 | 18.34 | 100.0 | 0 | 0 |
| `2024-12` | 36302 | 81.17 | 18.83 | 100.0 | 0 | 0 |
| `2025-01` | 37408 | 85.12 | 14.88 | 100.0 | 0 | 0 |
| `2025-02` | 34804 | 82.75 | 17.25 | 100.0 | 0 | 0 |
| `2025-03` | 36862 | 81.74 | 18.26 | 100.0 | 0 | 0 |
| `2025-04` | 22596 | 90.37 | 9.63 | 100.0 | 0 | 0 |
| `2025-05` | 11288 | 88.6 | 11.4 | 100.0 | 0 | 0 |
| `2025-06` | 6970 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-07` | 8612 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-08` | 8238 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-09` | 7342 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-10` | 7604 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-11` | 6292 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2025-12` | 7406 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-01` | 8286 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-02` | 8346 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-03` | 9853 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-04` | 9243 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-05` | 29030 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `2026-06` | 20548 | 100.0 | 0.0 | 0.0 | 0 | 0 |

### Quote Minute

| Minute ET | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `585` | 50712 | 82.69 | 17.31 | 100.0 | 0 | 0 |
| `610` | 51248 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `611` | 2667 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `612` | 2675 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `613` | 2674 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `614` | 2667 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `615` | 2667 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `616` | 2668 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `617` | 2669 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `618` | 2677 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `619` | 2674 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `620` | 2675 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `621` | 2673 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `622` | 2674 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `623` | 2673 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `624` | 2677 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `625` | 2671 | 100.0 | 0.0 | 0.0 | 0 | 0 |
| `645` | 50712 | 84.15 | 15.85 | 100.0 | 0 | 0 |
| `705` | 50712 | 84.29 | 15.71 | 100.0 | 0 | 0 |
| `765` | 50712 | 84.59 | 15.41 | 100.0 | 0 | 0 |
| `825` | 50712 | 84.56 | 15.44 | 100.0 | 0 | 0 |
| `885` | 50712 | 84.49 | 15.51 | 100.0 | 0 | 0 |
| `945` | 50712 | 84.43 | 15.57 | 100.0 | 0 | 0 |
| `955` | 48993 | 100.0 | 0.0 | 0.0 | 0 | 0 |

### Worst Quote Dates

| Date | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |
|---|---:|---:|---:|---:|---:|---:|
| `2024-12-10` | 1512 | 74.14 | 25.86 | 100.0 | 0 | 0 |
| `2024-08-02` | 1330 | 74.29 | 25.71 | 100.0 | 0 | 0 |
| `2024-12-06` | 1932 | 74.95 | 25.05 | 100.0 | 0 | 0 |
| `2024-11-29` | 1890 | 74.97 | 25.03 | 100.0 | 0 | 0 |
| `2024-12-04` | 1484 | 75.13 | 24.87 | 100.0 | 0 | 0 |
| `2024-07-03` | 1302 | 75.27 | 24.73 | 100.0 | 0 | 0 |
| `2024-07-11` | 1274 | 75.75 | 24.25 | 100.0 | 0 | 0 |
| `2024-08-01` | 1344 | 75.82 | 24.18 | 100.0 | 0 | 0 |
| `2024-07-02` | 1064 | 76.13 | 23.87 | 100.0 | 0 | 0 |
| `2024-07-12` | 1316 | 76.14 | 23.86 | 100.0 | 0 | 0 |
| `2024-12-05` | 1848 | 76.24 | 23.76 | 100.0 | 0 | 0 |
| `2024-11-26` | 1498 | 76.5 | 23.5 | 100.0 | 0 | 0 |
| `2024-07-16` | 1050 | 76.86 | 23.14 | 100.0 | 0 | 0 |
| `2024-07-25` | 1330 | 77.07 | 22.93 | 100.0 | 0 | 0 |
| `2025-05-12` | 854 | 77.17 | 22.83 | 100.0 | 0 | 0 |

## Boundary

A zero bid with a positive ask is an observed non-executable quote for proof purposes, not missing data. The allowed responses are source repair for genuinely bad rows, candidate-scope exclusion, or a kill verdict for affected candidates. The diagnostic must not be used to lower quote-quality floors or manufacture historical fills.
