# Regular Options Open-Risk Resolution Plan

This report is generated from `scripts/build_regular_options_open_risk_resolution_plan.py`. It is a read-only row plan for resolving open-risk blockers before monthly profitability, live-entry, or promotion decisions.

## Summary

- Status: `open_risk_resolution_plan_ready_blocked_for_market_window`.
- Source open-risk status: `open_risk_governor_blocked`.
- Live entry allowed: `False`.
- Live exact negative IDs: `[537]`.
- Open rows / negative rows: `12` / `10`.
- Avg / median open P&L: `-44.14` / `-47.58`.
- Plan rows: `2`.
- Live exact plan rows: `1`.
- Display-only SELL rows: `1`.
- Live policy change: `false`.

## Resolution Rows

| Priority | ID | Ticker | Lane | Class | Action | Status | Evidence | P&L | Warning |
|---:|---:|---|---|---|---|---|---|---:|---|
| 0 | 537 | QQQ | volatility_expansion_observation | live_exact_tracked | `refresh_live_exact_negative_open_position_review` | `fresh_quote_monitor_or_close_decision_required` | fresh_executable_open_position_review,open_risk_governor_rerun,monitor_or_close_decision_under_exit_rules | -58.2639 |  |
| 1 | 104 | SBUX | bullish_pullback_observation | main_zero_pick_research_backfill | `refresh_display_only_sell_executable_review` | `market_window_required_display_only_sell_review` | fresh_executable_open_position_review,spread_bid_ask_exact_or_explicit_unpriced_review |  | Using display-only spread marks because one or both legs are missing a live executable bid/ask quote. |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 0 | `execute_open_risk_resolution_review_plan` | 2 | open_risk_rows_need_fresh_executable_review_or_monitor_decision |

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, auto-close display-only marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote open-risk rows to production proof.

