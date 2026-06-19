# Regular Options Paper Shadow Evidence Plan

No live release. Next best action: collect paper-shadow exact evidence for volatility_expansion_observation.

## At a glance

- Overall status: `paper_shadow_evidence_collecting`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Exact realized P&L rows: `0`.
- Promotion-ready rows: `0`.
- Paper-shadow actions: `13`.
- Market-window actions: `14`.
- Waiting actions: `1`.
- Blocked actions: `4`.
- Action counts: `{"capture_fill_attempt_evidence": 4, "collect_exact_entry_evidence": 8, "collect_exact_exit_evidence": 1, "no_chase_quarantine": 4, "refresh_suggested_trade_review": 1, "repair_replay_evidence": 3}`.
- Status counts: `{"blocked_missing_fill_attempt": 4, "no_action": 4, "ready_for_market_window": 8, "repair_only": 3, "review_only": 1, "waiting_for_policy_exit": 1}`.

## Best evidence lane

- Lane: `volatility_expansion_observation`.
- Decision: `paper_shadow_collect`.
- Disposition: `paper_shadow`.
- Promotion state: `paper_probation`.
- Profit factor: `1.83`.
- Average net P&L pct: `6.74`.
- Fresh exact entry count: `3`.
- Exact realized P&L count: `0`.

## Next market-window actions

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `2` | `collect_exact_exit_evidence` | `waiting_for_policy_exit` | `volatility_expansion_observation` | `QQQ` | `537` | Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `QQQ` | `2026-06-05|range_breakout_observation|QQQ|call|2026-06-18|QQQ260618C00740000|QQQ260618C00765000|740.0|765.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00739000|QQQ260626C00770000|739.0|770.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00756000|SPY260626C00775000|756.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00759000|SPY260626C00775000|759.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `short_term` | `QQQ` | `2026-06-05|short_term|QQQ|call|2026-06-12|QQQ260612C00728000|QQQ260612C00744000|728.0|744.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00730000|QQQ260626C00750000|730.0|750.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00752000|SPY260626C00770000|752.0|770.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00751000|SPY260618C00763000|751.0|763.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `5` | `refresh_suggested_trade_review` | `review_only` | `legacy_unlabeled` | `AAA` | `138` | During the next fresh executable quote window, refresh this paper idea's explicit review, then rerun the suggested close-risk, candidate-ledger, and monthly profitability readbacks. |

## Waiting actions

- `collect_exact_exit_evidence` `volatility_expansion_observation` `QQQ`: Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence.

## Blocked actions

- `capture_fill_attempt_evidence` `short_term` `QQQ`: `["entry_status:fill_attempt_missing", "no_fill_attempt_logged", "lane_not_profitable_enough_for_live_validation"]`.
- `capture_fill_attempt_evidence` `swing` `QQQ`: `["entry_status:fill_attempt_missing", "no_fill_attempt_logged", "lane_not_profitable_enough_for_live_validation"]`.
- `capture_fill_attempt_evidence` `swing` `SPY`: `["entry_status:fill_attempt_missing", "no_fill_attempt_logged", "lane_not_profitable_enough_for_live_validation"]`.
- `capture_fill_attempt_evidence` `volatility_expansion_observation` `SPY`: `["entry_status:fill_attempt_missing", "no_fill_attempt_logged", "lane_self_guardrail_blocked_negative_ticker_cluster"]`.

## Open-risk / exact-exit evidence

- `waiting_for_policy_exit` `volatility_expansion_observation` `QQQ` position `537`: Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence.

## Fill-attempt evidence

- `blocked_missing_fill_attempt` `short_term` `QQQ` `2026-06-05`: During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot.
- `blocked_missing_fill_attempt` `swing` `QQQ` `2026-06-05`: During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot.
- `blocked_missing_fill_attempt` `swing` `SPY` `2026-06-05`: During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot.
- `blocked_missing_fill_attempt` `volatility_expansion_observation` `SPY` `2026-06-05`: During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot.

## Suggested-trade review actions

- Review only: suggested trade `138` `AAA`. During the next fresh executable quote window, refresh this paper idea's explicit review, then rerun the suggested close-risk, candidate-ledger, and monthly profitability readbacks.

## Quarantined / no-chase lanes

- `bullish_momentum`: Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence.
- `bullish_pullback_observation`: Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence.
- `short_term`: Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence.
- `swing`: Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence.

## Promotion requirements still missing

- fresh executable exact OPRA/NBBO entry evidence for the paper-shadow lane after freeze.
- policy-defined exact executable OPRA/NBBO exit evidence for linked rows.
- exact realized P&L rows built from executable entry plus executable exit evidence.
- promotion_ready_count greater than zero from the fresh evidence loop.
- sufficient fresh forward sample size under the frozen lane gate.
- no active no-chase or quarantine blocker for the lane.
- open-risk governor clear in fresh local readbacks.

## Source artifacts and staleness

| Source | Status | Age hours | Generated at | Reasons |
| --- | --- | ---: | --- | --- |
| `candidate_outcome_ledger` | `loaded` | `20.9` | `2026-06-17T05:11:09Z` | `[]` |
| `fill_attempt_evidence_capture_plan` | `loaded` | `20.38` | `2026-06-17T05:42:01Z` | `[]` |
| `fresh_evidence_loop` | `loaded` | `20.9` | `2026-06-17T05:10:59Z` | `[]` |
| `gateboard` | `loaded` | `20.28` | `2026-06-17T05:48:07Z` | `[]` |
| `lane_promotion_state` | `loaded` | `0.26` | `2026-06-18T01:49:14Z` | `[]` |
| `monthly_profitability` | `loaded` | `0.0` | `2026-06-18T02:04:50Z` | `[]` |
| `open_position_risk` | `loaded` | `20.9` | `2026-06-17T05:10:58Z` | `[]` |
| `paper_shortlist` | `loaded` | `20.9` | `2026-06-17T05:10:57Z` | `[]` |
| `profit_capture_queue` | `loaded` | `20.9` | `2026-06-17T05:10:49Z` | `[]` |
| `suggested_trade_close_risk` | `loaded` | `20.9` | `2026-06-17T05:10:43Z` | `[]` |
| `suggested_trade_review_plan` | `loaded` | `20.38` | `2026-06-17T05:42:01Z` | `[]` |
| `trade_qualification` | `loaded` | `0.0` | `2026-06-18T02:04:54Z` | `[]` |

Source status counts: `{"loaded": 12}`.

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
