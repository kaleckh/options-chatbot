# Regular Options Open-Risk Resolution Plan

This report is generated from `scripts/build_regular_options_open_risk_resolution_plan.py`. It is a read-only row plan for resolving open-risk blockers before monthly profitability, live-entry, or promotion decisions.

## Summary

- Status: `open_risk_resolution_plan_ready_blocked_for_market_window`.
- Source open-risk status: `open_risk_governor_blocked`.
- Live entry allowed: `False`.
- Live exact negative IDs: `[537]`.
- Open rows / negative rows: `1` / `1`.
- Avg / median open P&L: `-33.25` / `-33.25`.
- Plan rows: `1`.
- Live exact plan rows: `1`.
- Display-only SELL rows: `0`.
- Live policy change: `false`.

## Resolution Rows

| Priority | ID | Ticker | Lane | Class | Action | Status | Evidence | P&L | Warning |
|---:|---:|---|---|---|---|---|---|---:|---|
| 0 | 537 | QQQ | volatility_expansion_observation | live_exact_tracked | `refresh_live_exact_negative_open_position_review` | `market_window_required_live_exact_negative_review` | fresh_executable_open_position_review,open_risk_governor_rerun | -33.2543 |  |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 0 | `execute_open_risk_resolution_review_plan` | 1 | open_risk_rows_need_fresh_executable_review_or_monitor_decision |

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, auto-close display-only marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote open-risk rows to production proof.

