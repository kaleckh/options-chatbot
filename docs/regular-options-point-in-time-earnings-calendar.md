# Regular Options Point-In-Time Earnings Calendar

This generated artifact validates a point-in-time earnings calendar source for the frozen equity symbols. It is read-only and does not use earnings actuals, estimates, surprises, realized moves, or P&L.

## Summary

- Status: `point_in_time_earnings_calendar_ready`.
- Window: `2024-06-01` through `2026-05-31` plus max DTE `45`.
- Accepted events: `74`.
- Covered equity symbols: `9` / `9`.
- Rejected rows: `0`.

## Blockers

- None.

## Symbol Coverage

| Symbol | Events | Coverage Start | Coverage End | Covers Window |
|---|---:|---|---|---:|
| `AAPL` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `COP` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `CVX` | `9` | `2024-06-01` | `2026-07-15` | `true` |
| `GOOGL` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `JNJ` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `LLY` | `9` | `2024-06-01` | `2026-07-15` | `true` |
| `NEM` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `UNH` | `8` | `2024-06-01` | `2026-07-15` | `true` |
| `XOM` | `8` | `2024-06-01` | `2026-07-15` | `true` |

## Boundary

No replay, quote import, evidence mutation, broker action, live validation, auto-track, scanner policy change, proof-bar change, protected-holdout consumption, or promotion is performed.
