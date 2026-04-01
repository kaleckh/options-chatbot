# Proposal

## Slug

`broad-ev7-momentum070-control-truth-check`

## Purpose

Freeze the current `ev7 + momentum0.70` champion as the truth-first control and validate it under the narrowed `SPY` / `QQQ` scope.

## Exact Rules

- Cohort: `broad_ev7_momentum070`
- Overrides come only from the frozen phase manifest.
- No live defaults or saved profiles change.
- This run is validation-only, not a new search mutation.

## Evaluation

- `historical_imported`
- `historical_imported_daily`
- `rolling_6m`
- forward-holdout evidence bundle if available

## Notes

- This run exists to anchor honest comparisons for later challengers.
- The result should be treated as the control for the current replay engine and data window, not as a promotion candidate by itself.
