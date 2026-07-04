# Regular Options Point-In-Time Earnings Calendar

This generated artifact validates a point-in-time earnings calendar source for the frozen equity symbols. It is read-only and does not use earnings actuals, estimates, surprises, realized moves, or P&L.

## Summary

- Status: `blocked_point_in_time_earnings_calendar`.
- Window: `2022-01-01` through `2024-05-31` plus max DTE `45`.
- Accepted events: `74`.
- Covered equity symbols: `0` / `9`.
- Rejected rows: `0`.

## Blockers

- `point_in_time_earnings_calendar_symbol_coverage_incomplete`

## Symbol Coverage

| Symbol | Events | Coverage Start | Coverage End | Covers Window |
|---|---:|---|---|---:|
| `AAPL` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `COP` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `CVX` | `9` | `2024-06-01` | `2026-07-15` | `false` |
| `GOOGL` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `JNJ` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `LLY` | `9` | `2024-06-01` | `2026-07-15` | `false` |
| `NEM` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `UNH` | `8` | `2024-06-01` | `2026-07-15` | `false` |
| `XOM` | `8` | `2024-06-01` | `2026-07-15` | `false` |

## Boundary

No replay, quote import, evidence mutation, broker action, live validation, auto-track, scanner policy change, proof-bar change, protected-holdout consumption, or promotion is performed.
