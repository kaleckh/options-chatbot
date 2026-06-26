# Regular Options 13-Symbol Frozen Daily Candidate Decisions

This generated artifact materializes one frozen daily candidate/no-pick/blocker row per market date, lane, and symbol. It is read-only and fails closed when historical scanner replay inputs are unavailable.

## Summary

- Status: `blocked_frozen_daily_candidate_decisions`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Daily rows: `6916`.
- Covered months: `0` / `24`.
- Selected candidates: `0`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `6916` |

## Blockers

- `candidate_generation_months_0_below_requested_24`
- `missing_historical_entry_underlying_price_surface`
- `missing_historical_option_chain_selection_surface`
- `missing_historical_scanner_point_in_time_inputs`
- `missing_lane_specific_point_in_time_feature_inputs`
- `missing_point_in_time_earnings_calendar_source`
- `missing_point_in_time_market_regime_inputs`
- `underlying_daily_history_source_not_point_in_time`

## Boundary

No rows are fabricated, broad-source rows are not post-hoc filtered into proof, and scanner policy is unchanged.

