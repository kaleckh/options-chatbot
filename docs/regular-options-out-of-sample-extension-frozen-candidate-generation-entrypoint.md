# Regular Options 13-Symbol Frozen Candidate Generation Entrypoint

This generated artifact exposes a reusable read-only daily candidate/no-pick entrypoint for the frozen 13-symbol regular-options universe. It fails closed if the source is broad, missing daily diagnostics, or otherwise not exact.

## Summary

- Status: `frozen_13_symbol_candidate_generation_entrypoint_ready`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily rows: `7574`.
- Covered months: `29` / `29`.
- Selected candidates: `3474`.
- Outside-universe rows: `0`.

## Status Counts

| Status | Count |
|---|---:|
| `explicit_no_pick` | `4100` |
| `selected_candidate` | `3474` |

## Boundary

- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

Historical rows and broad-source rows are not forward proof and are not converted into picks here.
