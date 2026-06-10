# Regular Options Fill-Attempt Evidence Capture Plan

This report is generated from `scripts/build_regular_options_fill_attempt_evidence_capture_plan.py`. It is a read-only row plan for candidates that still need durable fill-attempt evidence before monthly profitability, paper, live-validation, or promotion decisions.

## Summary

- Status: `fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection`.
- Source ledger status: `ledger_collect_exact_evidence`.
- Source fill-attempt rows: `497`.
- Plan rows: `4`.
- Missing fill-attempt evidence: `4`.
- Ledger-stale logged attempts: `0`.
- Market-window required rows: `4`.
- Scan dates: `["2026-06-05"]`.
- Lane counts: `{"short_term": 1, "swing": 2, "volatility_expansion_observation": 1}`.
- Ticker counts: `{"QQQ": 2, "SPY": 2}`.
- Live policy change: `false`.

## Capture Rows

| Priority | Date | Lane | Ticker | Long | Short | Status | Action | Evidence |
|---:|---|---|---|---|---|---|---|---|
| 7 | 2026-06-05 | short_term | QQQ | QQQ260612C00728000 | QQQ260612C00744000 | `missing` | `capture_durable_fill_attempt_on_fresh_selection` | fresh_candidate_still_selected,durable_fill_attempt_jsonl_row,proof_live_opra_exact_contract_entry_snapshot,fill_discipline_snapshot,keep_diagnostic_or_paper_only_until_lane_profitability_gate_passes |
| 7 | 2026-06-05 | swing | QQQ | QQQ260626C00730000 | QQQ260626C00750000 | `missing` | `capture_durable_fill_attempt_on_fresh_selection` | fresh_candidate_still_selected,durable_fill_attempt_jsonl_row,proof_live_opra_exact_contract_entry_snapshot,fill_discipline_snapshot,keep_diagnostic_or_paper_only_until_lane_profitability_gate_passes |
| 7 | 2026-06-05 | swing | SPY | SPY260626C00752000 | SPY260626C00770000 | `missing` | `capture_durable_fill_attempt_on_fresh_selection` | fresh_candidate_still_selected,durable_fill_attempt_jsonl_row,proof_live_opra_exact_contract_entry_snapshot,fill_discipline_snapshot,keep_diagnostic_or_paper_only_until_lane_profitability_gate_passes |
| 7 | 2026-06-05 | volatility_expansion_observation | SPY | SPY260618C00751000 | SPY260618C00763000 | `missing` | `capture_durable_fill_attempt_on_fresh_selection` | fresh_candidate_still_selected,durable_fill_attempt_jsonl_row,proof_live_opra_exact_contract_entry_snapshot,fill_discipline_snapshot |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 7 | `execute_fill_attempt_evidence_capture_plan` | 4 | fresh_candidates_need_durable_fill_attempt_evidence |

## Boundary

This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, backfill broker fills, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote fill-attempt evidence to production proof.

