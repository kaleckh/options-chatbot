# Regular Options Quote-Surface Opening-Range Reversal Replay

This generated report is read-only. It tests one quote-surface-only mean-reversion debit-vertical concept from existing local OPRA/NBBO rows without importing quotes, mutating evidence stores, changing scanner logic, consuming protected holdout, enabling live validation, auto-track, broker orders, or promotion.

## Summary

- Status: `blocked_quote_surface_opening_range_reversal_replay`.
- Concept: `quote_surface_opening_range_reversal_vertical_v1`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Universe: `SPY, QQQ, IWM, DIA`.
- Read-only DB open: `true`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Daily denominator rows: `1976`.
- Candidate rows: `0`.
- Latest-four strict executable rows: `0`.
- Full-window strict-new rows: `0`.
- Full-window net USD P&L: `0.0`.
- Full-window PF / lower-bound / stress PF: `None` / `None` / `None`.

## Blockers

- `blocked_latest_four_rows_below_30`
- `blocked_missing_quote_surface_underlying_price`

## Denominator Status Counts

| Status | Count |
|---|---:|
| `blocked_missing_underlying_price` | `1976` |

## Concentration

- Single-trade profit share: `0.0`.
- Top-5 trade profit share: `0.0`.
- Single-month profit share: `0.0`.
- Single-underlying profit share: `0.0`.
- Single-expiration profit share: `0.0`.

## Boundary

historical rows are read-only research falsification/nomination evidence and are not forward proof or accepted profitability

## Next Oracle Instruction

Return this result to the same GPT-5.5 Pro session. If blocked on missing underlying price/opening buckets or fewer than 30 latest-four strict executable completed rows, park this branch unless a new trusted quote/underlying surface or explicit research-only replay source changes the blocker; then select the next materially different read-only option-structure or quote-surface branch.

## Forbidden Actions

- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_append_forward_paper_shadow_cohort`
- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_treat_historical_rows_as_forward_proof`
- `do_not_count_midpoint_stale_eod_display_last_model_manual_or_synthetic_marks`
