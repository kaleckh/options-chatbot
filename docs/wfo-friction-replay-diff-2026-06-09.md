# WFO Friction Replay Diff - 2026-06-09

Purpose: Sprint 2 evidence for charging friction inside the WFO simulator.

Method: deterministic one-sleeve SPY-like 120-business-day grid through `wfo_optimizer._simulate_window`.
The grid compared nine stop/target pairs with the same entry settings. The "before" run used zero
commission and zero slippage. The "after" run used the new cost model: 1.0% entry slippage, 1.0%
exit slippage, and $0.65/contract commission.

Selection key for this diagnostic was `(profit_factor, avg_pnl_pct, n_trades)`. This is not a
promotion claim; it is a narrow before/after cost-treatment check.

| Run | Selected params | Trades | PF | Net P&L USD |
|---|---:|---:|---:|---:|
| Before friction | stop 40%, target 50% | 19 | 0.000274 | -218.92 |
| After friction | stop 25%, target 50% | 29 | 0.0 | -343.46 |

Observed effect: applying friction changed the selected parameter pair and pushed every tested
variant to effectively zero PF. The chosen after-friction branch was not profitable; it was merely
the least-bad result under the diagnostic ranking. This confirms prior no-cost tuning can select a
different parameter set than the executable-cost simulator.

Implementation note: `_simulate_window` now records `gross_pnl_pct`, `net_pnl_pct`, `gross_pnl_usd`,
`net_pnl_usd`, entry/exit slippage, fee totals, and `profit_factor_basis=net_pnl_usd`, matching the
truth lane's executable-cost treatment.
