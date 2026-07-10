# Regular Options Historical Frozen Scanner Replay Adapter

This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.

## Summary

- Status: `blocked_historical_frozen_scanner_replay_adapter`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily rows: `6986`.
- Covered months: `23` / `24`.
- Selected candidates: `2972`.
- Floored exit-value rows: `264`.
- Smallest next blocker: `candidate_generation_months_23_below_requested_24`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `70` |
| `explicit_no_pick` | `3944` |
| `selected_candidate` | `2972` |

## Blocker Counts

| Blocker | Count |
|---|---:|
| `missing_lane_specific_point_in_time_feature_inputs` | `70` |

## Blockers

- `candidate_generation_months_23_below_requested_24`
- `missing_lane_specific_point_in_time_feature_inputs`

## Boundary

The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.

