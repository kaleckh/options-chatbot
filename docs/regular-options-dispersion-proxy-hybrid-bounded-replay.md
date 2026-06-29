# Regular Options Dispersion-Proxy Hybrid Bounded Replay

This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_bounded_replay.py`. It is read-only research. It uses only existing local artifacts and trusted quote rows if available; it does not import quotes, mutate evidence stores, append cohort rows, change scanner policy, enable live validation or auto-track, submit broker orders, consume protected holdout, lower proof bars, or promote any lane.

## Summary

- Status: `blocked_dispersion_proxy_hybrid_bounded_replay`.
- Denominator rows: `494`.
- Priced exact rows: `0`.
- Strict-new exact completed rows: `0`.
- Quote coverage pct: `0.0`.
- Net P&L USD: `0.0`.
- Profit factor: `None`.
- PF lower bound: `None`.
- Smallest next blocker: `missing_dispersion_pair_candidate_rows`.

## Denominator Status Counts

- `blocked_missing_pair_contract_selection_surface`: `494`.

## Blockers

- `missing_dispersion_pair_candidate_rows`.
- `bounded_replay_rows_blocked`.

## Current Evidence Boundary

- The bounded replay is a research pricing harness, not accepted profitability.
- Priced rows remain historical research rows unless independent holdout, max-loss/collateral, slippage/stress, statistical, and strict forward proof gates are satisfied.
- Historical proxy rows are not forward proof, promotion evidence, or live/broker/autotrack permission.

## Forbidden Actions

- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_append_forward_cohort_rows`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_use_midpoint_last_eod_manual_synthetic_or_lookahead_prices`
