# Regular Options Materializer Match-Rate Stationarity

- Status: `post_freeze_zero_within_historical_variation`.
- Blockers: `[]`.
- Historical frozen-filter matches: `306` / disclosed `306`.
- Post-freeze materializer rows: `182`.
- Post-freeze filter-matched rows: `0`.
- Zero-run windows: `52` / `482`; fraction `0.107884`.
- Zero-run trigger schedule: `ready`; monotonicity `passed`.
- First <=0.05 trigger if zero-run continues: `2026-07-22` at `24` market days; fraction `0.048832`.
- First <=0.01 confirmation if zero-run continues: `2026-08-14` at `41` market days; fraction `0.008811`.
- Row-conditioned zero-window statistic: `historical_row_rich_zero_windows_exist`; descriptive only `True`.
- Minimum historical distance below frozen threshold: `0.023566`.
- Session-time overlap with materializer entry window: `14` / `341` distinct times.

## Zero-Run Trigger Schedule

| Threshold | Window Market Days | Projected Date If Zero Continues | Historical Zero Fraction |
|---|---:|---|---:|
| `<=0.05` | 24 | `2026-07-22` | 0.048832 |
| `<=0.01` | 41 | `2026-08-14` | 0.008811 |

These are descriptive overlapping-window fractions, not p-values or independent significance tests.

A single post-freeze parity materializer filter match voids this zero-run schedule and requires a fresh stationarity run.

Daily ops refreshes this report before the weekday fresh-window import, so trigger/void recognition can lag newly imported parity by one market day.

## Row-Conditioned Zero Windows

| Window Market Days | Zero Windows | Row-Conditioned Zero Windows | Fraction | Max Zero-Window Rows |
|---:|---:|---:|---:|---:|
| 13 | 52 | 0 | 0.0 | 130 |
| 24 | 23 | 13 | 0.565217 | 194 |
| 41 | 4 | 4 | 1.0 | 268 |

This statistic is descriptive only and does not change status, trigger dates, thresholds, scanner policy, filters, proof bars, or evidence-bar behavior.

## Monthly Zero Precedents

| Month | Accepted Rows | Frozen-Filter Matches | Match Rate |
|---|---:|---:|---:|
| `2024-10` | 187 | 0 | 0.0 |

## Monthly Match Counts

| Month | Accepted Rows | Frozen-Filter Matches | Match Rate |
|---|---:|---:|---:|
| `2024-06` | 98 | 10 | 0.102041 |
| `2024-07` | 163 | 13 | 0.079755 |
| `2024-08` | 107 | 5 | 0.046729 |
| `2024-09` | 97 | 2 | 0.020619 |
| `2024-10` | 187 | 0 | 0.0 |
| `2024-11` | 123 | 1 | 0.00813 |
| `2024-12` | 84 | 14 | 0.166667 |
| `2025-01` | 67 | 5 | 0.074627 |
| `2025-02` | 94 | 9 | 0.095745 |
| `2025-03` | 66 | 1 | 0.015152 |
| `2025-04` | 32 | 12 | 0.375 |
| `2025-05` | 71 | 14 | 0.197183 |
| `2025-06` | 148 | 12 | 0.081081 |
| `2025-07` | 238 | 12 | 0.05042 |
| `2025-08` | 158 | 23 | 0.14557 |
| `2025-09` | 211 | 40 | 0.189573 |
| `2025-10` | 186 | 14 | 0.075269 |
| `2025-11` | 100 | 19 | 0.19 |
| `2025-12` | 144 | 12 | 0.083333 |
| `2026-01` | 132 | 23 | 0.174242 |
| `2026-02` | 105 | 11 | 0.104762 |
| `2026-03` | 69 | 6 | 0.086957 |
| `2026-04` | 127 | 30 | 0.23622 |
| `2026-05` | 44 | 18 | 0.409091 |

## Boundary

This report emits descriptive stationarity and distance statistics only. It is not profitability evidence, does not evaluate alternative thresholds, and does not authorize scanner policy, filter, proof-bar, live, auto-track, broker, quote-import, cohort-append, holdout, or promotion actions.
