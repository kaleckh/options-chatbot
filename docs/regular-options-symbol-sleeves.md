# Regular Options Symbol Sleeves

This report is generated from `scripts/build_regular_options_symbol_sleeves.py`. It is a per-symbol audit/reporting layer under existing regular supervised options lanes, not a ticker-specific strategy-tuning surface.

## Summary

- Tracked symbols found: `60`.
- Symbol-lane rows: `343`.
- Classification counts: `{"keep": 25, "needs-paper": 86, "quarantine": 91, "rejected": 82, "watch": 59}`.
- Evidence classes: `{"blocked_no_data": 9, "daily_eod_research_only": 10, "mark_or_stale_review": 2, "trusted_intraday_opra_nbbo_exact": 257, "trusted_intraday_unresolved": 65}`.
- Bullish Pullback carrier symbols: `AAPL, COP, CVX, GOOGL, IWM, JNJ, LLY, NEM, UNH, XOM`.
- Queue removals are recommendations only: `True`.

## Proof Policy

- Strict proof claims require exact trusted intraday OPRA/NBBO contract rows with executable bid/ask evidence.
- Daily/EOD, research backfill, stale/display marks, unresolved candidates, midpoint-only, and last-trade rows remain non-production proof.
- Executable exit P&L is kept separate from paper/mark P&L in the open-risk readback.

## Best Rows

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| GOOGL | tracked_winner_cheap_debit_continuity_v1 | watch | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.15 | 31.4 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | watch | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.1 | 30.57 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time80_intraday | watch | trusted_intraday_opra_nbbo_exact | 34 | 42 | 8 | 80.95 | 7.4 | 51.31 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_liquidity_first_contract_hygiene_v1 | watch | trusted_intraday_opra_nbbo_exact | 32 | 36 | 4 | 88.89 | 1.63 | 10.84 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| WMT | bullish_pullback_core | watch | trusted_intraday_opra_nbbo_exact | 19 | 21 | 2 | 90.48 | 1.02 | 0.35 | quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 2.96 | 39.78 | quote_coverage_below_97_5, unresolved_rows_remain |
| JNJ | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 1.63 | 13.72 | quote_coverage_below_97_5, unresolved_rows_remain |
| WMT | sleeve_next_move_bucket_refill_v1 | watch | trusted_intraday_opra_nbbo_exact | 18 | 21 | 3 | 85.71 | 1.1 | 2.01 | quote_coverage_below_97_5, unresolved_rows_remain |
| NEM | bullish_pullback_clean_exact_reference | keep | trusted_intraday_opra_nbbo_exact | 16 | 16 | 0 | 100.0 | 13.37 | 84.03 | positive_exact_intraday_symbol_lane |
| NEM | bullish_pullback_core | keep | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | positive_exact_intraday_symbol_lane |
| NEM | sleeve_next_defensive_refill_v1 | keep | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | positive_exact_intraday_symbol_lane |

## Worst Rows

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| DIS | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -101.08 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| SMCI | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -101.08 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| IWM | iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -100.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 3 | 2 | 33.33 | 0.0 | -100.45 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| COIN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.38 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| JPM | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.33 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| XLK | bullish_pullback_clean_exact_reference | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.28 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| AMD | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.28 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| COIN | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| NVDA | regular_bearish_put_primary_timeexit_probe | quarantine | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -99.99 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| META | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -99.3 | adequate_negative_exact_intraday_evidence, sample_status:thin |

## Bullish Pullback

- Keep queue: `IWM, AAPL, GOOGL, UNH, LLY, JNJ, XOM, CVX, COP, NEM`.
- Move to frozen hypotheses: `QQQ, DIA, XLK, NVDA, AMZN, TSLA, WMT, PM, CAT, PLD`.
- Remove recommendations: `ABBV, BAC, C, COIN, FCX, JPM, PLTR, RTX, SLB`.

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| GOOGL | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 2.96 | 39.78 | quote_coverage_below_97_5, unresolved_rows_remain |
| JNJ | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 18 | 22 | 4 | 81.82 | 1.63 | 13.72 | quote_coverage_below_97_5, unresolved_rows_remain |
| NEM | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 15 | 16 | 1 | 93.75 | 12.46 | 68.81 | quote_coverage_below_97_5, unresolved_rows_remain |
| AAPL | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 11 | 13 | 2 | 84.62 | 273.54 | 24.87 | quote_coverage_below_97_5, unresolved_rows_remain |
| IWM | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| COP | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 9 | 9 | 0 | 100.0 | 76.14 | 66.87 | sample_status:thin |
| LLY | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 9 | 10 | 1 | 90.0 | 2.89 | 37.97 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| CVX | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 8 | 8 | 0 | 100.0 | 468.56 | 58.57 | sample_status:thin |
| UNH | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 8 | 10 | 2 | 80.0 | 2.08 | 29.86 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| XOM | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 210.66 | 52.66 | sample_status:thin |
| AMT | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| CLF | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| COST | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| DE | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| EQR | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| GS | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| LIN | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| LMT | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| MCD | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| MSFT | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| MSTR | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| PFE | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| PG | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SPG | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| SPY | bullish_pullback_observation | needs-paper | mark_or_stale_review | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:mark_or_stale_review, sample_status:none, trading_desk_guardrail_negative_concentration |
| V | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NVDA | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 7 | 2 | 71.43 | 0.15 | -38.21 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| JPM | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.06 | -34.13 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| QQQ | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 3 | 3 | 0 | 100.0 | 2.69 | 26.09 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| XLK | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 2 | 3 | 1 | 66.67 | 56.94 | 28.47 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| COIN | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| DIA | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -65.13 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| ABBV | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 10 | 14 | 4 | 71.43 | 0.63 | -6.65 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| PLTR | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 0.36 | -17.38 | bullish_pullback_remove_negative_exact_evidence |
| BAC | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 8 | 12 | 4 | 66.67 | 0.63 | -7.99 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| C | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 8 | 10 | 2 | 80.0 | 0.47 | -14.19 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| FCX | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 7 | 12 | 5 | 58.33 | 0.0 | -67.61 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| RTX | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 6 | 12 | 6 | 50.0 | 0.79 | -2.94 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| SLB | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 6 | 19 | 13 | 31.58 | 0.23 | -46.51 | bullish_pullback_remove_negative_exact_evidence, quote_coverage_below_97_5, sample_status:thin |
| TSLA | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 6 | 8 | 2 | 75.0 | 0.26 | -35.83 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| AMZN | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 4 | 9 | 5 | 44.44 | 0.03 | -48.1 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AA | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -63.48 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| META | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -83.99 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| BA | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -96.5 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| DIS | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -101.08 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| NKE | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -76.66 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| SBUX | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -18.82 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| WMT | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 11 | 20 | 9 | 55.0 | 1.75 | 13.37 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| OXY | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 1.07 | 2.08 | sample_status:thin |
| PLD | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 4 | 5 | 1 | 80.0 | 3.77 | 9.37 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| PM | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 4 | 7 | 3 | 57.14 | 205.02 | 51.25 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| CAT | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 3 | 10 | 7 | 30.0 | 116.08 | 38.69 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| ARM | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 28.18 | 14.09 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| KO | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 2 | 6 | 4 | 33.33 | 19.14 | 9.57 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| T | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 3.62 | 1.28 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| WELL | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 1 | 8 | 7 | 12.5 | 27.51 | 27.51 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |

## Bullish / High-Beta

High-beta upside is treated as a question, not an assumption. Rows below are exact-option evidence first; priced-only or zero-bid-damaged rows should not be called crushers.

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| AMD | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -100.33 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMD | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| AMD | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.28 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 4 | 9 | 5 | 44.44 | 0.03 | -48.1 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | high_beta_momentum_volatility | rejected | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.03 | -49.22 | adequate_negative_exact_intraday_evidence |
| AMZN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 7 | 6 | 14.29 | 0.8 | 0.8 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| AMZN | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| AMZN | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -82.72 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| AMZN | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -96.23 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| AMZN | sleeve_next_high_beta_momentum_fast_v1 | rejected | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.03 | -49.22 | adequate_negative_exact_intraday_evidence |
| AMZN | sleeve_next_high_beta_survival_v1 | rejected | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.03 | -40.77 | sample_status:thin |
| ARM | bullish_pullback_observation | watch | trusted_intraday_opra_nbbo_exact | 2 | 9 | 7 | 22.22 | 28.18 | 14.09 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| ARM | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| ARM | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 6 | 6 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| ARM | relative_strength_pullback_ex_clean_universe_v1 | needs-paper | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| COIN | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -100.23 | bullish_pullback_remove_queue_recommendation, sample_status:thin |
| COIN | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 0.0 | -100.38 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| COIN | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 11 | 11 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 2 | 4 | 2 | 50.0 | 0.0 | -83.99 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| META | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| META | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 0.0 | -99.3 | adequate_negative_exact_intraday_evidence, sample_status:thin |
| META | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -28.25 | sample_status:thin |
| MSTR | bullish_pullback_observation | needs-paper | blocked_no_data | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:blocked_no_data, sample_status:none |
| MSTR | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NFLX | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -65.13 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 7 | 10 | 3 | 70.0 | 0.08 | -34.37 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NFLX | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| NVDA | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 7 | 2 | 71.43 | 0.15 | -38.21 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | high_beta_momentum_volatility | rejected | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.15 | -47.28 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| NVDA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 3 | 2 | 33.33 | 0.0 | -100.45 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | regular_bearish_put_primary_timeexit_probe | quarantine | trusted_intraday_opra_nbbo_exact | 2 | 2 | 0 | 100.0 | 0.0 | -99.99 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | relative_strength_pullback_ex_clean_universe_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 5 | 0 | 100.0 | 0.0 | -85.2 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | sleeve_next_high_beta_momentum_fast_v1 | rejected | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.15 | -47.28 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| NVDA | sleeve_next_high_beta_survival_v1 | rejected | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -65.14 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.34 | 6.75 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 1.33 | 7.1 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 30 | 15 | 50.0 | 1.34 | 6.75 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time80_intraday | rejected | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 0.85 | -3.15 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 31 | 18 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| NVDA | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 14 | 31 | 17 | 45.16 | 0.85 | -3.15 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_cheap_debit_continuity_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.33 | 6.71 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | trusted_intraday_opra_nbbo_exact | 22 | 30 | 8 | 73.33 | 0.37 | -29.41 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| PLTR | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 0.36 | -17.38 | bullish_pullback_remove_negative_exact_evidence |
| PLTR | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 6 | 9 | 3 | 66.67 | 0.75 | -16.72 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| PLTR | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| PLTR | relative_strength_pullback_ex_clean_universe_v1 | watch | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 11.83 | 11.83 | positive_but_thin_or_incomplete, sample_status:thin |
| SMCI | bullish_pullback_observation | needs-paper | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | lane_a_chain_native_ret20_4_stop200_time75 | needs-paper | trusted_intraday_unresolved | 0 | 4 | 4 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 3 | 3 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMCI | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 1 | 4 | 3 | 25.0 | 0.0 | -101.08 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| TSLA | bullish_pullback_observation | rejected | trusted_intraday_opra_nbbo_exact | 6 | 8 | 2 | 75.0 | 0.26 | -35.83 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| TSLA | high_beta_momentum_volatility | rejected | trusted_intraday_opra_nbbo_exact | 15 | 27 | 12 | 55.56 | 0.62 | -10.4 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| TSLA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 4 | 5 | 1 | 80.0 | 0.56 | -32.83 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| TSLA | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 5 | 5 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| TSLA | relative_strength_pullback_ex_clean_universe_v1 | rejected | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 0.0 | -67.67 | sample_status:thin |
| TSLA | sleeve_next_high_beta_momentum_fast_v1 | rejected | trusted_intraday_opra_nbbo_exact | 15 | 27 | 12 | 55.56 | 0.62 | -10.4 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| TSLA | sleeve_next_high_beta_survival_v1 | rejected | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.34 | -25.82 | adequate_negative_exact_intraday_evidence, sample_status:thin |

## Tracked Winner

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| DIA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 22 | 36 | 14 | 61.11 | 1.67 | 7.64 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 26 | 34 | 8 | 76.47 | 1.02 | 0.32 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time80_intraday | quarantine | trusted_intraday_opra_nbbo_exact | 25 | 43 | 18 | 58.14 | 1.0 | -0.07 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 53 | 18 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| DIA | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 24 | 42 | 18 | 57.14 | 0.96 | -0.79 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | trusted_intraday_opra_nbbo_exact | 23 | 33 | 10 | 69.7 | 0.69 | -6.03 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| GOOGL | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 34 | 41 | 7 | 82.93 | 2.3 | 23.35 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 34 | 41 | 7 | 82.93 | 2.8 | 27.05 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | watch | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.1 | 30.57 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_qqq_time80_intraday | watch | trusted_intraday_opra_nbbo_exact | 34 | 42 | 8 | 80.95 | 7.4 | 51.31 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 41 | 10 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| GOOGL | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 33 | 40 | 7 | 82.5 | 6.85 | 48.33 | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| GOOGL | tracked_winner_cheap_debit_continuity_v1 | watch | trusted_intraday_opra_nbbo_exact | 35 | 42 | 7 | 83.33 | 3.15 | 31.4 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| GOOGL | tracked_winner_liquidity_first_contract_hygiene_v1 | watch | trusted_intraday_opra_nbbo_exact | 32 | 36 | 4 | 88.89 | 1.63 | 10.84 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.34 | 6.75 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 1.33 | 7.1 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 30 | 15 | 50.0 | 1.34 | 6.75 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_chain_native_qqq_time80_intraday | rejected | trusted_intraday_opra_nbbo_exact | 14 | 30 | 16 | 46.67 | 0.85 | -3.15 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| NVDA | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 31 | 18 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| NVDA | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 14 | 31 | 17 | 45.16 | 0.85 | -3.15 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_cheap_debit_continuity_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 31 | 16 | 48.39 | 1.33 | 6.71 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| NVDA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | trusted_intraday_opra_nbbo_exact | 22 | 30 | 8 | 73.33 | 0.37 | -29.41 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 22 | 47 | 25 | 46.81 | 1.37 | 7.21 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_chain_native_qqq_time80_intraday | quarantine | trusted_intraday_opra_nbbo_exact | 25 | 51 | 26 | 49.02 | 1.13 | 5.17 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_cheap_debit_continuity_v1 | rejected | trusted_intraday_opra_nbbo_exact | 19 | 48 | 29 | 39.58 | 0.81 | -6.01 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_liquidity_first_contract_hygiene_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 37 | 22 | 40.54 | 1.02 | 0.58 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| SPY | tracked_winner_chain_native_qqq_time65_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 16 | 45 | 29 | 35.56 | 0.24 | -36.02 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time80_intraday | rejected | trusted_intraday_opra_nbbo_exact | 20 | 49 | 29 | 40.82 | 0.62 | -18.15 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 52 | 28 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 16 | 50 | 34 | 32.0 | 0.38 | -32.92 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| SPY | tracked_winner_cheap_debit_continuity_v1 | rejected | trusted_intraday_opra_nbbo_exact | 16 | 46 | 30 | 34.78 | 0.37 | -30.45 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | trusted_intraday_opra_nbbo_exact | 11 | 40 | 29 | 27.5 | 0.94 | -1.73 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |

## Sector / Index ETF

| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| AAPL | sleeve_next_index_refill_v1 | watch | trusted_intraday_opra_nbbo_exact | 8 | 8 | 0 | 100.0 | 3.01 | 26.78 | positive_but_thin_or_incomplete, sample_status:thin |
| COP | sleeve_next_index_refill_v1 | watch | trusted_intraday_opra_nbbo_exact | 7 | 7 | 0 | 100.0 | 623.17 | 89.02 | positive_but_thin_or_incomplete, sample_status:thin |
| CVX | sleeve_next_index_refill_v1 | watch | trusted_intraday_opra_nbbo_exact | 4 | 4 | 0 | 100.0 | 6.01 | 100.9 | positive_but_thin_or_incomplete, sample_status:thin |
| DIA | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | etf_index_pullback_control | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 5 | 0 | 100.0 | 94.46 | 18.89 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| DIA | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 6 | 6 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| DIA | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 6 | 6 | 0 | 100.0 | 0.0 | -70.2 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_move_bucket_baseline_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_move_bucket_coverage_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | sleeve_next_index_with_iwm_spy_control_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 22.06 | 22.06 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 22 | 36 | 14 | 61.11 | 1.67 | 7.64 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 26 | 34 | 8 | 76.47 | 1.02 | 0.32 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_qqq_time80_intraday | quarantine | trusted_intraday_opra_nbbo_exact | 25 | 43 | 18 | 58.14 | 1.0 | -0.07 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_chain_native_research | needs-paper | daily_eod_research_only | 0 | 53 | 18 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| DIA | tracked_winner_chain_native_research_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 24 | 42 | 18 | 57.14 | 0.96 | -0.79 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| DIA | tracked_winner_cheap_debit_continuity_v1 | watch | trusted_intraday_opra_nbbo_exact | 22 | 32 | 10 | 68.75 | 1.88 | 10.76 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| DIA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | trusted_intraday_opra_nbbo_exact | 23 | 33 | 10 | 69.7 | 0.69 | -6.03 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| GOOGL | sleeve_next_index_refill_v1 | rejected | trusted_intraday_opra_nbbo_exact | 19 | 19 | 0 | 100.0 | 0.67 | -13.82 | adequate_negative_exact_intraday_evidence |
| IWM | bullish_pullback_clean_exact_reference | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | trading_desk_guardrail_negative_concentration |
| IWM | bullish_pullback_core | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | trading_desk_guardrail_negative_concentration |
| IWM | bullish_pullback_observation | keep | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| IWM | iwm_small_cap_risk | watch | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| IWM | iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 18 | 18 | 0 | 100.0 | 1.25 | 6.23 | trading_desk_guardrail_negative_concentration |
| IWM | iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 5 | 4 | 20.0 | 0.0 | -100.46 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 7 | 13 | 6 | 53.85 | 633.89 | 90.56 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 9 | 9 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| IWM | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 9 | 9 | 0 | 100.0 | 0.53 | -26.78 | adequate_negative_exact_intraday_evidence, sample_status:thin, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_defensive_refill_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_index_refill_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_index_with_iwm_spy_control_v1 | watch | trusted_intraday_opra_nbbo_exact | 10 | 13 | 3 | 76.92 | 1.94 | 19.59 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_move_bucket_refill_v1 | rejected | trusted_intraday_opra_nbbo_exact | 14 | 14 | 0 | 100.0 | 0.93 | -1.71 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| IWM | sleeve_next_reit_industrial_refill_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 1.48 | 11.24 | trading_desk_guardrail_negative_concentration |
| IWM | sleeve_ticker_iwm | watch | trusted_intraday_opra_nbbo_exact | 11 | 15 | 4 | 73.33 | 2.47 | 22.44 | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| JNJ | sleeve_next_index_refill_v1 | rejected | trusted_intraday_opra_nbbo_exact | 20 | 21 | 1 | 95.24 | 0.72 | -10.23 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| KRE | sector_rotation_regular_etf_call_stack_v1 | rejected | trusted_intraday_opra_nbbo_exact | 2 | 6 | 4 | 33.33 | 0.0 | -97.28 | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| LLY | sleeve_next_index_refill_v1 | keep | trusted_intraday_opra_nbbo_exact | 10 | 10 | 0 | 100.0 | 3.18 | 39.34 | positive_exact_intraday_symbol_lane |
| NEM | sleeve_next_index_refill_v1 | keep | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 12.67 | 84.52 | positive_exact_intraday_symbol_lane |
| QQQ | bearish_index_put_observation | needs-paper | daily_eod_research_only | 0 | 19 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | bearish_index_put_observation_chain_native_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 24 | 24 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | bullish_pullback_core | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -50.9 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | bullish_pullback_observation | quarantine | trusted_intraday_opra_nbbo_exact | 3 | 3 | 0 | 100.0 | 2.69 | 26.09 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | etf_index_pullback_control | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -46.35 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 123.13 | 123.13 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| QQQ | range_breakout_call_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 7 | 11 | 4 | 63.64 | 0.54 | -17.66 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| QQQ | range_breakout_observation | needs-paper | daily_eod_research_only | 0 | 17 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | range_breakout_observation_chain_native_call_timeexit_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 7 | 11 | 4 | 63.64 | 0.97 | -0.47 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| QQQ | range_breakout_observation_chain_native_put_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | regular_bearish_put_index_narrow_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 3 | 12 | 9 | 25.0 | 4.03 | 17.86 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 3 | 12 | 9 | 25.0 | 4.03 | 17.86 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 15 | 15 | 0 | 100.0 | 0.22 | -31.6 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_move_bucket_baseline_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -46.35 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_move_bucket_coverage_v1 | needs-paper | trusted_intraday_unresolved | 0 | 1 | 1 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| QQQ | sleeve_next_index_refill_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -32.04 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_index_with_iwm_spy_control_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 2 | 1 | 50.0 | 71.33 | 71.33 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | sleeve_next_move_bucket_refill_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -32.04 | sample_status:thin, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 22 | 47 | 25 | 46.81 | 1.37 | 7.21 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_chain_native_qqq_time80_intraday | quarantine | trusted_intraday_opra_nbbo_exact | 25 | 51 | 26 | 49.02 | 1.13 | 5.17 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | tracked_winner_cheap_debit_continuity_v1 | rejected | trusted_intraday_opra_nbbo_exact | 19 | 48 | 29 | 39.58 | 0.81 | -6.01 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | tracked_winner_liquidity_first_contract_hygiene_v1 | quarantine | trusted_intraday_opra_nbbo_exact | 15 | 37 | 22 | 40.54 | 1.02 | 0.58 | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| QQQ | volatility_expansion_call_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 26 | 30 | 4 | 86.67 | 0.71 | -8.3 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation | needs-paper | daily_eod_research_only | 0 | 66 | 4 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| QQQ | volatility_expansion_observation_chain_native_call_fast35_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 23 | 32 | 9 | 71.88 | 0.22 | -13.56 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation_chain_native_call_timeexit_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 24 | 30 | 6 | 80.0 | 0.63 | -10.02 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| QQQ | volatility_expansion_observation_chain_native_put_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 14 | 14 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SMH | sector_rotation_regular_etf_call_stack_v1 | rejected | trusted_intraday_opra_nbbo_exact | 11 | 14 | 3 | 78.57 | 0.52 | -16.04 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| SMH | smh_semiconductor_call_chain_native_timeexit_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 17 | 20 | 3 | 85.0 | 0.49 | -15.45 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, unresolved_rows_remain |
| SPY | bearish_index_put_observation | needs-paper | daily_eod_research_only | 0 | 18 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | bearish_index_put_observation_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 15 | 14 | 6.67 | 2.71 | 2.71 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | bullish_pullback_observation | needs-paper | mark_or_stale_review | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:mark_or_stale_review, sample_status:none, trading_desk_guardrail_negative_concentration |
| SPY | lane_a_chain_native_ret20_4_stop200_time75 | quarantine | trusted_intraday_opra_nbbo_exact | 1 | 1 | 0 | 100.0 | 0.0 | -72.47 | sample_status:thin, trading_desk_guardrail_negative_concentration, zero_bid_exit_rate_above_2 |
| SPY | range_breakout_call_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 7 | 10 | 3 | 70.0 | 0.24 | -30.71 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| SPY | range_breakout_observation | needs-paper | daily_eod_research_only | 0 | 6 | 0 | 0.0 | 0.0 | 0.0 | evidence_class:daily_eod_research_only, quote_coverage_below_97_5, sample_status:none |
| SPY | range_breakout_observation_chain_native_call_timeexit_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 7 | 9 | 2 | 77.78 | 0.1 | -37.7 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, sample_status:thin |
| SPY | range_breakout_observation_chain_native_put_timeexit_all_sleeves | needs-paper | trusted_intraday_unresolved | 0 | 2 | 2 | 0.0 | 0.0 | 0.0 | evidence_class:trusted_intraday_unresolved, quote_coverage_below_97_5, sample_status:none |
| SPY | regular_bearish_put_index_narrow_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 11 | 6 | 45.45 | 1.14 | 2.6 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | regular_bearish_put_primary_chain_native_timeexit_all_sleeves | quarantine | trusted_intraday_opra_nbbo_exact | 5 | 11 | 6 | 45.45 | 1.14 | 2.6 | quote_coverage_below_97_5, sample_status:thin, trading_desk_guardrail_negative_concentration |
| SPY | regular_bearish_put_primary_timeexit_probe | rejected | trusted_intraday_opra_nbbo_exact | 13 | 13 | 0 | 100.0 | 0.77 | -6.87 | adequate_negative_exact_intraday_evidence, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time65_all_sleeves | rejected | trusted_intraday_opra_nbbo_exact | 16 | 45 | 29 | 35.56 | 0.24 | -36.02 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| SPY | tracked_winner_chain_native_qqq_time80_intraday | rejected | trusted_intraday_opra_nbbo_exact | 20 | 49 | 29 | 40.82 | 0.62 | -18.15 | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |

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
