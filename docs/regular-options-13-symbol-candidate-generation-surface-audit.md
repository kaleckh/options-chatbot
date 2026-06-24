# Regular Options 13-Symbol Candidate-Generation Surface Audit

This report is generated from `scripts/build_regular_options_13_symbol_candidate_generation_surface_audit.py`. It audits whether the trusted 13-symbol quote surface can honestly support a bounded no-write candidate-generation replay over the requested historical window.

## Summary

- Status: `blocked_13_symbol_candidate_generation_surface_audit`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Frozen universe: `SPY, QQQ, IWM, AAPL, GOOGL, UNH, LLY, JNJ, XOM, CVX, COP, NEM, DIA`.
- Quote-surface months available: `24`.
- Candidate-generation months covered: `0`.
- Feature surface: `valid_13_symbol_point_in_time_quote_surface`.
- Candidate surface frozen 13-symbol: `False`.
- Non-13 selected rows: `0`.
- CVX scope enforced: `True` via `cvx_zero_bid_tradability_candidate_scope_v1`.
- Runner support: `read_only_no_write_runner_available`.

## Month Diagnostics

| Month | Quote Surface | Candidate Proven | Explicit Zero | Selected | Counted | Statuses |
|---|---:|---:|---:|---:|---:|---|
| `2024-06` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-07` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-08` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-09` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-10` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-11` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2024-12` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-01` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-02` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-03` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-04` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-05` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-06` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-07` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-08` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-09` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-10` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-11` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2025-12` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2026-01` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2026-02` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2026-03` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2026-04` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |
| `2026-05` | True | False | False | 0 | False | quote_surface_available, candidate_generation_missing, cannot_count_zero_selection_month |

## Blockers

- `candidate_generation_months_0_below_requested_24`
- `existing_candidate_generation_surface_not_frozen_13_symbol`
- `missing_candidate_generation_diagnostics`
- `not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof`
- `quote_depth_only_months_cannot_count`
- `source_artifact_universe_not_13_symbol`

## Boundary

A month is countable only when candidate generation, explicit no-pick proof, or selected rows are proven on the frozen 13-symbol surface. Quote-history depth alone is not a zero-selection month and cannot satisfy the 20-train plus latest-4 audit question.

