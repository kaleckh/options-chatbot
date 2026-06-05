# Regular Options Exact Repair Burn-Down

This report is generated from `scripts/build_regular_options_repair_burndown.py`. It ranks exact-date proof repair work for regular supervised options and keeps exhausted or lookahead-only rows out of the active import loop. It is not a trade recommendation, entry/exit instruction, or sizing signal.

## Summary

- Status: `repair_burndown_ready`.
- Active exact repair targets: `11`.
- Source replay required targets: `5`.
- Diagnostic lookahead-only targets: `32`.
- Exhausted current-source targets: `97`.
- Missing target-detail rows: `0`.
- Repair-attempt memory unavailable rows: `0`.
- Burn-down statuses: `{"active_unattempted_exact_repair": 11, "diagnostic_lookahead_only_not_exact_proof": 32, "excluded_current_source_exhausted": 97, "source_replay_required_before_graduation": 5}`.
- Evidence repair priorities: `{"high": 46, "medium": 99}`.
- Latest keyed repair attempts: `7212` from `156` summaries.
- Next operator step: Rerun source replay for rows with exact-date repair memory before importing more data.
- Live policy change: `False`.

## Proof Policy

- Active work is limited to unexhausted exact missing contract/date targets.
- Lookahead-only rows are diagnostic and never repair the exact missing proof date.
- Current-source no-match rows must not be repeated without a new exact source or materially new evidence.
- Exact-date rows already found or imported still require rerunning the source replay and rebuilding the queue before any Tier B graduation discussion.
- Missing or unreadable repair-attempt memory fails closed and emits no active provider commands.
- This report is paper/proof repair memory only; it does not alter scanner, broker, stop, auth, database, proof-bar, trade recommendation, entry/exit, or sizing behavior.

## Active Exact Repair Targets

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| active_unattempted_exact_repair | medium | CAT | bullish_pullback_observation | 2026-03-02 | CAT260327C00850000 | 3 | 7 | 116.08 | 38.69 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | KO | bullish_pullback_observation | 2026-03-18 | KO260402C00084000 | 2 | 4 | 19.14 | 9.57 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | CAT | sleeve_next_industrial_cat_mixedexit_v1 | 2026-03-02 | CAT260327C00850000 | 3 | 6 | 8.21 | 16.73 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | CAT | sleeve_next_industrial_cat_mixedexit_v1 | 2026-03-02 | CAT260327C00860000 | 3 | 6 | 8.21 | 16.73 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | IWM | sleeve_next_index_with_iwm_spy_control_v1 | 2026-03-03 | IWM260306C00276000 | 10 | 3 | 1.94 | 19.59 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | DIA | tracked_winner_cheap_debit_continuity_v1 | 2025-09-26 | DIA251031C00485000 | 22 | 10 | 1.88 | 10.76 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | DIA | tracked_winner_cheap_debit_continuity_v1 | 2025-10-14 | DIA251107C00485000 | 22 | 10 | 1.88 | 10.76 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | DIA | tracked_winner_cheap_debit_continuity_v1 | 2025-10-14 | DIA251114C00485000 | 22 | 10 | 1.88 | 10.76 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | WMT | sleeve_next_defensive_wmt_mixedexit_v1 | 2025-09-10 | WMT250912C00108000 | 11 | 9 | 1.58 | 10.41 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | T | bullish_pullback_observation | 2025-09-25 | T251003C00031000 | 2 | 7 | 3.62 | 1.28 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |
| active_unattempted_exact_repair | medium | T | bullish_pullback_observation | 2025-09-29 | T251003C00030000 | 2 | 7 | 3.62 | 1.28 | 0 | Run the plan-only command first, then exact dry-run/import only if the source can answer the same missing contract/date. Rerun the source replay before any graduation discussion. |

## Source Replay Required

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| source_replay_required_before_graduation | high | AAPL | bullish_pullback_observation | 2026-01-12 | AAPL260116C00295000 | 11 | 2 | 273.54 | 24.87 | 5 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| source_replay_required_before_graduation | high | AAPL | bullish_pullback_observation | 2026-03-12 | AAPL260320C00300000 | 11 | 2 | 273.54 | 24.87 | 5 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| source_replay_required_before_graduation | high | UNH | bullish_pullback_observation | 2025-11-06 | UNH251128C00410000 | 8 | 2 | 2.08 | 29.86 | 5 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| source_replay_required_before_graduation | medium | DIA | tracked_winner_cheap_debit_continuity_v1 | 2025-11-05 | DIA251128C00495000 | 22 | 10 | 1.88 | 10.76 | 1 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |
| source_replay_required_before_graduation | medium | DIA | tracked_winner_cheap_debit_continuity_v1 | 2025-11-17 | DIA251219C00500000 | 22 | 10 | 1.88 | 10.76 | 1 | Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue before treating this row as repaired. |

## Diagnostic Lookahead Only

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| diagnostic_lookahead_only_not_exact_proof | high | NEM | bullish_pullback_observation | 2025-10-27 | NEM251107C00093000 | 15 | 1 | 12.46 | 68.81 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | UNH | sleeve_next_defensive_refill_v1 | 2025-11-19 | UNH251128C00385000 | 9 | 1 | 4.9 | 51.6 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | UNH | sleeve_next_index_refill_v1 | 2025-11-19 | UNH251128C00385000 | 9 | 1 | 4.9 | 51.6 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | UNH | sleeve_next_move_bucket_refill_v1 | 2025-11-19 | UNH251128C00385000 | 9 | 1 | 4.9 | 51.6 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | UNH | sleeve_next_reit_industrial_refill_v1 | 2025-11-19 | UNH251128C00385000 | 9 | 1 | 4.9 | 51.6 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | LLY | bullish_pullback_observation | 2025-12-10 | LLY260109C01155000 | 9 | 1 | 2.89 | 37.97 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | WMT | relative_strength_pullback_ex_clean_universe_v1 | 2026-03-26 | WMT260402C00138000 | 9 | 3 | 3.53 | 24.77 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | UNH | bullish_pullback_observation | 2025-11-20 | UNH251205C00390000 | 8 | 2 | 2.08 | 29.86 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | bullish_pullback_observation | 2026-03-03 | IWM260306C00275000 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | iwm_small_cap_risk | 2026-03-03 | IWM260306C00275000 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | sleeve_ticker_iwm | 2026-03-03 | IWM260306C00275000 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | bullish_pullback_observation | 2026-03-06 | IWM260313C00277500 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | iwm_small_cap_risk | 2026-03-06 | IWM260313C00277500 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | high | IWM | sleeve_ticker_iwm | 2026-03-06 | IWM260313C00277500 | 11 | 4 | 2.47 | 22.44 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | PM | bullish_pullback_observation | 2026-03-04 | PM260327C00200000 | 4 | 3 | 205.02 | 51.25 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | PM | sleeve_next_defensive_pm_mixedexit_v1 | 2026-03-04 | PM260327C00200000 | 4 | 3 | 153.2 | 38.3 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | CAT | bullish_pullback_observation | 2026-03-09 | CAT260327C00840000 | 3 | 7 | 116.08 | 38.69 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | CAT | bullish_pullback_observation | 2026-03-18 | CAT260402C00810000 | 3 | 7 | 116.08 | 38.69 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | KO | bullish_pullback_observation | 2025-11-03 | KO251205C00074000 | 2 | 4 | 19.14 | 9.57 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |
| diagnostic_lookahead_only_not_exact_proof | medium | PLD | bullish_pullback_observation | 2025-09-30 | PLD251017C00125000 | 4 | 1 | 3.77 | 9.37 | 5 | Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof. |

## Exhausted Current Source

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2025-12-22 | GOOGL260102C00355000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2025-12-22 | GOOGL260102C00360000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2025-12-23 | GOOGL260102C00365000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2026-02-12 | GOOGL260213C00350000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2026-02-27 | GOOGL260306C00365000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | 2026-03-02 | GOOGL260306C00360000 | 34 | 8 | 7.4 | 51.31 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2025-12-22 | GOOGL260102C00355000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2025-12-22 | GOOGL260102C00360000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2025-12-23 | GOOGL260102C00365000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2026-02-12 | GOOGL260213C00350000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2026-02-27 | GOOGL260306C00365000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_cheap_debit_continuity_v1 | 2026-03-02 | GOOGL260306C00360000 | 35 | 7 | 3.15 | 31.4 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2025-12-22 | GOOGL260102C00355000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2025-12-22 | GOOGL260102C00360000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2025-12-23 | GOOGL260102C00365000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2026-02-12 | GOOGL260213C00350000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2026-02-27 | GOOGL260306C00365000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | tracked_winner_chain_native_qqq_time65_all_sleeves | 2026-03-02 | GOOGL260306C00360000 | 35 | 7 | 3.1 | 30.57 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | bullish_pullback_observation | 2025-12-29 | GOOGL260102C00350000 | 18 | 4 | 2.96 | 39.78 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |
| excluded_current_source_exhausted | high | GOOGL | bullish_pullback_observation | 2026-01-05 | GOOGL260109C00360000 | 18 | 4 | 2.96 | 39.78 | 5 | Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence. |

## Target Details Missing

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|

## Repair-Attempt Memory Unavailable

| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|

## Inputs

| Source | Status | Generated | Path |
|---|---|---|---|
| regular_options_profit_capture_queue | ok | 2026-06-05T01:06:55Z | data/profitability-lab/regular-options-profit-capture-queue/latest.json |
| regular_options_repair_attempt_readback | ok | 2026-06-05T01:06:45Z | data/profitability-lab/regular-options-repair-attempts/latest.json |
