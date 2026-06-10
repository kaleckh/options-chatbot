# Missed Regular Picks Filter Matrix

- Generated: `2026-06-10T06:27:17Z`
- Source report: `data/forward-tracking/missed_regular_picks_outcome_latest.json`
- Source generated: `2026-06-10T06:27:05Z`
- Priced untracked rows: `206`
- Quote evidence class: `trusted_intraday_opra_nbbo`
- Row evidence group: `research_backfill`
- Production proof claim: `False`
- Baseline PF: `0.32`
- Baseline avg net P&L: `-16.54%`
- Later-date holdout dates: `2026-06-03, 2026-06-04`

## Matrix

| Scenario | Status | Kept | Blocked | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Split |
|---|---|---:|---:|---:|---:|---:|---:|---|
| baseline_all_untracked | baseline_readback | 206 | 0 | 0.32 | -16.54 | 0 | 0 | watch |
| current_lane_gate_allowlist | active_safety_gate_paper_probation | 24 | 182 | 1.83 | 6.74 | 60 | 39 | watch |
| current_lane_gate_self_guardrails | active_safety_gate_paper_probation | 10 | 196 | 69.14 | 34.87 | 63 | 41 | pass |
| exact_spread_dedupe_only | immediate_suppression_candidate | 179 | 27 | 0.31 | -16.98 | 10 | 4 | watch |
| lane_gate_self_guardrails_plus_exact_spread_dedupe | recommended_paper_shadow_policy_candidate | 10 | 196 | 69.14 | 34.87 | 63 | 41 | pass |
| no_debit_gte_45 | diagnostic_retest_required | 169 | 37 | 0.41 | -11.79 | 6 | 14 | watch |
| no_dte_gte_36 | diagnostic_retest_required | 187 | 19 | 0.37 | -15.27 | 5 | 6 | watch |
| no_primary_damage_tickers | diagnostic_retest_required | 105 | 101 | 0.6 | -10.37 | 19 | 19 | watch |
| no_extended_damage_tickers | overfit_warning | 77 | 129 | 1.0 | 5.73 | 21 | 33 | watch |
| primary_combo_no_debit45_dte36_damage_tickers | diagnostic_retest_required | 76 | 130 | 1.06 | -3.69 | 28 | 27 | watch |

## Read

- Lane profitability remains the hard safety gate.
- Passed lanes are paper/probation candidates, not live-production permission.
- Exact duplicate spreads should be suppressed immediately to a single risk owner.
- Debit, DTE, and ticker filters are promising diagnostics but need fresh/OOS proof before scanner promotion.
- The extended ticker exclusion is explicitly overfit-warning territory.

