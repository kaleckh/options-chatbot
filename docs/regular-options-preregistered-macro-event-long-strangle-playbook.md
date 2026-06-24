# Regular Options Preregistered Macro Event Long Strangle Playbook

This report is generated from `scripts/build_regular_options_preregistered_macro_event_long_strangle_playbook.py`. It defines one read-only causal playbook design only. It does not implement an event calendar, scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `low_mid_vix_macro_event_long_strangle_v1`.
- Structure: `defined_risk_long_straddles_or_strangles_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.

## Concept

- Thesis: In low/mid VIX, scheduled macro events may underprice short-window index movement or post-event drift. Fixed-rule long straddles or strangles may capture convexity only if future replay proves point-in-time event calendars, exact all-leg OPRA/NBBO bid/ask pricing, policy-defined exits or expiry settlement, and full-denominator net USD economics.
- Structure: `defined_risk_long_straddles_or_strangles_only`.
- Status: `preregistered_design_only`.
- Event calendar implemented in this slice: `false`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Event Categories

- `fomc_rate_decision`
- `fomc_minutes`
- `cpi`
- `pce`
- `nonfarm_payrolls`
- `scheduled_fed_chair_testimony`

## Universe

| Symbol | Initial | Future Extension | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `true` | `false` | future implementation must recheck event-calendar availability, all-leg liquidity, expiry settlement, and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `true` | `false` | future implementation must recheck event-calendar availability, all-leg liquidity, expiry settlement, and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `false` | `true` | future extension only after a separate proof-surface recheck for event coverage and all-leg quote quality |
| `DIA` | `false` | `true` | future extension only after a separate proof-surface recheck for event coverage and all-leg quote quality |

## Frozen Design

### Event Universe

- event timestamp must be known point-in-time before entry.
- event category must be one of the preregistered categories.
- no event outcome, realized move, realized volatility, future IV, option return, or P&L may be read during candidate generation.
- this slice does not implement an event calendar.

### Entry Regime

- VIX low/mid bucket must be known point-in-time before entry.
- underlying must be SPY or QQQ for the initial design.
- IWM and DIA are future extensions only after proof-surface recheck.
- entry window must be frozen before replay, such as previous close or event-day morning.

### Structure Selection

- future replay must choose straddle versus strangle by a frozen rule before replay.
- moneyness, strike distance, DTE bucket, maximum debit, max bid/ask width, and minimum liquidity thresholds must be frozen before replay.
- all legs must have exact OPRA/NBBO bid/ask at the candidate entry timestamp.

### Exit Policy

- future replay must predefine same-day close, next-day close, time-exit, profit-take, loss-cut, and expiry-settlement handling.
- open rows must remain open_waiting_policy_exit_or_expiry until a policy-defined exit or expiry condition fires.

## Side-Aware Pricing

- `entry_debit`: `sum(long_leg_ask * quantity_bought)`.
- `exit_value`: `sum(long_leg_bid * quantity_sold_to_close)`.
- `expiry_settlement_value`: `policy_defined_intrinsic_value_for_each_long_leg_at_expiration`.
- `net_pnl_usd`: `(exit_or_settlement_value - entry_debit) * 100 - fees_and_slippage`.
- `max_loss_usd`: `entry_debit * 100 + fees_and_slippage`.

## Denominator Statuses

- `no_event`
- `no_candidate`
- `rejected_event_calendar_missing`
- `rejected_vix_bucket`
- `rejected_width_or_liquidity`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `exact_exit_captured`
- `expired_settled_exact`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future event outcomes, realized moves, future realized volatility, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- event timestamp and event category must be available point-in-time before candidate entry.
- future implementation must freeze all thresholds before replay.

## Required Future Replay Engine Support

- point-in-time macro event calendar for all preregistered event categories.
- multi-leg side-aware long-option bid/ask entry pricing.
- multi-leg side-aware exit pricing and expiry settlement.
- contract multiplier, fees, slippage, and net USD P&L.
- point-in-time VIX bucket inputs.
- trusted OPRA/NBBO quote availability for every leg.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.
- full denominator output including no-event, rejected, missing, zero-bid, open, exact-exit, expired-settled, and missing-exit rows.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-ticker, event-category, month, date, or winner dependence drives profitability.
- reject if event-calendar provenance, expiry settlement, or exit status is unresolved.
- reject if any protected-holdout overlap is detected.
- reject if profitability depends on post-hoc exclusions or parameter mining.

## Explicit Exclusions

- event-calendar implementation in this slice.
- implementation or replay in this slice.
- scanner policy or strategy logic changes.
- quote import or evidence mutation.
- protected holdout use.
- live validation, auto-track, broker order, or promotion.
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
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
