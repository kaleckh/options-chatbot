# Exit Follow-Up Batch

Generated: 2026-03-31

Common baseline: `research_runs/20260330_233407_equity-ev-7-plus-momentum-0p70`

## Focus

Start the next profitability branch on the cleanest currently-supported surface: exit-only research overrides on top of the current best entry cohort.

Base cohort:

- `equity.filters.min_calibrated_expectancy_pct = 7.0`
- `equity.entry.entry_momentum_pct = 0.70`

## Why This Batch First

Two higher-level ideas from the six-agent debate are paused for architecture reasons:

- Diversification-aware marginal ranking is not meaningfully testable under the fixed replay matrix because `n_picks=1`.
- Contract-level tradability-weighted ranking needs a replay refactor so candidate selection sees exact-contract quote quality before final ranking.

Those remain valid next steps, but exit-only testing is the highest-signal branch the current replay architecture can measure cleanly today.

## Batch

- `ev7-momentum070-exit-time33`
  `risk.time_exit_pct = 33.0`
- `ev7-momentum070-exit-target80`
  `risk.profit_target_pct = 80.0`
- `ev7-momentum070-exit-time33-target80-trail25-giveback40`
  `risk.time_exit_pct = 33.0`, `risk.profit_target_pct = 80.0`, `early_exit.trailing_profit_pct = 25.0`, `early_exit.trailing_giveback_pct = 40.0`

## Evaluation Notes

- Keep the same fixed matrix: `1y/2y`, `n_picks=1`, `iv_adj=1.2`, `mid` and `pessimistic`
- Keep the playbooks: `broad`, `bullish_momentum`, `bearish_defensive`
- Judge mainly on `broad / 2y / pessimistic`
- Confirm `broad / 2y / mid` and `bullish_momentum / 2y / pessimistic` agree
- Reject any result that only looks better because the cohort becomes too sparse
- Keep fills, expectancy calibration, stability gates, and watch/block policy unchanged
