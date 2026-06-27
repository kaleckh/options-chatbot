# Regular Options Market Window Evidence Checklist

No live release. Market-window task: collect/review evidence only for `volatility_expansion_observation`.

## At a glance

- Overall status: `waiting_for_market_window`.
- Market-window status: `unknown`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Trade recommendation: `false`.
- Exact realized P&L rows: `0`.
- Promotion-ready rows: `0`.
- Checklist steps: `32`.
- Waiting actions: `15`.
- Blocked actions: `5`.
- Review-only actions: `1`.
- Step counts: `{"bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval": 1, "bullish_pullback_layer_4_execution_safety_preflight": 1, "capture_fill_attempt_evidence": 4, "collect_exact_entry_evidence": 8, "no_chase_quarantine": 4, "prepare_bullish_pullback_layer_shadow_harness": 1, "refresh_bullish_pullback_layer4_forward_capture_protocol": 1, "refresh_bullish_pullback_layer_executable_economics": 1, "refresh_bullish_pullback_layer_execution_safety_audit": 1, "refresh_bullish_pullback_layer_shadow_selection": 1, "refresh_gateboard": 1, "refresh_market_window_approval_preflight": 1, "refresh_paper_shadow_plan": 1, "refresh_suggested_trade_review": 1, "refresh_trade_qualification": 1, "repair_replay_evidence": 3, "wait_for_policy_exit_condition": 1}`.

## Safe command order

- `1` `npm run options:gateboard`: Refresh operator gateboard and no-live/no-chase readback.
- `2` `npm run options:triage:trade-qualification`: Refresh read-only trade qualification.
- `3` `npm run options:plan:bullish-pullback-layer-shadow`: Refresh read-only bullish-pullback layer-shadow harness selection.
- `4` `npm run options:audit:bullish-pullback-layer-execution-safety`: Refresh read-only bullish-pullback layer execution-safety preflight.
- `5` `npm run options:audit:bullish-pullback-layer-executable-economics`: Refresh read-only bullish-pullback layer executable-economics audit.
- `6` `npm run options:plan:bullish-pullback-layer4-forward-capture`: Refresh read-only bullish-pullback layer4 forward capture protocol.
- `7` `npm run options:plan:paper-shadow-evidence`: Refresh paper-shadow evidence plan.
- `8` `npm run options:plan:fill-attempt-evidence-capture`: Refresh fill-attempt evidence capture plan.
- `9` `npm run options:plan:suggested-trade-review`: Refresh suggested-trade review-only plan.
- `10` `npm run options:audit:monthly-profitability`: Refresh monthly profitability audit readback.
- `11` `npm run options:preflight:market-window-approval`: Run the final no-write market-window approval preflight before any future approval discussion.

## Ready now

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `1` | `refresh_gateboard` | `ready` | `` | `` | `` | Refresh the gateboard before any market-window evidence work. |
| `2` | `refresh_trade_qualification` | `ready` | `` | `` | `` | Confirm no-live, no-auto-track, broker-order blocked state remains intact. |
| `3` | `refresh_bullish_pullback_layer_shadow_selection` | `ready` | `` | `` | `` | Refresh the selected bullish-pullback paper-shadow harness before using the market-window checklist. |
| `4` | `refresh_bullish_pullback_layer_execution_safety_audit` | `ready` | `` | `` | `` | Refresh the leg-level bid/ask and assignment/expiration preflight before using the selected bullish-pullback harness. |
| `5` | `refresh_bullish_pullback_layer_executable_economics` | `ready` | `` | `` | `` | Refresh the read-only executable-economics audit before any future approval discussion. |
| `6` | `refresh_bullish_pullback_layer4_forward_capture_protocol` | `ready` | `` | `` | `` | Refresh the read-only protocol before any future market-window candidate validation or approval discussion. |
| `6` | `refresh_paper_shadow_plan` | `ready` | `` | `` | `` | Refresh evidence rows before using this checklist during a valid market-data window. |
| `9` | `refresh_market_window_approval_preflight` | `ready` | `` | `` | `` | Run the no-write approval preflight as the final command before any future operator approval question. |

## Waiting for market window

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `34` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `range_breakout_observation` | `QQQ` | `2026-06-05|range_breakout_observation|QQQ|call|2026-06-18|QQQ260618C00740000|QQQ260618C00765000|740.0|765.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `35` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `36` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `range_breakout_observation` | `SPY` | `2026-06-05|range_breakout_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `37` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00739000|QQQ260626C00770000|739.0|770.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `38` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00756000|SPY260626C00775000|756.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `38` | `bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval` | `waiting_for_market_window_and_operator_approval` | `bullish_pullback_observation` | `` | `` | Use the bullish-pullback layer4 protocol only for future natural paper-shadow denominator rows after a valid market-data window and separate operator approval. |
| `39` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00759000|SPY260626C00775000|759.0|775.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `40` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00756000|SPY260618C00771000|756.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `41` | `collect_exact_entry_evidence` | `waiting_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00758000|SPY260618C00771000|758.0|771.0` | During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected. |
| `47` | `prepare_bullish_pullback_layer_shadow_harness` | `waiting_for_market_window` | `bullish_pullback_observation` | `` | `` | Use selected bullish-pullback layer layer_4_clean_exact / sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1 as the future paper-shadow harness target only when a fresh natural market-window selection appears. |
| `53` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `short_term` | `QQQ` | `2026-06-05|short_term|QQQ|call|2026-06-12|QQQ260612C00728000|QQQ260612C00744000|728.0|744.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `54` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00730000|QQQ260626C00750000|730.0|750.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `55` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00752000|SPY260626C00770000|752.0|770.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `56` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00751000|SPY260618C00763000|751.0|763.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |

## Waiting for policy exit

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `21` | `wait_for_policy_exit_condition` | `waiting_for_policy_exit` | `volatility_expansion_observation` | `QQQ` | `537` | Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence. |

## Review-only suggested trades

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `67` | `refresh_suggested_trade_review` | `review_only` | `legacy_unlabeled` | `AAA` | `138` | Resolve this expired paper idea through historical exact exit or expiry evidence before using its P&L; then rerun the suggested close-risk, candidate-ledger, and monthly profitability readbacks. |

## Fill-attempt evidence

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `53` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `short_term` | `QQQ` | `2026-06-05|short_term|QQQ|call|2026-06-12|QQQ260612C00728000|QQQ260612C00744000|728.0|744.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `54` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `swing` | `QQQ` | `2026-06-05|swing|QQQ|call|2026-06-26|QQQ260626C00730000|QQQ260626C00750000|730.0|750.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `55` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `swing` | `SPY` | `2026-06-05|swing|SPY|call|2026-06-26|SPY260626C00752000|SPY260626C00770000|752.0|770.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |
| `56` | `capture_fill_attempt_evidence` | `waiting_for_market_window` | `volatility_expansion_observation` | `SPY` | `2026-06-05|volatility_expansion_observation|SPY|call|2026-06-18|SPY260618C00751000|SPY260618C00763000|751.0|763.0` | During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot. |

## Repair-only evidence

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `78` | `repair_replay_evidence` | `repair_only` | `bullish_pullback_observation` | `AAPL` | `` | Exact-date rows exist, but status, sample, forward-validation, or clean-disqualifier gates still block Tier A. |
| `79` | `repair_replay_evidence` | `repair_only` | `bullish_pullback_observation` | `UNH` | `` | Exact-date rows exist, but status, sample, forward-validation, or clean-disqualifier gates still block Tier A. |
| `80` | `repair_replay_evidence` | `repair_only` | `tracked_winner_cheap_debit_continuity_v1` | `DIA` | `` | Exact-date rows exist, but status, sample, forward-validation, or clean-disqualifier gates still block Tier A. |

## Quarantined/no-chase lanes

| Priority | Type | Status | Lane | Ticker | Row | Next step |
| ---: | --- | --- | --- | --- | --- | --- |
| `91` | `no_chase_quarantine` | `blocked_by_no_chase` | `bullish_momentum` | `` | `` | Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence. |
| `92` | `no_chase_quarantine` | `blocked_by_no_chase` | `bullish_pullback_observation` | `` | `` | Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence. |
| `93` | `no_chase_quarantine` | `blocked_by_no_chase` | `short_term` | `` | `` | Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence. |
| `94` | `no_chase_quarantine` | `blocked_by_no_chase` | `swing` | `` | `` | Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence. |

## Prohibited actions

- `do_not_create_trades_from_market_window_checklist`
- `do_not_submit_broker_orders_from_market_window_checklist`
- `do_not_change_stops_from_market_window_checklist`
- `do_not_change_scanner_policy_from_market_window_checklist`
- `do_not_change_sizing_from_market_window_checklist`
- `do_not_enable_live_validation_from_market_window_checklist`
- `do_not_enable_auto_track_from_market_window_checklist`
- `do_not_lower_exact_executable_proof_bars_from_market_window_checklist`
- `do_not_mutate_evidence_databases_from_market_window_checklist`
- `do_not_treat_suggested_trade_review_as_recommendation`
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
- `do_not_create_trades_from_paper_shadow_evidence_plan`
- `do_not_submit_broker_orders_from_paper_shadow_evidence_plan`
- `do_not_change_stops_from_paper_shadow_evidence_plan`
- `do_not_change_scanner_policy_from_paper_shadow_evidence_plan`
- `do_not_change_sizing_from_paper_shadow_evidence_plan`
- `do_not_enable_live_validation_from_paper_shadow_evidence_plan`
- `do_not_enable_auto_track_from_paper_shadow_evidence_plan`
- `do_not_lower_exact_executable_proof_bars_from_paper_shadow_evidence_plan`
- `do_not_mutate_evidence_databases_from_paper_shadow_evidence_plan`
- `do_not_create_live_row_from_fill_attempt_evidence_capture_plan`
- `do_not_submit_broker_order_from_fill_attempt_evidence_capture_plan`
- `do_not_mutate_trading_row_database_from_fill_attempt_evidence_capture_plan`
- `do_not_backfill_broker_fills_from_fill_attempt_evidence_capture_plan`
- `do_not_change_scanner_policy_from_fill_attempt_evidence_capture_plan`
- `do_not_change_stop_policy_from_fill_attempt_evidence_capture_plan`
- `do_not_change_sizing_from_fill_attempt_evidence_capture_plan`
- `do_not_lower_exact_opra_nbbo_proof_bar_from_fill_attempt_evidence_capture_plan`
- `do_not_promote_fill_attempt_plan_to_production_proof`
- `do_not_create_live_row_from_suggested_trade_review_plan`
- `do_not_submit_broker_order_from_suggested_trade_review_plan`
- `do_not_mutate_suggested_trade_database_from_suggested_trade_review_plan`
- `do_not_auto_close_from_stale_display_or_missing_review_marks`
- `do_not_count_suggested_trades_as_production_proof`
- `do_not_change_scanner_policy_from_suggested_trade_review_plan`
- `do_not_change_stop_policy_from_suggested_trade_review_plan`
- `do_not_change_sizing_from_suggested_trade_review_plan`
- `do_not_lower_exact_opra_nbbo_proof_bar_from_suggested_trade_review_plan`
- `do_not_promote_suggested_trade_review_plan_to_production_proof`

## Promotion requirements still missing

- fresh executable exact OPRA/NBBO entry evidence for the lane after freeze.
- fresh executable exact OPRA/NBBO exit evidence and exact realized P&L for the lane.
- promotion_ready_count greater than zero from fresh forward evidence.
- sufficient fresh forward sample size under the policy-defined lane gate.
- positive lane economics under executable pricing, not midpoint, EOD, stale, or display-only marks.
- open-risk governor passing from fresh executable review or legitimate exit evidence.
- no active no-chase or quarantine blocker for the lane.
- paper-shadow/probation evidence bridge complete before any promotion discussion.
- fresh executable exact OPRA/NBBO entry evidence for the paper-shadow lane after freeze.
- policy-defined exact executable OPRA/NBBO exit evidence for linked rows.
- exact realized P&L rows built from executable entry plus executable exit evidence.
- promotion_ready_count greater than zero from the fresh evidence loop.
- sufficient fresh forward sample size under the frozen lane gate.
- open-risk governor clear in fresh local readbacks.

## Source artifacts and staleness

| Source | Status | Age hours | Generated at | Reasons |
| --- | --- | ---: | --- | --- |
| `candidate_outcome_ledger` | `loaded` | `0.09` | `2026-06-27T03:48:42Z` | `[]` |
| `fill_attempt_evidence_capture_plan` | `loaded` | `0.09` | `2026-06-27T03:48:43Z` | `[]` |
| `fresh_evidence_loop` | `loaded` | `0.09` | `2026-06-27T03:48:42Z` | `[]` |
| `gateboard` | `loaded` | `0.02` | `2026-06-27T03:53:00Z` | `[]` |
| `monthly_profitability` | `loaded` | `0.06` | `2026-06-27T03:50:51Z` | `[]` |
| `open_position_risk` | `loaded` | `0.09` | `2026-06-27T03:48:38Z` | `[]` |
| `paper_shadow_evidence_plan` | `loaded` | `0.02` | `2026-06-27T03:52:56Z` | `[]` |
| `suggested_trade_close_risk` | `loaded` | `0.09` | `2026-06-27T03:48:38Z` | `[]` |
| `suggested_trade_review_plan` | `loaded` | `0.09` | `2026-06-27T03:48:43Z` | `[]` |
| `trade_qualification` | `loaded` | `0.06` | `2026-06-27T03:50:52Z` | `[]` |

Source status counts: `{"loaded": 10}`.

## Non-goals

This checklist does not:

- create trades
- submit broker orders
- change stops
- change scanner policy
- change sizing
- lower proof bars
- promote lanes
- mutate evidence databases
