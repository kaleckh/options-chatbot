# Missed Regular Picks Outcome Audit

- Generated: `2026-06-10T06:27:05Z`
- Raw rows: `210`
- Already tracked rows: `4`
- Untracked missed rows: `206`
- Conservative mark coverage: `210` rows
- Mark quote evidence class: `trusted_intraday_opra_nbbo`
- Row evidence group: `research_backfill`
- Latest intraday quote date: `2026-06-08`

## Untracked Mark

- Winners / losers: `72` / `134`
- Win rate: `35.0%`
- Avg net P&L: `-16.54%`
- Median net P&L: `-12.64%`
- Profit factor: `0.32`
- 1-spread net dollars: `$-18755.0`

## Lane Gates

| Lane | Status | Rows | PF | Avg Net P&L | Winners | Losers | Self Guardrails |
|---|---|---:|---:|---:|---:|---:|---|
| bullish_momentum | diagnostic_only_unprofitable_lane | 16 | 0.04 | -48.45 | 2 | 14 | none |
| bullish_pullback_observation | diagnostic_only_unprofitable_lane | 15 | 0.24 | -22.81 | 5 | 10 | none |
| short_term | diagnostic_only_unprofitable_lane | 54 | 0.33 | -18.93 | 18 | 36 | none |
| speculative | diagnostic_only_unprofitable_lane | 8 | 0.1 | -12.62 | 2 | 6 | none |
| swing | diagnostic_only_unprofitable_lane | 49 | 0.2 | -20.24 | 15 | 34 | none |
| tracked_winner_observation | diagnostic_only_unprofitable_lane | 20 | 0.5 | -8.43 | 9 | 11 | none |
| tracked_winner_primary | diagnostic_only_unprofitable_lane | 20 | 0.5 | -8.43 | 9 | 11 | none |
| volatility_expansion_observation | candidate_flow_allowed_with_self_guardrails | 24 | 1.83 | 6.74 | 12 | 12 | blocked tickers: IWM,SPY; max debit 45.0% |

## Boundary

- This is historical/research mark evidence, not broker fills.
- `quote_evidence_class` describes the quote source used for the mark; it does not make the historical missed-pick row production proof.
- Lane gates are allowed to route candidates into validation only when the lane has enough exact rows, positive average net P&L, and profit factor above threshold.
- Profitable lanes still carry self-guardrails learned from negative clusters.

