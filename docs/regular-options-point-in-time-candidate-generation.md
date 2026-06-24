# Regular Options Point-In-Time Candidate Generation

This report is generated from `scripts/build_regular_options_point_in_time_candidate_generation.py`. It reconstructs candidate-generation coverage from existing selected-trade source artifacts and their `daily_selection_diagnostics`. It is read-only and does not import quotes, mutate evidence stores, overwrite canonical multilane artifacts, change policy, or create live trades.

## Summary

- Status: `blocked_point_in_time_candidate_generation`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Requested months: `24`.
- Candidate-generation covered months: `8`.
- Selected months with rows: `8`.
- Selected rows in window: `231`.
- Zero-selection months explicit: `False`.
- Source reproduction: `passed` over `231` rows.

## Source Artifacts

| Playbook | Diagnostic Months | Trades | Unpriced | Entrypoints |
|---|---:|---:|---:|---|
| `sleeve_pf59_coverage_a_refill_v1` | 8 | 130 | 3 | scripts/run_bullish_pullback_sleeves.py |
| `lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1` | 8 | 155 | 137 | scripts/run_bullish_pullback_next_round.py |

## Monthly Diagnostics

| Month | Covered | Attempted | Selected | Stage | Reasons |
|---|---:|---:|---:|---|---|
| `2024-06` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-07` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-08` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-09` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-10` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-11` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2024-12` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-01` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-02` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-03` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-04` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-05` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-06` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-07` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2025-08` | True | True | 23 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2025-09` | True | True | 43 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2025-10` | True | True | 41 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2025-11` | True | True | 11 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2025-12` | True | True | 48 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2026-01` | True | True | 29 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2026-02` | True | True | 24 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2026-03` | True | True | 12 | `selected_trades_available_after_candidate_generation` | quote_history_available, feature_store_available, source_reproduction_passed, all_source_artifacts_have_daily_diagnostics, selected_rows_present |
| `2026-04` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |
| `2026-05` | False | False | 0 | `historical_depth_candidate_generation_diagnostics_missing_for_month` | quote_history_available, feature_store_available, source_reproduction_passed, source_artifact_daily_diagnostics_missing, zero_selection_month_not_proven |

## Blockers

- `calendar_months_covered_8_below_requested_24`
- `selected_trade_calendar_coverage_not_proven`
- `historical_depth_candidate_generation_diagnostics_missing_for_month`
- `historical_depth_existing_replay_artifacts_only_8_diagnostic_months`

## Boundary

A month is covered only when every contributing selected-trade source artifact has daily candidate-generation diagnostics for that month and the source-reproduction check passes. Existing selected rows alone and quote-history depth alone do not prove zero-selection months.

