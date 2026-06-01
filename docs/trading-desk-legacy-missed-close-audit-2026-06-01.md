# Trading Desk Legacy Missed-Close Audit - 2026-06-01

This is a read-only audit of legacy rows that had stored executable SELL evidence before their final negative closed result. It does not mutate tracked positions.

## Summary

- Recommendation: `no_broad_exit_policy_change; preserve as historical stale-policy diagnostic`
- Diagnosis counts: `{'stale_or_non_autoclosing_review_path': 3}`
- Current action required count: `0`

## Targets

| Trade | Ticker | Lane | Final P&L | Actual Close | Current Policy Replay | Diagnosis |
|---:|---|---|---:|---|---|---|
| 26 | JPM | `legacy_unlabeled` | -44.7796% | 2026-05-10T17:29:09.587775-06:00 / auto_sell_recommendation | time_exit at 2026-05-06 08:09:09.055925-06:00 (3.9946%) | `stale_or_non_autoclosing_review_path` |
| 39 | DIA | `legacy_unlabeled` | -42.9751% | 2026-05-10T17:29:06.338694-06:00 / auto_sell_recommendation | time_exit at 2026-05-06 08:03:06.827552-06:00 (-22.179%) | `stale_or_non_autoclosing_review_path` |
| 44 | JPM | `legacy_unlabeled` | -80.098% | 2026-05-10T17:29:04.629719-06:00 / auto_sell_recommendation | time_exit at 2026-05-06 08:09:05.144366-06:00 (-38.925%) | `stale_or_non_autoclosing_review_path` |

## Interpretation

Rows diagnosed as `stale_or_non_autoclosing_review_path` are historical policy/application evidence, not proof that the current review endpoint is failing. The current review service now auto-closes open rows when a saved executable review recommends `SELL`, so a current bug claim requires a still-open row with an executable SELL that does not close.
