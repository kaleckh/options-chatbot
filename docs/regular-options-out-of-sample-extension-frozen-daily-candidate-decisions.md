# Regular Options 13-Symbol Frozen Daily Candidate Decisions

This generated artifact materializes one frozen daily candidate/no-pick/blocker row per market date, lane, and symbol. It is read-only and fails closed when historical scanner replay inputs are unavailable.

## Summary

- Status: `frozen_daily_candidate_decisions_ready`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily rows: `7574`.
- Covered months: `29` / `29`.
- Selected candidates: `3474`.

## Status Counts

| Status | Count |
|---|---:|
| `explicit_no_pick` | `4100` |
| `selected_candidate` | `3474` |

## Boundary

- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

No rows are fabricated, broad-source rows are not post-hoc filtered into proof, and scanner policy is unchanged.
