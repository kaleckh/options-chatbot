# Regular Options Suggested-Trade Review Plan

This report is generated from `scripts/build_regular_options_suggested_trade_review_plan.py`. It is a read-only row plan for refreshing suggested-trade attention rows before monthly profitability, paper-idea P&L, close-state, or promotion decisions.

## Summary

- Status: `suggested_trade_review_plan_ready_blocked_for_market_window`.
- Open suggested-trade rows: `1`.
- Attention rows: `1`.
- Close-risk rows: `0`.
- Stale/missing review rows: `1`.
- Missing review rows: `1`.
- Stale review rows: `0`.
- Executable close-ready rows: `0`.
- Non-executable close-risk rows: `0`.
- Plan rows: `1`.
- Market-window-required rows: `1`.
- Source evidence counts: `{"missing_review": 1}`.
- Live policy change: `false`.

## Review Rows

| Priority | ID | Ticker | Lane | Class | Action | Status | Evidence | P&L | Warning |
|---:|---:|---|---|---|---|---|---|---:|---|
| 1 | 138 | AAA | legacy_unlabeled | suggested_trade | `refresh_missing_suggested_trade_review` | `market_window_required_missing_suggested_trade_review` | fresh_explicit_suggested_trade_review,candidate_outcome_ledger_rerun,monthly_profitability_audit_rerun,stored_review_snapshot |  |  |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 1 | `execute_suggested_trade_review_plan` | 1 | suggested_trade_attention_rows_need_fresh_explicit_review |

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate suggested-trade DB state, auto-close from stale/display/missing review marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, count suggested trades as production proof, or promote paper/research/backfill evidence.

