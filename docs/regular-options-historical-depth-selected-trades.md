# Regular Options Historical Depth Selected Trades

This report is generated from `scripts/build_regular_options_historical_depth_selected_trades.py`. It checks whether the current selected-trade source proves enough calendar-month coverage to support a 20-month train plus latest-4-month historical simulated-forward audit. It is read-only and does not import quotes, mutate evidence stores, consume protected holdout, create trades, or change policy.

## Summary

- Status: `blocked_historical_depth_selected_trades`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Requested months: `24`.
- Proven covered months: `8`.
- Selected months with rows: `8`.
- Selected rows in window: `231`.
- Zero-selection months explicit: `False`.
- Protected holdout starts: `2026-06-05`; overlap `False`.
- Quote-history shared dates: `505` through `2026-06-04`.

## Coverage

- Coverage basis: `row_months_only_calendar_coverage_not_proven`.
- Covered months: `2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03`.
- Selected row months: `2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03`.
- Unproven requested months: `2024-06, 2024-07, 2024-08, 2024-09, 2024-10, 2024-11, 2024-12, 2025-01, 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2026-04, 2026-05`.

## Selected Rows By Month

| Month | Rows |
|---|---:|
| `2025-08` | 23 |
| `2025-09` | 43 |
| `2025-10` | 41 |
| `2025-11` | 11 |
| `2025-12` | 48 |
| `2026-01` | 29 |
| `2026-02` | 24 |
| `2026-03` | 12 |

## Blockers

- `selected_trade_calendar_coverage_not_proven`
- `calendar_months_covered_8_below_requested_24`

## Boundary

This is a selected-trade calendar-depth readback. It does not regenerate older candidates by itself. If calendar coverage is not proven, the next valid step is a bounded point-in-time selected-trade generator over the older trusted quote-history window.

