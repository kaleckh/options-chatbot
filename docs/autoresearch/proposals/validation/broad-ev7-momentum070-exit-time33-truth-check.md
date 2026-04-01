# Proposal

## Slug

`broad-ev7-momentum070-exit-time33-truth-check`

## Purpose

Validate the only surviving exit challenger, `time_exit_pct = 33`, against the frozen `ev7 + momentum0.70` control under the narrowed `SPY` / `QQQ` truth-first scope.

## Exact Rules

- Cohort: `broad_ev7_momentum070_exit_time33`
- Overrides come only from the frozen phase manifest.
- No live defaults or saved profiles change.
- This run is validation-only, not a new search mutation.

## Evaluation

- compare directly to the same-day control run
- `historical_imported`
- `historical_imported_daily`
- `rolling_6m`
- forward-holdout evidence bundle if available

## Notes

- Reject if imported truth collapses relative to the control or if the corroborating momentum slice meaningfully degrades.
- Keep this as the only active exit challenger until validation finishes.
