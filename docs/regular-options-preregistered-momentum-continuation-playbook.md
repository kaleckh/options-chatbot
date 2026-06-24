# Regular Options Preregistered Momentum Continuation Playbook

This report is generated from `scripts/build_regular_options_preregistered_momentum_continuation_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `preregistered_design_only`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Accepted profitability: `false`.
- Lane implementation performed: `false`.

## Concept

- Thesis: Strong index/QQQ momentum confirmed by breadth and low/mid VIX may support defined-risk call debit spreads, but only if the future implementation avoids tracked-winner overlap, quarantined lane reuse, and raw count aggregation.
- Structure: `defined_risk_call_debit_spreads_only`.
- Status: `preregistered_design_only`.

## Universe

| Symbol | Role | Proof Note |
| --- | --- | --- |
| `SPY` | `index_breadth_carrier` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `QQQ` | `index_breadth_carrier` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `IWM` | `index_breadth_carrier` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `DIA` | `index_breadth_carrier` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `AAPL` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `GOOGL` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `LLY` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `JNJ` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `XOM` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `CVX` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `COP` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |
| `NEM` | `liquid_confirming_constituent` | must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence |

## Causal Inputs

- SPY and QQQ trend/momentum confirmation must be present before candidate generation.
- breadth confirmation must be measured point-in-time, not inferred after outcomes.
- VIX state must be low-to-mid or otherwise explicitly bucketed before replay.
- candidate selection must not use future option outcomes, source marks, or realized P&L.

## Future Proof Path

- point-in-time candidate rows.
- trusted OPRA/NBBO exact-contract entry and policy-defined exit bid/ask evidence.
- side-aware debit-spread pricing.
- full denominator rows including no-pick, unpriced, zero-bid, and rejected rows.
- strict-new opportunity dedupe versus the 157-row clean base stack.
- positive point PF and positive net USD P&L after fees and execution-realistic pricing.
- stress PF and bootstrap PF lower-bound gates above the configured proof bars.
- simulated-forward and robust-search compatibility without protected-holdout consumption.
- fresh forward paper-shadow proof before promotion discussion.

## Explicit Exclusions

- tracked-winner retuning.
- raw overlapping aggregation.
- existing quarantined lane reopening.
- source marks as proof.
- midpoint, EOD, display-only, manual, last-trade, synthetic, stale, or lookahead evidence as proof.
- any scanner, stop, sizing, proof-bar, live-validation, auto-track, broker, quote-import, evidence-mutation, holdout-consumption, or promotion action.

## Forbidden Actions

- `do_not_implement_playbook`
- `do_not_create_scanner`
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
- `do_not_reuse_tracked_winner_retuning`
- `do_not_count_raw_overlapping_rows`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
