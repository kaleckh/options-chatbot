# Regular Options Multi-Lane Portfolio - 2026-05-30

This report stacks regular stock-options lane evidence without using the AI commodity, crypto, Polymarket, or day-trading lanes.
Only trusted intraday OPRA/NBBO exact rows are counted in the proof portfolio. Count success is separated from clean promotion and production readiness.

## Count Target Passed, Quality Pending

- Exact trades after dedupe: `234`.
- Gap to `200`: `0`.
- Count gate: `passed`.
- Overall quality gate: `quality_pending`.
- Read: this is not `200 good trades`; it is `200+` count-feasible trusted-intraday rows with unresolved quality blockers.

## Combined Count Stack

- PF: `2.16`.
- Avg PnL: `26.76%`.
- Win rate: `62.4%`.
- Suppressed duplicate exact trades: `51` across `51` duplicate groups.
- By lane: `{"bullish_pullback_core": 130, "lane_a_chain_native_ret20_4_stop200_time75": 104}`.

## 200 Quality Gate

- Overall: `quality_pending`.
- Count: `passed`.
- Coverage: `blocked`.
- Robustness: `blocked`.
- Lane A zero-bid: `blocked`.
- Paper shadow: `pending`.
- Blockers: `["bullish_pullback_core:unpriced_candidates_3", "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5", "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137", "lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch", "lane_a:conservative_zero_bid_pf_0.85_below_1_3", "lane_a:conservative_zero_bid_unpriced_11", "lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", "paper_shadow_fill_evidence_pending"]`.

## Lane A Side-Aware Zero-Bid Replay

- Artifact: `data\profitability-lab\side-aware-zero-bid\latest_lane_a_side_aware_zero_bid.json`.
- Conservative zero-bid mode priced `126` of `127` missing-exit candidates; `118` priced rows used at least one zero-bid exit quote.
- Conservative side-aware rows alone: PF `0.11`, avg `-66.59%`, win rate `16.7%`.
- Conservative combined Lane A: `281` priced, `11` unpriced, coverage `96.2%`, zero-bid exit rate `41.99%`, PF `0.85`, avg `-6.51%`.
- Midpoint zero-bid combined Lane A is still weak: PF `1.11`, avg `3.79%`.
- Read: the missing Lane A exits are mostly adverse zero-bid short-leg states, so the quality blocker is economic, not just a missing-import artifact.

## Lane Read

| Lane | Status | Proof grade | Exact | Candidates | Coverage | PF | Avg % | Portfolio exact | Main blockers |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| bullish_pullback_core | count_candidate | trusted_intraday_opra_nbbo | 130 | 133 | 97.7 | 2.04 | 24.54 | 130 | unpriced_candidates_remain |
| lane_a_chain_native_ret20_4_stop200_time75 | count_candidate | trusted_intraday_opra_nbbo | 155 | 292 | 53.1 | 3.59 | 42.34 | 155 | quote_coverage_below_97_5, unpriced_candidates_remain, rolling_oos_not_clean |
| bullish_pullback_clean_exact_reference | intraday_scout | trusted_intraday_opra_nbbo | 129 | 129 | 100.0 | 2.2 | 28.97 | 0 |  |
| iwm_small_cap_risk | intraday_scout | trusted_intraday_opra_nbbo | 11 | 15 | 73.3 | 2.47 | 22.44 | 0 | thin_exact_sample, quote_coverage_below_97_5, unpriced_candidates_remain |
| etf_index_pullback_control | intraday_scout | trusted_intraday_opra_nbbo | 4 | 4 | 100.0 | 1.7 | 8.16 | 0 | thin_exact_sample, pf_below_1_75 |
| high_beta_momentum_volatility | intraday_scout | trusted_intraday_opra_nbbo | 44 | 56 | 78.6 | 0.2 | -35.37 | 0 | pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5, unpriced_candidates_remain |
| high_beta_put_riskoff | blocked_or_empty | trusted_intraday_opra_nbbo | 0 | 0 | 0.0 | 0.0 | 0.0 | 0 | no_exact_priced_trades, thin_exact_sample, pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5 |
| regular_bearish_index_riskoff | blocked_or_empty | trusted_intraday_opra_nbbo | 0 | 0 | 0.0 | 0.0 | 0.0 | 0 | no_exact_priced_trades, thin_exact_sample, pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5 |
| regular_bearish_put_primary_timeexit_probe | intraday_scout | trusted_intraday_opra_nbbo | 73 | 78 | 93.6 | 0.21 | -43.72 | 0 | pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5, unpriced_candidates_remain |
| range_breakout_call_timeexit_probe | intraday_scout | trusted_intraday_opra_nbbo | 14 | 21 | 66.7 | 0.39 | -24.19 | 0 | thin_exact_sample, pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5, unpriced_candidates_remain |
| volatility_expansion_call_timeexit_probe | intraday_scout | trusted_intraday_opra_nbbo | 48 | 58 | 82.8 | 0.6 | -12.05 | 0 | pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5, unpriced_candidates_remain |
| tracked_winner_chain_native_qqq_time80_intraday | intraday_scout | trusted_intraday_opra_nbbo | 118 | 215 | 54.9 | 1.49 | 12.42 | 0 | pf_below_1_75, quote_coverage_below_97_5, unpriced_candidates_remain |
| tracked_winner_chain_native_research | daily_research_only | exact_daily_research | 103 | 177 | 58.2 | 2.04 | 19.17 | 0 | not_trusted_intraday_opra_nbbo, quote_coverage_below_97_5, unpriced_candidates_remain |
| bearish_index_put_observation | daily_research_only | exact_daily_research | 11 | 37 | 100.0 | 1.2 | 5.6 | 0 | not_trusted_intraday_opra_nbbo, thin_exact_sample, pf_below_1_75 |
| range_breakout_observation | daily_research_only | exact_daily_research | 2 | 23 | 95.7 | 101.69 | 50.84 | 0 | not_trusted_intraday_opra_nbbo, thin_exact_sample, quote_coverage_below_97_5, unpriced_candidates_remain |
| volatility_expansion_observation | daily_research_only | exact_daily_research | 18 | 95 | 90.5 | 0.92 | -1.72 | 0 | not_trusted_intraday_opra_nbbo, thin_exact_sample, pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5, unpriced_candidates_remain |
| bullish_mean_reversion | daily_research_only | exact_daily_research | 0 | 0 | 0.0 | 0.0 | 0.0 | 0 | not_trusted_intraday_opra_nbbo, no_exact_priced_trades, thin_exact_sample, pf_below_1_75, avg_pnl_not_positive, quote_coverage_below_97_5 |

## Blocked Specs

- `fill_discipline`: `partial_current_paper_result`; blockers: `no_spread_ask_bid_entry_fills_logged`.
- `liquidity_first_spread`: `blocked_instrumentation`; blockers: `instrumentation_blocked`.
- `high_debit_control`: `scored`; blockers: `none`.
- `gld_macro_breakout`: `blocked_missing_data`; blockers: `missing_required_underlyings, thin_required_history`.
- `relative_strength_pullback`: `pending_forward_paper_log`; blockers: `paper_log_pending`.
- `tlt_duration_shock`: `blocked_missing_data`; blockers: `missing_required_underlyings, thin_required_history`.
- `volatility_compression_breakout`: `pending_forward_paper_log`; blockers: `paper_log_pending`.
- `bull_put_credit_spread`: `pending_forward_paper_log`; blockers: `structure_instrumentation_pending`.
- `post_event_vol_crush`: `blocked_instrumentation`; blockers: `event_data_blocked`.
- `iron_condor_range`: `pending_forward_paper_log`; blockers: `structure_instrumentation_pending`.
- `market_neutral_premium_control`: `pending_forward_paper_log`; blockers: `structure_instrumentation_pending`.
- `no_trade_opportunity_cost`: `blocked_instrumentation`; blockers: `instrumentation_blocked`.
- `random_approved_control`: `blocked_instrumentation`; blockers: `instrumentation_blocked`.
- `inverse_signal_bearish_control`: `blocked_instrumentation`; blockers: `instrumentation_blocked`.
- `risk_budget_sizing`: `pending_forward_paper_log`; blockers: `portfolio_sim_pending`.
- `mechanical_profit_harvest`: `pending_forward_paper_log`; blockers: `exit_sim_pending`.
- `quote_deterioration_stop`: `pending_forward_paper_log`; blockers: `exit_sim_pending`.
- `portfolio_throttle`: `pending_forward_paper_log`; blockers: `portfolio_sim_pending`.
- `sector_rotation_confirmation`: `pending_forward_paper_log`; blockers: `paper_log_pending`.
- `earnings_premium_avoidance`: `blocked_instrumentation`; blockers: `event_data_blocked`.
- `rsi_trend_reclaim`: `pending_forward_paper_log`; blockers: `paper_log_pending`.
- `breadth_gated_index`: `blocked_instrumentation`; blockers: `breadth_data_blocked`.
- `monday_gap_fade`: `blocked_instrumentation`; blockers: `intraday_data_blocked`.
- `opex_pin_risk`: `blocked_instrumentation`; blockers: `intraday_data_blocked`.
- `calendar_volatility`: `pending_forward_paper_log`; blockers: `structure_instrumentation_pending`.
- `pmcc_diagonal`: `pending_forward_paper_log`; blockers: `structure_instrumentation_pending`.
- `xle_energy_inflation`: `blocked_missing_data`; blockers: `missing_required_underlyings, thin_required_history`.
- `xlf_financials`: `blocked_missing_data`; blockers: `missing_required_underlyings, thin_required_history`.
- `smh_semiconductor`: `blocked_missing_data`; blockers: `missing_required_underlyings, thin_required_history`.

## Read

The refreshed stock-lane stack clears the `200` exact-trade target on strict date+ticker+direction dedupe by combining the current bullish-pullback core with the older Lane A chain-native extension.

The count is not permission to stop. Lane A improved after exact and lookahead fills, but the side-aware zero-bid replay shows the missing exits are mostly adverse short-leg liquidity states, not harmless missing imports. A contrarian tracked-winner intraday rerun adds a visible 102-exact-trade scout, but its current trusted-intraday economics are below gate at PF `1.36` with `51.8%` coverage, so it is not counted toward the proof portfolio. The bearish, range, and volatility probes have now been rerun on trusted intraday data and rejected on profitability.

## Next Actions

- Treat the current combined proof count as the honest starting point, not a production-ready annual capacity estimate.
- Do not add daily/EOD research artifacts to the proof count until they are rerun on trusted intraday OPRA/NBBO.
- Do not chase 300 until the current 200+ stack clears the quality gate: coverage, robustness, and paper-shadow fills.
- Use the side-aware zero-bid replay to decide whether Lane A can be made clean or must be reframed; zero-bid short-leg exits are economic losses, not harmless import gaps.
- Keep the tracked-winner intraday rerun visible as a rejected count-expansion scout unless a new causal/contract-selection version clears PF and coverage gates.
- Implement or rerun truly separate regular stock lanes only after the current 200+ stack is quality-gated.
- Do not promote bearish put, range-breakout, or volatility-expansion probes until they show positive PF on exact intraday evidence.
