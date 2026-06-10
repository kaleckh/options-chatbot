# Fresh Executable Evidence Defect Report - 2026-06-09

Generated after the Sprint 3 readback on 2026-06-09 at 17:35 MDT, then refreshed on 2026-06-10 after starting/probing local market-data paths.

## Result

The forward funnel still has no measured realized cohort:

- `scripts/build_regular_options_fresh_evidence_loop.py --no-write --json`
- `summary.exact_realized_pnl_count`: `0`
- `summary.promotion_discussion_ready_count`: `0`
- `summary.candidate_count`: `34`

This satisfies the Sprint 3 stop-rule deliverable instead of the 20-row target: the blocking gate is named below, and no stale/display/paper marks were converted into proof. The remaining blocker is not ThetaTerminal availability or a generic GitHub/push issue.

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

- original 2026-06-09 readback: `open_risk_resolution_plan_ready_blocked_for_market_window`
- top rows requiring review at that time: QQQ `id=537` and SBUX `id=104`

## Market-Data Follow-Up

On 2026-06-10, local ThetaTerminal v3 was already listening on `127.0.0.1:25503`. The exact-expiration importer path was added so targeted ThetaData history calls can request one expiration instead of the wildcard chain when needed. A 2026-06-08 exact-expiration import for QQQ/SBUX 2026-06-18 calls wrote batch `2124` with `1,016` trusted `thetadata_opra_nbbo_1m` rows and `0` rejects. The 2026-06-09 exact-expiration ThetaData history query still returned no data for the same contracts, so the blocker was provider history availability for that date, not a down terminal.

Alpaca OPRA latest snapshots supplied fresh 2026-06-09 bid/ask quotes for the same QQQ and SBUX contracts. That exposed and fixed a side-aware execution bug: buy/cover execution can use an ask when bid is zero, while sell-to-close still requires a positive bid and debit-spread entry still requires the short leg to have a positive bid.

After rerunning tracked-position review:

- QQQ `id=537` has a fresh executable exact HOLD review, with side-aware spread exit value `3.6855`, net P&L `-59.35%`, and price trigger OK.
- SBUX `id=104` closed from an executable exact side-aware zero exit, with net P&L `-100.0%`. This was a tracked-position state update only; no broker order was submitted.
- `scripts/audit_regular_open_position_risk.py --json` now reports `open_risk_governor_pass`, `live_entry_allowed=true`, `blockers=[]`, `live_exact_negative_resolved_hold_ids=[537]`, and `live_exact_negative_unresolved_ids=[]`.
- `scripts/build_regular_options_open_risk_resolution_plan.py --json` now reports `open_risk_resolution_plan_clear`, `plan_row_count=0`, and `next_evidence_queue=[]`.

## Remaining Required Fix

The fresh-evidence loop still reports:

- `summary.exact_realized_pnl_count`: `0`
- `summary.promotion_discussion_ready_count`: `0`
- `summary.evidence_bridge_status_counts.exact_exit_pnl_required`: `1`
- QQQ `position_id=537`: `evidence_bridge_status=exact_exit_pnl_required`, `realized_pnl_status=missing_realized_pnl`

The exact remaining gate is a legitimate trusted OPRA/NBBO realized exit for QQQ `id=537`, or a different fresh candidate that reaches a legitimate realized exit. QQQ must not be closed just to manufacture evidence while the current executable review says HOLD and price-trigger checks pass.

Next actions:

1. Continue monitoring QQQ `id=537` with executable OPRA/NBBO quotes until stop, target, time-exit, or another policy-defined exit condition fires.
2. Capture durable fill-attempt evidence for the `28` missing-fill-attempt candidates and exact entry evidence for the `8` paper/probation rows without loosening guardrails.
3. Rerun `scripts/build_regular_options_fresh_evidence_loop.py`, monthly profitability, and gateboard readbacks after the next legitimate exact realized exit.

Do not resolve this defect by using midpoint, stale, display-only SELL, daily/EOD, last-trade, or paper mark evidence.
