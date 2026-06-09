# Regular Options Minute-Exit Quote Import Plan

This report is generated from `scripts/build_regular_options_minute_exit_quote_import_plan.py`. It is a read-only import/query plan for exact OPRA/NBBO minute quote coverage needed before minute-level exit replay.

## Summary

- Status: `no_minute_exit_quote_seeds_to_plan`.
- Source readiness: `minute_exit_replay_readiness_readback` / `minute_exit_replay_coverage_ready`.
- Source entry / position seeds: `12` / `1`.
- Exact quote demands: `0` parsed, `0` unparsed.
- Command groups: `0`.
- Dates: `[]`.
- Underlyings: `[]`.
- Replay P&L status: `available_in_source_readiness`.
- Live policy change: `false`.

## Command Groups

| Group | Priority | Date | Right | Symbols | Time Window | DTE | Demands | Seeds | Contracts |
|---|---:|---|---|---|---|---|---:|---:|---:|

## Commands

No import/query command groups are available.
## Exact Contract Manifest

| Priority | Contract | Date | Window | Leg | Replay Eligibility | Ticker | Lane |
|---:|---|---|---|---|---|---|---|

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, change scanner policy, change stops, change sizing, synthesize minute-exit P&L, lower exact OPRA/NBBO proof bars, or promote quote-import rows to production proof.

