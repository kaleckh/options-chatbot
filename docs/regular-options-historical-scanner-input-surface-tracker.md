# Regular Options Historical Scanner Input Surface Tracker

This generated artifact tracks whether the paid/local source surfaces needed for the frozen 13-symbol historical candidate replay are materialized. It is read-only and does not replay candidates.

## Summary

- Status: `blocked_historical_scanner_input_surfaces`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Symbol-dates: `6487`.
- Smallest next blocker: `missing_daily_candidate_generation_diagnostics`.

## Surfaces

| Surface | Available | Coverage |
|---|---:|---:|
| `known_source_gaps` | `false` |  |
| `feature_store_denominator` | `true` |  |
| `market_regime_inputs` | `true` |  |
| `underlying_daily_feature_source_rows` | `false` | `98.998%` |
| `vix_bucket` | `true` |  |
| `entry_underlying_price_surface` | `true` | `100.0%` |
| `option_chain_selection_surface` | `true` | `100.0%` |
| `earnings_calendar` | `true` |  |
| `lane_specific_feature_inputs` | `false` |  |
| `candidate_decision_replay_execution` | `false` |  |

## Blockers

- `missing_daily_candidate_generation_diagnostics`
- `missing_historical_candidate_decision_replay_execution`
- `missing_lane_specific_point_in_time_feature_inputs`
- `missing_point_in_time_underlying_daily_feature_source_rows`

## Boundary

The tracker reads generated source rows and trusted local ThetaData rows. It does not fetch market data, import quotes, mutate evidence stores, call the scanner, append cohorts, enable live validation, enable auto-track, submit broker orders, lower proof bars, consume protected holdout, or promote any lane.
