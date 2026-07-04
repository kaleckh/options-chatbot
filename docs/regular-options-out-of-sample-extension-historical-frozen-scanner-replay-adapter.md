# Regular Options Historical Frozen Scanner Replay Adapter

This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.

## Summary

- Status: `blocked_historical_frozen_scanner_replay_adapter`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily rows: `7574`.
- Covered months: `0` / `29`.
- Selected candidates: `0`.
- Floored exit-value rows: `0`.
- Smallest next blocker: `underlying_daily_history_source_not_point_in_time`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `7574` |

## Blocker Counts

| Blocker | Count |
|---|---:|
| `missing_historical_entry_underlying_price_surface` | `7574` |
| `missing_historical_option_chain_selection_surface` | `7574` |
| `missing_historical_scanner_point_in_time_inputs` | `7574` |
| `missing_lane_specific_point_in_time_feature_inputs` | `7574` |
| `missing_point_in_time_earnings_calendar_source` | `4869` |
| `missing_point_in_time_market_regime_inputs` | `7574` |
| `missing_point_in_time_vix_source` | `7574` |
| `underlying_daily_history_source_not_point_in_time` | `7574` |

## Blockers

- `candidate_generation_months_0_below_requested_29`
- `missing_historical_entry_underlying_price_surface`
- `missing_historical_option_chain_selection_surface`
- `missing_historical_scanner_point_in_time_inputs`
- `missing_lane_specific_point_in_time_feature_inputs`
- `missing_point_in_time_earnings_calendar_source`
- `missing_point_in_time_market_regime_inputs`
- `missing_point_in_time_vix_source`
- `underlying_daily_history_source_not_point_in_time`

## Boundary

The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.
