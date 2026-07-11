# Regular Options Preregistered Playbook Readiness Selector

This report is generated from `scripts/build_regular_options_preregistered_playbook_readiness_selector.py`. It is a read-only selector across completed preregistered design artifacts. It does not implement scanner or playbook logic, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `no_research_implementation_candidate_ready_without_blocker`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.
- Forward strict completed rows: `0` / `30`.
- Cohort log status: `missing`.

## Selected Candidate

No research-only implementation candidate is ready without a named blocker.

## Inventory

| Rank | Concept | Structure | Readiness | Blockers |
| --- | --- | --- | --- | --- |
| 1 | `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1` | `defined_risk_call_debit_spreads_only` | `blocked_by_known_readiness_audit` | `bootstrap_pf_lower_bound_not_above_1_after_resolution`, `preregistered_stress_test_not_implemented` |
| 2 | `low_mid_vix_index_put_credit_spread_vrp_v1` | `defined_risk_put_credit_spreads_only` | `blocked_by_known_readiness_audit` | `missing_native_vrp_candidate_generation_engine` |
| 3 | `low_mid_vix_macro_event_long_strangle_v1` | `defined_risk_long_straddles_or_strangles_only` | `blocked_by_known_readiness_audit` | `macro_event_calendar_source_missing` |
| 4 | `low_mid_vix_index_calendar_term_structure_dislocation_v1` | `defined_risk_calendar_or_diagonal_debit_spreads_only` | `blocked_by_known_readiness_audit` | `missing_index_calendar_quote_surface`, `missing_point_in_time_term_structure_inputs` |
| 5 | `low_mid_vix_index_skew_broken_wing_put_fly_v1` | `defined_risk_broken_wing_put_butterflies_only` | `blocked_by_known_readiness_audit` | `missing_index_broken_wing_quote_surface`, `missing_point_in_time_downside_skew_inputs` |
| 6 | `low_mid_vix_index_pmcc_diagonal_income_v1` | `defined_risk_pmcc_style_call_diagonals_only` | `blocked_by_known_readiness_audit` | `missing_point_in_time_trend_or_regime_inputs`, `missing_trusted_pmcc_diagonal_quote_surface` |
| 7 | `post_event_iv_crush_index_iron_condor_v1` | `defined_risk_short_iron_condors_or_iron_butterflies_only` | `blocked_by_known_readiness_audit` | `insufficient_full_window_rows`, `insufficient_latest_four_months`, `insufficient_latest_four_rows`, `insufficient_train_months`, `iv_event_premium_proxy_missing`, `macro_event_calendar_category_coverage_missing`, `macro_event_calendar_source_missing`, `missing_required_macro_event_categories` |
| 8 | `index_flow_extreme_mean_reversion_ratio_backspread_v1` | `defined_risk_ratio_spreads_or_backspreads_only` | `blocked_by_known_readiness_audit` | `missing_point_in_time_flow_extreme_input` |
| 9 | `index_constituent_dispersion_proxy_defined_risk_hybrid_v1` | `defined_risk_index_constituent_debit_credit_hybrid_pairs_only` | `blocked_by_known_readiness_audit` | `bounded_replay_rows_blocked` |

## Forbidden Actions

- `do_not_implement_scanner_or_playbook_logic`
- `do_not_run_historical_replay`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
