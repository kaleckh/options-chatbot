# Regular Options Point-In-Time Earnings Calendar

This generated artifact validates a point-in-time earnings calendar source for the frozen equity symbols. It is read-only and does not use earnings actuals, estimates, surprises, realized moves, or P&L.

## Summary

- Status: `point_in_time_earnings_calendar_ready`.
- Window: `2022-01-01` through `2024-05-31` plus max DTE `45`.
- Accepted events: `103`.
- Covered equity symbols: `9` / `9`.
- Rejected rows: `0`.

## Blockers

- None.

## Symbol Coverage

| Symbol | Events | Coverage Start | Coverage End | Covers Window |
|---|---:|---|---|---:|
| `AAPL` | `11` | `2021-10-01` | `2024-07-31` | `true` |
| `COP` | `11` | `2021-10-01` | `2024-07-31` | `true` |
| `CVX` | `13` | `2021-10-01` | `2024-07-31` | `true` |
| `GOOGL` | `5` | `2021-10-01` | `2024-07-31` | `true` |
| `JNJ` | `14` | `2021-10-01` | `2024-07-31` | `true` |
| `LLY` | `14` | `2021-10-01` | `2024-07-31` | `true` |
| `NEM` | `12` | `2021-10-01` | `2024-07-31` | `true` |
| `UNH` | `12` | `2021-10-01` | `2024-07-31` | `true` |
| `XOM` | `11` | `2021-10-01` | `2024-07-31` | `true` |

## Boundary

No replay, quote import, evidence mutation, broker action, live validation, auto-track, scanner policy change, proof-bar change, protected-holdout consumption, or promotion is performed.
