# Regular Options Bullish-Pullback Layer4 Forward Capture Protocol

Status: `protocol_ready_waiting_for_market_window_and_operator_approval`.

This is a read-only future paper-shadow capture protocol. It does not collect evidence, append rows, import quotes, mutate evidence stores, create trades, submit broker orders, enable live validation, enable auto-track, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote a lane.

## Selected Harness

- Lane: `bullish_pullback_observation`.
- Layer: `layer_4_clean_exact`.
- Variant: `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1`.
- Source run: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`.
- Freeze date: `2026-06-14`.
- Allowed symbols: `["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"]`.

## Historical Context

- Historical executable status: `executable_economics_recomputed_profitable_but_preflight_blocked`.
- Harness decision: `profitable_but_preflight_blocked`.
- Tradable executable rows: `120`.
- Side-aware PF: `3.7414`.
- Side-aware PF lower bound 5pct: `2.27`.
- Historical rows are forward proof: `false`.

## Protocol Requirements

- `assignment_expiration_risk_classification_required`: `true`.
- `contract_multiplier_and_fee_convention_required`: `true`.
- `denominator_statuses`: `["exact_entry_captured", "open_waiting_policy_exit", "exact_exit_captured", "missed_entry", "zero_untradable", "stale_display_rejected", "failed_or_incomplete_fill_attempt", "missing_exit"]`.
- `full_denominator_logging_required`: `true`.
- `future_natural_scanner_selections_only`: `true`.
- `leg_level_occ_identity_required`: `true`.
- `net_pnl_usd_required_for_exact_exit`: `true`.
- `policy_defined_exit_condition_required_for_exact_exit`: `true`.
- `required_row_fields`: `["row_id", "lane_id", "layer_id", "variant_id", "ticker", "selection_date", "denominator_status", "scanner_run_id", "scanner_policy_hash", "long_contract_symbol", "short_contract_symbol"]`.
- `scanner_policy_snapshot_required`: `true`.
- `side_aware_entry_price_formula`: `"long_ask_minus_short_bid"`.
- `side_aware_exit_price_formula`: `"long_bid_minus_short_ask"`.
- `source_marks_midpoint_eod_display_stale_last_trade_manual_synthetic_lookahead_percent_only_rejected_as_proof`: `true`.
- `trusted_opra_nbbo_entry_bid_ask_required_for_entry_rows`: `true`.
- `trusted_opra_nbbo_exit_bid_ask_required_for_exact_exit_rows`: `true`.

## Blockers

- None for protocol readiness. Actual row collection still requires a future market-data window and separate operator approval.

## Non-Goals

- `do_not_create_trades_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_submit_broker_orders_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_enable_live_validation_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_enable_auto_track_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_change_scanner_policy_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_change_strategy_logic_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_change_stops_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_change_sizing_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_mutate_evidence_databases_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_import_quotes_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_append_forward_cohort_rows_from_bullish_pullback_layer4_forward_capture_protocol`
- `do_not_consume_protected_holdout_from_bullish_pullback_layer4_forward_capture_protocol`
