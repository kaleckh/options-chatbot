# Regular Options Stale Candidate Archive

This report is generated from `scripts/build_regular_options_stale_candidate_archive.py`. It records no-longer-matched regular-options candidates as read-only archived stale branches without mutating scanner, broker, database, proof, or promotion behavior.

## Summary

- Status: `stale_candidate_archive_readback`.
- Overall status: `stale_candidates_archived`.
- Source wait/archive rows: `16`.
- Archived no-longer-matched candidates: `16`.
- Archive exceptions: `0`.
- Archive complete: `True`.
- Lane counts: `{"quality90_debit55_canary": 2, "swing": 9, "tracked_winner_observation": 1, "tracked_winner_primary": 1, "volatility_expansion_observation": 3}`.
- Ticker counts: `{"QQQ": 7, "SPY": 9}`.
- Production proof-ready rows: `0`.
- Promotion ready: `False`.
- Blockers: `["fresh_executable_match_required_for_reactivation"]`.
- Live policy change: `false`.

## Archived Candidates

| Scan Date | Lane | Ticker | Direction | Expiry | Long Contract | Short Contract | Status | Validation | Archive |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-02 | swing | QQQ | call | 2026-06-26 | QQQ260626C00750000 | QQQ260626C00780000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-02 | swing | QQQ | call | 2026-06-26 |  |  | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-02 | swing | SPY | call | 2026-06-26 | SPY260626C00762000 | SPY260626C00780000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-02 | swing | SPY | call | 2026-06-26 |  |  | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-03 | swing | QQQ | call | 2026-06-26 | QQQ260626C00745000 | QQQ260626C00780000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-03 | swing | SPY | call | 2026-06-26 | SPY260626C00757000 | SPY260626C00775000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-03 | tracked_winner_observation | SPY | call | 2026-07-02 | SPY260702C00757000 | SPY260702C00780000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-03 | tracked_winner_primary | SPY | call | 2026-07-02 | SPY260702C00757000 | SPY260702C00780000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | quality90_debit55_canary | QQQ | call | 2026-06-18 | QQQ260618C00743000 | QQQ260618C00770000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | quality90_debit55_canary | SPY | call | 2026-06-18 | SPY260618C00756000 | SPY260618C00770000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | swing | QQQ | call | 2026-06-26 | QQQ260626C00745000 | QQQ260626C00775000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | swing | SPY | call | 2026-06-26 | SPY260626C00756000 | SPY260626C00770000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | swing | SPY | call | 2026-06-26 | SPY260626C00758000 | SPY260626C00775000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | volatility_expansion_observation | QQQ | call | 2026-06-18 | QQQ260618C00743000 | QQQ260618C00770000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-04 | volatility_expansion_observation | SPY | call | 2026-06-18 | SPY260618C00756000 | SPY260618C00770000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |
| 2026-06-05 | volatility_expansion_observation | QQQ | call | 2026-06-18 | QQQ260618C00740000 | QQQ260618C00765000 | `live_validation_attempted` | `no_longer_matched` | `archived_no_longer_matched_candidate` |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|

## Boundary

This archive is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower proof bars, or reactivate no-longer-matched candidates without fresh executable exact OPRA/NBBO evidence.

