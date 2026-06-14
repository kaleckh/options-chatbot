# Regular Options Historical Walk-Forward Workflow

This report is generated from `scripts/build_regular_options_historical_walk_forward.py`. It refreshes the point-in-time feature-store readback, runs the robust historical search evaluation, ingests the all-planned peer sleeve readback, and combines the outputs into an operator-facing walk-forward summary. It is read-only research and does not create trades, change scanner policy, consume protected forward holdout, lower proof bars, or treat historical rows as fresh forward proof.

## Summary

- Status: `historical_walkforward_ran_candidates_blocked`.
- Feature store: `feature_store_built` with `505` shared quote dates through `2026-06-04`.
- Robust search: `historical_candidates_blocked`.
- Accepted exact trades: `231`.
- Ready historical candidates: `0` / `3`.
- Variants searched: `12`; selection-adjusted PF-LB bar `1.18`.
- All-planned sleeves: `all_planned_sleeves_loaded`; tested `44` / `44` as of `2026-06-04`.
- Latest candidate entry date: `2026-03-24`.
- Protected forward holdout starts: `2026-06-05`; overlap `False`.
- Forward holdout guard: `passed`.
- Promotion ready: `False`.
- Repair queue: `3` high-priority rows / `19` total.

## Forward Holdout Guard

- Status: `passed`.
- Contract status: `active`.
- Date basis: `candidate_entry_date`.
- Protected start: `2026-06-05`.
- Latest candidate entry: `2026-03-24`.
- Overlap: `False`.
- Blockers: `none`.

## Candidate Results

| Candidate | Status | Total N | Val N | Holdout N | Holdout PF | Holdout PF LB | Holdout DD | Total DD | Blockers |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `combined_portfolio` | `historical_candidate_blocked` | 231 | 59 | 28 | 1.2725 | 0.61 | 290.42 | 738.83 | bullish_pullback_core:unpriced_candidates_3, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:bullish_pullback_core` | `historical_candidate_blocked` | 127 | 36 | 18 | 0.8074 | 0.32 | 558.39 | 738.83 | bullish_pullback_core:unpriced_candidates_3, final_holdout_avg_not_above_baseline, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, final_holdout_pf_not_above_baseline, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `historical_candidate_blocked` | 104 | 22 | 14 | 1.2143 | 0.28 | 241.64 | 641.27 | final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending, validation_exact_trades_below_30 |

## Repair Queue

| Rank | Priority | Category | Subject | Targets | Action | Permission | Holdout Boundary |
|---:|---|---|---|---:|---|---|---|
| 1 | `high` | `candidate_source_quality_repair` | `combined_portfolio` |  | repair_source_quality_and_unpriced_rows_before_any_nomination | `requires_explicit_approval_before_evidence_store_mutation` | `protected_forward_holdout_must_remain_unused` |
| 2 | `high` | `candidate_source_quality_repair` | `lane:bullish_pullback_core` |  | repair_source_quality_and_unpriced_rows_before_any_nomination | `requires_explicit_approval_before_evidence_store_mutation` | `protected_forward_holdout_must_remain_unused` |
| 3 | `high` | `candidate_source_quality_repair` | `lane:lane_a_chain_native_ret20_4_stop200_time75` |  | repair_source_quality_and_unpriced_rows_before_any_nomination | `requires_explicit_approval_before_evidence_store_mutation` | `protected_forward_holdout_must_remain_unused` |
| 4 | `medium` | `candidate_zero_bid_economics` | `combined_portfolio` |  | separate_zero_bid_artifacts_from_fillable_edge_or_keep_lane_parked | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 5 | `medium` | `candidate_zero_bid_economics` | `lane:lane_a_chain_native_ret20_4_stop200_time75` |  | separate_zero_bid_artifacts_from_fillable_edge_or_keep_lane_parked | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 6 | `medium` | `candidate_sample_size_gap` | `combined_portfolio` |  | fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows | `requires_new_forward_or_pre_holdout_evidence_repair` | `do_not_use_protected_forward_holdout_to_fill_sample_gap` |
| 7 | `medium` | `peer_variant_stress_repair` | `sleeve_next_reit_industrial_refill_v1` |  | repair_stress_or_risk_shape_before_counting | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 8 | `medium` | `candidate_sample_size_gap` | `lane:bullish_pullback_core` |  | fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows | `requires_new_forward_or_pre_holdout_evidence_repair` | `do_not_use_protected_forward_holdout_to_fill_sample_gap` |
| 9 | `medium` | `candidate_sample_size_gap` | `lane:lane_a_chain_native_ret20_4_stop200_time75` |  | fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows | `requires_new_forward_or_pre_holdout_evidence_repair` | `do_not_use_protected_forward_holdout_to_fill_sample_gap` |
| 10 | `low` | `candidate_statistical_bar` | `combined_portfolio` |  | do_not_promote_until_lower_bound_clears_adjusted_bar | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 11 | `low` | `candidate_statistical_bar` | `lane:bullish_pullback_core` |  | do_not_promote_until_lower_bound_clears_adjusted_bar | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 12 | `low` | `candidate_statistical_bar` | `lane:lane_a_chain_native_ret20_4_stop200_time75` |  | do_not_promote_until_lower_bound_clears_adjusted_bar | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 13 | `low` | `peer_variant_overlap_review` | `sleeve_next_index_refill_v1` |  | do_not_count_as_gap_closer_without_non_overlapping_edge | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 14 | `low` | `peer_variant_hypothesis_review` | `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` |  | require_causal_hypothesis_before_tuning_or_more_replay | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |
| 15 | `low` | `peer_variant_hypothesis_review` | `sleeve_next_defensive_refill_v1` |  | require_causal_hypothesis_before_tuning_or_more_replay | `read_only_research_ok` | `protected_forward_holdout_must_remain_unused` |

Showing top `15` of `19` repair rows; see the JSON artifact for the full queue.

## Peer/Variant Sleeve Results

| Variant | Worth Status | Exact N | PF | Avg % | Coverage % | Stress PF | Strict New | Gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `sleeve_next_reit_industrial_refill_v1` | `repair_stress_before_counting` | 128 | 1.53 | 15.94 | 100.0 | 1.17 | 15 | 28 |
| `sleeve_next_index_refill_v1` | `profitable_but_overlaps` | 116 | 1.74 | 20.49 | 100.0 | 1.33 | 6 | 37 |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | `weak_positive_or_marginal` | 140 | 1.0 | 0.06 | 50.9 | 0.67 | 140 | 0 |
| `tracked_winner_chain_native_research_all_sleeves` | `weak_positive_or_marginal` | 112 | 1.23 | 6.73 | 70.9 | 0.9 | 112 | 0 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `weak_positive_or_marginal` | 82 | 1.05 | 1.29 | 79.6 | 0.71 | 82 | 0 |
| `sleeve_next_move_bucket_refill_v1` | `weak_positive_or_marginal` | 153 | 1.27 | 8.52 | 100.0 | 0.96 | 23 | 20 |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `weak_positive_or_marginal` | 30 | 1.38 | 9.06 | 69.8 | 0.97 | 19 | 24 |
| `sleeve_next_defensive_refill_v1` | `weak_positive_or_marginal` | 143 | 1.48 | 14.43 | 100.0 | 1.13 | 15 | 28 |
| `sleeve_ticker_iwm` | `thin_sample` | 21 | 3.08 | 26.58 | 75.0 | 2.02 | 10 | 33 |
| `sleeve_next_index_with_iwm_spy_control_v1` | `thin_sample` | 14 | 2.7 | 25.22 | 73.7 | 1.88 | 4 | 39 |
| `sleeve_next_industrial_cat_mixedexit_v1` | `thin_sample` | 3 | 8.21 | 16.73 | 33.3 | 2.19 | 3 | 40 |
| `sleeve_next_index_move_bucket_baseline_v1` | `thin_sample` | 4 | 1.7 | 8.16 | 100.0 | 0.87 | 3 | 40 |
| `sleeve_next_defensive_wmt_mixedexit_v1` | `thin_sample` | 11 | 1.58 | 10.41 | 55.0 | 1.02 | 0 | 43 |
| `sleeve_next_reit_pld_mixedexit_v1` | `thin_sample` | 4 | 3.77 | 9.37 | 80.0 | 0.89 | 0 | 43 |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `not_worth_current_shape` | 148 | 0.68 | -10.96 | 73.3 | 0.46 | 148 | 0 |

Showing top `15` of `44` variant rows; see the JSON artifact for the full table.

## Boundary

A ready candidate here means only that historical evidence is strong enough to nominate or refreeze future forward tracking. Production proof still requires fresh exact realized OPRA/NBBO P&L after the applicable freeze date.
