# Regular Options 13-Symbol Frozen Candidate Generation Engine

This generated artifact materializes the frozen 13-symbol candidate-generation engine diagnostics. It is read-only and fails closed instead of inventing scanner decisions.

## Summary

- Status: `blocked_frozen_13_symbol_candidate_generation_engine`.
- Decision: `blocked_frozen_candidate_generation_entrypoint_incomplete`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily diagnostics rows: `6916`.
- Candidate-generation months covered: `0` / `24`.
- Train months covered: `0`.
- Audit months covered: `0`.
- Latest audit exact trades: `0`.
- Prior source-surface months covered: `0`.
- Prior denominator all rows blocked: `True`.
- Accepted profitability: `False`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `6916` |

## Blockers

- `blocked_daily_candidate_generation_coverage`
- `blocked_latest_audit_rows_below_30`
- `blocked_train_or_audit_month_coverage`
- `candidate_generation_months_0_below_requested_24`
- `missing_historical_entry_underlying_price_surface`
- `missing_historical_option_chain_selection_surface`
- `missing_historical_scanner_point_in_time_inputs`
- `missing_lane_specific_point_in_time_feature_inputs`
- `missing_point_in_time_earnings_calendar_source`
- `missing_point_in_time_market_regime_inputs`
- `underlying_daily_history_source_not_point_in_time`

## Boundary

This artifact does not run historical simulated-forward audit metrics because candidate-generation coverage is not proven. Historical rows remain non-forward proof.

