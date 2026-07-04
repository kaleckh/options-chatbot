# Regular Options Historical Scanner Input Surface Tracker

This generated artifact tracks whether the paid/local source surfaces needed for the frozen 13-symbol historical candidate replay are materialized. It is read-only and does not replay candidates.

## Summary

- Status: `blocked_historical_scanner_input_surfaces`.
- Window: `2024-06-01` through `2026-07-02` as of `2026-07-02`.
- Symbol-dates: `6760`.
- Smallest next blocker: `missing_historical_entry_underlying_price_surface`.

## Surfaces

| Surface | Available | Coverage |
|---|---:|---:|
| `feature_store_denominator` | `true` |  |
| `market_regime_inputs` | `true` |  |
| `underlying_daily_feature_source_rows` | `false` | `95.0%` |
| `vix_bucket` | `true` |  |
| `entry_underlying_price_surface` | `false` | `95.9615%` |
| `option_chain_selection_surface` | `false` | `96.7308%` |
| `earnings_calendar` | `false` |  |
| `lane_specific_feature_inputs` | `true` |  |
| `candidate_decision_replay_execution` | `true` |  |

## Blockers

- `missing_historical_entry_underlying_price_surface`
- `missing_historical_option_chain_selection_surface`
- `missing_point_in_time_earnings_calendar_source`
- `missing_point_in_time_underlying_daily_feature_source_rows`

## Boundary

The tracker reads generated source rows and trusted local ThetaData rows. It does not fetch market data, import quotes, mutate evidence stores, call the scanner, append cohorts, enable live validation, enable auto-track, submit broker orders, lower proof bars, consume protected holdout, or promote any lane.
