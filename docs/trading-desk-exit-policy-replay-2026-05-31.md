# Trading Desk Exit Policy Replay - 2026-05-31

This is a read-only replay of Trading Desk exit policies over stored executable review rows. It excludes unpriced reviews, last-trade/display-only marks, midpoint-only rows, and rows without executable exit evidence.

## Inventory

- Regular positions: `536`
- Replayable positions with executable review timelines: `107`
- Baseline positions with P&L: `107`

## Baseline

| Priced | Negative | Positive/Flat | Avg P&L | Median P&L | Negative Rate |
|---:|---:|---:|---:|---:|---:|
| 107 | 23 | 84 | 39.06% | 43.72% | 21.5% |

## Deep-Loss Buckets

| Scope | <= -50% | <= -70% | <= -80% | <= -90% | <= -95% | <= -99% |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 14 | 11 | 9 | 2 | 1 | 1 |

## Policy Results

| Policy | Recommendation | Avg Delta | Avg P&L | Negatives | <= -90% | <= -95% | <= -99% | Stop Rows | Stop Avg Delta | Winner Losses | Top Reasons |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `stop_60` | research_candidate | 2.87% | 41.93% | 24 | 1 | 1 | 1 | 10 | 3.16% | 2 | time_exit:51, no_policy_trigger:41, stop_loss:10, profit_target:5 |
| `stop_70` | research_candidate | 2.68% | 41.75% | 24 | 1 | 1 | 1 | 8 | 1.54% | 2 | time_exit:51, no_policy_trigger:43, stop_loss:8, profit_target:5 |
| `stop_80` | research_candidate | 2.66% | 41.73% | 24 | 1 | 1 | 1 | 8 | 1.27% | 2 | time_exit:51, no_policy_trigger:43, stop_loss:8, profit_target:5 |
| `stop_90` | research_candidate | 2.56% | 41.62% | 24 | 1 | 1 | 1 | 1 | -1.0% | 2 | time_exit:51, no_policy_trigger:50, profit_target:5, stop_loss:1 |
| `current_policy_replay` | research_candidate | 1.59% | 40.65% | 24 | 1 | 1 | 1 | 1 | -1.0% | 2 | time_exit:49, no_policy_trigger:39, profit_harvest:8, trailing_giveback:5 |
| `stop_50` | reject_current_shape | 1.51% | 40.58% | 25 | 1 | 1 | 1 | 13 | -7.5% | 3 | time_exit:49, no_policy_trigger:40, stop_loss:13, profit_target:5 |
| `time_exit_10` | reject_current_shape | -4.89% | 34.17% | 26 | 1 | 1 | 1 | 1 | -1.0% | 6 | time_exit:101, no_policy_trigger:5, stop_loss:1 |
| `profit_harvest_all_lanes_50` | reject_current_shape | -8.41% | 30.65% | 24 | 1 | 1 | 1 | 1 | -1.0% | 2 | profit_harvest:51, no_policy_trigger:38, time_exit:17, stop_loss:1 |
| `stored_sell_recommendation` | reject_current_shape | -11.15% | 27.91% | 24 | 1 | 1 | 1 | 0 |  | 2 | stored_executable_sell_recommendation:76, no_policy_trigger:31 |
| `profit_harvest_all_lanes_35` | reject_current_shape | -11.87% | 27.19% | 24 | 1 | 1 | 1 | 1 | -1.0% | 2 | profit_harvest:64, no_policy_trigger:32, time_exit:10, stop_loss:1 |
| `time_exit_7` | reject_current_shape | -12.71% | 26.35% | 28 | 1 | 1 | 1 | 1 | -1.0% | 8 | time_exit:105, stop_loss:1, no_policy_trigger:1 |
| `trailing_giveback_all_lanes_50_20` | reject_current_shape | -17.96% | 21.1% | 24 | 1 | 1 | 1 | 1 | -1.0% | 2 | no_policy_trigger:44, trailing_giveback:43, time_exit:19, stop_loss:1 |

## Stop-Loss Trigger Detail

| Policy | Stop Rows | Stop Avg P&L | Stop Avg Baseline | Stop Avg Delta | Stop <= -90% | Stop Winner Losses | Top Stop Lanes |
|---|---:|---:|---:|---:|---:|---:|---|
| `stop_60` | 10 | -78.73% | -81.89% | 3.16% | 1 | 0 | bullish_pullback_observation:5, tracked_winner_observation:2, tracked_winner_primary:2, swing:1 |
| `stop_70` | 8 | -85.1% | -86.64% | 1.54% | 1 | 0 | bullish_pullback_observation:3, tracked_winner_observation:2, tracked_winner_primary:2, swing:1 |
| `stop_80` | 8 | -85.37% | -86.64% | 1.27% | 1 | 0 | bullish_pullback_observation:3, tracked_winner_observation:2, tracked_winner_primary:2, swing:1 |
| `stop_90` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `current_policy_replay` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `stop_50` | 13 | -72.55% | -65.05% | -7.5% | 1 | 1 | bullish_pullback_observation:6, legacy_unlabeled:2, tracked_winner_observation:2, tracked_winner_primary:2 |
| `time_exit_10` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `profit_harvest_all_lanes_50` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `profit_harvest_all_lanes_35` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `time_exit_7` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |
| `trailing_giveback_all_lanes_50_20` | 1 | -101.0% | -100.0% | -1.0% | 1 | 0 | bullish_pullback_observation:1 |

## Legacy Rows 26, 39, 44

| Policy | Trade | Ticker | Lane | Baseline | Replay P&L | Delta | Reason | Reviewed At |
|---|---:|---|---|---:|---:|---:|---|---|
| `stop_60` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_60` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_60` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `stop_70` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_70` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_70` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `stop_80` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_80` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_80` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `stop_90` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_90` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_90` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `current_policy_replay` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `current_policy_replay` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `current_policy_replay` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `stop_50` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_50` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_50` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `time_exit_10` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `time_exit_10` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `time_exit_10` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `profit_harvest_all_lanes_50` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `profit_harvest_all_lanes_50` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `profit_harvest_all_lanes_50` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
| `stored_sell_recommendation` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | stored_executable_sell_recommendation | 2026-05-06 08:09:05.144366-06:00 |
| `stored_sell_recommendation` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | stored_executable_sell_recommendation | 2026-05-06 08:03:06.827552-06:00 |
| `stored_sell_recommendation` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 6.555% | 51.3346% | stored_executable_sell_recommendation | 2026-04-16 12:47:00.148232-06:00 |
| `profit_harvest_all_lanes_35` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `profit_harvest_all_lanes_35` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `profit_harvest_all_lanes_35` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 35.1693% | 79.9489% | profit_harvest | 2026-04-20 11:00:38.270751-06:00 |
| `time_exit_7` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `time_exit_7` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `time_exit_7` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 30.3304% | 75.11% | time_exit | 2026-04-22 10:32:51.424375-06:00 |
| `trailing_giveback_all_lanes_50_20` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `trailing_giveback_all_lanes_50_20` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `trailing_giveback_all_lanes_50_20` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |

## Recommendation

Do not promote an exit rule unless it improves average and median executable P&L, reduces or holds the deep-loss buckets, does not increase the negative rate, and does not convert stored winners into losses. Treat legacy missed-auto-close rows as a separate diagnostic unless the same rule improves the broader executable-review universe.

This stored-review replay cannot answer whether tighter stops would have saved current-policy historical-paper rows that have no executable review timeline. Those rows need a separate exact OPRA/NBBO historical stop replay before live review stops are changed.
