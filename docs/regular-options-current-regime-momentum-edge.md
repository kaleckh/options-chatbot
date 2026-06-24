# Regular Options Current-Regime Momentum Edge Test

This report is generated from `scripts/build_regular_options_current_regime_momentum_edge.py`. It is a read-only edge/throughput test over existing current-regime and momentum-compatible replay artifacts. It does not create trades, run live validation, import quotes, mutate evidence stores, change scanner policy, consume protected holdout, or promote a lane.

## Summary

- Status: `raw_count_available_but_not_countable_profitable_edge`.
- Accepted profitability: `false`.
- Target exact rows: `200`.
- Base clean stack exact rows: `157`.
- Raw count target met candidates: `8`.
- Countable momentum edge candidates: `0`.
- Decision counts: `{"blocked_below_trade_count_target": 5, "raw_count_target_met_but_not_countable_edge": 2, "rejected_negative_or_flat_edge": 10}`.
- Conclusion: More historical rows exist, but the high-count current-regime/momentum-compatible candidates are negative, execution-fragile, stress-fragile, or overlap the existing clean stack.

## Candidate Rankings

| Candidate | Decision | Exact | Strict New | With Candidate | PF | Stress PF | Coverage | Worth | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `tracked_winner_chain_native_research_all_sleeves` | `raw_count_target_met_but_not_countable_edge` | 112 | 112 | 269 | 1.23 | 0.9 | 70.9 | `weak_positive_or_marginal` | quote_coverage_70.9_below_90.0, rolling_status_watch, stress_pf_0.9_below_1.0, unpriced_rows_46, worth_status:weak_positive_or_marginal |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `raw_count_target_met_but_not_countable_edge` | 82 | 82 | 239 | 1.05 | 0.71 | 79.6 | `weak_positive_or_marginal` | quote_coverage_79.6_below_90.0, rolling_status_watch, stress_pf_0.71_below_1.0, unpriced_rows_21, worth_status:weak_positive_or_marginal |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `blocked_below_trade_count_target` | 30 | 19 | 176 | 1.38 | 0.97 | 69.8 | `weak_positive_or_marginal` | quote_coverage_69.8_below_90.0, rolling_status_watch, stress_pf_0.97_below_1.0, strict_new_rows_19_below_needed_43, unpriced_rows_13, with_candidate_rows_176_below_target_200, worth_status:weak_positive_or_marginal |
| `sleeve_ticker_iwm` | `blocked_below_trade_count_target` | 21 | 10 | 167 | 3.08 | 2.02 | 75.0 | `thin_sample` | quote_coverage_75.0_below_90.0, rolling_status_watch, strict_new_rows_10_below_needed_43, unpriced_rows_7, with_candidate_rows_167_below_target_200, worth_status:thin_sample |
| `sleeve_next_index_refill_v1` | `blocked_below_trade_count_target` | 116 | 6 | 163 | 1.74 | 1.33 | 100.0 | `profitable_but_overlaps` | strict_new_rows_6_below_needed_43, with_candidate_rows_163_below_target_200, worth_status:profitable_but_overlaps |
| `sleeve_next_index_with_iwm_spy_control_v1` | `blocked_below_trade_count_target` | 14 | 4 | 161 | 2.7 | 1.88 | 73.7 | `thin_sample` | quote_coverage_73.7_below_90.0, rolling_status_watch, strict_new_rows_4_below_needed_43, unpriced_rows_5, with_candidate_rows_161_below_target_200, worth_status:thin_sample |
| `sleeve_next_index_move_bucket_baseline_v1` | `blocked_below_trade_count_target` | 4 | 3 | 160 | 1.7 | 0.87 | 100.0 | `thin_sample` | rolling_status_watch, stress_pf_0.87_below_1.0, strict_new_rows_3_below_needed_43, with_candidate_rows_160_below_target_200, worth_status:thin_sample |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `rejected_negative_or_flat_edge` | 148 | 148 | 305 | 0.68 | 0.46 | 73.3 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_73.3_below_90.0, rolling_status_watch, stress_pf_0.46_below_1.0, unpriced_rows_54, worth_status:not_worth_current_shape |
| `tracked_winner_cheap_debit_continuity_v1` | `rejected_negative_or_flat_edge` | 130 | 130 | 287 | 0.85 | 0.59 | 69.9 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_69.9_below_90.0, rolling_status_watch, stress_pf_0.59_below_1.0, unpriced_rows_56, worth_status:not_worth_current_shape |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | `rejected_negative_or_flat_edge` | 108 | 108 | 265 | 0.74 | 0.49 | 65.1 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_65.1_below_90.0, rolling_status_watch, stress_pf_0.49_below_1.0, unpriced_rows_58, worth_status:not_worth_current_shape |
| `relative_strength_pullback_ex_clean_universe_v1` | `rejected_negative_or_flat_edge` | 79 | 73 | 230 | 0.16 | 0.11 | 100.0 | `not_worth_current_shape` | point_profit_factor_not_above_1, rolling_status_watch, stress_pf_0.11_below_1.0, worth_status:not_worth_current_shape |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | `rejected_negative_or_flat_edge` | 58 | 58 | 215 | 0.98 | 0.7 | 82.9 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_82.9_below_90.0, rolling_status_watch, stress_pf_0.7_below_1.0, unpriced_rows_12, worth_status:not_worth_current_shape |
| `sleeve_next_high_beta_momentum_fast_v1` | `rejected_negative_or_flat_edge` | 46 | 46 | 203 | 0.26 | 0.18 | 79.3 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_79.3_below_90.0, rolling_status_watch, stress_pf_0.18_below_1.0, unpriced_rows_12, worth_status:not_worth_current_shape |
| `sector_rotation_regular_etf_call_stack_v1` | `rejected_negative_or_flat_edge` | 19 | 19 | 176 | 0.19 | 0.14 | 82.6 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_82.6_below_90.0, rolling_status_watch, stress_pf_0.14_below_1.0, strict_new_rows_19_below_needed_43, unpriced_rows_4, worth_status:not_worth_current_shape |
| `smh_semiconductor_call_chain_native_timeexit_all_sleeves` | `rejected_negative_or_flat_edge` | 17 | 17 | 174 | 0.4 | 0.27 | 100.0 | `not_worth_current_shape` | point_profit_factor_not_above_1, rolling_status_watch, stress_pf_0.27_below_1.0, strict_new_rows_17_below_needed_43, worth_status:not_worth_current_shape |
| `sleeve_next_high_beta_survival_v1` | `rejected_negative_or_flat_edge` | 16 | 16 | 173 | 0.11 | 0.07 | 100.0 | `not_worth_current_shape` | point_profit_factor_not_above_1, rolling_status_watch, stress_pf_0.07_below_1.0, strict_new_rows_16_below_needed_43, worth_status:not_worth_current_shape |
| `sleeve_next_index_move_bucket_coverage_v1` | `rejected_negative_or_flat_edge` | 3 | 3 | 160 | 0.0 | 0.0 | 75.0 | `not_worth_current_shape` | point_profit_factor_not_above_1, quote_coverage_75.0_below_90.0, rolling_status_watch, stress_pf_0.0_below_1.0, strict_new_rows_3_below_needed_43, unpriced_rows_1, worth_status:not_worth_current_shape |

## Boundary

- Historical rows are not forward proof: `true`.
- Raw overlapping combined counts are not accepted as throughput unless the strict-new de-duplicated rows clear the gap.
- Positive point PF is not enough without quote coverage, stress, and strict-new count gates.

## Next Oracle Question

Given this read-only edge test, choose the next concrete repo task to increase countable profitable regular-options throughput. Prefer a new causal, point-in-time momentum-continuation playbook or a specific falsification path; do not recommend raw overlapping aggregation, proof-bar reductions, quote imports, live validation, broker actions, scanner-policy release, protected-holdout use, or promotion.

## Prohibited Actions

- `do_not_create_trades_from_current_regime_momentum_edge_test`
- `do_not_submit_broker_orders_from_current_regime_momentum_edge_test`
- `do_not_enable_auto_track_from_current_regime_momentum_edge_test`
- `do_not_enable_live_validation_from_current_regime_momentum_edge_test`
- `do_not_change_scanner_policy_from_current_regime_momentum_edge_test`
- `do_not_change_strategy_logic_from_current_regime_momentum_edge_test`
- `do_not_change_stops_from_current_regime_momentum_edge_test`
- `do_not_change_sizing_from_current_regime_momentum_edge_test`
- `do_not_lower_proof_bars_from_current_regime_momentum_edge_test`
- `do_not_import_quotes_from_current_regime_momentum_edge_test`
- `do_not_mutate_evidence_databases_from_current_regime_momentum_edge_test`
- `do_not_consume_protected_holdout_from_current_regime_momentum_edge_test`
- `do_not_treat_raw_overlapping_trade_counts_as_countable_edge`
- `do_not_treat_historical_rows_as_forward_profitability_proof`
