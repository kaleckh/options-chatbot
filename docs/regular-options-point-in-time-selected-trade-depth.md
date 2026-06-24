# Regular Options Point-In-Time Selected Trade Depth

This report is generated from `scripts/build_regular_options_point_in_time_selected_trade_depth.py`. It traces whether the requested historical calendar window has selected-trade coverage or a named blocker by month. It is read-only and does not import quotes, mutate evidence stores, overwrite canonical selected-trade artifacts, create trades, or change policy.

## Summary

- Status: `blocked_point_in_time_selected_trade_depth`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Requested months: `24`.
- Selected-trade covered months: `0`.
- Selected months with rows: `0`.
- Selected rows in window: `0`.
- Zero-selection months explicit: `False`.
- Candidate generation proven: `False`.
- Quote-history shared dates: `505` through `2026-06-04`.

## Monthly Diagnostics

| Month | Covered | Selected | Stage | Reasons |
|---|---:|---:|---|---|
| `2024-06` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-07` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-08` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-09` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-10` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-11` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2024-12` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-01` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-02` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-03` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-04` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-05` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-06` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-07` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-08` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-09` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-10` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-11` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2025-12` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2026-01` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2026-02` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2026-03` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2026-04` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |
| `2026-05` | False | 0 | `historical_depth_no_candidate_generator_for_month` | quote_history_available, feature_store_available, candidate_generation_not_proven_for_zero_selection_month, zero_selection_month_not_proven |

## Blockers

- `historical_depth_no_candidate_generator_for_month`
- `historical_depth_current_definition_replay_only`
- `calendar_months_covered_0_below_requested_24`
- `selected_trade_calendar_coverage_not_proven`

## Boundary

A month with quote coverage but no proven point-in-time candidate-generation run is not treated as a safe zero-selection month. The next implementation step after this report is the missing candidate generator for any unproven months.

