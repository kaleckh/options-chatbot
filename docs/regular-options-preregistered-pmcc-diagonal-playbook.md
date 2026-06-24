# Regular Options Preregistered PMCC Diagonal Playbook

This report is generated from `scripts/build_regular_options_preregistered_pmcc_diagonal_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, allow naked short calls, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `low_mid_vix_index_pmcc_diagonal_income_v1`.
- Structure: `defined_risk_pmcc_style_call_diagonals_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.
- Undefined or uncapped short-call risk allowed: `false`.

## Concept

- Thesis: In low/mid VIX with persistent index or QQQ trend or range-bound grind, a long later-dated call financed by short nearer-dated calls may capture directional carry or term premium. This is only researchable if future replay proves point-in-time trend/regime inputs, diagonal side-aware OPRA/NBBO pricing, short-call roll/assignment/ex-dividend handling, max-loss/collateral, and full-denominator net USD economics.
- Structure: `defined_risk_pmcc_style_call_diagonals_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Universe

| Symbol | Initial | Future Extension | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `true` | `false` | future implementation must recheck long-dated and near-dated call quote depth, short-call roll/assignment/ex-dividend handling, max-loss/collateral, and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `true` | `false` | future implementation must recheck long-dated and near-dated call quote depth, short-call roll/assignment/ex-dividend handling, max-loss/collateral, and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `false` | `true` | future extension only after a separate proof-surface recheck for diagonal quote depth, roll liquidity, and denominator completeness |
| `DIA` | `false` | `true` | future extension only after a separate proof-surface recheck for diagonal quote depth, roll liquidity, and denominator completeness |

## Frozen Design

### Entry Regime

- trend or range-bound grind signal must be known point-in-time before entry.
- VIX low or mid bucket must be known point-in-time before entry.
- no single-name earnings dependency is allowed in the initial index-only design.
- underlying must be SPY or QQQ for the initial design.

### Structure Selection

- long call DTE bucket, short call DTE bucket, long-call moneyness or delta proxy, short-call moneyness or delta proxy, max debit, max width, max bid/ask width, and minimum liquidity thresholds must be frozen before replay.
- short call must be covered by the long later-dated call under a defined max-loss/collateral convention.
- naked or undefined-risk short-call exposure is forbidden.
- all entry, roll, and exit legs must have exact OPRA/NBBO bid/ask at the relevant timestamp.

### Roll And Exit Policy

- future replay must predefine short-call roll trigger, buy-to-close, sell-to-open, short-call expiry, long-call exit, profit-take, loss-cut, assignment, ex-dividend, and expiry-settlement handling.
- open rows must remain open_waiting_policy_roll_or_exit until a policy-defined roll, exit, or expiry condition fires.

## Side-Aware Pricing And Risk

- `entry_debit`: `long_call_ask - short_call_bid`.
- `roll_debit_or_credit`: `buy_to_close_short_call_ask - sell_to_open_next_short_call_bid`.
- `exit_value_with_open_short`: `long_call_bid - short_call_ask`.
- `exit_value_without_open_short`: `long_call_bid`.
- `expiry_settlement_value`: `policy_defined_intrinsic_value_for_long_call_and_short_call_assignment_or_expiration`.
- `net_pnl_usd`: `(exit_or_settlement_value - entry_debit - sum(roll_debits_or_credits)) * 100 - fees_and_slippage`.
- `max_loss_usd`: `policy_defined_long_call_debit_minus_short_call_credit_plus_roll_risk_and_assignment_adjustments_times_100_plus_fees`.
- `collateral_convention`: `future replay must derive max_loss_usd and required collateral from long/short call strikes, expiries, net debit, roll ledger, assignment/ex-dividend state, contract multiplier, fees, and slippage before any row can be exact`.

## Denominator Statuses

- `no_candidate`
- `rejected_trend_or_vix_bucket`
- `rejected_width_or_liquidity`
- `rejected_undefined_or_uncapped_short_call_risk`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_roll_or_exit`
- `short_call_roll_captured`
- `short_call_expired`
- `assignment_or_ex_dividend_blocked`
- `exact_exit_captured`
- `expired_settled_exact`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future trend, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- trend signal, VIX bucket, DTE, strikes, roll policy, exit policy, and liquidity thresholds must be available point-in-time before candidate entry.
- future implementation must freeze all thresholds and roll rules before replay.

## Required Future Replay Engine Support

- point-in-time trend and VIX inputs.
- diagonal side-aware entry pricing.
- short-call roll ledger with buy-to-close and sell-to-open bid/ask pricing.
- side-aware exit pricing and expiry settlement.
- short-call assignment and ex-dividend classifier.
- long-call expiration and settlement classifier.
- max-loss and collateral convention.
- contract multiplier, fees, slippage, roll costs, and net USD P&L.
- trusted OPRA/NBBO quote availability for entry, roll, and exit legs.
- full denominator mapping including rejected undefined-risk short-call rows.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-ticker, month, date, roll-state, or winner dependence drives profitability.
- reject if roll, assignment, ex-dividend, expiration, settlement, collateral, or max-loss status is unresolved.
- reject if any naked or undefined-risk short-call exposure is required.
- reject if any protected-holdout overlap is detected.
- reject if profitability depends on post-hoc exclusions or parameter mining.

## Explicit Exclusions

- scanner or strategy implementation in this slice.
- historical replay in this slice.
- quote import or evidence mutation.
- protected holdout use.
- live validation, auto-track, broker order, or promotion.
- naked or undefined-risk short-call exposure.
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
- `do_not_allow_undefined_risk_naked_short_calls`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
