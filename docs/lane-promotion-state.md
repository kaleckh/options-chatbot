# Lane Promotion State

This report is generated from `scripts/lane_promotion_state.py`. It turns the regular-options lane promotion protocol into a rerunnable state artifact. It does not create trades, change scanner policy, submit broker orders, change stops, lower proof bars, or convert research/backfill evidence into production proof.

## Summary

- Status: `lane_promotion_state_readback`.
- Lanes: `14`.
- State counts: `{"diagnostic": 13, "paper_probation": 1}`.
- Candidate status counts: `{"diagnostic_only_lane_promotion_state": 13, "pending_paper_exact_evidence": 1}`.
- Live-validation lanes: `0`.
- Auto-track lanes: `0`.
- Current live-exact negative open rows: `1`.
- Live policy change: `False`.

## Promotion Contract

- `diagnostic`: the lane is outside regular auto-track scope, lacks clean data, lacks a lane row, or is not profitable enough.
- `paper_probation`: the lane is historically profitable enough to study, but still lacks fresh walk-forward/paper/risk clearance.
- `live_validation`: the lane may enter fresh validation; this still is not broker execution by itself.
- `auto_track`: reserved for an explicit future release review after live-validation gates pass.

## Lane States

| Lane | State | Candidate status | PF | Avg P&L % | Fresh ready | Exact realized | Main blockers |
|---|---:|---:|---:|---:|---:|---:|---|
| ai_commodity_infra_observation | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_outside_regular_auto_track_scope, lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| bearish_defensive | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| bearish_index_put_observation | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| bullish_momentum | diagnostic | diagnostic_only_lane_promotion_state | 0.1 | -48.45 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| bullish_pullback_observation | diagnostic | diagnostic_only_lane_promotion_state | 0.29 | -22.81 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked, recent_cohort_circuit_breaker_active |
| quality90_debit55_canary | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| range_breakout_observation | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| regular_bearish_put_primary | diagnostic | diagnostic_only_lane_promotion_state |  |  | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| short_term | diagnostic | diagnostic_only_lane_promotion_state | 0.28 | -18.93 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked, recent_cohort_circuit_breaker_active |
| speculative | diagnostic | diagnostic_only_lane_promotion_state | 0.12 | -12.62 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| swing | diagnostic | diagnostic_only_lane_promotion_state | 0.3 | -14.31 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| tracked_winner_observation | diagnostic | diagnostic_only_lane_promotion_state | 0.46 | -9.19 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| tracked_winner_primary | diagnostic | diagnostic_only_lane_promotion_state | 0.46 | -9.19 | 0 | 0 | lane_not_profitable_enough_for_probation, walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |
| volatility_expansion_observation | paper_probation | pending_paper_exact_evidence | 1.72 | 6.75 | 0 | 0 | walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked |

## Input Health

- Lane profitability gate: `{"age_hours": 11.7732, "generated_at_utc": "2026-06-05T19:35:21Z", "latest_intraday_quote_date": "2026-06-04", "mark_unpriced_count": 0, "max_age_hours": 36.0, "reason": "lane_profitability_gate_report_fresh", "tracked_row_count": 4, "tracked_rows_with_stored_pnl": 4, "usable": true}`.
- Filter matrix loaded: `True`.
- Fresh evidence loop loaded: `True`.
- Open risk loaded: `True`.
- Current-policy circuit breaker loaded: `True`.
