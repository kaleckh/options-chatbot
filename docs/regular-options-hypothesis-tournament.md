# Regular Options Hypothesis Tournament

No tournament candidate is ready for forward freeze. Current state remains paper-shadow only.

## Search budget and variants tested

- Max variants: `100`.
- Raw candidate count: `65`.
- Variants tested: `65`.
- Budget enforced: `False`.
- Min trades / holdout / months: `200` / `30` / `4`.
- Selection-adjusted bar preserved from robust search: `1.18`.

## Data/proof standard

- Feature store: `feature_store_built` with `505` shared dates from `2024-05-22` to `2026-06-04`.
- Quote source: `thetadata_opra_nbbo_1m` / `intraday` / `trusted`.
- Robust search: `historical_candidates_blocked`, accepted exact rows `231`, ready candidates `0`.
- Walk-forward: `historical_walkforward_ran_candidates_blocked`, promotion ready `False`.
- Counted proof must be executable exact options evidence, not midpoint/EOD/stale/manual/display-only/last/model marks.

## Best candidate, if any

- Candidate: `lane:volatility_expansion_observation`.
- Decision: `paper_shadow_candidate`.
- Lane: `volatility_expansion_observation`.
- Exact / holdout rows: `24` / `0`.
- PF / PF lower bound / avg: `1.83` / `None` / `6.74`.
- Next step: Keep paper-shadow only; collect fresh exact entries and exact realized exits.

## Candidate leaderboard

| Candidate | Decision | Complexity | Exact | Holdout | PF | PF LB | Avg % | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `lane:volatility_expansion_observation` | `paper_shadow_candidate` | 1 | 24 | 0 | 1.83 |  | 6.74 | trade_qualification_decision:paper_shadow_collect, fresh_paper_cohort, fresh_paper_cohort_insufficient, walk_forward_holdout_depth, walk_forward_holdout_too_small_or_failed, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, positive_histori |
| `filter:current_lane_gate_self_guardrails` | `thin_sample_watch` | 1 | 10 | 0 | 69.14 |  | 34.87 | filter_matrix_status:active_safety_gate_paper_probation, lost_winner_count_63, total_exact_rows_10_below_200 |
| `filter:lane_gate_self_guardrails_plus_exact_spread_dedupe` | `thin_sample_watch` | 2 | 10 | 0 | 69.14 |  | 34.87 | filter_matrix_status:recommended_paper_shadow_policy_candidate, lost_winner_count_63, total_exact_rows_10_below_200 |
| `sleeve_next_index_refill_v1` | `thin_sample_watch` | 2 | 116 | 0 | 1.74 | 1.33 | 20.49 | profitable_but_overlaps_existing_stack, worth_status:profitable_but_overlaps, total_exact_rows_116_or_holdout_rows_0_below_gate, total_exact_rows_116_below_200 |
| `sleeve_next_reit_industrial_refill_v1` | `thin_sample_watch` | 2 | 128 | 0 | 1.53 | 1.17 | 15.94 | stress_or_risk_repair_required, worth_status:repair_stress_before_counting, total_exact_rows_128_or_holdout_rows_0_below_gate, total_exact_rows_128_below_200 |
| `sleeve_next_defensive_refill_v1` | `thin_sample_watch` | 2 | 143 | 0 | 1.48 | 1.13 | 14.43 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, total_exact_rows_143_or_holdout_rows_0_below_gate, total_exact_rows_143_below_200 |
| `sleeve_next_industrial_cat_mixedexit_v1` | `repair_needed` | 2 | 3 | 0 | 8.21 | 2.19 | 16.73 | thin_sample_variant, worth_status:thin_sample, quote_coverage_33.3_below_90, unpriced_rows_6 |
| `sleeve_next_reit_pld_mixedexit_v1` | `repair_needed` | 2 | 4 | 0 | 3.77 | 0.89 | 9.37 | thin_sample_variant, worth_status:thin_sample, quote_coverage_80.0_below_90, unpriced_rows_1 |
| `sleeve_ticker_iwm` | `repair_needed` | 2 | 21 | 0 | 3.08 | 2.02 | 26.58 | thin_sample_variant, worth_status:thin_sample, quote_coverage_75.0_below_90, unpriced_rows_7 |
| `sleeve_next_index_with_iwm_spy_control_v1` | `repair_needed` | 2 | 14 | 0 | 2.7 | 1.88 | 25.22 | thin_sample_variant, worth_status:thin_sample, quote_coverage_73.7_below_90, unpriced_rows_5 |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `repair_needed` | 2 | 104 | 14 | 2.3283 | 0.28 | 29.53 | final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_b |
| `lane:bullish_pullback_core` | `repair_needed` | 2 | 127 | 18 | 1.9463 | 0.32 | 22.25 | bullish_pullback_core:unpriced_candidates_3, final_holdout_avg_not_above_baseline, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, final_holdout_pf_not_above_baseline, paper_shad |
| `sleeve_next_defensive_wmt_mixedexit_v1` | `repair_needed` | 2 | 11 | 0 | 1.58 | 1.02 | 10.41 | thin_sample_variant, worth_status:thin_sample, quote_coverage_55.0_below_90, unpriced_rows_9 |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `repair_needed` | 2 | 30 | 0 | 1.38 | 0.97 | 9.06 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_69.8_below_90, unpriced_rows_13 |
| `tracked_winner_chain_native_research_all_sleeves` | `repair_needed` | 2 | 112 | 0 | 1.23 | 0.9 | 6.73 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_70.9_below_90, unpriced_rows_46 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `repair_needed` | 2 | 82 | 0 | 1.05 | 0.71 | 1.29 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_79.6_below_90, unpriced_rows_21 |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | `repair_needed` | 2 | 140 | 0 | 1.0 | 0.67 | 0.06 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, quote_coverage_50.9_below_90, unpriced_rows_135 |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | `repair_needed` | 2 | 58 | 0 | 0.98 | 0.7 | -0.63 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_82.9_below_90, unpriced_rows_12 |
| `tracked_winner_cheap_debit_continuity_v1` | `repair_needed` | 2 | 130 | 0 | 0.85 | 0.59 | -4.76 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_69.9_below_90, unpriced_rows_56 |
| `range_breakout_observation_chain_native_call_timeexit_all_sleeves` | `repair_needed` | 2 | 20 | 0 | 0.75 | 0.43 | -5.78 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, quote_coverage_54.1_below_90, unpriced_rows_17 |
Showing `20` of `65` candidates; see JSON for all rows.

## Rejection table with reason codes

| Candidate | Decision | Complexity | Exact | Holdout | PF | PF LB | Avg % | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `filter:current_lane_gate_allowlist` | `overfit_reject` | 1 | 24 | 0 | 1.83 |  | 6.74 | filter_matrix_status:active_safety_gate_paper_probation, does_not_survive_later_date_split, lost_winner_count_60, stress_or_later_date_split_failed |
| `filter:no_extended_damage_tickers` | `overfit_reject` | 1 | 77 | 0 | 1.0 |  | 5.73 | filter_matrix_status:overfit_warning, does_not_survive_later_date_split, lost_winner_count_21, point_profit_factor_not_above_1 |
| `filter:no_primary_damage_tickers` | `overfit_reject` | 1 | 105 | 0 | 0.6 |  | -10.37 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_19, point_profit_factor_not_above_1 |
| `lane:tracked_winner_observation` | `overfit_reject` | 1 | 20 | 0 | 0.5 |  | -8.43 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_profit_factor_not_above_1 |
| `lane:tracked_winner_primary` | `overfit_reject` | 1 | 20 | 0 | 0.5 |  | -8.43 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_profit_factor_not_above_1 |
| `filter:no_debit_gte_45` | `overfit_reject` | 1 | 169 | 0 | 0.41 |  | -11.79 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_6, point_profit_factor_not_above_1 |
| `filter:no_dte_gte_36` | `overfit_reject` | 1 | 187 | 0 | 0.37 |  | -15.27 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_5, point_profit_factor_not_above_1 |
| `filter:baseline_all_untracked` | `overfit_reject` | 1 | 206 | 0 | 0.32 |  | -16.54 | filter_matrix_status:baseline_readback, does_not_survive_later_date_split, point_profit_factor_not_above_1 |
| `filter:exact_spread_dedupe_only` | `overfit_reject` | 1 | 179 | 0 | 0.31 |  | -16.98 | filter_matrix_status:immediate_suppression_candidate, does_not_survive_later_date_split, lost_winner_count_10, point_profit_factor_not_above_1 |
| `lane:speculative` | `overfit_reject` | 1 | 8 | 0 | 0.1 |  | -12.62 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, insufficient_priced_exact_outcomes, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_pro |
| `sleeve_next_index_move_bucket_baseline_v1` | `overfit_reject` | 2 | 4 | 0 | 1.7 | 0.87 | 8.16 | thin_sample_variant, worth_status:thin_sample, total_exact_rows_4_or_holdout_rows_0_below_gate, stress_or_later_date_split_failed |
| `sleeve_next_move_bucket_refill_v1` | `overfit_reject` | 2 | 153 | 0 | 1.27 | 0.96 | 8.52 | weak_or_negative_peer_variant, worth_status:weak_positive_or_marginal, total_exact_rows_153_or_holdout_rows_0_below_gate, stress_or_later_date_split_failed |
| `filter:primary_combo_no_debit45_dte36_damage_tickers` | `overfit_reject` | 2 | 76 | 0 | 1.06 |  | -3.69 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_28, stress_or_later_date_split_failed |
| `smh_semiconductor_call_chain_native_timeexit_all_sleeves` | `overfit_reject` | 2 | 17 | 0 | 0.4 | 0.27 | -20.11 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, point_profit_factor_not_above_1 |
| `relative_strength_pullback_ex_clean_universe_v1` | `overfit_reject` | 2 | 79 | 0 | 0.16 | 0.11 | -53.65 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, point_profit_factor_not_above_1 |
| `sleeve_next_high_beta_survival_v1` | `overfit_reject` | 2 | 16 | 0 | 0.11 | 0.07 | -44.3 | weak_or_negative_peer_variant, worth_status:not_worth_current_shape, point_profit_factor_not_above_1 |
| `bearish_defensive_chain_native_put_timeexit_all_sleeves` | `execution_fragile_reject` | 2 | 0 | 0 | 0.0 | 0.0 | 0.0 | no_current_candidates, worth_status:no_current_candidates, quote_coverage_0.0_below_90, execution_or_liquidity_fragility |
| `bullish_mean_reversion_chain_native_call_timeexit_all_sleeves` | `execution_fragile_reject` | 2 | 0 | 0 | 0.0 | 0.0 | 0.0 | no_current_candidates, worth_status:no_current_candidates, quote_coverage_0.0_below_90, execution_or_liquidity_fragility |
| `kre_regional_bank_call_chain_native_timeexit_all_sleeves` | `execution_fragile_reject` | 2 | 0 | 0 | 0.0 | 0.0 | 0.0 | no_current_candidates, worth_status:no_current_candidates, quote_coverage_0.0_below_90, execution_or_liquidity_fragility |
| `kre_regional_bank_put_chain_native_timeexit_all_sleeves` | `execution_fragile_reject` | 2 | 0 | 0 | 0.0 | 0.0 | 0.0 | no_current_candidates, worth_status:no_current_candidates, quote_coverage_0.0_below_90, execution_or_liquidity_fragility |
Showing `20` of `31` candidates; see JSON for all rows.

## Stress-test summary

- `{"rows": [{"candidate_id": "lane:volatility_expansion_observation", "decision": "paper_shadow_candidate", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "filter:current_lane_gate_self_guardrails", "decision": "thin_sample_watch", "stress_results": {"avoided_lte_minus_50": 41, "lost_winner_count": 63, "survives_later_date_split": true}, "top_winner_dependency": {"lost_winner_count": 63, "status": "winner_damage_available"}}, {"candidate_id": "filter:lane_gate_self_guardrails_plus_exact_spread_dedupe", "decision": "thin_sample_watch", "stress_results": {"avoided_lte_minus_50": 41, "lost_winner_count": 63, "survives_later_date_split": true}, "top_winner_dependency": {"lost_winner_count": 63, "status": "winner_damage_available"}}, {"candidate_id": "sleeve_next_index_refill_v1", "decision": "thin_sample_watch", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.33, "strict_new_trade_count": 6}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_reit_industrial_refill_v1", "decision": "thin_sample_watch", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.17, "strict_new_trade_count": 15}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_defensive_refill_v1", "decision": "thin_sample_watch", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.13, "strict_new_trade_count": 15}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_industrial_cat_mixedexit_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 33.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 2.19, "strict_new_trade_count": 3}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_reit_pld_mixedexit_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 80.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.89, "strict_new_trade_count": 0}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_ticker_iwm", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 75.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 2.02, "strict_new_trade_count": 10}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_index_with_iwm_spy_control_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 73.7, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 1.88, "strict_new_trade_count": 4}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:lane_a_chain_native_ret20_4_stop200_time75", "decision": "repair_needed", "stress_results": {"final_holdout_pf_lb_5pct": 0.28, "statistical_confidence": "underpowered"}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:bullish_pullback_core", "decision": "repair_needed", "stress_results": {"final_holdout_pf_lb_5pct": 0.32, "statistical_confidence": "negative_or_flat"}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_defensive_wmt_mixedexit_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 55.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 1.02, "strict_new_trade_count": 0}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 69.8, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.97, "strict_new_trade_count": 19}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_chain_native_research_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 70.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.9, "strict_new_trade_count": 112}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_chain_native_no_spy_time65_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 79.6, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.71, "strict_new_trade_count": 82}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "volatility_expansion_observation_chain_native_call_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 50.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.67, "strict_new_trade_count": 140}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_chain_native_googl_nvda_time65_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 82.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.7, "strict_new_trade_count": 58}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_cheap_debit_continuity_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 69.9, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.59, "strict_new_trade_count": 130}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "range_breakout_observation_chain_native_call_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 54.1, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.43, "strict_new_trade_count": 20}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_liquidity_first_contract_hygiene_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 65.1, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.49, "strict_new_trade_count": 108}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "tracked_winner_chain_native_qqq_time65_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 73.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.46, "strict_new_trade_count": 148}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "volatility_expansion_observation_chain_native_call_fast35_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 46.6, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.24, "strict_new_trade_count": 108}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "volatility_expansion_observation_chain_native_put_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 32.1, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.27, "strict_new_trade_count": 25}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "bearish_index_put_observation_chain_native_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 26.4, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.27, "strict_new_trade_count": 23}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "regular_bearish_put_primary_chain_native_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 34.4, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.23, "strict_new_trade_count": 54}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "regular_bearish_put_index_narrow_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 23.2, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.2, "strict_new_trade_count": 33}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_high_beta_momentum_fast_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 79.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.18, "strict_new_trade_count": 46}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sector_rotation_regular_etf_call_stack_v1", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 82.6, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.14, "strict_new_trade_count": 19}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "range_breakout_observation_chain_native_put_timeexit_all_sleeves", "decision": "repair_needed", "stress_results": {"quote_coverage_pct": 50.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.0, "strict_new_trade_count": 4}, "top_winner_dependency": {"status": "not_available"}}], "stress_failed_count": 5, "stress_rows_reported": 65}`

## Split/holdout summary

- `{"forward_holdout_guard_status": "passed", "latest_candidate_entry_date": "2026-03-24", "promotion_ready": false, "protected_forward_holdout_overlap": false, "protected_forward_holdout_start_date": "2026-06-05", "selection_adjusted_bar": 1.18, "split_policy": {"final_holdout_fraction": 0.15, "no_same_entry_date_crosses_splits": true, "split_unit": "unique_entry_date", "train_fraction": 0.6, "validation_fraction": 0.25}, "variants_searched_upstream": 12}`

## Concentration analysis

- `{"flagged_month_candidates": [], "flagged_ticker_candidates": [], "month_concentration_flagged_count": 0, "ticker_concentration_flagged_count": 0}`

## Forward-freeze spec if any

- None. No candidate passed the tournament gates.

## If no candidate survived, next hypothesis queue

- Priority `1` `collect_forward_exact_paper_shadow_for_best_lane`: freeze no live behavior; collect fresh exact paper entries and policy-defined exact realized exits (best current lane is positive but lacks forward exact realized P&L and holdout depth).
- Priority `2` `repair_source_quality_or_execution_fragility`: Repair unpriced rows before any forward-freeze discussion. (thin_sample_variant, worth_status:thin_sample, quote_coverage_33.3_below_90, unpriced_rows_6).
- Priority `3` `diagnostic_filter_matrix_current_lane_gate_self_guardrails`: preregister as diagnostic point-in-time replay only; do not change scanner policy (kept_count=10 pf=69.14 status=active_safety_gate_paper_probation lost_winners=63).
- Priority `3` `diagnostic_filter_matrix_lane_gate_self_guardrails_plus_exact_spread_dedupe`: preregister as diagnostic point-in-time replay only; do not change scanner policy (kept_count=10 pf=69.14 status=recommended_paper_shadow_policy_candidate lost_winners=63).
- Priority `3` `diagnostic_filter_matrix_current_lane_gate_allowlist`: preregister as diagnostic point-in-time replay only; do not change scanner policy (kept_count=24 pf=1.83 status=active_safety_gate_paper_probation lost_winners=60).
- Priority `4` `debit_pct_gte_45_diagnostic`: keep as simple diagnostic exclusion candidate for future preregistered replay (rows=37 pf=0.05 avg=-38.26).
- Priority `4` `dte_gte_36_diagnostic`: keep as simple diagnostic exclusion candidate for future preregistered replay (rows=19 pf=0.12 avg=-29.05).
- Priority `9` `keep_quarantined_lanes_parked`: do not resurrect no-chase lanes without fresh exact earn-back evidence (quarantined lanes remain negative or no-chase in current readbacks).

## Requirements before live discussion

- a frozen forward-paper candidate spec with no post-hoc edits.
- at least 30 post-freeze exact realized paper-shadow rows.
- fresh executable exact OPRA/NBBO entry evidence for each row.
- policy-defined executable exact OPRA/NBBO exit evidence for each row.
- positive forward net P&L after fees and execution-realistic pricing.
- forward paper profit-factor lower bound above 1.0.
- no source-quality, unpriced, midpoint, stale, EOD, display-only, manual, last-trade, or model proof contamination.
- no open-risk or no-chase blocker.

## What not to do

- `do_not_create_trades_from_hypothesis_tournament`
- `do_not_submit_broker_orders_from_hypothesis_tournament`
- `do_not_enable_auto_track_from_hypothesis_tournament`
- `do_not_enable_live_validation_from_hypothesis_tournament`
- `do_not_change_scanner_policy_from_hypothesis_tournament`
- `do_not_change_stops_from_hypothesis_tournament`
- `do_not_change_sizing_from_hypothesis_tournament`
- `do_not_lower_proof_bars_from_hypothesis_tournament`
- `do_not_mutate_evidence_databases_from_hypothesis_tournament`
- `do_not_count_midpoint_eod_stale_manual_display_last_or_model_marks_as_proof`
- `do_not_treat_historical_research_rows_as_live_proof`
- `do_not_create_trades_from_robust_edge_discovery`
- `do_not_submit_broker_orders_from_robust_edge_discovery`
- `do_not_enable_auto_track_from_robust_edge_discovery`
- `do_not_enable_live_validation_from_robust_edge_discovery`
- `do_not_change_scanner_policy_from_robust_edge_discovery`
- `do_not_change_stops_from_robust_edge_discovery`
- `do_not_change_sizing_from_robust_edge_discovery`
- `do_not_lower_proof_bars_from_robust_edge_discovery`
- `do_not_mutate_evidence_databases_from_robust_edge_discovery`
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
| `feature_store` | `loaded` | `0.01` | `2026-06-18T06:09:35Z` | `[]` |
| `historical_walk_forward` | `loaded` | `0.0` | `2026-06-18T06:09:39Z` | `[]` |
| `lane_promotion_state` | `loaded` | `3.93` | `2026-06-18T02:13:58Z` | `[]` |
| `missed_failures` | `loaded` | `3.94` | `2026-06-18T02:13:48Z` | `[]` |
| `missed_filter_matrix` | `loaded` | `3.93` | `2026-06-18T02:13:53Z` | `[]` |
| `monthly_profitability` | `loaded` | `3.34` | `2026-06-18T02:49:24Z` | `[]` |
| `robust_edge_discovery` | `loaded` | `0.0` | `2026-06-18T06:09:46Z` | `[]` |
| `robust_search` | `loaded` | `0.0` | `2026-06-18T06:09:39Z` | `[]` |

## Non-goals

This workflow does not:

- create trades
- submit broker orders
- enable auto-track
- enable live validation
- change scanner policy
- change stops
- change sizing
- lower proof bars
- mutate evidence databases
- prove future profits with certainty
