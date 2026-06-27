# Regular Options Trade Qualification

No live release. Best current action: paper-shadow/evidence collection only.

## At a glance

- Overall status: `blocked_no_live_release`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- No-chase active: `true`.
- Fresh exact entry rows: `6`.
- Exact realized P&L rows: `0`.
- Promotion-ready rows: `0`.
- Paper-review candidates: `0`.
- Open-risk status: `open_risk_governor_pass`.
- Lane decisions: `{"insufficient_sample": 3, "paper_shadow_collect": 1, "quarantine_no_chase": 4}`.

## Best current lane, if any

- Lane: `volatility_expansion_observation`.
- Decision: `paper_shadow_collect`.
- Profit factor: `1.83`.
- Average net P&L pct: `6.74`.
- Fresh exact entry count: `3`.
- Exact realized P&L count: `0`.
- Operator action: paper-shadow evidence collection only; capture fresh exact entries and policy-defined exact exits.

## Lane table

| Lane | Disposition | Decision | PF | Avg % | Median % | Win % | Priced | Fresh entries | Exact realized | Next action |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `speculative` | `retest` | `insufficient_sample` | `0.1` | `-12.62` | `-15.53` | `25.0` | `8` | `0` | `0` | Collect or repair exact priced outcomes before lane decisions. |
| `tracked_winner_observation` | `retest` | `insufficient_sample` | `0.5` | `-8.43` | `-5.72` | `45.0` | `20` | `0` | `0` | Collect or repair exact priced outcomes before lane decisions. |
| `tracked_winner_primary` | `retest` | `insufficient_sample` | `0.5` | `-8.43` | `-5.72` | `45.0` | `20` | `0` | `0` | Collect or repair exact priced outcomes before lane decisions. |
| `volatility_expansion_observation` | `paper_shadow` | `paper_shadow_collect` | `1.83` | `6.74` | `2.15` | `50.0` | `24` | `3` | `0` | Collect fresh exact entry and exact realized exit evidence; do not route live. |
| `bullish_momentum` | `quarantine` | `quarantine_no_chase` | `0.04` | `-48.45` | `-54.84` | `12.5` | `16` | `0` | `0` | Keep lane parked; require earn-back or frozen retest before any fresh collection. |
| `bullish_pullback_observation` | `quarantine` | `quarantine_no_chase` | `0.24` | `-22.81` | `-24.1` | `33.3` | `15` | `0` | `0` | Keep lane parked; require earn-back or frozen retest before any fresh collection. |
| `short_term` | `quarantine` | `quarantine_no_chase` | `0.33` | `-18.93` | `-16.91` | `33.3` | `54` | `0` | `0` | Keep lane parked; require earn-back or frozen retest before any fresh collection. |
| `swing` | `quarantine` | `quarantine_no_chase` | `0.2` | `-20.24` | `-16.81` | `30.6` | `49` | `1` | `0` | Keep lane parked; require earn-back or frozen retest before any fresh collection. |

## Why live trading is blocked

- live_entry_allowed is false.
- auto_track_allowed is false.
- broker_order_allowed is permanently false for this report.
- exact_realized_pnl_count is 0.
- promotion_ready_count is 0.

## Next market-window actions

- `2` `collect_exact_exit_evidence` count `1`: Collect exact exit evidence for linked/live exact rows only when policy-defined exit conditions fire.
- `3` `collect_paper_shadow_exact_evidence` count `1`: Collect fresh exact entry and exact realized exit evidence for the strongest paper-shadow lane.
- `4` `capture_missing_fill_attempt_evidence` count `4`: Capture missing fill-attempt evidence only for fresh selections during a valid market-data window.
- `5` `refresh_suggested_trade_reviews` count `1`: Refresh suggested-trade reviews during valid market-data windows; this is review attention, not a trade recommendation.
- `6` `repair_replay_source_evidence` count `16`: Repair replay/source evidence only where the repair burn-down target is active and unexhausted.
- `7` `keep_broad_quarantined_lanes_parked` count `4`: Keep broad and quarantined lanes parked; do not chase historical winners.

## Evidence repair queue

- Active/unexhausted repair targets: `16`. Repair replay/source evidence only where the repair burn-down target is active and unexhausted.

## What not to do

- `do_not_create_trades_from_trade_qualification`
- `do_not_submit_broker_orders_from_trade_qualification`
- `do_not_change_scanner_policy_from_trade_qualification`
- `do_not_change_stops_from_trade_qualification`
- `do_not_change_sizing_from_trade_qualification`
- `do_not_enable_live_validation_from_trade_qualification`
- `do_not_enable_auto_track_from_trade_qualification`
- `do_not_lower_exact_executable_proof_bars_from_trade_qualification`
- `do_not_mutate_evidence_databases_from_trade_qualification`
- `do_not_open_live_or_auto_track_rows_from_blocked_readbacks`
- `do_not_chase_paper_or_historical_signature_rows_without_fresh_exact_bridge`
- `do_not_use_stale_midpoint_eod_manual_or_display_only_marks_as_proof`
- `do_not_create_live_row_from_monthly_profitability_audit`
- `do_not_submit_broker_order_from_monthly_profitability_audit`
- `do_not_mutate_database_from_monthly_profitability_audit`
- `do_not_change_scanner_policy_from_monthly_profitability_audit`
- `do_not_change_stop_policy_from_monthly_profitability_audit`
- `do_not_change_sizing_from_monthly_profitability_audit`
- `do_not_lower_exact_opra_nbbo_proof_bar_from_monthly_profitability_audit`
- `do_not_promote_paper_research_or_backfill_rows_to_production_proof`

## Promotion requirements still missing

- fresh executable exact OPRA/NBBO entry evidence for the lane after freeze.
- fresh executable exact OPRA/NBBO exit evidence and exact realized P&L for the lane.
- promotion_ready_count greater than zero from fresh forward evidence.
- sufficient fresh forward sample size under the policy-defined lane gate.
- positive lane economics under executable pricing, not midpoint, EOD, stale, or display-only marks.
- open-risk governor passing from fresh executable review or legitimate exit evidence.
- no active no-chase or quarantine blocker for the lane.
- paper-shadow/probation evidence bridge complete before any promotion discussion.

## Source artifacts and staleness

| Source | Status | Age hours | Generated at | Reasons |
| --- | --- | ---: | --- | --- |
| `candidate_outcome_ledger` | `loaded` | `0.04` | `2026-06-27T03:48:42Z` | `[]` |
| `fill_attempt_evidence_capture_plan` | `loaded` | `0.04` | `2026-06-27T03:48:43Z` | `[]` |
| `fresh_evidence_loop` | `loaded` | `0.04` | `2026-06-27T03:48:42Z` | `[]` |
| `gateboard` | `loaded` | `0.0` | `2026-06-27T03:50:52Z` | `[]` |
| `historical_walk_forward` | `loaded` | `0.0` | `2026-06-27T03:50:47Z` | `[]` |
| `lane_promotion_state` | `loaded` | `0.0` | `2026-06-27T03:50:51Z` | `[]` |
| `monthly_profitability` | `loaded` | `0.0` | `2026-06-27T03:50:51Z` | `[]` |
| `open_position_risk` | `loaded` | `0.04` | `2026-06-27T03:48:38Z` | `[]` |
| `open_risk_resolution_plan` | `loaded` | `0.04` | `2026-06-27T03:48:42Z` | `[]` |
| `paper_shortlist` | `loaded` | `0.04` | `2026-06-27T03:48:42Z` | `[]` |
| `profit_capture_queue` | `loaded` | `0.04` | `2026-06-27T03:48:39Z` | `[]` |
| `repair_burndown` | `loaded` | `0.04` | `2026-06-27T03:48:40Z` | `[]` |
| `robust_search_evaluation` | `loaded` | `0.0` | `2026-06-27T03:50:49Z` | `[]` |
| `suggested_trade_close_risk` | `loaded` | `0.04` | `2026-06-27T03:48:38Z` | `[]` |
| `suggested_trade_review_plan` | `loaded` | `0.04` | `2026-06-27T03:48:43Z` | `[]` |

Source status counts: `{"loaded": 15}`.

## Non-goals

This report does not:

- create trades
- submit broker orders
- change stops
- change scanner policy
- change sizing
- lower proof bars
- promote lanes
- mutate evidence databases

It also does not enable live validation or auto-track.
