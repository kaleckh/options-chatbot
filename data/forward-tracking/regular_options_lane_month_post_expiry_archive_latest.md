# Regular Options Lane-Month Post-Expiry Archive

This report is generated from `scripts/build_regular_options_lane_month_post_expiry_archive.py`. It is a read-only archive for selected lane-month missing-P&L branches whose requested exact exit quote is after the encoded OCC contract expiration.

## Summary

- Status: `lane_month_post_expiry_archive_readback`.
- Overall status: `post_expiry_lane_month_branches_archived`.
- Source lane-month: `2025-10` / `tracked_winner_chain_native_research_all_sleeves`.
- Source true rows: `36`.
- Source missing rows: `5`.
- Feed readiness: `healthy`.
- Newly archived rows: `5`.
- Archived rows: `39`.
- Archived contract legs: `78`.
- Live policy change: `false`.

## Archived Branches

| Archive Key | Ticker | Entry | Exit | Exit UTC | Long Contract | Short Contract | Expiration | Reason |
|---|---|---:|---:|---:|---|---|---:|---|
| 2026-03\|bullish_pullback_observation\|AA\|2026-03-19\|2026-04-27\|AA260424C00062000\|AA260424C00067000 | AA | 2026-03-19 | 2026-04-27 | 2026-04-27T19:55:00Z | AA260424C00062000 | AA260424C00067000 | 2026-04-24 | exit_date_after_contract_expiration |
| 2026-03\|bullish_pullback_observation\|COIN\|2026-03-24\|2026-04-27\|COIN260424C00210000\|COIN260424C00225000 | COIN | 2026-03-24 | 2026-04-27 | 2026-04-27T19:55:00Z | COIN260424C00210000 | COIN260424C00225000 | 2026-04-24 | exit_date_after_contract_expiration |
| 2025-09\|bullish_pullback_observation\|TSLA\|2025-09-02\|2025-10-06\|TSLA251003C00335000\|TSLA251003C00365000 | TSLA | 2025-09-02 | 2025-10-06 | 2025-10-06T19:55:00Z | TSLA251003C00335000 | TSLA251003C00365000 | 2025-10-03 | exit_date_after_contract_expiration |
| 2025-09\|bullish_pullback_observation\|GOOGL\|2025-09-26\|2025-11-03\|GOOGL251031C00250000\|GOOGL251031C00270000 | GOOGL | 2025-09-26 | 2025-11-03 | 2025-11-03T20:55:00Z | GOOGL251031C00250000 | GOOGL251031C00270000 | 2025-10-31 | exit_date_after_contract_expiration |
| 2025-09\|bullish_pullback_observation\|PLTR\|2025-09-30\|2025-11-03\|PLTR251031C00182500\|PLTR251031C00200000 | PLTR | 2025-09-30 | 2025-11-03 | 2025-11-03T20:55:00Z | PLTR251031C00182500 | PLTR251031C00200000 | 2025-10-31 | exit_date_after_contract_expiration |
| 2025-09\|bullish_pullback_observation\|QQQ\|2025-09-30\|2025-11-03\|QQQ251031C00601000\|QQQ251031C00620000 | QQQ | 2025-09-30 | 2025-11-03 | 2025-11-03T20:55:00Z | QQQ251031C00601000 | QQQ251031C00620000 | 2025-10-31 | exit_date_after_contract_expiration |
| 2025-10\|bullish_pullback_observation\|JPM\|2025-10-06\|2025-11-17\|JPM251114C00310000\|JPM251114C00330000 | JPM | 2025-10-06 | 2025-11-17 | 2025-11-17T20:55:00Z | JPM251114C00310000 | JPM251114C00330000 | 2025-11-14 | exit_date_after_contract_expiration |
| 2025-10\|bullish_pullback_observation\|LLY\|2025-10-14\|2025-11-24\|LLY251121C00830000\|LLY251121C00910000 | LLY | 2025-10-14 | 2025-11-24 | 2025-11-24T20:55:00Z | LLY251121C00830000 | LLY251121C00910000 | 2025-11-21 | exit_date_after_contract_expiration |
| 2025-10\|bullish_pullback_observation\|LLY\|2025-10-16\|2025-11-24\|LLY251121C00840000\|LLY251121C00920000 | LLY | 2025-10-16 | 2025-11-24 | 2025-11-24T20:55:00Z | LLY251121C00840000 | LLY251121C00920000 | 2025-11-21 | exit_date_after_contract_expiration |
| 2025-10\|bullish_pullback_observation\|CAT\|2025-10-27\|2025-12-01\|CAT251128C00530000\|CAT251128C00575000 | CAT | 2025-10-27 | 2025-12-01 | 2025-12-01T20:55:00Z | CAT251128C00530000 | CAT251128C00575000 | 2025-11-28 | exit_date_after_contract_expiration |
| 2025-11\|bullish_pullback_observation\|GOOGL\|2025-11-10\|2025-12-15\|GOOGL251212C00285000\|GOOGL251212C00310000 | GOOGL | 2025-11-10 | 2025-12-15 | 2025-12-15T20:55:00Z | GOOGL251212C00285000 | GOOGL251212C00310000 | 2025-12-12 | exit_date_after_contract_expiration |
| 2025-11\|bullish_pullback_observation\|GOOGL\|2025-11-19\|2025-12-29\|GOOGL251226C00295000\|GOOGL251226C00320000 | GOOGL | 2025-11-19 | 2025-12-29 | 2025-12-29T20:55:00Z | GOOGL251226C00295000 | GOOGL251226C00320000 | 2025-12-26 | exit_date_after_contract_expiration |
| 2025-12\|bullish_pullback_observation\|GOOGL\|2025-12-15\|2026-01-20\|GOOGL260116C00315000\|GOOGL260116C00345000 | GOOGL | 2025-12-15 | 2026-01-20 | 2026-01-20T20:55:00Z | GOOGL260116C00315000 | GOOGL260116C00345000 | 2026-01-16 | exit_date_after_contract_expiration |
| 2025-12\|bullish_pullback_observation\|SLB\|2025-12-26\|2026-02-02\|SLB260130C00039000\|SLB260130C00042000 | SLB | 2025-12-26 | 2026-02-02 | 2026-02-02T20:55:00Z | SLB260130C00039000 | SLB260130C00042000 | 2026-01-30 | exit_date_after_contract_expiration |
| 2025-12\|bullish_pullback_observation\|SLB\|2025-12-29\|2026-02-09\|SLB260206C00039000\|SLB260206C00042000 | SLB | 2025-12-29 | 2026-02-09 | 2026-02-09T20:55:00Z | SLB260206C00039000 | SLB260206C00042000 | 2026-02-06 | exit_date_after_contract_expiration |
| 2025-12\|bullish_pullback_observation\|SLB\|2025-12-30\|2026-02-09\|SLB260206C00039000\|SLB260206C00042000 | SLB | 2025-12-30 | 2026-02-09 | 2026-02-09T20:55:00Z | SLB260206C00039000 | SLB260206C00042000 | 2026-02-06 | exit_date_after_contract_expiration |
| 2026-01\|bullish_pullback_observation\|AA\|2026-01-02\|2026-02-02\|AA260130C00055000\|AA260130C00060000 | AA | 2026-01-02 | 2026-02-02 | 2026-02-02T20:55:00Z | AA260130C00055000 | AA260130C00060000 | 2026-01-30 | exit_date_after_contract_expiration |
| 2026-01\|bullish_pullback_observation\|FCX\|2026-01-02\|2026-02-09\|FCX260206C00052000\|FCX260206C00057000 | FCX | 2026-01-02 | 2026-02-09 | 2026-02-09T20:55:00Z | FCX260206C00052000 | FCX260206C00057000 | 2026-02-06 | exit_date_after_contract_expiration |
| 2026-01\|bullish_pullback_observation\|FCX\|2026-01-05\|2026-02-17\|FCX260213C00054000\|FCX260213C00059000 | FCX | 2026-01-05 | 2026-02-17 | 2026-02-17T20:55:00Z | FCX260213C00054000 | FCX260213C00059000 | 2026-02-13 | exit_date_after_contract_expiration |
| 2026-01\|bullish_pullback_observation\|PM\|2026-01-09\|2026-02-17\|PM260213C00160000\|PM260213C00175000 | PM | 2026-01-09 | 2026-02-17 | 2026-02-17T20:55:00Z | PM260213C00160000 | PM260213C00175000 | 2026-02-13 | exit_date_after_contract_expiration |
| 2026-01\|bullish_pullback_observation\|FCX\|2026-01-23\|2026-03-02\|FCX260227C00061000\|FCX260227C00066000 | FCX | 2026-01-23 | 2026-03-02 | 2026-03-02T20:55:00Z | FCX260227C00061000 | FCX260227C00066000 | 2026-02-27 | exit_date_after_contract_expiration |
| 2026-02\|bullish_pullback_observation\|OXY\|2026-02-06\|2026-03-09\|OXY260306C00046000\|OXY260306C00050000 | OXY | 2026-02-06 | 2026-03-09 | 2026-03-09T19:55:00Z | OXY260306C00046000 | OXY260306C00050000 | 2026-03-06 | exit_date_after_contract_expiration |
| 2026-02\|bullish_pullback_observation\|RTX\|2026-02-06\|2026-03-16\|RTX260313C00200000\|RTX260313C00215000 | RTX | 2026-02-06 | 2026-03-16 | 2026-03-16T19:55:00Z | RTX260313C00200000 | RTX260313C00215000 | 2026-03-13 | exit_date_after_contract_expiration |
| 2026-02\|bullish_pullback_observation\|RTX\|2026-02-09\|2026-03-16\|RTX260313C00200000\|RTX260313C00215000 | RTX | 2026-02-09 | 2026-03-16 | 2026-03-16T19:55:00Z | RTX260313C00200000 | RTX260313C00215000 | 2026-03-13 | exit_date_after_contract_expiration |
| 2026-02\|bullish_pullback_observation\|COP\|2026-02-18\|2026-03-30\|COP260327C00112000\|COP260327C00122000 | COP | 2026-02-18 | 2026-03-30 | 2026-03-30T19:55:00Z | COP260327C00112000 | COP260327C00122000 | 2026-03-27 | exit_date_after_contract_expiration |
| 2026-02\|bullish_pullback_observation\|COP\|2026-02-26\|2026-04-06\|COP260402C00110000\|COP260402C00120000 | COP | 2026-02-26 | 2026-04-06 | 2026-04-06T19:55:00Z | COP260402C00110000 | COP260402C00120000 | 2026-04-02 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|DIA\|2025-08-14\|2025-09-22\|DIA250919C00450000\|DIA250919C00465000 | DIA | 2025-08-14 | 2025-09-22 | 2025-09-22T19:55:00Z | DIA250919C00450000 | DIA250919C00465000 | 2025-09-19 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|SPY\|2025-08-14\|2025-09-22\|SPY250919C00645000\|SPY250919C00665000 | SPY | 2025-08-14 | 2025-09-22 | 2025-09-22T19:55:00Z | SPY250919C00645000 | SPY250919C00665000 | 2025-09-19 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|DIA\|2025-08-18\|2025-09-22\|DIA250919C00451000\|DIA250919C00465000 | DIA | 2025-08-18 | 2025-09-22 | 2025-09-22T19:55:00Z | DIA250919C00451000 | DIA250919C00465000 | 2025-09-19 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|SPY\|2025-08-18\|2025-09-22\|SPY250919C00646000\|SPY250919C00665000 | SPY | 2025-08-18 | 2025-09-22 | 2025-09-22T19:55:00Z | SPY250919C00646000 | SPY250919C00665000 | 2025-09-19 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|NVDA\|2025-08-27\|2025-10-06\|NVDA251003C00185000\|NVDA251003C00200000 | NVDA | 2025-08-27 | 2025-10-06 | 2025-10-06T19:55:00Z | NVDA251003C00185000 | NVDA251003C00200000 | 2025-10-03 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|GOOGL\|2025-08-27\|2025-10-06\|GOOGL251003C00205000\|GOOGL251003C00220000 | GOOGL | 2025-08-27 | 2025-10-06 | 2025-10-06T19:55:00Z | GOOGL251003C00205000 | GOOGL251003C00220000 | 2025-10-03 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|NVDA\|2025-08-28\|2025-10-06\|NVDA251003C00180000\|NVDA251003C00195000 | NVDA | 2025-08-28 | 2025-10-06 | 2025-10-06T19:55:00Z | NVDA251003C00180000 | NVDA251003C00195000 | 2025-10-03 | exit_date_after_contract_expiration |
| 2025-08\|tracked_winner_chain_native_research_all_sleeves\|NVDA\|2025-08-29\|2025-10-06\|NVDA251003C00180000\|NVDA251003C00195000 | NVDA | 2025-08-29 | 2025-10-06 | 2025-10-06T19:55:00Z | NVDA251003C00180000 | NVDA251003C00195000 | 2025-10-03 | exit_date_after_contract_expiration |
| 2025-10\|tracked_winner_chain_native_research_all_sleeves\|GOOGL\|2025-10-20\|2025-11-24\|GOOGL251121C00257500\|GOOGL251121C00275000 | GOOGL | 2025-10-20 | 2025-11-24 | 2025-11-24T20:55:00Z | GOOGL251121C00257500 | GOOGL251121C00275000 | 2025-11-21 | exit_date_after_contract_expiration |
| 2025-10\|tracked_winner_chain_native_research_all_sleeves\|GOOGL\|2025-10-21\|2025-11-24\|GOOGL251121C00257500\|GOOGL251121C00275000 | GOOGL | 2025-10-21 | 2025-11-24 | 2025-11-24T20:55:00Z | GOOGL251121C00257500 | GOOGL251121C00275000 | 2025-11-21 | exit_date_after_contract_expiration |
| 2025-10\|tracked_winner_chain_native_research_all_sleeves\|DIA\|2025-10-27\|2025-12-01\|DIA251128C00477000\|DIA251128C00490000 | DIA | 2025-10-27 | 2025-12-01 | 2025-12-01T20:55:00Z | DIA251128C00477000 | DIA251128C00490000 | 2025-11-28 | exit_date_after_contract_expiration |
| 2025-10\|tracked_winner_chain_native_research_all_sleeves\|GOOGL\|2025-10-27\|2025-12-08\|GOOGL251205C00265000\|GOOGL251205C00290000 | GOOGL | 2025-10-27 | 2025-12-08 | 2025-12-08T20:55:00Z | GOOGL251205C00265000 | GOOGL251205C00290000 | 2025-12-05 | exit_date_after_contract_expiration |
| 2025-10\|tracked_winner_chain_native_research_all_sleeves\|GOOGL\|2025-10-29\|2025-12-08\|GOOGL251205C00270000\|GOOGL251205C00290000 | GOOGL | 2025-10-29 | 2025-12-08 | 2025-12-08T20:55:00Z | GOOGL251205C00270000 | GOOGL251205C00290000 | 2025-12-05 | exit_date_after_contract_expiration |

## Boundary

This archive is read-only. It does not create trades, submit broker orders, mutate trading rows, change scanner or contract-selection policy, change stops or sizing, lower exact OPRA/NBBO proof bars, or count post-expiry no-match rows as production proof.

