# Options Product Readiness Audit (2026-03-31)

## Scope

This audit checked whether the options product is:

- real
- usable
- product ready

The focus was the supervised options workflow plus the imported historical validation lane.

## What Was Verified

- The full regression suite passes:
  - `python -m unittest discover -s tests -v`
  - `npx tsc --noEmit`
- Imported daily validation now uses trusted public SPY/QQQ option-chain data rather than fixture-only data.
- Imported-lane artifacts are ignored unless the backing truth store still matches.
- Explicit imported-policy requests now fail closed instead of silently falling back to synthetic results.
- The live API can serve the imported-daily policy path end to end.
- The live smoke output now labels synthetic replay separately from imported-daily policy so the summary cannot blur the two lanes.

## Real Data Loaded

Source:

- [philippdubach/options-data](https://github.com/philippdubach/options-data)
- local files:
  - `tmp_public/spy_options.parquet`
  - `tmp_public/qqq_options.parquet`

Imported into `data/options-validation/options_history.db`:

- `philippdubach_spy_2024`
- `philippdubach_spy_2025`
- `philippdubach_qqq_2024`
- `philippdubach_qqq_2025`

Trusted daily snapshot summary after import:

- snapshot kind: `daily_eod`
- underlyings: `SPY`, `QQQ`
- quote count: `8,572,756`
- batch count: `4`
- quote window: `2024-01-02T20:55:00Z` through `2025-12-15T20:55:00Z`

## Current Imported-Daily Validation Result

Latest imported-daily backtest:

- truth source: `historical_imported_daily`
- validation universe: `SPY`, `QQQ`
- lookback years: `1`
- priced trades: `237`
- unpriced trades: `0`
- quote coverage: `100.0%`
- exact target-contract matches: `57`
- nearest-listed substitutions: `180`
- profit factor: `0.66`
- average trade P&L: `-10.65%`
- directional accuracy: `53.6%`
- promotion status: `block`

Why it is blocked:

- the replay is still unprofitable even with full daily quote coverage
- too much of the broad result still comes from nearest-listed substitutions
- the broad baseline is not strong enough to justify trust-by-default behavior

## 1Y Synthetic vs Imported-Daily Comparison

Matched broad-playbook comparison on a `1y` run:

- synthetic:
  - trades: `7`
  - profit factor: `0.14`
  - average trade P&L: `-56.94%`
  - directional accuracy: `14.3%`
  - quote coverage: `100%` by construction
- imported daily:
  - trades: `237`
  - profit factor: `0.66`
  - average trade P&L: `-10.65%`
  - directional accuracy: `53.6%`
  - quote coverage: `100.0%`

Takeaway:

- the imported daily lane did not rescue the strategy
- real daily quotes improved coverage dramatically but still did not create a profitable broad strategy
- the free daily dataset is useful and honest, but it now points more toward strategy weakness than data scarcity

## Product Verdict

### Real

Yes, with caveats.

- The supervised scan and tracked-position workflow uses real market data at runtime.
- The imported daily validation lane now uses real public SPY/QQQ options-chain data.
- Fixture-only imported artifacts no longer count as validation truth.

### Usable

Yes, as a supervised research and decision-support product.

- The scanner, tracked positions, review flow, and policy endpoints work.
- The imported-daily policy path is live and returns truthful `block/watch` guidance.
- The product now distinguishes synthetic research from imported validation clearly enough to use without self-deception.

### Product Ready

Not yet, if "product ready" means ready to trust for profitable options recommendations.

Current blockers:

1. Imported daily validation is still blocked.
2. Daily validation does not prove morning fill quality.
3. Imported replay still prices replay-selected contracts; it does not recover the exact historical live scan contract from archived scan output.
4. The validated result is still negative even with `100%` broad daily quote coverage.
5. Exact-contract match quality is still weaker than ideal for trust-by-default deployment.

## Live Smoke Snapshot

Current live smoke output:

- scan truth lane: `historical_imported_daily`
- live policy truth source: `historical_imported_daily`
- live policy promotion status: `block`
- live policy quote coverage: `100.0%`
- synthetic backtest truth source: `synthetic_research`
- live scan returned `0` current candidates at audit time

## Important Fixes Landed During This Audit

- Imported validation is now scoped to the intended v1 universe: `SPY` and `QQQ`.
- `build_live_options_trade_policy(truth_lane=...)` now fails closed when the requested lane has no saved result.
- Strategy audit tests no longer read ambient local imported artifacts from disk.
- Daily imports stream parquet in batches and preserve trusted-vs-fixture labeling.
- Daily and intraday snapshots can coexist in the same truth store without uniqueness collisions.

## Operational Notes

- SQLite imports should be run sequentially. Parallel imports can hit `database is locked`.
- The free `philippdubach` data is strong enough for daily exact-contract validation, but not for intraday fill validation.

## Recommended Next Steps

1. Keep using the current imported-daily lane as the truth source for free validation.
2. Treat options strategy optimization as secondary until a narrower pocket earns better exact-contract evidence.
3. Add an intraday quote lane if morning fill realism becomes the next bottleneck.
4. Continue treating the product as supervised research support until imported validation produces positive results in a narrower repeatable slice.
