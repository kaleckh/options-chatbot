# ThetaData Preservation Final Report - 2026-05-26

## What Is Preserved

Clean trusted ThetaData OPRA/NBBO intraday data is preserved in `data/options-validation/options_history.db` under source label `thetadata_opra_nbbo_1m` and snapshot kind `intraday`.

The high-ROI option-lane set is ready for exact replay:

- Symbols: `AMZN`, `DIA`, `GOOGL`, `IWM`, `JPM`, `NVDA`, `QQQ`, `SPY`, `XLK`
- Dates: 252 shared quote dates, `2025-05-22` through `2026-05-22`
- Quote minutes: 10:10 ET and 15:55 ET
- Rows: 1,949,805 trusted executable bid/ask rows
- Readiness status: `ready_for_exact_replay`

The broader bullish-pullback 60-symbol universe has ThetaData rows, but most of it does not have the same clean 252-date, two-minute profile. The broad set mostly has a thinner 15:55 profile for a smaller December 2025 window.

## What Was Added

New reusable scripts:

- `scripts/backfill_thetadata_main_lane_last_chance.py`
- `scripts/import_missing_replay_quotes_from_thetadata.py`
- `scripts/iterate_thetadata_exact_fill_replays.py`

The exact-fill loop repeatedly reruns the target replays, imports the newly exposed missing exit-leg contracts from ThetaData, and stops only when the marginal import is low or the configured cycle cap is reached.

Latest exact-fill summary:

- Artifact: `data/profitability-lab/thetadata-exact-fill-iteration-summary.json`
- Latest cycle count: 12
- Latest exact import: 4 imported rows, 51 no-match rows

## Latest Replay Results

All replays used:

- `truth_lane=historical_imported`
- `historical_source_labels=thetadata_opra_nbbo_1m`
- `allow_research_imported_data=False`
- `pricing_lane=pessimistic`

Final measured results:

- `tracked_winner_chain_native_qqq_time60_debit60_ret20_watch`: 19 priced / 24 candidates, 79.2% coverage, profit factor 1.58
- `tracked_winner_chain_native_spy_qqq_time60_ret20_watch`: 43 priced / 50 candidates, 86.0% coverage, profit factor 0.99
- `tracked_winner_chain_native_qqq_time80_research`: 144 priced / 202 candidates, 71.3% coverage, profit factor 1.26

The broad research lane now has more than 100 priced trades from trusted ThetaData-backed replay.

## Bottleneck

The remaining replay failures are not missing entry data or missing market days. They are still `missing_exit_quote_for_leg`.

The root cause is now mostly algorithm-side:

- Some vertical spreads choose short legs too far out of the liquid/quoted chain.
- Some contracts repeatedly return no exact 15:55 ThetaData match, especially far OTM `NVDA`, `GOOGL`, `DIA`, plus some `QQQ` and `SPY` strikes.
- Continuing exact imports adds fewer rows over time, while profit factor falls as more previously unpriced outcomes are included.

## Recommendation

Stop brute-force import for the high-ROI lane unless we specifically want the full 60-symbol two-minute dataset. The next profitability work should constrain the algorithm:

- Cap vertical spread width and short-leg distance from the long leg.
- Require exit-leg quote availability or liquid-chain membership before selecting a spread.
- Prefer quoted, tighter-spread contracts over nearest-listed far OTM contracts.
- Re-run the exact-fill loop after each algorithm change to compare coverage, profit factor, and priced-trade count.

The data is now good enough to reveal the real issue: the current spread construction can select contracts that are too sparse or too far OTM for dependable historical replay.
