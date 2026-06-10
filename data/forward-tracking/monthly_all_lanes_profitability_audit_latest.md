# Monthly All-Lanes Profitability Audit

This report is generated from `scripts/build_monthly_all_lanes_profitability_audit.py`. It is a read-only command center for monthly regular-options profitability iteration and does not change scanner, broker, database, stop, sizing, proof, or lane-promotion behavior.

## Summary

- Status: `monthly_profitability_readback`.
- Overall status: `profitability_iteration_ready_blocked_for_promotion`.
- Baseline PF / avg: `0.32` / `-16.54%`.
- Recent month: `2026-05` / `paper_only_recent_break`.
- Execution realism: `ready`.
- Risk/portfolio: `blocked`.
- Promotion gate: `blocked` with `24` blockers.
- Open-risk status / live entry allowed: `open_risk_governor_pass` / `True`.
- Oracle ceiling: `not_available_replay_gap`.
- Stale candidate archive: `stale_candidates_archived` / `built` / `{"archive_complete": true, "archive_exception_count": 0, "archived_no_longer_matched_candidate_count": 16, "lane_counts": {"quality90_debit55_canary": 2, "swing": 9, "tracked_winner_observation": 1, "tracked_winner_primary": 1, "volatility_expansion_observation": 3}, "production_proof_ready_count": 0, "source_wait_or_archive_count": 16, "ticker_counts": {"QQQ": 7, "SPY": 9}}`.
- Candidate rules: `10` total, `0` paper candidates, `10` rejected/overfit.
- Lane dispositions: `all_active_regular_lanes_classified_read_only` / `{"archive": 0, "needs_replay_engine": 5, "paper_shadow": 1, "profitable_candidate": 0, "quarantine": 4, "retest": 3}`.
- Lane outcome replay: `lane_outcome_replay_built_collecting` / `built_collecting` / `{"active_lane_count": 13, "missing_outcome_lane_count": 5, "outcome_status_counts": {"monthly_exact_outcome_available": 8, "no_signal_candidates_in_monthly_window": 4, "signal_candidates_without_exact_chain_native_spreads": 1}, "priced_outcome_lane_count": 8}`.
- Lane scan hypothesis repair: `lane_scan_hypothesis_repair_built_collecting` / `built_collecting` / `{"fresh_exact_scan_retest_row_count": 0, "missing_replacement_candidate_lane_count": 2, "predeclared_candidate_lane_count": 2, "predeclared_replacement_candidate_count": 3, "proof_ready_replacement_candidate_count": 0, "repair_status_counts": {"causal_replacement_hypothesis_missing": 2, "predeclared_proof_only_candidate_found": 2}, "target_no_signal_lane_count": 4, "true_lane_outcome_pnl_row_count": 0}`.
- Exact-candidate selection repair: `exact_candidate_selection_repair_targets_ready` / `built_collecting` / `{"exact_reject_reason_counts": {"no_chain_native_spread_passed_current_filters": 4}, "target_date_count": 1, "target_exact_candidate_count": 0, "target_lane_count": 1, "target_signal_candidate_count": 4, "top_signal_tickers": ["COIN", "DIS", "META", "SBUX"]}`.
- Chain-native filter relaxation replay: `chain_native_filter_relaxation_replay_candidates_found_diagnostic_only` / `built_collecting` / `{"current_selected_chain_native_entry_spread_count": 4, "entry_quote_demand_count": 0, "entry_quote_demand_tickers": [], "relaxed_selected_chain_native_entry_spread_count": 24, "replay_signal_candidate_count": 4, "scenario_count": 7, "scenario_row_count": 28, "scenario_status_counts": {"selected_chain_native_entry_spread": 28}, "target_date_count": 1, "target_lane_count": 1, "target_signal_candidate_count": 4}`.
- Chain-native exit outcome replay: `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only` / `built_collecting` / `{"best_relaxed_scenario": {"avg_net_pnl_pct": -9.26, "avg_net_pnl_usd": -288.5, "loser_count": 3, "max_net_pnl_pct": 61.57, "median_net_pnl_pct": -18.85, "min_net_pnl_pct": -60.9, "priced": 4, "profit_factor": 0.62, "relaxation_kind": "relaxed", "rows": 4, "scenario_id": "widen_dte_window_only", "sum_net_pnl_usd": -1154.0, "unpriced": 0, "win_rate_pct": 25.0, "winner_count": 1}, "current_selected_scenario_row_count": 4, "latest_intraday_quote_date": "2026-06-04", "missing_exit_quote_demand_count": 0, "priced_current_scenario_row_count": 4, "priced_relaxed_scenario_row_count": 24, "priced_scenario_row_count": 28, "relaxed_selected_scenario_row_count": 24, "selected_scenario_row_count": 28}`.
- Execution-alternative quote import plan: `no_quote_demands_to_plan` / `built` / `{"command_group_count": 0, "entry_quote_demand_count": 0, "exact_contract_manifest_count": 0, "exit_quote_demand_count": 0, "operator_command_status": "not_available", "quote_dates": [], "source_coverage_status": "execution_alternative_replay_coverage_readback", "source_quote_demand_manifest_status": "no_missing_quote_demands", "underlyings": [], "unparsed_quote_demand_count": 0}`.
- Minute-exit quote import plan: `no_minute_exit_quote_seeds_to_plan` / `built` / `{"command_group_count": 0, "entry_only_quote_demand_count": 0, "exact_contract_manifest_count": 0, "operator_command_status": "not_available", "position_linked_quote_demand_count": 0, "quote_dates": [], "replay_pnl_status": "available_in_source_readiness", "source_entry_seed_ready_count": 12, "source_minute_exit_replay_engine_status": "read_only_side_aware_engine_partial", "source_minute_quote_coverage_status": "full", "source_overall_status": "minute_exit_replay_coverage_ready", "source_position_seed_ready_count": 1, "source_readiness_status": "minute_exit_replay_readiness_readback", "source_true_minute_exit_pnl_count": 12, "underlyings": [], "unparsed_quote_demand_count": 0}`.
- Open-risk resolution plan: `open_risk_resolution_plan_clear` / `built` / `{"action_counts": {}, "display_only_sell_count": 0, "live_entry_allowed": true, "live_exact_negative_count": 1, "live_exact_negative_ids": [537], "live_exact_plan_row_count": 0, "market_window_required_count": 0, "open_position_avg_pnl_pct": -54.51, "open_position_median_pnl_pct": -57.66, "open_position_negative_count": 5, "open_position_row_count": 5, "operator_plan_status": "no_rows_to_resolve", "plan_row_count": 0, "source_open_risk_status": "open_risk_governor_pass"}`.
- Fill-attempt evidence capture plan: `fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection` / `built_collecting` / `{"lane_counts": {"short_term": 1, "swing": 2, "volatility_expansion_observation": 1}, "ledger_stale_fill_attempt_logged_count": 0, "market_window_required_count": 4, "missing_fill_attempt_evidence_count": 4, "operator_plan_status": "ready_for_fresh_selection_capture", "plan_row_count": 4, "scan_dates": ["2026-06-05"], "source_candidate_ledger_operating_status": "ledger_collect_exact_evidence", "source_fill_attempt_rows": 497, "source_missing_fill_attempt_action_count": 4, "ticker_counts": {"QQQ": 2, "SPY": 2}}`.
- Suggested-trade review plan: `suggested_trade_review_plan_ready_blocked_for_market_window` / `built_collecting` / `{"attention_trade_count": 1, "close_risk_trade_count": 0, "executable_close_ready_count": 0, "market_window_required_count": 1, "missing_review_count": 1, "non_executable_close_risk_count": 0, "open_suggested_trade_rows": 1, "operator_plan_status": "ready_for_fresh_suggested_trade_review_window", "plan_row_count": 1, "source_action_counts": {"no_stored_review": 1}, "source_evidence_counts": {"missing_review": 1}, "stale_or_missing_review_trade_count": 1, "stale_review_count": 0}`.
- Quarantine archive: `4` archived, `0` unarchived.
- Archived rejected rules: `10` archived, `0` unarchived.
- Next evidence actions: `10`.
- Live policy change: `false`.

## Lane Leaderboard

| Lane | Rows | PF | Avg Net | Median | Win Rate | Net USD | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| bullish_momentum | 16 | 0.04 | -48.45 | -54.84 | 12.5 | -3819.3 | diagnostic_only_until_earn_back |
| bullish_pullback_observation | 15 | 0.24 | -22.81 | -24.1 | 33.3 | -3698.45 | diagnostic_only_until_earn_back |
| swing | 49 | 0.2 | -20.24 | -16.81 | 30.6 | -6331.95 | diagnostic_only_until_earn_back |
| short_term | 54 | 0.33 | -18.93 | -16.91 | 33.3 | -3518.15 | diagnostic_only_until_earn_back |
| speculative | 8 | 0.1 | -12.62 | -15.53 | 25.0 | -413.15 | diagnostic_only_until_earn_back |
| tracked_winner_primary | 20 | 0.5 | -8.43 | -5.72 | 45.0 | -972.65 | diagnostic_only_until_earn_back |
| tracked_winner_observation | 20 | 0.5 | -8.43 | -5.72 | 45.0 | -972.65 | diagnostic_only_until_earn_back |
| volatility_expansion_observation | 24 | 1.83 | 6.74 | 2.15 | 50.0 | 971.3 | probation_candidate_flow_with_self_guardrails |

## Lane Dispositions

- Status: `all_active_regular_lanes_classified_read_only`.
- Allowed statuses: `["profitable_candidate", "paper_shadow", "retest", "needs_replay_engine", "quarantine", "archive"]`.
- Counts: `{"archive": 0, "needs_replay_engine": 5, "paper_shadow": 1, "profitable_candidate": 0, "quarantine": 4, "retest": 3}`.
- Quarantine archive: `4` archived, `0` unarchived.

| Lane | Disposition | Archive | Priced | PF | Avg Net | Promotion State | Source Decision | Next Step |
|---|---|---|---:|---:|---:|---|---|---|
| bearish_defensive | `needs_replay_engine` | `` |  |  |  | diagnostic | diagnostic_only_lane_promotion_state | build or refresh exact lane outcome replay before tuning or promotion discussion |
| bearish_index_put_observation | `needs_replay_engine` | `` |  |  |  | diagnostic | diagnostic_only_lane_promotion_state | build or refresh exact lane outcome replay before tuning or promotion discussion |
| bullish_momentum | `quarantine` | `archived_quarantine_lane` | 16 | 0.04 | -48.45 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| bullish_pullback_observation | `quarantine` | `archived_quarantine_lane` | 15 | 0.24 | -22.81 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| quality90_debit55_canary | `needs_replay_engine` | `` |  |  |  | diagnostic | diagnostic_only_lane_promotion_state | build or refresh exact lane outcome replay before tuning or promotion discussion |
| range_breakout_observation | `needs_replay_engine` | `` |  |  |  | diagnostic | diagnostic_only_lane_promotion_state | build or refresh exact lane outcome replay before tuning or promotion discussion |
| regular_bearish_put_primary | `needs_replay_engine` | `` |  |  |  | diagnostic | diagnostic_only_lane_promotion_state | build or refresh exact lane outcome replay before tuning or promotion discussion |
| short_term | `quarantine` | `archived_quarantine_lane` | 54 | 0.33 | -18.93 | diagnostic | diagnostic_only_until_earn_back | negative sufficiently sized lane should stay out of live validation until earn-back |
| speculative | `retest` | `` | 8 | 0.1 | -12.62 | diagnostic | diagnostic_only_until_earn_back | freeze an entry-time-only retest or collect more exact evidence before lane decisions |
| swing | `quarantine` | `archived_quarantine_lane` | 49 | 0.2 | -20.24 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| tracked_winner_observation | `retest` | `` | 20 | 0.5 | -8.43 | diagnostic | diagnostic_only_until_earn_back | freeze an entry-time-only retest or collect more exact evidence before lane decisions |
| tracked_winner_primary | `retest` | `` | 20 | 0.5 | -8.43 | diagnostic | diagnostic_only_until_earn_back | freeze an entry-time-only retest or collect more exact evidence before lane decisions |
| volatility_expansion_observation | `paper_shadow` | `` | 24 | 1.83 | 6.74 | paper_probation | probation_candidate_flow_with_self_guardrails | collect fresh exact paper entries and exact realized exits before promotion |

## Stale Candidate Archive

- Status: `stale_candidates_archived` / `built`.
- Source wait/archive rows: `16`.
- Archived no-longer-matched candidates: `16`.
- Archive exceptions: `0`.
- Archive complete: `True`.
- Lane counts: `{"quality90_debit55_canary": 2, "swing": 9, "tracked_winner_observation": 1, "tracked_winner_primary": 1, "volatility_expansion_observation": 3}`.
- Ticker counts: `{"QQQ": 7, "SPY": 9}`.
- Production proof-ready rows: `0`.

## Lane Outcome Replay

- Status: `lane_outcome_replay_built_collecting` / `built_collecting`.
- Active / priced / missing lanes: `13` / `8` / `5`.
- Outcome status counts: `{"monthly_exact_outcome_available": 8, "no_signal_candidates_in_monthly_window": 4, "signal_candidates_without_exact_chain_native_spreads": 1}`.

## Lane Scan Hypothesis Repair

- Status: `lane_scan_hypothesis_repair_built_collecting` / `built_collecting`.
- Target no-signal lanes: `4`.
- Predeclared replacement candidates / lanes: `3` / `2`.
- Missing replacement-candidate lanes: `2`.
- Production proof-ready candidates: `0`.
- Fresh exact scan retest / true lane outcome P&L rows: `0` / `0`.
- Repair status counts: `{"causal_replacement_hypothesis_missing": 2, "predeclared_proof_only_candidate_found": 2}`.

## Exact Candidate Selection Repair

- Status: `exact_candidate_selection_repair_targets_ready` / `built_collecting`.
- Target lanes / dates: `1` / `1`.
- Signals / exact candidates: `4` / `0`.
- Exact reject reasons: `{"no_chain_native_spread_passed_current_filters": 4}`.
- Top signal tickers: `["COIN", "DIS", "META", "SBUX"]`.

## Chain-Native Filter Relaxation Replay

- Status: `chain_native_filter_relaxation_replay_candidates_found_diagnostic_only` / `built_collecting`.
- Target lanes / dates: `1` / `1`.
- Replay signals / scenario rows: `4` / `28`.
- Current / relaxed selected entry spreads: `4` / `24`.
- Entry quote demands: `0` / `[]`.
- Scenario status counts: `{"selected_chain_native_entry_spread": 28}`.

## Chain-Native Exit Outcome Replay

- Status: `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only` / `built_collecting`.
- Selected / priced rows: `28` / `28`.
- Current / relaxed priced rows: `4` / `24`.
- Missing exit quote demands: `0`.
- Best relaxed scenario: `{"avg_net_pnl_pct": -9.26, "avg_net_pnl_usd": -288.5, "loser_count": 3, "max_net_pnl_pct": 61.57, "median_net_pnl_pct": -18.85, "min_net_pnl_pct": -60.9, "priced": 4, "profit_factor": 0.62, "relaxation_kind": "relaxed", "rows": 4, "scenario_id": "widen_dte_window_only", "sum_net_pnl_usd": -1154.0, "unpriced": 0, "win_rate_pct": 25.0, "winner_count": 1}`.

## Chain-Native Relaxation Archive

- Status: `negative_chain_native_branches_archived` / `built`.
- Source ready / archive requested: `True` / `True`.
- Total / negative / archived branches: `7` / `7` / `7`.
- Current / negative / archived scenarios: `1` / `1` / `1`.
- Relaxed / negative / archived scenarios: `6` / `6` / `6`.
- Unarchived negative branches: `0`.
- Archive complete: `True`.

## Exhausted Contract Archive

- Status: `exhausted_contract_target_archived` / `built`.
- Source ready: `True`.
- Archived exhausted contracts: `8`.
- Previously / newly archived exhausted contracts: `7` / `1`.
- Remaining eligible exhausted contracts: `38`.
- Source exhausted targets: `97`.

## Monthly Drift

- Showcase month: `2026-04`.
- Recent month: `2026-05`.
- Recent week: `2026-W21`.

| Month | Priced | Avg P&L | Median | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| 2026-04 | 70 | 81.17 | 71.82 | 8.6 | healthy |
| 2026-05 | 42 | 7.49 | -4.6 | 54.8 | paper_only_recent_break |

| Recent Lane Cohort | Priced | Avg P&L | Median | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| 2026-05:bullish_momentum | 5 | 53.55 | 51.21 | 20.0 | healthy |
| 2026-05:bullish_pullback_observation | 2 | -73.37 | -73.37 | 100.0 | paper_only_thin_severe |
| 2026-05:short_term | 17 | -12.3 | -55.41 | 70.6 | paper_only_recent_break |
| 2026-05:swing | 18 | 22.38 | 7.35 | 44.4 | watch_recent_fragile |

| Recent Ticker Cohort | Priced | Avg P&L | Median | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| 2026-05:DIS | 1 | -99.54 | -99.54 | 100.0 | paper_only_thin_severe |
| 2026-05:WMT | 1 | -99.46 | -99.46 | 100.0 | paper_only_thin_severe |
| 2026-05:BAC | 1 | -97.5 | -97.5 | 100.0 | paper_only_thin_severe |
| 2026-05:BA | 1 | -96.17 | -96.17 | 100.0 | paper_only_thin_severe |
| 2026-05:MSTR | 1 | -92.19 | -92.19 | 100.0 | paper_only_thin_severe |
| 2026-05:TSLA | 3 | -90.57 | -91.93 | 100.0 | paper_only_recent_break |
| 2026-05:GOOGL | 1 | -83.61 | -83.61 | 100.0 | paper_only_thin_severe |
| 2026-05:COIN | 1 | -71.42 | -71.42 | 100.0 | paper_only_thin_severe |
| 2026-05:UNH | 1 | -63.12 | -63.12 | 100.0 | paper_only_thin_severe |
| 2026-05:NVDA | 2 | -7.0 | -7.0 | 50.0 | paper_only_recent_break |

## Worst Buckets

| Ticker Cluster | Rows | PF | Avg Net | Net USD |
|---|---:|---:|---:|---:|
| XLK | 31 | 0.01 | -37.43 | -6099.6 |
| SPY | 39 | 0.22 | -11.03 | -2073.5 |
| TSLA | 11 | 0.0 | -36.14 | -4086.7 |
| IWM | 20 | 0.12 | -16.51 | -1251.2 |
| AA | 5 | 0.0 | -58.93 | -935.95 |
| AMZN | 4 | 0.03 | -61.01 | -1108.5 |
| PLD | 2 | 0.0 | -101.43 | -369.2 |
| NVDA | 3 | 0.0 | -67.12 | -1357.2 |
| FCX | 7 | 0.08 | -25.81 | -419.9 |
| SLB | 3 | 0.0 | -58.47 | -312.25 |
| BA | 2 | 0.0 | -79.67 | -580.4 |
| QQQ | 21 | 0.57 | -4.66 | -1326.3 |

| DTE Bucket | Rows | PF | Avg Net | Net USD |
|---|---:|---:|---:|---:|
| 36_plus | 19 | 0.12 | -29.05 | -5454.7 |
| 11_20 | 55 | 0.24 | -19.36 | -6993.35 |
| 6_10 | 61 | 0.37 | -18.04 | -3535.6 |
| 21_35 | 66 | 0.57 | -10.03 | -2664.2 |
| lte5 | 5 | 0.3 | -5.78 | -107.15 |

- Fill degradation buckets: `not_available_in_missed_pick_failure_modes`.

## Candidate Rules

| Scenario | Classification | Archive | Kept | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Rows | Later Pass | Blockers |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| current_lane_gate_self_guardrails | `reject_overfit` | `archived_rejected_rule` | 10 | 69.14 | 34.87 | 63 | 41 | 2 | True | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, winner_damage_warning |
| lane_gate_self_guardrails_plus_exact_spread_dedupe | `reject_overfit` | `archived_rejected_rule` | 10 | 69.14 | 34.87 | 63 | 41 | 2 | True | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, winner_damage_warning |
| current_lane_gate_allowlist | `reject_overfit` | `archived_rejected_rule` | 24 | 1.83 | 6.74 | 60 | 39 | 4 | False | winner_damage_exceeds_deep_losses_avoided, thin_later_date_holdout, later_date_holdout_not_passed, winner_damage_warning |
| primary_combo_no_debit45_dte36_damage_tickers | `reject_overfit` | `archived_rejected_rule` | 76 | 1.06 | -3.69 | 28 | 27 | 16 | False | winner_damage_exceeds_deep_losses_avoided, later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| no_extended_damage_tickers | `reject_overfit` | `archived_rejected_rule` | 77 | 1.0 | 5.73 | 21 | 33 | 16 | False | overfit_status, later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, winner_damage_warning |
| no_primary_damage_tickers | `reject_overfit` | `archived_rejected_rule` | 105 | 0.6 | -10.37 | 19 | 19 | 22 | False | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| no_debit_gte_45 | `reject_overfit` | `archived_rejected_rule` | 169 | 0.41 | -11.79 | 6 | 14 | 38 | False | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| no_dte_gte_36 | `reject_overfit` | `archived_rejected_rule` | 187 | 0.37 | -15.27 | 5 | 6 | 36 | False | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |
| baseline_all_untracked | `reject_overfit` | `archived_rejected_rule` | 206 | 0.32 | -16.54 | 0 | 0 | 43 | False | later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive |
| exact_spread_dedupe_only | `reject_overfit` | `archived_rejected_rule` | 179 | 0.31 | -16.98 | 10 | 4 | 37 | False | winner_damage_exceeds_deep_losses_avoided, later_date_holdout_not_passed, profit_factor_below_paper_candidate_gate, average_net_pnl_not_positive, winner_damage_warning |

## Execution Realism

- Fill-attempt rows: `497`.
- Candidate-shown rows: `12`.
- Proof-live exact rows: `10`.
- No-fill / not-submitted / paper-fill-recorded: `6` / `3` / `1`.
- Fill-discipline snapshots: `1`.
- Fill-discipline coverage: `8.33%`.
- Replay blockers: `[]`.
- Minute-exit readiness: `minute_exit_replay_coverage_ready`; entry seeds `12`, position seeds `1`, true minute P&L `12`.

## Execution Alternative Quote Import Plan

- Status: `no_quote_demands_to_plan` / `built`.
- Source coverage: `execution_alternative_replay_coverage_readback` / `no_missing_quote_demands`.
- Exact demands / command groups: `0` / `0`.
- Entry / exit demands: `0` / `0`.
- Dates / underlyings: `[]` / `[]`.

## Minute-Exit Quote Import Plan

- Status: `no_minute_exit_quote_seeds_to_plan` / `built`.
- Source readiness: `minute_exit_replay_readiness_readback` / `minute_exit_replay_coverage_ready`.
- Source entry / position seeds: `12` / `1`.
- Exact demands / command groups: `0` / `0`.
- Position-linked / entry-only demands: `0` / `0`.
- Replay P&L status: `available_in_source_readiness`.
- Dates / underlyings: `[]` / `[]`.

## Open-Risk Resolution Plan

- Status: `open_risk_resolution_plan_clear` / `built`.
- Source open-risk status: `open_risk_governor_pass`.
- Live entry allowed: `True`.
- Plan rows / live exact / display-only SELL: `0` / `0` / `0`.
- Open rows / negative rows: `5` / `5`.
- Avg / median open P&L: `-54.51` / `-57.66`.

| Priority | ID | Ticker | Lane | Class | Action | Status |
|---:|---:|---|---|---|---|---|

## Suggested-Trade Review Plan

- Status: `suggested_trade_review_plan_ready_blocked_for_market_window` / `built_collecting`.
- Open / attention / plan rows: `1` / `1` / `1`.
- Close-risk / stale-missing rows: `0` / `1`.
- Missing / stale reviews: `1` / `0`.
- Executable / non-executable close-ready: `0` / `0`.

| Priority | ID | Ticker | Lane | Class | Action | Status |
|---:|---:|---|---|---|---|---|
| 1 | 138 | AAA | legacy_unlabeled | suggested_trade | `refresh_missing_suggested_trade_review` | `market_window_required_missing_suggested_trade_review` |

## Risk And Portfolio

- Open-risk status: `open_risk_governor_pass`.
- Live entry allowed: `True`.
- Live exact negative IDs: `[537]`.
- Multilane quality status: `quality_pending`.
- Risk-budget sizing status: `collecting` / `built_collecting`.
- Risk-budget sizing best research scenario: `paper_shadow_only` / net `971.3` / PF `1.83`.
- Zero-bid/liquidity blockers: `["bullish_pullback_core:unpriced_candidates_3", "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "lane_a:conservative_zero_bid_pf_0.85_below_1_3", "lane_a:conservative_zero_bid_unpriced_11", "lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0"]`.
- Promotion blockers: `["multilane:bullish_pullback_core:unpriced_candidates_3", "multilane:lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "multilane:lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "multilane:lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch", "multilane:lane_a:conservative_zero_bid_pf_0.85_below_1_3", "multilane:lane_a:conservative_zero_bid_unpriced_11", "multilane:lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", "multilane:paper_shadow_fill_evidence_pending", "bullish_pullback_core:unpriced_candidates_3", "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch", "lane_a:conservative_zero_bid_pf_0.85_below_1_3", "lane_a:conservative_zero_bid_unpriced_11", "lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", "paper_shadow_fill_evidence_pending"]`.

## Oracle Ceiling

- Status: `not_available_replay_gap`.
- V1 does not synthesize maximum possible P&L from midpoint, daily, stale, or display marks.

## Next Evidence Queue

| Priority | Source | Action | Count | Reason |
|---:|---|---|---:|---|
| 1 | suggested_trade_review_plan | `execute_suggested_trade_review_plan` | 1 | suggested_trade_attention_rows_need_fresh_explicit_review |
| 2 | candidate_outcome_ledger | `collect_exact_exit_evidence` | 1 | collect_exact_exit_evidence |
| 4 | lane_disposition | `collect_paper_shadow_exact_evidence` | 1 | profitable_but_not_promotable_lane_needs_fresh_exact_paper_evidence |
| 4 | candidate_outcome_ledger | `create_or_link_paper_review_row` | 5 | create_or_link_paper_review_row |
| 5 | candidate_outcome_ledger | `capture_paper_only_exact_entry` | 8 | capture_paper_only_exact_entry |
| 5 | lane_disposition | `retest_lane` | 3 | lane_economics_are_not_profitable_but_not_sufficiently_severe_for_archive |
| 7 | fill_attempt_evidence_capture_plan | `execute_fill_attempt_evidence_capture_plan` | 4 | fresh_candidates_need_durable_fill_attempt_evidence |
| 9 | candidate_outcome_ledger | `wait_for_fresh_executable_tier_a_bridge` | 21 | wait_for_fresh_executable_tier_a_bridge |
| 10 | candidate_outcome_ledger | `repair_historical_evidence` | 39 | repair_historical_evidence |
| 11 | candidate_outcome_ledger | `respect_guardrail_or_lane_mismatch` | 9 | respect_guardrail_or_lane_mismatch |

## Promotion Gate

- Status: `blocked`.
- Promotion ready: `False`.
- Blockers: `["bullish_pullback_core:unpriced_candidates_3", "current_policy_circuit_breaker_active", "entry_filter_walkforward_not_passed", "fresh_exact_paper_rows_still_collecting", "lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", "lane_a:conservative_zero_bid_pf_0.85_below_1_3", "lane_a:conservative_zero_bid_unpriced_11", "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch", "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "multilane:bullish_pullback_core:unpriced_candidates_3", "multilane:lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", "multilane:lane_a:conservative_zero_bid_pf_0.85_below_1_3", "multilane:lane_a:conservative_zero_bid_unpriced_11", "multilane:lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "multilane:lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch", "multilane:lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "multilane:paper_shadow_fill_evidence_pending", "no_exact_realized_pnl_rows", "no_live_validation_lanes", "paper_monitor_not_passed", "paper_shadow_fill_evidence_pending", "point_in_time_replay_not_passed", "profitability_layer_stack_blocked_or_collecting"]`.

## Boundary

This command center is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote paper/research/backfill evidence.

