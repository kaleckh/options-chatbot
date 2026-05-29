# Bullish Pullback Profitability Testing Goal Prompt - 2026-05-26

Test profitability for the completed `bullish_pullback_observation` universe of 59 active symbols, excluding `CMCSA`, using trusted ThetaData OPRA/NBBO intraday coverage at both 10:10 ET and 15:55 ET.

Build an end-to-end profitability study that evaluates the current bullish pullback strategy across the full completed universe with realistic option execution assumptions. The primary objective is to increase profit factor while preserving or improving executable coverage. Trade count is a minimum viability constraint, not the optimization target.

Use only the frozen 59-symbol universe from `data/options-lanes/universes/bullish_pullback_observation.json`. Do not re-add or drop symbols during testing. Use only trusted `thetadata_opra_nbbo_1m` intraday data with `snapshot_kind=intraday`, `dataset_kind=intraday_csv`, and `data_trust=trusted`. Require timestamp-safe joins: all signals, underlying prices, option quotes, spreads, and filters must use only data available before the simulated decision time.

Do not run profitability conclusions on insufficient data. Before testing or promoting a result, prove that each required input is present at the needed timestamp, symbol, contract, and quote side. If required data is missing, first try to fill it from approved sources before continuing: trusted ThetaData OPRA/NBBO history for option quotes, available Alpaca credentials for stock/option market data, and free reliable online sources only for non-option supporting data such as underlying OHLCV, corporate actions, calendars, sectors, and macro/reference fields. Load local credentials from `.env` / `.env.local` when needed before declaring Alpaca unavailable. Do not use free online data as a substitute for proof-grade historical option fills unless it contains the required bid/ask contract quote evidence and can be source-labeled, timestamped, and reproduced.

If data remains incomplete after attempted fills, stop the affected test path and report the data bottleneck instead of making judgment calls from a thin sample. A variant is not ready when profitability depends on missing exits, stale quotes, nearest-contract substitutions, unsupported mid fills, or a symbol/date subset that is materially smaller than the full active universe.

Establish a baseline from the current bullish pullback logic before testing variants. Then search strategy variants conservatively across entry filters, option selection rules, spread/liquidity thresholds, exits, stop/target logic, max hold time, and time-of-day constraints. Avoid high-dimensional brute-force tuning. Prefer simple rule changes with stable neighboring-parameter performance.

Use strict chronological splits: train/calibration, validation, and untouched final out-of-sample. Do not change parameters after viewing final OOS. Add symbol-holdout, date-holdout, liquidity-stress, slippage-stress, and top-winner-removal robustness checks.

Model execution conservatively: bid/ask-aware fills, spread/slippage penalties, stale quote rejection, minimum quote quality, minimum volume/open-interest where available, realistic entry/exit timing, and no mid-price fill assumptions unless explicitly compared as a non-production sensitivity lane.

Measure and report signal coverage, chain availability, option selection success, spread/volume pass rate, simulated fill rate, trade count, win rate, average win/loss, expectancy, profit factor, max drawdown, tail losses, exposure time, symbol concentration, regime breakdowns, DTE/delta/time-of-day breakdowns, and performance after removing top winners.

Rank candidates by risk-adjusted profitability first: profit factor, expectancy, drawdown stability, and robustness. Then use executable coverage and trade count as tie-breakers and viability gates. Reject candidates with too few OOS trades, excessive dependence on a small number of symbols, unstable regime performance, unrealistic fills, high sensitivity to slippage, or parameters that look curve-fit.

Deliver a concise report with baseline results, top candidate variants, coverage diagnostics, robustness checks, rejected overfit patterns, counterarguments, and the recommended production-ready configuration.
