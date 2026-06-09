# Regular Options Profitability Layer Stack

This report is generated from `scripts/build_regular_options_profitability_layer_stack.py`. It wires the 20 profitability iteration layers into one read-only control plane without changing scanner, broker, auth, DB, stop, sizing, or proof behavior.

## Summary

- Status: `profitability_layer_stack_readback`.
- Overall status: `all_20_layers_wired_live_blocked_collect_evidence`.
- Layers wired: `20` / `20`.
- Blocked or collecting layers: `13`.
- Gate statuses: `{"blocked": 6, "collecting": 7, "ready": 7}`.
- Implementation statuses: `{"built": 5, "built_blocked": 4, "built_collecting": 8, "built_replay_coverage_blocked": 2, "built_replay_coverage_ready": 1}`.
- Candidate ledger status: `ledger_live_entry_blocked_collect_evidence`.
- Open-risk status: `open_risk_governor_blocked`.
- Live policy change: `false`.

## Layer Table

| # | Layer | Implementation | Gate | Blockers | Next action |
| ---: | --- | --- | --- | --- | --- |
| `1` | Unified candidate outcome ledger | `built` | `blocked` | open_risk_governor_blocked, no_exact_realized_pnl_rows | Use the ledger queue from priority 0 downward. |
| `2` | Fresh exact paper cohort | `built_collecting` | `collecting` | no_fresh_exact_realized_pnl, paper_probation_exact_entry_required | Collect fresh exact paper entries and exact realized exits, then rebuild the fresh-evidence loop. |
| `3` | Paper-only fill-attempt logging | `built` | `ready` | none | Keep durable fill-attempt logging enabled for every paper/live-validation candidate. |
| `4` | Paper-review create/link workflow | `built_collecting` | `collecting` | paper_review_rows_need_create_or_link | Create/link paper review rows for fresh exact entries; do not count them as live proof. |
| `5` | Fill-discipline paper log | `built` | `ready` | none | Preserve fill-degradation, top alternatives, and leg-spread fields in every fill-attempt row. |
| `6` | Operator next-evidence queue | `built` | `ready` | none | Use `docs/regular-options-candidate-outcome-ledger.md` as the operator queue. |
| `7` | Volatility paper/probation current cohort | `built_collecting` | `blocked` | walk_forward_holdout_too_small_or_failed, fresh_paper_cohort_insufficient, current_live_exact_risk_governor_blocked | Collect current volatility paper exact evidence and clear open-risk before promotion discussion. |
| `8` | Resolve open-risk exact-exit hygiene | `built_blocked` | `blocked` | live_exact_negative_open_risk, exact_exit_evidence_required | Resolve open-risk governor and exact-exit evidence before any new live validation. |
| `9` | Top-spread alternative replay / liquidity-first v2 | `built_replay_coverage_blocked` | `ready` | none | Use the execution-alternative quote-demand manifest to import/query missing trusted OPRA/NBBO alternative entry and exit quotes, then rerun side-aware coverage before changing selection. |
| `10` | Contract replacement for exit survivability | `built_replay_coverage_blocked` | `ready` | none | Use the execution-alternative quote-demand manifest to import/query missing trusted OPRA/NBBO replacement entry and exit quotes, then rerun side-aware coverage before contract-selection changes. |
| `11` | Minute-level exit / quote-deterioration replay | `built_replay_coverage_ready` | `ready` | none | Use the minute-exit readiness queue to build exact OPRA/NBBO minute quote coverage and replay before stop/exit policy changes. |
| `12` | Anti-overfit controls | `built_blocked` | `blocked` | recent_cohort_recovered, fresh_current_policy_rows, fresh_champion_matched_rows, trusted_exact_realized_pnl_rows, point_in_time_replay_pass, paper_monitor_pass | Keep anti-overfit controls active; require later-date and fresh-paper gates before promotion. |
| `13` | Rejected near-miss outcome replay | `built` | `ready` | none | Use missed-pick outcome and failure-mode readbacks before retesting rejected filters. |
| `14` | Tier A bridge watchlist | `built_collecting` | `collecting` | no_paper_shortlist_candidates, no_tier_a_fresh_match_bridge | Watch Tier A clean exact rows until a fresh executable lane-signature bridge appears. |
| `15` | Source-replay repair burn-down | `built_collecting` | `collecting` | source_replay_required_targets | Run source replays before more provider imports or any repair graduation. |
| `16` | Lane-lab freshness reconciler | `built_blocked` | `blocked` | no_live_validation_lanes, open_risk_governor_blocked | Regenerate lane promotion, circuit-breaker, and guardrail-starvation readbacks before candidate routing. |
| `17` | Portfolio throttle replay | `built_blocked` | `blocked` | bullish_pullback_core:unpriced_candidates_3, lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5, lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137, lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch, lane_a:conservative_zero_bid_pf_0.85_below_1_3, lane_a:conservative_zero_bid_unpriced_11, lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0, paper_shadow_fill_evidence_pending | Use portfolio replay as throttle evidence; do not treat count success as quality success. |
| `18` | Risk-budget sizing replay | `built_collecting` | `collecting` | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, open_risk_governor_blocks_sizing, sizing_change_requires_separate_promotion_gate | Use the sizing replay as research readback only; resolve open risk and collect fresh exact sizing evidence before any size-tier change. |
| `19` | Structure-specific multi-leg harness | `built_collecting` | `collecting` | single_leg_or_other_multileg_samples_missing | Use the structure-specific harness as diagnostic readback; collect true executable entry/fill/exit P&L before any structure-specific promotion claim. |
| `20` | Event data spine / post-event vol crush | `built_collecting` | `collecting` | event_calendar_annotations_missing, post_event_vol_crush_replay_rows_missing, true_event_executable_pnl_rows_missing | Use the event data spine as diagnostic readback; collect durable event annotations and true executable post-event P&L before event-sensitive lane changes. |

## Boundary

All 20 layers are wired as readbacks. Blocked or collecting states are intentional fail-closed outputs when market-window evidence, exact exit evidence, source replay, or a deeper replay harness is missing. This stack does not create trades, submit broker orders, change scanner policy, change stops, change sizing, mutate DB state, lower proof bars, or promote paper/research evidence.
