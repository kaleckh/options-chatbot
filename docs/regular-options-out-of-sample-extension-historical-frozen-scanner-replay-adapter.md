# Regular Options Historical Frozen Scanner Replay Adapter

This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.

## Summary

- Status: `historical_frozen_scanner_replay_adapter_ready`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily rows: `7574`.
- Covered months: `29` / `29`.
- Selected candidates: `3474`.
- Floored exit-value rows: `208`.
- Smallest next blocker: `None`.

## Status Counts

| Status | Count |
|---|---:|
| `explicit_no_pick` | `4100` |
| `selected_candidate` | `3474` |

## Blocker Counts

| Blocker | Count |
|---|---:|

## Boundary

The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.
