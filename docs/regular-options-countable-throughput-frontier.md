# Regular Options Countable Throughput Frontier

This report is generated from `scripts/build_regular_options_countable_throughput_frontier.py`. It is a read-only falsification artifact over existing historical candidates. It does not create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/stops/sizing/proof bars, run live validation, enable auto-track, submit broker orders, or promote any lane.

## Summary

- Status: `current_historical_surface_exhausted_under_current_prohibitions`.
- Countable throughput candidate found: `false`.
- Current historical surface exhausted under current prohibitions: `true`.
- Base clean stack exact rows: `157`.
- Target exact rows: `200`.
- Strict-new gap required: `43`.
- Candidate count: `44`.
- Raw count candidates: `11`.
- Decision counts: `{"blocked_below_strict_new_count": 33, "blocked_execution_quality": 2, "rejected_negative_or_flat_edge": 9}`.
- Row-level ledger status: `run_trade_ledgers_loaded_where_available_strict_new_identity_summary_only`.

## Candidate Frontier

| Candidate | Family | Decision | Exact | Strict New | With Base | PF | Strict PF | PF LB | Stress PF | Coverage | Unpriced | Blockers |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `tracked_winner_chain_native_research_all_sleeves` | `tracked_winner_primary` | `blocked_execution_quality` | 112 | 112 | 269 | 1.23 | 1.23 | 0.56 | 0.9 | 70.9 | 46 | quote_coverage_70.9_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_46 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `tracked_winner_primary` | `blocked_execution_quality` | 82 | 82 | 239 | 1.05 | 1.05 | 0.58 | 0.71 | 79.6 | 21 | quote_coverage_79.6_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_21 |
| `regular_bearish_put_index_narrow_timeexit_all_sleeves` | `bearish_put_debit_spread` | `blocked_below_strict_new_count` | 33 | 33 | 190 | 0.28 | 0.28 | 0.03 | 0.2 | 23.2 | 109 | strict_new_row_level_identity_ledger_missing, strict_new_rows_33_below_required_43, with_candidate_rows_190_below_target_200 |
| `volatility_expansion_observation_chain_native_put_timeexit_all_sleeves` | `volatility_expansion_observation` | `blocked_below_strict_new_count` | 25 | 25 | 182 | 0.38 | 0.38 | 0.0 | 0.27 | 32.1 | 53 | strict_new_row_level_identity_ledger_missing, strict_new_rows_25_below_required_43, with_candidate_rows_182_below_target_200 |
| `bearish_index_put_observation_chain_native_timeexit_all_sleeves` | `bearish_index_put_observation` | `blocked_below_strict_new_count` | 23 | 23 | 180 | 0.37 | 0.37 | 0.0 | 0.27 | 26.4 | 64 | strict_new_row_level_identity_ledger_missing, strict_new_rows_23_below_required_43, with_candidate_rows_180_below_target_200 |
| `sleeve_next_move_bucket_refill_v1` | `move_bucket_combined_control` | `blocked_below_strict_new_count` | 153 | 23 | 180 | 1.27 | 0.13 | 0.96 | 0.96 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_23_below_required_43, with_candidate_rows_180_below_target_200 |
| `range_breakout_observation_chain_native_call_timeexit_all_sleeves` | `range_breakout_observation` | `blocked_below_strict_new_count` | 20 | 20 | 177 | 0.75 | 0.75 | 0.23 | 0.43 | 54.1 | 17 | strict_new_row_level_identity_ledger_missing, strict_new_rows_20_below_required_43, with_candidate_rows_177_below_target_200 |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `iwm_small_cap_risk` | `blocked_below_strict_new_count` | 30 | 19 | 176 | 1.38 | 1.97 | 0.0 | 0.97 | 69.8 | 13 | strict_new_row_level_identity_ledger_missing, strict_new_rows_19_below_required_43, with_candidate_rows_176_below_target_200 |
| `sector_rotation_regular_etf_call_stack_v1` | `sector_rotation_confirmation` | `blocked_below_strict_new_count` | 19 | 19 | 176 | 0.19 | 0.19 | 0.0 | 0.14 | 82.6 | 4 | strict_new_row_level_identity_ledger_missing, strict_new_rows_19_below_required_43, with_candidate_rows_176_below_target_200 |
| `smh_semiconductor_call_chain_native_timeexit_all_sleeves` | `smh_semiconductor` | `blocked_below_strict_new_count` | 17 | 17 | 174 | 0.4 | 0.4 | 0.0 | 0.27 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_17_below_required_43, with_candidate_rows_174_below_target_200 |
| `sleeve_next_high_beta_survival_v1` | `high_beta_momentum_volatility` | `blocked_below_strict_new_count` | 16 | 16 | 173 | 0.11 | 0.11 | 0.0 | 0.07 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_16_below_required_43, with_candidate_rows_173_below_target_200 |
| `sleeve_next_defensive_refill_v1` | `defensive_refill_income` | `blocked_below_strict_new_count` | 143 | 15 | 172 | 1.48 | 0.19 | 1.13 | 1.13 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_15_below_required_43, with_candidate_rows_172_below_target_200 |
| `sleeve_next_reit_industrial_refill_v1` | `reit_rate_sensitive` | `blocked_below_strict_new_count` | 128 | 15 | 172 | 1.53 | 0.12 | 1.14 | 1.17 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_15_below_required_43, with_candidate_rows_172_below_target_200 |
| `sleeve_ticker_iwm` | `iwm_small_cap_risk` | `blocked_below_strict_new_count` | 21 | 10 | 167 | 3.08 | 4.11 | 0.0 | 2.02 | 75.0 | 7 | strict_new_row_level_identity_ledger_missing, strict_new_rows_10_below_required_43, with_candidate_rows_167_below_target_200 |
| `sleeve_next_index_refill_v1` | `etf_index_pullback_control` | `blocked_below_strict_new_count` | 116 | 6 | 163 | 1.74 | 0.0 | 1.28 | 1.33 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_6_below_required_43, with_candidate_rows_163_below_target_200 |
| `range_breakout_observation_chain_native_put_timeexit_all_sleeves` | `range_breakout_observation` | `blocked_below_strict_new_count` | 4 | 4 | 161 | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 | 4 | strict_new_row_level_identity_ledger_missing, strict_new_rows_4_below_required_43, with_candidate_rows_161_below_target_200 |
| `sleeve_next_defensive_pm_mixedexit_v1` | `defensive_refill_income` | `blocked_below_strict_new_count` | 4 | 4 | 161 | None | 153.2 | 0.0 | 17.65 | 57.1 | 3 | strict_new_row_level_identity_ledger_missing, strict_new_rows_4_below_required_43, with_candidate_rows_161_below_target_200 |
| `sleeve_next_index_with_iwm_spy_control_v1` | `etf_index_pullback_control` | `blocked_below_strict_new_count` | 14 | 4 | 161 | 2.7 | 157.26 | 0.48 | 1.88 | 73.7 | 5 | strict_new_row_level_identity_ledger_missing, strict_new_rows_4_below_required_43, with_candidate_rows_161_below_target_200 |
| `sleeve_next_index_move_bucket_baseline_v1` | `etf_index_pullback_control` | `blocked_below_strict_new_count` | 4 | 3 | 160 | 1.7 | 79.0 | 0.0 | 0.87 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_3_below_required_43, with_candidate_rows_160_below_target_200 |
| `sleeve_next_index_move_bucket_coverage_v1` | `etf_index_pullback_control` | `blocked_below_strict_new_count` | 3 | 3 | 160 | None | 85.93 | 0.0 | 0.0 | 75.0 | 1 | strict_new_row_level_identity_ledger_missing, strict_new_rows_3_below_required_43, with_candidate_rows_160_below_target_200 |
| `sleeve_next_industrial_cat_mixedexit_v1` | `industrial_scout` | `blocked_below_strict_new_count` | 3 | 3 | 160 | 8.21 | 8.21 | 0.0 | 2.19 | 33.3 | 6 | strict_new_row_level_identity_ledger_missing, strict_new_rows_3_below_required_43, with_candidate_rows_160_below_target_200 |
| `iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves` | `iwm_small_cap_risk` | `blocked_below_strict_new_count` | 2 | 2 | 159 | 0.0 | 0.0 | 0.0 | 0.0 | 4.7 | 41 | strict_new_row_level_identity_ledger_missing, strict_new_rows_2_below_required_43, with_candidate_rows_159_below_target_200 |
| `bearish_defensive_chain_native_put_timeexit_all_sleeves` | `bearish_defensive` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `bullish_mean_reversion_chain_native_call_timeexit_all_sleeves` | `bullish_mean_reversion` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `kre_regional_bank_call_chain_native_timeexit_all_sleeves` | `kre_regional_bank_observation` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `kre_regional_bank_put_chain_native_timeexit_all_sleeves` | `kre_regional_bank_observation` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `sleeve_next_defensive_wmt_mixedexit_v1` | `defensive_refill_income` | `blocked_below_strict_new_count` | 11 | 0 | 157 | 1.58 | 0.0 | 0.0 | 1.02 | 55.0 | 9 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `sleeve_next_high_beta_put_riskoff_v1` | `high_beta_momentum_volatility` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `sleeve_next_reit_pld_mixedexit_v1` | `reit_rate_sensitive` | `blocked_below_strict_new_count` | 4 | 0 | 157 | 3.77 | 0.0 | 0.0 | 0.89 | 80.0 | 1 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `tlt_duration_shock_call_chain_native_timeexit_all_sleeves` | `tlt_duration_shock` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `tlt_duration_shock_put_chain_native_timeexit_all_sleeves` | `tlt_duration_shock` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `xle_energy_inflation_call_chain_native_timeexit_all_sleeves` | `xle_energy_inflation` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `xle_energy_inflation_put_chain_native_timeexit_all_sleeves` | `xle_energy_inflation` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `xlf_financials_call_chain_native_timeexit_all_sleeves` | `xlf_financials` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `xlf_financials_put_chain_native_timeexit_all_sleeves` | `xlf_financials` | `blocked_below_strict_new_count` | 0 | 0 | 157 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_0_below_required_43, with_candidate_rows_157_below_target_200 |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `tracked_winner_primary` | `rejected_negative_or_flat_edge` | 148 | 148 | 305 | 0.68 | 0.68 | 0.43 | 0.46 | 73.3 | 54 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | `volatility_expansion_observation` | `rejected_negative_or_flat_edge` | 140 | 140 | 297 | 1.0 | 1.0 | 0.55 | 0.67 | 50.9 | 135 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_cheap_debit_continuity_v1` | `tracked_winner_primary` | `rejected_negative_or_flat_edge` | 130 | 130 | 287 | 0.85 | 0.85 | 0.55 | 0.59 | 69.9 | 56 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | `liquidity_first_spread` | `rejected_negative_or_flat_edge` | 108 | 108 | 265 | 0.74 | 0.74 | 0.49 | 0.49 | 65.1 | 58 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` | `volatility_expansion_observation` | `rejected_negative_or_flat_edge` | 108 | 108 | 265 | 0.47 | 0.47 | 0.24 | 0.24 | 46.6 | 124 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `relative_strength_pullback_ex_clean_universe_v1` | `relative_strength_pullback` | `rejected_negative_or_flat_edge` | 79 | 73 | 230 | 0.16 | 0.13 | 0.08 | 0.11 | 100.0 | 0 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | `tracked_winner_primary` | `rejected_negative_or_flat_edge` | 58 | 58 | 215 | 0.98 | 0.98 | 0.39 | 0.7 | 82.9 | 12 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `regular_bearish_put_primary_chain_native_timeexit_all_sleeves` | `bearish_put_debit_spread` | `rejected_negative_or_flat_edge` | 54 | 54 | 211 | 0.33 | 0.33 | 0.12 | 0.23 | 34.4 | 103 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `sleeve_next_high_beta_momentum_fast_v1` | `high_beta_momentum_volatility` | `rejected_negative_or_flat_edge` | 46 | 46 | 203 | 0.26 | 0.26 | 0.07 | 0.18 | 79.3 | 12 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |

## Strict-New Tranche Profitability

| Candidate | Strict New | Strict PF | Strict PF LB | Strict Stress PF | Strict Avg P&L % | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `tracked_winner_chain_native_research_all_sleeves` | 112 | 1.23 | None | 0.9 | 6.73 | `blocked_execution_quality` |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | 82 | 1.05 | None | 0.71 | 1.29 | `blocked_execution_quality` |
| `regular_bearish_put_index_narrow_timeexit_all_sleeves` | 33 | 0.28 | None | None | -32.58 | `blocked_below_strict_new_count` |
| `volatility_expansion_observation_chain_native_put_timeexit_all_sleeves` | 25 | 0.38 | None | None | -28.39 | `blocked_below_strict_new_count` |
| `bearish_index_put_observation_chain_native_timeexit_all_sleeves` | 23 | 0.37 | None | None | -32.36 | `blocked_below_strict_new_count` |
| `sleeve_next_move_bucket_refill_v1` | 23 | 0.13 | None | None | -67.56 | `blocked_below_strict_new_count` |
| `range_breakout_observation_chain_native_call_timeexit_all_sleeves` | 20 | 0.75 | None | None | -5.78 | `blocked_below_strict_new_count` |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | 19 | 1.97 | None | None | 19.77 | `blocked_below_strict_new_count` |
| `sector_rotation_regular_etf_call_stack_v1` | 19 | 0.19 | None | None | -41.76 | `blocked_below_strict_new_count` |
| `smh_semiconductor_call_chain_native_timeexit_all_sleeves` | 17 | 0.4 | None | None | -20.11 | `blocked_below_strict_new_count` |
| `sleeve_next_high_beta_survival_v1` | 16 | 0.11 | None | None | -44.3 | `blocked_below_strict_new_count` |
| `sleeve_next_defensive_refill_v1` | 15 | 0.19 | None | None | -63.34 | `blocked_below_strict_new_count` |
| `sleeve_next_reit_industrial_refill_v1` | 15 | 0.12 | None | None | -68.97 | `blocked_below_strict_new_count` |
| `sleeve_ticker_iwm` | 10 | 4.11 | None | None | 31.12 | `blocked_below_strict_new_count` |
| `sleeve_next_index_refill_v1` | 6 | 0.0 | None | None | -94.65 | `blocked_below_strict_new_count` |
| `range_breakout_observation_chain_native_put_timeexit_all_sleeves` | 4 | 0.0 | None | None | -41.41 | `blocked_below_strict_new_count` |
| `sleeve_next_defensive_pm_mixedexit_v1` | 4 | 153.2 | None | None | 38.3 | `blocked_below_strict_new_count` |
| `sleeve_next_index_with_iwm_spy_control_v1` | 4 | 157.26 | None | None | 39.31 | `blocked_below_strict_new_count` |
| `sleeve_next_index_move_bucket_baseline_v1` | 3 | 79.0 | None | None | 26.33 | `blocked_below_strict_new_count` |
| `sleeve_next_index_move_bucket_coverage_v1` | 3 | 85.93 | None | None | 28.64 | `blocked_below_strict_new_count` |
| `sleeve_next_industrial_cat_mixedexit_v1` | 3 | 8.21 | None | None | 16.73 | `blocked_below_strict_new_count` |
| `iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves` | 2 | 0.0 | None | None | -76.38 | `blocked_below_strict_new_count` |
| `bearish_defensive_chain_native_put_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `bullish_mean_reversion_chain_native_call_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `kre_regional_bank_call_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `kre_regional_bank_put_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `sleeve_next_defensive_wmt_mixedexit_v1` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `sleeve_next_high_beta_put_riskoff_v1` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `sleeve_next_reit_pld_mixedexit_v1` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `tlt_duration_shock_call_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `tlt_duration_shock_put_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `xle_energy_inflation_call_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `xle_energy_inflation_put_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `xlf_financials_call_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `xlf_financials_put_chain_native_timeexit_all_sleeves` | 0 | 0.0 | None | None | 0.0 | `blocked_below_strict_new_count` |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | 148 | 0.68 | None | 0.46 | -10.96 | `rejected_negative_or_flat_edge` |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | 140 | 1.0 | None | 0.67 | 0.06 | `rejected_negative_or_flat_edge` |
| `tracked_winner_cheap_debit_continuity_v1` | 130 | 0.85 | None | 0.59 | -4.76 | `rejected_negative_or_flat_edge` |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | 108 | 0.74 | None | 0.49 | -7.46 | `rejected_negative_or_flat_edge` |
| `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` | 108 | 0.47 | None | 0.24 | -11.88 | `rejected_negative_or_flat_edge` |
| `relative_strength_pullback_ex_clean_universe_v1` | 73 | 0.13 | None | 0.11 | -59.15 | `rejected_negative_or_flat_edge` |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | 58 | 0.98 | None | 0.7 | -0.63 | `rejected_negative_or_flat_edge` |
| `regular_bearish_put_primary_chain_native_timeexit_all_sleeves` | 54 | 0.33 | None | 0.23 | -30.8 | `rejected_negative_or_flat_edge` |
| `sleeve_next_high_beta_momentum_fast_v1` | 46 | 0.26 | None | 0.18 | -31.38 | `rejected_negative_or_flat_edge` |

## Raw Count Blockers

| Candidate | With Base | Strict New | PF | Stress PF | Coverage | Unpriced | Decision | Blockers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `tracked_winner_chain_native_research_all_sleeves` | 269 | 112 | 1.23 | 0.9 | 70.9 | 46 | `blocked_execution_quality` | quote_coverage_70.9_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_46 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | 239 | 82 | 1.05 | 0.71 | 79.6 | 21 | `blocked_execution_quality` | quote_coverage_79.6_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_21 |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | 305 | 148 | 0.68 | 0.46 | 73.3 | 54 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | 297 | 140 | 1.0 | 0.67 | 50.9 | 135 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_cheap_debit_continuity_v1` | 287 | 130 | 0.85 | 0.59 | 69.9 | 56 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | 265 | 108 | 0.74 | 0.49 | 65.1 | 58 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` | 265 | 108 | 0.47 | 0.24 | 46.6 | 124 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `relative_strength_pullback_ex_clean_universe_v1` | 230 | 73 | 0.16 | 0.11 | 100.0 | 0 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | 215 | 58 | 0.98 | 0.7 | 82.9 | 12 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `regular_bearish_put_primary_chain_native_timeexit_all_sleeves` | 211 | 54 | 0.33 | 0.23 | 34.4 | 103 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `sleeve_next_high_beta_momentum_fast_v1` | 203 | 46 | 0.26 | 0.18 | 79.3 | 12 | `rejected_negative_or_flat_edge` | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |

## Stop Verdict

- `countable_throughput_candidate_found`: `false`.
- `current_historical_surface_exhausted_under_current_prohibitions`: `true`.
- If the stop verdict is true, the next loop needs a separate operator approval gate for fresh forward paper-shadow collection, scoped source repair/replay, a new causal playbook, or a new historical data surface/longer lookback.

## Prohibited Actions

- `do_not_create_trades`
- `do_not_submit_broker_orders`
- `do_not_enable_auto_track`
- `do_not_enable_live_validation`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic_for_release`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_databases`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_raw_overlapping_rows`
- `do_not_treat_historical_rows_as_forward_proof`
- `do_not_treat_midpoint_stale_eod_display_manual_last_or_model_marks_as_executable_proof`
- `do_not_drop_zero_bid_untradable_or_unpriced_rows_as_missing_data`
