# Regular Options 13-Symbol Frozen Candidate Generation Entrypoint

This generated artifact exposes a reusable read-only daily candidate/no-pick entrypoint for the frozen 13-symbol regular-options universe. It fails closed if the source is broad, missing daily diagnostics, or otherwise not exact.

## Summary

- Status: `blocked_frozen_13_symbol_candidate_generation_entrypoint`.
- Window: `2022-01-01` through `2024-05-31` as of `2024-05-31`.
- Daily rows: `7574`.
- Covered months: `0` / `29`.
- Selected candidates: `0`.
- Outside-universe rows: `0`.

## Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_historical_scanner_point_in_time_inputs` | `7574` |

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

- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

Historical rows and broad-source rows are not forward proof and are not converted into picks here.
