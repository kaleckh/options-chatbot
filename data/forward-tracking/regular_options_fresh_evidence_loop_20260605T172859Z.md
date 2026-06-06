# Regular Options Fresh Evidence Loop

This report is generated from `scripts/build_regular_options_fresh_evidence_loop.py`. It reconciles pending validation candidates, fill attempts, tracked-position linkage, and exact realized P&L readbacks without changing scanner, broker, auth, DB, stop, or proof behavior.

## Summary

- Status: `fresh_evidence_loop_readback`.
- Candidates: `34`.
- Validation outcomes: `{"created": 1, "diagnostic_only_lane_profitability_gate": 4, "no_longer_matched": 16, "paper_only": 8, "proof_ineligible": 5}`.
- Entry evidence statuses: `{"fill_attempt_missing": 28, "fresh_executable_exact_entry": 6}`.
- Realized P&L statuses: `{"missing_realized_pnl": 1, "no_position_link": 33}`.
- No-longer-matched: `16`.
- Proof-ineligible: `5`.
- Linked positions: `1`.
- Exact realized P&L rows: `0`.
- Missing realized P&L: `1`.
- Stale entry evidence: `0`.
- Non-executable entry evidence: `0`.
- Promotion discussion ready: `0`.
- Live policy change: `False`.

## Evidence Boundary

- Exact realized P&L is required before promotion discussion.
- Entry evidence status describes scanner quote/limit evidence only; it is not a fill, position, or broker execution status.
- `created` and `duplicate` validation outcomes are still paper/tracked linkage states, not broker fills.
- Missing, stale, non-executable, proof-ineligible, and no-longer-matched rows remain blocked from promotion.

## Candidate Readback

| Date | Lane | Ticker | Outcome | Entry Evidence | P&L Status | Position | Ready | Reason |
|---|---|---|---|---|---|---:|---|---|
| 2026-06-02 | swing | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-02 | swing | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-02 | swing | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-02 | swing | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-03 | swing | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-03 | swing | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-03 | tracked_winner_observation | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-03 | tracked_winner_primary | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | quality90_debit55_canary | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | quality90_debit55_canary | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | range_breakout_observation | QQQ | proof_ineligible | fresh_executable_exact_entry | no_position_link |  | False | auto_track_skipped_or_missing_fill_price |
| 2026-06-04 | range_breakout_observation | SPY | proof_ineligible | fresh_executable_exact_entry | no_position_link |  | False | auto_track_skipped_or_missing_fill_price |
| 2026-06-04 | swing | QQQ | proof_ineligible | fresh_executable_exact_entry | no_position_link |  | False | auto_track_skipped_or_missing_fill_price |
| 2026-06-04 | swing | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | swing | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | swing | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | volatility_expansion_observation | QQQ | proof_ineligible | fresh_executable_exact_entry | no_position_link |  | False | auto_track_skipped_or_missing_fill_price |
| 2026-06-04 | volatility_expansion_observation | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | volatility_expansion_observation | SPY | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-04 | volatility_expansion_observation | SPY | proof_ineligible | fresh_executable_exact_entry | no_position_link |  | False | auto_track_skipped_or_missing_fill_price |
| 2026-06-05 | range_breakout_observation | QQQ | paper_only | fill_attempt_missing | no_position_link |  | False | missing_lane_profitability_gate_report_or_lane_row |
| 2026-06-05 | range_breakout_observation | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | missing_lane_profitability_gate_report_or_lane_row |
| 2026-06-05 | range_breakout_observation | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | missing_lane_profitability_gate_report_or_lane_row |
| 2026-06-05 | short_term | QQQ | diagnostic_only_lane_profitability_gate | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | swing | QQQ | diagnostic_only_lane_profitability_gate | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | swing | QQQ | paper_only | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | swing | SPY | diagnostic_only_lane_profitability_gate | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | swing | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | swing | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | lane_not_profitable_enough_for_live_validation |
| 2026-06-05 | volatility_expansion_observation | QQQ | created | fresh_executable_exact_entry | missing_realized_pnl | 537 | False | fresh_validation_created_or_confirmed_auto_track_position |
| 2026-06-05 | volatility_expansion_observation | QQQ | no_longer_matched | fill_attempt_missing | no_position_link |  | False | candidate_not_returned_by_market_hours_validation_scan |
| 2026-06-05 | volatility_expansion_observation | SPY | diagnostic_only_lane_profitability_gate | fill_attempt_missing | no_position_link |  | False | lane_self_guardrail_blocked_negative_ticker_cluster |
| 2026-06-05 | volatility_expansion_observation | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | lane_self_guardrail_blocked_negative_ticker_cluster |
| 2026-06-05 | volatility_expansion_observation | SPY | paper_only | fill_attempt_missing | no_position_link |  | False | lane_self_guardrail_blocked_negative_ticker_cluster |
