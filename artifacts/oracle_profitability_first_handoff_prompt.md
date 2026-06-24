# Profitability-First GPT-5.5 Pro Handoff

Replace the current 5.5 Pro handoff prompt with this profitability-first blocker-ranking prompt before continuing the loop.

We are running an options-profitability loop. The user's goal is profit: at least 30 profitable strict completed forward-audit trades in the latest approximately 4-month/post-freeze audit window.

Current state:
- We are not forward-audit profitable.
- Strict completed forward proof is currently 0/30.
- Historical rows, dashboard rows, midpoint/stale/EOD/last/model/manual/synthetic/lookahead rows, and old-algorithm picks are not accepted profitability proof.
- Codex can implement, test, inspect the repo, build artifacts, run read-only research, and run non-live/non-broker source-planning tasks.
- The user approves non-live, non-broker research/source-planning work.
- Broker orders, live validation, auto-track, protected-holdout consumption, promotion, production scanner/strategy/stop/sizing/proof-bar changes, and real source/evidence mutation still require exact explicit approval.

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

3. Data/source blocker
- Which missing point-in-time sources block the most downstream profitable tests?
- Current known blockers include VIX, macro-event calendar, flow volume/OI, dispersion/concentration, trend/regime, and possibly broader OPRA/NBBO coverage.
- Rank source repairs by downstream unlock value and time-to-test.
- Do not select another packet-only source plan unless it is the highest-leverage blocker to running a real replay or forward audit.

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

Hard rules:
- Do not repeat a branch already marked parked unless new source state changed.
- Do not select macro_event_calendar_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select direct_point_in_time_vix_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select trusted_flow_volume_oi_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select the 59-symbol ThetaTerminal retry again until provider/source availability changes.
- Do not select historical dashboard/picks visibility unless it directly affects forward capture.
- Do not claim profitability from historical rows alone.
- Do not stop unless you prove no meaningful upgrade remains across forward capture, source repair/materialization, candidate-generation repair, replay engine support, new option structures, and longer/lookback audits.

Current completed/parked branch facts:
- `direct_vix_source_repair_packet_ready_for_operator_import_decision`: implemented and verified. No VIX import or replay was run.
- `macro_event_calendar_source_repair_packet_ready_for_operator_import_decision`: implemented and verified. No macro-event import or replay was run.
- `flow_extreme_source_repair_packet_ready_for_operator_import_decision`: implemented and verified. No flow import or replay was run.
- `blocked_thetaterminal_source_unavailable_retry`: do not retry 59-symbol ThetaTerminal until provider/source availability changes.
- `blocked_point_in_time_flow_extreme_input`: no trusted local flow source rows exist.
- `blocked_point_in_time_dispersion_concentration_proxy`: no trusted local dispersion/concentration proxy source rows exist.
- `blocked_frozen_13_symbol_candidate_generation_engine`: no reusable frozen no-write candidate-generation entrypoint is proven.
- `no_phase2_natural_selections_no_append`: forward capture staged 0 real same-day Phase 2 rows.

Output JSON-like structure:
```json
{
  "verdict": "continue|stop_exception",
  "continue_loop": true,
  "current_profitability_state": {
    "forward_strict_completed_rows": 0,
    "target_rows": 30,
    "accepted_profitability": false,
    "main_reason_not_profitable": "string"
  },
  "blocker_map": {
    "forward_proof": [],
    "candidate_generation": [],
    "data_sources": [],
    "replay_engine": [],
    "strategy_edges": [],
    "historical_audit": [],
    "dashboard_operator": []
  },
  "ranked_next_tasks": [
    {
      "rank": 1,
      "task_id": "string",
      "expected_profitability_impact": "string",
      "downstream_unlocks": [],
      "time_to_test": "string",
      "why_not_selected_if_applicable": null
    }
  ],
  "selected_branch_id": "string",
  "next_codex_task": {
    "objective": "string",
    "why_highest_leverage": "string",
    "exact_scope": "string",
    "allowed_files_or_artifacts": [],
    "forbidden_actions": [],
    "implementation_steps": [],
    "commands_to_run": [],
    "acceptance_criteria": [],
    "failure_criteria": [],
    "downstream_enabled_if_passes": [],
    "branch_stop_condition_if_fails": "string"
  },
  "branches_to_stop": [],
  "operator_questions": [],
  "anti_handwave_audit": {
    "exact_next_action_present": true,
    "measurable_threshold_present": true,
    "generic_advice_removed": true
  }
}
```

Use the attached current Oracle packet and current memory docs as evidence. If any attached artifact conflicts with this instruction, obey the profitability-first blocker-ranking instruction and explain the conflict.
