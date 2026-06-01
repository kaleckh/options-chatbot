# Main Product Lane Negative Trade Audit - 2026-05-31

## Scope

This is the broader audit of the Trading Desk regular supervised options product lane. It includes every regular tracked position in the UI-backed Postgres `tracked_positions` ledger, across all supervised scan playbooks currently represented in the Trading Desk.

It intentionally separates live exact-contract tracked rows from migrated historical paper/research backfills. It does not treat crypto, Polymarket, day-trading, or AI commodity proof work as part of this product-lane audit.

Suggested trades were checked separately in `chat_history.db`; the store currently has two `AAA` rows and is not included in the tracked-position product-lane P&L counts.

## Outputs

- Full JSON negative ledger: `data/forward-tracking/main_product_lane_negative_trade_audit_20260531.json`
- CSV negative ledger: `data/forward-tracking/main_product_lane_negative_trade_audit_20260531.csv`
- Narrow Bullish Pullback-only audit: `docs/main-lane-negative-trade-audit-2026-05-31.md`

## Ledger Inventory

Postgres tracked-position state at audit generation:

| Class | Count |
|---|---:|
| Total tracked positions | 536 |
| Closed positions | 487 |
| Open positions | 49 |
| Positive or flat P&L | 261 |
| Negative P&L | 213 |
| Unknown/unpriced lifecycle P&L | 62 |
| Live exact-contract tracked rows | 5 |
| Negative live exact-contract tracked rows | 0 |
| Research/backfill rows | 485 |
| Negative research/backfill rows | 208 |

The headline is the same as the narrow audit, but louder: the product has many negative rows, yet the audit did not find a negative live exact-contract tracked row. The losses are overwhelmingly migrated research/backfill paper rows.

## Playbook Coverage

| Playbook | Total Rows | Negative Rows |
|---|---:|---:|
| `short_term` | 159 | 84 |
| `swing` | 157 | 60 |
| `bullish_pullback_observation` | 62 | 26 |
| `bullish_momentum` | 51 | 23 |
| `legacy_unlabeled` | 46 | 5 |
| `tracked_winner_observation` | 35 | 7 |
| `volatility_expansion_observation` | 13 | 5 |
| `tracked_winner_primary` | 12 | 3 |
| `range_breakout_observation` | 1 | 0 |

## Negative Row Classes

| Record Class | Negative Rows | Read |
|---|---:|---|
| `all_lanes_zero_pick_research_backfill` | 182 | All-lanes historical paper/research migration |
| `main_zero_pick_research_backfill` | 26 | Bullish Pullback zero-pick historical paper/research migration |
| `legacy_or_unknown_tracked` | 5 | Older tracked rows without current proof/backfill classification |
| `live_exact_tracked` | 0 | No negative live exact tracked rows found |

## Worst Concentrations

Top negative tickers:

| Ticker | Negative Rows |
|---|---:|
| XLK | 22 |
| IWM | 22 |
| DIA | 21 |
| SLB | 16 |
| QQQ | 15 |
| SPY | 15 |
| NVDA | 13 |
| GOOGL | 9 |
| NFLX | 9 |
| COIN | 8 |

The worst individual rows are mostly all-lanes short-term/swing research backfills and Bullish Pullback zero-pick research backfills. Several closed at or near `-100%` by historical executable stop or time-exit logic, but they remain research/paper rows, not broker fills.

## Why The Negative Trades Were Picked

The broad product-lane negatives were picked by current or historical scan playbooks when replayed/backfilled over days that previously had no tracked rows:

- `all_lanes_zero_pick_current_algo_v1` generated the majority of broad product negatives.
- `main_lane_zero_pick_current_algo_v1` generated the Bullish Pullback negatives.
- The `source_pick_snapshot` carries the pick rationale fields: playbook, scan date, ticker, selected contract/spread, scores, expectancy, signal fields, and entry evidence.
- The rows are intentionally marked as research/backfill or proof-ineligible, so they should be used to learn failure patterns rather than to claim live system failure.

## Exit Behavior

Most negative backfill rows have no intra-life `position_reviews` timeline. They were inserted as historical paper positions and either closed by historical time-exit/stop logic or left open for later review. That means the audit can identify final negative outcomes, but it cannot honestly prove a missed earlier executable positive close unless the row has timestamped executable review evidence.

For rows with stored reviews, the first review for many losers was already negative. The audit did not find evidence that a live exact row had a prior executable profitable exit that the system ignored.

Some stored review text still reflects an older `50%` effective stop cap. Current code uses the durable profit-first `90%` live-review stop cap. Treat older review text as stale historical review evidence unless the position is freshly reviewed under current code.

## Root Causes

| Root Cause | Evidence | Fix Direction |
|---|---|---|
| Research/backfill rows dominate the negative set | `208` of `213` negatives are research/backfill | Make research/paper/backfill provenance impossible to miss in reports and UI |
| All-lanes migration expanded weak historical paper rows | `182` negatives came from `all_lanes_zero_pick_current_algo_v1` | Do not interpret all-lanes migrated rows as production picks; rank lanes by research value and proof quality |
| Main Bullish Pullback ticker-bucket problem still matters | `26` Bullish Pullback negatives, most outside keep bucket | Enforce keep/move/remove buckets before new current-lane tracking |
| Legacy rows are under-instrumented | `5` negative rows are legacy/unknown tracked | Backfill or quarantine legacy provenance before treating them as proof |
| Missing intra-life review timelines limit missed-exit claims | Many closed negatives have no review rows | Future migrations should optionally generate deterministic historical review snapshots, or explicitly mark missed-exit audit as unavailable |
| Open negative rows often remain inside policy | `16` open negatives, mostly paper/backfill | Test profit harvest/trailing/time-exit variants before changing the durable 90% stop |

## Recommended Guardrails

1. Add a product-lane provenance gate.
   Every Trading Desk row should be visibly one of `Live exact`, `Research backfill`, `Historical paper`, `Lifecycle-only`, or `Legacy/unclassified`.

2. Keep all-lanes zero-pick rows out of production-proof metrics.
   They are useful for learning, but the audit shows they produce most negative rows.

3. Enforce lane-specific eligibility before auto-tracking.
   Bullish Pullback should use the current keep list unless explicitly scout-tagged. Other playbooks need equivalent promotion buckets before they can be read as product-ready.

4. Build a per-playbook negative dashboard.
   Start with `short_term`, `swing`, and `bullish_momentum`, because they account for `167` of the `213` negatives.

5. Require executable review history before claiming missed exits.
   The standard should be exact contract/spread, trusted intraday bid/ask, `price_trigger_ok=true`, non-null executable exit, and timestamped rule evidence.

6. Test exits before tightening stops.
   The next real experiment should compare profit-harvest, trailing giveback, and time-exit variants on exact bid/ask replay. Do not assume tighter stops improve expectancy.

7. Add policy-version fields to reviews.
   Stale `50%` stop messages living beside current `90%` policy create audit confusion.

## What Is Proven

- The Trading Desk tracked ledger has `536` regular product-lane positions at audit generation.
- `213` are negative by stored P&L fields.
- `0` of the `5` live exact-contract tracked rows are negative.
- `208` of `213` negative rows are research/backfill.
- The largest negative concentrations are `short_term`, `swing`, `bullish_pullback_observation`, and `bullish_momentum`.

## What Is Not Proven

- The audit does not prove the live exact-contract scanner is producing negative broker-like fills.
- The audit does not prove missed profitable exits for most closed backfills, because many lack intra-life review history.
- The audit does not prove tighter stops are better.
- Unknown/unpriced lifecycle rows are not wins or losses until trusted exit quotes exist.

## Verification Notes

The audit read local files and Postgres. It did not call the state-changing review endpoint.

Verification run:

```powershell
npm run verify:docs
```
