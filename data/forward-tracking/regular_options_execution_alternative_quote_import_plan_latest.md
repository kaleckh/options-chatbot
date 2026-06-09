# Regular Options Execution Alternative Quote Import Plan

This report is generated from `scripts/build_regular_options_execution_alternative_quote_import_plan.py`. It is a read-only import/query plan for exact OPRA/NBBO quote demands produced by the execution-alternative replay coverage layer.

## Summary

- Status: `no_quote_demands_to_plan`.
- Source coverage: `execution_alternative_replay_coverage_readback` / `no_missing_quote_demands`.
- Exact quote demands: `0` parsed, `0` unparsed.
- Entry / exit demands: `0` / `0`.
- Command groups: `0`.
- Dates: `[]`.
- Underlyings: `[]`.
- Live policy change: `false`.
- Theta probe: `not_requested`.

## Command Groups

| Group | Priority | Date | Phase | Right | Symbols | Time Window | DTE | Demands | Contracts |
|---|---:|---|---|---|---|---|---|---:|---:|

## Commands

No import/query command groups are available.
## Exact Contract Manifest

| Priority | Contract | Date | Time | Phase | Right | Expiry | Strike | Usage | Missing Reasons |
|---:|---|---|---|---|---|---|---:|---|---|

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|

## Boundary

This import plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, change scanner policy, change contract selection, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote replay rows to production proof.

