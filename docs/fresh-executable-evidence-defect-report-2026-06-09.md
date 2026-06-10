# Fresh Executable Evidence Defect Report - 2026-06-09

Generated after the Sprint 3 readback on 2026-06-09 at 17:35 MDT, outside the regular U.S. options quote window.

## Result

The forward funnel still has no measured realized cohort:

- `scripts/build_regular_options_fresh_evidence_loop.py --no-write --json`
- `summary.exact_realized_pnl_count`: `0`
- `summary.promotion_discussion_ready_count`: `0`
- `summary.candidate_count`: `34`

This satisfies the Sprint 3 stop-rule deliverable instead of the 20-row target: the blocking gate is named below, and no stale/display/paper marks were converted into proof.

## Blocking Gates

Largest fresh-evidence blockers:

- `summary.entry_evidence_status_counts.fill_attempt_missing`: `28`
- `summary.entry_evidence_status_counts.fresh_executable_exact_entry`: `6`
- `summary.evidence_bridge_status_counts.non_executable_entry_blocked`: `20`
- `summary.evidence_bridge_status_counts.paper_probation_exact_entry_required`: `8`
- `summary.evidence_bridge_status_counts.exact_exit_pnl_required`: `1`

The single exact-entry row that has a tracked position is QQQ `position_id=537`:

- candidate key: `2026-06-05|volatility_expansion_observation|QQQ|call|2026-06-18|QQQ260618C00728000|QQQ260618C00750000|728.0|750.0`
- `entry_evidence_status`: `fresh_executable_exact_entry`
- `fill_attempt_status`: `logged`
- `fill_outcome`: `paper_fill_recorded`
- `evidence_bridge_status`: `exact_exit_pnl_required`
- `realized_pnl_status`: `missing_realized_pnl`

Open-risk readback also blocks live entry and promotion:

- `scripts/build_regular_options_open_risk_resolution_plan.py --no-write --json`
- `status`: `open_risk_resolution_plan_ready_blocked_for_market_window`
- open rows: `12`
- negative rows: `10`
- average open P&L: `-44.14%`
- median open P&L: `-47.58%`
- top rows requiring review: QQQ `id=537` and SBUX `id=104`

## Required Fix

During the next fresh executable quote window:

1. Refresh executable open-position review for QQQ `id=537`.
2. Refresh executable review for display-only SBUX `id=104`.
3. Collect exact OPRA/NBBO exit evidence for QQQ `id=537`, then rerun `scripts/build_regular_options_fresh_evidence_loop.py`.
4. Rerun open-risk, monthly profitability, and gateboard readbacks before any live-validation or promotion decision.

Do not resolve this defect by using midpoint, stale, display-only SELL, daily/EOD, last-trade, or paper mark evidence.
