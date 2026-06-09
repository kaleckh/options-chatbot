# Regular Options Chain-Native Filter Relaxation Replay

This report is generated from `scripts/build_regular_options_chain_native_filter_relaxation_replay.py`. It replays frozen exact-candidate repair targets through predeclared diagnostic chain-native entry-filter relaxation scenarios.

## Summary

- Status: `chain_native_filter_relaxation_replay_readback`.
- Overall status: `chain_native_filter_relaxation_replay_candidates_found_diagnostic_only`.
- Target lanes: `1`.
- Target dates: `1`.
- Target signal candidates: `4`.
- Replay signal candidates: `4`.
- Scenario rows: `28`.
- Current selected entry spreads: `4`.
- Relaxed selected entry spreads: `24`.
- Entry quote demands: `0`.
- Entry quote demand tickers: `[]`.
- Scenario status counts: `{"selected_chain_native_entry_spread": 28}`.
- Selected relaxation scenario counts: `{"combined_broad_entry_relaxation": 4, "relax_debit_cap_only": 4, "relax_entry_liquidity_caps_only": 4, "relax_prior_quote_continuity_only": 4, "relax_width_cap_only": 4, "widen_dte_window_only": 4}`.
- Promotion ready: `False`.
- Blockers: `["exact_exit_pnl_replay_missing", "fresh_paper_holdout_required_before_policy_change", "single_date_target_overfit_risk"]`.
- Live policy change: `false`.

## Scenario Grid

| Scenario | Relaxed Filters | Description |
|---|---|---|
| `current_chain_native_filters` | [] | Current lane chain-native entry filters. |
| `relax_debit_cap_only` | ["max_debit_pct_of_width"] | Remove only the debit-percent-of-width cap. |
| `relax_width_cap_only` | ["spread_max_width_pct"] | Widen only the max spread-width percent cap. |
| `widen_dte_window_only` | ["chain_native_min_dte", "chain_native_max_dte"] | Widen only the entry DTE search window. |
| `relax_prior_quote_continuity_only` | ["chain_native_min_prior_quote_days", "chain_native_min_long_prior_quote_days", "chain_native_min_short_prior_quote_days"] | Remove prior quote-continuity requirements only. |
| `relax_entry_liquidity_caps_only` | ["chain_native_max_entry_leg_bid_ask_pct", "chain_native_min_entry_short_bid"] | Remove entry-leg bid/ask and short-bid caps only. |
| `combined_broad_entry_relaxation` | ["max_debit_pct_of_width", "spread_max_width_pct", "chain_native_min_dte", "chain_native_max_dte", "chain_native_min_prior_quote_days", "chain_native_min_long_prior_quote_days", "chain_native_min_short_prior_quote_days", "chain_native_max_entry_leg_bid_ask_pct", "chain_native_min_entry_short_bid"] | Broad diagnostic relaxation of debit, width, DTE, prior continuity, and entry-liquidity caps. |

## Target Replay Summary

| Target | Signals | Scenario Rows | Current Selected | Relaxed Selected | Entry Quote Demands | Status |
|---|---:|---:|---:|---:|---:|---|
| `regular_bearish_put_primary:2026-05-22` | 4 | 28 | 4 | 24 | 0 | `replayed` |

## Entry Quote Demands

| Lane | Date | Ticker | Option Type | Minute ET | Expiry Window | Missing Reason |
|---|---|---|---|---:|---|---|

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 4 | `build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates` | 24 | relaxed_entry_candidates_have_no_exact_exit_pnl |
| 5 | `validate_chain_native_relaxation_on_later_holdout` | 1 | single_date_target_overfit_risk |

## Boundary

This chain-native filter relaxation replay is read-only and diagnostic. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, change stops or sizing, lower exact OPRA/NBBO proof bars, or synthesize P&L from relaxed entry candidates.

