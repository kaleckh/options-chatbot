# Regular Options Evidence Blocker Burn-Down

No robust candidate passed, and local artifacts do not expose an actionable row-level repair queue.

## Current Algorithm Status

- Overall status: `blocked_stale_readbacks`.
- Hypothesis tournament: `None`.
- Robust-edge discovery: `None`.
- Best lane: `None` / `None`.
- Best PF / avg net P&L: `None` / `None`.
- Promotion ready: `None`.
- Live entry / auto-track / broker order allowed: `False` / `False` / `False`.

## Why No Robust Candidate Passed

- The current best lane is still paper-shadow/probation, not robust/live-ready.
- The historical combined candidate remains blocked by final-holdout depth and PF lower-bound quality.
- Source-quality, unpriced, zero-bid/tradability, lookahead-only, exhausted-source, stress, and concentration blockers remain separated rather than merged into a false positive.

## Ranked Repair Queue

No rows.

## Source Replay Queue

No rows.

## Do-Not-Repeat Exhausted Queue

No rows.

## Zero-Bid/Tradability Failures

- Count: `0`.
- Zero-bid/non-executable rows are execution/tradability failures, not provider-missing rows.

## Diagnostic Lookahead-Only Queue

No rows.

## Holdout Gap: 28 To 30 Analysis

- Current final-holdout rows: `None`.
- Target final-holdout rows: `None`.
- Gap rows: `None`.
- Actionable exact repair rows exposed: `None`.
- Can currently prove the exact 28-to-30 bridge: `None`.
- Conclusion: None

## PF Lower-Bound Gap: 0.61 To >1.0 Analysis

- Current PF lower bound: `None`.
- Target PF lower bound: `None`.
- Repairable exact blockers that could affect replay distribution: `None`.
- Count repair is not PF repair: `None`.
- Conclusion: None

## Safe Plan-Only/Dry-Run Command Hints

- `uv run --locked python scripts/build_regular_options_repair_attempt_readback.py --no-write --json`
- `uv run --locked python scripts/build_regular_options_repair_burndown.py --no-write --json`
- `uv run --locked python scripts/build_regular_options_profit_capture_queue.py --no-write --json`
- `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --plan-only --json`
- `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --dry-run --json`

## Post-Repair Rerun Command Order

- `npm run options:features:regular-options`
- `npm run options:robust-search:regular-options`
- `npm run options:replay:regular-options-walk-forward`
- `npm run options:research:robust-edge`
- `npm run options:research:hypothesis-tournament`
- `npm run options:research:evidence-blocker-burndown`
- `npm run options:audit:monthly-profitability`

## What Not To Repair

- Do not repeat exhausted current-source exact-date loops without a new source or materially new evidence.
- Do not use lookahead-only rows as proof.
- Do not treat zero-bid/non-executable rows as missing data.
- Do not repair no-chase/quarantined lanes for promotion; keep them parked except for falsification.

## Source Artifacts And Staleness

| Path | Required | Status | Generated | Age Hours |
| --- | --- | --- | --- | --- |
| data/profitability-lab/regular-options-hypothesis-tournament/latest.json | True | stale | 2026-06-22T03:48:35Z | 133.9 |
| data/profitability-lab/regular-options-robust-edge-discovery/latest.json | True | loaded | 2026-06-27T03:54:10Z | 13.81 |
| data/profitability-lab/regular-options-repair-burndown/latest.json | True | loaded | 2026-06-27T03:48:40Z | 13.9 |
| data/profitability-lab/regular-options-repair-attempts/latest.json | False | loaded | 2026-06-05T01:06:45Z | 544.6 |
| data/profitability-lab/regular-options-profit-capture-queue/latest.json | False | loaded | 2026-06-27T03:48:39Z | 13.9 |
| data/profitability-lab/regular-options-multilane/latest.json | False | stale |  |  |
| data/forward-tracking/monthly_all_lanes_profitability_audit_latest.json | False | loaded | 2026-06-27T03:50:51Z | 13.86 |
| data/forward-tracking/lane_promotion_state_latest.json | False | loaded | 2026-06-27T03:50:51Z | 13.86 |
| data/forward-tracking/regular_options_trade_qualification_latest.json | False | loaded | 2026-06-27T03:50:52Z | 13.86 |
| data/forward-tracking/regular_options_paper_shadow_evidence_plan_latest.json | False | loaded | 2026-06-27T03:52:56Z | 13.83 |
| data/forward-tracking/regular_options_market_window_evidence_checklist_latest.json | False | loaded | 2026-06-27T03:54:10Z | 13.81 |

## Non-Goals

- This workflow does not create trades.
- This workflow does not submit broker orders.
- This workflow does not enable auto-track.
- This workflow does not enable live validation.
- This workflow does not change scanner policy.
- This workflow does not change stops.
- This workflow does not change sizing.
- This workflow does not lower proof bars.
- This workflow does not mutate evidence databases.
- This workflow does not prove future profits with certainty.
