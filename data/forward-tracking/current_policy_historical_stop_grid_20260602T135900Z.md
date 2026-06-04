# Current-Policy Historical Stop Grid

Read-only exact-contract OPRA/NBBO daily close-check replay for current-policy realized rows. This does not change live stops and does not claim minute-by-minute intraday stop evidence.

- Generated: `2026-06-02T13:58:48Z`
- Replayed rows: `112`
- Unresolved rows: `0`
- Tickers with unresolved rows: `0` of `17`
- Annual replay-backed rows: `234` replayed, `0` unresolved across `37` tickers
- Source labels: `thetadata_opra_nbbo_1m`
- Pricing lane: `pessimistic`

## Per-Ticker Coverage

| Ticker | Rows | Replayed | Unresolved | Reasons |
| --- | ---: | ---: | ---: | --- |
| AAPL | 6 | 6 | 0 | {} |
| AMD | 29 | 29 | 0 | {} |
| AMZN | 8 | 8 | 0 | {} |
| BA | 1 | 1 | 0 | {} |
| BAC | 1 | 1 | 0 | {} |
| COIN | 1 | 1 | 0 | {} |
| DIS | 1 | 1 | 0 | {} |
| GOOGL | 1 | 1 | 0 | {} |
| IWM | 3 | 3 | 0 | {} |
| MSTR | 2 | 2 | 0 | {} |
| NFLX | 5 | 5 | 0 | {} |
| NVDA | 4 | 4 | 0 | {} |
| QQQ | 26 | 26 | 0 | {} |
| SPY | 14 | 14 | 0 | {} |
| TSLA | 3 | 3 | 0 | {} |
| UNH | 6 | 6 | 0 | {} |
| WMT | 1 | 1 | 0 | {} |

## Annual Replay-Backed Coverage

Entry window: `2025-08-14` to `2026-03-24`. Exit window: `2025-09-09` to `2026-04-27`.

| Ticker | Rows | Replayed | Unresolved | Reasons |
| --- | ---: | ---: | ---: | --- |
| AA | 3 | 3 | 0 | {} |
| AAPL | 14 | 14 | 0 | {} |
| ABBV | 4 | 4 | 0 | {} |
| AMZN | 1 | 1 | 0 | {} |
| BA | 1 | 1 | 0 | {} |
| BAC | 4 | 4 | 0 | {} |
| C | 2 | 2 | 0 | {} |
| CAT | 3 | 3 | 0 | {} |
| COIN | 1 | 1 | 0 | {} |
| COP | 9 | 9 | 0 | {} |
| CVX | 3 | 3 | 0 | {} |
| DIA | 5 | 5 | 0 | {} |
| FCX | 6 | 6 | 0 | {} |
| GOOGL | 30 | 30 | 0 | {} |
| IWM | 19 | 19 | 0 | {} |
| JNJ | 20 | 20 | 0 | {} |
| JPM | 1 | 1 | 0 | {} |
| LLY | 14 | 14 | 0 | {} |
| MCD | 1 | 1 | 0 | {} |
| NEM | 15 | 15 | 0 | {} |
| NFLX | 7 | 7 | 0 | {} |
| NVDA | 1 | 1 | 0 | {} |
| OXY | 8 | 8 | 0 | {} |
| PFE | 1 | 1 | 0 | {} |
| PLD | 1 | 1 | 0 | {} |
| PLTR | 6 | 6 | 0 | {} |
| PM | 1 | 1 | 0 | {} |
| QQQ | 2 | 2 | 0 | {} |
| RTX | 4 | 4 | 0 | {} |
| SLB | 5 | 5 | 0 | {} |
| SPY | 1 | 1 | 0 | {} |
| T | 2 | 2 | 0 | {} |
| TSLA | 4 | 4 | 0 | {} |
| UNH | 8 | 8 | 0 | {} |
| WMT | 19 | 19 | 0 | {} |
| XLK | 4 | 4 | 0 | {} |
| XOM | 4 | 4 | 0 | {} |

### Annual Replay Stop Grid

| Policy | Rows | Avg | Median | Negatives | <= -50% | <= -70% | <= -80% | <= -90% | Stop hits | Avg delta | Winner flips |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 234 | +26.76% | +23.15% | 87 | 54 | 43 | 38 | 31 | - | - | - |
| Stop 50% | 234 | -14.43% | -53.09% | 159 | 147 | 25 | 11 | 5 | 147 | -41.18% | 71 |
| Stop 60% | 234 | -0.85% | -53.41% | 132 | 117 | 51 | 20 | 9 | 116 | -27.61% | 45 |
| Stop 70% | 234 | +7.73% | +4.33% | 114 | 97 | 93 | 37 | 14 | 92 | -19.03% | 27 |
| Stop 80% | 234 | +13.13% | +14.35% | 105 | 82 | 76 | 74 | 28 | 71 | -13.63% | 18 |
| Stop 90% | 234 | +18.18% | +18.26% | 97 | 68 | 59 | 55 | 51 | 46 | -8.57% | 10 |

## Baseline And Stop Grid

| Policy | Rows | Avg | Median | Negatives | <= -50% | <= -70% | <= -80% | <= -90% | Stop hits | Avg delta | Winner flips | First priced already through stop |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 112 | +53.54% | +50.60% | 29 | 16 | 12 | 10 | 8 | - | - | - | - |
| Stop 50% | 112 | +51.48% | +46.40% | 32 | 19 | 9 | 5 | 4 | 18 | -2.06% | 3 | 1 |
| Stop 60% | 112 | +51.18% | +46.40% | 32 | 19 | 10 | 6 | 4 | 17 | -2.36% | 3 | 1 |
| Stop 70% | 112 | +53.25% | +50.60% | 30 | 17 | 14 | 8 | 6 | 14 | -0.28% | 1 | 0 |
| Stop 80% | 112 | +53.69% | +50.60% | 29 | 16 | 12 | 10 | 7 | 9 | +0.15% | 0 | 0 |
| Stop 90% | 112 | +53.54% | +50.60% | 29 | 16 | 12 | 10 | 8 | 8 | +0.00% | 0 | 0 |

## Focus Loss Cohort

Rows at or below `-50.00%`: `16`. Average `-82.87%`, median `-87.77%`.

- Lane counts: `{"bullish_momentum": 2, "bullish_pullback_observation": 2, "short_term": 11, "swing": 1}`
- Ticker counts: `{"AMZN": 1, "BA": 1, "BAC": 1, "COIN": 1, "GOOGL": 1, "MSTR": 2, "NFLX": 1, "QQQ": 2, "TSLA": 3, "UNH": 1}`
- Market regimes: `{"bearish": 2, "bullish": 12, "neutral": 2}`
- Fill degradation >= 15%: `6`
- Debit >= 45% of width: `0`
- Worst-leg bid/ask >= 20%: `0`
- Quality score below 60: `4`

## Worst Loss Examples

| ID | Ticker | Lane | Entry | Baseline close | Baseline | Best close-check stop | Best stop P&L | Stop quality | Entry signals |
| ---: | --- | --- | --- | --- | ---: | --- | ---: | --- | --- |
| 228 | DIS | short_term | 2026-05-07 | 2026-05-12 | -99.54% | 50 | -65.71% | actionable_close_check_stop | regime=bullish, fill=15.6%, debit_width=43.2%, worst_spread=11.1%, quality=60.3 |
| 275 | WMT | short_term | 2026-05-20 | 2026-05-21 | -99.46% | 50 | -99.46% | actionable_close_check_stop | regime=bearish, fill=19.0%, debit_width=36.2%, worst_spread=5.7%, quality=63.8 |
| 258 | TSLA | short_term | 2026-05-14 | 2026-05-18 | -98.36% | 50 | -81.67% | actionable_close_check_stop | regime=bullish, fill=12.5%, debit_width=29.1%, worst_spread=2.8%, quality=72.6 |
| 472 | BAC | bullish_momentum | 2026-05-01 | 2026-05-08 | -97.50% | 50 | -71.29% | actionable_close_check_stop | regime=bullish, fill=14.0%, debit_width=38.8%, worst_spread=10.0%, quality=79.7 |
| 241 | BA | short_term | 2026-05-11 | 2026-05-15 | -96.17% | 50 | -67.17% | actionable_close_check_stop | regime=bullish, fill=14.3%, debit_width=27.6%, worst_spread=12.5%, quality=57.5 |
| 449 | NFLX | bullish_momentum | 2026-04-15 | 2026-04-17 | -94.07% | 50 | -94.07% | actionable_close_check_stop | regime=bullish, fill=16.5%, debit_width=44.5%, worst_spread=1.8%, quality=80.5 |
| 214 | MSTR | short_term | 2026-05-05 | 2026-05-07 | -92.19% | 50 | -92.19% | actionable_close_check_stop | regime=neutral, fill=17.2%, debit_width=31.6%, worst_spread=4.3%, quality=59.7 |
| 245 | TSLA | short_term | 2026-05-12 | 2026-05-15 | -91.93% | 50 | -91.93% | actionable_close_check_stop | regime=bullish, fill=11.8%, debit_width=29.6%, worst_spread=3.1%, quality=71.6 |
| 93 | GOOGL | bullish_pullback_observation | 2026-05-18 | 2026-05-30 | -83.61% | 50 | -60.18% | actionable_close_check_stop | regime=neutral, fill=13.3%, debit_width=41.4%, worst_spread=7.6%, quality=58.4 |
| 402 | TSLA | swing | 2026-05-12 | 2026-05-22 | -81.41% | 50 | -58.63% | actionable_close_check_stop | regime=bullish, fill=11.2%, debit_width=29.1%, worst_spread=1.9%, quality=83.6 |
| 183 | MSTR | short_term | 2026-04-24 | 2026-04-28 | -75.80% | 50 | -75.80% | actionable_close_check_stop | regime=bullish, fill=16.5%, debit_width=23.5%, worst_spread=13.3%, quality=60.5 |
| 265 | COIN | short_term | 2026-05-15 | 2026-05-19 | -71.42% | 80 | -71.42% | no_stop_trigger | regime=bullish, fill=16.7%, debit_width=21.6%, worst_spread=7.7%, quality=76.7 |
| 155 | AMZN | short_term | 2026-04-17 | 2026-04-21 | -65.07% | 80 | -65.07% | no_stop_trigger | regime=bullish, fill=10.1%, debit_width=26.6%, worst_spread=9.9%, quality=61.0 |
| 101 | UNH | bullish_pullback_observation | 2026-05-20 | 2026-05-30 | -63.12% | 50 | -63.12% | no_stop_trigger | regime=bearish, fill=13.2%, debit_width=29.7%, worst_spread=16.5%, quality=88.0 |
| 244 | QQQ | short_term | 2026-05-11 | 2026-05-15 | -60.86% | 50 | -60.86% | actionable_close_check_stop | regime=bullish, fill=8.7%, debit_width=41.1%, worst_spread=1.4%, quality=56.4 |

## Decision Read

Status: `daily_close_research_candidate`

Best non-destructive daily close-check stop: `80`

Recommended next action: Keep live stops unchanged for now. Treat the best non-destructive daily close-check stop as a research candidate, then test minute-by-minute OPRA/NBBO stops and entry avoidance filters before promotion.

Promote a live stop change only if a stop level reduces deep-loss buckets without increasing negative rows or flipping winners. If the best rows show first-priced or unpriced-before-stop failures, treat that as an entry/liquidity filter problem rather than a stop-policy win.

Unresolved reasons: `{}`

