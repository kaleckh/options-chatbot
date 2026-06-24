# Regular Options 13-Symbol Frozen Candidate Generation Denominator v2

This generated artifact materializes the daily candidate/no-pick/blocker denominator for the frozen 13-symbol surface. It is read-only and does not run live scans, create trades, import quotes, mutate evidence stores, append forward cohorts, consume protected holdout, change scanner or strategy logic, or promote any lane.

## Summary

- Status: `blocked_13_symbol_frozen_candidate_generation_denominator_v2`.
- Requested window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Requested months: `24`.
- Latest four months: `2026-02, 2026-03, 2026-04, 2026-05`.
- Market-date denominator rows: `494`.
- Baseline quote months: `24`.
- Baseline source-surface months: `0`.
- Runner status: `read_only_no_write_runner_available`.
- Latest-four strict-new candidates: `0`.
- Blocked days: `494`.
- Accepted profitability: `False`.

## Daily Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_daily_diagnostics` | `327` |
| `blocked_missing_runner_output` | `167` |

## Blockers

- `blocked_daily_candidate_generation_coverage`
- `blocked_latest_four_month_rows_below_30`
- `candidate_generation_months_0_below_requested_24`
- `missing_daily_candidate_generation_diagnostics`
- `missing_frozen_13_symbol_candidate_generation_engine`
- `outside_universe_source_rows_present`
- `source_artifact_universe_not_13_symbol`

## Boundary

This artifact only decides whether the frozen 13-symbol candidate-generation denominator is auditable. Quote coverage alone does not count as candidate-generation proof, and historical rows remain non-forward proof.

