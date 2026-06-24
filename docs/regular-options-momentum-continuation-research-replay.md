# Regular Options Momentum Continuation Research Replay

This report is generated from `scripts/build_regular_options_momentum_continuation_research_replay.py`. It implements the operator-approved research-only replay harness for the preregistered momentum-continuation call-debit-spread concept. It writes derived research artifacts only; it does not enable live validation, auto-track, broker orders, quote import, evidence-store mutation, protected-holdout consumption, scanner release, stop/sizing/proof-bar changes, or promotion.

## Summary

- Status: `implemented_research_replay_no_proof_qualified_rows`.
- Concept: `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`.
- Research harness implemented: `true`.
- Historical replay performed: `true`.
- Accepted profitability: `false`.
- Forward strict completed rows: `0` / `30`.
- Denominator rows: `1291`.
- Proof-qualified rows: `0`.
- Diagnostic priced rows: `896`.

## Proof Formula

- `entry_debit`: long_call_ask - short_call_bid.
- `exit_value`: long_call_bid - short_call_ask.
- `net_pnl_usd`: (exit_value - entry_debit) * 100 - fees_and_slippage.
- `important_boundary`: existing imported spread marks and midpoint-like marks may be diagnostic, but are not counted as proof unless explicit side-aware OPRA/NBBO bid/ask legs are present.

## Proof Metrics

- Proof metrics: `{"avg_pnl_usd": null, "gross_loss_usd": 0, "gross_win_usd": 0, "loss_count": 0, "net_pnl_usd": null, "priced_row_count": 0, "profit_factor": null, "row_count": 0, "win_count": 0, "win_rate_pct": null}`.
- Diagnostic-only metrics: `{"avg_pnl_usd": -65.68, "gross_loss_usd": 239470.75, "gross_win_usd": 180623.09, "loss_count": 427, "net_pnl_usd": -58847.66, "priced_row_count": 896, "profit_factor": 0.7543, "row_count": 896, "win_count": 469, "win_rate_pct": 52.34}`.
- Diagnostic-only boundary: Existing imported spread marks and midpoint-basis rows are shown to audit what old artifacts imply, but they are not accepted as proof for this preregistered design without explicit side-aware entry and exit OPRA/NBBO bid/ask leg evidence plus point-in-time VIX and breadth inputs.

## Denominator Status Counts

| Status | Rows |
| --- | ---: |
| `duplicate_within_research_harness` | 461 |
| `missing_point_in_time_vix_bucket` | 415 |
| `rejected_not_call_debit_spread` | 237 |
| `rejected_outside_preregistered_universe` | 178 |

## Top Blockers

| Reason | Rows |
| --- | ---: |
| `missing_point_in_time_breadth_confirmation` | 1291 |
| `missing_point_in_time_vix_bucket` | 1291 |
| `missing_side_aware_exit_bid_ask` | 1291 |
| `missing_point_in_time_qqq_momentum_confirmation` | 1080 |
| `spread_diagnostics_marked_diagnostic_only` | 1064 |
| `entry_contains_mid_quote_basis` | 896 |
| `duplicate_within_research_harness` | 461 |
| `missing_net_usd_pnl` | 395 |
| `missing_point_in_time_spy_momentum_confirmation` | 395 |
| `rejected_not_call_debit_spread` | 290 |
| `rejected_outside_preregistered_universe` | 277 |
| `missing_side_aware_entry_bid_ask` | 227 |

## Run Compatibility

| Run | Variant | Trusted | Exact | Strict New | PF | Stress PF | Coverage |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `data/options-validation/runs/20260614_145612_sleeve_next_index_refill_v1_intraday.json` | `sleeve_next_index_refill_v1` | `true` | 116 | 6 | 1.74 | 1.33 | 100.0 |
| `data/options-validation/runs/20260614_145651_sleeve_next_index_move_bucket_baseline_v1_intraday.json` | `sleeve_next_index_move_bucket_baseline_v1` | `true` | 4 | 3 | 1.7 | 0.87 | 100.0 |
| `data/options-validation/runs/20260614_145732_sleeve_next_index_move_bucket_coverage_v1_intraday.json` | `sleeve_next_index_move_bucket_coverage_v1` | `true` | 3 | 3 | 0.0 | 0.0 | 75.0 |
| `data/options-validation/runs/20260614_145823_sleeve_next_index_with_iwm_spy_control_v1_intraday.json` | `sleeve_next_index_with_iwm_spy_control_v1` | `true` | 14 | 4 | 2.7 | 1.88 | 73.7 |
| `data/options-validation/runs/20260614_145859_sleeve_ticker_iwm_intraday.json` | `sleeve_ticker_iwm` | `true` | 21 | 10 | 3.08 | 2.02 | 75.0 |
| `data/options-validation/runs/20260614_150712_sleeve_next_high_beta_survival_v1_intraday.json` | `sleeve_next_high_beta_survival_v1` | `true` | 16 | 16 | 0.11 | 0.07 | 100.0 |
| `data/options-validation/runs/20260614_150818_sleeve_next_high_beta_momentum_fast_v1_intraday.json` | `sleeve_next_high_beta_momentum_fast_v1` | `true` | 46 | 46 | 0.26 | 0.18 | 79.3 |
| `data/options-validation/runs/20260614_150854_sleeve_next_high_beta_put_riskoff_v1_intraday.json` | `sleeve_next_high_beta_put_riskoff_v1` | `true` | 0 | 0 | 0.0 | 0.0 | 0.0 |
| `data/options-validation/runs/20260614_151123_sleeve_next_move_bucket_refill_v1_intraday.json` | `sleeve_next_move_bucket_refill_v1` | `true` | 153 | 23 | 1.27 | 0.96 | 100.0 |
| `data/options-validation/runs/20260614_151325_bearish_index_put_observation_chain_native_timeexit_all_sleeves_intraday.json` | `bearish_index_put_observation_chain_native_timeexit_all_sleeves` | `true` | 23 | 23 | 0.37 | 0.27 | 26.4 |
| `data/options-validation/runs/20260614_151836_iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves_intraday.json` | `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves` | `true` | 30 | 19 | 1.38 | 0.97 | 69.8 |
| `data/options-validation/runs/20260614_151909_iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves_intraday.json` | `iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves` | `true` | 2 | 2 | 0.0 | 0.0 | 4.7 |
| `data/options-validation/runs/20260614_152342_smh_semiconductor_call_chain_native_timeexit_all_sleeves_intraday.json` | `smh_semiconductor_call_chain_native_timeexit_all_sleeves` | `true` | 17 | 17 | 0.4 | 0.27 | 100.0 |
| `data/options-validation/runs/20260614_152519_tracked_winner_chain_native_qqq_time65_all_sleeves_intraday.json` | `tracked_winner_chain_native_qqq_time65_all_sleeves` | `true` | 148 | 148 | 0.68 | 0.46 | 73.3 |
| `data/options-validation/runs/20260614_152659_tracked_winner_chain_native_no_spy_time65_all_sleeves_intraday.json` | `tracked_winner_chain_native_no_spy_time65_all_sleeves` | `true` | 82 | 82 | 1.05 | 0.71 | 79.6 |
| `data/options-validation/runs/20260614_152741_tracked_winner_chain_native_googl_nvda_time65_all_sleeves_intraday.json` | `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` | `true` | 58 | 58 | 0.98 | 0.7 | 82.9 |
| `data/options-validation/runs/20260614_152922_tracked_winner_cheap_debit_continuity_v1_intraday.json` | `tracked_winner_cheap_debit_continuity_v1` | `true` | 130 | 130 | 0.85 | 0.59 | 69.9 |
| `data/options-validation/runs/20260614_153136_regular_bearish_put_index_narrow_timeexit_all_sleeves_intraday.json` | `regular_bearish_put_index_narrow_timeexit_all_sleeves` | `true` | 33 | 33 | 0.28 | 0.2 | 23.2 |

## Next Oracle Question

Given the approved research-only harness results, choose the next concrete repo task that can move from 0 proof-qualified momentum-continuation rows toward 30 profitable strict forward-audit rows. Prefer a falsifiable implementation or data-surface repair path that preserves the listed prohibitions. If this concept is blocked, pivot to the next materially different option edge family rather than stopping.

## Forbidden Actions

- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_release_scanner`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_profitability_proof`
- `do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof`
