# Regular Options Lane Scan Hypothesis Repair

This report is generated from `scripts/build_regular_options_lane_scan_hypothesis_repair.py`. It is a read-only proof-only diagnostic plan for active regular supervised lanes that produced no signal candidates in the monthly outcome window.

## Summary

- Status: `lane_scan_hypothesis_repair_readback`.
- Overall status: `lane_scan_hypothesis_repair_built_collecting`.
- Target no-signal lanes: `4`.
- Predeclared replacement candidates: `3` across `2` lanes.
- Missing replacement-candidate lanes: `2`.
- Production proof-ready replacement candidates: `0`.
- Fresh exact scan retest rows: `0`.
- True lane outcome P&L rows: `0`.
- Repair status counts: `{"causal_replacement_hypothesis_missing": 2, "predeclared_proof_only_candidate_found": 2}`.
- Promotion ready: `False`.
- Blockers: `["fresh_exact_scan_retest_rows_missing", "some_no_signal_lanes_lack_predeclared_replacement_candidate", "true_lane_outcome_pnl_rows_missing"]`.
- Live policy change: `false`.

## Repair Rows

| Lane | Repair Status | Dates | Signals | Exact | Would Track | Dominant Reject | Candidates | Proof Ready | Next Step |
|---|---|---:|---:|---:|---:|---|---:|---:|---|
| bearish_defensive | `causal_replacement_hypothesis_missing` | 10 | 0 | 0 | 0 | playbook_filter | 0 | 0 | Draft a causal replacement hypothesis from lane design evidence or keep the lane diagnostic; do not loosen thresholds, symbols, expiries, or windows from this zero-signal sample. |
| bearish_index_put_observation | `predeclared_proof_only_candidate_found` | 10 | 0 | 0 | 0 | playbook_filter | 1 | 0 | Collect proof-only exact intraday quote coverage and forward paper scan rows for the predeclared replacement candidate; do not tune scanner filters from the zero-signal sample. |
| quality90_debit55_canary | `causal_replacement_hypothesis_missing` | 10 | 0 | 0 | 0 | playbook_filter | 0 | 0 | Draft a causal replacement hypothesis from lane design evidence or keep the lane diagnostic; do not loosen thresholds, symbols, expiries, or windows from this zero-signal sample. |
| range_breakout_observation | `predeclared_proof_only_candidate_found` | 9 | 0 | 0 | 0 | playbook_filter | 2 | 0 | Collect proof-only exact intraday quote coverage and forward paper scan rows for the predeclared replacement candidate; do not tune scanner filters from the zero-signal sample. |

## Predeclared Replacement Candidates

| Lane | Sleeve | Symbol | Status | Evidence | Candidates | Exact | Unresolved | Quote Coverage | PF | Proof Status |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| bearish_index_put_observation | bearish_index_put_observation_chain_native_timeexit_all_sleeves:QQQ | QQQ | `needs-paper` | `trusted_intraday_unresolved` | 24 | 0 | 24 | 0.0 | 0.0 | `proof_only_collecting_not_production_proof` |
| range_breakout_observation | range_breakout_observation_chain_native_put_timeexit_all_sleeves:QQQ | QQQ | `needs-paper` | `trusted_intraday_unresolved` | 2 | 0 | 2 | 0.0 | 0.0 | `proof_only_collecting_not_production_proof` |
| range_breakout_observation | range_breakout_observation_chain_native_put_timeexit_all_sleeves:SPY | SPY | `needs-paper` | `trusted_intraday_unresolved` | 2 | 0 | 2 | 0.0 | 0.0 | `proof_only_collecting_not_production_proof` |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 7 | `collect_proof_only_lane_scan_retest_rows` | 2 | no_signal_lanes_have_predeclared_proof_only_replacement_candidates |
| 7 | `draft_causal_hypothesis_for_no_signal_lane_without_tuning` | 2 | no_signal_lanes_lack_predeclared_replacement_candidate |

## Boundary

This repair plan is read-only and proof-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, tune thresholds/symbols/expiries/windows from tiny samples, change stops or sizing, change lane promotion, lower proof bars, or synthesize P&L.

