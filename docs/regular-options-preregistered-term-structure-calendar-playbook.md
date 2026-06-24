# Regular Options Preregistered Term Structure Calendar Playbook

This report is generated from `scripts/build_regular_options_preregistered_term_structure_calendar_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `low_mid_vix_index_calendar_term_structure_dislocation_v1`.
- Structure: `defined_risk_calendar_or_diagonal_debit_spreads_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.

## Concept

- Thesis: In low/mid VIX, eventless index ETF term-structure dislocations may support buying a later-dated option and selling a nearer-dated option with fixed strike, delta, or moneyness rules, but only if future replay proves side-aware entry, side-aware exit or expiry handling, short-leg assignment risk, and full-denominator economics.
- Structure: `defined_risk_calendar_or_diagonal_debit_spreads_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Universe

| Symbol | Initial | Future Extension | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `true` | `false` | future implementation must recheck term-structure inputs, multi-expiry leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `true` | `false` | future implementation must recheck term-structure inputs, multi-expiry leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `false` | `true` | future extension only; requires a separate proof-surface recheck before inclusion |
| `DIA` | `false` | `true` | future extension only; requires a separate proof-surface recheck before inclusion |

## Frozen Design

### Entry Regime

- VIX low/mid bucket must be known point-in-time before entry.
- underlying must be SPY or QQQ for the initial design.
- no single-name earnings/event window is allowed in the initial design.
- index trend must not be in a crash regime before entry.

### Term Structure Selection

- front and back expirations must use fixed spacing frozen before replay.
- long back-month option and short front-month option must use fixed strike, delta, or moneyness rules frozen before replay.
- minimum term-structure dislocation, max spread width/debit, max bid/ask width, and liquidity thresholds must be frozen before replay.
- all legs must have exact OPRA/NBBO bid/ask at the candidate entry timestamp.

### Exit Policy

- future replay must predefine profit-take, loss-cut, time-exit, front-leg expiry, roll, assignment, and expiration handling.
- open rows must remain open_waiting_policy_exit_or_expiry until a policy-defined exit or expiry condition fires.

## Side-Aware Pricing

- `entry_debit`: `long_back_month_ask - short_front_month_bid`.
- `exit_debit_or_value`: `long_back_month_bid - short_front_month_ask`.
- `front_leg_expiry_value`: `policy_defined_intrinsic_or_settlement_value_for_short_front_leg`.
- `net_pnl_usd`: `(exit_debit_or_value - entry_debit) * 100 - fees_and_slippage`.
- `max_loss_usd`: `entry_debit * 100 + fees_and_slippage unless future replay proves a stricter defined-risk convention`.

## Denominator Statuses

- `no_candidate`
- `rejected_liquidity`
- `rejected_term_structure`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `front_leg_expired`
- `assignment_or_expiration_blocked`
- `exact_exit_captured`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- term-structure inputs must be tradable point-in-time before candidate entry.
- future implementation must freeze all thresholds before replay.

## Required Future Replay Engine Support

- calendar/diagonal side-aware bid/ask entry pricing.
- calendar/diagonal side-aware exit pricing plus front-leg expiry or roll handling.
- short-leg assignment and expiration classification.
- contract multiplier, fees, slippage, and net USD P&L.
- point-in-time VIX and term-structure inputs.
- trusted OPRA/NBBO quote availability for every leg.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.
- full denominator output including no-candidate, rejected, missing, zero-bid, open, front-expired, assignment, exact-exit, and missing-exit rows.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-ticker, month, date, or winner dependence drives profitability.
- reject if assignment, expiration, roll, or front-leg settlement status is unresolved.
- reject if any protected-holdout overlap is detected.
- reject if profitability depends on post-hoc exclusions or parameter mining.

## Explicit Exclusions

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
