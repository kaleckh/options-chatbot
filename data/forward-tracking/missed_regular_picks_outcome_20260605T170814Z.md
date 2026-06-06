# Missed Regular Picks Outcome Audit

- Generated: `2026-06-05T17:08:14Z`
- Raw rows: `210`
- Already tracked rows: `4`
- Untracked missed rows: `206`
- Conservative mark coverage: `210` rows
- Latest intraday quote date: `2026-06-04`

## Untracked Mark

- Winners / losers: `70` / `136`
- Win rate: `34.0%`
- Avg net P&L: `-15.19%`
- Median net P&L: `-11.5%`
- Profit factor: `0.34`
- 1-spread net dollars: `$-16244.0`

## Lane Gates

| Lane | Status | Rows | PF | Avg Net P&L | Winners | Losers | Self Guardrails |
|---|---|---:|---:|---:|---:|---:|---|
| bullish_momentum | diagnostic_only_unprofitable_lane | 16 | 0.1 | -48.45 | 2 | 14 | none |
| bullish_pullback_observation | diagnostic_only_unprofitable_lane | 15 | 0.3 | -21.62 | 5 | 10 | none |
| short_term | diagnostic_only_unprofitable_lane | 54 | 0.28 | -18.93 | 18 | 36 | none |
| speculative | diagnostic_only_unprofitable_lane | 8 | 0.12 | -12.62 | 2 | 6 | none |
| swing | diagnostic_only_unprofitable_lane | 49 | 0.3 | -14.31 | 15 | 34 | none |
| tracked_winner_observation | diagnostic_only_unprofitable_lane | 20 | 0.46 | -9.19 | 8 | 12 | none |
| tracked_winner_primary | diagnostic_only_unprofitable_lane | 20 | 0.46 | -9.19 | 8 | 12 | none |
| volatility_expansion_observation | candidate_flow_allowed_with_self_guardrails | 24 | 1.72 | 6.75 | 12 | 12 | blocked tickers: IWM,SPY; max debit 45.0% |

## Boundary

- This is historical/research mark evidence, not broker fills.
- Lane gates are allowed to route candidates into validation only when the lane has enough exact rows, positive average net P&L, and profit factor above threshold.
- Profitable lanes still carry self-guardrails learned from negative clusters.

