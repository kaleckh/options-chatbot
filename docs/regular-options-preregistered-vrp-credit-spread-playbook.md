# Regular Options Preregistered VRP Credit Spread Playbook

This report is generated from `scripts/build_regular_options_preregistered_vrp_credit_spread_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `low_mid_vix_index_put_credit_spread_vrp_v1`.
- Structure: `defined_risk_put_credit_spreads_only`.
- Accepted profitability: `false`.
- Lane implementation performed: `false`.

## Concept

- Thesis: In low/mid VIX, liquid index put-credit verticals may harvest volatility risk premium and skew while using defined max loss, but the idea is only useful if future replay proves side-aware credit entry, side-aware debit exit, assignment/expiration handling, and full-denominator economics.
- Structure: `defined_risk_put_credit_spreads_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Universe

| Symbol | Role | Proof Note |
| --- | --- | --- |
| `SPY` | `index_credit_spread_underlying` | future implementation must recheck point-in-time option-chain liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `index_credit_spread_underlying` | future implementation must recheck point-in-time option-chain liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `index_credit_spread_underlying` | future implementation must recheck point-in-time option-chain liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |
| `DIA` | `index_credit_spread_underlying` | future implementation must recheck point-in-time option-chain liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence |

## Frozen Design

### Entry Regime

- VIX low/mid bucket must be known point-in-time before entry.
- index trend must not be in a crash regime before entry.
- underlying must be one of SPY, QQQ, IWM, DIA.

### Contract Selection

- short put is out-of-the-money by a fixed moneyness or delta proxy frozen before replay.
- long put is farther out-of-the-money than the short put.
- spread width, minimum credit, maximum bid/ask width, and liquidity thresholds must be frozen before replay.
- both legs must have exact OPRA/NBBO bid/ask at the candidate entry timestamp.

### Exit Policy

- future replay must predefine profit-take, loss-cut, time-exit, assignment, and expiration handling.
- open rows must remain open_waiting_policy_exit until a policy-defined exit condition fires.

## Side-Aware Pricing

- `entry_credit`: `short_put_bid - long_put_ask`.
- `exit_debit`: `short_put_ask - long_put_bid`.
- `net_pnl_usd`: `(entry_credit - exit_debit) * 100 - fees_and_slippage`.
- `max_loss_usd`: `(spread_width - entry_credit) * 100 + fees_and_slippage`.

## Denominator Statuses

- `no_candidate`
- `rejected_width_or_credit`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit`
- `exact_exit_captured`
- `assignment_or_expiration_blocked`
- `missing_exit`

## Required Future Replay Engine Support

- credit-spread side-aware bid/ask pricing.
- assignment and expiration classification.
- margin and max-loss convention.
- policy-defined exit handling.
- strict-new dedupe versus the 157-row clean base stack.
- full denominator output including rejected, missing, zero-bid, open, exact-exit, assignment, and expiration rows.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows.
- reject if quote coverage is below 90 percent.
- reject if PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is negative.
- reject if material single-ticker, month, date, or winner dependence drives profitability.
- reject if assignment, expiration, margin, or max-loss accounting is unresolved.
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
