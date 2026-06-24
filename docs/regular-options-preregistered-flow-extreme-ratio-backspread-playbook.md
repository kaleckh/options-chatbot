# Regular Options Preregistered Flow-Extreme Ratio/Backspread Playbook

This report is generated from `scripts/build_regular_options_preregistered_flow_extreme_ratio_backspread_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, allow undefined-risk spreads, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `index_flow_extreme_mean_reversion_ratio_backspread_v1`.
- Structure: `defined_risk_ratio_spreads_or_backspreads_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.
- Undefined risk allowed: `false`.

## Concept

- Thesis: Point-in-time SPY/QQQ flow or overextension extremes may create short-lived snapback mean-reversion or convex continuation opportunities. Fixed-rule defined-risk ratio spreads or backspreads may capture that dislocation only if future replay proves point-in-time inputs, all-leg side-aware OPRA/NBBO pricing, strict max-loss/collateral accounting, assignment/expiration handling, and full denominator net USD economics.
- Structure: `defined_risk_ratio_spreads_or_backspreads_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Allowed Design Variants

- `call_backspread_for_upside_flow_extreme`
- `put_backspread_for_downside_flow_extreme`
- `capped_ratio_spread_for_snapback_mean_reversion`

## Universe

| Symbol | Initial | Future Extension | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `true` | `false` | future implementation must recheck point-in-time overextension inputs, VIX bucket, all-leg OPRA/NBBO quote quality, defined-risk cap, max-loss, assignment, expiration, and strict-new dedupe |
| `QQQ` | `true` | `false` | future implementation must recheck point-in-time overextension inputs, VIX bucket, all-leg OPRA/NBBO quote quality, defined-risk cap, max-loss, assignment, expiration, and strict-new dedupe |
| `IWM` | `false` | `true` | future extension only after a separate proof-surface recheck for flow proxy availability, quote quality, and denominator completeness |
| `DIA` | `false` | `true` | future extension only after a separate proof-surface recheck for flow proxy availability, quote quality, and denominator completeness |

## Frozen Design

### Entry Signal

- point-in-time overextension signal must be known before entry.
- allowed proxy families are a fixed z-score of index return versus recent realized range, or an existing repo breadth/flow proxy with tradable_after_time at or before candidate entry.
- future option outcome, realized P&L, future return, future flow, future IV, and protected-holdout data are forbidden inputs.

### Entry Regime

- VIX low or mid bucket must be known point-in-time before entry.
- compressed realized-volatility context may be used only if computed point-in-time before entry.
- underlying must be SPY or QQQ for the initial design.
- IWM and DIA are future extensions only after proof-surface recheck.

### Structure Selection

- future replay must select exactly one variant by a frozen rule before replay, not by best result.
- allowed variants are call backspread for upside flow extreme, put backspread for downside flow extreme, and capped ratio spread for snapback mean reversion.
- DTE bucket, strike spacing, fixed ratio, extra long wing or cap, maximum net debit or minimum net credit, max bid/ask width, and liquidity thresholds must be frozen before replay.
- all legs and all quantities must have exact OPRA/NBBO bid/ask at the candidate entry timestamp.
- uncapped or undefined-risk naked ratio spreads are forbidden.

### Exit Policy

- future replay must predefine time-exit, profit-take, loss-cut, assignment, expiration, and expiry-settlement handling.
- open rows must remain open_waiting_policy_exit_or_expiry until a policy-defined exit or expiry condition fires.

## Side-Aware Pricing And Risk

- `entry_net_premium`: `sum(long_leg_ask * long_quantity_bought) - sum(short_leg_bid * short_quantity_sold)`.
- `entry_cashflow_sign`: `positive entry_net_premium is net debit; negative entry_net_premium is net credit`.
- `exit_net_value`: `sum(long_leg_bid * long_quantity_sold_to_close) - sum(short_leg_ask * short_quantity_bought_to_close)`.
- `expiry_settlement_value`: `policy_defined_intrinsic_value_for_each_leg_and_quantity_at_expiration`.
- `net_pnl_usd`: `(exit_or_settlement_value - entry_net_premium) * 100 - fees_and_slippage`.
- `max_loss_usd`: `policy_defined_defined_risk_cap_or_worst_case_payoff_minus_entry_cashflow_times_100_plus_fees`.
- `collateral_convention`: `future replay must derive max_loss_usd and required collateral from all leg quantities, wing/cap width, net debit or credit, contract multiplier, fees, and slippage before any row can be exact`.

## Denominator Statuses

- `no_candidate`
- `rejected_overextension_signal_missing`
- `rejected_vix_bucket`
- `rejected_width_or_liquidity`
- `rejected_undefined_risk`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `assignment_or_expiration_blocked`
- `exact_exit_captured`
- `expired_settled_exact`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future flow, future realized move, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- overextension signal, flow proxy, VIX bucket, realized-volatility context, strikes, ratios, DTE, and liquidity thresholds must be available point-in-time before candidate entry.
- future implementation must freeze all thresholds and the selected variant before replay.

## Required Future Replay Engine Support

- point-in-time overextension or flow proxy inputs.
- point-in-time VIX bucket and optional realized-volatility compression inputs.
- multi-leg side-aware ratio-spread and backspread bid/ask entry pricing.
- multi-leg side-aware exit pricing and expiry settlement.
- defined-risk cap or extra-wing max-loss convention.
- assignment and expiration classifier.
- contract multiplier, fees, slippage, collateral, and net USD P&L.
- trusted OPRA/NBBO quote availability for every leg and quantity.
- full denominator mapping including rejected undefined-risk rows.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-ticker, month, date, signal-bucket, variant, or winner dependence drives profitability.
- reject if assignment, expiration, settlement, collateral, defined-risk cap, or max-loss status is unresolved.
- reject if any undefined-risk exposure is required.
- reject if overextension or flow proxy provenance is unresolved.
- reject if any protected-holdout overlap is detected.
- reject if profitability depends on post-hoc exclusions or parameter mining.

## Explicit Exclusions

- scanner or strategy implementation in this slice.
- historical replay in this slice.
- quote import or evidence mutation.
- protected holdout use.
- live validation, auto-track, broker order, or promotion.
- uncapped or undefined-risk naked ratio spreads.
- source marks, midpoint, EOD, display-only, stale, last-trade, manual, synthetic, lookahead, or percent-only values as proof.

## Forbidden Actions

- `do_not_implement_scanner_or_playbook_logic`
- `do_not_run_replay`
- `do_not_create_trades`
- `do_not_submit_broker_orders`
- `do_not_enable_auto_track`
- `do_not_enable_live_validation`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_databases`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_allow_undefined_risk_naked_ratio_spreads`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
