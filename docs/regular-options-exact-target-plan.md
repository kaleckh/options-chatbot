# Regular Options Exact Target Plan

This report is generated from `scripts/build_regular_options_exact_target_plan.py`. It is read-only: it extracts exact target rows from existing replay artifacts and does not request quotes, import quotes, mutate evidence stores, change policy, consume protected holdout, or make production proof claims.

## Summary

- Status: `exact_target_plan_ready_read_only`.
- Protected holdout starts `2026-06-05`; overlap `False`.
- Bullish-pullback missing-exit quote rows: `3` rows / `3` unique targets.
- Lane A missing-exit quote rows: `127` rows / `111` unique targets.
- Lane A no-chain-native-spread rows: `10` non-importable selection-gap rows.
- Global importable target count: `130` rows / `114` unique targets; duplicate extra rows `16`.

## Holdout Guard

- Guard status: `passed_pre_holdout_only`.
- Importable target date basis: `missing_quote_date`.
- Selection-gap date basis: `candidate_entry_date`.
- Importable target overlap count: `0`.
- Selection-gap entry overlap count: `0`.
- If any target or selection-gap entry overlaps the protected holdout, this report status fails closed.

## Target Counts

| Group | Rows | Unique Targets | Duplicate Extra Rows | Date Range | Top Tickers | Reason Counts | Holdout |
|---|---:|---:|---:|---|---|---|---|
| `bullish_pullback_missing_exit_quotes` | 3 | 3 | 0 | `2026-03-23` to `2026-03-26` | WMT=2, JNJ=1 | missing_exit_quote_for_leg=3 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | 127 | 111 | 16 | `2025-08-26` to `2026-04-30` | SLB=15, WELL=8, CAT=7, AMZN=6, FCX=6, IWM=6, RTX=5, AA=4, ... +37 | missing_exit_quote_for_leg=127 | `pre_holdout` |

## Machine-Readable Target List

| Group | Ticker | Quote Date | Side / Field | Reason | Contract | Occurrences | Holdout |
|---|---|---|---|---|---|---:|---|
| `bullish_pullback_missing_exit_quotes` | `JNJ` | `2026-03-23` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `JNJ260327C00260000` | 1 | `pre_holdout` |
| `bullish_pullback_missing_exit_quotes` | `WMT` | `2026-03-25` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WMT260402C00140000` | 1 | `pre_holdout` |
| `bullish_pullback_missing_exit_quotes` | `WMT` | `2026-03-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WMT260402C00139000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AA` | `2025-11-14` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AA251121C00043000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AA` | `2026-01-27` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AA260227C00071000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AA` | `2026-02-12` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AA260220C00072000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AA` | `2026-02-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AA260220C00068000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AAPL` | `2026-03-12` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AAPL260320C00300000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `ABBV` | `2025-11-07` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `ABBV251121C00250000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMD` | `2025-11-25` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMD251128C00280000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMD` | `2025-12-01` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMD251205C00290000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMD` | `2026-02-27` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMD260306C00285000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMT` | `2026-03-13` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMT260417C00210000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2025-10-08` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN251010C00255000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2025-12-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN251212C00275000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2025-12-15` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN251219C00280000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2025-12-16` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN251219C00270000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2026-02-18` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN260220C00252500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `AMZN` | `2026-02-18` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `AMZN260220C00260000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `ARM` | `2025-11-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `ARM251128C00192500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `ARM` | `2025-11-14` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `ARM251205C00195000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `ARM` | `2025-11-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `ARM251121C00190000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `BA` | `2026-02-25` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `BA260227C00260000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `BA` | `2026-03-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `BA260306C00260000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `C` | `2026-01-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `C260206C00130000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `C` | `2026-02-02` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `C260206C00127000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2025-11-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT251205C00625000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2025-11-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT251212C00625000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2025-11-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT251212C00635000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2026-03-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT260327C00840000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2026-03-10` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT260402C00825000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2026-03-16` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT260402C00815000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CAT` | `2026-03-18` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CAT260402C00810000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `CLF` | `2025-11-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `CLF251107C00014000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `COIN` | `2025-11-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `COIN251121C00375000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `COP` | `2026-01-20` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `COP260123C00103000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `DIS` | `2026-02-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `DIS260206C00120000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `FCX` | `2025-09-25` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `FCX251017C00049000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `FCX` | `2025-10-16` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `FCX251017C00050000` | 3 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `FCX` | `2026-03-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `FCX260306C00071000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `FCX` | `2026-03-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `FCX260320C00075000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `GOOGL` | `2025-12-29` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `GOOGL260102C00350000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `GOOGL` | `2026-01-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `GOOGL260109C00360000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `GOOGL` | `2026-02-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `GOOGL260227C00345000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `GOOGL` | `2026-03-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `GOOGL260313C00335000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-02` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260306C00281000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-03` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260306C00275000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-03` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260306C00278000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-03` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260306C00279000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-06` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260313C00277500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `IWM` | `2026-03-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `IWM260313C00273000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `JNJ` | `2026-03-18` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `JNJ260327C00260000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `JPM` | `2025-11-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `JPM251107C00325000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `KO` | `2025-12-03` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `KO260109C00077000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `KO` | `2025-12-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `KO251212C00074000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `KO` | `2026-03-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `KO260320C00085000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `LIN` | `2026-03-23` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `LIN260417C00535000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `LLY` | `2025-12-10` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `LLY260109C01155000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `LLY` | `2026-02-12` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `LLY260213C01155000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `MCD` | `2026-01-14` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `MCD260116C00335000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `META` | `2025-09-24` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `META250926C00855000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NEM` | `2025-10-27` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NEM251107C00093000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NFLX` | `2026-03-23` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NFLX260410C00106000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NFLX` | `2026-04-08` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NFLX260410C00109000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NFLX` | `2026-04-30` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NFLX260501C00103000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NKE` | `2026-01-15` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NKE260116C00072500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NKE` | `2026-01-29` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NKE260220C00074000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NVDA` | `2025-12-08` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NVDA251212C00220000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `NVDA` | `2025-12-15` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `NVDA251219C00219000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `OXY` | `2025-10-08` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `OXY251010C00050000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PFE` | `2025-09-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PFE251010C00027500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PFE` | `2025-12-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PFE260109C00028000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PG` | `2026-03-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PG260327C00170000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PG` | `2026-03-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PG260402C00172500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PLD` | `2025-11-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PLD251219C00140000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PLD` | `2025-12-16` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PLD251219C00135000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PLTR` | `2025-09-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PLTR250912C00200000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PLTR` | `2026-01-20` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PLTR260123C00210000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `PLTR` | `2026-04-23` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `PLTR260424C00175000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `RTX` | `2025-11-24` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `RTX251205C00190000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `RTX` | `2025-12-01` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `RTX251219C00195000` | 3 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `RTX` | `2026-04-08` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `RTX260417C00230000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SBUX` | `2026-01-30` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SBUX260227C00106000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SBUX` | `2026-03-03` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SBUX260313C00104000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SBUX` | `2026-03-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SBUX260424C00109000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-09-22` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251024C00039000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-10-01` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251010C00039000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-10-01` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251010C00040000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-10-10` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251024C00038000` | 3 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-11-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251212C00040000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-11-19` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251212C00041000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2025-11-24` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB251205C00040000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2026-03-04` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB260306C00055000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2026-03-05` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB260306C00053000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SLB` | `2026-03-09` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SLB260320C00057500` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SMCI` | `2025-11-10` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SMCI251114C00061000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SMCI` | `2025-11-13` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SMCI251121C00062000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `SMCI` | `2026-03-30` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `SMCI260417C00036000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `T` | `2026-03-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `T260402C00031000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `T` | `2026-03-12` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `T260402C00030500` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `TSLA` | `2026-01-29` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `TSLA260130C00525000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `UNH` | `2025-11-20` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `UNH251121C00390000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `V` | `2026-01-23` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `V260206C00380000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WELL` | `2025-12-11` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WELL260116C00230000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WELL` | `2025-12-12` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WELL260116C00220000` | 2 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WELL` | `2026-03-13` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WELL260320C00220000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WELL` | `2026-03-20` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WELL260417C00230000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WELL` | `2026-04-13` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WELL260417C00220000` | 3 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WMT` | `2025-08-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WMT250926C00109000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WMT` | `2025-12-26` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WMT260123C00124000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `WMT` | `2026-03-06` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `WMT260313C00136000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `XLK` | `2025-11-25` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `XLK251219C00320000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `XOM` | `2025-10-21` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `XOM251024C00121000` | 1 | `pre_holdout` |
| `lane_a_missing_exit_quotes` | `XOM` | `2025-12-17` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `XOM251226C00124000` | 1 | `pre_holdout` |

## Lane A Selection-Gap Bucket

- Classification: `non_importable_selection_gap`.
- Rows: `10`.
- Candidate entry range: `2025-09-22` to `2026-03-04`.
- Tickers: `PLD=7, AMT=1, CLF=1, WELL=1`.

| Ticker | Candidate Entry Date | Reason | Classification | Holdout |
|---|---|---|---|---|
| `AMT` | `2026-02-24` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `CLF` | `2025-10-27` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-09-22` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-10-28` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-10-29` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-10-30` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-10-31` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2025-11-03` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `PLD` | `2026-02-25` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |
| `WELL` | `2026-03-04` | `no_chain_native_spread` | `non_importable_selection_gap` | `pre_holdout` |

## Duplicates

- Global duplicate extra rows: `16`.
- Cross-group duplicate targets: `0`.

| Quote Date | Contract | Side / Field | Reason | Groups | Occurrences |
|---|---|---|---|---|---:|
| `2025-10-01` | `SLB251010C00039000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2025-10-10` | `SLB251024C00038000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 3 |
| `2025-10-16` | `FCX251017C00050000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 3 |
| `2025-11-10` | `SMCI251114C00061000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2025-11-14` | `ARM251205C00195000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2025-12-01` | `RTX251219C00195000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 3 |
| `2025-12-12` | `WELL260116C00220000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2026-01-20` | `COP260123C00103000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2026-03-05` | `SLB260306C00053000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2026-03-09` | `SLB260320C00057500` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2026-03-13` | `AMT260417C00210000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 2 |
| `2026-04-13` | `WELL260417C00220000` | `short` / `missing_short_contract_symbol` | `missing_exit_quote_for_leg` | `lane_a_missing_exit_quotes` | 3 |

## Proposed Dry-Run / Plan-Only Commands

No write/import command is approved by this report.

| Label | Mode | Approved For Write/Import | Command |
|---|---|---|---|
| Regenerate exact target plan without writing artifacts | `read_only_no_write` | `False` | `uv run --locked python scripts/build_regular_options_exact_target_plan.py --no-write --json` |
| Plan-only bullish-pullback helper readback | `plan_only_no_provider_request_no_write` | `False` | `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json --plan-only --json` |
| Plan-only Lane A helper readback | `plan_only_no_provider_request_no_write` | `False` | `uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json --plan-only --json` |

## Permission Table

| Permission | Allowed Here | Requires Approval | Applies To |
|---|---|---|---|
| `read_only_ok` | `True` | `False` | Extracting, grouping, deduping, and reporting exact target rows from existing artifacts. |
| `evidence_mutation_requires_approval` | `False` | `True` | Any quote import, evidence-store write, replay write, DB migration, backup/delete, or --apply path. |
| `policy_change_requires_approval` | `False` | `True` | Any source-quality policy, scanner, contract-selection, proof-bar, lane-state, stop, or sizing change. |
| `not_actionable_without_forward_evidence` | `False` | `True` | Promotion, production proof, live-validation, or forward-proof claims from these historical rows. |

## Proof/Gate Status

- `current_status`: `read_only_plan_not_proof`.
- `historical_rows_are_forward_proof`: `False`.
- `production_proof_claim`: `False`.
- `live_validation_allowed`: `False`.
- `promotion_allowed`: `False`.
- `protected_holdout_consumed`: `False`.
- `quote_import_approved`: `False`.
- `evidence_store_mutation_approved`: `False`.
- `policy_change_approved`: `False`.

## Artifacts

- `json`: `data/profitability-lab/regular-options-exact-target-plan/regular_options_exact_target_plan_20260614T232225Z.json`
- `latest_json`: `data/profitability-lab/regular-options-exact-target-plan/latest.json`
- `markdown`: `data/profitability-lab/regular-options-exact-target-plan/regular_options_exact_target_plan_20260614T232225Z.md`
- `latest_markdown`: `data/profitability-lab/regular-options-exact-target-plan/latest.md`
- `docs_report`: `docs/regular-options-exact-target-plan.md`
