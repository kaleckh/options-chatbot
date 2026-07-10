# Regular Options 13-Symbol Frozen Candidate Generation Entrypoint

This generated artifact exposes a reusable read-only daily candidate/no-pick entrypoint for the frozen 13-symbol regular-options universe. It fails closed if the source is broad, missing daily diagnostics, or otherwise not exact.

## Summary

- Status: `blocked_frozen_13_symbol_candidate_generation_entrypoint`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily rows: `6986`.
- Covered months: `23` / `24`.
- Selected candidates: `2972`.
- Outside-universe rows: `0`.

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

Historical rows and broad-source rows are not forward proof and are not converted into picks here.

