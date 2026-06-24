# Regular Options Existing Input Surface Atlas

- Status: `research_only_input_surfaces_exhausted_under_current_repository`
- Generated: `2026-06-24T00:16:55Z`
- Read-only DB open: `True`
- Accepted profitability: `False`
- Strict latest-four/forward rows: `0/30`
- Ready source surfaces: `0`
- Stop exception candidate: `True`

This is a source/input inventory only. It does not run P&L replay, generate trades, import quotes, mutate evidence, consume protected holdout, change strategy logic, or promote a lane.

## Baseline

- `accepted_profitability`: `False`
- `current_forward_or_latest_four_strict_rows`: `0`
- `target_latest_four_strict_rows`: `30`
- `historical_rows_are_forward_proof`: `False`
- `frontier_candidate_count`: `44`
- `countable_throughput_candidate_found`: `False`
- `base_identity_hash_count`: `157`
- `all_local_quote_surface_replayability_exhausted_under_current_data`: `True`
- `local_quote_matrix_status`: `local_quote_surface_only_structures_exhausted_under_current_data`
- `opening_range_blocker`: `blocked_latest_four_rows_below_30`
- `synthetic_forward_blocker`: `blocked_insufficient_synthetic_forward_coverage`

## Candidate Surfaces

- `option_quote_snapshots_underlying_price_opening_bucket` (underlying_or_opening_bucket, direct_market_source): ready=`False`, train_months=`0`, latest_four_months=`1`, date_coverage=`0.58%`, latest_four_date_coverage=`3.53%`, blockers=blocked_missing_quote_surface_underlying_price, date_coverage_below_90, latest_four_date_coverage_below_90, latest_four_months_below_4, train_months_below_20
- `option_quote_snapshots_underlying_price_trend_proxy` (trend_or_regime, derived_point_in_time_proxy): ready=`False`, train_months=`0`, latest_four_months=`1`, date_coverage=`0.58%`, latest_four_date_coverage=`3.53%`, blockers=date_coverage_below_90, insufficient_underlying_price_history_for_trend_proxy, latest_four_date_coverage_below_90, latest_four_months_below_4, train_months_below_20
- `point_in_time_vix_bucket_artifact` (direct_vix_or_volatility_regime, direct_market_source): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, direct_vix_source_not_present, latest_four_date_coverage_below_90, latest_four_months_below_4, missing_or_unsafe_known_at, missing_required_fields, missing_vix_bucket_threshold_policy, point_in_time_vix_source_missing, train_months_below_20, vix_bucket_date_coverage_incomplete
- `option_quote_snapshots_iv_proxy_volatility_regime` (option_iv_proxy_volatility_regime, derived_point_in_time_proxy): ready=`False`, train_months=`0`, latest_four_months=`1`, date_coverage=`0.58%`, latest_four_date_coverage=`3.53%`, blockers=date_coverage_below_90, latest_four_date_coverage_below_90, latest_four_months_below_4, proxy_may_not_clear_direct_vix_blocker, train_months_below_20
- `point_in_time_flow_extreme_input_artifact` (flow_or_liquidity_pressure, missing): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, insufficient_date_coverage, insufficient_month_coverage, latest_four_date_coverage_below_90, latest_four_months_below_4, missing_or_unsafe_known_at, missing_point_in_time_flow_extreme_source, missing_required_fields, missing_required_flow_fields, plain_bid_ask_availability_is_not_flow_input, source_missing, train_months_below_20
- `option_quote_snapshots_volume_open_interest` (volume_open_interest, direct_market_source): ready=`False`, train_months=`0`, latest_four_months=`1`, date_coverage=`0.58%`, latest_four_date_coverage=`3.53%`, blockers=date_coverage_below_90, insufficient_volume_open_interest_history, latest_four_date_coverage_below_90, latest_four_months_below_4, train_months_below_20
- `macro_event_calendar_artifact` (macro_event_calendar, direct_market_source): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, latest_four_date_coverage_below_90, latest_four_months_below_4, macro_event_calendar_source_missing, missing_or_unsafe_known_at, missing_required_fields, missing_required_macro_event_categories, train_months_below_20
- `earnings_event_calendar_existing_artifact_search` (earnings_event_calendar, missing): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, earnings_event_calendar_source_missing, latest_four_date_coverage_below_90, latest_four_months_below_4, missing_or_unsafe_known_at, missing_required_fields, source_missing, train_months_below_20
- `option_quote_snapshots_term_structure_skew_quote_proxy` (term_structure_or_skew, derived_point_in_time_proxy): ready=`False`, train_months=`20`, latest_four_months=`4`, date_coverage=`95.0%`, latest_four_date_coverage=`96.47%`, blockers=already_parked_quote_surface_only
- `dispersion_concentration_proxy_artifact` (dispersion_or_concentration_proxy, derived_point_in_time_proxy): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, insufficient_date_coverage, insufficient_month_coverage, latest_four_date_coverage_below_90, latest_four_months_below_4, missing_or_unsafe_known_at, missing_point_in_time_dispersion_proxy_source, missing_required_fields, missing_required_return_fields, train_months_below_20
- `candidate_generation_diagnostics_from_oracle_packet` (candidate_generation_diagnostics, diagnostic_only): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=date_coverage_below_90, latest_four_date_coverage_below_90, latest_four_months_below_4, missing_daily_candidate_generation_diagnostics, missing_or_unsafe_known_at, missing_required_fields, train_months_below_20
- `fresh_forward_collection_readiness_from_existing_contracts` (fresh_forward_collection_readiness, approval_required_import): ready=`False`, train_months=`0`, latest_four_months=`0`, date_coverage=`0.0%`, latest_four_date_coverage=`0.0%`, blockers=approval_required, date_coverage_below_90, forward_cohort_append_forbidden_in_this_slice, latest_four_date_coverage_below_90, latest_four_months_below_4, train_months_below_20, valid_market_window_required

## Next Gates

- `fresh_forward_cohort_append_during_valid_market_window`
- `scoped_source_repair_or_replay`
- `quote_import_or_new_data_surface`
- `protected_holdout_decision`
- `promotion_review`
