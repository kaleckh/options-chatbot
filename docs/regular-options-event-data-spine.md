# Regular Options Event Data Spine

This report is generated from `scripts/build_regular_options_event_data_spine.py`. It inventories regular-options candidate rows for durable event-calendar and post-event volatility-crush replay coverage without creating trades, changing policy, tuning thresholds, mutating rows, or treating research/backfill/midpoint evidence as production proof.

## Summary

- Status: `event_data_spine_built_collecting`.
- Candidate-shown rows: `12`.
- Event-annotated rows: `0`.
- Missing event annotations: `12`.
- Unique tickers: `3`.
- Proof-live exact entry rows: `10`.
- Paper fill recorded rows: `1`.
- True event replay P&L rows: `0`.
- Post-event vol-crush replay P&L rows: `0`.
- Spine rows: `11`.
- Event annotation fields: `{}`.
- Blockers: `["event_calendar_annotations_missing", "post_event_vol_crush_replay_rows_missing", "true_event_executable_pnl_rows_missing"]`.
- Live policy change: `false`.

## Spine Rows

| Ticker | Playbook | Expiry | Candidates | Annotated | Missing Annotations | Exact Entries | Paper Fills | True Event P&L | Post-Event P&L |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `IWM` | `volatility_expansion_observation` | `2026-06-12` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `QQQ` | `bullish_pullback_observation` | `2026-06-18` | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| `QQQ` | `range_breakout_observation` | `2026-06-18` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `QQQ` | `swing` | `2026-06-26` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `QQQ` | `volatility_expansion_observation` | `2026-06-12` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `QQQ` | `volatility_expansion_observation` | `2026-06-18` | 2 | 0 | 2 | 2 | 1 | 0 | 0 |
| `SPY` | `bullish_pullback_observation` | `2026-06-18` | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| `SPY` | `range_breakout_observation` | `2026-06-18` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `SPY` | `swing` | `2026-06-26` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `SPY` | `volatility_expansion_observation` | `2026-06-12` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |
| `SPY` | `volatility_expansion_observation` | `2026-06-18` | 1 | 0 | 1 | 1 | 0 | 0 | 0 |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 7 | `collect_event_calendar_annotations` | 12 | candidate_rows_missing_durable_event_calendar_annotations |
| 8 | `build_post_event_vol_crush_replay_from_annotated_rows` | 0 | no_true_post_event_vol_crush_executable_pnl_rows |
| 8 | `collect_event_exact_entry_exit_pnl` | 12 | no_true_event_executable_entry_exit_pnl_rows |

## Boundary

This spine is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, tune event thresholds, lower exact OPRA/NBBO proof bars, or count daily/EOD, midpoint, stale, last-trade, display marks, migrated paper, or research/backfill rows as production proof.

