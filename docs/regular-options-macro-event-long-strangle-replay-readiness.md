# Regular Options Macro-Event Long Strangle Replay Readiness

This report is generated from `scripts/build_regular_options_macro_event_long_strangle_replay_readiness.py`. It is a read-only readiness audit for the preregistered macro-event long straddle/strangle concept. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner or strategy logic, consume protected holdout, or promote any lane.

## Summary

- Status: `blocked_macro_event_long_strangle_replay_readiness`.
- Concept: `low_mid_vix_macro_event_long_strangle_v1`.
- Structure: `defined_risk_long_straddles_or_strangles_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Readiness audit performed: `true`.

## Readiness

- Event calendar: `blocked`.
- VIX bucket: `ready`.
- Protected holdout guard: `ready`.

## Blockers

- `macro_event_calendar_source_missing`

## Required Event Categories

- `fomc_rate_decision`
- `fomc_minutes`
- `cpi`
- `pce`
- `nonfarm_payrolls`
- `scheduled_fed_chair_testimony`

## Proof Formulas

- `entry_debit`: call_ask + put_ask for one straddle/strangle unit, using exact OPRA/NBBO ask on each long leg
- `exit_value`: call_bid + put_bid for one straddle/strangle unit, using exact OPRA/NBBO bid on each long leg
- `expiry_settlement_value`: max(0, underlying_settlement - call_strike) + max(0, put_strike - underlying_settlement)
- `net_pnl_usd`: (exit_or_settlement_value - entry_debit) * 100 - fees_and_slippage

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
- `protected_holdout_blocked`
- `duplicate_strict_new_identity`
- `replay_gate_blocked`

## Strict-New Identity

- `concept_id`
- `event_id`
- `event_category`
- `event_timestamp_utc`
- `underlying`
- `entry_timestamp_utc`
- `expiration`
- `call_occ_symbol`
- `put_occ_symbol`
- `call_strike`
- `put_strike`
- `side`
- `quantity_ratio`
- `quote_timestamp_basis`

## Smallest Next Slice

{
  "blocker": "macro_event_calendar_source_missing",
  "smallest_future_codex_slice": "Clear exactly this named blocker with a read-only artifact before replay."
}

## Forbidden Actions

- `broker_orders`
- `live_validation`
- `auto_track`
- `scanner_release`
- `strategy_logic_change`
- `stop_or_sizing_change`
- `proof_bar_relaxation`
- `quote_import`
- `evidence_database_mutation`
- `protected_holdout_consumption`
- `promotion`
- `historical_rows_as_forward_proof`
- `source_midpoint_eod_stale_display_manual_last_model_synthetic_or_lookahead_proof`
