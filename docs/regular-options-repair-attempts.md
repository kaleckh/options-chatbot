# Regular Options Repair Attempts

This report is generated from `scripts/build_regular_options_repair_attempt_readback.py`. It is a repair-memory/readback layer for regular options proof work, not a scanner or broker-action surface.

## Summary

- Latest attempts: `7212`.
- Input summaries scanned: `156`.
- Latest outcomes: `{"exact_date_no_match": 4754, "imported_pending_replay": 517, "lookahead_only_rows_found": 1941}`.
- Latest proof repair statuses: `{"current_source_exhausted": 4754, "exact_date_imported_pending_replay": 517, "lookahead_only_not_exact_proof": 1941}`.
- Current-source exhausted exact dates: `6695`.
- Exact-date rows found: `95430`.
- Lookahead-only rows found: `225697`.

## Outcome Matrix

| Outcome | Meaning | Proof posture |
|---|---|---|
| `imported_pending_replay` | Exact missing-date rows were imported. | Rerun the source replay before graduation. |
| `exact_date_rows_found` | Exact missing-date rows were found in dry-run. | Candidate only until imported and replayed. |
| `lookahead_only_rows_found` | Later dates had rows, missing date did not. | Diagnostic only; not proof repair. |
| `exact_date_no_match` | Current source returned no exact rows. | Exhausted for this source/date until new evidence exists. |
| `planned_not_requested` | Plan-only target; no provider request. | No proof change. |

## Latest Attempts

| Outcome | Proof status | Ticker | Contract | Missing date | Exact rows | Lookahead rows | First later date | Source |
|---|---|---|---|---|---:|---:|---|---|
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00595000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00600000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251003C00595000 | 2025-09-02 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251024C00618000 | 2025-09-25 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251031C00594000 | 2025-10-27 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251031C00625000 | 2025-09-24 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251107C00625000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251114C00630000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251121C00635000 | 2025-10-23 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00640000 | 2025-11-07 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00645000 | 2025-11-05 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00665000 | 2025-11-04 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251205C00660000 | 2025-11-04 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ260123C00641000 | 2026-01-20 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ260130C00646000 | 2025-12-29 | 0 | 1 |  | data/options-validation/runs/20260526_022852_tracked_winner_chain_native_qqq_time60_debit60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00595000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00600000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251003C00595000 | 2025-09-02 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251024C00618000 | 2025-09-25 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251031C00594000 | 2025-10-27 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251031C00625000 | 2025-09-24 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251107C00625000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251114C00630000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251121C00635000 | 2025-10-23 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00640000 | 2025-11-07 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00645000 | 2025-11-05 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251128C00665000 | 2025-11-04 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ251205C00660000 | 2025-11-04 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ260123C00641000 | 2026-01-20 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ260130C00646000 | 2025-12-29 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY250919C00665000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY250926C00660000 | 2025-08-21 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251003C00666000 | 2025-09-02 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251031C00684000 | 2025-09-25 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251107C00686000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251107C00687000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251114C00687000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251128C00701000 | 2025-11-05 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251128C00706000 | 2025-11-04 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY251205C00715000 | 2025-10-30 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY260123C00708000 | 2026-01-20 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | SPY | SPY260130C00712000 | 2026-01-02 | 0 | 1 |  | data/options-validation/runs/20260526_022857_tracked_winner_chain_native_spy_qqq_time60_ret20_watch_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251114C00480000 | 2025-10-13 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251128C00481000 | 2025-11-21 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251128C00490000 | 2025-11-18 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251205C00487500 | 2025-11-18 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251205C00489000 | 2025-11-18 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251205C00490000 | 2025-11-18 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251212C00490000 | 2025-11-07 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA251219C00495000 | 2025-11-18 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | DIA | DIA260102C00495000 | 2025-12-31 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260116C00510000 | 2025-12-16 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260130C00505000 | 2026-01-02 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260206C00510000 | 2026-01-21 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260213C00510000 | 2026-01-21 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260320C00520000 | 2026-02-24 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | DIA | DIA260320C00525000 | 2026-02-24 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | DIA | DIA260331C00515000 | 2026-03-17 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260102C00355000 | 2025-12-22 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260102C00360000 | 2025-12-22 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260102C00365000 | 2025-12-23 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260109C00360000 | 2025-12-24 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260213C00350000 | 2026-02-12 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260220C00350000 | 2026-02-18 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260306C00360000 | 2026-03-02 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | GOOGL | GOOGL260306C00365000 | 2026-02-27 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA251114C00215000 | 2025-11-13 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA251128C00215000 | 2025-11-25 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA251205C00230000 | 2025-11-28 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA251205C00235000 | 2025-11-28 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260130C00210000 | 2026-01-29 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260306C00210000 | 2026-03-04 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260306C00215000 | 2026-03-03 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260320C00210000 | 2026-03-19 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260320C00220000 | 2026-03-18 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| exact_date_no_match | current_source_exhausted | NVDA | NVDA260402C00220000 | 2026-03-26 | 0 | 0 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00595000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250919C00600000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250926C00600000 | 2025-08-20 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |
| lookahead_only_rows_found | lookahead_only_not_exact_proof | QQQ | QQQ250930C00595000 | 2025-09-02 | 0 | 1 |  | data/options-validation/runs/20260526_022915_tracked_winner_chain_native_qqq_time80_research_intraday.json |

## Inputs

| Status | Generated | Attempts | Path |
|---|---|---:|---|
| ok | 2026-05-29T04:27:12.582006Z | 15 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T042707Z.json |
| ok | 2026-05-29T05:08:11.560245Z | 97 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T050747Z.json |
| ok | 2026-05-29T05:15:37.716334Z | 71 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T051508Z.json |
| ok | 2026-05-30T00:00:32.297057Z | 10 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json |
| ok | 2026-05-30T22:41:46.775156Z | 125 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224027Z.json |
| ok | 2026-05-30T22:43:53.011062Z | 122 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224330Z.json |
| ok | 2026-05-30T22:47:07.748956Z | 17 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224659Z.json |
| ok | 2026-05-31T01:06:57.063980Z | 123 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T010645Z.json |
| ok | 2026-05-31T01:12:19.564388Z | 120 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011208Z.json |
| ok | 2026-05-31T01:14:06.008590Z | 120 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011246Z.json |
| ok | 2026-05-31T01:17:55.968897Z | 113 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011611Z.json |
| ok | 2026-06-02T13:54:22.031343Z | 421 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260602T135406Z.json |
| ok | 2026-06-02T17:05:32.477606Z | 83 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260602T170524Z.json |
| ok | 2026-06-04T18:27:33.794877Z | 1 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T182733Z.json |
| ok | 2026-06-04T18:27:48.393392Z | 1 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T182747Z.json |
| ok | 2026-06-04T18:31:47.917836Z | 1 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183147Z.json |
| ok | 2026-06-04T18:32:32.595256Z | 2 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183231Z.json |
| ok | 2026-06-04T18:33:40.635021Z | 2 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183339Z.json |
| ok | 2026-06-04T18:46:25.356933Z | 2 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T184624Z.json |
| ok | 2026-06-04T18:47:26.228489Z | 2 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T184725Z.json |

Older input summaries omitted from this Markdown table: `136`.
