# Missed Regular Picks Failure Modes

- Generated: `2026-06-10T06:27:17Z`
- Source report: `data/forward-tracking/missed_regular_picks_outcome_latest.json`
- Source generated: `2026-06-10T06:27:05Z`
- Data status: `clean_for_failure_analysis`
- Rows: `210` total, `4` tracked, `206` untracked
- Mark coverage: `210` priced / `0` unpriced
- Quote evidence class: `trusted_intraday_opra_nbbo`
- Row evidence group: `research_backfill`
- Production proof claim: `False`
- Tracked P&L complete: `True`

## Verdict

- Status: `data_clean_strategy_unprofitable`
- Untracked avg net P&L: `-16.54%`
- Untracked PF: `0.32`
- Winners / losers: `72` / `134`
- One-spread net dollars: `$-18755.0`
- Negative rate: `65.0%`
- Rows <= -50%: `41`
- Rows <= -80%: `15`
- Zero-exit-credit rows: `4`

## Lane Decisions

| Lane | Decision | Rows | PF | Avg Net | Blockers |
|---|---|---:|---:|---:|---|
| bullish_momentum | diagnostic_only_until_earn_back | 16 | 0.04 | -48.45 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| bullish_pullback_observation | diagnostic_only_until_earn_back | 15 | 0.24 | -22.81 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| short_term | diagnostic_only_until_earn_back | 54 | 0.33 | -18.93 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| speculative | diagnostic_only_until_earn_back | 8 | 0.1 | -12.62 | insufficient_priced_exact_outcomes, profit_factor_below_lane_gate, average_net_pnl_not_positive |
| swing | diagnostic_only_until_earn_back | 49 | 0.2 | -20.24 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| tracked_winner_observation | diagnostic_only_until_earn_back | 20 | 0.5 | -8.43 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| tracked_winner_primary | diagnostic_only_until_earn_back | 20 | 0.5 | -8.43 | profit_factor_below_lane_gate, average_net_pnl_not_positive |
| volatility_expansion_observation | probation_candidate_flow_with_self_guardrails | 24 | 1.83 | 6.74 | none |

## Guardrail Candidates

- Active lane blocks: `bullish_momentum, bullish_pullback_observation, short_term, speculative, swing, tracked_winner_observation, tracked_winner_primary`
- Probation lanes: `volatility_expansion_observation`
- Debit >= 45% of width: `37` rows, avg `-38.26%`, PF `0.05`
- DTE >= 36: `19` rows, avg `-29.05%`, PF `0.12`

## Ticker Quarantine Candidates

| Ticker | Rows | PF | Avg Net | Winners | Losers | Net Points |
|---|---:|---:|---:|---:|---:|---:|
| XLK | 31 | 0.01 | -37.43 | 4 | 27 | -1160.44 |
| SPY | 39 | 0.22 | -11.03 | 9 | 30 | -430.22 |
| TSLA | 11 | 0.0 | -36.14 | 0 | 11 | -397.54 |
| IWM | 20 | 0.12 | -16.51 | 6 | 14 | -330.23 |
| AA | 5 | 0.0 | -58.93 | 0 | 5 | -294.66 |
| AMZN | 4 | 0.03 | -61.01 | 1 | 3 | -244.02 |
| PLD | 2 | 0.0 | -101.43 | 0 | 2 | -202.86 |
| NVDA | 3 | 0.0 | -67.12 | 0 | 3 | -201.36 |
| FCX | 7 | 0.08 | -25.81 | 1 | 6 | -180.67 |
| SLB | 3 | 0.0 | -58.47 | 0 | 3 | -175.4 |
| BA | 2 | 0.0 | -79.67 | 0 | 2 | -159.35 |
| QQQ | 21 | 0.57 | -4.66 | 10 | 11 | -97.94 |

## Worst Ticker Clusters

| Ticker | Rows | PF | Avg Net | Winners | Losers | Net Points |
|---|---:|---:|---:|---:|---:|---:|
| XLK | 31 | 0.01 | -37.43 | 4 | 27 | -1160.44 |
| SPY | 39 | 0.22 | -11.03 | 9 | 30 | -430.22 |
| TSLA | 11 | 0.0 | -36.14 | 0 | 11 | -397.54 |
| IWM | 20 | 0.12 | -16.51 | 6 | 14 | -330.23 |
| AA | 5 | 0.0 | -58.93 | 0 | 5 | -294.66 |
| AMZN | 4 | 0.03 | -61.01 | 1 | 3 | -244.02 |
| PLD | 2 | 0.0 | -101.43 | 0 | 2 | -202.86 |
| NVDA | 3 | 0.0 | -67.12 | 0 | 3 | -201.36 |
| FCX | 7 | 0.08 | -25.81 | 1 | 6 | -180.67 |
| SLB | 3 | 0.0 | -58.47 | 0 | 3 | -175.4 |
| BA | 2 | 0.0 | -79.67 | 0 | 2 | -159.35 |
| QQQ | 21 | 0.57 | -4.66 | 10 | 11 | -97.94 |
| SMCI | 2 | 0.0 | -36.28 | 0 | 2 | -72.55 |
| LLY | 2 | 0.03 | -19.27 | 1 | 1 | -38.54 |
| AAPL | 2 | 0.0 | -17.82 | 0 | 2 | -35.64 |
| C | 8 | 1.47 | 7.9 | 4 | 4 | 63.19 |
| UNH | 4 | None | 34.7 | 4 | 0 | 138.81 |
| DIA | 34 | 40.27 | 24.36 | 31 | 3 | 828.33 |

## Failure Buckets

### Debit Percent Of Width

| Bucket | Rows | PF | Avg Net | Winners | Losers |
|---|---:|---:|---:|---:|---:|
| 55_plus | 6 | 0.0 | -55.4 | 0 | 6 |
| 45_55 | 31 | 0.05 | -34.94 | 6 | 25 |
| 25_35 | 43 | 0.33 | -13.62 | 17 | 26 |
| 35_45 | 121 | 0.38 | -11.57 | 46 | 75 |
| lt25 | 5 | 1.84 | -1.29 | 3 | 2 |

### DTE

| Bucket | Rows | PF | Avg Net | Winners | Losers |
|---|---:|---:|---:|---:|---:|
| 36_plus | 19 | 0.12 | -29.05 | 5 | 14 |
| 11_20 | 55 | 0.24 | -19.36 | 17 | 38 |
| 6_10 | 61 | 0.37 | -18.04 | 19 | 42 |
| 21_35 | 66 | 0.57 | -10.03 | 29 | 37 |
| lte5 | 5 | 0.3 | -5.78 | 2 | 3 |

## Earn-Back Policy

- Diagnostic lanes need at least `30` exact marked rows, `0` unpriced rows, PF `>= 1.2`, positive average net P&L, entry-time-only rules, and a later-date/OOS pass before probation.
- Probation lanes need PF near `1.5`, positive fee/slippage stress, no unblocked negative ticker/debit cluster, and fresh forward paper rows before production discussion.
- This report is a routing and repair audit, not broker execution evidence or a recommendation.

