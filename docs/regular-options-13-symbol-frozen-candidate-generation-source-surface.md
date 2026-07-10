# Regular Options 13-Symbol Frozen Candidate Generation Source Surface

This generated artifact attempts to materialize a frozen 13-symbol candidate-generation source surface from trusted local artifacts. It fails closed rather than treating broad-source or quote-history-only data as proof.

## Summary

- Status: `blocked_13_symbol_frozen_candidate_generation_source_surface`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Source exact 13-symbol: `True`.
- Covered months: `23` / `24`.
- Selected rows: `2972`.

## Month Diagnostics

| Month | Attempted | Proven | Explicit No-Pick | Selected | Outside Universe | Coverable | Blockers |
|---|---:|---:|---:|---:|---:|---:|---|
| `2024-06` | True | True | False | 98 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-07` | True | True | False | 163 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-08` | True | True | False | 107 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-09` | True | True | False | 97 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-10` | True | True | False | 187 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-11` | True | True | False | 123 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2024-12` | True | True | False | 84 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-01` | True | True | False | 67 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-02` | True | True | False | 94 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-03` | True | True | False | 66 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-04` | True | True | False | 32 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-05` | False | False | False | 78 | 0 | False | candidate_generation_months_23_below_requested_24, missing_daily_candidate_generation_diagnostics, missing_lane_specific_point_in_time_feature_inputs |
| `2025-06` | True | True | False | 148 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-07` | True | True | False | 238 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-08` | True | True | False | 158 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-09` | True | True | False | 211 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-10` | True | True | False | 186 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-11` | True | True | False | 100 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2025-12` | True | True | False | 144 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2026-01` | True | True | False | 132 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2026-02` | True | True | False | 105 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2026-03` | True | True | False | 69 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2026-04` | True | True | False | 127 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |
| `2026-05` | True | True | False | 158 | 0 | True | candidate_generation_months_23_below_requested_24, missing_lane_specific_point_in_time_feature_inputs |

## Blockers

- `candidate_generation_months_23_below_requested_24`
- `missing_daily_candidate_generation_diagnostics`
- `missing_lane_specific_point_in_time_feature_inputs`

## Boundary

- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

