# Regular Options Exhausted Contract Archive

This report is generated from `scripts/build_regular_options_exhausted_contract_archive.py`. It is a read-only archive for exact contract/date repair targets where the current source repeatedly returned no exact rows.

## Summary

- Status: `exhausted_contract_archive_readback`.
- Overall status: `exhausted_contract_target_archived`.
- Archived exhausted contracts: `8`.
- Previously archived exhausted contracts: `7`.
- Newly archived exhausted contracts: `1`.
- Remaining eligible exhausted contracts: `38`.
- Source exhausted targets: `97`.
- Live policy change: `false`.

## Archived Contract Targets

| Archive Key | Symbol | Lane | Contract | Missing Quote Date | Attempts | Reason |
|---|---|---|---|---:|---:|---|
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260102C00355000\|2025-12-22 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260102C00355000 | 2025-12-22 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260102C00360000\|2025-12-22 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260102C00360000 | 2025-12-22 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260102C00365000\|2025-12-23 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260102C00365000 | 2025-12-23 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260213C00350000\|2026-02-12 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260213C00350000 | 2026-02-12 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260306C00365000\|2026-02-27 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260306C00365000 | 2026-02-27 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_chain_native_qqq_time80_intraday\|GOOGL260306C00360000\|2026-03-02 | GOOGL | tracked_winner_chain_native_qqq_time80_intraday | GOOGL260306C00360000 | 2026-03-02 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_cheap_debit_continuity_v1\|GOOGL260102C00355000\|2025-12-22 | GOOGL | tracked_winner_cheap_debit_continuity_v1 | GOOGL260102C00355000 | 2025-12-22 | 5 | repeated_exact_date_no_match_current_source_exhausted |
| GOOGL\|tracked_winner_cheap_debit_continuity_v1\|GOOGL260102C00360000\|2025-12-22 | GOOGL | tracked_winner_cheap_debit_continuity_v1 | GOOGL260102C00360000 | 2025-12-22 | 5 | repeated_exact_date_no_match_current_source_exhausted |

## Boundary

This archive is read-only. It does not create trades, submit broker orders, mutate trading rows, change scanner or contract-selection policy, change stops or sizing, lower exact OPRA/NBBO proof bars, or count no-match rows as production proof.

