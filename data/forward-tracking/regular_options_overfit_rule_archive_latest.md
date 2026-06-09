# Regular Options Overfit Rule Archive

This report is generated from `scripts/build_regular_options_overfit_rule_archive.py`. It is a read-only archive of candidate filter rules rejected for overfit, holdout, non-entry-time, or winner-damage reasons.

## Summary

- Status: `overfit_rule_archive_readback`.
- Overall status: `overfit_rules_archived`.
- Candidate rules: `10`.
- Rejected/overfit rules archived: `10` / `10`.
- Unarchived rejected rules: `[]`.
- Paper-candidate rules: `0`.
- Diagnostic retest rules: `0`.
- Live policy change: `false`.

## Archived Rules

| Scenario | Reason | Kept | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Rows | Blockers |
|---|---|---:|---:|---:|---:|---:|---:|---|
| no_primary_damage_tickers | later_date_holdout_not_passed | 105 | 0.66 | -7.32 | 15 | 19 | 22 | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| no_debit_gte_45 | later_date_holdout_not_passed | 169 | 0.44 | -11.72 | 8 | 11 | 38 | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| no_dte_gte_36 | later_date_holdout_not_passed | 187 | 0.37 | -13.88 | 5 | 6 | 36 | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| baseline_all_untracked | later_date_holdout_not_passed | 206 | 0.34 | -15.28 |  |  | 43 | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive |
| no_extended_damage_tickers | source_status_is_overfit_warning | 77 | 2.12 | 9.9 | 17 | 33 | 16 | overfit_status, later_date_holdout_not_passed, winner_damage_warning |
| current_lane_gate_self_guardrails | winner_damage_exceeds_deep_losses_avoided | 10 | 84.9 | 34.87 | 61 | 37 | 2 | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, winner_damage_warning |
| lane_gate_self_guardrails_plus_exact_spread_dedupe | winner_damage_exceeds_deep_losses_avoided | 10 | 84.9 | 34.87 | 61 | 37 | 2 | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, winner_damage_warning |
| current_lane_gate_allowlist | winner_damage_exceeds_deep_losses_avoided | 24 | 1.72 | 6.75 | 58 | 35 | 4 | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, winner_damage_warning |
| primary_combo_no_debit45_dte36_damage_tickers | winner_damage_exceeds_deep_losses_avoided | 76 | 0.86 | -2.75 | 26 | 24 | 16 | winner_damage_exceeds_deep_losses_avoided, later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| exact_spread_dedupe_only | winner_damage_exceeds_deep_losses_avoided | 179 | 0.34 | -15.44 | 9 | 4 | 37 | winner_damage_exceeds_deep_losses_avoided, later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |

## Boundary

This archive is read-only. It does not delete filter-matrix scenarios, create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote rejected rules.

