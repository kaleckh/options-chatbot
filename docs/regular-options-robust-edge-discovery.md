# Regular Options Robust Edge Discovery and Falsification

No robust execution-realistic edge is supported by the current local data.

## Best candidate, if any

- Candidate: `combined_portfolio`.
- Decision: `blocked_missing_readbacks`.
- Lane: `combined_portfolio`.
- Exact rows: `231`; holdout rows: `28`.
- Profit factor / lower bound: `2.113` / `0.61`.
- Next step: Refresh required readbacks before classifying this candidate..

## Why it is or is not trustworthy

- Overall status: `blocked_stale_readbacks`.
- Robust candidates: `0`.
- Paper-shadow candidates: `0`.
- Rejected candidates: `0`.
- Blocked candidates: `55`.
- Existing promotion_ready preserved: `false`.

## Data coverage summary

- Feature store: `feature_store_built`.
- Quote source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Shared quote dates: `505` from `2024-05-22` to `2026-06-04`.
- Robust-search status: `historical_candidates_blocked`; accepted exact rows `231`; ready candidates `0`.
- Source-quality gate: `source_quality_gate_blocked`.
- Walk-forward status: `historical_walkforward_ran_candidates_blocked`; promotion ready `False`.

## Proof standard used

- Standard: `executable exact options evidence only`.
- Counted proof must be executable exact options evidence, not midpoint/EOD/stale/display/manual/last/model marks.
- Historical rows can nominate or reject a future forward candidate only; they are not live proof.

## Candidate leaderboard

| Candidate | Decision | Exact | Holdout | PF | PF LB | Avg % | Evidence | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `combined_portfolio` | `blocked_missing_readbacks` | 231 | 28 | 2.113 | 0.61 | 25.53 | `trusted_intraday_opra_nbbo` | bullish_pullback_core:unpriced_candidates_3, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_ |
| `sleeve_next_move_bucket_refill_v1` | `blocked_missing_readbacks` | 153 | 0 | 1.27 | 0.96 | 8.52 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, required_source_readback_not_loaded |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `blocked_missing_readbacks` | 148 | 0 | 0.68 | 0.46 | -10.96 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_73.3_below_90, required_source_readback_not_loaded |
| `sleeve_next_defensive_refill_v1` | `blocked_missing_readbacks` | 143 | 0 | 1.48 | 1.13 | 14.43 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, required_source_readback_not_loaded |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | `blocked_missing_readbacks` | 140 | 0 | 1.0 | 0.67 | 0.06 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_50.9_below_90, required_source_readback_not_loaded |
| `tracked_winner_cheap_debit_continuity_v1` | `blocked_missing_readbacks` | 130 | 0 | 0.85 | 0.59 | -4.76 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_69.9_below_90, required_source_readback_not_loaded |
| `sleeve_next_reit_industrial_refill_v1` | `blocked_missing_readbacks` | 128 | 0 | 1.53 | 1.17 | 15.94 | `trusted_intraday_opra_nbbo` | stress_or_risk_repair_required, worth_status:repair_stress_before_counting, required_source_readback_not_loaded |
| `lane:bullish_pullback_core` | `blocked_missing_readbacks` | 127 | 18 | 1.9463 | 0.32 | 22.25 | `trusted_intraday_opra_nbbo` | bullish_pullback_core:unpriced_candidates_3, final_holdout_avg_not_above_baseline, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, final_holdout_pf_not_above_baseline, paper_shad |
| `sleeve_next_index_refill_v1` | `blocked_missing_readbacks` | 116 | 0 | 1.74 | 1.33 | 20.49 | `trusted_intraday_opra_nbbo` | profitable_but_overlaps_existing_stack, worth_status:profitable_but_overlaps, required_source_readback_not_loaded |
| `tracked_winner_chain_native_research_all_sleeves` | `blocked_missing_readbacks` | 112 | 0 | 1.23 | 0.9 | 6.73 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_70.9_below_90, required_source_readback_not_loaded |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | `blocked_missing_readbacks` | 108 | 0 | 0.74 | 0.49 | -7.46 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_65.1_below_90, required_source_readback_not_loaded |
| `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` | `blocked_missing_readbacks` | 108 | 0 | 0.47 | 0.24 | -11.88 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_46.6_below_90, required_source_readback_not_loaded |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `blocked_missing_readbacks` | 104 | 14 | 2.3283 | 0.28 | 29.53 | `trusted_intraday_opra_nbbo` | final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_b |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `blocked_missing_readbacks` | 82 | 0 | 1.05 | 0.71 | 1.29 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_79.6_below_90, required_source_readback_not_loaded |
| `relative_strength_pullback_ex_clean_universe_v1` | `blocked_missing_readbacks` | 79 | 0 | 0.16 | 0.11 | -53.65 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, required_source_readback_not_loaded |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | `blocked_missing_readbacks` | 58 | 0 | 0.98 | 0.7 | -0.63 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_82.9_below_90, required_source_readback_not_loaded |
| `lane:short_term` | `blocked_missing_readbacks` | 54 | 0 | 0.33 |  | -18.93 | `trusted_intraday_opra_nbbo` | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, required_source_readback_not_loaded |
| `regular_bearish_put_primary_chain_native_timeexit_all_sleeves` | `blocked_missing_readbacks` | 54 | 0 | 0.33 | 0.23 | -30.8 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_34.4_below_90, required_source_readback_not_loaded |
| `lane:swing` | `blocked_missing_readbacks` | 49 | 0 | 0.2 |  | -20.24 | `trusted_intraday_opra_nbbo` | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, required_source_readback_not_loaded |
| `sleeve_next_high_beta_momentum_fast_v1` | `blocked_missing_readbacks` | 46 | 0 | 0.26 | 0.18 | -31.38 | `trusted_intraday_opra_nbbo` | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_79.3_below_90, required_source_readback_not_loaded |
Showing `20` of `55` candidates; see JSON for all rows.

## Rejection table

No candidates.

## Stress-test results

- `combined_portfolio` `blocked_missing_readbacks`: `{"final_holdout_pf_lb_5pct": 0.61, "statistical_confidence": "underpowered"}`.
- `sleeve_next_move_bucket_refill_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 0.96, "strict_new_trade_count": 23}`.
- `tracked_winner_chain_native_qqq_time65_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 73.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.46, "strict_new_trade_count": 148}`.
- `sleeve_next_defensive_refill_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.13, "strict_new_trade_count": 15}`.
- `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 50.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.67, "strict_new_trade_count": 140}`.
- `tracked_winner_cheap_debit_continuity_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 69.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.59, "strict_new_trade_count": 130}`.
- `sleeve_next_reit_industrial_refill_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.17, "strict_new_trade_count": 15}`.
- `lane:bullish_pullback_core` `blocked_missing_readbacks`: `{"final_holdout_pf_lb_5pct": 0.32, "statistical_confidence": "negative_or_flat"}`.
- `sleeve_next_index_refill_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.33, "strict_new_trade_count": 6}`.
- `tracked_winner_chain_native_research_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 70.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.9, "strict_new_trade_count": 112}`.
- `tracked_winner_liquidity_first_contract_hygiene_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 65.1, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.49, "strict_new_trade_count": 108}`.
- `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 46.6, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.24, "strict_new_trade_count": 108}`.
- `lane:lane_a_chain_native_ret20_4_stop200_time75` `blocked_missing_readbacks`: `{"final_holdout_pf_lb_5pct": 0.28, "statistical_confidence": "underpowered"}`.
- `tracked_winner_chain_native_no_spy_time65_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 79.6, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.71, "strict_new_trade_count": 82}`.
- `relative_strength_pullback_ex_clean_universe_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 100.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.11, "strict_new_trade_count": 73}`.
- `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 82.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.7, "strict_new_trade_count": 58}`.
- `regular_bearish_put_primary_chain_native_timeexit_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 34.4, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.23, "strict_new_trade_count": 54}`.
- `sleeve_next_high_beta_momentum_fast_v1` `blocked_missing_readbacks`: `{"quote_coverage_pct": 79.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.18, "strict_new_trade_count": 46}`.
- `regular_bearish_put_index_narrow_timeexit_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 23.2, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.2, "strict_new_trade_count": 33}`.
- `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` `blocked_missing_readbacks`: `{"quote_coverage_pct": 69.8, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.97, "strict_new_trade_count": 19}`.

## Split / holdout summary

- `{"forward_holdout_guard_status": "passed", "latest_candidate_entry_date": "2026-03-24", "protected_forward_holdout_overlap": false, "protected_forward_holdout_start_date": "2026-06-05", "selection_adjusted_bar": 1.18, "split_policy": {"final_holdout_fraction": 0.15, "no_same_entry_date_crosses_splits": true, "split_unit": "unique_entry_date", "train_fraction": 0.6, "validation_fraction": 0.25}, "variants_searched": 12}`

## Concentration analysis

- `{"flagged_month_candidates": [], "flagged_ticker_candidates": [], "month_concentration_flagged_count": 0, "ticker_concentration_flagged_count": 0}`

## Forward-freeze candidate spec, if any

- Status: `not_recommended`.
- Candidate: `None`.
- Rules: none

## Requirements before live discussion

- frozen candidate algorithm spec with no post-hoc rule edits.
- at least 30 post-freeze exact realized paper-shadow rows.
- fresh executable exact OPRA/NBBO entry evidence for each forward row.
- policy-defined executable exact OPRA/NBBO exit evidence for each forward row.
- positive forward net P&L after fees and executable pricing.
- forward paper profit-factor lower bound above 1.0.
- no open-risk governor blocker.
- no source-quality, unpriced, midpoint, stale, EOD, display-only, manual, last-trade, or model proof contamination.

## What not to do

- `do_not_create_trades_from_robust_edge_discovery`
- `do_not_submit_broker_orders_from_robust_edge_discovery`
- `do_not_enable_auto_track_from_robust_edge_discovery`
- `do_not_enable_live_validation_from_robust_edge_discovery`
- `do_not_change_scanner_policy_from_robust_edge_discovery`
- `do_not_change_stops_from_robust_edge_discovery`
- `do_not_change_sizing_from_robust_edge_discovery`
- `do_not_lower_proof_bars_from_robust_edge_discovery`
- `do_not_mutate_evidence_databases_from_robust_edge_discovery`
- `do_not_treat_historical_research_rows_as_live_proof`
- `do_not_count_midpoint_eod_stale_manual_display_last_or_model_marks_as_proof`
- `do_not_create_live_row_from_robust_search_evaluation`
- `do_not_submit_broker_order_from_robust_search_evaluation`
- `do_not_change_scanner_policy_from_robust_search_evaluation`
- `do_not_change_stop_policy_from_robust_search_evaluation`
- `do_not_change_sizing_from_robust_search_evaluation`
- `do_not_lower_exact_opra_nbbo_proof_bar_from_robust_search_evaluation`
- `do_not_count_historical_rows_as_fresh_forward_promotion_proof`
- `do_not_consume_protected_forward_holdout_from_robust_search_evaluation`
- `do_not_create_trades_from_historical_walkforward`
- `do_not_submit_broker_orders_from_historical_walkforward`
- `do_not_change_scanner_policy_from_historical_walkforward`
- `do_not_change_proof_bars_from_historical_walkforward`
- `do_not_consume_protected_forward_holdout_from_historical_walkforward`
- `do_not_treat_historical_results_as_fresh_forward_proof`
- `do_not_create_live_row_from_monthly_profitability_audit`
- `do_not_submit_broker_order_from_monthly_profitability_audit`
- `do_not_mutate_database_from_monthly_profitability_audit`
- `do_not_change_scanner_policy_from_monthly_profitability_audit`
- `do_not_change_stop_policy_from_monthly_profitability_audit`
- `do_not_change_sizing_from_monthly_profitability_audit`
- `do_not_lower_exact_opra_nbbo_proof_bar_from_monthly_profitability_audit`
- `do_not_promote_paper_research_or_backfill_rows_to_production_proof`

## Source artifacts and staleness

| Source | Status | Age hours | Generated at | Reasons |
| --- | --- | ---: | --- | --- |
| `feature_store` | `loaded` | `93.65` | `2026-06-18T06:09:35Z` | `[]` |
| `historical_walk_forward` | `loaded` | `93.65` | `2026-06-18T06:09:39Z` | `[]` |
| `lane_promotion_state` | `loaded` | `10.44` | `2026-06-21T17:22:02Z` | `[]` |
| `market_window_evidence_checklist` | `loaded` | `7.06` | `2026-06-21T20:45:05Z` | `[]` |
| `missed_failures` | `stale` | `97.58` | `2026-06-18T02:13:48Z` | `["stale_readback"]` |
| `missed_filter_matrix` | `stale` | `97.58` | `2026-06-18T02:13:53Z` | `["stale_readback"]` |
| `missed_outcomes` | `loaded` | `10.47` | `2026-06-21T17:20:10Z` | `[]` |
| `monthly_profitability` | `loaded` | `10.44` | `2026-06-21T17:22:27Z` | `[]` |
| `paper_shadow_evidence_plan` | `loaded` | `7.06` | `2026-06-21T20:44:57Z` | `[]` |
| `robust_search` | `loaded` | `93.65` | `2026-06-18T06:09:39Z` | `[]` |
| `trade_qualification` | `loaded` | `10.44` | `2026-06-21T17:22:16Z` | `[]` |

## Non-goals

This report does not:

- prove future profits with certainty
- create trades
- submit broker orders
- enable auto-track
- enable live validation
- change scanner policy
- change stops
- change sizing
- lower proof bars
- mutate evidence databases
