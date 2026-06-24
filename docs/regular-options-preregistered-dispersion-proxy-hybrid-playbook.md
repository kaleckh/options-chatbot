# Regular Options Preregistered Dispersion-Proxy Hybrid Playbook

This report is generated from `scripts/build_regular_options_preregistered_dispersion_proxy_hybrid_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, allow undefined-risk pair structures, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `index_constituent_dispersion_proxy_defined_risk_hybrid_v1`.
- Structure: `defined_risk_index_constituent_debit_credit_hybrid_pairs_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.
- Undefined or uncapped pair risk allowed: `false`.

## Concept

- Thesis: Point-in-time dispersion or concentration extremes may create a temporary mismatch between index option pricing and constituent option pricing. Fixed-rule defined-risk debit/credit hybrid pairs may capture relative constituent-versus-index movement only if future replay proves point-in-time inputs, all-leg side-aware OPRA/NBBO pricing, pair-level max-loss/collateral, and full-denominator net USD economics.
- Structure: `defined_risk_index_constituent_debit_credit_hybrid_pairs_only`.
- Status: `preregistered_design_only`.
- Historical research window target: `2024-06-01` through `2026-05-31` as of `2026-06-04`.

## Allowed Design Variants

- `long_constituent_debit_spread_short_index_credit_spread_dispersion_v1`
- `long_index_debit_spread_short_constituent_credit_spread_convergence_v1`
- `paired_constituent_basket_vs_index_defined_risk_proxy_v1`

## Universe

| Symbol | Role | Source Quality Note | Proof Note |
| --- | --- | --- | --- |
| `SPY` | `index_leg` | `` | index leg requires point-in-time dispersion input, exact OPRA/NBBO all-leg quotes, pair-level max-loss, and strict-new dedupe |
| `QQQ` | `index_leg` | `` | index leg requires point-in-time dispersion input, exact OPRA/NBBO all-leg quotes, pair-level max-loss, and strict-new dedupe |
| `AAPL` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `GOOGL` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `LLY` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `JNJ` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `XOM` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `CVX` | `constituent_leg` | `requires_source_quality_scope_or_zero_bid_tradability_check` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `COP` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |
| `NEM` | `constituent_leg` | `standard_existing_proof_import_universe_member` | constituent leg requires exact OPRA/NBBO all-leg quotes, earnings/event exclusion unless annotated, pair sizing, and source-quality checks |

## Frozen Design

### Entry Signal

- dispersion or concentration proxy must be known point-in-time before entry.
- allowed proxy families are fixed index-versus-constituent realized range dispersion, breadth/concentration proxy, or relative implied-vol proxy only when already available with tradable_after_time at or before entry.
- future dispersion, future constituent/index relative returns, future IV, future option outcomes, realized P&L, and protected-holdout data are forbidden inputs.

### Pair Universe

- index leg must be SPY or QQQ.
- constituent leg must be one of AAPL, GOOGL, LLY, JNJ, XOM, CVX, COP, or NEM.
- CVX must pass source-quality scope or zero-bid tradability handling before any future replay row can count.
- no earnings or scheduled single-name event window is allowed unless a separate point-in-time event annotation exists.

### Structure Selection

- future replay must select exactly one variant by a frozen rule before replay, not by best result.
- each pair must combine a defined-risk debit spread side with a defined-risk credit spread side or an explicitly capped constituent basket proxy.
- DTE bucket, strike spacing, fixed pair sizing, max-loss cap, max bid/ask width, and liquidity thresholds must be frozen before replay.
- all legs and quantities on both underlyings must have exact OPRA/NBBO bid/ask at entry.
- uncapped or undefined-risk pair exposure is forbidden.

### Exit Policy

- future replay must predefine time-exit, profit-take, loss-cut, assignment, expiration, and expiry-settlement handling for every leg and pair.
- open rows must remain open_waiting_policy_exit_or_expiry until a policy-defined exit or expiry condition fires.

## Side-Aware Pricing And Risk

- `debit_side_entry`: `sum(debit_long_leg_ask * quantity_bought) - sum(debit_short_leg_bid * quantity_sold)`.
- `credit_side_entry`: `sum(credit_short_leg_bid * quantity_sold) - sum(credit_long_leg_ask * quantity_bought)`.
- `pair_entry_cashflow`: `credit_side_entry - debit_side_entry`.
- `debit_side_exit_value`: `sum(debit_long_leg_bid * quantity_sold_to_close) - sum(debit_short_leg_ask * quantity_bought_to_close)`.
- `credit_side_exit_debit`: `sum(credit_short_leg_ask * quantity_bought_to_close) - sum(credit_long_leg_bid * quantity_sold_to_close)`.
- `pair_exit_value`: `debit_side_exit_value - credit_side_exit_debit`.
- `expiry_settlement_value`: `policy_defined_intrinsic_value_for_each_leg_and_quantity_at_expiration`.
- `pair_net_pnl_usd`: `(pair_exit_or_settlement_value + pair_entry_cashflow) * 100 - fees_and_slippage`.
- `pair_max_loss_usd`: `policy_defined_worst_case_pair_payoff_after_entry_cashflow_times_100_plus_fees`.
- `collateral_convention`: `future replay must derive pair_max_loss_usd and required collateral from all leg quantities, spread widths, net debit or credit, contract multiplier, fees, and slippage before any row can be exact`.

## Denominator Statuses

- `no_candidate`
- `rejected_dispersion_proxy_missing`
- `rejected_pair_universe_mismatch`
- `rejected_width_or_liquidity`
- `rejected_undefined_or_uncapped_risk`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `assignment_or_expiration_blocked`
- `exact_exit_captured`
- `expired_settled_exact`
- `missing_exit`

## Leakage Controls

- candidate generation must not read future dispersion, future constituent/index relative returns, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data.
- dispersion proxy, VIX bucket, symbols, pair sizing, strikes, DTE, and liquidity thresholds must be available point-in-time before candidate entry.
- future implementation must freeze all thresholds and the selected variant before replay.

## Required Future Replay Engine Support

- point-in-time dispersion or concentration proxy inputs.
- point-in-time VIX bucket and optional relative-volatility inputs.
- multi-underlying pair construction.
- side-aware all-leg debit and credit spread entry pricing.
- side-aware all-leg pair exit pricing and expiry settlement.
- pair-level max-loss and collateral convention.
- assignment and expiration classifier for every leg.
- contract multiplier, fees, slippage, collateral, and pair net USD P&L.
- trusted OPRA/NBBO quote availability for every leg and quantity.
- full denominator mapping including rejected pair-universe and undefined-risk rows.
- protected-holdout guard.
- strict-new dedupe versus the 157-row clean base stack.

## Falsification Plan

- reject if a future implementation cannot produce at least 200 historical exact pair rows or 30 latest-audit exact pair rows.
- reject if quote coverage is below 90 percent.
- reject if bootstrap PF lower bound is less than or equal to 1.0.
- reject if stress PF is below 1.0.
- reject if net USD P&L is less than or equal to 0.
- reject if material single-symbol, pair, month, date, signal-bucket, variant, or winner dependence drives profitability.
- reject if assignment, expiration, settlement, collateral, defined-risk cap, or max-loss status is unresolved.
- reject if any uncapped or undefined-risk exposure is required.
- reject if dispersion or concentration proxy provenance is unresolved.
- reject if CVX rows are counted without source-quality scope or zero-bid tradability handling.
- reject if any protected-holdout overlap is detected.
- reject if profitability depends on post-hoc exclusions or parameter mining.

## Explicit Exclusions

- scanner or strategy implementation in this slice.
- historical replay in this slice.
- quote import or evidence mutation.
- protected holdout use.
- live validation, auto-track, broker order, or promotion.
- uncapped or undefined-risk pair structures.
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
- `do_not_allow_undefined_or_uncapped_pair_structures`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
