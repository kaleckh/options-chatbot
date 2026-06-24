# Regular Options Paper Shadow Evidence Plan

No live release. Next best action: collect paper-shadow exact evidence for volatility_expansion_observation.

## At a glance

- Overall status: `paper_shadow_evidence_collecting`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Exact realized P&L rows: `0`.
- Promotion-ready rows: `0`.
- Paper-shadow actions: `16`.
- Market-window actions: `15`.
- Waiting actions: `3`.
- Blocked actions: `5`.
- Action counts: `{"bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval": 1, "bullish_pullback_layer_4_execution_safety_preflight": 1, "capture_fill_attempt_evidence": 4, "collect_exact_entry_evidence": 8, "collect_exact_exit_evidence": 1, "no_chase_quarantine": 4, "prepare_bullish_pullback_layer_shadow_harness": 1, "refresh_suggested_trade_review": 1, "repair_replay_evidence": 3}`.
- Status counts: `{"blocked_execution_safety_preflight": 1, "blocked_missing_fill_attempt": 4, "no_action": 4, "ready_for_market_window": 8, "repair_only": 3, "review_only": 1, "waiting_for_market_window": 1, "waiting_for_market_window_and_operator_approval": 1, "waiting_for_policy_exit": 1}`.

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
| `3` | `bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval` | `waiting_for_market_window_and_operator_approval` | `bullish_pullback_observation` | `` | `` | Use the bullish-pullback layer4 protocol only for future natural paper-shadow denominator rows after a valid market-data window and separate operator approval. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `QQQ` | `2026-06-05|range_breakout_observation|QQQ|call|2026-06-18|QQQ260618C00740000|QQQ260618C00765000|740.0|765.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00739000|QQQ260626C00770000|739.0|770.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00756000|SPY260626C00775000|756.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00759000|SPY260626C00775000|759.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `collect_exact_entry_evidence` | `ready_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `3` | `prepare_bullish_pullback_layer_shadow_harness` | `waiting_for_market_window` | `bullish_pullback_observation` | `` | `` | Use selected bullish-pullback layer layer_4_clean_exact / sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1 as the future paper-shadow harness target only when a fresh natural market-window selection appears. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `short_term` | `QQQ` | `2026-06-05|short_term|QQQ|call|2026-06-12|QQQ260612C00728000|QQQ260612C00744000|728.0|744.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00730000|QQQ260626C00750000|730.0|750.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00752000|SPY260626C00770000|752.0|770.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `4` | `capture_fill_attempt_evidence` | `blocked_missing_fill_attempt` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00751000|SPY260618C00763000|751.0|763.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |

## Waiting actions

- `collect_exact_exit_evidence` `volatility_expansion_observation` `QQQ`: Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence.
- `bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval` `bullish_pullback_observation` `None`: Use the bullish-pullback layer4 protocol only for future natural paper-shadow denominator rows after a valid market-data window and separate operator approval.
- `prepare_bullish_pullback_layer_shadow_harness` `bullish_pullback_observation` `None`: Use selected bullish-pullback layer layer_4_clean_exact / sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1 as the future paper-shadow harness target only when a fresh natural market-window selection appears.

## Blocked actions

- `bullish_pullback_layer_4_execution_safety_preflight` `bullish_pullback_observation` `None`: `["existing_trusted_leg_exit_quotes_missing", "existing_trusted_missing_or_crossed_quote_fields", "existing_trusted_side_aware_bid_ask_prices_missing", "existing_trusted_side_aware_price_mismatch_with_source_run", "existing_trusted_zero_bid_or_untradable_leg_quote"]`.
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

- Review only: suggested trade `138` `AAA`. Resolve this expired paper idea through historical exact exit or expiry evidence before using its P&L; then rerun the suggested close-risk, candidate-ledger, and monthly profitability readbacks.

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
| `bullish_pullback_layer4_forward_capture_protocol` | `loaded` | `0.38` | `2026-06-21T20:22:09Z` | `[]` |
| `bullish_pullback_layer_execution_safety_audit` | `loaded` | `0.38` | `2026-06-21T20:21:52Z` | `[]` |
| `bullish_pullback_layer_shadow_selection` | `loaded` | `0.39` | `2026-06-21T20:21:48Z` | `[]` |
| `candidate_outcome_ledger` | `loaded` | `3.38` | `2026-06-21T17:21:56Z` | `[]` |
| `fill_attempt_evidence_capture_plan` | `loaded` | `3.41` | `2026-06-21T17:20:20Z` | `[]` |
| `fresh_evidence_loop` | `loaded` | `3.41` | `2026-06-21T17:20:30Z` | `[]` |
| `gateboard` | `loaded` | `3.38` | `2026-06-21T17:22:22Z` | `[]` |
| `lane_promotion_state` | `loaded` | `3.38` | `2026-06-21T17:22:02Z` | `[]` |
| `monthly_profitability` | `loaded` | `3.38` | `2026-06-21T17:22:27Z` | `[]` |
| `open_position_risk` | `loaded` | `3.41` | `2026-06-21T17:20:19Z` | `[]` |
| `paper_shortlist` | `loaded` | `3.39` | `2026-06-21T17:21:47Z` | `[]` |
| `profit_capture_queue` | `loaded` | `3.39` | `2026-06-21T17:21:48Z` | `[]` |
| `regular_options_market_window_approval_preflight` | `loaded` | `0.0` | `2026-06-21T20:44:57Z` | `[]` |
| `suggested_trade_close_risk` | `loaded` | `3.95` | `2026-06-21T16:47:57Z` | `[]` |
| `suggested_trade_review_plan` | `loaded` | `3.72` | `2026-06-21T17:01:59Z` | `[]` |
| `trade_qualification` | `loaded` | `3.38` | `2026-06-21T17:22:16Z` | `[]` |

Source status counts: `{"loaded": 16}`.

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
