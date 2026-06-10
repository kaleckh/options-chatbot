# Regular Options Open-Risk Resolution Plan

This report is generated from `scripts/build_regular_options_open_risk_resolution_plan.py`. It is a read-only row plan for resolving open-risk blockers before monthly profitability, live-entry, or promotion decisions.

## Summary

- Status: `open_risk_resolution_plan_clear`.
- Source open-risk status: `open_risk_governor_pass`.
- Live entry allowed: `True`.
- Live exact negative IDs: `[537]`.
- Open rows / negative rows: `5` / `5`.
- Avg / median open P&L: `-54.51` / `-57.66`.
- Plan rows: `0`.
- Live exact plan rows: `0`.
- Display-only SELL rows: `0`.
- Live policy change: `false`.

## Resolution Rows

| Priority | ID | Ticker | Lane | Class | Action | Status | Evidence | P&L | Warning |
|---:|---:|---|---|---|---|---|---|---:|---|

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, auto-close display-only marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote open-risk rows to production proof.

