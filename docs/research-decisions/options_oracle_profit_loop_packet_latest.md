# Options Oracle Profit Loop Packet

This artifact is the reusable same-session GPT-5.5 Pro handoff for the regular-options profitability loop.

## Status

- Status: `ready_for_same_session_gpt55_guidance`.
- Frontier status: `current_historical_surface_exhausted_under_current_prohibitions`.
- Countable throughput candidate found: `False`.
- Raw count candidates: `11`.
- Decision counts: `{"blocked_below_strict_new_count": 33, "blocked_execution_quality": 2, "rejected_negative_or_flat_edge": 9}`.

## Continuation Branches

- `fresh_forward_paper_shadow_collection`: requires approval `true`; Only fresh post-freeze executable rows can become proof-qualified profitability.
- `scoped_source_repair_or_replay`: requires approval `true`; May require quote import, evidence repair, or source-surface mutation; must be explicitly scoped.
- `new_causal_playbook_generation`: requires approval `false`; Read-only preregistration/falsification can continue without live or evidence mutation.
- `new_historical_data_surface_or_longer_lookback`: requires approval `true`; Changes the data surface and can invalidate prior branch-scoped stop verdicts.
- `dashboard_or_operator_visibility`: requires approval `false`; Useful only if it changes execution decisions; not significant by itself unless tied to a proof blocker.

## Prompt

```text
You are GPT-5.5 Pro acting as strategic reviewer and next-slice selector for the regular-options profitability loop. Codex will implement and verify exactly one selected task.

Goal: make the regular-options workflow profitable under proof-qualified criteria: at least 30 profitable strict completed forward-audit rows in the latest post-freeze/approximately four-month audit window.

Current state:
- We are not forward-audit profitable.
- Strict completed forward proof is currently 0/30.
- Only real approved forward-cohort rows with exact executable entry and exit evidence may count toward the 30 strict completed forward-audit target. Historical, replay, simulated-forward, dashboard, research/backfill, old-algorithm, midpoint/stale/EOD/last/model/manual/synthetic/lookahead, diagnostic, or repaired historical rows may rank hypotheses but must not be counted as accepted forward profitability.
- Codex can implement, test, inspect the repo, build artifacts, run read-only research, and run non-live/non-broker source-planning tasks.
- The user approves read-only non-live, non-broker research/source-planning work. That approval does not authorize quote import, source-row writes, default source_rows materialization, evidence-store mutation, cohort-log append, protected-holdout use, live validation, auto-track, broker/order actions, promotion, or production scanner/strategy/stop/sizing/proof-bar changes.
- Broker orders, live validation, auto-track, protected-holdout consumption, promotion, production scanner/strategy/stop/sizing/proof-bar changes, and real source/evidence mutation still require exact explicit approval.

Current Fact Table:
- Forward proof: strict completed forward rows are 0/30; promotion_ready, live_entry_allowed, auto_track_allowed, and broker_order_allowed are false.
- Phase 2 forward capture: latest real run produced 0 staged rows, no candidate JSONL, and no cohort log unless a newer current artifact says otherwise.
- Historical rows remain research evidence only; they are not forward profitability proof.
- VIX is cleared when current artifacts show `direct_vix_source_import_materialized` / `point_in_time_vix_bucket_ready` with 505/505 coverage. Do not rank VIX as missing unless a newer artifact is stale, malformed, or policy-incompatible.
- 59-symbol ThetaData repair must be interpreted from the current resume artifact. If it reports `blocked_thetaterminal_source_unavailable_retry`, treat that as provider/source availability. If it reports `blocked_59_symbol_import_repair` / `bulk_import_execution_not_started_by_preflight_wrapper`, treat the blocker as scoped import execution or entitlement-source state, not a stale connection-refused retry.
- 13-symbol historical scanner path remains blocked when current artifacts show 0/24 candidate-generation months and 0 selected rows; quote depth alone is not candidate-generation proof.
- Underlying daily OHLCV is a first-class blocker/source: it is cleared when current source-import status is `underlying_daily_history_source_import_materialized` with generated source rows written. If only acquisition is ready, the next material step is the exact tokened import. If acquisition is missing/invalid, name that source-file/parser blocker. Do not rerun packet-only plans for this blocker.
- Macro-event calendar and flow volume/OI source packets are ready for operator import decision when their current statuses say so, but real trusted CSV/source materialization is still missing.
- Bullish pullback layer4 is a relevant existing economics branch when current docs/artifacts show it: executable economics were profitable but preflight/forward protocol remains blocked or waiting for natural full-denominator market-window capture and explicit approval. Compare it against source-repair branches instead of omitting it.

Evidence precedence:
1. Current Fact Table overrides older embedded blocker text.
2. Latest structured artifact statuses override pasted docs.
3. Older artifact blockers that still name VIX as missing are stale if current VIX is `point_in_time_vix_bucket_ready`.
4. If pasted NEXT_STEPS and structured 59-symbol repair artifacts disagree, prefer the latest resume artifact. Do not select another provider-down retry when the current state is scoped import execution/entitlement-source blocked.
5. Historical/dashboard/replay rows can guide ranking but cannot satisfy forward proof.

Your job:
Do not optimize for documentation completeness. Do not choose the safest artifact by default. Optimize for the shortest honest path to 30 profitable strict completed forward-audit trades.

Before selecting a task, produce a blocker map with these categories:

1. Forward proof blocker
- Why are there 0/30 strict completed forward rows?
- Are current scanners producing real same-day candidates?
- If not, what is the fastest way to increase real candidate throughput without fake rows?

2. Candidate-generation blocker
- Is the current algorithm generating enough eligible candidates?
- If candidate generation is missing/broken, what exact repair unlocks real rows fastest?
- Do not accept quote-depth-only coverage as candidate-generation proof.
- Explicitly evaluate `bullish_pullback_layer4_forward_protocol` as a promising-but-not-proof-complete branch if current docs/artifacts show it. Treat executable economics as research support only until natural market-window/operator-approved forward capture produces proof-qualified rows.

3. Data/source blocker
- Which missing point-in-time sources block the most downstream profitable tests?
- Explicitly evaluate `underlying_daily_point_in_time_source` as a first-class source. If current import status is materialized, do not rank daily OHLCV as missing; rank the remaining opening/intraday underlying, candidate-generation, option-chain, lane-specific input, earnings/calendar, or quote-surface blockers instead.
- VIX is cleared in current artifacts when the VIX bucket is ready; stale branch blockers naming missing VIX must be refreshed and ranked by their remaining non-VIX blockers.
- Macro-event and flow volume/OI are not missing parser/plan work if their packet statuses are ready; they are missing trusted input CSV/source-row materialization.
- Rank source repairs by downstream unlock value, time-to-test, and whether a trusted source file is actually staged and ready.
- Do not select packet-only source planning for a source family whose packet is already ready.
- Do not select source import/materialization unless the corresponding acquisition/readiness artifact identifies a ready trusted source file and the task names the exact required approval/token boundary.

4. Replay/engine blocker
- Which strategies cannot be honestly tested because pricing/replay engine support is missing?
- Consider credit spreads, calendars, diagonals, condors, butterflies, ratio/backspreads, straddles/strangles, PMCC-style diagonals, debit/credit hybrids.
- Rank engine work by ability to unlock countable exact rows.

5. Strategy/edge blocker
- Are we testing enough option edge families?
- Consider volatility risk premium, skew, term structure, event volatility, IV crush, post-event drift, momentum continuation, mean reversion, dispersion proxy, and flow/liquidity effects.
- Do not assume existing directional debit-spread surfaces exhaust the opportunity set.

6. Historical audit blocker
- Can the existing 2-year data be used to produce a strict simulated-forward audit?
- If not, name the exact missing chain: candidate-generation surface, source depth, quote coverage, strict-new dedupe, exact bid/ask pricing, or holdout/proof issue.
- Do not say "collect more data" unless you name the exact file/source/command/threshold.

7. Dashboard/operator blocker
- Only choose dashboard work if it directly changes operator decisions or forward evidence capture.
- Dashboard visibility alone is not a profit upgrade.

Then rank all possible next tasks by:
- expected increase in countable profitable rows,
- chance of unlocking a replay or forward audit,
- time-to-test,
- number of downstream branches unblocked,
- overfit/leakage/data-integrity risk,
- whether it can be done now without live/broker action.

Before selecting the task, answer:
- Is there an already-profitable executable historical/economics branch whose main blocker is forward capture rather than edge quality? If yes, why is it not rank 1?
- What is the shortest honest path to the first 5 strict forward-audit rows?
- Can the selected branch plausibly reach 30 completed strict rows in the latest-four/post-freeze window, given observed or expected candidate cadence?
- Which measurable blocker changes in one Codex turn: staged/validated forward rows, candidate-generation months covered, selected strict-new candidates, replayable exact rows, latest-four audit rows, or PF lower-bound?

Return exactly one next Codex task.

The selected task must include:
- objective,
- why this is the highest-leverage path to profitability,
- exact files/artifacts allowed,
- exact files/artifacts forbidden,
- implementation steps,
- commands to run,
- acceptance criteria,
- failure criteria,
- what downstream replay/audit becomes possible if it passes,
- what branch should be stopped if it fails.

For every serious branch considered, assign one branch status:
- `continue_now`: Codex can execute the next slice under current approvals.
- `approval_blocked`: promising, but requires exact explicit operator approval before execution.
- `source_blocked`: requires a real external source file or provider state change.
- `market_window_blocked`: requires a valid market window and explicit operator confirmation.
- `parked_until_state_change`: do not rerun until a named artifact/status/threshold changes.
- `falsified_under_current_data`: stop this branch under current evidence.
- `exhausted_under_current_data`: no significant upgrade remains without a named new data/source/engine condition.

Stopping a branch is not stopping the global loop. Use `stop_exception` only if all meaningful branches are exhausted or blocked by external input/approval/source availability.

Hard rules:
- Do not repeat a branch already marked parked unless new source state changed.
- Do not select macro_event_calendar_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select direct_point_in_time_vix_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select trusted_flow_volume_oi_source_repair_packet_v1 again if the attached/current artifact status is flow_extreme_source_repair_packet_ready_for_operator_import_decision; it is already implemented and verified.
- Do not select the 59-symbol ThetaTerminal provider-down retry again unless current provider availability is actually down; if the resume artifact is blocked by wrapper execution or entitlement-source state, name that exact blocker.
- Do not select historical dashboard/picks visibility unless it directly affects forward capture.
- Do not select another packet-only source plan for a blocker that already has a verified source packet, parser/import contract, and approval boundary. Packet-only work is allowed only for a newly identified blocker that lacks a safe parser, approval boundary, or measurable acceptance criteria.
- Do not select an import/materialization command unless the needed trusted source file exists or the selected task explicitly asks the operator for the exact approval/source file and provides a safe read-only fallback. Approved non-live source materialization may be recommended when it is the shortest path to a replay or forward audit, but the task must name the source file, approval token, write target, forbidden writes, and pass/fail thresholds.
- Do not select any tokened source import/materialization task when the corresponding acquisition artifact reports `candidate_file_count=0`, `ready_candidate_count=0`, or `selected_ready_source_file=null`. In that case, name the missing trusted source file as an external blocker and choose a different executable Codex task or return a concrete operator source-supply question.
- Do not use local shortcut sources as proof-grade point-in-time inputs: `market_data.db:daily_history`, historical reconstruction, inferred known-at policy, fixture/sample rows, manual rows, synthetic rows, source-mark rows, midpoint/EOD/last/model rows, or lookahead rows.
- Do not select any 13-symbol runner-support, no-write-runner, source-surface, denominator, entrypoint, engine-diagnostics, atlas, or dashboard task unless it can change these metrics: `candidate_generation_months_covered_count`, `selected_candidate_row_count`, `latest_four_strict_new_candidates`, and `historical_simulated_forward_audit_command`. Re-emitting 6,916 blocked rows with `missing_daily_candidate_generation_diagnostics` is a failed repeat and should stop that branch until a real daily frozen candidate-decision source or required point-in-time input source changes.
- For any replay/engine task, acceptance criteria must include `denominator_rows`, `priced_exact_rows`, `strict_new_exact_completed_rows`, side-aware entry/exit pricing basis, fees/slippage, assignment/expiration/max-loss/collateral handling where structure-specific, strict-new dedupe, protected-holdout guard, net USD P&L, PF, and latest-four/post-freeze row counts. If `priced_exact_rows=0`, the task must name the single smallest next blocker and the branch stop condition.
- Do not claim accepted profitability from historical rows alone or in combination with simulated-forward/research rows. Accepted profitability requires strict completed forward-audit rows from the approved forward cohort path.
- Do not stop unless you prove no meaningful upgrade remains across forward capture, source repair/materialization, candidate-generation repair, replay engine support, new option structures, and longer/lookback audits.

Current repo evidence appendix follows. Use this evidence for the blocker map and next-task ranking; do not ignore completed/parked artifacts.

We are continuing the same regular-options profitability loop in the existing GPT-5.5 Pro ChatGPT session.

You are GPT-5.5 Pro acting as strategic reviewer and next-slice selector. Codex will implement and verify. The user wants this loop to continue until GPT-5.5 Pro says there are no significant upgrades left.

Operator approval posture:
{
  "fixture_temp_verification_generated_artifacts": "pre_approved_by_user_for_loop_continuation",
  "questions_to_gpt55": "Do not block on read-only/research-only operator questions; state the assumption as approved and choose the next task.",
  "read_only_research_only_work": "pre_approved_by_user_for_loop_continuation",
  "still_requires_separate_explicit_approval": [
    "broker orders or order preparation",
    "live validation",
    "auto-track enablement",
    "production scanner, strategy, stop, sizing, or proof-bar changes",
    "quote import",
    "source-row writes or default source_rows materialization",
    "cohort-log append",
    "protected-holdout consumption",
    "promotion",
    "unsafe evidence-store mutation"
  ]
}

Primary goal:
Make the regular-options workflow profitable under proof-qualified criteria. The practical target is at least 30 profitable strict completed rows in the latest approximately four months / post-freeze forward-style audit window. Profit means executable exact net P&L after fees/slippage, defensible PF/lower-bound/holdout/forward proof, and no unresolved data-quality defects that could flip the result. Do not accept raw overlapping historical count, midpoint/stale/display/EOD/last/model/manual marks, lookahead-only rows, zero-bid/untradable rows, or historical dashboard/replay rows as live proof.

Current proof posture:
- The system is not forward-audit profitable.
- Strict post-freeze forward proof is currently 0/30 completed exact rows.
- The historical current-policy replay panel was removed from the operator dashboard because it could be mistaken for current recommendations or forward-audit performance.
- The latest-four-month simulated audit is hypothesis-generating only unless its row set, data depth, leakage controls, and PF lower-bound satisfy the strict proof contract.

Current frontier result:
{
  "base_clean_stack_exact_rows": 157,
  "candidate_count": 44,
  "countable_throughput_candidate_found": false,
  "current_historical_surface_exhausted_under_current_prohibitions": true,
  "decision_counts": {
    "blocked_below_strict_new_count": 33,
    "blocked_execution_quality": 2,
    "rejected_negative_or_flat_edge": 9
  },
  "raw_count_candidate_count": 11,
  "status": "current_historical_surface_exhausted_under_current_prohibitions",
  "strict_new_gap_required": 43,
  "target_exact_rows": 200
}

Current momentum-edge result:
{
  "countable_momentum_edge_candidate_count": 0,
  "decision_counts": {
    "blocked_below_trade_count_target": 5,
    "raw_count_target_met_but_not_countable_edge": 2,
    "rejected_negative_or_flat_edge": 10
  },
  "status": "raw_count_available_but_not_countable_profitable_edge"
}

Current causal-falsification result, if available:
{
  "branches_to_stop": [
    "raw overlapping count aggregation",
    "tracked-winner count retuning without new causal evidence",
    "clean index/IWM refill as the primary gap closer",
    "existing current-regime momentum-compatible artifact aggregation"
  ],
  "continue_loop": true,
  "hypothesis_status_counts": {
    "falsified_existing_surface": 4,
    "not_falsified_requires_next_oracle_or_operator_selection": 1
  },
  "significant_upgrade_available": true,
  "status": "existing_surface_falsified_new_causal_branch_still_possible"
}

Current preregistered playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation, replay, quote import, evidence mutation, or forward collection requires a separate explicit decision.",
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "lane_implementation_performed": false,
  "status": "preregistered_design_only"
}

Current approved momentum-continuation research replay result, if available:
{
  "accepted_profitability": false,
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "denominator_rows": 1291,
  "denominator_status_counts": {
    "duplicate_within_research_harness": 461,
    "missing_point_in_time_breadth_confirmation": 415,
    "rejected_not_call_debit_spread": 237,
    "rejected_outside_preregistered_universe": 178
  },
  "diagnostic_only_metrics": {
    "avg_pnl_usd": -65.68,
    "gross_loss_usd": 239470.75,
    "gross_win_usd": 180623.09,
    "loss_count": 427,
    "net_pnl_usd": -58847.66,
    "priced_row_count": 896,
    "profit_factor": 0.7543,
    "row_count": 896,
    "win_count": 469,
    "win_rate_pct": 52.34
  },
  "historical_replay_performed": true,
  "lane_implementation_performed": false,
  "proof_metrics": {
    "avg_pnl_usd": null,
    "gross_loss_usd": 0,
    "gross_win_usd": 0,
    "loss_count": 0,
    "net_pnl_usd": null,
    "priced_row_count": 0,
    "profit_factor": null,
    "row_count": 0,
    "win_count": 0,
    "win_rate_pct": null
  },
  "proof_qualified_rows": 0,
  "research_only_replay_harness_implemented": true,
  "status": "implemented_research_replay_no_proof_qualified_rows",
  "top_blockers": [
    {
      "reason": "missing_point_in_time_breadth_confirmation",
      "row_count": 1291
    },
    {
      "reason": "missing_side_aware_exit_bid_ask",
      "row_count": 1291
    },
    {
      "reason": "missing_point_in_time_qqq_momentum_confirmation",
      "row_count": 1080
    },
    {
      "reason": "spread_diagnostics_marked_diagnostic_only",
      "row_count": 1064
    },
    {
      "reason": "entry_contains_mid_quote_basis",
      "row_count": 896
    },
    {
      "reason": "duplicate_within_research_harness",
      "row_count": 461
    },
    {
      "reason": "missing_net_usd_pnl",
      "row_count": 395
    },
    {
      "reason": "missing_point_in_time_spy_momentum_confirmation",
      "row_count": 395
    },
    {
      "reason": "rejected_not_call_debit_spread",
      "row_count": 290
    },
    {
      "reason": "rejected_outside_preregistered_universe",
      "row_count": 277
    },
    {
      "reason": "missing_side_aware_entry_bid_ask",
      "row_count": 227
    }
  ]
}

Current momentum-continuation proof-blocker resolution result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "bootstrap_pf_lower_bound_not_above_1_after_resolution",
    "duplicate_within_research_harness",
    "entry_missing_leg_quote",
    "exit_missing_leg_quote",
    "exit_value_negative",
    "exit_zero_or_nonpositive_bid_ask",
    "missing_net_usd_pnl",
    "missing_point_in_time_breadth_confirmation",
    "missing_point_in_time_qqq_momentum_confirmation",
    "missing_point_in_time_spy_momentum_confirmation",
    "net_usd_not_positive_after_resolution",
    "rejected_not_call_debit_spread",
    "rejected_outside_preregistered_universe",
    "strict_rows_below_30_after_resolution"
  ],
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "historical_rows_are_forward_proof": false,
  "proof_qualified_rows_after_resolution": 0,
  "proof_qualified_rows_before_resolution": 0,
  "reconstructed_denominator_rows": 1291,
  "resolution_counts": {
    "blocker_counts": {
      "duplicate_within_research_harness": 461,
      "entry_missing_leg_quote": 227,
      "exit_missing_leg_quote": 413,
      "exit_value_negative": 6,
      "exit_zero_or_nonpositive_bid_ask": 95,
      "missing_net_usd_pnl": 395,
      "missing_point_in_time_breadth_confirmation": 1291,
      "missing_point_in_time_qqq_momentum_confirmation": 1080,
      "missing_point_in_time_spy_momentum_confirmation": 395,
      "rejected_not_call_debit_spread": 290,
      "rejected_outside_preregistered_universe": 277
    },
    "full_denominator_fail_closed": 1291,
    "point_in_time_breadth_confirmation_resolved": 0,
    "point_in_time_inputs_resolved": 0,
    "point_in_time_market_regime_inputs_resolved": 0,
    "point_in_time_qqq_momentum_confirmation_resolved": 0,
    "point_in_time_spy_momentum_confirmation_resolved": 0,
    "point_in_time_vix_bucket_resolved": 1291,
    "proof_qualified_candidate_rows": 0,
    "side_aware_quotes_resolved": 783
  },
  "side_aware_diagnostic_metrics": {
    "avg_pnl_usd": 201.07,
    "bootstrap_pf_lower_bound_5pct": null,
    "gross_loss_usd": 121252.6,
    "gross_win_usd": 278693.8,
    "loss_count": 281,
    "net_pnl_usd": 157441.2,
    "priced_row_count": 783,
    "profit_factor": 2.2985,
    "row_count": 783,
    "stress_pf": 2.2985,
    "win_count": 502,
    "win_rate_pct": 64.11
  },
  "source_denominator_rows": 1291,
  "status": "momentum_continuation_blocked_missing_local_proof_inputs",
  "strict_research_metrics": {
    "avg_pnl_usd": null,
    "bootstrap_pf_lower_bound_5pct": null,
    "gross_loss_usd": 0,
    "gross_win_usd": 0,
    "loss_count": 0,
    "net_pnl_usd": null,
    "priced_row_count": 0,
    "profit_factor": null,
    "row_count": 0,
    "stress_pf": null,
    "win_count": 0,
    "win_rate_pct": null
  }
}

Current momentum-continuation bounded replay gate result, if available:
{
  "accepted_profitability": false,
  "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
  "existing_resolution_consumed": true,
  "historical_replay_performed": false,
  "historical_rows_are_forward_proof": false,
  "metrics": {
    "blocker_counts": {
      "duplicate_within_research_harness": 461,
      "entry_missing_leg_quote": 227,
      "exit_missing_leg_quote": 413,
      "exit_value_negative": 6,
      "exit_zero_or_nonpositive_bid_ask": 95,
      "missing_net_usd_pnl": 395,
      "missing_point_in_time_breadth_confirmation": 1291,
      "missing_point_in_time_qqq_momentum_confirmation": 1080,
      "missing_point_in_time_spy_momentum_confirmation": 395,
      "rejected_not_call_debit_spread": 290,
      "rejected_outside_preregistered_universe": 277
    },
    "exact_completed_rows": 0,
    "latest_audit_30_row_bar_met": false,
    "minimum_historical_exact_rows": 200,
    "old_mark_diagnostic_metrics": {
      "avg_pnl_usd": -65.68,
      "gross_loss_usd": 239470.75,
      "gross_win_usd": 180623.09,
      "loss_count": 427,
      "net_pnl_usd": -58847.66,
      "priced_row_count": 896,
      "profit_factor": 0.7543,
      "row_count": 896,
      "win_count": 469,
      "win_rate_pct": 52.34
    },
    "point_in_time_inputs_resolved": 0,
    "proof_qualified_rows_after_resolution": 0,
    "quote_coverage": 0.6065,
    "replay_gate_blocker_count": 14,
    "side_aware_diagnostic_metrics": {
      "avg_pnl_usd": 201.07,
      "bootstrap_pf_lower_bound_5pct": null,
      "gross_loss_usd": 121252.6,
      "gross_win_usd": 278693.8,
      "loss_count": 281,
      "net_pnl_usd": 157441.2,
      "priced_row_count": 783,
      "profit_factor": 2.2985,
      "row_count": 783,
      "stress_pf": 2.2985,
      "win_count": 502,
      "win_rate_pct": 64.11
    },
    "side_aware_quotes_resolved": 783,
    "strict_new_exact_completed_rows": 0,
    "strict_research_metrics": {
      "avg_pnl_usd": null,
      "bootstrap_pf_lower_bound_5pct": null,
      "gross_loss_usd": 0,
      "gross_win_usd": 0,
      "loss_count": 0,
      "net_pnl_usd": null,
      "priced_row_count": 0,
      "profit_factor": null,
      "row_count": 0,
      "stress_pf": null,
      "win_count": 0,
      "win_rate_pct": null
    },
    "total_denominator_rows": 1291
  },
  "next_oracle_instruction": "Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time breadth/momentum input surface or explicit approved data repair changes the blocker. Select the next materially different, falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows.",
  "replay_gate_blockers": [
    "bootstrap_pf_lower_bound_not_above_1_after_resolution",
    "duplicate_within_research_harness",
    "entry_missing_leg_quote",
    "exit_missing_leg_quote",
    "exit_value_negative",
    "exit_zero_or_nonpositive_bid_ask",
    "missing_net_usd_pnl",
    "missing_point_in_time_breadth_confirmation",
    "missing_point_in_time_qqq_momentum_confirmation",
    "missing_point_in_time_spy_momentum_confirmation",
    "net_usd_not_positive_after_resolution",
    "rejected_not_call_debit_spread",
    "rejected_outside_preregistered_universe",
    "strict_rows_below_30_after_resolution"
  ],
  "status": "blocked_momentum_continuation_bounded_replay"
}

Current preregistered VRP credit-spread playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_put_credit_spreads_only"
}

Current VRP credit-spread replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If blocked, GPT-5.5 Pro should decide whether a named blocker needs operator approval or whether another read-only option-structure branch remains.",
  "blockers": [
    "missing_index_credit_spread_quote_surface"
  ],
  "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "blocked_vrp_credit_spread_bounded_replay_gate"
}

Current preregistered term-structure calendar/diagonal playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_calendar_or_diagonal_debit_spreads_only"
}

Current term-structure calendar/diagonal replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If ready, the next step is one bounded research-only implementation/replay task inside the current non-live, non-broker research posture. If blocked, GPT-5.5 Pro should decide whether a named blocker needs approval or whether another read-only option-structure branch remains.",
  "blockers": [
    "missing_index_calendar_quote_surface",
    "missing_point_in_time_term_structure_inputs"
  ],
  "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "blocked_term_structure_calendar_bounded_replay"
}

Current preregistered skew broken-wing playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_index_skew_broken_wing_put_fly_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_broken_wing_put_butterflies_only"
}

Current preregistered macro-event long straddle/strangle playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_long_straddles_or_strangles_only"
}

Current macro-event calendar artifact result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "macro_event_calendar_source_missing",
    "missing_required_macro_event_categories"
  ],
  "covered_categories": [],
  "event_calendar_implemented": true,
  "event_count": 0,
  "historical_replay_performed": false,
  "missing_categories": [
    "cpi",
    "fomc_minutes",
    "fomc_rate_decision",
    "nonfarm_payrolls",
    "pce",
    "scheduled_fed_chair_testimony"
  ],
  "source_rows_proof_eligible": false,
  "status": "blocked_macro_event_calendar_source_missing"
}

Current point-in-time VIX bucket artifact result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
  "coverage_pct": 100.0,
  "covered_date_count": 505,
  "historical_replay_performed": false,
  "late_known_at_count": 0,
  "leakage_reject_count": 0,
  "point_in_time_vix_low_mid_bucket_available": true,
  "requested_date_count": 505,
  "source_rows_count": 505,
  "source_status": "loaded",
  "status": "point_in_time_vix_bucket_ready"
}

Current macro-event long straddle/strangle replay readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this readiness artifact back to GPT-5.5 Pro for continue/stop. A later bounded read-only replay requires a separate Codex task, and still cannot enable live validation, auto-track, broker orders, quote import, evidence mutation, protected-holdout consumption, scanner release, proof-bar changes, or promotion.",
  "blockers": [
    "macro_event_calendar_source_missing"
  ],
  "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "smallest_next_blocker_clearing_slice": {
    "blocker": "macro_event_calendar_source_missing",
    "smallest_future_codex_slice": "Clear exactly this named blocker with a read-only artifact before replay."
  },
  "status": "blocked_macro_event_long_strangle_replay_readiness"
}

Current 13-symbol candidate-generation surface audit result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "existing_candidate_generation_surface_not_frozen_13_symbol",
    "missing_candidate_generation_diagnostics",
    "not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof",
    "quote_depth_only_months_cannot_count",
    "source_artifact_universe_not_13_symbol"
  ],
  "candidate_surface": {
    "frozen_universe_exact_13_symbols": false,
    "non_13_symbol_selected_row_count": 0,
    "outside_allowed_universe": [
      "AA",
      "ABBV",
      "AMD",
      "AMT",
      "AMZN",
      "ARM",
      "BA",
      "BAC",
      "C",
      "CAT",
      "CLF",
      "COIN",
      "COST",
      "DE",
      "DIS",
      "EQR",
      "FCX",
      "GS",
      "JPM",
      "KO",
      "LIN",
      "LMT",
      "MCD",
      "META",
      "MSFT",
      "MSTR",
      "NFLX",
      "NKE",
      "NVDA",
      "OXY",
      "PFE",
      "PG",
      "PLD",
      "PLTR",
      "PM",
      "RTX",
      "SBUX",
      "SLB",
      "SMCI",
      "SPG",
      "T",
      "TSLA",
      "V",
      "WELL",
      "WMT",
      "XLK"
    ]
  },
  "cvx_scope": {
    "cvx_scope_enforced": true,
    "excluded_months": [],
    "excluded_trade_count": 0,
    "minimum_executable_quote_pct": 90.0,
    "observed_executable_quote_pct": 88.66,
    "policy_blocker": null,
    "policy_loaded": true,
    "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
    "rule_status": "active"
  },
  "historical_rows_are_forward_proof": false,
  "quote_vs_candidate_generation": {
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "distinction": "quote-history coverage does not prove pick/no-pick candidate-generation coverage",
    "quote_surface_months_available": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "quote_surface_months_available_count": 24,
    "selected_trade_depth_months_covered": [
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03"
    ],
    "selected_trade_depth_months_covered_count": 8
  },
  "runner_support": {
    "candidate_commands": [
      "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json"
    ],
    "read_only_no_write_runner_available": true,
    "rejected_commands": [],
    "source_artifact_status": "candidate_generation_no_write_runner_ready_with_blockers",
    "status": "read_only_no_write_runner_available",
    "support_manifest": {
      "as_of_date": "2026-06-04",
      "as_of_gated": true,
      "candidate_commands": [
        "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json"
      ],
      "evidence_stores_mutated": false,
      "frozen_universe_exact_13_symbols": true,
      "mutating": false,
      "no_write": true,
      "pre_holdout_as_of": true,
      "production_scanner_changed": false,
      "proof_bars_changed": false,
      "protected_holdout_consumed": false,
      "quotes_imported": false,
      "read_only": true,
      "read_only_no_write_runner_available": true,
      "research_only": true,
      "sizing_changed": false,
      "stops_changed": false,
      "strategy_logic_changed": false,
      "universe_filter": true
    },
    "validation_reason_codes": []
  },
  "status": "blocked_13_symbol_candidate_generation_surface_audit"
}

Current frozen 13-symbol reusable candidate-generation entrypoint result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "missing_historical_entry_underlying_price_surface",
    "missing_historical_option_chain_selection_surface",
    "missing_historical_scanner_point_in_time_inputs",
    "missing_lane_specific_point_in_time_feature_inputs",
    "missing_point_in_time_earnings_calendar_source"
  ],
  "coverage": {
    "blocked_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "zero_selection_months": [],
    "zero_selection_months_explicit": false
  },
  "daily_candidate_generation_row_count": 6916,
  "daily_status_counts": {
    "blocked_missing_historical_scanner_point_in_time_inputs": 6916
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "read_only": true,
  "selected_candidate_row_count": 0,
  "status": "blocked_frozen_13_symbol_candidate_generation_entrypoint"
}

Current 13-symbol frozen candidate-generation source-surface materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "candidate_generation_months_0_below_requested_24",
    "missing_daily_candidate_generation_diagnostics",
    "missing_historical_entry_underlying_price_surface",
    "missing_historical_option_chain_selection_surface",
    "missing_historical_scanner_point_in_time_inputs",
    "missing_lane_specific_point_in_time_feature_inputs",
    "missing_point_in_time_earnings_calendar_source"
  ],
  "calendar_coverage": {
    "calendar_months_covered": [],
    "calendar_months_covered_count": 0,
    "coverage_basis": "source_surface_not_frozen_13_symbol_or_missing_month_diagnostics",
    "covered_months": [],
    "status": "calendar_coverage_not_proven",
    "unproven_requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "zero_selection_months": [],
    "zero_selection_months_explicit": false
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "posthoc_filtering_allowed_as_proof": null,
  "read_only": true,
  "selected_trade_summary": {
    "selected_entry_months_with_rows": [],
    "selected_rows_in_window": 0
  },
  "source_artifact_universe_exact_13_symbols": null,
  "status": "blocked_13_symbol_frozen_candidate_generation_source_surface"
}

Current frozen 13-symbol candidate-generation engine result, if available:
{
  "accepted_profitability": false,
  "audit_consumed_generated_surface": false,
  "blockers": [
    "blocked_daily_candidate_generation_coverage",
    "blocked_latest_audit_rows_below_30",
    "blocked_train_or_audit_month_coverage",
    "candidate_generation_months_0_below_requested_24",
    "missing_historical_entry_underlying_price_surface",
    "missing_historical_option_chain_selection_surface",
    "missing_historical_scanner_point_in_time_inputs",
    "missing_lane_specific_point_in_time_feature_inputs",
    "missing_point_in_time_earnings_calendar_source"
  ],
  "coverage": {
    "audit_months_covered": 0,
    "blocked_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "candidate_generation_months_covered": [],
    "candidate_generation_months_covered_count": 0,
    "latest_audit_exact_trades": 0,
    "latest_four_strict_new_candidates": 0,
    "missing_daily_diagnostics": 24,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "train_months_covered": 0
  },
  "daily_candidate_generation_row_count": 6916,
  "decision": "blocked_frozen_candidate_generation_entrypoint_incomplete",
  "historical_simulated_forward_audit_command": null,
  "legacy_blocker_aliases": [
    "missing_frozen_13_symbol_candidate_generation_engine"
  ],
  "no_write": true,
  "read_only": true,
  "reusable_entrypoint_discovery": {
    "artifact_path": "C:\\Users\\kalec\\options-chatbot\\data\\profitability-lab\\regular-options-13-symbol-frozen-candidate-generation-entrypoint\\latest.json",
    "artifact_status": "blocked_frozen_13_symbol_candidate_generation_entrypoint",
    "available": true,
    "basis": "frozen_entrypoint_artifact",
    "entrypoint": "scripts/regular_options_frozen_candidate_generation_entrypoint.py"
  },
  "selected_candidate_row_count": 0,
  "status": "blocked_frozen_13_symbol_candidate_generation_engine"
}

Interpretation: the reusable frozen entrypoint now exists, but the real latest readback still has 0/24 covered candidate-generation months and 0 selected candidates because every daily row is blocked by missing daily candidate-generation diagnostics. Do not repeat the 13-symbol source-surface/no-write/denominator/engine branch unless a real daily frozen candidate-generation source changes this blocker. Treat quote depth alone as insufficient. Choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current preregistered post-event IV-crush iron-condor playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.",
  "concept_id": "post_event_iv_crush_index_iron_condor_v1",
  "event_calendar_implemented_in_this_slice": false,
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_short_iron_condors_or_iron_butterflies_only"
}

Current preregistered flow-extreme ratio/backspread playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk spreads, and promotion.",
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_ratio_spreads_or_backspreads_only",
  "undefined_risk_allowed": false
}

Current flow-extreme volume/open-interest source-row generator result, if available:
{
  "accepted_profitability": false,
  "aggregate_source_summary": {
    "aggregate_row_count": 1635,
    "data_trust": "trusted",
    "date_count": 501,
    "snapshot_kind": "intraday",
    "source_labels": [
      "thetadata_opra_nbbo_1m"
    ],
    "usable_aggregate_row_count": 0
  },
  "blockers": [
    "missing_trusted_volume_open_interest_source_rows",
    "trusted_rows_have_null_volume_open_interest",
    "insufficient_month_coverage",
    "insufficient_date_coverage"
  ],
  "coverage": {
    "covered_date_count": 0,
    "covered_month_count": 0,
    "covered_months": [],
    "date_coverage_pct": 0.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ]
  },
  "evidence_stores_mutated": false,
  "historical_rows_are_forward_proof": false,
  "quotes_imported": false,
  "source_row_count": 0,
  "status": "blocked_flow_extreme_volume_oi_source_rows",
  "threshold_policy": {
    "flow_input_basis": "volume_open_interest",
    "future_outcomes_used": false,
    "known_at_rule": "prior trusted source date strictly before input_date_et",
    "outcome_tuned": false,
    "plain_bid_ask_used_as_flow": false,
    "quote_depth_fabricated": false,
    "realized_pnl_used": false,
    "selected_winners_used": false,
    "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1"
  },
  "write_source_rows_allowed": false
}

Current point-in-time flow-extreme input materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [
    "missing_point_in_time_flow_extreme_source",
    "missing_required_flow_fields",
    "insufficient_month_coverage",
    "insufficient_date_coverage"
  ],
  "coverage": {
    "covered_date_count": 0,
    "covered_month_count": 0,
    "covered_months": [],
    "date_coverage_pct": 0.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "required_underlyings": [
      "QQQ",
      "SPY"
    ]
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "proxy_basis": [],
  "read_only": true,
  "source_inventory": {
    "feature_store": {
      "available_symbols": [
        "QQQ",
        "SPY"
      ],
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-18T06:09:35Z",
      "inventory_status": "feature_store_loaded_for_underlyings",
      "missing_symbols": [],
      "path": "data/profitability-lab/regular-options-feature-store/latest.json",
      "report_id": "regular_options_feature_store",
      "requested_date_count": 494,
      "required": true,
      "status": "loaded",
      "status_value": "feature_store_built"
    },
    "options_history_db": {
      "error": null,
      "exists": true,
      "flow_columns": {
        "ask_size": false,
        "bid_size": false,
        "open_interest": true,
        "quote_depth": false,
        "volume": true
      },
      "path": "data/options-validation/options_history.db",
      "status": "loaded",
      "tables": {
        "import_batches": [
          "id",
          "source_label",
          "dataset_kind",
          "data_trust",
          "input_path",
          "file_hash",
          "imported_at_utc",
          "total_rows",
          "imported_rows",
          "duplicate_rows",
          "rejected_rows",
          "warnings_json"
        ],
        "option_quote_snapshots": [
          "id",
          "as_of_utc",
          "quote_date_et",
          "quote_minute_et",
          "snapshot_kind",
          "underlying",
          "contract_symbol",
          "expiry",
          "option_type",
          "strike",
          "bid",
          "ask",
          "last",
          "iv",
          "underlying_price",
          "volume",
          "open_interest",
          "source_batch_id"
        ],
        "sqlite_sequence": [
          "name",
          "seq"
        ]
      }
    },
    "plain_bid_ask_only_is_not_flow": true,
    "preregistered_playbook": {
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-23T05:51:48Z",
      "path": "data/profitability-lab/regular-options-preregistered-flow-extreme-ratio-backspread-playbook/latest.json",
      "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
      "required": true,
      "status": "loaded",
      "status_value": "preregistered_design_only"
    },
    "schema_declared_flow_basis": {
      "bid_ask_size_imbalance": false,
      "quote_depth_pressure": false,
      "volume_open_interest": true
    },
    "source_rows": {
      "error": null,
      "exists": false,
      "path": "data/profitability-lab/regular-options-point-in-time-flow-extreme-input/source_rows.jsonl",
      "required": false,
      "row_count": 0,
      "status": "missing"
    },
    "status": "missing_flow_source_rows"
  },
  "status": "blocked_point_in_time_flow_extreme_input"
}

Current multi-leg side-aware pricing capability result, if available:
{
  "accepted_profitability": false,
  "fixture_source_not_proof_eligible": true,
  "historical_rows_are_forward_proof": false,
  "pricing_capability_blockers": [],
  "quote_resolution_counts": {
    "blocker_counts": {},
    "fixture_count": 1,
    "resolved_fixture_count": 1,
    "status_counts": {
      "exact_exit_captured": 1
    }
  },
  "source_inventory": {
    "bid_ask_schema_fields": [
      "bid",
      "ask"
    ],
    "contract_symbol_fields": [
      "underlying",
      "contract_symbol",
      "expiry",
      "option_type",
      "strike"
    ],
    "error": null,
    "exists": true,
    "path": "data/options-validation/options_history.db",
    "quote_timestamp_fields": [
      "as_of_utc",
      "quote_date_et",
      "quote_minute_et"
    ],
    "read_only_mode": true,
    "status": "loaded",
    "tables": {
      "import_batches": {
        "columns": [
          "id",
          "source_label",
          "dataset_kind",
          "data_trust",
          "input_path",
          "file_hash",
          "imported_at_utc",
          "total_rows",
          "imported_rows",
          "duplicate_rows",
          "rejected_rows",
          "warnings_json"
        ]
      },
      "option_quote_snapshots": {
        "columns": [
          "id",
          "as_of_utc",
          "quote_date_et",
          "quote_minute_et",
          "snapshot_kind",
          "underlying",
          "contract_symbol",
          "expiry",
          "option_type",
          "strike",
          "bid",
          "ask",
          "last",
          "iv",
          "underlying_price",
          "volume",
          "open_interest",
          "source_batch_id"
        ]
      },
      "sqlite_sequence": {
        "columns": [
          "name",
          "seq"
        ]
      }
    },
    "trusted_source_labels": [
      "alpaca_opra_daily_snapshot",
      "thetadata_opra_nbbo_1m"
    ]
  },
  "status": "multi_leg_side_aware_pricing_capability_available",
  "structure_support": {
    "ratio_backspread_bounded": {
      "blockers": [],
      "denominator_mapping_status": "ready",
      "fixture_count": 1,
      "resolved_fixture_count": 1,
      "status": "available",
      "undefined_or_naked_ratio_risk_allowed": false
    }
  }
}

Current base clean stack row-level identity ledger result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "duplicate_identity_count": 0,
  "expected_base_clean_stack_exact_rows": 157,
  "future_or_outcome_field_dependency_count": 0,
  "historical_rows_are_forward_proof": false,
  "ledger_row_count": 157,
  "missing_identity_field_row_count": 0,
  "proof_row_count": 0,
  "protected_holdout_overlap_count": 0,
  "status": "base_clean_stack_identity_ledger_ready",
  "unique_identity_count": 157
}

Current flow-extreme denominator/dedupe bridge result, if available:
{
  "accepted_profitability": false,
  "base_identity_hash_count": 157,
  "base_identity_ledger_status": "ready",
  "bridge_blockers": [],
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "denominator_status_contract": [
    "candidate_not_generated_missing_flow_input",
    "candidate_not_generated_missing_vix_bucket",
    "candidate_rejected_missing_required_flow_fields",
    "candidate_rejected_missing_vix_bucket",
    "candidate_rejected_unbounded_or_undefined_risk",
    "candidate_rejected_missing_leg_quote",
    "candidate_rejected_zero_bid_or_untradable",
    "candidate_rejected_crossed_or_stale_quote",
    "candidate_duplicate_existing_base_stack",
    "candidate_duplicate_within_research_harness",
    "candidate_protected_holdout_overlap",
    "priced_fixture_not_proof_eligible",
    "readiness_candidate_priced_not_replayed",
    "no_pick_explicit",
    "blocked_source_missing"
  ],
  "fixture_source_not_proof_eligible": true,
  "full_denominator_mapping_status": "ready",
  "historical_rows_are_forward_proof": false,
  "identity_fields": [
    "concept_id",
    "structure",
    "underlying",
    "signal_date",
    "planned_entry_timestamp",
    "option_rights",
    "expirations",
    "strikes",
    "leg_sides",
    "leg_ratios",
    "entry_policy",
    "exit_policy",
    "candidate_source_id"
  ],
  "proof_row_count": 0,
  "status": "flow_extreme_denominator_dedupe_bridge_ready",
  "strict_new_dedupe_status": "ready",
  "structure": "ratio_backspread_bounded"
}

Current flow-extreme ratio/backspread replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.",
  "blockers": [
    "missing_point_in_time_flow_extreme_input"
  ],
  "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "packet_ingestion": {
    "expected_concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
    "expected_report_id": "regular_options_flow_extreme_ratio_backspread_replay_readiness",
    "expected_structure": "defined_risk_ratio_spreads_or_backspreads_only",
    "generated_at_utc": "2026-06-24T02:40:26Z",
    "playbook_generated_at_utc": "2026-06-23T05:51:48Z",
    "raw_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
    "reason_codes": [],
    "unsafe_flags": [],
    "validated_status": "blocked_flow_extreme_ratio_backspread_replay_readiness"
  },
  "raw_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": "missing_point_in_time_flow_extreme_input",
  "status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
  "structure": "defined_risk_ratio_spreads_or_backspreads_only",
  "undefined_risk_allowed": false
}

Current preregistered dispersion-proxy hybrid playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk pair structures, and promotion.",
  "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only",
  "undefined_or_uncapped_pair_risk_allowed": false
}

Current point-in-time dispersion/concentration proxy materializer result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "coverage": {
    "covered_date_count": 494,
    "covered_month_count": 24,
    "covered_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ],
    "date_coverage_pct": 100.0,
    "minimum_covered_months": 20,
    "minimum_date_coverage_pct": 90.0,
    "missing_months": [],
    "requested_date_count": 494,
    "requested_month_count": 24,
    "requested_months": [
      "2024-06",
      "2024-07",
      "2024-08",
      "2024-09",
      "2024-10",
      "2024-11",
      "2024-12",
      "2025-01",
      "2025-02",
      "2025-03",
      "2025-04",
      "2025-05",
      "2025-06",
      "2025-07",
      "2025-08",
      "2025-09",
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05"
    ]
  },
  "historical_rows_are_forward_proof": false,
  "no_write": true,
  "read_only": true,
  "source_inventory": {
    "feature_store": {
      "available_symbols": [
        "AAPL",
        "COP",
        "CVX",
        "DIA",
        "GOOGL",
        "IWM",
        "JNJ",
        "LLY",
        "NEM",
        "QQQ",
        "SPY",
        "UNH",
        "XOM"
      ],
      "error": null,
      "exists": true,
      "generated_at_utc": "2026-06-27T03:50:44Z",
      "inventory_status": "feature_store_return_fields_present",
      "missing_symbols": [],
      "path": "data/profitability-lab/regular-options-feature-store/latest.json",
      "proxy_source_rows_provide_return_fields": true,
      "report_id": "regular_options_feature_store",
      "requested_date_count": 494,
      "required": true,
      "return_fields_available": true,
      "status": "loaded",
      "status_value": "feature_store_built",
      "underlying_price_row_count": 0
    },
    "source_rows": {
      "error": null,
      "exists": true,
      "path": "data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/source_rows.jsonl",
      "required": false,
      "row_count": 6422,
      "status": "loaded"
    },
    "status": "ready"
  },
  "status": "point_in_time_dispersion_concentration_proxy_available"
}

Current dispersion-proxy hybrid replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.",
  "blockers": [],
  "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": null,
  "status": "dispersion_proxy_hybrid_replay_readiness_ready",
  "structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only"
}

Current preregistered PMCC diagonal playbook result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk short calls, and promotion.",
  "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "status": "preregistered_design_only",
  "structure": "defined_risk_pmcc_style_call_diagonals_only",
  "undefined_or_uncapped_short_call_risk_allowed": false
}

Current PMCC diagonal replay-readiness result, if available:
{
  "accepted_profitability": false,
  "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.",
  "blockers": [
    "missing_point_in_time_trend_or_regime_inputs",
    "missing_trusted_pmcc_diagonal_quote_surface"
  ],
  "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
  "historical_replay_performed": false,
  "lane_implementation_performed": false,
  "packet_ingestion": {
    "expected_concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
    "expected_report_id": "regular_options_pmcc_diagonal_replay_readiness",
    "expected_structure": "defined_risk_pmcc_style_call_diagonals_only",
    "generated_at_utc": "2026-06-26T04:26:13Z",
    "playbook_generated_at_utc": "2026-06-23T06:22:04Z",
    "raw_status": "blocked_pmcc_diagonal_replay_readiness",
    "reason_codes": [],
    "unsafe_flags": [],
    "validated_status": "blocked_pmcc_diagonal_replay_readiness"
  },
  "raw_status": "blocked_pmcc_diagonal_replay_readiness",
  "replay_performed": false,
  "smallest_next_blocker_clearing_slice": "missing_point_in_time_trend_or_regime_inputs",
  "status": "blocked_pmcc_diagonal_replay_readiness",
  "structure": "defined_risk_pmcc_style_call_diagonals_only",
  "undefined_or_uncapped_short_call_risk_allowed": false
}

Current approved 59-symbol ThetaData OPRA/NBBO source-repair result, if available:
{
  "accepted_profitability": false,
  "approval_token_valid": true,
  "blockers": [
    "thetaterminal_source_unavailable"
  ],
  "historical_simulated_forward_status": "blocked_historical_simulated_forward_audit",
  "import_attempted": false,
  "imported_rows": 0,
  "missing_symbol_date_count": 11565,
  "quotes_imported": false,
  "shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "status": "blocked_thetaterminal_source_unavailable",
  "theta_terminal": {
    "available": false,
    "error": "<urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>",
    "status": "unavailable",
    "url": "http://127.0.0.1:25503/v2/system/status"
  }
}

Interpretation: the original 59-symbol repair artifact is provenance. If it is still `blocked_thetaterminal_source_unavailable` but a newer resume artifact exists, prefer the newer resume artifact for current provider/source state. If the current state is provider, wrapper, or entitlement-source blocked, do not treat that as an operator-approval blocker or an earned stop; choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current tokened 59-symbol ThetaData OPRA/NBBO source-repair resume result, if available:
{
  "approval_token_valid": true,
  "blockers": [
    "bulk_import_execution_not_started_by_preflight_wrapper"
  ],
  "import_attempted": false,
  "imported_rows": 0,
  "missing_symbol_date_count": 11565,
  "outside_universe_import_rows": 0,
  "post_import_shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "protected_holdout_overlap_rows": 0,
  "provider_recheck": true,
  "quotes_imported": false,
  "resume_missing_only": true,
  "shared_trusted_imported_quote_dates": {
    "count": 260,
    "first": "2025-05-22",
    "last": "2026-06-04"
  },
  "split_audit_gate": {
    "audit_months_covered": 0,
    "cleared": false,
    "latest_audit_exact_trades": 0,
    "reason": "not_run_until_import_clears_shared_date_coverage",
    "train_months_covered": 0
  },
  "status": "blocked_59_symbol_import_repair",
  "theta_terminal": {
    "available": true,
    "body_preview": "We have upgraded to API v3. Please use API v3 instead. Update your endpoint URLs to /v3/* format. Consult API v3 documentation for more information: https://docs.thetadata.us/",
    "http_status": 410,
    "status": "available_status_endpoint_gone",
    "url": "http://127.0.0.1:25503/v2/system/status"
  }
}

Interpretation: if the tokened 59-symbol resume status is `blocked_thetaterminal_source_unavailable_retry`, do not select another 59-symbol ThetaTerminal retry until provider/source availability changes. If it is `blocked_59_symbol_import_repair` with `bulk_import_execution_not_started_by_preflight_wrapper`, the blocker is scoped import execution/wrapper state; if direct probes return entitlement errors, the blocker is entitlement-source state. In all cases, no coverage improvement or forward proof exists until a permitted import path actually writes trusted rows.

Current direct point-in-time VIX source state:
{
  "current_branch_implications": [
    {
      "branch": "macro_event_long_strangle",
      "remaining_non_vix_blockers": [
        "macro_event_calendar_source_missing"
      ],
      "source_status": "blocked_macro_event_long_strangle_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "post_event_iv_crush_iron_condor",
      "remaining_non_vix_blockers": [
        "insufficient_full_window_rows",
        "insufficient_latest_four_months",
        "insufficient_latest_four_rows",
        "insufficient_train_months",
        "iv_event_premium_proxy_missing",
        "macro_event_calendar_category_coverage_missing",
        "macro_event_calendar_source_missing",
        "missing_required_macro_event_categories"
      ],
      "source_status": "blocked_post_event_iv_crush_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "flow_extreme_ratio_backspread",
      "remaining_non_vix_blockers": [
        "missing_point_in_time_flow_extreme_input"
      ],
      "source_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "pmcc_diagonal",
      "remaining_non_vix_blockers": [
        "missing_point_in_time_trend_or_regime_inputs",
        "missing_trusted_pmcc_diagonal_quote_surface"
      ],
      "source_status": "blocked_pmcc_diagonal_replay_readiness",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "vrp_credit_spread",
      "remaining_non_vix_blockers": [
        "missing_index_credit_spread_quote_surface"
      ],
      "source_status": "blocked_vrp_credit_spread_bounded_replay_gate",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "momentum_continuation",
      "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
      "remaining_non_vix_blockers": [
        "bootstrap_pf_lower_bound_not_above_1_after_resolution",
        "duplicate_within_research_harness",
        "entry_missing_leg_quote",
        "exit_missing_leg_quote",
        "exit_value_negative",
        "exit_zero_or_nonpositive_bid_ask",
        "missing_net_usd_pnl",
        "missing_point_in_time_breadth_confirmation",
        "missing_point_in_time_qqq_momentum_confirmation",
        "missing_point_in_time_spy_momentum_confirmation",
        "net_usd_not_positive_after_resolution",
        "rejected_not_call_debit_spread",
        "rejected_outside_preregistered_universe",
        "strict_rows_below_30_after_resolution"
      ],
      "source_status": "blocked_momentum_continuation_bounded_replay",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    },
    {
      "branch": "dispersion_proxy_hybrid",
      "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
      "remaining_non_vix_blockers": [],
      "source_status": "dispersion_proxy_hybrid_replay_readiness_ready",
      "vix_status": "ready",
      "would_clear_vix_blocker_if_future_source_passes": false
    }
  ],
  "legacy_future_import_command": "npm run options:source-import:direct-vix -- --source-file data/import-staging/vix/cboe_vix_daily_history.csv --lookback-start-date 2023-05-22 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family direct_vix_daily_close --approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json",
  "legacy_future_import_manifest_template": {
    "date_window": {
      "end": "2026-06-04",
      "start": "2023-05-22"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
    "required_fields": [
      "source_date",
      "vix_open",
      "vix_high",
      "vix_low",
      "vix_close",
      "source_name",
      "source_file_hash",
      "source_row_hash",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id"
    ],
    "source_family": "direct_vix_daily_close",
    "source_file": "data/import-staging/vix/cboe_vix_daily_history.csv",
    "superseded_by_materialized_vix": true,
    "write_target": "generated point-in-time VIX source artifact only"
  },
  "legacy_source_repair_packet_status": "direct_vix_source_repair_packet_superseded_by_materialized_vix",
  "source_import": {
    "accepted_profitability": false,
    "downstream_vix_bucket_status": "point_in_time_vix_bucket_ready",
    "downstream_vix_coverage_pct": 100.0,
    "evidence_stores_mutated": false,
    "protected_holdout_consumed": false,
    "quotes_imported": false,
    "source_family": "direct_vix_daily_close",
    "source_row_count": 505,
    "source_rows_path": "data/profitability-lab/regular-options-point-in-time-vix-bucket/source_rows.jsonl",
    "source_rows_written": true,
    "status": "direct_vix_source_import_materialized",
    "threshold_policy_path": "data/contracts/regular-options-vix-bucket-policy.json"
  },
  "vix_bucket": {
    "blockers": [],
    "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
    "coverage_pct": 100.0,
    "covered_date_count": 505,
    "late_known_at_count": 0,
    "leakage_reject_count": 0,
    "requested_date_count": 505,
    "source_rows_count": 505,
    "status": "point_in_time_vix_bucket_ready",
    "threshold_policy": {
      "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
      "frozen_at_utc": "2026-06-04T00:00:00Z",
      "low_max": 15.0,
      "mid_max": 25.0,
      "policy_id": "vix_prior_close_fixed_buckets_v1"
    }
  }
}

Interpretation: when the current VIX state shows `direct_vix_source_import_materialized` and `point_in_time_vix_bucket_ready`, the prior operator-supplied official daily VIX CSV has already been materialized; do not select the direct VIX source plan or VIX source import again; do not rerun the same VIX packet. Branches that still name VIX as a blocker must be refreshed or treated as stale with respect to VIX; rank their remaining non-VIX blockers instead.

Current macro-event calendar source repair packet result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "branch_implications": [
    {
      "branch": "macro_event_long_strangle",
      "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
      "event_calendar_blockers": [
        "macro_event_calendar_source_missing"
      ],
      "remaining_non_event_blockers": [],
      "status": "blocked_macro_event_long_strangle_replay_readiness",
      "would_clear_event_calendar_blocker_if_future_source_passes": true
    },
    {
      "branch": "post_event_iv_crush_iron_condor",
      "concept_id": "post_event_iv_crush_index_iron_condor_v1",
      "event_calendar_blockers": [
        "future_replay_requires_point_in_time_macro_event_calendar"
      ],
      "remaining_non_event_blockers": [
        "iv_event_premium_proxy_missing"
      ],
      "status": "preregistered_design_only",
      "would_clear_event_calendar_blocker_if_future_source_passes": true
    },
    {
      "branch": "direct_vix_source_repair",
      "concept_id": "direct_vix_daily_close",
      "event_calendar_blockers": [],
      "remaining_non_event_blockers": [],
      "status": "direct_vix_source_repair_packet_superseded_by_materialized_vix",
      "would_clear_event_calendar_blocker_if_future_source_passes": false
    }
  ],
  "current_macro_event_source_baseline": {
    "covered_categories": [],
    "current_forward_rows": 0,
    "event_count": 0,
    "macro_event_calendar_status": "blocked_macro_event_calendar_source_missing",
    "missing_required_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "target_forward_rows": 30
  },
  "downstream_readiness_commands": {
    "macro_event_long_strangle": "npm run options:research:macro-event-long-strangle-replay-readiness -- --json",
    "post_event_iv_crush_iron_condor": "npm run options:research:post-event-iv-crush-replay-readiness -- --json"
  },
  "evidence_stores_mutated": false,
  "fixture_validation": {
    "after_market_case_present": true,
    "all_required_categories_present": true,
    "before_market_case_present": true,
    "category_counts": {
      "cpi": 1,
      "fomc_minutes": 1,
      "fomc_rate_decision": 1,
      "nonfarm_payrolls": 1,
      "pce": 1,
      "scheduled_fed_chair_testimony": 1
    },
    "covered_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "duplicate_event_id_reject_count": 0,
    "during_market_case_present": true,
    "errors": [],
    "fixture_path": "tests/fixtures/macro_events/macro_event_calendar_sample.csv",
    "holiday_weekend_adjacent_case_present": true,
    "known_at_reject_count": 0,
    "known_at_safe": true,
    "leakage_reject_count": 0,
    "missing_required_categories": [],
    "protected_holdout_overlap_rows": 0,
    "required_fields_present": true,
    "row_count": 6,
    "sample_rows": [
      {
        "event_category": "cpi",
        "event_id": "cpi-2026-02",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-02-12T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-02-12T13:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "52849c991555cdb6e9b2395c3fe8e891e65126c469ab5a61ceebff49b2fd7e5b",
        "source_url_or_file_name": "fixture://macro-events/cpi",
        "tradable_after_et": "2026-02-12T09:30 America/New_York"
      },
      {
        "event_category": "fomc_minutes",
        "event_id": "fomc-minutes-2026-02",
        "event_window_type": "during_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-02-18T14:00 America/New_York",
        "scheduled_event_datetime_utc": "2026-02-18T19:00Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "a5403f4d2fb10e504cb793aba1b09182134543703ca4b1d8deb654b346d1e000",
        "source_url_or_file_name": "fixture://macro-events/fomc-minutes",
        "tradable_after_et": "2026-02-18T14:00 America/New_York"
      },
      {
        "event_category": "fomc_rate_decision",
        "event_id": "fomc-rate-2026-03",
        "event_window_type": "during_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-03-18T14:00 America/New_York",
        "scheduled_event_datetime_utc": "2026-03-18T18:00Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "7c722f1dab5013c3aee98b8843afcaeb35559156b09a651317f5092a7e77a35e",
        "source_url_or_file_name": "fixture://macro-events/fomc-rate",
        "tradable_after_et": "2026-03-18T14:00 America/New_York"
      },
      {
        "event_category": "nonfarm_payrolls",
        "event_id": "nfp-2026-04",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-04-03T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-04-03T12:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "58a333e847821302ccfd01a3518294ce35749dc881101825d5908ba49b3df4eb",
        "source_url_or_file_name": "fixture://macro-events/nfp",
        "tradable_after_et": "2026-04-03T09:30 America/New_York"
      },
      {
        "event_category": "pce",
        "event_id": "pce-2026-05",
        "event_window_type": "before_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-05-29T08:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-05-29T12:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "df980a9d7cfda234b8906a24dfa99bb7b153c69d6b0772797b69ae960e95da9e",
        "source_url_or_file_name": "fixture://macro-events/pce",
        "tradable_after_et": "2026-05-29T09:30 America/New_York"
      },
      {
        "event_category": "scheduled_fed_chair_testimony",
        "event_id": "fed-chair-2026-05",
        "event_window_type": "after_market",
        "known_at_utc": "2026-01-02T15:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "revision_status": "scheduled",
        "scheduled_event_datetime_et": "2026-05-22T16:30 America/New_York",
        "scheduled_event_datetime_utc": "2026-05-22T20:30Z",
        "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
        "source_file_hash": "1984812eca4e7a22c0e01c442b77bd59fc3c944ed63ce2fb94bd898bb0628e82",
        "source_name": "operator_approved_macro_calendar",
        "source_published_at_utc": "2026-01-02T15:00Z",
        "source_row_hash": "631e32d316bf45b7cc0cce6c06caaf2eec273a74dbe287f5ba6b02f20bcc9b56",
        "source_url_or_file_name": "fixture://macro-events/fed-chair",
        "tradable_after_et": "2026-05-26T09:30 America/New_York"
      }
    ]
  },
  "future_import_command": "npm run options:source-import:macro-event-calendar -- --source-file data/import-staging/macro_events/macro_event_calendar.csv --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --source-family scheduled_macro_event_calendar_v1 --required-categories cpi,fomc_minutes,fomc_rate_decision,nonfarm_payrolls,pce,scheduled_fed_chair_testimony --approval-token APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT --no-replay --json",
  "future_import_command_executed": false,
  "future_import_manifest_template": {
    "date_window": {
      "as_of": "2026-06-04",
      "end": "2026-05-31",
      "start": "2024-06-01"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT",
    "required_categories": [
      "cpi",
      "fomc_minutes",
      "fomc_rate_decision",
      "nonfarm_payrolls",
      "pce",
      "scheduled_fed_chair_testimony"
    ],
    "required_fields": [
      "event_id",
      "event_category",
      "scheduled_event_datetime_et",
      "event_window_type",
      "source_name",
      "source_url_or_file_name",
      "source_file_hash",
      "source_row_hash",
      "source_published_at_utc",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id",
      "revision_status",
      "proof_exclusion_reason"
    ],
    "source_family": "scheduled_macro_event_calendar_v1",
    "source_file": "data/import-staging/macro_events/macro_event_calendar.csv",
    "write_target": "generated point-in-time macro-event calendar source artifact only"
  },
  "historical_rows_are_forward_proof": false,
  "known_at_policy": {
    "forbidden_candidate_inputs": [
      "actual",
      "actual_value",
      "beat_miss",
      "consensus",
      "forecast",
      "iv_crush",
      "market_reaction",
      "net_pnl",
      "net_pnl_usd",
      "pnl",
      "post_event_drift",
      "post_event_iv",
      "realized_move",
      "realized_vol",
      "revised_value",
      "revision_value",
      "surprise"
    ],
    "policy_id": "scheduled_macro_event_known_before_candidate_decision_v1",
    "rule": "Rows are usable only when source_published_at_utc and known_at_utc are no later than the candidate decision timestamp."
  },
  "protected_holdout_consumed": false,
  "quotes_imported": false,
  "source_family": "scheduled_macro_event_calendar_v1",
  "status": "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision",
  "tradable_after_policy": {
    "after_market": "next regular session no earlier than 09:30 America/New_York",
    "before_market": "same regular session post-open only if schedule was known before entry",
    "during_market": "decisions after the scheduled release timestamp only",
    "policy_id": "scheduled_macro_event_tradable_after_release_window_v1"
  }
}

Interpretation: if the macro-event calendar source repair packet status is macro_event_calendar_source_repair_packet_ready_for_operator_import_decision, do not rerun the same macro-event source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real macro-event source import/materialization still needs the exact tokened source-import slice and an operator-supplied official macro-event calendar CSV. Do not run macro-event or post-event replay until a real point-in-time macro-event source artifact exists. VIX is already materialized and must not be selected as the next slice. Decide whether the next meaningful slice is that tokened non-live source materialization path, a readiness audit for post-event IV-crush, or another safe fallback.

Current flow-extreme volume/open-interest source repair packet result, if available:
{
  "accepted_profitability": false,
  "blockers": [],
  "branch_implications": [
    {
      "branch": "flow_extreme_ratio_backspread",
      "flow_blockers": [
        "missing_point_in_time_flow_extreme_input"
      ],
      "remaining_non_flow_blockers": [],
      "status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
      "would_clear_flow_blocker_if_future_source_passes": true
    },
    {
      "branch": "direct_vix_source_repair",
      "flow_blockers": [],
      "remaining_non_flow_blockers": [],
      "status": "direct_vix_source_repair_packet_superseded_by_materialized_vix",
      "would_clear_flow_blocker_if_future_source_passes": false
    }
  ],
  "current_flow_source_baseline": {
    "covered_month_count": 0,
    "current_forward_rows": 0,
    "date_coverage_pct": 0.0,
    "flow_extreme_ratio_backspread_replay_readiness_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
    "flow_extreme_volume_oi_source_rows_status": "blocked_flow_extreme_volume_oi_source_rows",
    "point_in_time_flow_extreme_input_status": "blocked_point_in_time_flow_extreme_input",
    "target_forward_rows": 30
  },
  "downstream_readiness_commands": {
    "flow_extreme_ratio_backspread_replay_readiness": "npm run options:research:flow-extreme-ratio-backspread-replay-readiness -- --json",
    "point_in_time_flow_extreme_input": "npm run options:research:point-in-time-flow-extreme-input -- --no-write --json"
  },
  "evidence_stores_mutated": false,
  "fixture_validation": {
    "duplicate_source_row_hash_reject_count": 0,
    "errors": [],
    "fixture_path": "tests/fixtures/flow/spy_qqq_option_volume_oi_daily_sample.csv",
    "holiday_gap_case_present": true,
    "known_at_safe": true,
    "late_known_at_reject_count": 1,
    "leakage_reject_count": 0,
    "missing_value_reject_count": 1,
    "prior_day_aggregate_safe_for_next_session_entry": true,
    "protected_holdout_overlap_rows": 0,
    "reject_count": 2,
    "rejected_rows": [
      {
        "index": 5,
        "reasons": [
          "missing_or_invalid_total_option_volume"
        ],
        "source_date": "2024-07-05",
        "underlying": "SPY"
      },
      {
        "index": 6,
        "reasons": [
          "known_at_after_tradable_after"
        ],
        "source_date": "2024-07-05",
        "underlying": "QQQ"
      }
    ],
    "required_fields_present": true,
    "row_count": 4,
    "same_day_aggregate_safe_for_same_day_entry": false,
    "sample_rows": [
      {
        "call_open_interest": 4100000.0,
        "call_put_volume_ratio": 1.083333,
        "call_volume": 520000.0,
        "data_trust": "trusted",
        "flow_extreme": false,
        "known_at_utc": "2024-06-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 3900000.0,
        "put_volume": 480000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "e3f724fb5aa7d94168aa03db771b24b87e49e322fffa96a5248c9a0b2b37ca44",
        "source_url_or_file_name": "fixture://flow/spy",
        "strictly_prior_rows_used": 0,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 8000000.0,
        "total_option_volume": 1000000.0,
        "total_option_volume_prior_percentile": null,
        "tradable_after_et": "2024-06-04T09:30 America/New_York",
        "underlying": "SPY",
        "volume_open_interest_ratio": 0.125
      },
      {
        "call_open_interest": 3300000.0,
        "call_put_volume_ratio": 1.162162,
        "call_volume": 430000.0,
        "data_trust": "trusted",
        "flow_extreme": false,
        "known_at_utc": "2024-06-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 2900000.0,
        "put_volume": 370000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "103ba37b0742d11e2fbf8fd1bc4d6fc6e38e65a04c3c622154a412c82e644021",
        "source_url_or_file_name": "fixture://flow/qqq",
        "strictly_prior_rows_used": 0,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 6200000.0,
        "total_option_volume": 800000.0,
        "total_option_volume_prior_percentile": null,
        "tradable_after_et": "2024-06-04T09:30 America/New_York",
        "underlying": "QQQ",
        "volume_open_interest_ratio": 0.129032
      },
      {
        "call_open_interest": 4800000.0,
        "call_put_volume_ratio": 0.5625,
        "call_volume": 900000.0,
        "data_trust": "trusted",
        "flow_extreme": true,
        "known_at_utc": "2024-06-04T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 7200000.0,
        "put_volume": 1600000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-06-04",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "eca5ed34a5f0cc49e6db608078c808bfa9ae00905b739bbf3047163c1861d298",
        "source_url_or_file_name": "fixture://flow/spy-extreme",
        "strictly_prior_rows_used": 1,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 12000000.0,
        "total_option_volume": 2500000.0,
        "total_option_volume_prior_percentile": 100.0,
        "tradable_after_et": "2024-06-05T09:30 America/New_York",
        "underlying": "SPY",
        "volume_open_interest_ratio": 0.208333
      },
      {
        "call_open_interest": 3400000.0,
        "call_put_volume_ratio": 1.093023,
        "call_volume": 470000.0,
        "data_trust": "trusted",
        "flow_extreme": true,
        "known_at_utc": "2024-07-03T22:00Z",
        "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
        "put_open_interest": 3000000.0,
        "put_volume": 430000.0,
        "revision_status": "final",
        "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
        "source_date": "2024-07-03",
        "source_file_hash": "b68f69bffa0faccbd2322fd67a95f3619a600723c129373ef982033ef0775bc5",
        "source_name": "operator_approved_flow_calendar",
        "source_row_hash": "51bc2acdaace30a1a140a9146414a3fbaf330edd0e64ff221fc793fca8a6f5d7",
        "source_url_or_file_name": "fixture://flow/qqq-gap",
        "strictly_prior_rows_used": 1,
        "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
        "total_open_interest": 6400000.0,
        "total_option_volume": 900000.0,
        "total_option_volume_prior_percentile": 100.0,
        "tradable_after_et": "2024-07-05T09:30 America/New_York",
        "underlying": "QQQ",
        "volume_open_interest_ratio": 0.140625
      }
    ],
    "underlyings_covered": [
      "SPY",
      "QQQ"
    ]
  },
  "future_import_command": "npm run options:source-import:flow-extreme-volume-oi -- --source-file data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv --lookback-start-date 2023-06-01 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --underlyings SPY,QQQ --source-family trusted_option_volume_open_interest_daily_v1 --approval-token APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT --no-replay --json",
  "future_import_command_executed": false,
  "future_import_manifest_template": {
    "date_window": {
      "as_of": "2026-06-04",
      "lookback_start": "2023-06-01",
      "target_end": "2026-05-31",
      "target_start": "2024-06-01"
    },
    "protected_holdout_consumption_allowed": false,
    "required_approval_token": "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT",
    "required_fields": [
      "source_date",
      "underlying",
      "total_option_volume",
      "call_volume",
      "put_volume",
      "total_open_interest",
      "call_open_interest",
      "put_open_interest",
      "source_name",
      "source_url_or_file_name",
      "source_file_hash",
      "source_row_hash",
      "known_at_utc",
      "tradable_after_et",
      "source_batch_id",
      "data_trust",
      "revision_status",
      "proof_exclusion_reason"
    ],
    "source_family": "trusted_option_volume_open_interest_daily_v1",
    "source_file": "data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv",
    "underlyings": [
      "SPY",
      "QQQ"
    ],
    "write_target": "generated point-in-time flow-extreme source artifact only"
  },
  "historical_rows_are_forward_proof": false,
  "known_at_policy": {
    "policy_id": "trusted_flow_prior_source_date_known_before_candidate_v1",
    "rule": "source_date D aggregate volume/OI is usable only when known_at_utc is no later than candidate decision time and source_date is strictly before input_date_et",
    "same_day_aggregate_volume_oi_allowed_for_same_day_entry": false
  },
  "protected_holdout_consumed": false,
  "quotes_imported": false,
  "source_family": "trusted_option_volume_open_interest_daily_v1",
  "status": "flow_extreme_source_repair_packet_ready_for_operator_import_decision",
  "threshold_policy": {
    "call_put_volume_ratio": "diagnostic_only_unless_separately_preregistered",
    "flow_extreme_rule": "flow_extreme=true only when prior-day flow percentile >= 95.0 using strictly prior source rows only",
    "outcome_tuned": false,
    "plain_bid_ask_used_as_flow": false,
    "policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
    "realized_pnl_used": false,
    "selected_winners_used": false,
    "volume_open_interest_ratio": "diagnostic_only_unless_separately_preregistered"
  }
}

Interpretation: if the flow-extreme source repair packet status is flow_extreme_source_repair_packet_ready_for_operator_import_decision, do not rerun the same flow-source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real SPY/QQQ option volume/open-interest source import/materialization still needs the exact tokened source-import slice and an operator-supplied trusted daily volume/OI CSV. Do not run flow-extreme replay until real point-in-time flow source rows exist. VIX is no longer the flow blocker. Decide whether the next meaningful slice is that tokened non-live flow-source materialization path or another safe fallback.

Current underlying daily OHLCV source acquisition/import state:
{
  "acquisition": {
    "blockers": [],
    "candidate_blocker_counts": {},
    "candidate_file_count": 1,
    "future_import_command": "npm run options:source-import:underlying-daily-history -- --source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv --approval-token APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT --no-replay --json",
    "ready_candidate_count": 1,
    "selected_ready_source_file": "data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv",
    "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
    "source_import_command_executed": false,
    "source_rows_written": false,
    "status": "ready_for_underlying_daily_source_import_approval"
  },
  "source_import": {
    "accepted_profitability": false,
    "blockers": [],
    "historical_rows_are_forward_proof": false,
    "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
    "source_row_count": 6422,
    "source_rows_path": "data/profitability-lab/regular-options-point-in-time-underlying-daily-history/source_rows.jsonl",
    "source_rows_written": true,
    "status": "underlying_daily_history_source_import_materialized"
  }
}

Interpretation: if underlying daily source import is `underlying_daily_history_source_import_materialized` with source rows written, daily OHLCV is no longer the 13-symbol historical scanner blocker; rank the remaining opening/intraday underlying, option-chain selection, scanner point-in-time, lane-specific input, earnings/calendar, candidate-generation coverage, and quote-surface blockers. If acquisition is `blocked_underlying_daily_source_acquisition_missing`, the blocker is an absent trusted full-window source CSV. If acquisition is `blocked_underlying_daily_source_acquisition_invalid`, name the exact parser/coverage/local-provenance blocker. If acquisition is `ready_for_underlying_daily_source_import_approval` and import is not materialized, the next material step requires the exact tokened source import command and source materialization approval. Do not treat `market_data.db:daily_history`, local historical reconstruction, inferred known-at rows, or fixture rows as point-in-time proof.

Current goal-loop state:
{
  "forward_evidence_accounting": {
    "auto_track_allowed": false,
    "broker_order_allowed": false,
    "cohort_append_performed": false,
    "cohort_log_exists": false,
    "cohort_log_malformed_row_count": 0,
    "cohort_log_path": "data/forward-tracking/phase2_regular_options_forward_paper_shadow_cohort.jsonl",
    "cohort_log_row_count": 0,
    "cohort_log_status": "missing",
    "excluded_or_rejected_row_flags": 0,
    "live_entry_allowed": false,
    "minimum_required": 30,
    "post_freeze_strict_exact_completed_rows": 0,
    "promotion_ready": false,
    "state": "log_missing_blocker",
    "strict_reject_counts": {
      "blocked_by_required_contracts": 0,
      "duplicate_completed_selection_id": 0,
      "duplicate_row_id": 0,
      "exact_completed_missing_entry_quote_provenance": 0,
      "exact_completed_missing_exit_quote_provenance": 0,
      "exact_completed_missing_policy_exit_condition": 0,
      "fixture_source_not_proof_eligible": 0,
      "lookahead_claimed_as_exact": 0,
      "market_window_not_open": 0,
      "missing_net_pnl_usd": 0,
      "missing_real_source_provenance": 0,
      "missing_required_schema_fields": 0,
      "missing_source_provenance_fields": 0,
      "non_executable_mark_claimed_as_exact": 0,
      "non_frozen_lane": 0,
      "non_preregistered_symbol": 0,
      "pre_freeze_not_acceptance_eligible": 0,
      "scanner_hash_drift": 0,
      "unknown_denominator_status": 0
    },
    "strict_rows_remaining_to_minimum": 30,
    "strict_usd_pf_lower_bound_5pct": null,
    "total_natural_selections": 0
  },
  "next_safe_action": "continue_paper_shadow_only",
  "state": "underpowered_forward_evidence"
}

Important instruction:
You are not being asked for generic strategy advice or a casual continue/stop vote. Treat stopping as an exceptional claim. Because strict post-freeze forward proof is currently 0/30, you may recommend stopping only if you can prove that no significant upgrade remains after explicitly considering new lanes, new option structures, historical data-depth repair, and forward collection. Ask up to five operator questions that would materially affect the decision, but do not block on read-only/research-only work; the user has already approved that category. For any live/broker/import/mutation/promotion/proof-bar/holdout action, name the needed approval and select a safe read-only fallback unless no such fallback exists.

Return a concrete loop decision. If a significant upgrade remains, return verdict=continue, continue_loop=true, and exactly one next Codex task with files/artifacts/commands/tests/acceptance criteria. If a branch needs operator approval, ask the exact operator question and explain why it is required. If no significant upgrade remains under current approvals, return verdict=stop_exception, continue_loop=false, and provide the burden-of-proof check that earned that stop.

Do not say "collect more data", "try more strategies", "optimize parameters", or "run more backtests" unless you specify the exact data, lane, option structure, date window, command, and pass/fail threshold.

Before any stop_exception, explicitly evaluate whether there is a falsifiable path through:
1. fresh forward paper-shadow collection,
2. scoped source repair or replay,
3. a new historical data surface or longer-lookback audit,
4. a new causal playbook,
5. new option structures beyond the current directional-spread surface.

New option edge families to consider before stopping:
- volatility risk premium,
- skew mispricing,
- term-structure dislocation,
- earnings or macro event volatility,
- post-event IV crush,
- post-event drift,
- trend or momentum continuation,
- mean reversion,
- dispersion-like proxy behavior,
- liquidity or flow effects.

Option structures to consider before stopping:
- vertical spreads,
- calendars,
- diagonals,
- broken-wing butterflies,
- ratio spreads,
- backspreads,
- straddles,
- strangles,
- iron condors,
- iron butterflies,
- synthetic covered calls or PMCC-style diagonals,
- debit/credit hybrids.

For every proposed lane, provide the frozen rule, eligible universe, inclusion/exclusion rules, leakage controls, required data repairs, minimum sample size, profitability thresholds, and the exact result that would falsify it. A lane should not pass because it has an attractive point backtest; it needs an economic mechanism and a falsifiable audit plan.

Allowed branch families:
1. fresh_forward_paper_shadow_collection - requires operator approval and a valid market-data window if rows will be appended.
2. scoped_source_repair_or_replay - requires operator approval before quote import, evidence mutation, or source repair.
3. new_causal_playbook_generation - read-only preregistration/falsification can continue without live/broker/evidence mutation.
4. new_historical_data_surface_or_longer_lookback - requires operator approval if it changes the data surface.
5. dashboard_or_operator_visibility - only significant if tied to a proof blocker or execution decision.

Forbidden unless explicitly approved later:
- broker orders, live validation, auto-track, scanner release, stop/sizing changes, proof-bar relaxation, quote import, evidence DB mutation, protected holdout consumption, promotion.

Required JSON-like output shape:
{
  "anti_handwave_audit": {
    "exact_next_action_present": "boolean",
    "generic_advice_removed": "boolean",
    "measurable_threshold_present": "boolean",
    "packet_only_justified_or_rejected": "boolean",
    "ranked_existing_forward_capture_paths": "boolean",
    "stale_artifacts_overridden_by_current_fact_table": "boolean"
  },
  "assumption_challenges": [
    {
      "assumption": "string",
      "risk": "string",
      "verification": "string"
    }
  ],
  "blocker_map": {
    "candidate_generation": [],
    "dashboard_operator": [],
    "data_sources": [],
    "forward_proof": [],
    "historical_audit": [],
    "replay_engine": [],
    "strategy_edges": []
  },
  "branches_to_stop": [
    "branch ids or candidate ids to avoid repeating"
  ],
  "burden_of_proof_check": {
    "current_forward_rows": "number",
    "reason": "string",
    "stop_allowed": "boolean",
    "target_profitable_strict_completed_rows": "number"
  },
  "candidate_branches": [
    {
      "branch": "string",
      "expected_value": "string",
      "main_uncertainty": "string",
      "why_not_selected": "string|null"
    }
  ],
  "continue_loop": "boolean",
  "current_profitability_state": {
    "accepted_profitability": "boolean",
    "forward_strict_completed_rows": "number",
    "main_reason_not_profitable": "string",
    "target_rows": 30
  },
  "loop_control_fallback": {
    "needed_if_selected_branch_blocked_by_approval_or_missing_source": "string",
    "safe_fallback_task": "string|null"
  },
  "next_codex_task": {
    "acceptance_criteria": [
      "measurable pass/fail criteria"
    ],
    "allowed_files_or_artifacts": [
      "paths or artifact families"
    ],
    "approval_required_before_followup": [],
    "approval_required_for_selected_task": "boolean",
    "branch_status": "continue_now",
    "commands_to_run": [
      "exact commands"
    ],
    "exact_scope": "files/modules/artifacts included and excluded",
    "executable_under_current_approval": "boolean",
    "expected_artifacts": [
      "files or readbacks expected after Codex runs"
    ],
    "failure_criteria": [
      "what result rejects or parks this branch"
    ],
    "fallback_reason_if_top_rank_blocked": "string|null",
    "forbidden_actions": [
      "actions that remain forbidden"
    ],
    "implementation_steps": [
      "ordered steps"
    ],
    "must_not_count_as_forward_profitability": true,
    "objective": "one concrete implementation or verification task",
    "proof_boundary_statement": "This task cannot produce accepted profitability or promotion unless strict forward-audit evidence is later collected through the approved forward cohort path.",
    "safe_read_only_fallback_if_approval_missing": "string|null",
    "stop_condition_after_task": "what would make this branch exhausted"
  },
  "operator_questions": [
    {
      "default_if_unanswered": "string",
      "question": "string",
      "why_it_matters": "string"
    }
  ],
  "ranked_next_tasks": [
    {
      "approval_required": "none|string",
      "branch_status": "continue_now|approval_blocked|source_blocked|market_window_blocked|parked_until_state_change|falsified_under_current_data|exhausted_under_current_data",
      "downstream_unlocks": [],
      "expected_profitability_impact": "string",
      "rank": "number",
      "task_id": "string",
      "time_to_test": "string",
      "why_not_selected_if_applicable": "string|null"
    }
  ],
  "selected_branch_id": "string|null",
  "significant_upgrade_available": "boolean",
  "stale_blockers_ignored": [
    {
      "blocker": "string",
      "current_replacing_fact": "string",
      "why_stale": "string"
    }
  ],
  "verdict": "continue|stop_exception",
  "why_this_is_significant": "short explanation tied to profitability proof"
}

Relevant NEXT_STEPS excerpt:
# Next Steps

Last updated: 2026-06-27

## Active Historical Robust-Search Track

Current read:
- Latest blocker-surface refresh after the paid-provider source pass is `2026-06-27T18:36:10Z`. Alpaca SIP underlying daily history, Alpaca SIP underlying minute source rows, base market-regime inputs, direct VIX, and Alpaca-backed dispersion/concentration proxy inputs are cleared. The latest dispersion artifacts report `point_in_time_dispersion_concentration_proxy_available`, `dispersion_proxy_hybrid_replay_readiness_ready`, and selector status `candidate_selected_for_research_only_implementation_approval` with `recommended_operator_approval_question=null` and a bounded research-only task boundary. The Oracle packet is `ready_for_same_session_gpt55_guidance`; the strict-forward operator queue is still `strict_forward_queue_ready_approval_and_market_window_blocked`, `profitability_readiness=false`, and strict completed rows remain `0/30`. Do not start the 30-trade profitability collection loop until a valid market-window run produces real same-day Phase 2 scanner candidates, candidate review clears, and strict-forward completion rows are actually appended and completed under the guarded proof rules.
- Earlier strict-forward stale-state cleanup remains valid. The dedicated `\OptionsStrictForward30Collector` Windows runtime blocker is cleared: scheduler health is `scheduler_ready_for_next_market_window`, runtime telemetry is `scheduler_runtime_observed_ok`, `Last Run Time=6/27/2026 11:09:20 AM`, `Last Result=0`, and `Next Run Time=6/29/2026 7:35:00 AM`. The stale temp candidate-stager artifact is also cleared: `docs/regular-options-phase2-forward-paper-shadow-candidate-row-stager.md` now reports `blocked_market_window_not_confirmed`, `0` staged rows, and `candidate_jsonl_written=false`. The active `30`-trade strict-forward audit is still not ready for the profitability loop: strict completed rows remain `0/30`, scan tasks are `scan_tasks_ready_for_next_market_window`, throughput is `blocked_no_same_day_phase2_natural_selections` for `target_selection_date=2026-06-26` with `zero_candidate_diagnostics.status=opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons`, candidate review is `candidate_review_blocked_no_scanner_candidates_for_target_date`, and completion monitor is `completion_monitor_waiting_for_first_cohort_row`.
- Treat the cleared scheduler/stager items as local stale-state cleanup only, not profitability readiness. Remaining active blockers still include valid-market-window and real-candidate requirements, explicit operator approval before any guarded append, missing Phase 2 cohort/open rows/exits, and the broader source/input/quote-surface/provider blockers tracked in the blocker inventory and operator queue. These are not safe to clear by rewriting readbacks or lowering gates.
- `docs/regular-options-profitability-blocker-inventory.md` is the current whole-surface blocker inventory. It records direct VIX, Alpaca SIP underlying daily history, Alpaca SIP underlying minute price surface for opening-range replay, base point-in-time market-regime inputs, and Alpaca-backed dispersion/concentration proxy inputs as cleared, and keeps the profitability goal open on remaining forward, candidate-generation, macro/earnings, flow, branch-specific input, quote-surface, engine, provider/entitlement, approval, and market-window blockers.
- `docs/regular-options-strict-forward-operator-queue.md` is the current strict-forward profitability-loop queue, exposed as `npm run options:plan:strict-forward-operator-queue`. Current status is `strict_forward_queue_ready_approval_and_market_window_blocked`: strict forward rows are `0/30`, profitability readiness is `false`, fresh forward capture is blocked by operator approval plus a valid market window, and the selected path is bullish-pullback `layer_4_clean_exact`. The queue is read-only and explicitly forbids live release, broker orders, auto-track, quote import, evidence-store mutation, cohort append, holdout consumption, proof-bar changes, scanner/strategy/stop/sizing changes, promotion, and treating historical rows as forward proof.
- `docs/regular-options-strict-forward-market-window-readiness-refresh.md` is the latest no-write loop refresh selected by GPT-5.5 Pro after the queue. Current status is `market_window_blocked_no_candidate_jsonl`: `0/30` strict forward rows, `accepted_profitability=false`, `profitability_readiness=false`, `historical_rows_are_forward_proof=false`, `market_window_status=market_closed`, `candidate_jsonl_exists=false`, `candidate_rows=0`, `append_allowed=false`, `operator_approval_required=true`, and `scan_task_health_status=scan_tasks_ready_for_next_market_window` with no scan-task blockers. Source readbacks are current after the 2026-06-27 refresh chain, with `paper_shadow_evidence_plan=paper_shadow_evidence_collecting`, market preflight `blocked_market_closed`, and robust-edge discovery `paper_shadow_only`.
- `docs/regular-options-forward-candidate-throughput-audit.md` is the current scan-pick throughput readback, exposed as `npm run options:audit:forward-candidate-throughput`. Current status is `blocked_no_same_day_phase2_natural_selections`: `550` scan-pick rows, `1` post-freeze Phase 2 row, `0` target-date Phase 2 rows for `2026-06-26`, both frozen-lane scheduled sessions present, `0` staged candidates, and stager rejects dominated by non-Phase-2/pre-freeze/non-preregistered rows. Standalone weekend/pre-open refreshes now target the latest completed market day, so this is true candidate starvation rather than a false Saturday missing-session blocker. The scheduled drop-stage summary reports `candidate_starvation_from_scan_filters` with total drop count `63`; scan-funnel drops were led by `momentum=50`, `history_or_liquidity=8`, `tech_score=2`, `direction_score=1`, `ev_floor=1`, and `option_liquidity=1`. Treat scheduled-session labels such as `policy_not_applied` as secondary when there are `0` scan picks; the actionable blocker is candidate starvation under current filters. Future scheduled sessions now persist symbol-level scan-drop reasons into the forward ledger for this audit; the existing June 26 sessions predate that persistence and therefore show `0` symbol drop reasons with `candidate_starvation_evidence_status=stage_counts_only_waiting_for_symbol_drop_reasons`.
- `npm run options:scan:forward-cohort-sweep` is the passive market-window scanner wrapper for the frozen Phase 2 cohort. It runs/checks `volatility_expansion_observation` and `bullish_pullback_observation` individually, keeps portfolio/profitability gates on, and forces `OPTIONS_SCAN_AUTO_TRACK=0`. The June 26 ledger has both frozen-lane scheduled sessions (`8293` bullish pullback, `8294` volatility expansion), both with `0` picks, so the current blocker is true candidate starvation under current gates rather than a skipped volatility scan.
- `npm run options:goal-loop:strict-forward-30` is the active strict-forward coordinator. Current use is read-only/closed-window unless a valid market window is explicitly confirmed. Its latest generated next-window command is `npm run options:goal-loop:strict-forward-30 -- --selection-date 2026-06-29 --market-window-confirmed --market-window-status open --run-scan-sweep --json`; it still defaults to no append and no live/broker/auto-track. The top-level report now carries `scan_task_health_status=scan_tasks_ready_for_next_market_window` plus scan-task blockers, so broken 11:00/11:30 scan feeders are visible without opening downstream review artifacts. Only after real candidate rows are staged and independently reviewed should any guarded append be considered through the existing tokened append path.
- `npm run options:goal-loop:strict-forward-30-collector` is the bounded market-window collector for the active `30`-row forward-audit goal. Latest status is `waiting_for_valid_market_window`: strict forward rows are still `0/30`, candidate rows are `0`, no candidate JSONL exist

Relevant DECISIONS excerpt:
# Decisions

## 2026-06-27: Paid Provider Source Priority And Underlying Source Materialization

Regular-options profitability blocker repair should prefer paid provider data already available to the operator before falling back to public web sources. Alpaca and ThetaData are first-choice import/probe sources for market data blockers; web sources are acceptable only when those providers do not cover the required field family or current provider state blocks the exact source.

Durable decision: Alpaca SIP adjusted daily bars were staged as `point_in_time_underlying_daily_ohlcv_adjusted_v1` and tokened-imported through `npm run options:source-import:underlying-daily-history`, writing `6,422` generated source rows without replay, quote import, evidence-store mutation, live validation, broker action, auto-track, holdout consumption, proof-bar change, or promotion. `npm run options:research:point-in-time-market-regime-inputs` now reports `point_in_time_market_regime_inputs_ready` with `494` / `494` requested dates and `24` / `24` months covered. `npm run options:source-import:dispersion-concentration-proxy -- --approval-token APPROVE_DISPERSION_CONCENTRATION_PROXY_SOURCE_IMPORT --no-replay --json` now derives `6,422` Alpaca-backed dispersion/concentration proxy source rows from those daily rows, and `npm run options:research:dispersion-proxy-hybrid-replay-readiness -- --json` reports `dispersion_proxy_hybrid_replay_readiness_ready` with `blockers=[]`. The daily OHLCV, base market-regime, opening-range underlying-minute source, and dispersion/concentration source/input readiness blockers are cleared, while candidate-generation diagnostics, macro/earnings, flow, branch-specific inputs, quote surfaces, real forward rows, approvals, and market-window blockers remain.

ThetaTerminal source state also changed. The local v3 terminal is reachable and the scoped 59-symbol resume dry-run preflight is ready, but the non-dry wrapper still reports `blocked_59_symbol_import_repair` / `bulk_import_execution_not_started_by_preflight_wrapper`, and a direct OPRA quote dry-run returned `403 Forbidden` while the loaded terminal banner showed `Options: FREE`. Do not repeat stale connection-refused conclusions; treat this as scoped import execution/entitlement-source state until the configured ThetaData account/entitlement and import wrapper path are proven.

## 2026-06-27: Agent Runtime Memory Is An Active Agent Workflow, Not A Passive Database

Future agents must treat the options runtime memory graph as an active handoff and writeback surface for multi-step, resumed, CEO-style, audit, or subagent work.

Durable decision: repo startup now points agents to `docs/agent-control-plane.md` for meaningful multi-step work, and the first agent commands are `npm run memory:bootstrap` and `npm run memory:context -- --goal "<goal>" --pathway operator --prompt-only`. Reviewed worker/subagent reports can be made durable through the explicit `npm run memory:writeback -- <task-id> --summary "..."` alias, which fails closed unless a worker report exists and accepted operating-memory nodes are written. `npm run memory:review-dreams` now emits a prompt-ready review packet for proposed dreams, accepted dream lessons/constraints, and dream-origin open questions. Dream proposals validate shape at proposal time, including entry object type, duplicate IDs, metadata object shape, evidence/supersedes list shape, and non-negative integer `freshness_days`, so malformed dreams do not fail later during acceptance. Context packs include accepted dream-derived lessons and constraints by default so agents do not need to know a special query to benefit from prior dream loops.

Automated dreaming runs through `npm run memory:dream-run` and the registered Windows task `\OptionsMemoryDreaming`. The automation is deterministic: it extracts only explicit `Lesson:`, `Constraint:`, and `Open question:` lines from logged session transcript nodes and their transcript files, then auto-accepts only same-tenant session-transcript-graph-evidence-backed `lesson`, `constraint`, and `open_question` entries under `auto_dream_v1`. It auto-rejects decisions, blockers, supersession attempts, observed-confidence claims, unevidenced or fabricated-evidence entries, self-referential dream evidence, non-session evidence, unreadable transcript-source sessions, and any high-risk options-action wording including auto-track, broker/order, live-validation, evidence-store mutation, quote import, protected-holdout, scanner-policy, proof-bar, promotion, and stop/sizing wording. Audits are available through `npm run memory:dream-audit` and `data/agent-control/dream-runs/latest.md`.

All operating-memory nodes are machine-labeled `authority_scope=orchestration_only` and `does_not_authorize_trading_or_evidence_mutation=true`. Memory remains useful for coordination, recovery, lessons, blockers, and review context only. It does not authorize evidence mutation, scanner policy changes, proof-bar changes, broker action, promotion, live validation, quote import, stop/sizing changes, protected-holdout use, or treating task acceptance, worker reports, dreams, or historical rows as options proof.

## 2026-06-27: Strict-Forward Profitability Handoffs Fail Closed On Runtime And Fresh Zero-Candidate Evidence

Strict-forward profitability handoffs must not treat configured scheduled tasks, stale throughput artifacts, or empty candidate files as enough evidence to continue the `30`-trade forward audit.

Durable decision: `scripts/build_regular_options_strict_forward_30_scheduler_health.py` separates scheduler configuration from actual runtime telemetry and fails closed as `scheduler_runtime_blocked` when `\OptionsStrictForward30Collector` is stale, failed, or unobservable. `scripts/build_regular_options_strict_forward_scan_task_health.py` evaluates the 11:00/11:30 scheduled scan feeders as weekday daily tasks, not as repeated 30-minute collectors. `scripts/build_regular_options_forward_candidate_throughput_audit.py` emits scoped `zero_candidate_diagnostics` only for target-date, post-freeze, scheduled-session zero-candidate states and avoids false zero-candidate claims when ledger sources are unavailable, target dates are pre-freeze, or scheduled scan picks exist. `scripts/build_regular_options_strict_forward_30_candidate_review_packet.py` loads the throughput latest artifact, requires it to be fresh and same-target before using zero-candidate evidence, and surfaces that evidence in the review packet without appending or authorizing live paths.

This is read-only blocker reporting. It does not append cohort rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, mutate evidence stores, promote lanes, or treat historical rows as forward proof.

## 2026-06-27: Agent-Control Task Lifecycle Writes Use Guarded Status Transitions

The runtime memory graph's task ledger must not allow stale concurrent writers to regress task state after a task has already reached a terminal or newer lifecycle state.

Durable decision: `scripts/agent_control.py` now uses compare-and-swap-style guarded updates for `claim`, `report`, and `accept`. Each transition writes only when the current database status is still in the allowed source set, otherwise the transaction rolls back with a controlled concurrency error. This keeps submitted reports, claims, accepted decisions, graph status metadata, and operating-memory writeback aligned under concurrent CEO/worker activity.

This is local orchestration and memory integrity only. It does not authorize evidence mutation, scanner policy changes, proof-bar changes, broker action, promotion, live validation, quote import, or treating task acceptance as options proof.

## 2026-06-27: Strict-Forward Readiness, Review, And Completion Require Scan-Task Health

Strict-forward review and completion must not be able to report fresh dependencies when the scheduled scan feeders are broken. Scheduler h

Relevant PROJECT_CONTEXT excerpt:
# Project Context

This repository is a mixed Next.js and FastAPI options research system. The active regular-options product is a supervised lane family for scanning, replay diagnostics, paper ideas, and tracked-position review. The browser UI is organized as a `Trading Desk` for open/closed positions, Alpaca paper-tracked positions, and an all-tracked-stock rollup, with live scan picks available behind the archive toggle, plus a replay-first `Strategy Lab` for validation and policy editing. FastAPI `python-backend/main.py` remains the app composition root, while profile, predictions, and tools routes are extracted into late-bound route modules so LLM agents can read route ownership without losing test-time monkeypatch behavior. Decorator-free application services now include `python-backend/proof_summary_service.py` for `/api/proof-summary`, `python-backend/replay_profit_service.py` for replay/profit readback assembly, and `python-backend/alpaca_paper_trading.py` for opt-in Alpaca paper order submission from proof-gated scanner-origin creates; proof, replay, scanner policy, broker-paper, and profit-cycle semantics stay in the domain modules named by `docs/replay-profit-contract.md` and `docs/DECISIONS.md`. The Trading Desk now treats open tracked positions, Alpaca paper-tracked rows, and open paper ideas as operator review surfaces, while closed/history-heavy rows load on demand through paged read routes. Closed Trades defaults to `Truth-grade`, the strict production-proof filter for live-production accuracy claims. `Realized P&L` remains available as a broader executable historical-learning slice, but historical current-policy guardrail replay is no longer surfaced in the operator dashboard because it can be mistaken for current recommendations or forward-audit performance.

The proof/evidence contract for those views is versioned at `data/contracts/proof-evidence-contract.json` and explained in `docs/proof-evidence-contract.md`. Backend proof predicates remain authoritative; frontend evidence groups flow from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts` as display/readability wrappers around the same proof classes, quote evidence classes, research/backfill markers, top-level and source-snapshot backfill/migration identity fields, and exit-basis tokens. Compact Trading Desk rows emit read-time `evidence_group` and `quote_evidence_class` diagnostics from the same contract; those labels are not persisted authority and stale frontend labels fail closed by contract version. Read-only audit and research reports use `scripts/quote_evidence_readback.py` for the same quote-class vocabulary, while separately labeling research/backfill row policy and production-proof falsehood. The generated `docs/proof-invariant-table.md`, sourced from `data/contracts/proof-invariant-cases.json`, is the shared backend/frontend regression matrix for raw exact, production proof, Truth-grade, and realized-P&L boundaries.

AI commodity / commodity-infrastructure options is a separate proof-first strategy lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`. The generated isolation owner is `docs/ai-commodity-isolation.md`, backed by `data/contracts/ai-commodity-isolation.json`. Its preferred final proof path is Alpaca SIP/OPRA bid/ask snapshot replay using `alpaca_opra_daily_snapshot` rows in `data/options-validation/options_history.db`.

The lane must not claim profitability from underlying bars, option OHLC bars, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, or in-sample-only sweeps. Final promotion requires point-in-time bid/ask or NBBO replay with realistic costs and validation splits.

Regular-options metric readbacks must now use the same proof posture. WFO simulation charges slippage and per-contract fees, expiry settlement uses expiry-day prices, blank/unknown evidence classes quarantine instead of fail-opening to live evidence, profit factor is nullable for no-loss samples, and PF claims use net USD P&L where available. The fresh forward evidence funnel still has `0` exact realized P&L rows and `0` promotion-ready rows; the current named-gate defect report is `docs/fresh-executable-evidence-defect-report-2026-06-09.md`. QQQ `id=537` now has a fresh executable exact HOLD review and SBUX `id=104` is closed from executable exact side-aware exit evidence, so the remaining fresh-evidence gate is legitimate exact realized exit P&L for QQQ `id=537` or another fresh candidate.

The regular supervised scanner safety contract is now lane-wide and metadata-driven. Regular playbooks default to fresh live validation and `position_tracking_mode=auto_track`; AI Commodity remains separate with scanner/tracked-position tracking disabled. Production scans default to portfolio caps on; caps-off scans are diagnostic unless explicitly allowed. Scanner-origin position and suggested-trade creation requires verified archived forward-scan lineage, a caps-enforced source scan, source `creation_eligible=true`, a current guardrail rerun, and exact-contract proof eligibility. When caps are enforced, existing positions, same-ticker/exact-spread exposure, max concurrent positions, cost-risk, drawdown, daily/weekly loss, sector/regime caps, and correlated-index exposure are hard blockers for auto-track and scanner-origin creation; near-cap notes and sizing reductions may remain cautions. Historical/research rows must use explicit manual modes and remain separated from production proof; control/scout proof labels do not make fresh executable regular rows paper-review-only.
The scanner creation safety contract is versioned at `data/contracts/scanner-creation-safety-contract.json` and explained in `docs/scanner-creation-safety-contract.md`. Scheduled auto-track requires explicit market-open state, an available caps-enforced exposure snapshot, auto-track playbook metadata, source `creation_eligible=true`, no creation blockers, proof eligibility, fresh profitability/promotion artifacts, and a passing regular open-risk governor; unknown market, exposure, lane, proof, or open-risk state is not a creation event. Manual Alpaca paper execution uses the same scanner-origin creation gate, submits exactly `1` contract through the Alpaca paper endpoint when explicitly enabled, and records broker-paper metadata separately from OPRA/NBBO production-proof evidence.
The candidate lifecycle status contract is generated by `scripts/candidate_lifecycle.py` at `data/contracts/candidate-lifecycle-contract.json`, `docs/candidate-lifecycle-contract.md`, and `src/lib/generated/candidateLifecycleContract.ts`. Queue builders, profitability/promotion gates, pending validation, disposition reporting, and fresh-evidence readbacks use this shared status/outcome vocabulary so paper-only, diagnostic, pending, and validation-attempted rows cannot disappear because a new status was added in only one module. Paper/probation lanes use `pending_paper_exact_evidence` for exact evidence collection; they do not enter `pending_live_validation`.
The Phase 2 regular-options forward cohort is preregistered at `data/contracts/forward-cohort-preregistration.json`, with generated doc `docs/forward-cohort-preregistration.md`. Freeze date is `2026-06-14` and eval date is `2026-07-28`. The frozen lanes are `volatility_expansion_observation` and the clean `bullish_pullback_observation` carrier set (`IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`). `scripts/lane_promotion_state.py`, daily all-lanes/starvation checks, audit completeness guards, scheduled scan logging, and pending validation read this contract so every other regular lane is parked outside the cohort with scans and chores disabled until evaluation or an explicit refreeze. The contract does not lower existing proof bars, consume the protected holdout, submit orders, or convert research/backfill rows into production proof.
Phase 2 candidat

```
