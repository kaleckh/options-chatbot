# Regular Options Minute Exit Replay Readiness

This report is generated from `scripts/build_regular_options_minute_exit_replay_readiness.py`. It is a read-only readiness and side-aware fixed-minute exit replay for exact OPRA/NBBO rows; it does not change stops, submit orders, or mutate trading rows.

## Summary

- Status: `minute_exit_replay_readiness_readback`.
- Overall status: `minute_exit_replay_coverage_ready`.
- Candidate-shown rows: `12`.
- Entry seed ready / position seed ready: `12` / `1`.
- True minute exit P&L rows: `12`.
- Position-linked true minute exit P&L rows: `1`.
- Minute quote coverage / engine: `full` / `read_only_side_aware_engine_partial`.
- Minute decisions: `{"hold_for_current_open_risk_review": 1, "reject_production_use_without_fill_or_position_link": 11}`.
- Daily stop-grid replayed rows: `112`.
- Blockers: `[]`.
- Live policy change: `false`.

## Candidate Queue

| Status | Ticker | Lane | Entry Time | Long | Short | Position | Blockers |
|---|---|---|---|---|---|---:|---|
| `position_seed_ready_engine_missing` | QQQ | volatility_expansion_observation | 2026-06-05T14:39:44.945897Z | QQQ260618C00728000 | QQQ260618C00750000 | 537 | minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | SPY | bullish_pullback_observation | 2026-05-21T14:27:47.890289+00:00 | SPY260618C00740000 | SPY260618C00760000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | QQQ | bullish_pullback_observation | 2026-05-21T14:27:49.005738+00:00 | QQQ260618C00710000 | QQQ260618C00745000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | SPY | volatility_expansion_observation | 2026-05-29T17:45:16.006159Z | SPY260612C00757000 | SPY260612C00770000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | QQQ | volatility_expansion_observation | 2026-05-29T17:45:20.554574Z | QQQ260612C00738000 | QQQ260612C00760000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | IWM | volatility_expansion_observation | 2026-05-29T17:45:24.054950Z | IWM260612C00290000 | IWM260612C00296000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | QQQ | range_breakout_observation | 2026-06-04T17:03:11.116739Z | QQQ260618C00743000 | QQQ260618C00765000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | SPY | swing | 2026-06-04T17:07:12.311709Z | SPY260626C00760000 | SPY260626C00775000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | QQQ | swing | 2026-06-04T17:07:16.606684Z | QQQ260626C00745000 | QQQ260626C00770000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | SPY | range_breakout_observation | 2026-06-04T17:07:18.297519Z | SPY260618C00758000 | SPY260618C00771000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | SPY | volatility_expansion_observation | 2026-06-04T17:07:18.297519Z | SPY260618C00758000 | SPY260618C00771000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |
| `entry_seed_only_fill_not_recorded` | QQQ | volatility_expansion_observation | 2026-06-04T17:09:06.793391Z | QQQ260618C00743000 | QQQ260618C00765000 |  | paper_fill_or_position_link_missing, minute_level_exit_replay_engine_missing, minute_opra_nbbo_quote_coverage_missing |

## True Minute Exit Replay Rows

| Ticker | Lane | Position | Long Quote | Short Quote | Entry Debit | Exit Value | Gross P&L % | Decision |
|---|---|---:|---|---|---:|---:|---:|---|
| QQQ | volatility_expansion_observation | 537 | entry 2026-06-05T14:39:00Z bid/ask 11.77/11.85; exit 2026-06-05T19:55:00Z bid/ask 6.13/6.5 | entry 2026-06-05T14:39:00Z bid/ask 3.17/3.22; exit 2026-06-05T19:55:00Z bid/ask 1.41/1.47 | 8.68 | 4.66 | -46.31 | `hold_for_current_open_risk_review` |
| SPY | bullish_pullback_observation |  | entry 2026-05-21T14:27:00Z bid/ask 11.98/12.03; exit 2026-05-21T19:55:00Z bid/ask 13.9/14.11 | entry 2026-05-21T14:27:00Z bid/ask 3.55/3.58; exit 2026-05-21T19:55:00Z bid/ask 4.38/4.51 | 8.48 | 9.39 | 10.73 | `reject_production_use_without_fill_or_position_link` |
| QQQ | bullish_pullback_observation |  | entry 2026-05-21T14:27:00Z bid/ask 16.58/16.63; exit 2026-05-21T19:55:00Z bid/ask 19.72/19.88 | entry 2026-05-21T14:27:00Z bid/ask 3.85/3.89; exit 2026-05-21T19:55:00Z bid/ask 4.9/4.98 | 12.78 | 14.74 | 15.34 | `reject_production_use_without_fill_or_position_link` |
| SPY | volatility_expansion_observation |  | entry 2026-05-29T17:45:00Z bid/ask 7.0/7.02; exit 2026-05-29T19:55:00Z bid/ask 7.15/7.29 | entry 2026-05-29T17:45:00Z bid/ask 1.77/1.78; exit 2026-05-29T19:55:00Z bid/ask 1.78/1.82 | 5.25 | 5.33 | 1.52 | `reject_production_use_without_fill_or_position_link` |
| QQQ | volatility_expansion_observation |  | entry 2026-05-29T17:45:00Z bid/ask 11.1/11.15; exit 2026-05-29T19:55:00Z bid/ask 11.78/11.99 | entry 2026-05-29T17:45:00Z bid/ask 2.94/2.97; exit 2026-05-29T19:55:00Z bid/ask 3.11/3.18 | 8.21 | 8.6 | 4.75 | `reject_production_use_without_fill_or_position_link` |
| IWM | volatility_expansion_observation |  | entry 2026-05-29T17:45:00Z bid/ask 4.88/4.94; exit 2026-05-29T19:55:00Z bid/ask 4.58/4.66 | entry 2026-05-29T17:45:00Z bid/ask 2.31/2.35; exit 2026-05-29T19:55:00Z bid/ask 2.04/2.1 | 2.63 | 2.48 | -5.7 | `reject_production_use_without_fill_or_position_link` |
| QQQ | range_breakout_observation |  | entry 2026-06-04T17:03:00Z bid/ask 11.27/11.3; exit 2026-06-04T19:55:00Z bid/ask 11.44/11.64 | entry 2026-06-04T17:03:00Z bid/ask 3.01/3.04; exit 2026-06-04T19:55:00Z bid/ask 3.04/3.09 | 8.29 | 8.35 | 0.72 | `reject_production_use_without_fill_or_position_link` |
| SPY | swing |  | entry 2026-06-04T17:07:00Z bid/ask 7.64/7.67; exit 2026-06-04T19:55:00Z bid/ask 7.87/8.01 | entry 2026-06-04T17:07:00Z bid/ask 2.08/2.1; exit 2026-06-04T19:55:00Z bid/ask 2.14/2.19 | 5.59 | 5.68 | 1.61 | `reject_production_use_without_fill_or_position_link` |
| QQQ | swing |  | entry 2026-06-04T17:07:00Z bid/ask 13.08/13.13; exit 2026-06-04T19:55:00Z bid/ask 13.53/13.73 | entry 2026-06-04T17:07:00Z bid/ask 3.99/4.03; exit 2026-06-04T19:55:00Z bid/ask 4.19/4.25 | 9.14 | 9.28 | 1.53 | `reject_production_use_without_fill_or_position_link` |
| SPY | range_breakout_observation |  | entry 2026-06-04T17:07:00Z bid/ask 6.9/6.93; exit 2026-06-04T19:55:00Z bid/ask 7.11/7.32 | entry 2026-06-04T17:07:00Z bid/ask 1.72/1.73; exit 2026-06-04T19:55:00Z bid/ask 1.77/1.84 | 5.21 | 5.27 | 1.15 | `reject_production_use_without_fill_or_position_link` |
| SPY | volatility_expansion_observation |  | entry 2026-06-04T17:07:00Z bid/ask 6.9/6.93; exit 2026-06-04T19:55:00Z bid/ask 7.11/7.32 | entry 2026-06-04T17:07:00Z bid/ask 1.72/1.73; exit 2026-06-04T19:55:00Z bid/ask 1.77/1.84 | 5.21 | 5.27 | 1.15 | `reject_production_use_without_fill_or_position_link` |
| QQQ | volatility_expansion_observation |  | entry 2026-06-04T17:09:00Z bid/ask 11.27/11.29; exit 2026-06-04T19:55:00Z bid/ask 11.44/11.64 | entry 2026-06-04T17:09:00Z bid/ask 3.0/3.02; exit 2026-06-04T19:55:00Z bid/ask 3.04/3.09 | 8.29 | 8.35 | 0.72 | `reject_production_use_without_fill_or_position_link` |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 2 | `collect_position_linked_exact_entry_seed` | 11 | entry_seed_only_rows_need_fill_or_position_link_for_realized_exit |

## Boundary

- Readback is: `readiness queue for building a future exact OPRA/NBBO minute-level exit replay`.
- Readback is not: `simulated P&L, promotion proof, stop-policy approval, broker action, or a live-risk instruction`.
- Daily stop-grid boundary: `This is not yet a minute-by-minute intraday stop simulation.`.
- P&L rule: `P&L is emitted only when entry and fixed-minute exit long/short bid/ask quotes are present from trusted intraday OPRA/NBBO rows; long exit uses bid and short cover uses ask.`.
- Fees/slippage assumption: `gross replay only: no additional fees or slippage beyond side-aware bid/ask prices`.

This report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stop policy, change sizing, synthesize exit P&L from daily/midpoint/stale/display marks, lower proof bars, or promote replay rows to production proof.

