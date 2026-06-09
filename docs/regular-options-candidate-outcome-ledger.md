# Regular Options Candidate Outcome Ledger

This report is generated from `scripts/build_regular_options_candidate_outcome_ledger.py`. It turns the fresh-evidence loop, paper shortlist, profit-capture queue, open-risk governor, and suggested-trade close-risk readbacks into one read-only next-evidence queue without changing scanner, broker, auth, DB, stop, or proof behavior.

## Summary

- Status: `candidate_outcome_ledger_readback`.
- Operating status: `ledger_live_entry_blocked_collect_evidence`.
- Ledger rows: `106`.
- Fresh candidates: `34`.
- Paper-shortlist eligible rows: `0`.
- Profit-capture paper-review candidates: `15`.
- Promotion-ready rows: `0`.
- Exact realized P&L rows: `0`.
- Missing realized P&L rows: `1`.
- Paper/probation exact-entry bridges: `8`.
- Exact-exit bridges: `1`.
- Open-risk live entry allowed: `False`.
- Suggested-trade attention rows: `1`.
- Action counts: `{"capture_missing_fill_attempt_evidence": 4, "capture_paper_only_exact_entry": 8, "collect_exact_exit_evidence": 1, "create_or_link_paper_review_row": 5, "refresh_open_position_executable_review": 1, "refresh_suggested_trade_review": 1, "repair_historical_evidence": 39, "resolve_open_risk_governor": 1, "respect_guardrail_or_lane_mismatch": 9, "wait_for_fresh_executable_tier_a_bridge": 21, "wait_for_fresh_match_or_archive_candidate": 16}`.
- Live policy change: `false`.

## Next Evidence Queue

| Priority | Action | Count | Operator next step |
| --- | --- | ---: | --- |
| `0` | `resolve_open_risk_governor` | `1` | Refresh explicit open-position reviews during a fresh executable quote window; do not open new live scanner-origin rows while blocked. |
| `1` | `refresh_open_position_executable_review` | `1` | Rerun the read-only open-position risk audit during a fresh executable quote window before acting on display-only marks. |
| `1` | `refresh_suggested_trade_review` | `1` | Refresh explicit suggested-trade review before relying on paper-idea close state or P&L. |
| `2` | `collect_exact_exit_evidence` | `1` | Refresh exact OPRA/NBBO exit evidence for the linked paper/tracked row, then regenerate the fresh-evidence loop. |
| `4` | `create_or_link_paper_review_row` | `5` | Create or link a paper-review row from fresh exact entry evidence; do not count it as live proof until exact exit readback exists. |
| `5` | `capture_paper_only_exact_entry` | `8` | During market hours, capture a fresh executable exact OPRA/NBBO entry for this paper/probation lane. |
| `7` | `capture_missing_fill_attempt_evidence` | `4` | Rerun the market-window validation path only if the candidate is still freshly selected; require durable fill-attempt logging. |
| `8` | `wait_for_fresh_match_or_archive_candidate` | `16` | Do not chase old rows. Wait for a fresh scanner match or archive the stale candidate as no-longer-matched. |
| `9` | `wait_for_fresh_executable_tier_a_bridge` | `21` | Keep clean historical Tier A evidence in paper routing until a fresh executable lane-signature match appears. |
| `10` | `repair_historical_evidence` | `39` | Use the exact repair burn-down/source replay path before importing more data or treating the row as proof. |
| `11` | `respect_guardrail_or_lane_mismatch` | `9` | Keep blocked, symbol-only, or lane-mismatch rows out of paper shortlist and live promotion. |

## Highest Priority Rows

| Priority | Action | Source | Lane | Ticker | Reason |
| --- | --- | --- | --- | --- | --- |
| `0` | `resolve_open_risk_governor` | `open_position_risk` | `volatility_expansion_observation` | `QQQ` | open_risk_governor_blocks_live_entry |
| `1` | `refresh_open_position_executable_review` | `open_position_risk` | `bullish_pullback_observation` | `SBUX` | open_position_actionable_row_requires_fresh_executable_review |
| `1` | `refresh_suggested_trade_review` | `suggested_trade_close_risk` | `legacy_unlabeled` | `AAA` | suggested_trade_attention_row_requires_explicit_review_refresh |
| `2` | `collect_exact_exit_evidence` | `fresh_evidence_loop` | `volatility_expansion_observation` | `QQQ` | linked_position_has_missing_realized_pnl |
| `4` | `create_or_link_paper_review_row` | `fresh_evidence_loop` | `range_breakout_observation` | `QQQ` | fresh_exact_entry_exists_without_paper_or_tracked_link |
| `4` | `create_or_link_paper_review_row` | `fresh_evidence_loop` | `range_breakout_observation` | `SPY` | fresh_exact_entry_exists_without_paper_or_tracked_link |
| `4` | `create_or_link_paper_review_row` | `fresh_evidence_loop` | `swing` | `QQQ` | fresh_exact_entry_exists_without_paper_or_tracked_link |
| `4` | `create_or_link_paper_review_row` | `fresh_evidence_loop` | `volatility_expansion_observation` | `QQQ` | fresh_exact_entry_exists_without_paper_or_tracked_link |
| `4` | `create_or_link_paper_review_row` | `fresh_evidence_loop` | `volatility_expansion_observation` | `SPY` | fresh_exact_entry_exists_without_paper_or_tracked_link |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `range_breakout_observation` | `QQQ` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `range_breakout_observation` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `range_breakout_observation` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `swing` | `QQQ` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `swing` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `swing` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `volatility_expansion_observation` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `5` | `capture_paper_only_exact_entry` | `fresh_evidence_loop` | `volatility_expansion_observation` | `SPY` | paper_or_probation_candidate_requires_fresh_exact_entry_evidence |
| `7` | `capture_missing_fill_attempt_evidence` | `fresh_evidence_loop` | `short_term` | `QQQ` | candidate_missing_durable_fill_attempt_evidence |
| `7` | `capture_missing_fill_attempt_evidence` | `fresh_evidence_loop` | `swing` | `QQQ` | candidate_missing_durable_fill_attempt_evidence |
| `7` | `capture_missing_fill_attempt_evidence` | `fresh_evidence_loop` | `swing` | `SPY` | candidate_missing_durable_fill_attempt_evidence |

## Source Readbacks

- Fresh evidence validation outcomes: `{"created": 1, "diagnostic_only": 4, "no_longer_matched": 16, "paper_only": 8, "proof_ineligible": 5}`.
- Fresh evidence bridge statuses: `{"exact_exit_pnl_required": 1, "non_executable_entry_blocked": 20, "not_evidence_bridge_candidate": 5, "paper_probation_exact_entry_required": 8}`.
- Paper shortlist release gate: `no_paper_shortlist_candidates`.
- Profit-capture selection readiness: `{"blocked_guardrail_only": 9, "do_not_chase": 173, "historical_signature_only": 6, "paper_review_candidate": 15, "watch_repair_only": 82}`.
- Open-risk governor status: `open_risk_governor_blocked`.

## Boundary

This is an operator readback only. It does not create trades, submit broker orders, change scanner promotion, change stop policy, change auth/session behavior, change DB schema, lower proof bars, or turn paper/research/backfill evidence into production proof.
