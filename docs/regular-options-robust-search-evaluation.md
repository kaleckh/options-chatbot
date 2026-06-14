# Regular Options Robust Search Evaluation

This report is generated from `scripts/build_regular_options_robust_search_evaluation.py`. It evaluates historical trusted intraday exact rows with chronological train/validation/final-holdout splits and fail-closed nomination criteria. It does not create trades, change policy, consume protected forward holdout, lower proof bars, or treat historical rows as fresh forward promotion proof.

## Summary

- Status: `historical_candidates_blocked`.
- Accepted exact trades: `231` / source selected `234`.
- Ready historical candidates: `0` / `3`.
- Variants searched: `12`.
- Selection-adjusted PF-LB bar: `1.18`.
- Regime status: `regime_robust_passed`.
- Feature-store status: `feature_store_built`; shared dates `505`.
- Feature-store gate: `feature_store_gate_passed`.
- Source-quality scope policy: `source_quality_scope_policy_loaded`; excluded trades `3`.
- Source quality gate: `source_quality_gate_blocked`.
- Rejected row counts: `{}`.

## Candidate Table

| Candidate | Type | Status | Total N | Validation N | Final N | Final PF LB | Total Max DD | Final Max DD | Blockers |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `combined_portfolio` | `combined` | `historical_candidate_blocked` | 231 | 59 | 28 | 0.61 | 738.83 | 290.42 | bullish_pullback_core:unpriced_candidates_3, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:bullish_pullback_core` | `lane` | `historical_candidate_blocked` | 127 | 36 | 18 | 0.32 | 738.83 | 558.39 | bullish_pullback_core:unpriced_candidates_3, final_holdout_avg_not_above_baseline, final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, final_holdout_pf_not_above_baseline, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `lane` | `historical_candidate_blocked` | 104 | 22 | 14 | 0.28 | 641.27 | 241.64 | final_holdout_bootstrap_pf_lb_not_above_1, final_holdout_exact_trades_below_30, final_holdout_pf_lb_below_selection_adjusted_bar, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, paper_shadow_fill_evidence_pending, source_quality_gate:quality_pending, validation_exact_trades_below_30 |

## Source-Quality Scope Exclusions

| Rule | Date | Ticker | Lane | P&L % | Reason |
|---|---|---|---|---:|---|
| `cvx_zero_bid_tradability_candidate_scope_v1` | `2026-01-13` | `CVX` | `bullish_pullback_core` | 189.08 | zero_bid_tradability_floor_failure |
| `cvx_zero_bid_tradability_candidate_scope_v1` | `2026-01-23` | `CVX` | `bullish_pullback_core` | 255.68 | zero_bid_tradability_floor_failure |
| `cvx_zero_bid_tradability_candidate_scope_v1` | `2026-03-11` | `CVX` | `bullish_pullback_core` | -80.52 | zero_bid_tradability_floor_failure |

## Boundary

A ready row here means only that a historical candidate is eligible to be nominated for future forward tracking. It is not live-validation eligibility and is not a profit claim without later fresh exact realized P&L.
