# Regular Options Bullish-Pullback Layer Execution-Safety Audit

Status: `blocked_execution_safety_preflight`.

This is a read-only preflight for future paper-shadow harness work. It does not collect market evidence, create trades, submit broker orders, import quotes, mutate evidence stores, change scanner policy, change strategy/stops/sizing/proof bars, enable live validation, enable auto-track, consume protected holdout, append forward cohort rows, or promote a lane.

## Selected Harness

- Layer: `layer_4_clean_exact`.
- Variant: `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1`.
- Source run: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`.
- Metrics: `{"candidate_trade_count": 129, "exact_trade_count": 129, "profit_factor": 2.2, "quote_coverage_pct": 100.0, "stress_5pct_per_side_profit_factor": 1.67, "unpriced_trade_count": 0}`.

## Preflight Counts

- `total_selected_rows`: `129`.
- `rows_with_parsed_leg_identity`: `129`.
- `rows_with_source_run_leg_level_entry_bid_ask`: `0`.
- `rows_with_source_run_leg_level_exit_bid_ask`: `0`.
- `rows_with_existing_trusted_entry_leg_bid_ask`: `129`.
- `rows_with_existing_trusted_exit_leg_bid_ask`: `126`.
- `rows_with_leg_level_entry_bid_ask`: `129`.
- `rows_with_leg_level_exit_bid_ask`: `126`.
- `rows_with_side_aware_entry_price`: `129`.
- `rows_with_side_aware_exit_price`: `126`.
- `rows_with_side_aware_entry_price_matching_source_run`: `0`.
- `rows_with_side_aware_exit_price_matching_source_run`: `10`.
- `rows_with_side_aware_price_mismatch`: `129`.
- `rows_with_assignment_expiration_classification`: `129`.
- `rows_missing_policy_exit_condition`: `0`.
- `zero_bid_or_untradable_rows`: `6`.
- `crossed_or_missing_quote_rows`: `3`.
- `fatal_blocker_count`: `129`.

## Blockers

- `existing_trusted_leg_exit_quotes_missing`
- `existing_trusted_missing_or_crossed_quote_fields`
- `existing_trusted_side_aware_bid_ask_prices_missing`
- `existing_trusted_side_aware_price_mismatch_with_source_run`
- `existing_trusted_zero_bid_or_untradable_leg_quote`

## Diagnostics

- `source_run_missing_leg_level_entry_bid_ask`
- `source_run_missing_leg_level_exit_bid_ask`

## Existing Quote Resolution

- Quote store: `{"data_trust": "trusted", "error": null, "exists": true, "intraday_quote_row_count": 26452017, "path": "data/options-validation/options_history.db", "read_only_mode": true, "snapshot_kind": "intraday", "source_labels": ["thetadata_opra_nbbo_1m"], "status": "loaded", "trusted_source_batch_count": 2079}`.
- Resolution rules: `{"enabled": true, "entry_lookup_rule": "exact trusted quote at 10:10 ET", "exit_lookup_rule": "latest common trusted quote at or before 15:55 ET", "read_only": true, "side_aware_entry_price_formula": "long_ask_minus_short_bid", "side_aware_exit_price_formula": "long_bid_minus_short_ask", "side_aware_price_tolerance": 0.05, "source_labels": ["thetadata_opra_nbbo_1m"]}`.

Fatal reason counts: `{"missing_leg_level_exit_bid_ask": 3, "missing_side_aware_exit_price": 3, "side_aware_price_mismatch_with_source_run": 129, "zero_bid_or_untradable_leg_quote": 6}`.

## Source Artifacts

| Source | Status | Age hours | Generated at | Reasons |
| --- | --- | ---: | --- | --- |
| `bullish_pullback_layer_shadow_selection` | `loaded` | `0.0` | `2026-06-26T14:26:07Z` | `[]` |
| `bullish_pullback_layer_stack` | `loaded` | `662.37` | `2026-05-30T00:04:04Z` | `[]` |
| `selected_layer_source_run` | `loaded` | `702.88` | `2026-05-28T01:33:03` | `[]` |

## Non-Goals

- `do_not_create_trades_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_submit_broker_orders_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_enable_live_validation_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_enable_auto_track_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_change_scanner_policy_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_change_strategy_logic_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_change_stops_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_change_sizing_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_mutate_evidence_databases_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_import_quotes_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_append_forward_cohort_rows_from_bullish_pullback_layer_execution_safety_audit`
- `do_not_consume_protected_holdout_from_bullish_pullback_layer_execution_safety_audit`