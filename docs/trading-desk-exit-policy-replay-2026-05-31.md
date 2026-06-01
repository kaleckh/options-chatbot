# Trading Desk Exit Policy Replay - 2026-05-31

This is a read-only replay of Trading Desk exit policies over stored executable review rows. It excludes unpriced reviews, last-trade/display-only marks, midpoint-only rows, and rows without executable exit evidence.

## Inventory

- Regular positions: `536`
- Replayable positions with executable review timelines: `107`
- Baseline positions with P&L: `107`

## Baseline

| Priced | Negative | Positive/Flat | Avg P&L | Median P&L | Negative Rate |
|---:|---:|---:|---:|---:|---:|
| 107 | 25 | 82 | 37.28% | 35.79% | 23.4% |

## Policy Results

No tested broad exit variant clears the promotion bar. The replayable subset has `107` regular Trading Desk rows with stored executable review timelines; the baseline is already positive at `+37.28%` average P&L and `+35.79%` median P&L. The only positive-delta broad shapes, `stop_70` and `current_policy_replay`, are research candidates because they still increase the negative count from `25` to `26` and convert `2` stored winners into losses. Global profit harvest, global trailing giveback, shorter time exits, and stored-SELL following all reduce average executable P&L.

| Policy | Recommendation | Avg Delta | Median Delta | Avg P&L | Median P&L | Negatives | Winner Losses | Top Reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `stop_70` | research_candidate | 2.56% | 0.0% | 39.83% | 37.63% | 26 | 2 | time_exit:48, no_policy_trigger:48, stop_loss:7, profit_target:4 |
| `current_policy_replay` | research_candidate | 2.32% | 0.0% | 39.6% | 36.34% | 26 | 2 | no_policy_trigger:53, time_exit:46, profit_target:4, profit_harvest:2 |
| `stop_50` | reject_current_shape | 1.13% | 0.0% | 38.41% | 36.34% | 27 | 3 | time_exit:46, no_policy_trigger:45, stop_loss:12, profit_target:4 |
| `time_exit_10` | reject_current_shape | -3.11% | 0.0% | 34.17% | 35.79% | 26 | 2 | time_exit:92, no_policy_trigger:14, stop_loss:1 |
| `profit_harvest_all_lanes_50` | reject_current_shape | -7.94% | 0.0% | 29.34% | 37.63% | 26 | 2 | no_policy_trigger:51, profit_harvest:41, time_exit:14, stop_loss:1 |
| `profit_harvest_all_lanes_35` | reject_current_shape | -10.12% | 0.0% | 27.16% | 37.42% | 26 | 2 | profit_harvest:60, no_policy_trigger:36, time_exit:10, stop_loss:1 |
| `time_exit_7` | reject_current_shape | -10.92% | 0.0% | 26.35% | 34.09% | 28 | 4 | time_exit:105, stop_loss:1, no_policy_trigger:1 |
| `stored_sell_recommendation` | reject_current_shape | -11.15% | 0.0% | 26.13% | 32.51% | 26 | 2 | stored_executable_sell_recommendation:60, no_policy_trigger:47 |
| `trailing_giveback_all_lanes_50_20` | reject_current_shape | -16.75% | 0.0% | 20.53% | 28.44% | 26 | 2 | no_policy_trigger:52, trailing_giveback:38, time_exit:16, stop_loss:1 |

## Legacy Rows 26, 39, 44

| Policy | Trade | Ticker | Lane | Baseline | Replay P&L | Delta | Reason | Reviewed At |
|---|---:|---|---|---:|---:|---:|---|---|
| `stop_70` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `stop_70` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `stop_70` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |
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
| `profit_harvest_all_lanes_35` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `profit_harvest_all_lanes_35` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `profit_harvest_all_lanes_35` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 35.1693% | 79.9489% | profit_harvest | 2026-04-20 11:00:38.270751-06:00 |
| `time_exit_7` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `time_exit_7` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `time_exit_7` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 30.3304% | 75.11% | time_exit | 2026-04-22 10:32:51.424375-06:00 |
| `stored_sell_recommendation` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | stored_executable_sell_recommendation | 2026-05-06 08:09:05.144366-06:00 |
| `stored_sell_recommendation` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | stored_executable_sell_recommendation | 2026-05-06 08:03:06.827552-06:00 |
| `stored_sell_recommendation` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 6.555% | 51.3346% | stored_executable_sell_recommendation | 2026-04-16 12:47:00.148232-06:00 |
| `trailing_giveback_all_lanes_50_20` | 44 | JPM | `legacy_unlabeled` | -80.098% | -38.925% | 41.173% | time_exit | 2026-05-06 08:09:05.144366-06:00 |
| `trailing_giveback_all_lanes_50_20` | 39 | DIA | `legacy_unlabeled` | -42.9751% | -22.179% | 20.7961% | time_exit | 2026-05-06 08:03:06.827552-06:00 |
| `trailing_giveback_all_lanes_50_20` | 26 | JPM | `legacy_unlabeled` | -44.7796% | 3.9946% | 48.7742% | time_exit | 2026-05-06 08:09:09.055925-06:00 |

## Recommendation

Do not promote a new broad exit rule from this replay. Keep the current profit-first `90%` stop posture and existing lane-limited profit harvest behavior.

The real follow-up is narrower: legacy rows `26`, `39`, and `44` show that current time-exit style replay would have materially improved their outcomes, but the broader universe does not support turning global harvest/giveback or shorter time exits into production rules. Audit those legacy rows as an execution/application problem: determine whether the state-changing review endpoint, historical migration timing, or stale policy-version behavior prevented an executable time exit from being realized.

Do not promote an exit rule unless it improves average and median executable P&L, does not increase the negative rate, and does not convert stored winners into losses. Treat legacy missed-auto-close rows as a separate diagnostic unless the same rule improves the broader executable-review universe.
