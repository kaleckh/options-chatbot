# Regular Options Preregistered Skew Broken Wing Playbook

This report is generated from `scripts/build_regular_options_preregistered_skew_broken_wing_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `low_mid_vix_index_skew_broken_wing_put_fly_v1`.
- Structure: `defined_risk_broken_wing_put_butterflies_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.

## Concept

- Thesis: In low/mid VIX, elevated downside skew or put-wing richness may let fixed-rule broken-wing put butterflies buy asymmetric defined-risk exposure to moderate pullbacks or skew normalization, but only if future replay proves all-leg side-aware pricing, expiration settlement, assignment handling, and full-denominator economics.
- Structure: `defined_risk_broken_wing_put_butterflies_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Universe

| Symbol | Initial | Future Extension | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `true` | `false` | future implementation must recheck downside-skew inputs, all-leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `true` | `false` | future implementation must recheck downside-skew inputs, all-leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `true` | `false` | future implementation must recheck downside-skew inputs, all-leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `DIA` | `true` | `false` | future implementation must recheck downside-skew inputs, all-leg liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `sector_etfs` | `false` | `true` | future extension only; requires a separate proof-surface recheck before inclusion |
| `single_names` | `false` | `true` | future extension only; requires a separate proof-surface recheck before inclusion |

## Frozen Design

### Entry Regime

- VIX low/mid bucket must be known point-in-time before entry.
- underlying must be SPY, QQQ, IWM, or DIA for the initial design.
- index trend must not be in a crash regime before entry.
- downside skew or put-wing richness proxy must be available point-in-time before entry.

### Structure Selection

- DTE bucket must be fixed before replay.
- lower, middle, and upper put strikes must use fixed spacing, delta, or moneyness rules frozen before replay.
- broken wing width and max debit or minimum credit threshold must be frozen before replay.
- max bid/ask width and liquidity thresholds must be frozen before replay.
- all legs must have exact OPRA/NBBO bid/ask at the candidate entry timestamp.

### Exit Policy

- future replay must predefine profit-take, loss-cut, time-exit, assignment, expiration, and expiry-settlement handling.
- open rows must remain open_waiting_policy_exit_or_expiry until a policy-defined exit or expiry condition fires.

## Side-Aware Pricing

- `entry_value`: `sum(long_leg_ask * quantity_bought) - sum(short_leg_bid * quantity_sold)`.
- `exit_value`: `sum(long_leg_bid * quantity_sold_to_close) - sum(short_leg_ask * quantity_bought_to_close)`.
- `expiry_settlement_value`: `policy_defined_intrinsic_value_for_each_leg_at_expiration`.
- `net_pnl_usd`: `(exit_or_settlement_value - entry_value) * 100 - fees_and_slippage`.
- `max_loss_usd`: `policy_defined_broken_wing_max_loss_after_entry_value_and_widths_plus_fees`.

## Denominator Statuses

- `no_candidate`
- `rejected_skew_or_regime`
- `rejected_width_or_liquidity`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `assignment_or_expiration_blocked`
- `exact_exit_captured`
- `expired_settled_exact`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future skew, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- skew inputs must be tradable point-in-time before candidate entry.
- future implementation must freeze all thresholds before replay.

## Required Future Replay Engine Support

- multi-leg broken-wing side-aware bid/ask entry pricing.
- multi-leg side-aware exit pricing and expiry settlement.
- assignment and expiration classifier.
- contract multiplier, fees, slippage, and net USD P&L.
- point-in-time VIX and downside-skew inputs.
- trusted OPRA/NBBO quote availability for every leg.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.
- full denominator output including no-candidate, rejected, missing, zero-bid, open, assignment, exact-exit, expired-settled, and missing-exit rows.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-ticker, month, date, or winner dependence drives profitability.
- reject if assignment, expiration, or expiry-settlement status is unresolved.
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
