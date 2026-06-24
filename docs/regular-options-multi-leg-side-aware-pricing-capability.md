# Regular Options Multi-Leg Side-Aware Pricing Capability

This generated artifact is a read-only, research-only capability check. It resolves fixture legs from the local `options_history.db` using bid/ask only and never treats fixture output as profitability, historical replay, or forward proof.

## Summary

- Status: `multi_leg_side_aware_pricing_capability_available`.
- Accepted profitability: `false`.
- Fixture source proof eligible: `false`.
- Options DB read-only: `true`.
- Resolved fixtures: `1` of `1`.

## Structure Support

| Structure | Status | Resolved | Blockers |
| --- | --- | --- | --- |
| `ratio_backspread_bounded` | `available` | `1` / `1` | - |

## Pricing Formula

- `entry`: long/open legs use ask; short/open legs use bid; net_entry_cashflow_per_share = sum(short_bid * qty) - sum(long_ask * qty)
- `exit`: long/close legs use bid; short/close legs use ask; net_exit_cashflow_per_share = sum(long_bid * qty) - sum(short_ask * qty)
- `net_pnl_usd_after_costs`: (entry_net_cashflow_per_share + exit_net_cashflow_per_share) * 100 - fees_usd - slippage_usd
- `forbidden_fallbacks`: ['display', 'eod', 'last', 'last_trade', 'lookahead', 'manual', 'mark', 'mid', 'midpoint', 'model', 'source_mark', 'synthetic']

## Denominator Status Contract

- `no_candidate`
- `rejected_flow_input_missing`
- `rejected_vix_bucket`
- `rejected_width_or_liquidity`
- `rejected_undefined_risk`
- `missing_leg_quote`
- `zero_bid_or_untradable`
- `crossed_or_invalid_quote`
- `stale_or_untrusted_quote`
- `exact_entry_captured`
- `open_waiting_policy_exit_or_expiry`
- `assignment_or_expiration_blocked`
- `exact_exit_captured`
- `missing_exit`
- `protected_holdout_blocked`
- `malformed_candidate`

## Blockers

- None.

## Forbidden Actions

- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_run_or_change_production_scanners`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_fetch_external_market_data`
- `do_not_mutate_options_history_db`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort_rows`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_allow_undefined_or_naked_ratio_backspread_risk`
- `do_not_count_fixture_rows_as_profitability_or_forward_proof`
