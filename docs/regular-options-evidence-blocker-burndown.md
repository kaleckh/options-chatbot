# Regular Options Evidence Blocker Burn-Down

No robust candidate passed. Source replay is the first blocker-burn-down step before any quote repair.

## Current Algorithm Status

- Overall status: `source_replay_required_before_repairs`.
- Hypothesis tournament: `paper_shadow_only`.
- Robust-edge discovery: `paper_shadow_only`.
- Best lane: `volatility_expansion_observation` / `paper_shadow_candidate`.
- Best PF / avg net P&L: `1.83` / `6.74`.
- Promotion ready: `False`.
- Live entry / auto-track / broker order allowed: `False` / `False` / `False`.

## Why No Robust Candidate Passed

- The current best lane is still paper-shadow/probation, not robust/live-ready.
- The historical combined candidate remains blocked by final-holdout depth and PF lower-bound quality.
- Source-quality, unpriced, zero-bid/tradability, lookahead-only, exhausted-source, stress, and concentration blockers remain separated rather than merged into a false positive.

## Ranked Repair Queue

| ID | Lane | Ticker | Contract | Date | Type | Actionability | Value | Next |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| repair-0001 | bullish_pullback_observation | AAPL | AAPL260116C00295000 | 2026-01-12 | source_replay_required | source_replay_first | high_proof_value | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0002 | bullish_pullback_observation | AAPL | AAPL260320C00300000 | 2026-03-12 | source_replay_required | source_replay_first | high_proof_value | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0003 | bullish_pullback_observation | UNH | UNH251128C00410000 | 2025-11-06 | source_replay_required | source_replay_first | high_proof_value | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0004 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251128C00495000 | 2025-11-05 | source_replay_required | source_replay_first | high_proof_value | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0005 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251219C00500000 | 2025-11-17 | source_replay_required | source_replay_first | high_proof_value | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0011 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251031C00485000 | 2025-09-26 | repairable_missing_quote | ready_for_plan_only_check | high_proof_value | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| repair-0012 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251107C00485000 | 2025-10-14 | repairable_missing_quote | ready_for_plan_only_check | high_proof_value | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| repair-0013 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251114C00485000 | 2025-10-14 | repairable_missing_quote | ready_for_plan_only_check | high_proof_value | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |

## Source Replay Queue

| ID | Lane | Ticker | Contract | Date | Next |
| --- | --- | --- | --- | --- | --- |
| repair-0001 | bullish_pullback_observation | AAPL | AAPL260116C00295000 | 2026-01-12 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0002 | bullish_pullback_observation | AAPL | AAPL260320C00300000 | 2026-03-12 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0003 | bullish_pullback_observation | UNH | UNH251128C00410000 | 2025-11-06 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0004 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251128C00495000 | 2025-11-05 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| repair-0005 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251219C00500000 | 2025-11-17 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |

## Do-Not-Repeat Exhausted Queue

| ID | Lane | Ticker | Contract | Date | Type | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| repair-0049 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260102C00355000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0050 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260102C00360000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0051 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260102C00365000 | 2025-12-23 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0052 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260213C00350000 | 2026-02-12 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0053 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260306C00365000 | 2026-02-27 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0054 | tracked_winner_chain_native_qqq_time80_intraday | GOOGL | GOOGL260306C00360000 | 2026-03-02 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0055 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260102C00355000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0056 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260102C00360000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0057 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260102C00365000 | 2025-12-23 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0058 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260213C00350000 | 2026-02-12 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0059 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260306C00365000 | 2026-02-27 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0060 | tracked_winner_cheap_debit_continuity_v1 | GOOGL | GOOGL260306C00360000 | 2026-03-02 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0061 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260102C00355000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0062 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260102C00360000 | 2025-12-22 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0063 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260102C00365000 | 2025-12-23 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0064 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260213C00350000 | 2026-02-12 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0065 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260306C00365000 | 2026-02-27 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0066 | tracked_winner_chain_native_qqq_time65_all_sleeves | GOOGL | GOOGL260306C00360000 | 2026-03-02 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0067 | bullish_pullback_observation | GOOGL | GOOGL260102C00350000 | 2025-12-29 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0068 | bullish_pullback_observation | GOOGL | GOOGL260109C00360000 | 2026-01-05 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0069 | bullish_pullback_observation | GOOGL | GOOGL260109C00355000 | 2026-01-06 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0078 | sleeve_next_defensive_refill_v1 | PM | PM260327C00200000 | 2026-03-19 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0079 | sleeve_next_move_bucket_refill_v1 | PM | PM260327C00200000 | 2026-03-19 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0080 | sleeve_next_defensive_refill_v1 | PM | PM260327C00190000 | 2026-03-20 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |
| repair-0081 | sleeve_next_move_bucket_refill_v1 | PM | PM260327C00190000 | 2026-03-20 | exhausted_current_source_no_match | Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence. |

Showing `25` of `278` rows.

## Zero-Bid/Tradability Failures

- Count: `2`.
- Zero-bid/non-executable rows are execution/tradability failures, not provider-missing rows.

## Diagnostic Lookahead-Only Queue

| ID | Lane | Ticker | Contract | Date | Type | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| repair-0006 | bullish_pullback_observation | CAT | CAT260327C00850000 | 2026-03-02 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0007 | bullish_pullback_observation | KO | KO260402C00084000 | 2026-03-18 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0008 | sleeve_next_industrial_cat_mixedexit_v1 | CAT | CAT260327C00850000 | 2026-03-02 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0009 | sleeve_next_industrial_cat_mixedexit_v1 | CAT | CAT260327C00860000 | 2026-03-02 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0010 | sleeve_next_index_with_iwm_spy_control_v1 | IWM | IWM260306C00276000 | 2026-03-03 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0014 | sleeve_next_defensive_wmt_mixedexit_v1 | WMT | WMT250912C00108000 | 2025-09-10 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0015 | bullish_pullback_observation | T | T251003C00031000 | 2025-09-25 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0016 | bullish_pullback_observation | T | T251003C00030000 | 2025-09-29 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0017 | bullish_pullback_observation | NEM | NEM251107C00093000 | 2025-10-27 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0018 | sleeve_next_defensive_refill_v1 | UNH | UNH251128C00385000 | 2025-11-19 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0019 | sleeve_next_index_refill_v1 | UNH | UNH251128C00385000 | 2025-11-19 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0020 | sleeve_next_move_bucket_refill_v1 | UNH | UNH251128C00385000 | 2025-11-19 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0021 | sleeve_next_reit_industrial_refill_v1 | UNH | UNH251128C00385000 | 2025-11-19 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0022 | bullish_pullback_observation | LLY | LLY260109C01155000 | 2025-12-10 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0023 | relative_strength_pullback_ex_clean_universe_v1 | WMT | WMT260402C00138000 | 2026-03-26 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0024 | bullish_pullback_observation | UNH | UNH251205C00390000 | 2025-11-20 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0025 | bullish_pullback_observation | IWM | IWM260306C00275000 | 2026-03-03 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0026 | iwm_small_cap_risk | IWM | IWM260306C00275000 | 2026-03-03 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0027 | sleeve_ticker_iwm | IWM | IWM260306C00275000 | 2026-03-03 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0028 | bullish_pullback_observation | IWM | IWM260313C00277500 | 2026-03-06 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0029 | iwm_small_cap_risk | IWM | IWM260313C00277500 | 2026-03-06 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0030 | sleeve_ticker_iwm | IWM | IWM260313C00277500 | 2026-03-06 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0031 | bullish_pullback_observation | PM | PM260327C00200000 | 2026-03-04 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0032 | sleeve_next_defensive_pm_mixedexit_v1 | PM | PM260327C00200000 | 2026-03-04 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |
| repair-0033 | bullish_pullback_observation | CAT | CAT260327C00840000 | 2026-03-09 | lookahead_only_not_proof | Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof. |

Showing `25` of `104` rows.

## Holdout Gap: 28 To 30 Analysis

- Current final-holdout rows: `28`.
- Target final-holdout rows: `30`.
- Gap rows: `2`.
- Actionable exact repair rows exposed: `8`.
- Can currently prove the exact 28-to-30 bridge: `True`.
- Conclusion: Local artifacts expose exact repair rows that may increase holdout count after source replay.

## PF Lower-Bound Gap: 0.61 To >1.0 Analysis

- Current PF lower bound: `0.61`.
- Target PF lower bound: `1.0`.
- Repairable exact blockers that could affect replay distribution: `8`.
- Count repair is not PF repair: `True`.
- Conclusion: Exact repairs may change replay distribution, but the current PF lower-bound blocker is strategy-quality/statistical until rerun evidence proves otherwise.

## Safe Plan-Only/Dry-Run Command Hints

- `uv run --locked python scripts/build_regular_options_repair_attempt_readback.py --no-write --json`
- `uv run --locked python scripts/build_regular_options_repair_burndown.py --no-write --json`
- `uv run --locked python scripts/build_regular_options_profit_capture_queue.py --no-write --json`
- `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --plan-only --json`
- `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --dry-run --json`

## Post-Repair Rerun Command Order

- `npm run options:features:regular-options`
- `npm run options:robust-search:regular-options`
- `npm run options:replay:regular-options-walk-forward`
- `npm run options:research:robust-edge`
- `npm run options:research:hypothesis-tournament`
- `npm run options:research:evidence-blocker-burndown`
- `npm run options:audit:monthly-profitability`

## What Not To Repair

- Do not repeat exhausted current-source exact-date loops without a new source or materially new evidence.
- Do not use lookahead-only rows as proof.
- Do not treat zero-bid/non-executable rows as missing data.
- Do not repair no-chase/quarantined lanes for promotion; keep them parked except for falsification.

## Source Artifacts And Staleness

| Path | Required | Status | Generated | Age Hours |
| --- | --- | --- | --- | --- |
| data/profitability-lab/regular-options-hypothesis-tournament/latest.json | True | loaded | 2026-06-18T06:09:54Z | 0.0 |
| data/profitability-lab/regular-options-robust-edge-discovery/latest.json | True | loaded | 2026-06-18T06:09:46Z | 0.0 |
| data/profitability-lab/regular-options-repair-burndown/latest.json | True | loaded | 2026-06-17T05:10:49Z | 24.99 |
| data/profitability-lab/regular-options-repair-attempts/latest.json | False | loaded | 2026-06-05T01:06:45Z | 317.05 |
| data/profitability-lab/regular-options-profit-capture-queue/latest.json | False | loaded | 2026-06-17T05:10:49Z | 24.99 |
| data/profitability-lab/regular-options-multilane/latest.json | False | stale |  |  |
| data/forward-tracking/monthly_all_lanes_profitability_audit_latest.json | False | loaded | 2026-06-18T02:49:24Z | 3.34 |
| data/forward-tracking/lane_promotion_state_latest.json | False | loaded | 2026-06-18T02:13:58Z | 3.93 |
| data/forward-tracking/regular_options_trade_qualification_latest.json | False | loaded | 2026-06-18T02:04:54Z | 4.09 |
| data/forward-tracking/regular_options_paper_shadow_evidence_plan_latest.json | False | loaded | 2026-06-18T02:04:58Z | 4.08 |
| data/forward-tracking/regular_options_market_window_evidence_checklist_latest.json | False | loaded | 2026-06-18T02:05:03Z | 4.08 |

## Non-Goals

- This workflow does not create trades.
- This workflow does not submit broker orders.
- This workflow does not enable auto-track.
- This workflow does not enable live validation.
- This workflow does not change scanner policy.
- This workflow does not change stops.
- This workflow does not change sizing.
- This workflow does not lower proof bars.
- This workflow does not mutate evidence databases.
- This workflow does not prove future profits with certainty.
