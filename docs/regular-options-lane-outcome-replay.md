# Regular Options Lane Outcome Replay

This report is generated from `scripts/build_regular_options_lane_outcome_replay.py`. It is a read-only lane-outcome coverage report and does not synthesize P&L for lanes without exact priced outcome rows.

## Summary

- Status: `lane_outcome_replay_readback`.
- Overall status: `lane_outcome_replay_built_collecting`.
- Active lanes: `13`.
- Priced outcome lanes: `8`.
- Missing outcome lanes: `5`.
- Outcome status counts: `{"monthly_exact_outcome_available": 8, "no_signal_candidates_in_monthly_window": 4, "signal_candidates_without_exact_chain_native_spreads": 1}`.
- Zero-pick lanes completed: `13` / `13`.
- Next evidence actions: `2`.
- Promotion ready: `False`.
- Blockers: `["missing_monthly_exact_outcome_rows_for_5_lanes", "no_signal_candidates_for_lane_outcome_replay", "signals_without_exact_candidates"]`.
- Live policy change: `false`.

## Lane Outcome Table

| Lane | Disposition | Outcome Status | Monthly Priced | PF | Avg Net | Net USD | Signals | Exact | Would Track | Next Action |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| bearish_defensive | `needs_replay_engine` | `no_signal_candidates_in_monthly_window` |  |  |  |  | 0 | 0 | 0 | `build_or_repair_lane_scan_hypothesis_before_pnl_replay` |
| bearish_index_put_observation | `needs_replay_engine` | `no_signal_candidates_in_monthly_window` |  |  |  |  | 0 | 0 | 0 | `build_or_repair_lane_scan_hypothesis_before_pnl_replay` |
| bullish_momentum | `quarantine` | `monthly_exact_outcome_available` | 16 | 0.1 | -48.45 | -3819.3 | 44 | 44 | 16 | `use_monthly_profitability_audit_disposition` |
| bullish_pullback_observation | `quarantine` | `monthly_exact_outcome_available` | 15 | 0.29 | -22.81 | -3698.45 | 27 | 27 | 15 | `use_monthly_profitability_audit_disposition` |
| quality90_debit55_canary | `needs_replay_engine` | `no_signal_candidates_in_monthly_window` |  |  |  |  | 0 | 0 | 0 | `build_or_repair_lane_scan_hypothesis_before_pnl_replay` |
| range_breakout_observation | `needs_replay_engine` | `no_signal_candidates_in_monthly_window` |  |  |  |  | 0 | 0 | 0 | `build_or_repair_lane_scan_hypothesis_before_pnl_replay` |
| regular_bearish_put_primary | `needs_replay_engine` | `signal_candidates_without_exact_chain_native_spreads` |  |  |  |  | 4 | 0 | 0 | `repair_chain_native_exact_candidate_selection` |
| short_term | `quarantine` | `monthly_exact_outcome_available` | 54 | 0.28 | -18.93 | -3518.15 | 137 | 131 | 54 | `use_monthly_profitability_audit_disposition` |
| speculative | `retest` | `monthly_exact_outcome_available` | 8 | 0.12 | -12.62 | -413.15 | 8 | 8 | 8 | `use_monthly_profitability_audit_disposition` |
| swing | `quarantine` | `monthly_exact_outcome_available` | 49 | 0.3 | -14.31 | -3781.95 | 114 | 114 | 49 | `use_monthly_profitability_audit_disposition` |
| tracked_winner_observation | `retest` | `monthly_exact_outcome_available` | 20 | 0.46 | -9.19 | -1027.65 | 23 | 20 | 20 | `use_monthly_profitability_audit_disposition` |
| tracked_winner_primary | `retest` | `monthly_exact_outcome_available` | 20 | 0.46 | -9.19 | -1027.65 | 23 | 20 | 20 | `use_monthly_profitability_audit_disposition` |
| volatility_expansion_observation | `paper_shadow` | `monthly_exact_outcome_available` | 24 | 1.72 | 6.75 | 972.3 | 25 | 25 | 24 | `use_monthly_profitability_audit_disposition` |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 4 | `repair_chain_native_exact_candidate_selection` | 1 | signals_exist_but_no_exact_chain_native_spreads |
| 7 | `build_or_repair_lane_scan_hypothesis_before_pnl_replay` | 4 | no_signal_candidates_in_monthly_window |

## Boundary

This lane outcome replay is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or synthesize outcome P&L for lanes without exact priced rows.

