# Missed Regular Picks Filter Matrix

- Generated: `2026-06-05T22:10:15Z`
- Source report: `data/forward-tracking/missed_regular_picks_outcome_latest.json`
- Source generated: `2026-06-05T19:35:21Z`
- Priced untracked rows: `206`
- Baseline PF: `0.34`
- Baseline avg net P&L: `-15.28%`
- Later-date holdout dates: `2026-06-03, 2026-06-04`

## Matrix

| Scenario | Status | Kept | Blocked | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Split |
|---|---|---:|---:|---:|---:|---:|---:|---|
| baseline_all_untracked | baseline_readback | 206 | 0 | 0.34 | -15.28 | 0 | 0 | watch |
| current_lane_gate_allowlist | active_safety_gate_paper_probation | 24 | 182 | 1.72 | 6.75 | 58 | 35 | pass |
| current_lane_gate_self_guardrails | active_safety_gate_paper_probation | 10 | 196 | 84.9 | 34.87 | 61 | 37 | pass |
| exact_spread_dedupe_only | immediate_suppression_candidate | 179 | 27 | 0.34 | -15.44 | 9 | 4 | watch |
| lane_gate_self_guardrails_plus_exact_spread_dedupe | recommended_paper_shadow_policy_candidate | 10 | 196 | 84.9 | 34.87 | 61 | 37 | pass |
| no_debit_gte_45 | diagnostic_retest_required | 169 | 37 | 0.44 | -11.72 | 8 | 11 | watch |
| no_dte_gte_36 | diagnostic_retest_required | 187 | 19 | 0.37 | -13.88 | 5 | 6 | watch |
| no_primary_damage_tickers | diagnostic_retest_required | 105 | 101 | 0.66 | -7.32 | 15 | 19 | watch |
| no_extended_damage_tickers | overfit_warning | 77 | 129 | 2.12 | 9.9 | 17 | 33 | watch |
| primary_combo_no_debit45_dte36_damage_tickers | diagnostic_retest_required | 76 | 130 | 0.86 | -2.75 | 26 | 24 | watch |

## Read

- Lane profitability remains the hard safety gate.
- Passed lanes are paper/probation candidates, not live-production permission.
- Exact duplicate spreads should be suppressed immediately to a single risk owner.
- Debit, DTE, and ticker filters are promising diagnostics but need fresh/OOS proof before scanner promotion.
- The extended ticker exclusion is explicitly overfit-warning territory.

