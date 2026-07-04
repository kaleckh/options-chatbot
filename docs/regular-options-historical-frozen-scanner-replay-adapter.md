# Regular Options Historical Frozen Scanner Replay Adapter

This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.

## Summary

- Status: `blocked_historical_frozen_scanner_replay_adapter`.
- Window: `2024-06-01` through `2026-07-02` as of `2026-07-02`.
- Daily rows: `7280`.
- Covered months: `0` / `26`.
- Selected candidates: `0`.
- Floored exit-value rows: `0`.
- Smallest next blocker: `candidate_generation_months_0_below_requested_26`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `7280` |

## Blocker Counts

| Blocker | Count |
|---|---:|
| `missing_historical_entry_underlying_price_surface` | `7280` |
| `missing_historical_option_chain_selection_surface` | `7280` |
| `missing_historical_scanner_point_in_time_inputs` | `7280` |
| `missing_lane_specific_point_in_time_feature_inputs` | `364` |
| `missing_point_in_time_earnings_calendar_source` | `4680` |

## Blockers

- `candidate_generation_months_0_below_requested_26`
- `missing_historical_entry_underlying_price_surface`
- `missing_historical_option_chain_selection_surface`
- `missing_historical_scanner_point_in_time_inputs`
- `missing_lane_specific_point_in_time_feature_inputs`
- `missing_point_in_time_earnings_calendar_source`

## Boundary

The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.

