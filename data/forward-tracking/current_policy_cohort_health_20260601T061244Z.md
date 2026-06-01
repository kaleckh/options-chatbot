# Current-Policy Cohort Health

This report separates the strong April current-policy cohort from the broken recent cohort. It is a read-only regime health and paper-only recommendation layer; it does not rewrite historical P&L.

## Headline

- Overall status: `paper_only_recent_week_break`.
- Showcase month: `2026-04`.
- Recent month: `2026-05`.
- Recent week: `2026-W21`.
- Interpretation: April-like historical cohorts can be shown as a discovered edge, but recent broken cohorts should be paper-only until revalidated.

| Cohort | Priced | Avg P&L | Median P&L | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| Overall current policy | 112 | 53.54% | 50.6% | 25.9% | paper_only_recent_week_break |
| Showcase 2026-04 | 70 | 81.17% | 71.82% | 8.6% | healthy |
| Recent 2026-05 | 42 | 7.49% | -4.6% | 54.8% | paper_only_recent_break |
| Recent 2026-W21 | 3 | -82.06% | -83.61% | 100.0% | paper_only_recent_break |

## Monthly Cohorts

| Month | Priced | Avg P&L | Median P&L | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| 2026-04 | 70 | 81.17% | 71.82% | 8.6% | healthy |
| 2026-05 | 42 | 7.49% | -4.6% | 54.8% | paper_only_recent_break |

## Lane By Recent Month

| Lane Cohort | Priced | Avg P&L | Median P&L | Negative Rate | Health |
|---|---:|---:|---:|---:|---|
| 2026-05:bullish_momentum | 5 | 53.55% | 51.21% | 20.0% | healthy |
| 2026-05:bullish_pullback_observation | 2 | -73.37% | -73.37% | 100.0% | paper_only_thin_severe |
| 2026-05:short_term | 17 | -12.3% | -55.41% | 70.6% | paper_only_recent_break |
| 2026-05:swing | 18 | 22.38% | 7.35% | 44.4% | watch_recent_fragile |

## Recent Month Losers

| Trade | Ticker | Lane | Entry | Closed | P&L |
|---:|---|---|---|---|---:|
| 228 | DIS | short_term | 2026-05-07 | 2026-05-12 | -99.5429% |
| 275 | WMT | short_term | 2026-05-20 | 2026-05-21 | -99.4552% |
| 258 | TSLA | short_term | 2026-05-14 | 2026-05-18 | -98.3586% |
| 472 | BAC | bullish_momentum | 2026-05-01 | 2026-05-08 | -97.5031% |
| 241 | BA | short_term | 2026-05-11 | 2026-05-15 | -96.1663% |
| 214 | MSTR | short_term | 2026-05-05 | 2026-05-07 | -92.1914% |
| 245 | TSLA | short_term | 2026-05-12 | 2026-05-15 | -91.9284% |
| 93 | GOOGL | bullish_pullback_observation | 2026-05-18 | 2026-05-30 | -83.6131% |
| 402 | TSLA | swing | 2026-05-12 | 2026-05-22 | -81.4149% |
| 265 | COIN | short_term | 2026-05-15 | 2026-05-19 | -71.4211% |
| 101 | UNH | bullish_pullback_observation | 2026-05-20 | 2026-05-30 | -63.125% |
| 244 | QQQ | short_term | 2026-05-11 | 2026-05-15 | -60.8643% |
| 257 | QQQ | short_term | 2026-05-13 | 2026-05-18 | -55.4118% |
| 251 | QQQ | short_term | 2026-05-12 | 2026-05-15 | -26.4962% |
| 395 | SPY | swing | 2026-05-08 | 2026-05-18 | -22.827% |
| 396 | NVDA | swing | 2026-05-11 | 2026-05-21 | -21.5156% |
| 201 | AMD | short_term | 2026-05-01 | 2026-05-05 | -18.7259% |
| 400 | SPY | swing | 2026-05-11 | 2026-05-21 | -16.8601% |
| 376 | AMD | swing | 2026-05-06 | 2026-05-15 | -13.4242% |
| 266 | QQQ | short_term | 2026-05-15 | 2026-05-20 | -13.2134% |

## Recommended Actions

- **P0** `month:2026-05`: Mark current-policy picks paper-only until the recent cohort revalidates. Evidence: 2026-05 avg=7.49%, median=-4.6%, negative_rate=54.8%.
- **P0** `lane:bullish_pullback_observation`: Pause this lane or route it to paper-only in the current regime. Evidence: 2026-05:bullish_pullback_observation avg=-73.37%, median=-73.37%, negative_rate=100.0%.
- **P0** `lane:short_term`: Pause this lane or route it to paper-only in the current regime. Evidence: 2026-05:short_term avg=-12.3%, median=-55.41%, negative_rate=70.6%.
- **P1** `ticker:DIS`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:DIS avg=-99.54%, median=-99.54%, negative_rate=100.0%.
- **P1** `ticker:WMT`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:WMT avg=-99.46%, median=-99.46%, negative_rate=100.0%.
- **P1** `ticker:BAC`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:BAC avg=-97.5%, median=-97.5%, negative_rate=100.0%.
- **P1** `ticker:BA`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:BA avg=-96.17%, median=-96.17%, negative_rate=100.0%.
- **P1** `ticker:MSTR`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:MSTR avg=-92.19%, median=-92.19%, negative_rate=100.0%.
- **P1** `ticker:TSLA`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:TSLA avg=-90.57%, median=-91.93%, negative_rate=100.0%.
- **P1** `ticker:GOOGL`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:GOOGL avg=-83.61%, median=-83.61%, negative_rate=100.0%.
- **P1** `ticker:COIN`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:COIN avg=-71.42%, median=-71.42%, negative_rate=100.0%.
- **P1** `ticker:UNH`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:UNH avg=-63.12%, median=-63.12%, negative_rate=100.0%.
- **P1** `ticker:NVDA`: Do not showcase or re-enable this ticker cluster without a fresh recovery cohort. Evidence: 2026-05:NVDA avg=-7.0%, median=-7.0%, negative_rate=50.0%.
