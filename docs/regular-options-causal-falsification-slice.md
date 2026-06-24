# Regular Options Causal Falsification Slice

This report is generated from `scripts/build_regular_options_causal_falsification_slice.py`. It is a read-only preregistered causal falsification artifact. It does not create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, run live validation, enable auto-track, submit broker orders, or promote any lane.

## Summary

- Status: `existing_surface_falsified_new_causal_branch_still_possible`.
- Continue loop: `true`.
- Significant upgrade available: `true`.
- Frontier status: `current_historical_surface_exhausted_under_current_prohibitions`.
- Frontier candidates / raw-count candidates: `44` / `11`.
- Countable candidate found: `false`.
- Hypothesis status counts: `{"falsified_existing_surface": 4, "not_falsified_requires_next_oracle_or_operator_selection": 1}`.

## Hypotheses

| Hypothesis | Status | Approval Required | Falsification Reason | Next Action |
| --- | --- | --- | --- | --- |
| `raw_count_aggregation_is_enough` | `falsified_existing_surface` | `false` | 11 raw-count candidates exist, but False countable throughput candidates passed strict-new, execution, stress, and lower-bound gates. | Stop raw overlapping aggregation as a profitability branch. |
| `tracked_winner_throughput_addon` | `falsified_existing_surface` | `false` | The highest-count tracked-winner rows are execution-fragile, stress-fragile, negative/flat, or lower-bound blocked. | Do not spend the next loop retuning tracked-winner count variants without new causal evidence. |
| `index_or_iwm_clean_refill_closes_gap` | `falsified_existing_surface` | `false` | The cleaner index/IWM rows are too thin after strict-new opportunity dedupe to reach the 200-row target. | Keep them as small scouts or controls, not the next profitability loop driver. |
| `current_regime_momentum_playbook_existing_artifacts` | `falsified_existing_surface` | `false` | The momentum-edge report found raw count but zero countable profitable momentum-edge candidates; status is `raw_count_available_but_not_countable_profitable_edge`. | A genuinely new causal playbook would need preregistration; existing momentum-compatible artifacts are not enough. |
| `new_preregistered_causal_playbook` | `not_falsified_requires_next_oracle_or_operator_selection` | `false` | This branch has not been tested because the current artifacts only cover implemented historical variants. | Ask GPT-5.5 Pro to choose exactly one new read-only causal playbook design or declare that no significant non-approved upgrade remains. Implementation must remain artifact-only unless operator approval is explicitly granted. |

## Evidence Rows

### `raw_count_aggregation_is_enough`

| Candidate | Decision | Strict New | With Base | PF | Stress PF | Coverage | Unpriced | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `tracked_winner_chain_native_research_all_sleeves` | `blocked_execution_quality` | 112 | 269 | 1.23 | 0.9 | 70.9 | 46 | quote_coverage_70.9_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_46 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `blocked_execution_quality` | 82 | 239 | 1.05 | 0.71 | 79.6 | 21 | quote_coverage_79.6_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_21 |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `rejected_negative_or_flat_edge` | 148 | 305 | 0.68 | 0.46 | 73.3 | 54 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_timeexit_all_sleeves` | `rejected_negative_or_flat_edge` | 140 | 297 | 1.0 | 0.67 | 50.9 | 135 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_cheap_debit_continuity_v1` | `rejected_negative_or_flat_edge` | 130 | 287 | 0.85 | 0.59 | 69.9 | 56 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | `rejected_negative_or_flat_edge` | 108 | 265 | 0.74 | 0.49 | 65.1 | 58 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `volatility_expansion_observation_chain_native_call_fast35_all_sleeves` | `rejected_negative_or_flat_edge` | 108 | 265 | 0.47 | 0.24 | 46.6 | 124 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `relative_strength_pullback_ex_clean_universe_v1` | `rejected_negative_or_flat_edge` | 73 | 230 | 0.16 | 0.11 | 100.0 | 0 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |

### `tracked_winner_throughput_addon`

| Candidate | Decision | Strict New | With Base | PF | Stress PF | Coverage | Unpriced | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `tracked_winner_chain_native_research_all_sleeves` | `blocked_execution_quality` | 112 | 269 | 1.23 | 0.9 | 70.9 | 46 | quote_coverage_70.9_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_46 |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `blocked_execution_quality` | 82 | 239 | 1.05 | 0.71 | 79.6 | 21 | quote_coverage_79.6_below_90, strict_new_row_level_identity_ledger_missing, unpriced_rows_21 |
| `tracked_winner_chain_native_qqq_time65_all_sleeves` | `rejected_negative_or_flat_edge` | 148 | 305 | 0.68 | 0.46 | 73.3 | 54 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_cheap_debit_continuity_v1` | `rejected_negative_or_flat_edge` | 130 | 287 | 0.85 | 0.59 | 69.9 | 56 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |
| `tracked_winner_liquidity_first_contract_hygiene_v1` | `rejected_negative_or_flat_edge` | 108 | 265 | 0.74 | 0.49 | 65.1 | 58 | point_profitability_not_positive, strict_new_row_level_identity_ledger_missing |

### `index_or_iwm_clean_refill_closes_gap`

| Candidate | Decision | Strict New | With Base | PF | Stress PF | Coverage | Unpriced | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `sleeve_next_index_refill_v1` | `blocked_below_strict_new_count` | 6 | 163 | 1.74 | 1.33 | 100.0 | 0 | strict_new_row_level_identity_ledger_missing, strict_new_rows_6_below_required_43, with_candidate_rows_163_below_target_200 |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `blocked_below_strict_new_count` | 19 | 176 | 1.38 | 0.97 | 69.8 | 13 | strict_new_row_level_identity_ledger_missing, strict_new_rows_19_below_required_43, with_candidate_rows_176_below_target_200 |
| `sleeve_ticker_iwm` | `blocked_below_strict_new_count` | 10 | 167 | 3.08 | 2.02 | 75.0 | 7 | strict_new_row_level_identity_ledger_missing, strict_new_rows_10_below_required_43, with_candidate_rows_167_below_target_200 |
| `sleeve_next_index_with_iwm_spy_control_v1` | `blocked_below_strict_new_count` | 4 | 161 | 2.7 | 1.88 | 73.7 | 5 | strict_new_row_level_identity_ledger_missing, strict_new_rows_4_below_required_43, with_candidate_rows_161_below_target_200 |

### `current_regime_momentum_playbook_existing_artifacts`

| Candidate | Decision | Strict New | With Base | PF | Stress PF | Coverage | Unpriced | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `tracked_winner_chain_native_research_all_sleeves` | `raw_count_target_met_but_not_countable_edge` | 112 | 269 | 1.23 | 0.9 | 70.9 | 46 | quote_coverage_70.9_below_90.0, rolling_status_watch, stress_pf_0.9_below_1.0, unpriced_rows_46, worth_status:weak_positive_or_marginal |
| `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `raw_count_target_met_but_not_countable_edge` | 82 | 239 | 1.05 | 0.71 | 79.6 | 21 | quote_coverage_79.6_below_90.0, rolling_status_watch, stress_pf_0.71_below_1.0, unpriced_rows_21, worth_status:weak_positive_or_marginal |
| `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `blocked_below_trade_count_target` | 19 | 176 | 1.38 | 0.97 | 69.8 | 13 | quote_coverage_69.8_below_90.0, rolling_status_watch, stress_pf_0.97_below_1.0, strict_new_rows_19_below_needed_43, unpriced_rows_13, with_candidate_rows_176_below_target_200, worth_status:weak_positive_or_marginal |
| `sleeve_ticker_iwm` | `blocked_below_trade_count_target` | 10 | 167 | 3.08 | 2.02 | 75.0 | 7 | quote_coverage_75.0_below_90.0, rolling_status_watch, strict_new_rows_10_below_needed_43, unpriced_rows_7, with_candidate_rows_167_below_target_200, worth_status:thin_sample |
| `sleeve_next_index_refill_v1` | `blocked_below_trade_count_target` | 6 | 163 | 1.74 | 1.33 | 100.0 | 0 | strict_new_rows_6_below_needed_43, with_candidate_rows_163_below_target_200, worth_status:profitable_but_overlaps |
| `sleeve_next_index_with_iwm_spy_control_v1` | `blocked_below_trade_count_target` | 4 | 161 | 2.7 | 1.88 | 73.7 | 5 | quote_coverage_73.7_below_90.0, rolling_status_watch, strict_new_rows_4_below_needed_43, unpriced_rows_5, with_candidate_rows_161_below_target_200, worth_status:thin_sample |

### `new_preregistered_causal_playbook`

- No existing artifact rows. This branch requires a new preregistered design before testing.

## Next GPT-5.5 Instruction

Use this causal falsification slice in the next GPT-5.5 Pro packet. GPT-5.5 must either select exactly one new read-only causal playbook/design task or return continue_loop=false because no significant upgrade remains without operator approval.

## Branches To Stop

- raw overlapping count aggregation.
- tracked-winner count retuning without new causal evidence.
- clean index/IWM refill as the primary gap closer.
- existing current-regime momentum-compatible artifact aggregation.

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
