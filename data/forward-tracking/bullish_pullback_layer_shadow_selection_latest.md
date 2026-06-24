# Bullish Pullback Layer Shadow Selection

No live release. This read-only report selects the bullish-pullback paper-shadow harness layer for future natural market-window evidence collection.

## At a glance

- Overall status: `layer_shadow_selection_ready`.
- Selection ready: `true`.
- Paper-shadow only: `true`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Trade recommendation: `false`.

## Harness Selection

| Role | Layer | Variant | Status | Exact | PF | Coverage | Stress PF | Unpriced |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| primary_clean_harness_layer | layer_4_clean_exact | sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1 | selected_primary_clean_harness_layer | 129 | 2.2 | 100.0 | 1.67 | 0 |
| count_expanded_reference | layer_5_count_expanded | sleeve_pf59_coverage_a_refill_v1 | count_expanded_reference_blocked_by_unpriced_candidates | 130 | 2.04 | 97.7 | 1.53 | 3 |
| high_pf_core_queue_reference | layer_0_confidence_core_s_a_b | confidence_s_a_b_queue | high_pf_core_reference_with_provenance_caveat | 108 | 4.86 |  |  |  |

## Target Truth

- Preferred target exact trades: `200`.
- Current best exact trades: `130`.
- Gap to 200: `70`.
- Honest status: `not_reached`.

## Allowed Symbols

`IWM, AAPL, GOOGL, UNH, LLY, JNJ, XOM, CVX, COP, NEM`

## Harness Requirements

- `allowed_symbols`: `['IWM', 'AAPL', 'GOOGL', 'UNH', 'LLY', 'JNJ', 'XOM', 'CVX', 'COP', 'NEM']`.
- `assignment_expiration_risk_review_required`: `True`.
- `denominator_failure_row_handling_required`: `True`.
- `entry_exit_quote_source`: `trusted exact OPRA/NBBO bid/ask only`.
- `exact_entry_quote_required`: `True`.
- `future_evidence_posture`: `future_natural_market_window_paper_shadow_collection_only`.
- `is_broker_order`: `False`.
- `is_trade_recommendation`: `False`.
- `leg_level_bid_ask_audit_required`: `True`.
- `paper_shadow_only`: `True`.
- `policy_defined_exact_exit_required`: `True`.
- `selected_layer_id`: `layer_4_clean_exact`.
- `selected_variant_id`: `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1`.
- `source_result_path`: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`.

## Blockers

- None.

## Prohibited Actions

- `do_not_create_trades_from_bullish_pullback_layer_shadow_selection`
- `do_not_submit_broker_orders_from_bullish_pullback_layer_shadow_selection`
- `do_not_enable_live_validation_from_bullish_pullback_layer_shadow_selection`
- `do_not_enable_auto_track_from_bullish_pullback_layer_shadow_selection`
- `do_not_change_scanner_policy_from_bullish_pullback_layer_shadow_selection`
- `do_not_change_strategy_logic_from_bullish_pullback_layer_shadow_selection`
- `do_not_change_stops_from_bullish_pullback_layer_shadow_selection`
- `do_not_change_sizing_from_bullish_pullback_layer_shadow_selection`
- `do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_shadow_selection`
- `do_not_mutate_evidence_databases_from_bullish_pullback_layer_shadow_selection`
- `do_not_import_quotes_from_bullish_pullback_layer_shadow_selection`
- `do_not_append_forward_cohort_rows_from_bullish_pullback_layer_shadow_selection`
- `do_not_consume_protected_holdout_from_bullish_pullback_layer_shadow_selection`
