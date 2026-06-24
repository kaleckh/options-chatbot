# Regular Options Hypothesis Tournament

No tournament candidate survived the current local evidence gates.

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

- Candidate: `filter:current_lane_gate_self_guardrails`.
- Decision: `blocked_missing_readbacks`.
- Lane: `multi_lane_filter_matrix`.
- Exact / holdout rows: `10` / `0`.
- PF / PF lower bound / avg: `69.14` / `None` / `34.87`.
- Next step: Refresh required readbacks before testing hypotheses.

## Candidate leaderboard

| Candidate | Decision | Complexity | Exact | Holdout | PF | PF LB | Avg % | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `filter:current_lane_gate_self_guardrails` | `blocked_missing_readbacks` | 1 | 10 | 0 | 69.14 |  | 34.87 | filter_matrix_status:active_safety_gate_paper_probation, lost_winner_count_63, required_source_readback_not_loaded |
| `filter:current_lane_gate_allowlist` | `blocked_missing_readbacks` | 1 | 24 | 0 | 1.83 |  | 6.74 | filter_matrix_status:active_safety_gate_paper_probation, does_not_survive_later_date_split, lost_winner_count_60, required_source_readback_not_loaded |
| `lane:volatility_expansion_observation` | `blocked_missing_readbacks` | 1 | 24 | 0 | 1.83 |  | 6.74 | trade_qualification_decision:paper_shadow_collect, fresh_paper_cohort, fresh_paper_cohort_insufficient, walk_forward_holdout_depth, walk_forward_holdout_too_small_or_failed, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, positive_histori |
| `filter:no_extended_damage_tickers` | `blocked_missing_readbacks` | 1 | 77 | 0 | 1.0 |  | 5.73 | filter_matrix_status:overfit_warning, does_not_survive_later_date_split, lost_winner_count_21, required_source_readback_not_loaded |
| `filter:no_primary_damage_tickers` | `blocked_missing_readbacks` | 1 | 105 | 0 | 0.6 |  | -10.37 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_19, required_source_readback_not_loaded |
| `lane:tracked_winner_observation` | `blocked_missing_readbacks` | 1 | 20 | 0 | 0.5 |  | -8.43 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_profit_factor_not_above_1, required_sou |
| `lane:tracked_winner_primary` | `blocked_missing_readbacks` | 1 | 20 | 0 | 0.5 |  | -8.43 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_profit_factor_not_above_1, required_sou |
| `filter:no_debit_gte_45` | `blocked_missing_readbacks` | 1 | 169 | 0 | 0.41 |  | -11.79 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_6, required_source_readback_not_loaded |
| `filter:no_dte_gte_36` | `blocked_missing_readbacks` | 1 | 187 | 0 | 0.37 |  | -15.27 | filter_matrix_status:diagnostic_retest_required, does_not_survive_later_date_split, lost_winner_count_5, required_source_readback_not_loaded |
| `lane:short_term` | `blocked_missing_readbacks` | 1 | 54 | 0 | 0.33 |  | -18.93 | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, quarantine_or_no_chase_active, required_source_readback_not_loaded |
| `filter:baseline_all_untracked` | `blocked_missing_readbacks` | 1 | 206 | 0 | 0.32 |  | -16.54 | filter_matrix_status:baseline_readback, does_not_survive_later_date_split, required_source_readback_not_loaded |
| `filter:exact_spread_dedupe_only` | `blocked_missing_readbacks` | 1 | 179 | 0 | 0.31 |  | -16.98 | filter_matrix_status:immediate_suppression_candidate, does_not_survive_later_date_split, lost_winner_count_10, required_source_readback_not_loaded |
| `lane:bullish_pullback_observation` | `blocked_missing_readbacks` | 1 | 15 | 0 | 0.24 |  | -22.81 | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, fresh_paper_cohort, fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, profit_factor_below_lane_gate, profitable_lane_gate, recent_cohort_circuit_breaker_ac |
| `lane:swing` | `blocked_missing_readbacks` | 1 | 49 | 0 | 0.2 |  | -20.24 | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, quarantine_or_no_chase_active, required_source_readback_not_loaded |
| `lane:speculative` | `blocked_missing_readbacks` | 1 | 8 | 0 | 0.1 |  | -12.62 | trade_qualification_decision:insufficient_sample, average_net_pnl_not_positive, insufficient_priced_exact_outcomes, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, point_pro |
| `lane:bullish_momentum` | `blocked_missing_readbacks` | 1 | 16 | 0 | 0.04 |  | -48.45 | trade_qualification_decision:quarantine_no_chase, average_net_pnl_not_positive, profit_factor_below_lane_gate, no_chase_active, no_exact_realized_pnl_rows, no_promotion_ready_rows, insufficient_priced_exact_sample, quarantine_or_no_chase_active, required_sourc |
| `filter:lane_gate_self_guardrails_plus_exact_spread_dedupe` | `blocked_missing_readbacks` | 2 | 10 | 0 | 69.14 |  | 34.87 | filter_matrix_status:recommended_paper_shadow_policy_candidate, lost_winner_count_63, required_source_readback_not_loaded |
| `sleeve_next_industrial_cat_mixedexit_v1` | `blocked_missing_readbacks` | 2 | 3 | 0 | 8.21 | 2.19 | 16.73 | thin_sample_variant, worth_status:thin_sample, quote_coverage_33.3_below_90, unpriced_rows_6, required_source_readback_not_loaded |
| `sleeve_next_reit_pld_mixedexit_v1` | `blocked_missing_readbacks` | 2 | 4 | 0 | 3.77 | 0.89 | 9.37 | thin_sample_variant, worth_status:thin_sample, quote_coverage_80.0_below_90, unpriced_rows_1, required_source_readback_not_loaded |
| `sleeve_ticker_iwm` | `blocked_missing_readbacks` | 2 | 21 | 0 | 3.08 | 2.02 | 26.58 | thin_sample_variant, worth_status:thin_sample, quote_coverage_75.0_below_90, unpriced_rows_7, required_source_readback_not_loaded |
Showing `20` of `65` candidates; see JSON for all rows.

## Rejection table with reason codes

No candidates.

## Stress-test summary

- `{"rows": [{"candidate_id": "filter:current_lane_gate_self_guardrails", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 41, "lost_winner_count": 63, "survives_later_date_split": true}, "top_winner_dependency": {"lost_winner_count": 63, "status": "winner_damage_available"}}, {"candidate_id": "filter:current_lane_gate_allowlist", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 39, "lost_winner_count": 60, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 60, "status": "winner_damage_available"}}, {"candidate_id": "lane:volatility_expansion_observation", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "filter:no_extended_damage_tickers", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 33, "lost_winner_count": 21, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 21, "status": "winner_damage_available"}}, {"candidate_id": "filter:no_primary_damage_tickers", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 19, "lost_winner_count": 19, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 19, "status": "winner_damage_available"}}, {"candidate_id": "lane:tracked_winner_observation", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:tracked_winner_primary", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "filter:no_debit_gte_45", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 14, "lost_winner_count": 6, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 6, "status": "winner_damage_available"}}, {"candidate_id": "filter:no_dte_gte_36", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 6, "lost_winner_count": 5, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 5, "status": "winner_damage_available"}}, {"candidate_id": "lane:short_term", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "filter:baseline_all_untracked", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 0, "lost_winner_count": 0, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 0, "status": "winner_damage_available"}}, {"candidate_id": "filter:exact_spread_dedupe_only", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 4, "lost_winner_count": 10, "survives_later_date_split": false}, "top_winner_dependency": {"lost_winner_count": 10, "status": "winner_damage_available"}}, {"candidate_id": "lane:bullish_pullback_observation", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:swing", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:speculative", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:bullish_momentum", "decision": "blocked_missing_readbacks", "stress_results": {}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "filter:lane_gate_self_guardrails_plus_exact_spread_dedupe", "decision": "blocked_missing_readbacks", "stress_results": {"avoided_lte_minus_50": 41, "lost_winner_count": 63, "survives_later_date_split": true}, "top_winner_dependency": {"lost_winner_count": 63, "status": "winner_damage_available"}}, {"candidate_id": "sleeve_next_industrial_cat_mixedexit_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 33.3, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 2.19, "strict_new_trade_count": 3}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_reit_pld_mixedexit_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 80.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.89, "strict_new_trade_count": 0}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_ticker_iwm", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 75.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 2.02, "strict_new_trade_count": 10}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_index_with_iwm_spy_control_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 73.7, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 1.88, "strict_new_trade_count": 4}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:lane_a_chain_native_ret20_4_stop200_time75", "decision": "blocked_missing_readbacks", "stress_results": {"final_holdout_pf_lb_5pct": 0.28, "statistical_confidence": "underpowered"}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "lane:bullish_pullback_core", "decision": "blocked_missing_readbacks", "stress_results": {"final_holdout_pf_lb_5pct": 0.32, "statistical_confidence": "negative_or_flat"}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_index_refill_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.33, "strict_new_trade_count": 6}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_index_move_bucket_baseline_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.87, "strict_new_trade_count": 3}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_defensive_wmt_mixedexit_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 55.0, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 1.02, "strict_new_trade_count": 0}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_reit_industrial_refill_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.17, "strict_new_trade_count": 15}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_defensive_refill_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.13, "strict_new_trade_count": 15}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 69.8, "rolling_status": "watch", "stress_5pct_per_side_profit_factor": 0.97, "strict_new_trade_count": 19}, "top_winner_dependency": {"status": "not_available"}}, {"candidate_id": "sleeve_next_move_bucket_refill_v1", "decision": "blocked_missing_readbacks", "stress_results": {"quote_coverage_pct": 100.0, "rolling_status": "passed", "stress_5pct_per_side_profit_factor": 0.96, "strict_new_trade_count": 23}, "top_winner_dependency": {"status": "not_available"}}], "stress_failed_count": 1, "stress_rows_reported": 65}`

## Split/holdout summary

- `{"forward_holdout_guard_status": "passed", "latest_candidate_entry_date": "2026-03-24", "promotion_ready": false, "protected_forward_holdout_overlap": false, "protected_forward_holdout_start_date": "2026-06-05", "selection_adjusted_bar": 1.18, "split_policy": {"final_holdout_fraction": 0.15, "no_same_entry_date_crosses_splits": true, "split_unit": "unique_entry_date", "train_fraction": 0.6, "validation_fraction": 0.25}, "variants_searched_upstream": 12}`

## Concentration analysis

- `{"flagged_month_candidates": [], "flagged_ticker_candidates": [], "month_concentration_flagged_count": 0, "ticker_concentration_flagged_count": 0}`

## Forward-freeze spec if any

- None. No candidate passed the tournament gates.

## If no candidate survived, next hypothesis queue

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
| `feature_store` | `loaded` | `93.65` | `2026-06-18T06:09:35Z` | `[]` |
| `historical_walk_forward` | `loaded` | `93.65` | `2026-06-18T06:09:39Z` | `[]` |
| `lane_promotion_state` | `loaded` | `10.44` | `2026-06-21T17:22:02Z` | `[]` |
| `missed_failures` | `stale` | `97.58` | `2026-06-18T02:13:48Z` | `["stale_readback"]` |
| `missed_filter_matrix` | `stale` | `97.58` | `2026-06-18T02:13:53Z` | `["stale_readback"]` |
| `monthly_profitability` | `loaded` | `10.44` | `2026-06-21T17:22:27Z` | `[]` |
| `robust_edge_discovery` | `loaded` | `93.65` | `2026-06-18T06:09:46Z` | `[]` |
| `robust_search` | `loaded` | `93.65` | `2026-06-18T06:09:39Z` | `[]` |

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
