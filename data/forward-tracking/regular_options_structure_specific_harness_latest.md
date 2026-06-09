# Regular Options Structure-Specific Harness

This report is generated from `scripts/build_regular_options_structure_specific_harness.py`. It separates regular-options fill-attempt evidence by option structure without creating trades, changing policy, mutating rows, or treating research/backfill/midpoint evidence as production proof.

## Summary

- Status: `structure_specific_harness_built_collecting`.
- Candidate-shown rows: `12`.
- Structure buckets: `{"multi_leg_other": 0, "single_leg": 0, "unknown": 0, "vertical_spread": 12}`.
- Strategy types: `{"vertical_spread": 12}`.
- Proof-live exact entry rows: `10`.
- Paper fill recorded rows: `1`.
- True structure-specific P&L rows: `12`.
- Structure P&L decisions: `{"hold_for_current_open_risk_review": 1, "reject_production_use_without_fill_or_position_link": 11}`.
- Harness rows: `1`.
- Blockers: `["single_leg_or_other_multileg_samples_missing"]`.
- Live policy change: `false`.

## Harness Rows

| Bucket | Strategy | Candidates | Selected | Top Alts | Exact Entries | Paper Fills | True P&L | Fill Statuses |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `vertical_spread` | `vertical_spread` | 12 | 12 | 12 | 10 | 1 | 12 | {"auto_tracked": 1, "not_filled_auto_track_skipped": 6, "not_submitted_auto_track_disabled": 3, "skipped_observation_only": 2} |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 8 | `collect_single_leg_or_other_multileg_structure_samples` | 1 | current_harness_only_has_vertical_spread_candidate_rows |

## Structure P&L Rows

| Ticker | Lane | Long | Short | Entry UTC | Entry Bid/Ask | Exit UTC | Exit Bid/Ask | P&L/Spread | Decision |
|---|---|---|---|---|---|---|---|---:|---|
| `QQQ` | `bullish_pullback_observation` | `QQQ260618C00710000` | `QQQ260618C00745000` | 2026-05-21T14:27:00Z | 16.58/16.63 ; 3.85/3.89 | 2026-05-21T19:55:00Z | 19.72/19.88 ; 4.9/4.98 | 1.96 | `reject_production_use_without_fill_or_position_link` |
| `SPY` | `bullish_pullback_observation` | `SPY260618C00740000` | `SPY260618C00760000` | 2026-05-21T14:27:00Z | 11.98/12.03 ; 3.55/3.58 | 2026-05-21T19:55:00Z | 13.9/14.11 ; 4.38/4.51 | 0.91 | `reject_production_use_without_fill_or_position_link` |
| `IWM` | `volatility_expansion_observation` | `IWM260612C00290000` | `IWM260612C00296000` | 2026-05-29T17:45:00Z | 4.88/4.94 ; 2.31/2.35 | 2026-05-29T19:55:00Z | 4.58/4.66 ; 2.04/2.1 | -0.15 | `reject_production_use_without_fill_or_position_link` |
| `QQQ` | `volatility_expansion_observation` | `QQQ260612C00738000` | `QQQ260612C00760000` | 2026-05-29T17:45:00Z | 11.1/11.15 ; 2.94/2.97 | 2026-05-29T19:55:00Z | 11.78/11.99 ; 3.11/3.18 | 0.39 | `reject_production_use_without_fill_or_position_link` |
| `SPY` | `volatility_expansion_observation` | `SPY260612C00757000` | `SPY260612C00770000` | 2026-05-29T17:45:00Z | 7.0/7.02 ; 1.77/1.78 | 2026-05-29T19:55:00Z | 7.15/7.29 ; 1.78/1.82 | 0.08 | `reject_production_use_without_fill_or_position_link` |
| `QQQ` | `range_breakout_observation` | `QQQ260618C00743000` | `QQQ260618C00765000` | 2026-06-04T17:03:00Z | 11.27/11.3 ; 3.01/3.04 | 2026-06-04T19:55:00Z | 11.44/11.64 ; 3.04/3.09 | 0.06 | `reject_production_use_without_fill_or_position_link` |
| `SPY` | `range_breakout_observation` | `SPY260618C00758000` | `SPY260618C00771000` | 2026-06-04T17:07:00Z | 6.9/6.93 ; 1.72/1.73 | 2026-06-04T19:55:00Z | 7.11/7.32 ; 1.77/1.84 | 0.06 | `reject_production_use_without_fill_or_position_link` |
| `QQQ` | `swing` | `QQQ260626C00745000` | `QQQ260626C00770000` | 2026-06-04T17:07:00Z | 13.08/13.13 ; 3.99/4.03 | 2026-06-04T19:55:00Z | 13.53/13.73 ; 4.19/4.25 | 0.14 | `reject_production_use_without_fill_or_position_link` |
| `SPY` | `swing` | `SPY260626C00760000` | `SPY260626C00775000` | 2026-06-04T17:07:00Z | 7.64/7.67 ; 2.08/2.1 | 2026-06-04T19:55:00Z | 7.87/8.01 ; 2.14/2.19 | 0.09 | `reject_production_use_without_fill_or_position_link` |
| `QQQ` | `volatility_expansion_observation` | `QQQ260618C00743000` | `QQQ260618C00765000` | 2026-06-04T17:09:00Z | 11.27/11.29 ; 3.0/3.02 | 2026-06-04T19:55:00Z | 11.44/11.64 ; 3.04/3.09 | 0.06 | `reject_production_use_without_fill_or_position_link` |
| `SPY` | `volatility_expansion_observation` | `SPY260618C00758000` | `SPY260618C00771000` | 2026-06-04T17:07:00Z | 6.9/6.93 ; 1.72/1.73 | 2026-06-04T19:55:00Z | 7.11/7.32 ; 1.77/1.84 | 0.06 | `reject_production_use_without_fill_or_position_link` |
| `QQQ` | `volatility_expansion_observation` | `QQQ260618C00728000` | `QQQ260618C00750000` | 2026-06-05T14:39:00Z | 11.77/11.85 ; 3.17/3.22 | 2026-06-05T19:55:00Z | 6.13/6.5 ; 1.41/1.47 | -4.02 | `hold_for_current_open_risk_review` |

## Boundary

This harness is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or count daily/EOD, midpoint, stale, last-trade, display marks, migrated paper, or research/backfill rows as production proof.

