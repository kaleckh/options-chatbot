# Current-Policy Circuit Breaker

This report is generated from `scripts/build_current_policy_circuit_breaker.py`. It is a readback-driven paper-validation route for recently broken current-policy cohorts, not a lane deletion or live scanner promotion.

## Summary

- Overall status: `paper_only_recent_week_break`.
- Breaker active: `True`.
- Route status: `paper_validation_only`.
- Paper-validation-only lanes: `2`.
- Recovery-review-required lanes: `0`.
- Recovery gate failures: `recent_cohort_recovered, fresh_current_policy_rows, fresh_champion_matched_rows, trusted_exact_realized_pnl_rows, point_in_time_replay_pass, paper_monitor_pass`.
- Live policy change: `False`.
- Lane deletion: `False`.

## Lane Routes

| Lane | Route | Recent Health | Reason | Gate Failures |
|---|---|---|---|---|
| short_term | paper_validation_only | paper_only_recent_break | recovery_gates_failed | recent_cohort_recovered, fresh_current_policy_rows, fresh_champion_matched_rows, trusted_exact_realized_pnl_rows, point_in_time_replay_pass, paper_monitor_pass |
| bullish_pullback_observation | paper_validation_only | paper_only_thin_severe | recovery_gates_failed | recent_cohort_recovered, fresh_current_policy_rows, fresh_champion_matched_rows, trusted_exact_realized_pnl_rows, point_in_time_replay_pass, paper_monitor_pass |

## Recovery Gates

| Gate | Passed | Current | Target |
|---|---:|---|---|
| recent_cohort_recovered | False | "paper_only_recent_week_break" | "not paper_only_*" |
| fresh_current_policy_rows | False | 0 | 20 |
| fresh_champion_matched_rows | False | 0 | 5 |
| trusted_exact_realized_pnl_rows | False | {"exact_priced_candidate_rows": 0, "exact_priced_champion_rows": 0} | {"exact_priced_candidate_rows": 20, "exact_priced_champion_rows": 5} |
| point_in_time_replay_pass | False | {"blockers": ["insufficient_exact_priced_candidate_rows", "insufficient_champion_matched_blocked_rows", "matched_rows_not_net_harmful_or_deep_loss", "unpriced_or_non_executable_rows_present"], "status": "paper_only_collecting"} | {"blockers": [], "status": "point_in_time_replay_pass_candidate_not_promoted"} |
| paper_monitor_pass | False | {"failures": ["insufficient_fresh_rows", "insufficient_candidate_blocked_rows", "blocked_rows_not_net_negative_or_deep_loss"], "status": "collecting"} | {"failures": [], "status": "paper_pass_candidate"} |
| no_winner_damage | True | {"monitor_losses_avoided": 0, "monitor_winners_lost": 0, "point_in_time_losses_avoided": 0, "point_in_time_lost_winners": 0} | "lost_winners <= losses_avoided in replay and monitor" |
| live_policy_change_false | True | {"paper_monitor_live_policy_change": false, "point_in_time_live_policy_change": false} | false |

## Boundary

- `paper_validation_only` means pending candidates in affected lanes should receive a paper-only validation disposition instead of entering the auto-track validation path while the breaker is active.
- Recovery gates passing creates a review candidate, not an automatic live promotion.
- The breaker never deletes `short_term` or `bullish_pullback_observation`; it keeps the lanes observable while recent evidence is broken.
- The short-term fill-degradation rule remains lane-scoped and paper-only.

