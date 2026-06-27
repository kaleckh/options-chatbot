# Lane Promotion State

This report is generated from `scripts/lane_promotion_state.py`. It turns the regular-options lane promotion protocol into a rerunnable state artifact. It does not create trades, change scanner policy, submit broker orders, change stops, lower proof bars, or convert research/backfill evidence into production proof.

## Summary

- Status: `lane_promotion_state_readback`.
- Lanes: `14`.
- State counts: `{"diagnostic": 3, "parked": 11}`.
- Candidate status counts: `{"diagnostic_only_lane_promotion_state": 14}`.
- Live-validation lanes: `0`.
- Auto-track lanes: `0`.
- Parked lanes: `11`.
- Current live-exact negative open rows: `0`.
- Live policy change: `False`.

## Promotion Contract

- `diagnostic`: the lane is outside regular auto-track scope, lacks clean data, lacks a lane row, or is not profitable enough.
- `paper_probation`: the lane is historically profitable enough to study, but still lacks fresh walk-forward/paper/risk clearance.
- `live_validation`: the lane may enter fresh validation; this still is not broker execution by itself.
- `auto_track`: reserved for an explicit future release review after live-validation gates pass.
- `parked`: the lane is outside the frozen forward cohort; readbacks disable scans and chores for that lane without changing the frozen cohort proof bars.


## Forward Cohort Freeze

- Freeze date: `2026-06-14`.
- Eval date: `2026-07-28`.
- Cohort lanes: `["volatility_expansion_observation", "bullish_pullback_observation"]`.
- Parked regular lanes: `11`.
- Parked-status line: All non-cohort regular lanes are parked outside the frozen forward cohort: no scans, no chores, and no promotion work until the cohort is evaluated or explicitly refrozen.

## Lane States

| Lane | State | Candidate status | PF | Avg P&L % | Fresh ready | Exact realized | Main blockers |
|---|---:|---:|---:|---:|---:|---:|---|
| ai_commodity_infra_observation | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient |
| bearish_defensive | parked | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| bearish_index_put_observation | parked | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| bullish_momentum | parked | diagnostic_only_lane_promotion_state | 0.04 | -48.45 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| bullish_pullback_observation | diagnostic | diagnostic_only_lane_promotion_state | 0.24 | -22.81 | 0 | 0 | lane_profitability_gate_report_unusable, lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, recent_cohort_circuit_breaker_active |
| quality90_debit55_canary | parked | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| range_breakout_observation | parked | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| regular_bearish_put_primary | parked | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| short_term | parked | diagnostic_only_lane_promotion_state | 0.33 | -18.93 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, recent_cohort_circuit_breaker_active, walk_forward_holdout_too_small_or_failed |
| speculative | parked | diagnostic_only_lane_promotion_state | 0.1 | -12.62 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| swing | parked | diagnostic_only_lane_promotion_state | 0.2 | -20.24 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| tracked_winner_observation | parked | diagnostic_only_lane_promotion_state | 0.5 | -8.43 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| tracked_winner_primary | parked | diagnostic_only_lane_promotion_state | 0.5 | -8.43 | 0 | 0 | fresh_paper_cohort_insufficient, lane_not_profitable_enough_for_probation, lane_outside_regular_auto_track_scope, lane_profitability_gate_report_unusable, parked_outside_forward_cohort, walk_forward_holdout_too_small_or_failed |
| volatility_expansion_observation | diagnostic | diagnostic_only_lane_promotion_state | 1.83 | 6.74 | 0 | 0 | lane_profitability_gate_report_unusable, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient |

## Input Health

- Lane profitability gate: `{"age_hours": 130.5115, "generated_at_utc": "2026-06-21T17:20:10Z", "max_age_hours": 36.0, "reason": "lane_profitability_gate_report_stale", "usable": false}`.
- Filter matrix loaded: `True`.
- Fresh evidence loop loaded: `True`.
- Open risk loaded: `True`.
- Current-policy circuit breaker loaded: `True`.
