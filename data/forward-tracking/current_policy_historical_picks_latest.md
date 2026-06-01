# Current-Policy Historical Picks Audit

This report replays closed Trading Desk history through the currently promoted entry guardrails. It does not delete, rewrite, or promote historical paper rows; it separates rows the current policy would still take from rows that have been learned away.

## Summary

- Closed rows audited: `488`.
- Current-policy scope rows: `400`.
- Decision counts: `{"blocked_by_current_policy": 274, "out_of_scope_lane": 88, "unknown_missing_evidence": 14, "would_take_today": 112}`.
- Guardrail hit counts: `{"bullish_pullback_not_keep_bucket": 30, "bullish_pullback_ret5_lt_minus_2": 6, "debit_gt_45_width": 69, "fill_degradation_ge_20": 131, "lane_ticker_quarantine": 170, "worst_leg_spread_ge_20": 129}`.
- Current-policy avg P&L delta versus raw realized scope: `48.67` percentage points.

| Set | Rows | Priced | Negative | Positive/Flat | Avg P&L | Median P&L | Negative Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Raw realized scope | 355 | 355 | 184 | 171 | 4.87% | -6.53% | 51.8% |
| Would take today | 112 | 112 | 29 | 83 | 53.54% | 50.6% | 25.9% |
| Blocked by current policy | 274 | 243 | 155 | 88 | -17.56% | -30.41% | 63.8% |
| Unknown or missing evidence | 14 | 0 | 0 | 0 |  |  |  |

## Policy

- Repair lanes: `bullish_momentum, bullish_pullback_observation, short_term, swing`.
- Promoted guardrails: `debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine, bullish_pullback_not_keep_bucket, bullish_pullback_ret5_lt_minus_2`.
- Bullish Pullback keep tickers: `AAPL, COP, CVX, GOOGL, IWM, JNJ, LLY, NEM, UNH, XOM`.
- `would_take_today` means the row clears these current entry guardrails and has trusted realized P&L.
- `blocked_by_current_policy` means today's promoted entry guardrails would block or flag the historical entry.
- `unknown_missing_evidence` rows stay visible because they do not have trusted executable realized P&L.

## Worst Learned-Away Rows

| Trade | Ticker | Lane | P&L | Evidence | Guardrails | Sleeve |
|---:|---|---|---:|---|---|---|
| 432 | WMT | swing | -100.0% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 273 | WMT | short_term | -100.0% | historical_paper | debit_gt_45_width, fill_degradation_ge_20 |  |
| 429 | XLK | swing | -100.0% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 417 | XLK | swing | -100.0% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 260 | XLK | short_term | -100.0% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 88 | SBUX | bullish_pullback_observation | -100.0% | historical_paper | worst_leg_spread_ge_20, bullish_pullback_not_keep_bucket | rejected |
| 404 | NEM | swing | -100.0% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 61 | BAC | bullish_pullback_observation | -100.0% | historical_paper | worst_leg_spread_ge_20, bullish_pullback_not_keep_bucket | rejected |
| 285 | NFLX | swing | -100.0% | historical_paper | lane_ticker_quarantine |  |
| 430 | WMT | swing | -99.2941% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 242 | IWM | short_term | -99.1645% | historical_paper | lane_ticker_quarantine |  |
| 254 | XLK | short_term | -98.7871% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 57 | JPM | bullish_pullback_observation | -97.4635% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20, bullish_pullback_not_keep_bucket | quarantine |
| 474 | SLB | bullish_momentum | -96.5577% | historical_paper | fill_degradation_ge_20 |  |
| 471 | SLB | bullish_momentum | -96.3689% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 202 | SLB | short_term | -96.3689% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 342 | SLB | swing | -96.3168% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 385 | DIS | swing | -95.6861% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 483 | TSLA | bullish_momentum | -95.6383% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 270 | NVDA | short_term | -95.4057% | historical_paper | lane_ticker_quarantine |  |
| 247 | NEM | short_term | -95.1417% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 458 | PFE | bullish_momentum | -94.8718% | historical_paper | fill_degradation_ge_20, worst_leg_spread_ge_20 |  |
| 420 | XLK | swing | -94.7374% | historical_paper | debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine |  |
| 135 | NFLX | short_term | -94.4869% | historical_paper | debit_gt_45_width, fill_degradation_ge_20 |  |
| 300 | NFLX | swing | -94.0719% | historical_paper | lane_ticker_quarantine |  |

## Best Current-Policy Rows

| Trade | Ticker | Lane | P&L | Evidence | Sleeve |
|---:|---|---|---:|---|---|
| 162 | AMZN | short_term | 280.2281% | historical_paper |  |
| 473 | AAPL | bullish_momentum | 230.7359% | historical_paper |  |
| 453 | AMD | bullish_momentum | 219.2796% | historical_paper |  |
| 313 | AMD | swing | 219.2796% | historical_paper |  |
| 136 | AMD | short_term | 215.9041% | historical_paper |  |
| 455 | AMD | bullish_momentum | 212.3632% | historical_paper |  |
| 163 | AMD | short_term | 212.3632% | historical_paper |  |
| 451 | AMD | bullish_momentum | 190.69% | historical_paper |  |
| 307 | AMD | swing | 190.69% | historical_paper |  |
| 226 | AMD | short_term | 178.7139% | historical_paper |  |
| 450 | AMD | bullish_momentum | 171.6231% | historical_paper |  |
| 448 | AMD | bullish_momentum | 167.3657% | historical_paper |  |
| 211 | QQQ | short_term | 167.2646% | historical_paper |  |
| 293 | AMD | swing | 164.2692% | historical_paper |  |
| 441 | AMZN | bullish_momentum | 153.4016% | historical_paper |  |
| 466 | UNH | bullish_momentum | 150.3726% | historical_paper |  |
| 320 | AMD | swing | 149.4997% | historical_paper |  |
| 440 | AMD | bullish_momentum | 141.3163% | historical_paper |  |
| 459 | AMD | bullish_momentum | 138.7444% | historical_paper |  |
| 174 | AMD | short_term | 138.7444% | historical_paper |  |
| 456 | UNH | bullish_momentum | 138.4256% | historical_paper |  |
| 331 | AMD | swing | 136.9952% | historical_paper |  |
| 166 | QQQ | short_term | 135.6592% | historical_paper |  |
| 147 | QQQ | short_term | 127.1605% | historical_paper |  |
| 370 | SPY | swing | 119.2529% | historical_paper |  |

## Inputs

| Source | Status | Generated | Path |
|---|---|---|---|
| trading_desk_profitability_guardrails | ok | 2026-05-31T21:29:54Z | data/forward-tracking/trading_desk_profitability_guardrails_latest.json |
| bullish_pullback_ticker_audit | ok | 2026-05-29T01:19:33Z | data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json |
| regular_options_symbol_sleeves | ok | 2026-06-01T05:23:22Z | data/profitability-lab/regular-options-symbol-sleeves/latest.json |
