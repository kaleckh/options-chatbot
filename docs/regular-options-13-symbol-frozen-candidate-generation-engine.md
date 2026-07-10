# Regular Options 13-Symbol Frozen Candidate Generation Engine

This generated artifact materializes the frozen 13-symbol candidate-generation engine diagnostics. It is read-only and fails closed instead of inventing scanner decisions.

## Summary

- Status: `blocked_frozen_13_symbol_candidate_generation_engine`.
- Decision: `blocked_frozen_candidate_generation_entrypoint_incomplete`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily diagnostics rows: `6986`.
- Candidate-generation months covered: `23` / `24`.
- Train months covered: `19`.
- Audit months covered: `4`.
- Latest audit exact trades: `0`.
- Latest audit exact-trade scope: `strict_calendar_coverage_only`.
- Partial selected-row exact trades: `2840`.
- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.
- Prior source-surface months covered: `23`.
- Prior denominator all rows blocked: `True`.
- Accepted profitability: `False`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `70` |
| `explicit_no_pick` | `3944` |
| `selected_candidate` | `2972` |

## Blockers

- `blocked_daily_candidate_generation_coverage`
- `blocked_train_or_audit_month_coverage`
- `candidate_generation_months_23_below_requested_24`
- `missing_lane_specific_point_in_time_feature_inputs`
- `strict_latest_audit_exact_trades_0_below_30`

## Boundary

This artifact does not run historical simulated-forward audit metrics because candidate-generation coverage is not proven. Historical rows remain non-forward proof.

