# Regular Options Forward Evidence-Bar Throughput Projection

- Status: `bar_unreachable_without_state_change`.
- Freeze date: `2026-06-14`.
- Cohort eval date: `2026-07-28`.
- Four-month forward audit end: `2026-10-14`.
- Blockers: `[]`.

## Horizon Projections

| Horizon | Market Days | Remaining | Completed | Required Rate | Current Rate | Projected Rows | Reachable |
|---|---:|---:|---:|---:|---:|---:|---|
| `cohort_eval_2026_07_28` | 30 | 15 | 0 / 30 | 2.0 | 0.0 | 0.0 | false |
| `freeze_anchored_four_month_forward_2026_10_14` | 85 | 70 | 0 / 30 | 0.428571 | 0.0 | 0.0 | false |

## Separate Denominators

- Tracker denominator `filtered_forward_paper_shadow_tracker`: matched `0`, completed `0`.
- Materializer denominator `scanner_materializer_parity_diff_materializer_window`: in-window rows `182`, filter-matched selected `0`, historical upper-bound rows/market-day `0.607143`.
- Scheduled-scan denominator `forward_candidate_throughput_audit_scheduled_scan_drops`: drops `571`, symbol drop reasons `571`, near-miss status `symbol_level_near_miss_table_ready`.

## Dominant Starvation Stage

- Status: `forward_candidate_starvation`.
- Reason: No filter-matched materializer rows and no tracker matches in the observed post-freeze window.

## Boundary

This projection is not profitability evidence and is not a promotion input. Only fresh post-freeze executable exact rows evaluated by the frozen evidence-bar evaluator can support a bar_met_pending_operator_review outcome, and that outcome authorizes nothing.

This report is read-only. It does not import quotes, mutate evidence stores, append cohorts, change scanner policy, change filters, lower proof bars, enable live validation, enable auto-track, submit broker orders, consume protected holdout, or promote a lane.
