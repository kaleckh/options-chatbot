# Regular Options 13-Symbol Frozen Candidate Generation Engine

This generated artifact materializes the frozen 13-symbol candidate-generation engine diagnostics. It is read-only and fails closed instead of inventing scanner decisions.

## Summary

- Status: `blocked_frozen_13_symbol_candidate_generation_engine`.
- Decision: `blocked_frozen_candidate_generation_entrypoint_incomplete`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily diagnostics rows: `7574`.
- Candidate-generation months covered: `29` / `29`.
- Train months covered: `20`.
- Audit months covered: `0`.
- Latest audit exact trades: `0`.
- Latest audit exact-trade scope: `strict_calendar_coverage_only`.
- Partial selected-row exact trades: `2048`.
- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.
- Prior source-surface months covered: `29`.
- Prior denominator all rows blocked: `True`.
- Accepted profitability: `False`.

## Status Counts

| Status | Count |
|---|---:|
| `explicit_no_pick` | `4100` |
| `selected_candidate` | `3474` |

## Blockers

- `blocked_train_or_audit_month_coverage`
- `strict_latest_audit_exact_trades_0_below_30`

## Boundary

This artifact does not run historical simulated-forward audit metrics because candidate-generation coverage is not proven. Historical rows remain non-forward proof.
