# Regular Options Chain-Native Relaxation Archive

This report is generated from `scripts/build_regular_options_chain_native_relaxation_archive.py`. It is a read-only archive for chain-native relaxation branches that exact exit replay already disproved.

## Summary

- Status: `chain_native_relaxation_archive_readback`.
- Overall status: `negative_chain_native_branches_archived`.
- Source exit-outcome status: `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only`.
- Archived negative chain-native branches: `7` / `7`.
- Archived negative current scenarios: `1` / `1`.
- Archived negative relaxed scenarios: `6` / `6`.
- Unarchived negative branches: `[]`.
- Archive requested by exit-outcome replay: `true`.
- Best relaxed scenario: `{"avg_net_pnl_pct": -9.26, "avg_net_pnl_usd": -288.5, "loser_count": 3, "max_net_pnl_pct": 61.57, "median_net_pnl_pct": -18.85, "min_net_pnl_pct": -60.9, "priced": 4, "profit_factor": 0.62, "relaxation_kind": "relaxed", "rows": 4, "scenario_id": "widen_dte_window_only", "sum_net_pnl_usd": -1154.0, "unpriced": 0, "win_rate_pct": 25.0, "winner_count": 1}`.
- Live policy change: `false`.

## Archived Branches

| Branch | Scenario | Reason | Priced | PF | Avg Net | Net USD | Win Rate | Target Dates | Tickers |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| current_chain_native_filters\|regular_bearish_put_primary\|2026-05-22 | current_chain_native_filters | negative_exact_exit_pnl_and_profit_factor_below_one | 4 |  | -27.93 | -1705.25 |  | 2026-05-22 | COIN, DIS, META, SBUX |
| relax_entry_liquidity_caps_only\|regular_bearish_put_primary\|2026-05-22 | relax_entry_liquidity_caps_only | negative_exact_exit_pnl_and_profit_factor_below_one | 4 |  | -27.93 | -1705.25 |  | 2026-05-22 | COIN, DIS, META, SBUX |
| relax_prior_quote_continuity_only\|regular_bearish_put_primary\|2026-05-22 | relax_prior_quote_continuity_only | negative_exact_exit_pnl_and_profit_factor_below_one | 4 |  | -27.93 | -1705.25 |  | 2026-05-22 | COIN, DIS, META, SBUX |
| relax_debit_cap_only\|regular_bearish_put_primary\|2026-05-22 | relax_debit_cap_only | negative_exact_exit_pnl_and_profit_factor_below_one | 4 |  | -24.92 | -1603.0 |  | 2026-05-22 | COIN, DIS, META, SBUX |
| combined_broad_entry_relaxation\|regular_bearish_put_primary\|2026-05-22 | combined_broad_entry_relaxation | negative_exact_exit_pnl_and_profit_factor_below_one | 4 | 0.18 | -20.22 | -1247.5 | 25.0 | 2026-05-22 | COIN, DIS, META, SBUX |
| relax_width_cap_only\|regular_bearish_put_primary\|2026-05-22 | relax_width_cap_only | negative_exact_exit_pnl_and_profit_factor_below_one | 4 | 0.18 | -20.22 | -1247.5 | 25.0 | 2026-05-22 | COIN, DIS, META, SBUX |
| widen_dte_window_only\|regular_bearish_put_primary\|2026-05-22 | widen_dte_window_only | negative_exact_exit_pnl_and_profit_factor_below_one | 4 | 0.62 | -9.26 | -1154.0 | 25.0 | 2026-05-22 | COIN, DIS, META, SBUX |

## Boundary

This archive is read-only. It does not delete chain-native scenarios, create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote negative chain-native replay.

