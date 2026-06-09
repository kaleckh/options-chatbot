# Regular Options Execution Alternative Replay Readiness

This report is generated from `scripts/build_regular_options_execution_alternative_replay_readiness.py`. It is a read-only readiness queue for future top-spread and contract-replacement replay work and does not simulate P&L or change contract selection.

## Summary

- Status: `execution_alternative_replay_readiness_readback`.
- Overall status: `blocked_ready_seed_missing_execution_alternative_replay_engine`.
- Candidate-shown rows: `12`.
- Top-spread replay seeds: `12`.
- Contract-replacement seeds: `12`.
- True top-spread / contract-replacement P&L rows: `0` / `0`.
- Alternative exit quote coverage: `missing`.
- Replay engines: `missing` / `missing`.
- Blockers: `["alternate_contract_exit_quote_coverage_missing", "contract_replacement_exit_survivability_replay_engine_missing", "top_spread_liquidity_first_replay_engine_missing", "true_alternative_replay_pnl_rows_missing"]`.
- Live policy change: `false`.

## Candidate Queue

| Status | Ticker | Lane | Entry Time | Selected Long | Selected Short | Alternatives | Replacements | Blockers |
|---|---|---|---|---|---|---:|---:|---|
| `alternative_seed_ready_engine_missing` | SPY | bullish_pullback_observation | 2026-05-21T14:27:47.890289+00:00 | SPY260618C00740000 | SPY260618C00760000 | 3 | 2 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | bullish_pullback_observation | 2026-05-21T14:27:49.005738+00:00 | QQQ260618C00710000 | QQQ260618C00745000 | 3 | 2 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | SPY | volatility_expansion_observation | 2026-05-29T17:45:16.006159Z | SPY260612C00757000 | SPY260612C00770000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | volatility_expansion_observation | 2026-05-29T17:45:20.554574Z | QQQ260612C00738000 | QQQ260612C00760000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | IWM | volatility_expansion_observation | 2026-05-29T17:45:24.054950Z | IWM260612C00290000 | IWM260612C00296000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | range_breakout_observation | 2026-06-04T17:03:11.116739Z | QQQ260618C00743000 | QQQ260618C00765000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | SPY | swing | 2026-06-04T17:07:12.311709Z | SPY260626C00760000 | SPY260626C00775000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | swing | 2026-06-04T17:07:16.606684Z | QQQ260626C00745000 | QQQ260626C00770000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | SPY | range_breakout_observation | 2026-06-04T17:07:18.297519Z | SPY260618C00758000 | SPY260618C00771000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | SPY | volatility_expansion_observation | 2026-06-04T17:07:18.297519Z | SPY260618C00758000 | SPY260618C00771000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | volatility_expansion_observation | 2026-06-04T17:09:06.793391Z | QQQ260618C00743000 | QQQ260618C00765000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |
| `alternative_seed_ready_engine_missing` | QQQ | volatility_expansion_observation | 2026-06-05T14:39:44.945897Z | QQQ260618C00728000 | QQQ260618C00750000 | 6 | 4 | contract_replacement_exit_survivability_replay_engine_missing, top_spread_liquidity_first_replay_engine_missing, alternate_contract_exit_quote_coverage_missing, true_alternative_replay_pnl_rows_missing |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 0 | `build_contract_replacement_exit_survivability_replay_engine` | 1 | contract_replacement_exit_survivability_replay_engine_missing |
| 1 | `build_top_spread_liquidity_first_replay_engine` | 1 | top_spread_liquidity_first_replay_engine_missing |
| 2 | `import_or_query_alternative_exit_quotes` | 12 | alternate_contract_exit_quote_coverage_missing_for_seed_rows |

## Boundary

- Readback is: `readiness queue for future exact OPRA/NBBO top-spread and contract-replacement replay work`.
- Readback is not: `simulated P&L, contract-selection permission, promotion proof, broker action, or a live-risk instruction`.
- Trusted future requirement: `exact-contract OPRA/NBBO bid/ask replay for selected and alternative contracts from entry through exit with no midpoint, daily/EOD, stale, display, or manual marks`.

This readiness report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change contract selection, change stops, change sizing, synthesize alternative P&L from midpoint/daily/stale/display marks, lower proof bars, or promote readiness rows to production proof.

