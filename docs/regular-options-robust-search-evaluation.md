# Regular Options Robust Search Evaluation

This report is generated from `scripts/build_regular_options_robust_search_evaluation.py`. It evaluates historical trusted intraday exact rows with chronological train/validation/final-holdout splits and fail-closed nomination criteria. It does not create trades, change policy, consume protected forward holdout, lower proof bars, or treat historical rows as fresh forward promotion proof.

## Summary

- Status: `historical_candidates_blocked`.
- Accepted exact trades: `234` / source selected `234`.
- Ready historical candidates: `0` / `3`.
- Variants searched: `12`.
- Selection-adjusted PF-LB bar: `1.18`.
- Regime status: `regime_robust_blocked`.
- Feature-store status: `feature_store_built`; shared dates `393`.
- Feature-store gate: `feature_store_gate_blocked`.
- Source quality gate: `source_quality_gate_blocked`.
- Rejected row counts: `{}`.

## Candidate Table

| Candidate | Type | Status | Total N | Validation N | Final N | Final PF LB | Blockers |
|---|---|---|---:|---:|---:|---:|---|
| `combined_portfolio` | `combined` | `historical_candidate_blocked` | 234 | 61 | 29 | 0.56 | baseline_ablation_report_missing, blocked_missing_market_context, bullish_pullback_core:unpriced_candidates_3, feature_store_shared_quote_dates_393_below_504, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:bullish_pullback_core` | `lane` | `historical_candidate_blocked` | 130 | 38 | 19 | 0.29 | baseline_ablation_report_missing, blocked_missing_market_context, bullish_pullback_core:unpriced_candidates_3, feature_store_shared_quote_dates_393_below_504, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `lane` | `historical_candidate_blocked` | 104 | 22 | 14 | 0.28 | baseline_ablation_report_missing, blocked_missing_market_context, bullish_pullback_core:unpriced_candidates_3, feature_store_shared_quote_dates_393_below_504, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending, validation_exact_trades_below_30 |

## Boundary

A ready row here means only that a historical candidate is eligible to be nominated for future forward tracking. It is not live-validation eligibility and is not a profit claim without later fresh exact realized P&L.
