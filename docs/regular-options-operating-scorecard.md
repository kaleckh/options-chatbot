# Active Options Operating Scorecard

- Status: `visible_product_profitability_progress_but_proof_still_blocked`
- Product profitability progress visible: `True`
- Proof-grade profitability progress visible: `False`

## Profitability Paper Gates

- Status: `paper_only_no_live_release`
- Eligible paper-review candidates: `0`
- Paper shortlist release gate: `no_paper_shortlist_candidates`
- Invariant violations: `0`
- Profit-capture queue rows / tiers: `97` / `{'tier_a_clean_exact_capture': 15, 'tier_b_profitable_watch_repair': 82}`
- Selection readiness: `{'blocked_guardrail_only': 9, 'do_not_chase': 173, 'historical_signature_only': 6, 'paper_review_candidate': 15, 'watch_repair_only': 82}`
- Fresh validation candidates / no-longer-matched / proof-ineligible: `34` / `16` / `5`
- Exact realized P&L / promotion-ready rows: `0` / `0`
- Current-policy route / paper-only lanes: `paper_validation_only` / `2`
- Recovery gate failures: `['recent_cohort_recovered', 'fresh_current_policy_rows', 'fresh_champion_matched_rows', 'trusted_exact_realized_pnl_rows', 'point_in_time_replay_pass', 'paper_monitor_pass']`
- Repair targets active / source replay / diagnostic / exhausted: `11` / `5` / `32` / `97`
- Repair next step: `Rerun source replay for rows with exact-date repair memory before importing more data.`
- Live policy change: `False`

## Trading Desk Guardrails

- Baseline avg/median/negative-rate: `5.21%` / `-1.58%` / `50.4%`
- Promoted kept avg/median/negative-rate: `53.08%` / `46.4%` / `25.0%`
- Deltas: `{'avg_pnl_pct': 47.87, 'median_pnl_pct': 47.98, 'negative_rate_priced_pct': -25.4}`

## Current-Policy Entry Filter Monitor

- Status: `collecting`
- Champion: `short_term_fill_degradation_ge_15`
- Since date: `2026-06-02`
- Fresh rows / closed / priced: `0` / `0` / `0`
- Champion matched / closed: `0` / `0`
- Gate failures: `['insufficient_fresh_rows', 'insufficient_candidate_blocked_rows', 'blocked_rows_not_net_negative_or_deep_loss']`
- Live policy change: `False`

## Current-Policy Entry Filter Walk-Forward

- Status: `mixed_walkforward_watch_not_promoted`
- Candidate: `short_term_fill_degradation_ge_15`
- Rows / months: `112` / `['2026-04', '2026-05']`
- Frozen filter status / matched: `historical_pass_candidate` / `9`
- Frozen avoided deep / near-total / lost winners: `5` / `3` / `2`
- Latest holdout: `2026-05` / `historical_pass_candidate`
- Broad all-lane fill>=15 status: `winner_damage_too_high`
- Lane statuses: `{'short_term': 'historical_pass_candidate', 'swing': 'no_deep_loss_reduction', 'bullish_momentum': 'winner_damage_too_high', 'bullish_pullback_observation': 'no_coverage'}`
- Live policy change: `False`

## Profit Capture Queue

- Status: `research_paper_capture_queue`
- Queue rows / tiers: `97` / `{'tier_a_clean_exact_capture': 15, 'tier_b_profitable_watch_repair': 82}`
- Evidence repair priorities: `{'high': 16, 'low': 43, 'medium': 23, 'none': 15}`
- Fresh scan matches / decisions: `15` / `{'blocked': 9, 'clear': 6}`
- Blocked but interesting: `9`
- Quarantine queue / overlay rows: `173` / `5`
- Top clean exact: `[{'symbol': 'NEM', 'lane_id': 'bullish_pullback_clean_exact_reference', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 16, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 13.37, 'avg_pnl': 84.03, 'median_pnl': 76.18, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'NEM', 'lane_id': 'bullish_pullback_core', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 15, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 12.67, 'avg_pnl': 84.52, 'median_pnl': 75.81, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'NEM', 'lane_id': 'sleeve_next_defensive_refill_v1', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 15, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 12.67, 'avg_pnl': 84.52, 'median_pnl': 75.81, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'NEM', 'lane_id': 'sleeve_next_index_refill_v1', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 15, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 12.67, 'avg_pnl': 84.52, 'median_pnl': 75.81, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'NEM', 'lane_id': 'sleeve_next_move_bucket_refill_v1', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 15, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 12.67, 'avg_pnl': 84.52, 'median_pnl': 75.81, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'NEM', 'lane_id': 'sleeve_next_reit_industrial_refill_v1', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 15, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 12.67, 'avg_pnl': 84.52, 'median_pnl': 75.81, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'AAPL', 'lane_id': 'bullish_pullback_core', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 11, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 6.62, 'avg_pnl': 54.5, 'median_pnl': 45.44, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}, {'symbol': 'AAPL', 'lane_id': 'bullish_pullback_clean_exact_reference', 'capture_tier': 'tier_a_clean_exact_capture', 'status': 'keep', 'exact': 13, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 3.7, 'avg_pnl': 42.67, 'median_pnl': 45.44, 'evidence_repair_priority': 'none', 'reason_codes': ['positive_exact_intraday_symbol_lane']}]`
- Top watch/repair: `[{'symbol': 'AMD', 'lane_id': 'bullish_momentum', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 10, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 47.61, 'avg_pnl': 139.08, 'median_pnl': 154.34, 'evidence_repair_priority': 'low', 'reason_codes': ['current_policy_historical_paper_only']}, {'symbol': 'AMZN', 'lane_id': 'bullish_momentum', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 1, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 153.4, 'avg_pnl': 153.4, 'median_pnl': 153.4, 'evidence_repair_priority': 'low', 'reason_codes': ['current_policy_historical_paper_only', 'sample_status:thin']}, {'symbol': 'AMD', 'lane_id': 'swing', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 11, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 23.86, 'avg_pnl': 112.43, 'median_pnl': 137.0, 'evidence_repair_priority': 'low', 'reason_codes': ['current_policy_historical_paper_only']}, {'symbol': 'AMD', 'lane_id': 'short_term', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 13, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 25.73, 'avg_pnl': 93.81, 'median_pnl': 89.73, 'evidence_repair_priority': 'low', 'reason_codes': ['current_policy_historical_paper_only']}, {'symbol': 'COP', 'lane_id': 'sleeve_next_index_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 7, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 623.17, 'avg_pnl': 89.02, 'median_pnl': 78.31, 'evidence_repair_priority': 'low', 'reason_codes': ['positive_but_thin_or_incomplete', 'sample_status:thin']}, {'symbol': 'COP', 'lane_id': 'bullish_pullback_core', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 6, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 544.86, 'avg_pnl': 90.81, 'median_pnl': 85.69, 'evidence_repair_priority': 'low', 'reason_codes': ['positive_but_thin_or_incomplete', 'sample_status:thin']}, {'symbol': 'COP', 'lane_id': 'sleeve_next_defensive_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 6, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 544.86, 'avg_pnl': 90.81, 'median_pnl': 85.69, 'evidence_repair_priority': 'low', 'reason_codes': ['positive_but_thin_or_incomplete', 'sample_status:thin']}, {'symbol': 'COP', 'lane_id': 'sleeve_next_move_bucket_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 6, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 544.86, 'avg_pnl': 90.81, 'median_pnl': 85.69, 'evidence_repair_priority': 'low', 'reason_codes': ['positive_but_thin_or_incomplete', 'sample_status:thin']}, {'symbol': 'COP', 'lane_id': 'sleeve_next_reit_industrial_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 6, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 544.86, 'avg_pnl': 90.81, 'median_pnl': 85.69, 'evidence_repair_priority': 'low', 'reason_codes': ['positive_but_thin_or_incomplete', 'sample_status:thin']}, {'symbol': 'UNH', 'lane_id': 'bullish_momentum', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 7, 'unresolved': 0, 'quote_coverage': 100.0, 'profit_factor': 607.86, 'avg_pnl': 86.84, 'median_pnl': 104.17, 'evidence_repair_priority': 'low', 'reason_codes': ['current_policy_historical_paper_only', 'sample_status:thin']}]`
- Evidence repair queue: `[{'symbol': 'NEM', 'lane_id': 'bullish_pullback_observation', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'keep', 'exact': 15, 'unresolved': 1, 'quote_coverage': 93.75, 'profit_factor': 12.46, 'avg_pnl': 68.81, 'median_pnl': 76.33, 'evidence_repair_priority': 'high', 'reason_codes': ['quote_coverage_below_97_5', 'unresolved_rows_remain']}, {'symbol': 'UNH', 'lane_id': 'sleeve_next_defensive_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 9, 'unresolved': 1, 'quote_coverage': 90.0, 'profit_factor': 4.9, 'avg_pnl': 51.6, 'median_pnl': 4.36, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'sample_status:thin', 'unresolved_rows_remain']}, {'symbol': 'UNH', 'lane_id': 'sleeve_next_index_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 9, 'unresolved': 1, 'quote_coverage': 90.0, 'profit_factor': 4.9, 'avg_pnl': 51.6, 'median_pnl': 4.36, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'sample_status:thin', 'unresolved_rows_remain']}, {'symbol': 'UNH', 'lane_id': 'sleeve_next_move_bucket_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 9, 'unresolved': 1, 'quote_coverage': 90.0, 'profit_factor': 4.9, 'avg_pnl': 51.6, 'median_pnl': 4.36, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'sample_status:thin', 'unresolved_rows_remain']}, {'symbol': 'UNH', 'lane_id': 'sleeve_next_reit_industrial_refill_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 9, 'unresolved': 1, 'quote_coverage': 90.0, 'profit_factor': 4.9, 'avg_pnl': 51.6, 'median_pnl': 4.36, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'sample_status:thin', 'unresolved_rows_remain']}, {'symbol': 'GOOGL', 'lane_id': 'tracked_winner_chain_native_qqq_time80_intraday', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 34, 'unresolved': 8, 'quote_coverage': 80.95, 'profit_factor': 7.4, 'avg_pnl': 51.31, 'median_pnl': 27.95, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'unresolved_rows_remain']}, {'symbol': 'GOOGL', 'lane_id': 'bullish_pullback_observation', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'keep', 'exact': 18, 'unresolved': 4, 'quote_coverage': 81.82, 'profit_factor': 2.96, 'avg_pnl': 39.78, 'median_pnl': 59.78, 'evidence_repair_priority': 'high', 'reason_codes': ['quote_coverage_below_97_5', 'unresolved_rows_remain']}, {'symbol': 'LLY', 'lane_id': 'bullish_pullback_observation', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'keep', 'exact': 9, 'unresolved': 1, 'quote_coverage': 90.0, 'profit_factor': 2.89, 'avg_pnl': 37.97, 'median_pnl': 57.51, 'evidence_repair_priority': 'high', 'reason_codes': ['quote_coverage_below_97_5', 'sample_status:thin', 'unresolved_rows_remain']}, {'symbol': 'GOOGL', 'lane_id': 'tracked_winner_cheap_debit_continuity_v1', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 35, 'unresolved': 7, 'quote_coverage': 83.33, 'profit_factor': 3.15, 'avg_pnl': 31.4, 'median_pnl': 27.72, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'unresolved_rows_remain']}, {'symbol': 'GOOGL', 'lane_id': 'tracked_winner_chain_native_qqq_time65_all_sleeves', 'capture_tier': 'tier_b_profitable_watch_repair', 'status': 'watch', 'exact': 35, 'unresolved': 7, 'quote_coverage': 83.33, 'profit_factor': 3.1, 'avg_pnl': 30.57, 'median_pnl': 27.72, 'evidence_repair_priority': 'high', 'reason_codes': ['positive_but_thin_or_incomplete', 'quote_coverage_below_97_5', 'unresolved_rows_remain']}]`
- Blocked interesting examples: `[{'symbol': 'SPY', 'playbook_id': 'tracked_winner_primary', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'lane_signature', 'debit_pct_of_width': 38.74, 'quality_score': 97.9, 'guardrail_reasons': ['Tracked Winner only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 0.0, 'capture_tier': None, 'exact': 0, 'lane_id': 'tracked_winner_chain_native_research', 'profit_factor': 0.0, 'status': 'needs-paper', 'symbol': 'SPY', 'unresolved': 28}, {'avg_pnl': -18.15, 'capture_tier': 'quarantine_do_not_chase', 'exact': 20, 'lane_id': 'tracked_winner_chain_native_qqq_time80_intraday', 'profit_factor': 0.62, 'status': 'rejected', 'symbol': 'SPY', 'unresolved': 29}, {'avg_pnl': -30.45, 'capture_tier': 'quarantine_do_not_chase', 'exact': 16, 'lane_id': 'tracked_winner_cheap_debit_continuity_v1', 'profit_factor': 0.37, 'status': 'rejected', 'symbol': 'SPY', 'unresolved': 30}]}, {'symbol': 'QQQ', 'playbook_id': 'bullish_momentum', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 37.6, 'quality_score': 91.9, 'guardrail_reasons': ['Bullish Momentum only allows asset classes: equity.', 'Bullish Momentum only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 40.52, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 19, 'lane_id': 'short_term', 'profit_factor': 4.04, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 38.5, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 15, 'lane_id': 'swing', 'profit_factor': 10.62, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 123.13, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'lane_a_chain_native_ret20_4_stop200_time75', 'profit_factor': 123.13, 'status': 'quarantine', 'symbol': 'QQQ', 'unresolved': 0}]}, {'symbol': 'QQQ', 'playbook_id': 'quality90_debit55_canary', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 39.61, 'quality_score': 91.9, 'guardrail_reasons': ['Quality90 Debit55 Canary only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 40.52, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 19, 'lane_id': 'short_term', 'profit_factor': 4.04, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 38.5, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 15, 'lane_id': 'swing', 'profit_factor': 10.62, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 123.13, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'lane_a_chain_native_ret20_4_stop200_time75', 'profit_factor': 123.13, 'status': 'quarantine', 'symbol': 'QQQ', 'unresolved': 0}]}, {'symbol': 'QQQ', 'playbook_id': 'speculative', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 38.8, 'quality_score': 68.0, 'guardrail_reasons': ['Quality score 68.0 is below the Speculative minimum of 70.0.', 'Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.'], 'matched_sleeves': [{'avg_pnl': 40.52, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 19, 'lane_id': 'short_term', 'profit_factor': 4.04, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 38.5, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 15, 'lane_id': 'swing', 'profit_factor': 10.62, 'status': 'watch', 'symbol': 'QQQ', 'unresolved': 0}, {'avg_pnl': 123.13, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'lane_a_chain_native_ret20_4_stop200_time75', 'profit_factor': 123.13, 'status': 'quarantine', 'symbol': 'QQQ', 'unresolved': 0}]}, {'symbol': 'SPY', 'playbook_id': 'bullish_momentum', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 39.8, 'quality_score': 92.0, 'guardrail_reasons': ['Bullish Momentum only allows asset classes: equity.', 'Bullish Momentum only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 44.48, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 14, 'lane_id': 'swing', 'profit_factor': 15.22, 'status': 'watch', 'symbol': 'SPY', 'unresolved': 0}, {'avg_pnl': 2.71, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'bearish_index_put_observation_chain_native_timeexit_all_sleeves', 'profit_factor': 2.71, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 14}, {'avg_pnl': 2.6, 'capture_tier': 'quarantine_do_not_chase', 'exact': 5, 'lane_id': 'regular_bearish_put_index_narrow_timeexit_all_sleeves', 'profit_factor': 1.14, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 6}]}, {'symbol': 'SPY', 'playbook_id': 'quality90_debit55_canary', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 42.0, 'quality_score': 92.0, 'guardrail_reasons': ['Quality90 Debit55 Canary only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 44.48, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 14, 'lane_id': 'swing', 'profit_factor': 15.22, 'status': 'watch', 'symbol': 'SPY', 'unresolved': 0}, {'avg_pnl': 2.71, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'bearish_index_put_observation_chain_native_timeexit_all_sleeves', 'profit_factor': 2.71, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 14}, {'avg_pnl': 2.6, 'capture_tier': 'quarantine_do_not_chase', 'exact': 5, 'lane_id': 'regular_bearish_put_index_narrow_timeexit_all_sleeves', 'profit_factor': 1.14, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 6}]}, {'symbol': 'SPY', 'playbook_id': 'short_term', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 46.9, 'quality_score': 60.3, 'guardrail_reasons': ['SPY is quarantined for Short-Term by the all-row profitability repair replay.', 'Profitability repair blocks spread debit 46.9% of width above 45.0%.'], 'matched_sleeves': [{'avg_pnl': 44.48, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 14, 'lane_id': 'swing', 'profit_factor': 15.22, 'status': 'watch', 'symbol': 'SPY', 'unresolved': 0}, {'avg_pnl': 2.71, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'bearish_index_put_observation_chain_native_timeexit_all_sleeves', 'profit_factor': 2.71, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 14}, {'avg_pnl': 2.6, 'capture_tier': 'quarantine_do_not_chase', 'exact': 5, 'lane_id': 'regular_bearish_put_index_narrow_timeexit_all_sleeves', 'profit_factor': 1.14, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 6}]}, {'symbol': 'SPY', 'playbook_id': 'speculative', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 39.7, 'quality_score': 81.6, 'guardrail_reasons': ['Speculative only surfaces high-convexity setups rated speculative on the risk/upside scale.'], 'matched_sleeves': [{'avg_pnl': 44.48, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 14, 'lane_id': 'swing', 'profit_factor': 15.22, 'status': 'watch', 'symbol': 'SPY', 'unresolved': 0}, {'avg_pnl': 2.71, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'bearish_index_put_observation_chain_native_timeexit_all_sleeves', 'profit_factor': 2.71, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 14}, {'avg_pnl': 2.6, 'capture_tier': 'quarantine_do_not_chase', 'exact': 5, 'lane_id': 'regular_bearish_put_index_narrow_timeexit_all_sleeves', 'profit_factor': 1.14, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 6}]}, {'symbol': 'SPY', 'playbook_id': 'tracked_winner_observation', 'capture_tier': 'blocked_but_interesting', 'guardrail_decision': 'blocked', 'match_type': 'symbol_only', 'debit_pct_of_width': 38.74, 'quality_score': 97.9, 'guardrail_reasons': ['Tracked Winner Observation only runs in bullish regimes.'], 'matched_sleeves': [{'avg_pnl': 44.48, 'capture_tier': 'tier_b_profitable_watch_repair', 'exact': 14, 'lane_id': 'swing', 'profit_factor': 15.22, 'status': 'watch', 'symbol': 'SPY', 'unresolved': 0}, {'avg_pnl': 2.71, 'capture_tier': 'quarantine_do_not_chase', 'exact': 1, 'lane_id': 'bearish_index_put_observation_chain_native_timeexit_all_sleeves', 'profit_factor': 2.71, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 14}, {'avg_pnl': 2.6, 'capture_tier': 'quarantine_do_not_chase', 'exact': 5, 'lane_id': 'regular_bearish_put_index_narrow_timeexit_all_sleeves', 'profit_factor': 1.14, 'status': 'quarantine', 'symbol': 'SPY', 'unresolved': 6}]}]`
- Live policy change: `False`

## Frozen Proof Judge

- Best variant: `lane_a_goal_stop200_time75_symbol_health90_backfill`
- Score/status: `0.0` / `scout_or_blocked`
- Clean/scout count: `0.0` / `191.0`
- Lane A conservative PF / zero-bid rate: `0.92` / `43.24%`
- Blockers: `['clean_trade_count_below_200', 'effective_unresolved_candidates_remain', 'rolling_oos_not_passed:lane_a_chain_native_ret20_4_stop200_time75', 'zero_bid_exit_rate_above_2pct', 'lane_a_conservative_pf_below_1_30']`

## Live Scan Starvation

- Status: `upstream_zero_candidate_scan_pressure`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `0` / `0`
- Guardrail starvation playbooks: `[]`
- Zero-candidate playbooks: `14`
- Leading drops: `[{'count': 106, 'value': 'momentum'}, {'count': 102, 'value': 'direction_filter'}, {'count': 84, 'value': 'option_liquidity'}, {'count': 55, 'value': 'history_or_liquidity'}, {'count': 29, 'value': 'tech_score'}, {'count': 20, 'value': 'direction_score'}, {'count': 6, 'value': 'ev_floor'}, {'count': 0, 'value': 'min_history'}]`

## Open Position Risk

- Open regular rows: `12`
- Evidence counts: `{'fresh_executable_review': 11, 'fresh_unpriced_review': 1}`
- Action counts: `{'hold_or_positive': 1, 'negative_mark_hold_or_unknown': 10, 'stored_non_executable_sell': 1}`
- Actionable open IDs: `[104]`
- Executable close-ready rows: `0`
- Review-required non-executable rows: `1`

## Suggested Trade Close Risk

- Open suggested rows: `1`
- Evidence counts: `{'missing_review': 1}`
- Action counts: `{'no_stored_review': 1}`
- Close-risk suggested IDs: `[]`
- Stale/missing review IDs: `[138]`
- Executable close-ready suggested rows: `0`
- Review-required suggested rows: `1`

## Trading Desk API Performance

- Status: `ok`
- Endpoints ok/errors: `11` / `0`
- Frontend max elapsed / total payload bytes: `230.6 ms` / `321783`
- Backend max duration header: `49.1 ms`
- Slowest frontend route: `{'label': 'next_suggested_trades_open', 'target': 'next_route', 'path': '/api/suggested-trades?status=open&compact=1', 'status_code': 200, 'elapsed_ms': 230.6, 'backend_duration_ms': 2.0, 'payload_bytes': 1368, 'row_count': 1, 'page': None}`
- Largest payload route: `{'label': 'backend_tracked_positions_closed_page_100', 'target': 'python_backend', 'path': '/api/positions?status=closed&limit=100&offset=0&compact=1', 'status_code': 200, 'elapsed_ms': 57.9, 'backend_duration_ms': 34.6, 'payload_bytes': 171667, 'row_count': 100, 'page': {'limit': 100, 'offset': 0, 'returned': 100}}`
- Cache stats: `{'memory_cache_entries': 0, 'memory_cache_families': {}, 'request_scope_active': False, 'request_scope_entries': 0, 'schema_initialized': False, 'status': 'ok', 'totals': {}}`

## AI Commodity OPRA Proof Lane

- Status: `recording_progress_waiting_for_exact_history_depth`
- Provider/source: `alpaca:sip:opra` / `alpaca_opra_daily_snapshot`
- Exact shared quote dates: `3` / `100` (remaining `97`)
- Verification/replay: `not_verified` / trades `None` / PF `None`
- Live/proof candidates: `0` / `0`
- Capture status: `no_rows_captured` target `2026-05-29` complete `False` missing symbols `24`
- Guarded command: status `ready_to_run_primary_next_execution` safe-now `True` next `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-29` not-before `2026-06-04T08:10:00-06:00`
- Safe to tune filters: `False`
- Top scan drops: `[{'drop_key': 'option_liquidity', 'count': 18, 'example_symbols': ['AA', 'ALB', 'BHP', 'CARR'], 'next_diagnostic_action': 'after_fresh_quotes_recheck_quote_age_then_structural_spread_distance'}, {'drop_key': 'momentum', 'count': 3, 'example_symbols': ['URA', 'VRT', 'VST'], 'next_diagnostic_action': 'review_commodity_momentum_distance_after_exact_replay_unlock'}, {'drop_key': 'tech_score', 'count': 3, 'example_symbols': ['CCJ', 'PWR', 'SLV'], 'next_diagnostic_action': 'review_commodity_tech_threshold_distance_after_exact_replay_unlock'}]`
- Blockers: `["capture_target_incomplete:['FCX', 'SLV', 'VRT', 'VST', 'ETN', 'GEV', 'PWR', 'CCJ', 'CEG', 'SCCO', 'COPX', 'URA', 'ALB', 'SQM', 'MP', 'RIO', 'BHP', 'TECK', 'AA', 'XME', 'NRG', 'NVT', 'CARR', 'TT']", 'shared_quote_dates:3/100', 'readiness:thin_required_history', 'replay_error:Imported historical validation has insufficient imported replay quote dates before replay under the requested trust scope. Selected dates: 3.', 'live_scan_candidates:0']`
- Failed goal requirements: `['full_scan_universe_is_exact_proof_scope', 'has_required_exact_alpaca_opra_history_depth', 'exact_replay_is_profitable', 'live_scan_has_verifiable_candidate', 'next_execution_contract_is_guarded']`

## Closed-Trade Follow-Up

- Negative trade rows audited: `213`
- Legacy missed-close targets: `3`
- Legacy missed-close recommendation: `no_broad_exit_policy_change; preserve as historical stale-policy diagnostic`
- Legacy current action required: `0`
- Broad exit promote candidates: `0`
- Legacy target positive replay rows: `36`

## Next Actions

- Do not close open rows from display-only marks; rerun explicit review during a fresh executable quote window for non-executable SELL or below-stop mark rows.
- Refresh stale or missing suggested-trade reviews before relying on suggested-trade P&L or close state.
- Treat legacy rows 26/39/44 as historical stale-policy diagnostics, not a broad current exit-policy change.
- Do not loosen promoted Trading Desk entry guardrails for the current no-pick state; investigate upstream scan/data/liquidity drops.
- Keep the short-term fill-degradation entry filter paper-only; the forward monitor is still collecting fresh rows.
- Keep the fill-degradation entry filter lane-scoped and paper-only; all-lane walk-forward rejects the broad fill>=15 rule and the frozen short-term rule is still mixed on historical folds.
- Keep the paper shortlist closed; there are no fresh executable Tier A lane matches eligible for paper review.
- Keep current-policy affected lanes on paper validation only until recovery gates pass with exact realized P&L evidence.
- Rerun source replays for exact-date repair-memory rows before treating any Tier B repair as graduated.
- Use the exact repair burn-down for new provider checks; target only active unexhausted exact contract/date rows.
- Use the profit capture queue to repair high-priority unresolved profitable watch sleeves before treating them as clean proof.
- Review fresh profit-capture signature matches as paper/research candidates only; do not treat Tier C matches as proof-grade recommendations.
- Keep blocked profitable-looking candidates blocked; inspect their guardrail reasons rather than loosening scanner policy from queue visibility alone.
- Do not tune Lane A entry/memory again; test a non-overlapping sleeve or materially different exit/liquidity rule.
- Do not promote a broad exit-policy replay; current candidates improve some rows but fail broader negative-rate/winner-loss checks.
- Run the allowed AI commodity guarded command and then rerun the next-execution readback: `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-29`.
- Repair the AI commodity exact OPRA capture failure before strategy tuning; the latest target capture did not advance shared quote dates.
