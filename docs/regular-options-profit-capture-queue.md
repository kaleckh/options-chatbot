# Regular Options Profit Capture Queue

This report is generated from `scripts/build_regular_options_profit_capture_queue.py`. It is a research/paper capture and proof-hardening layer, not a scanner promotion or broker-action surface.

## Summary

- Status: `research_paper_capture_queue`.
- Queue rows: `97`.
- Tier counts: `{"tier_a_clean_exact_capture": 15, "tier_b_profitable_watch_repair": 82}`.
- Selection readiness: `{"blocked_guardrail_only": 3, "do_not_chase": 173, "historical_signature_only": 2, "paper_review_candidate": 15, "watch_repair_only": 82}`.
- Evidence repair priorities: `{"high": 16, "low": 43, "medium": 23, "none": 15}`.
- Fresh scan matches: `5` with decisions `{"blocked": 3, "clear": 2}`.
- Blocked but interesting: `3`.
- Quarantine queue rows: `173`.
- Live policy change: `False`.

## Proof Policy

- Tier A requires trusted intraday OPRA/NBBO exact-contract evidence, zero unresolved rows, adequate sample, high quote coverage, positive PF/average P&L, and no clean disqualifier.
- Tier B is profitable watch evidence that still needs proof repair, sample, coverage, or forward-paper validation.
- Tier C fresh scan matches are historical-signature matches only; they are not validated trade recommendations by themselves.
- Selection readiness is paper/research routing only; it does not change scanner, broker, or stop-loss behavior.
- Blocked candidates remain blocked, with reasons preserved.

## Tier A Clean Exact

| Tier | Readiness | Symbol | Lane | Status | Exact | Unres | Cov % | PF | Avg % | Median % | Repair | Fresh | Reason |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| tier_a_clean_exact_capture | paper_review_candidate | NEM | bullish_pullback_clean_exact_reference | keep | 16 | 0 | 100.0 | 13.37 | 84.03 | 76.18 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | NEM | bullish_pullback_core | keep | 15 | 0 | 100.0 | 12.67 | 84.52 | 75.81 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | NEM | sleeve_next_defensive_refill_v1 | keep | 15 | 0 | 100.0 | 12.67 | 84.52 | 75.81 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | NEM | sleeve_next_index_refill_v1 | keep | 15 | 0 | 100.0 | 12.67 | 84.52 | 75.81 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | NEM | sleeve_next_move_bucket_refill_v1 | keep | 15 | 0 | 100.0 | 12.67 | 84.52 | 75.81 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | NEM | sleeve_next_reit_industrial_refill_v1 | keep | 15 | 0 | 100.0 | 12.67 | 84.52 | 75.81 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | AAPL | bullish_pullback_core | keep | 11 | 0 | 100.0 | 6.62 | 54.5 | 45.44 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | AAPL | bullish_pullback_clean_exact_reference | keep | 13 | 0 | 100.0 | 3.7 | 42.67 | 45.44 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | LLY | bullish_pullback_core | keep | 10 | 0 | 100.0 | 3.18 | 39.34 | 57.97 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | LLY | sleeve_next_defensive_refill_v1 | keep | 10 | 0 | 100.0 | 3.18 | 39.34 | 57.97 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | LLY | sleeve_next_index_refill_v1 | keep | 10 | 0 | 100.0 | 3.18 | 39.34 | 57.97 | none |  | positive_exact_intraday_symbol_lane |
| tier_a_clean_exact_capture | paper_review_candidate | LLY | sleeve_next_move_bucket_refill_v1 | keep | 10 | 0 | 100.0 | 3.18 | 39.34 | 57.97 | none |  | positive_exact_intraday_symbol_lane |

## Tier B Watch / Repair

| Tier | Readiness | Symbol | Lane | Status | Exact | Unres | Cov % | PF | Avg % | Median % | Repair | Fresh | Reason |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| tier_b_profitable_watch_repair | watch_repair_only | AMD | bullish_momentum | watch | 10 | 0 | 100.0 | 47.61 | 139.08 | 154.34 | low |  | current_policy_historical_paper_only |
| tier_b_profitable_watch_repair | watch_repair_only | AMZN | bullish_momentum | watch | 1 | 0 | 100.0 | 153.4 | 153.4 | 153.4 | low |  | current_policy_historical_paper_only, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | AMD | swing | watch | 11 | 0 | 100.0 | 23.86 | 112.43 | 137.0 | low |  | current_policy_historical_paper_only |
| tier_b_profitable_watch_repair | watch_repair_only | AMD | short_term | watch | 13 | 0 | 100.0 | 25.73 | 93.81 | 89.73 | low |  | current_policy_historical_paper_only |
| tier_b_profitable_watch_repair | watch_repair_only | COP | sleeve_next_index_refill_v1 | watch | 7 | 0 | 100.0 | 623.17 | 89.02 | 78.31 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | bullish_pullback_core | watch | 6 | 0 | 100.0 | 544.86 | 90.81 | 85.69 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | sleeve_next_defensive_refill_v1 | watch | 6 | 0 | 100.0 | 544.86 | 90.81 | 85.69 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | sleeve_next_move_bucket_refill_v1 | watch | 6 | 0 | 100.0 | 544.86 | 90.81 | 85.69 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | sleeve_next_reit_industrial_refill_v1 | watch | 6 | 0 | 100.0 | 544.86 | 90.81 | 85.69 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | bullish_momentum | watch | 7 | 0 | 100.0 | 607.86 | 86.84 | 104.17 | low |  | current_policy_historical_paper_only, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | AAPL | bullish_momentum | watch | 6 | 0 | 100.0 | 506.74 | 84.46 | 58.02 | low |  | current_policy_historical_paper_only, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | bullish_pullback_core | watch | 3 | 0 | 100.0 | 267.17 | 89.06 | 100.48 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | sleeve_next_defensive_refill_v1 | watch | 3 | 0 | 100.0 | 267.17 | 89.06 | 100.48 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | sleeve_next_move_bucket_refill_v1 | watch | 3 | 0 | 100.0 | 267.17 | 89.06 | 100.48 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | sleeve_next_reit_industrial_refill_v1 | watch | 3 | 0 | 100.0 | 267.17 | 89.06 | 100.48 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | bullish_pullback_observation | keep | 9 | 0 | 100.0 | 76.14 | 66.87 | 75.19 | low |  | sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | COP | bullish_pullback_clean_exact_reference | watch | 7 | 0 | 100.0 | 462.46 | 66.07 | 72.23 | low |  | positive_but_thin_or_incomplete, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | CVX | bullish_pullback_observation | keep | 8 | 0 | 100.0 | 468.56 | 58.57 | 44.88 | low |  | sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | bullish_pullback_observation | keep | 4 | 0 | 100.0 | 210.66 | 52.66 | 42.31 | low |  | sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | XOM | sleeve_next_index_refill_v1 | watch | 1 | 0 | 100.0 | 60.45 | 60.45 | 60.45 | low |  | positive_but_thin_or_incomplete, sample_status:thin |

## Fresh Scan Signature Matches

| Tier | Readiness | Symbol | Playbook | Decision | Match | Debit % | Quality | Matched sleeves | Reasons |
|---|---|---|---|---|---|---:|---:|---|---|
| tier_c_fresh_scan_signature_match | historical_signature_only | QQQ | swing | clear | lane_signature | 40.8 | 84.6 | swing:tier_b_profitable_watch_repair |  |
| tier_c_fresh_scan_signature_match | historical_signature_only | SPY | swing | clear | lane_signature | 37.3 | 98.9 | swing:tier_b_profitable_watch_repair |  |
| blocked_but_interesting | blocked_guardrail_only | SPY | tracked_winner_primary | blocked | lane_signature | 40.04 | 90.0 | tracked_winner_chain_native_research:needs-paper, tracked_winner_chain_native_qqq_time80_intraday:quarantine_do_not_chase, tracked_winner_cheap_debit_continuity_v1:quarantine_do_not_chase, tracked_winner_chain_native_research_all_sleeves:quarantine_do_not_chase | Spread debit is 40.0% of width, above the Tracked Winner cap of 40.0%. |
| blocked_but_interesting | blocked_guardrail_only | SPY | speculative | blocked | symbol_only | 38.9 | 82.7 | swing:tier_b_profitable_watch_repair, bearish_index_put_observation_chain_native_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_index_narrow_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_primary_chain_native_timeexit_all_sleeves:quarantine_do_not_chase | Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale. |
| blocked_but_interesting | blocked_guardrail_only | SPY | tracked_winner_observation | blocked | symbol_only | 40.04 | 90.0 | swing:tier_b_profitable_watch_repair, bearish_index_put_observation_chain_native_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_index_narrow_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_primary_chain_native_timeexit_all_sleeves:quarantine_do_not_chase | Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%. |

## Blocked But Interesting

| Tier | Readiness | Symbol | Playbook | Decision | Match | Debit % | Quality | Matched sleeves | Reasons |
|---|---|---|---|---|---|---:|---:|---|---|
| blocked_but_interesting | blocked_guardrail_only | SPY | tracked_winner_primary | blocked | lane_signature | 40.04 | 90.0 | tracked_winner_chain_native_research:needs-paper, tracked_winner_chain_native_qqq_time80_intraday:quarantine_do_not_chase, tracked_winner_cheap_debit_continuity_v1:quarantine_do_not_chase, tracked_winner_chain_native_research_all_sleeves:quarantine_do_not_chase | Spread debit is 40.0% of width, above the Tracked Winner cap of 40.0%. |
| blocked_but_interesting | blocked_guardrail_only | SPY | speculative | blocked | symbol_only | 38.9 | 82.7 | swing:tier_b_profitable_watch_repair, bearish_index_put_observation_chain_native_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_index_narrow_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_primary_chain_native_timeexit_all_sleeves:quarantine_do_not_chase | Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale. |
| blocked_but_interesting | blocked_guardrail_only | SPY | tracked_winner_observation | blocked | symbol_only | 40.04 | 90.0 | swing:tier_b_profitable_watch_repair, bearish_index_put_observation_chain_native_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_index_narrow_timeexit_all_sleeves:quarantine_do_not_chase, regular_bearish_put_primary_chain_native_timeexit_all_sleeves:quarantine_do_not_chase | Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%. |

## Evidence Repair Queue

| Tier | Readiness | Symbol | Lane | Status | Exact | Unres | Cov % | PF | Avg % | Median % | Repair | Fresh | Reason |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| tier_b_profitable_watch_repair | watch_repair_only | NEM | bullish_pullback_observation | keep | 15 | 1 | 93.75 | 12.46 | 68.81 | 76.33 | high |  | quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | sleeve_next_defensive_refill_v1 | watch | 9 | 1 | 90.0 | 4.9 | 51.6 | 4.36 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | sleeve_next_index_refill_v1 | watch | 9 | 1 | 90.0 | 4.9 | 51.6 | 4.36 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | sleeve_next_move_bucket_refill_v1 | watch | 9 | 1 | 90.0 | 4.9 | 51.6 | 4.36 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | sleeve_next_reit_industrial_refill_v1 | watch | 9 | 1 | 90.0 | 4.9 | 51.6 | 4.36 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | watch | 34 | 8 | 80.95 | 7.4 | 51.31 | 27.95 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | GOOGL | bullish_pullback_observation | keep | 18 | 4 | 81.82 | 2.96 | 39.78 | 59.78 | high |  | quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | LLY | bullish_pullback_observation | keep | 9 | 1 | 90.0 | 2.89 | 37.97 | 57.51 | high |  | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | GOOGL | tracked_winner_cheap_debit_continuity_v1 | watch | 35 | 7 | 83.33 | 3.15 | 31.4 | 27.72 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | watch | 35 | 7 | 83.33 | 3.1 | 30.57 | 27.72 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | UNH | bullish_pullback_observation | keep | 8 | 2 | 80.0 | 2.08 | 29.86 | -1.75 | high |  | quote_coverage_below_97_5, sample_status:thin, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | AAPL | bullish_pullback_observation | keep | 11 | 2 | 84.62 | 273.54 | 24.87 | 21.39 | high |  | quote_coverage_below_97_5, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | WMT | relative_strength_pullback_ex_clean_universe_v1 | watch | 9 | 3 | 75.0 | 3.53 | 24.77 | 21.61 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | IWM | bullish_pullback_observation | keep | 11 | 4 | 73.33 | 2.47 | 22.44 | 13.08 | high |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| tier_b_profitable_watch_repair | watch_repair_only | IWM | iwm_small_cap_risk | watch | 11 | 4 | 73.33 | 2.47 | 22.44 | 13.08 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| tier_b_profitable_watch_repair | watch_repair_only | IWM | sleeve_ticker_iwm | watch | 11 | 4 | 73.33 | 2.47 | 22.44 | 13.08 | high |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| tier_b_profitable_watch_repair | watch_repair_only | PM | sleeve_next_defensive_refill_v1 | watch | 3 | 3 | 50.0 | 222.51 | 74.17 | 67.32 | medium |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | PM | sleeve_next_move_bucket_refill_v1 | watch | 3 | 3 | 50.0 | 222.51 | 74.17 | 67.32 | medium |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | PM | relative_strength_pullback_ex_clean_universe_v1 | watch | 2 | 3 | 40.0 | 121.23 | 60.61 | 60.61 | medium |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |
| tier_b_profitable_watch_repair | watch_repair_only | RTX | relative_strength_pullback_ex_clean_universe_v1 | watch | 4 | 3 | 57.14 | 242.15 | 60.54 | 62.28 | medium |  | positive_but_thin_or_incomplete, quote_coverage_below_97_5, sample_status:thin |

## Quarantine / Do Not Chase

| Tier | Readiness | Symbol | Lane | Status | Exact | Unres | Cov % | PF | Avg % | Median % | Repair | Fresh | Reason |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| quarantine_do_not_chase | do_not_chase | GOOGL | tracked_winner_chain_native_googl_nvda_time65_all_sleeves | quarantine | 34 | 7 | 82.93 | 2.3 | 23.35 | 27.59 | none |  | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| quarantine_do_not_chase | do_not_chase | GOOGL | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | 34 | 7 | 82.93 | 2.8 | 27.05 | 27.59 | none |  | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| quarantine_do_not_chase | do_not_chase | GOOGL | tracked_winner_chain_native_research_all_sleeves | quarantine | 33 | 7 | 82.5 | 6.85 | 48.33 | 27.73 | none |  | quote_coverage_below_97_5, unresolved_rows_remain, zero_bid_exit_rate_above_2 |
| quarantine_do_not_chase | do_not_chase | SPY | volatility_expansion_observation_chain_native_call_fast35_all_sleeves | rejected | 26 | 9 | 74.29 | 0.08 | -24.04 | -27.7 | none | {"blocked_count": 2, "clear_count": 0, "fresh_scan_match_count": 2, "guardrail_reasons": ["Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.", "Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%."], "playbooks": ["speculative", "tracked_winner_observation"]} | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | QQQ | volatility_expansion_call_timeexit_probe | rejected | 26 | 4 | 86.67 | 0.71 | -8.3 | 8.59 | none |  | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | DIA | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | 26 | 8 | 76.47 | 1.02 | 0.32 | 7.13 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | DIA | tracked_winner_chain_native_qqq_time80_intraday | quarantine | 25 | 18 | 58.14 | 1.0 | -0.07 | 6.06 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | QQQ | tracked_winner_chain_native_qqq_time80_intraday | quarantine | 25 | 26 | 49.02 | 1.13 | 5.17 | -10.46 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | QQQ | volatility_expansion_observation_chain_native_call_timeexit_all_sleeves | rejected | 24 | 6 | 80.0 | 0.63 | -10.02 | -11.89 | none |  | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | DIA | tracked_winner_chain_native_research_all_sleeves | quarantine | 24 | 18 | 57.14 | 0.96 | -0.79 | 5.49 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | QQQ | volatility_expansion_observation_chain_native_call_fast35_all_sleeves | rejected | 23 | 9 | 71.88 | 0.22 | -13.56 | -10.88 | none |  | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | DIA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | 23 | 10 | 69.7 | 0.69 | -6.03 | 0.46 | none |  | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | NVDA | tracked_winner_liquidity_first_contract_hygiene_v1 | rejected | 22 | 8 | 73.33 | 0.37 | -29.41 | -33.65 | none |  | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | SPY | volatility_expansion_call_timeexit_probe | rejected | 22 | 6 | 78.57 | 0.47 | -16.48 | -26.46 | none | {"blocked_count": 2, "clear_count": 0, "fresh_scan_match_count": 2, "guardrail_reasons": ["Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.", "Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%."], "playbooks": ["speculative", "tracked_winner_observation"]} | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | GOOGL | bullish_pullback_clean_exact_reference | rejected | 22 | 0 | 100.0 | 0.76 | -9.08 | -24.29 | none |  | adequate_negative_exact_intraday_evidence |
| quarantine_do_not_chase | do_not_chase | QQQ | tracked_winner_chain_native_qqq_time65_all_sleeves | quarantine | 22 | 25 | 46.81 | 1.37 | 7.21 | 11.73 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | DIA | tracked_winner_chain_native_no_spy_time65_all_sleeves | quarantine | 22 | 14 | 61.11 | 1.67 | 7.64 | 10.09 | none |  | quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration, unresolved_rows_remain |
| quarantine_do_not_chase | do_not_chase | GOOGL | bullish_pullback_core | rejected | 21 | 0 | 100.0 | 0.67 | -13.4 | -27.32 | none |  | adequate_negative_exact_intraday_evidence |
| quarantine_do_not_chase | do_not_chase | SPY | tracked_winner_chain_native_qqq_time80_intraday | rejected | 20 | 29 | 40.82 | 0.62 | -18.15 | -46.8 | none | {"blocked_count": 3, "clear_count": 0, "fresh_scan_match_count": 3, "guardrail_reasons": ["Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.", "Spread debit is 40.0% of width, above the Tracked Winner cap of 40.0%.", "Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%."], "playbooks": ["speculative", "tracked_winner_primary", "tracked_winner_observation"]} | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |
| quarantine_do_not_chase | do_not_chase | SPY | volatility_expansion_observation_chain_native_call_timeexit_all_sleeves | rejected | 20 | 8 | 71.43 | 0.44 | -14.96 | -10.18 | none | {"blocked_count": 2, "clear_count": 0, "fresh_scan_match_count": 2, "guardrail_reasons": ["Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.", "Spread debit is 40.0% of width, above the Tracked Winner Observation cap of 40.0%."], "playbooks": ["speculative", "tracked_winner_observation"]} | adequate_negative_exact_intraday_evidence, quote_coverage_below_97_5, trading_desk_guardrail_negative_concentration |

## Inputs

| Source | Status | Generated | Path |
|---|---|---|---|
| regular_options_symbol_sleeves | ok | 2026-06-02T17:08:51Z | data/profitability-lab/regular-options-symbol-sleeves/latest.json |
| current_policy_historical_picks | ok | 2026-06-01T05:47:42Z | data/forward-tracking/current_policy_historical_picks_latest.json |
| regular_guardrail_starvation | ok | 2026-06-03T06:59:53Z | data/forward-tracking/regular_guardrail_starvation_latest.json |
