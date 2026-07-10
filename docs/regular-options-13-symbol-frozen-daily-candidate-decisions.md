# Regular Options 13-Symbol Frozen Daily Candidate Decisions

This generated artifact materializes one frozen daily candidate/no-pick/blocker row per market date, lane, and symbol. It is read-only and fails closed when historical scanner replay inputs are unavailable.

## Summary

- Status: `blocked_frozen_daily_candidate_decisions`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily rows: `6986`.
- Covered months: `23` / `24`.
- Selected candidates: `2972`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `70` |
| `explicit_no_pick` | `3944` |
| `selected_candidate` | `2972` |

## Blockers

- `candidate_generation_months_23_below_requested_24`
- `missing_lane_specific_point_in_time_feature_inputs`

## Boundary

- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

No rows are fabricated, broad-source rows are not post-hoc filtered into proof, and scanner policy is unchanged.

