# Regular Options Chain-Native Exit Outcome Replay

This report is generated from `scripts/build_regular_options_chain_native_exit_outcome_replay.py`. It prices selected chain-native diagnostic candidates with trusted intraday OPRA/NBBO exit quotes and remains read-only.

## Summary

- Status: `chain_native_exit_outcome_replay_readback`.
- Overall status: `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only`.
- Latest intraday quote date: `2026-06-04`.
- Selected scenario rows: `28`.
- Current / relaxed selected rows: `4` / `24`.
- Priced scenario rows: `28`.
- Missing exit quote demands: `0`.
- Best relaxed scenario: `{"avg_net_pnl_pct": -9.26, "avg_net_pnl_usd": -288.5, "loser_count": 3, "max_net_pnl_pct": 61.57, "median_net_pnl_pct": -18.85, "min_net_pnl_pct": -60.9, "priced": 4, "profit_factor": 0.62, "relaxation_kind": "relaxed", "rows": 4, "scenario_id": "widen_dte_window_only", "sum_net_pnl_usd": -1154.0, "unpriced": 0, "win_rate_pct": 25.0, "winner_count": 1}`.
- All-row metrics: `{"avg_net_pnl_pct": -22.63, "avg_net_pnl_usd": -370.28, "loser_count": 25, "max_net_pnl_pct": 61.57, "median_net_pnl_pct": -18.85, "min_net_pnl_pct": -60.9, "priced": 28, "profit_factor": 0.13, "rows": 28, "sum_net_pnl_usd": -10367.75, "unpriced": 0, "win_rate_pct": 10.7, "winner_count": 3}`.
- Promotion ready: `False`.
- Blockers: `["fresh_paper_holdout_required_before_policy_change", "single_date_target_overfit_risk"]`.
- Live policy change: `false`.

## Scenario Metrics

| Scenario | Kind | Rows | Priced | PF | Avg Net | Median | Win Rate | Net USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `current_chain_native_filters` | current | 4 | 4 | 0.0 | -27.93 | -18.85 | 0.0 | -1705.25 |
| `widen_dte_window_only` | relaxed | 4 | 4 | 0.62 | -9.26 | -18.85 | 25.0 | -1154.0 |
| `combined_broad_entry_relaxation` | relaxed | 4 | 4 | 0.18 | -20.22 | -18.85 | 25.0 | -1247.5 |
| `relax_width_cap_only` | relaxed | 4 | 4 | 0.18 | -20.22 | -18.85 | 25.0 | -1247.5 |
| `relax_debit_cap_only` | relaxed | 4 | 4 | 0.0 | -24.92 | -18.85 | 0.0 | -1603.0 |
| `relax_entry_liquidity_caps_only` | relaxed | 4 | 4 | 0.0 | -27.93 | -18.85 | 0.0 | -1705.25 |
| `relax_prior_quote_continuity_only` | relaxed | 4 | 4 | 0.0 | -27.93 | -18.85 | 0.0 | -1705.25 |

## Outcome Rows

| Scenario | Ticker | Long | Short | Entry Debit | Exit Credit | Net P&L % | Net USD | Quote Date | Blockers |
|---|---|---|---|---:|---:|---:|---:|---|---|
| `combined_broad_entry_relaxation` | COIN | `COIN260626P00200000` | `COIN260626P00165000` | 19.5175 | 23.0 | 17.7097 | 345.65 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `combined_broad_entry_relaxation` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `combined_broad_entry_relaxation` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `combined_broad_entry_relaxation` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `current_chain_native_filters` | COIN | `COIN260626P00180000` | `COIN260626P00165000` | 8.545 | 7.45 | -13.1188 | -112.1 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `current_chain_native_filters` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `current_chain_native_filters` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `current_chain_native_filters` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_debit_cap_only` | COIN | `COIN260626P00185000` | `COIN260626P00170000` | 9.1725 | 9.1 | -1.0739 | -9.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_debit_cap_only` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_debit_cap_only` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_debit_cap_only` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_entry_liquidity_caps_only` | COIN | `COIN260626P00180000` | `COIN260626P00165000` | 8.545 | 7.45 | -13.1188 | -112.1 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_entry_liquidity_caps_only` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_entry_liquidity_caps_only` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_entry_liquidity_caps_only` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_prior_quote_continuity_only` | COIN | `COIN260626P00180000` | `COIN260626P00165000` | 8.545 | 7.45 | -13.1188 | -112.1 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_prior_quote_continuity_only` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_prior_quote_continuity_only` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_prior_quote_continuity_only` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_width_cap_only` | COIN | `COIN260626P00200000` | `COIN260626P00165000` | 19.5175 | 23.0 | 17.7097 | 345.65 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_width_cap_only` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_width_cap_only` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `relax_width_cap_only` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `widen_dte_window_only` | COIN | `COIN260618P00187500` | `COIN260618P00170000` | 7.1325 | 11.55 | 61.5703 | 439.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `widen_dte_window_only` | DIS | `DIS260626P00105000` | `DIS260626P00095000` | 4.2255 | 3.66 | -13.9983 | -59.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `widen_dte_window_only` | META | `META260626P00615000` | `META260626P00555000` | 23.1025 | 9.06 | -60.896 | -1406.85 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |
| `widen_dte_window_only` | SBUX | `SBUX260626P00105000` | `SBUX260626P00096000` | 5.3655 | 4.12 | -23.6977 | -127.15 | 2026-06-04 | single_date_target_overfit_risk, fresh_paper_holdout_required_before_policy_change |

## Exit Quote Demands

| Scenario | Ticker | Long | Short | Date Window | Missing Reason |
|---|---|---|---|---|---|

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 5 | `archive_negative_chain_native_relaxation_branch` | 1 | relaxed_chain_native_exit_outcome_not_profitable_on_exact_replay |

## Boundary

This chain-native exit outcome replay is read-only and diagnostic. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, change stops or sizing, lower exact OPRA/NBBO proof bars, or promote a single-date replay into production proof.

