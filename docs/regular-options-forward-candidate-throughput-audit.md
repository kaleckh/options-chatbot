# Regular Options Forward Candidate Throughput Audit

Status: `blocked_no_same_day_phase2_natural_selections`.

- Target selection date: `2026-06-26`.
- Scan-pick rows: `550`.
- Post-freeze scan-pick rows: `4`.
- Post-freeze Phase 2 rows: `1`.
- Target-date rows: `0`.
- Target-date Phase 2 rows: `0`.
- Scheduled Phase 2 sessions: `2`.
- Scheduled Phase 2 raw candidates: `0`.
- Scheduled Phase 2 returned picks: `0`.
- Scheduled Phase 2 drop-count total: `63`.
- Scheduled Phase 2 drop-stage status: `candidate_starvation_from_scan_filters`.
- Scheduled Phase 2 symbol drop reasons: `0`.
- Scheduled Phase 2 near-miss status: `near_miss_table_waiting_for_symbol_drop_reasons`.
- Candidate-starvation evidence status: `stage_counts_only_waiting_for_symbol_drop_reasons`.
- Zero-candidate diagnostics: `opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons`.
- Scheduled Phase 2 scan picks: `0`.
- Scheduled Phase 2 all lanes scanned: `true`.
- Scheduled Phase 2 eligibility statuses: `{'ineligible': 2}`.
- Candidate rows staged: `0`.
- Candidate JSONL written: `false`.
- Cohort append performed: `false`.
- Next action: `wait_for_valid_market_window_and_real_phase2_scan_picks`.

## Scheduled Sessions

- `bullish_pullback_observation` session `8293`: `0` picks, `ineligible`, `0` symbol drop reasons. blockers `policy_not_applied, missing_truth_source, missing_promotion_status, unknown_quote_freshness, no_scan_picks`
- `volatility_expansion_observation` session `8294`: `0` picks, `ineligible`, `0` symbol drop reasons. blockers `policy_not_applied, missing_truth_source, missing_promotion_status, unknown_quote_freshness, no_scan_picks`

## Scheduled Eligibility Blockers

- `missing_promotion_status`: `2`.
- `missing_truth_source`: `2`.
- `no_scan_picks`: `2`.
- `policy_not_applied`: `2`.
- `unknown_quote_freshness`: `2`.

## Scheduled Drop Counts

- `direction_filter`: `0`.
- `direction_score`: `1`.
- `earnings`: `0`.
- `ev_floor`: `1`.
- `exceptions`: `0`.
- `guardrails`: `0`.
- `history_or_liquidity`: `8`.
- `iv_crush_penalty`: `0`.
- `min_history`: `0`.
- `momentum`: `50`.
- `option_liquidity`: `1`.
- `signal_index`: `0`.
- `stop_cooldown`: `0`.
- `tech_score`: `2`.
- `ticker_regime_filter`: `0`.
- `ticker_vol_filter`: `0`.

## Aggregate Candidate-Starvation Stages

- `momentum`: `50`.
- `history_or_liquidity`: `8`.
- `tech_score`: `2`.
- `direction_score`: `1`.
- `ev_floor`: `1`.

## Zero-Candidate Diagnostics

- Status: `opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons`.
- Scope: allowed lanes `true`, target date `true`, post-freeze `true`.
- Scheduled sessions reviewed: `2`.
- Symbol drop-reason status: `missing_symbol_drop_reasons_for_aggregate_drops`.
- Safe next read-only actions: `wait_for_future_scheduled_sessions_with_symbol_drop_reason_persistence`, `inspect_existing_aggregate_drop_stage_counts_read_only`.

## Ranked Symbol Near Misses

- Status: `near_miss_table_waiting_for_symbol_drop_reasons`.

## Rejection Counts

- `non_phase2_lane`: `468`.
- `non_preregistered_symbol`: `50`.
- `not_current_market_window_selection`: `1`.
- `pre_freeze_selection`: `31`.

This is a read-only throughput audit. It does not run the scanner, create trades, append cohort rows, import quotes, mutate evidence stores, change scanner policy, or promote a lane.
