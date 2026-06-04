# Regular Options Fresh Evidence Loop

This report is generated from `scripts/build_regular_options_fresh_evidence_loop.py`. It reconciles pending validation candidates, fill attempts, tracked-position linkage, and exact realized P&L readbacks without changing scanner, broker, auth, DB, stop, or proof behavior.

## Summary

- Status: `fresh_evidence_loop_readback`.
- Candidates: `20`.
- Validation outcomes: `{"no_longer_matched": 15, "proof_ineligible": 5}`.
- Entry evidence statuses: `{"fill_attempt_missing": 15, "fresh_executable_exact_entry": 5}`.
- Realized P&L statuses: `{"no_position_link": 20}`.
- No-longer-matched: `15`.
- Proof-ineligible: `5`.
- Linked positions: `0`.
- Exact realized P&L rows: `0`.
- Missing realized P&L: `0`.
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
