# Regular Options Symbol Sleeves

This report is generated from `scripts/build_regular_options_symbol_sleeves.py`. It is a per-symbol audit/reporting layer under existing regular supervised options lanes, not a ticker-specific strategy-tuning surface.

## Summary

- Tracked symbols found: `60`.
- Symbol-lane rows: `343`.
- Classification counts: `{"keep": 25, "needs-paper": 86, "quarantine": 91, "rejected": 82, "watch": 59}`.
- N-floor disposition counts: `{"insufficient_n_frozen": 336, "quarantine": 3, "watch": 4}`.
- Evidence classes: `{"blocked_no_data": 9, "daily_eod_research_only": 10, "mark_or_stale_review": 2, "trusted_intraday_opra_nbbo_exact": 257, "trusted_intraday_unresolved": 65}`.
- Bullish Pullback carrier symbols: `AAPL, COP, CVX, GOOGL, IWM, JNJ, LLY, NEM, UNH, XOM`.
- Queue removals are recommendations only: `True`.
- Per-ticker queue-change floor: `30` exact trades; rows below that carry `insufficient_n_frozen` in `n_floor_disposition` while legacy `status` stays visible.

## Proof Policy

- Strict proof claims require exact trusted intraday OPRA/NBBO contract rows with executable bid/ask evidence.
- Daily/EOD, research backfill, stale/display marks, unresolved candidates, midpoint-only, and last-trade rows remain non-production proof.
- Executable exit P&L is kept separate from paper/mark P&L in the open-risk readback.
- Per-symbol expectancy diagnostics shrink raw ticker average P&L toward the lane mean through `expectancy_calibration.py`; use the shrunk fields for new per-ticker research readbacks.
- Migration note: legacy `status` and ticker-audit `decision` fields are preserved. New keep/remove-style queue emission must use `n_floor_disposition` and `queue_change_allowed_by_n_floor`.

## Best Rows

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| GOOGL | tracked_winner_cheap_debit_continuity_v1 | watch | watch | False | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.15 | 31.4 | 28.45 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | watch | watch | False | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.1 | 30.57 | 27.58 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time80_intraday | watch | watch | False | trusted_intraday_opra_nbbo_exact | 34 | 42 | 8 | 80.95 | 7.4 | 51.31 | 46.32 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_liquidity_first_contract_hygiene_v1 | watch | watch | False | trusted_intraday_opra_nbbo_exact | 32 | 36 | 4 | 88.89 | 1.63 | 10.84 | 8.79 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | 10.21 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| WMT | bullish_pullback_core | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 19 | 21 | 2 | 90.48 | 1.02 | 0.35 | 5.39 | quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 2.96 | 39.78 | 33.29 | quote_coverage_below_97_5, unresolved_rows_remain |
| JNJ | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 1.63 | 13.72 | 12.9 | quote_coverage_below_97_5, unresolved_rows_remain |
| WMT | sleeve_next_move_bucket_refill_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 21 | 3 | 85.71 | 1.1 | 2.01 | 6.6 | quote_coverage_below_97_5, unresolved_rows_remain |
| NEM | bullish_pullback_clean_exact_reference | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 16 | 16 | 0 | 100.0 | 13.37 | 84.03 | 70.92 | positive_exact_intraday_symbol_lane |
| NEM | bullish_pullback_core | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | 69.53 | positive_exact_intraday_symbol_lane |
| NEM | sleeve_next_defensive_refill_v1 | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | 69.9 | positive_exact_intraday_symbol_lane |

## Worst Rows

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| DIS | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -101.08 | -8.57 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| SMCI | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -101.08 | -42.71 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| IWM | iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -100.46 | -100.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 3 | 2 | 33.33 | 0.0 | -100.45 | 18.54 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| COIN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.38 | 18.55 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | -8.45 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| JPM | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.33 | 18.56 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| XLK | bullish_pullback_clean_exact_reference | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.28 | 7.43 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| AMD | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.28 | -42.57 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| COIN | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | -8.43 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| NVDA | regular_bearish_put_primary_timeexit_probe | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -99.99 | -59.8 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| META | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -99.3 | -76.14 | adequate_negative_exact_intraday_evidence, sample_status:thin |

## Bullish Pullback

- Keep queue: `IWM, AAPL, GOOGL, UNH, LLY, JNJ, XOM, CVX, COP, NEM`.
- Move to frozen hypotheses: `QQQ, DIA, XLK, NVDA, AMZN, TSLA, WMT, PM, CAT, PLD`.
- Remove recommendations: `ABBV, BAC, C, COIN, FCX, JPM, PLTR, RTX, SLB`.
- Insufficient-N frozen: `AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA, BAC, C, CAT, CLF, COIN, COP, COST, CVX, DE, DIA, DIS, EQR, FCX, GOOGL, GS, IWM, JNJ, JPM, KO, LIN, LLY, LMT, MCD, META, MSFT, MSTR, NEM, NFLX, NKE, NVDA, OXY, PFE, PG, PLD, PLTR, PM, QQQ, RTX, SBUX, SLB, SMCI, SPG, SPY, T, TSLA, UNH, V, WELL, WMT, XLK, XOM`.
- Queue-change allowed by N floor: `none`.

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| GOOGL | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 2.96 | 39.78 | 33.29 | quote_coverage_below_97_5, unresolved_rows_remain |
| JNJ | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 1.63 | 13.72 | 12.9 | quote_coverage_below_97_5, unresolved_rows_remain |
| NEM | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 16 | 1 | 93.75 | 12.46 | 68.81 | 54.09 | quote_coverage_below_97_5, unresolved_rows_remain |
| AAPL | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 13 | 2 | 84.62 | 273.54 | 24.87 | 20.2 | quote_coverage_below_97_5, unresolved_rows_remain |
| IWM | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | 18.53 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| COP | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 9 | 9 | 0 | 100.0 | 76.14 | 66.87 | 46.53 | sample_status:thin |
| LLY | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 9 | 10 | 1 | 90.0 | 2.89 | 37.97 | 27.96 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| CVX | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 8 | 8 | 0 | 100.0 | 468.56 | 58.57 | 39.86 | sample_status:thin |
| UNH | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 8 | 10 | 2 | 80.0 | 2.08 | 29.86 | 22.19 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| XOM | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 210.66 | 52.66 | 28.92 | sample_status:thin |
| AMT | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| CLF | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| COST | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| DE | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| EQR | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| GS | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| LIN | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| LMT | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| MCD | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| MSFT | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| MSTR | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| PFE | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| PG | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SPG | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| SPY | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | mark_or_stale_review | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:mark_or_stale_review, sample_status:none, trading_desk_guardrail_negative_concentration |
| V | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NVDA | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 7 | 2 | 71.43 | 0.15 | -38.21 | -14.14 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| JPM | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.06 | -34.13 | -9.65 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| QQQ | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 3 | 3 | 0 | 100.0 | 2.69 | 26.09 | 15.99 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| XLK | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 3 | 1 | 66.67 | 56.94 | 28.47 | 15.23 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| COIN | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | -8.43 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| DIA | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 11.95 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -65.13 | -2.58 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| ABBV | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 10 | 14 | 4 | 71.43 | 0.63 | -6.65 | -1.12 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| PLTR | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 0.36 | -17.38 | -8.28 | bullish_pullback_remove_negative_exact_evidence |
| BAC | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 8 | 12 | 4 | 66.67 | 0.63 | -7.99 | -1.1 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| C | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 8 | 10 | 2 | 80.0 | 0.47 | -14.19 | -4.91 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| FCX | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 12 | 5 | 58.33 | 0.0 | -67.61 | -35.3 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| RTX | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 12 | 6 | 50.0 | 0.79 | -2.94 | 2.91 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| SLB | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 19 | 13 | 31.58 | 0.23 | -46.51 | -20.86 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| TSLA | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 8 | 2 | 75.0 | 0.26 | -35.83 | -15.03 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| AMZN | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 9 | 5 | 44.44 | 0.03 | -48.1 | -15.86 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AA | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -63.48 | -11.04 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| META | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -83.99 | -16.9 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | -8.45 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| BA | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -96.5 | -7.81 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| DIS | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -101.08 | -8.57 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| NKE | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -76.66 | -4.5 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| SBUX | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -18.82 | 5.14 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| WMT | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 20 | 9 | 55.0 | 1.75 | 13.37 | 12.29 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| OXY | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 1.07 | 2.08 | 5.65 | sample_status:thin |
| PLD | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 5 | 1 | 80.0 | 3.77 | 9.37 | 9.68 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| PM | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 7 | 3 | 57.14 | 205.02 | 51.25 | 28.29 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| CAT | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 3 | 10 | 7 | 30.0 | 116.08 | 38.69 | 20.71 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| ARM | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 28.18 | 14.09 | 11.12 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| KO | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 6 | 4 | 33.33 | 19.14 | 9.57 | 9.83 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| T | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 3.62 | 1.28 | 7.46 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| WELL | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 8 | 7 | 12.5 | 27.51 | 27.51 | 12.86 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |

## Bullish / High-Beta

High-beta upside is treated as a question, not an assumption. Rows below are exact-option evidence first; priced-only or zero-bid-damaged rows should not be called crushers.

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| AMD | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | -8.45 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | 42.34 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| AMD | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.28 | -42.57 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 9 | 5 | 44.44 | 0.03 | -48.1 | -15.86 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | high_beta_momentum_volatility | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.03 | -49.22 | -45.76 | adequate_negative_exact_intraday_evidence |
| AMZN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 7 | 6 | 14.29 | 0.8 | 0.8 | 35.42 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| AMZN | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -82.72 | -64.99 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| AMZN | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -96.23 | -69.06 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| AMZN | sleeve_next_high_beta_momentum_fast_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.03 | -49.22 | -45.76 | adequate_negative_exact_intraday_evidence |
| AMZN | sleeve_next_high_beta_survival_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.03 | -40.77 | -42.73 | sample_status:thin |
| ARM | bullish_pullback_observation | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 28.18 | 14.09 | 11.12 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| ARM | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | 42.34 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| ARM | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 6 | 6 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| ARM | relative_strength_pullback_ex_clean_universe_v1 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | -31.03 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| COIN | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | -8.43 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| COIN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.38 | 18.55 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| COIN | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 11 | 11 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -83.99 | -16.9 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| META | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 42.34 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -99.3 | -76.14 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| META | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -28.25 | -30.24 | sample_status:thin |
| MSTR | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:blocked_no_data, sample_status:none |
| MSTR | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NFLX | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -65.13 | -2.58 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 10 | 3 | 70.0 | 0.08 | -34.37 | -2.41 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NVDA | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 7 | 2 | 71.43 | 0.15 | -38.21 | -14.14 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | high_beta_momentum_volatility | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.15 | -47.28 | -44.15 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| NVDA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 3 | 2 | 33.33 | 0.0 | -100.45 | 18.54 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | regular_bearish_put_primary_timeexit_probe | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -99.99 | -59.8 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | relative_strength_pullback_ex_clean_universe_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 5 | 0 | 100.0 | 0.0 | -85.2 | -58.11 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | sleeve_next_high_beta_momentum_fast_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.15 | -47.28 | -44.15 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| NVDA | sleeve_next_high_beta_survival_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -65.14 | -55.67 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.34 | 6.75 | 9.63 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 1.33 | 7.1 | 9.69 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 30 | 15 | 50.0 | 1.34 | 6.75 | 6.73 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time80_intraday | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 0.85 | -3.15 | 0.95 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 31 | 18 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| NVDA | tracked_winner_chain_native_research_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 31 | 17 | 45.16 | 0.85 | -3.15 | 0.72 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_cheap_debit_continuity_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.33 | 6.71 | 6.98 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 30 | 8 | 73.33 | 0.37 | -29.41 | -24.77 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| PLTR | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 0.36 | -17.38 | -8.28 | bullish_pullback_remove_negative_exact_evidence |
| PLTR | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 9 | 3 | 66.67 | 0.75 | -16.72 | 10.13 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| PLTR | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| PLTR | relative_strength_pullback_ex_clean_universe_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 11.83 | 11.83 | -23.89 | positive_but_thin_or_incomplete, sample_status:thin |
| SMCI | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | 42.34 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -101.08 | -42.71 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| TSLA | bullish_pullback_observation | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 8 | 2 | 75.0 | 0.26 | -35.83 | -15.03 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| TSLA | high_beta_momentum_volatility | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 27 | 12 | 55.56 | 0.62 | -10.4 | -16.64 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| TSLA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 5 | 1 | 80.0 | 0.56 | -32.83 | 8.93 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| TSLA | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| TSLA | relative_strength_pullback_ex_clean_universe_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.0 | -67.67 | -47.31 | sample_status:thin |
| TSLA | sleeve_next_high_beta_momentum_fast_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 27 | 12 | 55.56 | 0.62 | -10.4 | -16.64 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| TSLA | sleeve_next_high_beta_survival_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.34 | -25.82 | -34.22 | adequate_negative_exact_intraday_evidence, sample_status:thin |

## Tracked Winner

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| DIA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 36 | 14 | 61.11 | 1.67 | 7.64 | 9.37 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 26 | 34 | 8 | 76.47 | 1.02 | 0.32 | 1.35 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time80_intraday | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 25 | 43 | 18 | 58.14 | 1.0 | -0.07 | 2.01 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 53 | 18 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| DIA | tracked_winner_chain_native_research_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 24 | 42 | 18 | 57.14 | 0.96 | -0.79 | 1.34 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | 10.21 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 23 | 33 | 10 | 69.7 | 0.69 | -6.03 | -5.73 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| GOOGL | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | quarantine | True | trusted_intraday_opra_nbbo_exact | 34 | 41 | 7 | 82.93 | 2.3 | 23.35 | 22.7 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | quarantine | True | trusted_intraday_opra_nbbo_exact | 34 | 41 | 7 | 82.93 | 2.8 | 27.05 | 25.76 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | watch | watch | False | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.1 | 30.57 | 27.58 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time80_intraday | watch | watch | False | trusted_intraday_opra_nbbo_exact | 34 | 42 | 8 | 80.95 | 7.4 | 51.31 | 46.32 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 41 | 10 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| GOOGL | tracked_winner_chain_native_research_all_sleeves | quarantine | quarantine | True | trusted_intraday_opra_nbbo_exact | 33 | 40 | 7 | 82.5 | 6.85 | 48.33 | 43.49 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_cheap_debit_continuity_v1 | watch | watch | False | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.15 | 31.4 | 28.45 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_liquidity_first_contract_hygiene_v1 | watch | watch | False | trusted_intraday_opra_nbbo_exact | 32 | 36 | 4 | 88.89 | 1.63 | 10.84 | 8.79 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.34 | 6.75 | 9.63 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 1.33 | 7.1 | 9.69 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 30 | 15 | 50.0 | 1.34 | 6.75 | 6.73 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time80_intraday | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 0.85 | -3.15 | 0.95 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 31 | 18 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| NVDA | tracked_winner_chain_native_research_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 31 | 17 | 45.16 | 0.85 | -3.15 | 0.72 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_cheap_debit_continuity_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.33 | 6.71 | 6.98 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 30 | 8 | 73.33 | 0.37 | -29.41 | -24.77 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 47 | 25 | 46.81 | 1.37 | 7.21 | 7.11 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_chain_native_qqq_time80_intraday | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 25 | 51 | 26 | 49.02 | 1.13 | 5.17 | 6.38 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_cheap_debit_continuity_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 19 | 48 | 29 | 39.58 | 0.81 | -6.01 | -3.13 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_liquidity_first_contract_hygiene_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 37 | 22 | 40.54 | 1.02 | 0.58 | -0.66 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| SPY | tracked_winner_chain_native_qqq_time65_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 16 | 45 | 29 | 35.56 | 0.24 | -36.02 | -25.85 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time80_intraday | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 20 | 49 | 29 | 40.82 | 0.62 | -18.15 | -12.04 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 52 | 28 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | tracked_winner_chain_native_research_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 16 | 50 | 34 | 32.0 | 0.38 | -32.92 | -22.33 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| SPY | tracked_winner_cheap_debit_continuity_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 16 | 46 | 30 | 34.78 | 0.37 | -30.45 | -21.34 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 40 | 29 | 27.5 | 0.94 | -1.73 | -2.55 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |

## Sector / Index ETF

| Symbol | Lane | Status | N-Floor Label | Queue Emit | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Shrunk Avg % | Reason |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| AAPL | sleeve_next_index_refill_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 8 | 8 | 0 | 100.0 | 3.01 | 26.78 | 27.41 | positive_but_thin_or_incomplete, sample_status:thin |
| COP | sleeve_next_index_refill_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 623.17 | 89.02 | 63.77 | positive_but_thin_or_incomplete, sample_status:thin |
| CVX | sleeve_next_index_refill_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 6.01 | 100.9 | 60.63 | positive_but_thin_or_incomplete, sample_status:thin |
| DIA | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 11.95 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | etf_index_pullback_control | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 10.48 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 5 | 0 | 100.0 | 94.46 | 18.89 | 30.62 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| DIA | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 6 | 6 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| DIA | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -70.2 | -58.16 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_move_bucket_baseline_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 10.48 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_move_bucket_coverage_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 27.54 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_with_iwm_spy_control_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | 24.69 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 36 | 14 | 61.11 | 1.67 | 7.64 | 9.37 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 26 | 34 | 8 | 76.47 | 1.02 | 0.32 | 1.35 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time80_intraday | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 25 | 43 | 18 | 58.14 | 1.0 | -0.07 | 2.01 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_research | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 53 | 18 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| DIA | tracked_winner_chain_native_research_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 24 | 42 | 18 | 57.14 | 0.96 | -0.79 | 1.34 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | 10.21 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 23 | 33 | 10 | 69.7 | 0.69 | -6.03 | -5.73 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| GOOGL | sleeve_next_index_refill_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 19 | 19 | 0 | 100.0 | 0.67 | -13.82 | -5.02 | adequate_negative_exact_intraday_evidence |
| IWM | bullish_pullback_clean_exact_reference | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | 15.67 | trading_desk_guardrail_negative_concentration |
| IWM | bullish_pullback_core | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | 14.56 | trading_desk_guardrail_negative_concentration |
| IWM | bullish_pullback_observation | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | 18.53 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| IWM | iwm_small_cap_risk | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | 22.44 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| IWM | iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 18 | 18 | 0 | 100.0 | 1.25 | 6.23 | 6.23 | trading_desk_guardrail_negative_concentration |
| IWM | iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -100.46 | -100.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 13 | 6 | 53.85 | 633.89 | 90.56 | 70.47 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 9 | 9 | 0.0 | 0.0 | 0.0 | 8.32 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| IWM | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 9 | 9 | 0 | 100.0 | 0.53 | -26.78 | -32.83 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_defensive_refill_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | 14.94 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_index_refill_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | 15.53 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_index_with_iwm_spy_control_v1 | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 10 | 13 | 3 | 76.92 | 1.94 | 19.59 | 21.47 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_move_bucket_refill_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.93 | -1.71 | 4.83 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_reit_industrial_refill_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | 15.36 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_ticker_iwm | watch | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | 22.44 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| JNJ | sleeve_next_index_refill_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 20 | 21 | 1 | 95.24 | 0.72 | -10.23 | -2.5 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| KRE | sector_rotation_regular_etf_call_stack_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 2 | 6 | 4 | 33.33 | 0.0 | -97.28 | -50.91 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| LLY | sleeve_next_index_refill_v1 | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 3.18 | 39.34 | 35.7 | positive_exact_intraday_symbol_lane |
| NEM | sleeve_next_index_refill_v1 | keep | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | 70.49 | positive_exact_intraday_symbol_lane |
| QQQ | bearish_index_put_observation | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 19 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | bearish_index_put_observation_chain_native_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 24 | 24 | 0.0 | 0.0 | 0.0 | 2.71 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | bullish_pullback_core | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -50.9 | 11.97 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | bullish_pullback_observation | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 3 | 3 | 0 | 100.0 | 2.69 | 26.09 | 15.99 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | etf_index_pullback_control | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -46.35 | -0.93 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 123.13 | 123.13 | 55.81 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| QQQ | range_breakout_call_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 11 | 4 | 63.64 | 0.54 | -17.66 | -20.38 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| QQQ | range_breakout_observation | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 17 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | range_breakout_observation_chain_native_call_timeexit_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 11 | 4 | 63.64 | 0.97 | -0.47 | -8.23 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| QQQ | range_breakout_observation_chain_native_put_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | regular_bearish_put_index_narrow_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 3 | 12 | 9 | 25.0 | 4.03 | 17.86 | 11.9 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 3 | 12 | 9 | 25.0 | 4.03 | 17.86 | 11.9 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.22 | -31.6 | -34.63 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_move_bucket_baseline_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -46.35 | -0.93 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_move_bucket_coverage_v1 | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | 28.64 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | sleeve_next_index_refill_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -32.04 | 18.34 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_with_iwm_spy_control_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 71.33 | 71.33 | 32.91 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_move_bucket_refill_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -32.04 | 13.93 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 22 | 47 | 25 | 46.81 | 1.37 | 7.21 | 7.11 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_chain_native_qqq_time80_intraday | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 25 | 51 | 26 | 49.02 | 1.13 | 5.17 | 6.38 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_cheap_debit_continuity_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 19 | 48 | 29 | 39.58 | 0.81 | -6.01 | -3.13 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_liquidity_first_contract_hygiene_v1 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 15 | 37 | 22 | 40.54 | 1.02 | 0.58 | -0.66 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | volatility_expansion_call_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 26 | 30 | 4 | 86.67 | 0.71 | -8.3 | -8.9 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 66 | 4 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | volatility_expansion_observation_chain_native_call_fast35_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 23 | 32 | 9 | 71.88 | 0.22 | -13.56 | -14.55 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation_chain_native_call_timeexit_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 24 | 30 | 6 | 80.0 | 0.63 | -10.02 | -10.41 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation_chain_native_put_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 14 | 14 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMH | sector_rotation_regular_etf_call_stack_v1 | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 11 | 14 | 3 | 78.57 | 0.52 | -16.04 | -21.14 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| SMH | smh_semiconductor_call_chain_native_timeexit_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 17 | 20 | 3 | 85.0 | 0.49 | -15.45 | -15.45 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| SPY | bearish_index_put_observation | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 18 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | bearish_index_put_observation_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 15 | 14 | 6.67 | 2.71 | 2.71 | 2.71 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | bullish_pullback_observation | needs-paper | insufficient_n_frozen | False | mark_or_stale_review | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 9.93 | evidence_class:mark_or_stale_review, sample_status:none, trading_desk_guardrail_negative_concentration |
| SPY | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -72.47 | 23.21 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| SPY | range_breakout_call_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 10 | 3 | 70.0 | 0.24 | -30.71 | -27.99 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| SPY | range_breakout_observation | needs-paper | insufficient_n_frozen | False | daily_eod_research_only | 0 | 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | range_breakout_observation_chain_native_call_timeexit_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 7 | 9 | 2 | 77.78 | 0.1 | -37.7 | -29.95 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| SPY | range_breakout_observation_chain_native_put_timeexit_all_sleeves | needs-paper | insufficient_n_frozen | False | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SPY | regular_bearish_put_index_narrow_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 11 | 6 | 45.45 | 1.14 | 2.6 | 5.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | quarantine | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 5 | 11 | 6 | 45.45 | 1.14 | 2.6 | 5.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | regular_bearish_put_primary_timeexit_probe | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 13 | 13 | 0 | 100.0 | 0.77 | -6.87 | -17.11 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time65_all_sleeves | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 16 | 45 | 29 | 35.56 | 0.24 | -36.02 | -25.85 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time80_intraday | rejected | insufficient_n_frozen | False | trusted_intraday_opra_nbbo_exact | 20 | 49 | 29 | 40.82 | 0.62 | -18.15 | -12.04 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |

## Open Position And Suggested-Trade Risk

- Open-position summary: `{"avg_pnl_pct": 10.04, "median_pnl_pct": 13.7, "negative": 15, "positive_or_flat": 32, "priced_or_marked": 47, "rows": 48}`.
- Open-position actionable ids: `[104]`.
- Suggested-trade summary: `{"avg_pnl_pct": null, "median_pnl_pct": null, "negative": 0, "positive_or_flat": 0, "priced_or_marked": 0, "rows": 1}`.
- Suggested-trade attention ids: `[138]`.

## Blockers

- `quote_coverage_below_97_5`: `221` rows.
- `unresolved_rows_remain`: `218` rows.
- `sample_status:thin`: `162` rows.
- `trading_desk_guardrail_negative_concentration`: `110` rows.
- `sample_status:none`: `86` rows.
- `evidence_class:trusted_intraday_unresolved`: `65` rows.
- `zero_bid_exit_rate_above_2`: `60` rows.
- `positive_but_thin_or_incomplete`: `55` rows.
- `adequate_negative_exact_intraday_evidence`: `51` rows.
- `positive_exact_intraday_symbol_lane`: `15` rows.
- `evidence_class:daily_eod_research_only`: `10` rows.
- `evidence_class:blocked_no_data`: `9` rows.

## Inputs

| Source | Status | Generated | Path |
|---|---|---|---|
| bullish_pullback_ticker_audit | ok | 2026-06-02T16:37:24Z | data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json |
| regular_options_multilane | ok | 2026-06-02T17:06:54Z | data/profitability-lab/regular-options-multilane/latest.json |
| all_planned_sleeves_full | ok | 2026-06-02T17:03:19Z | data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/latest.json |
| all_planned_sleeves_partial | stale | 2026-06-02T14:22:28Z | data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/latest_partial.json |
| lane_lab | ok | 2026-06-01T14:18:56Z | data/lane-lab/latest.json |
| trading_desk_guardrails | ok | 2026-05-31T21:29:54Z | data/forward-tracking/trading_desk_profitability_guardrails_latest.json |
| open_position_risk | ok | 2026-06-01T02:51:56Z | data/forward-tracking/regular_open_position_risk_latest.json |
| suggested_trade_close_risk | ok | 2026-06-01T03:02:34Z | data/forward-tracking/suggested_trade_close_risk_latest.json |
