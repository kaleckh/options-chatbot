# Regular Options Execution Alternative Replay Coverage

This report is generated from `scripts/build_regular_options_execution_alternative_replay_coverage.py`. It is a read-only exact OPRA/NBBO coverage and side-aware replay availability report for logged execution alternatives.

## Summary

- Status: `execution_alternative_replay_coverage_readback`.
- Overall status: `execution_alternative_replay_coverage_ready`.
- Candidate seeds: `12`.
- Top-spread true P&L rows: `12` / `12`.
- Contract-replacement true P&L rows: `12` / `12`.
- Top entry/exit coverage: `full` / `full`.
- Replacement entry/exit coverage: `full` / `full`.
- Quote-demand manifest: `no_missing_quote_demands` with `0` unique missing quote targets.
- Replay engines: `read_only_side_aware_engine_partial` / `read_only_side_aware_engine_partial`.
- Blockers: `[]`.
- Live policy change: `false`.

## Coverage Rows

| Ticker | Lane | Entry ET Minute | Top Entry | Top Exit | Replacement Entry | Replacement Exit | True Top P&L | True Replacement P&L | Blockers |
|---|---|---:|---|---|---|---|---:|---:|---|
| SPY | bullish_pullback_observation | 627 | True | True | True | True | True | True | none |
| QQQ | bullish_pullback_observation | 627 | True | True | True | True | True | True | none |
| SPY | volatility_expansion_observation | 825 | True | True | True | True | True | True | none |
| QQQ | volatility_expansion_observation | 825 | True | True | True | True | True | True | none |
| IWM | volatility_expansion_observation | 825 | True | True | True | True | True | True | none |
| QQQ | range_breakout_observation | 783 | True | True | True | True | True | True | none |
| SPY | swing | 787 | True | True | True | True | True | True | none |
| QQQ | swing | 787 | True | True | True | True | True | True | none |
| SPY | range_breakout_observation | 787 | True | True | True | True | True | True | none |
| SPY | volatility_expansion_observation | 787 | True | True | True | True | True | True | none |
| QQQ | volatility_expansion_observation | 789 | True | True | True | True | True | True | none |
| QQQ | volatility_expansion_observation | 639 | True | True | True | True | True | True | none |

## True Side-Aware Rows

| Ticker | Label | Entry Debit | Exit Value | Gross P&L % |
|---|---|---:|---:|---:|
| SPY | `top_spread` | 8.48 | 9.39 | 10.73 |
| SPY | `contract_replacement` | 8.74 | 9.69 | 10.87 |
| QQQ | `top_spread` | 12.78 | 14.74 | 15.34 |
| QQQ | `contract_replacement` | 10.67 | 12.27 | 15.0 |
| SPY | `top_spread` | 5.25 | 5.33 | 1.52 |
| SPY | `contract_replacement` | 4.69 | 4.78 | 1.92 |
| QQQ | `top_spread` | 8.21 | 8.6 | 4.75 |
| QQQ | `contract_replacement` | 7.15 | 7.54 | 5.45 |
| IWM | `top_spread` | 2.63 | 2.48 | -5.7 |
| IWM | `contract_replacement` | 1.62 | 1.48 | -8.64 |
| QQQ | `top_spread` | 8.29 | 8.35 | 0.72 |
| QQQ | `contract_replacement` | 8.85 | 8.9 | 0.56 |
| SPY | `top_spread` | 5.59 | 5.68 | 1.61 |
| SPY | `contract_replacement` | 6.13 | 6.22 | 1.47 |
| QQQ | `top_spread` | 9.14 | 9.28 | 1.53 |
| QQQ | `contract_replacement` | 10.13 | 10.33 | 1.97 |
| SPY | `top_spread` | 5.21 | 5.27 | 1.15 |
| SPY | `contract_replacement` | 4.66 | 4.71 | 1.07 |
| SPY | `top_spread` | 5.21 | 5.27 | 1.15 |
| SPY | `contract_replacement` | 4.66 | 4.71 | 1.07 |
| QQQ | `top_spread` | 8.29 | 8.35 | 0.72 |
| QQQ | `contract_replacement` | 8.85 | 8.9 | 0.56 |
| QQQ | `top_spread` | 8.68 | 4.66 | -46.31 |
| QQQ | `contract_replacement` | 8.91 | 4.72 | -47.03 |

## Quote Demand Manifest

| Priority | Phase | Contract | Date | Minute ET | Window | Usages | Source Rows | Missing Reasons |
|---:|---|---|---|---:|---:|---|---:|---|
|  | none |  |  |  |  |  |  |  |

## Missing Quote Reasons

`{}`

## Boundary

- Readback is: `read-only exact OPRA/NBBO bid/ask coverage and side-aware replay availability for logged execution alternatives`.
- Readback is not: `scanner policy, contract-selection permission, broker action, DB mutation, stop/sizing change, or promotion proof`.
- P&L rule: `P&L is emitted only when both entry and exit long/short bid/ask quotes are present from trusted intraday OPRA/NBBO rows.`.

This coverage report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change contract selection, change stops, change sizing, synthesize P&L from midpoint/daily/stale/display marks, lower proof bars, or promote replay rows to production proof.

