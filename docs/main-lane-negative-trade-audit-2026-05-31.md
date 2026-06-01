# Main Lane Negative Trade Audit - 2026-05-31

## Scope

This audit covers the main regular supervised options lane, `bullish_pullback_observation` / Bullish Pullback, using the UI-backed Postgres tracked-position store as the canonical tracked ledger. It excludes crypto, Polymarket, day-trading, AI commodity, and non-main all-lane backfills from the main-lane result.

Evidence standard: trusted intraday OPRA/NBBO exact-contract bid/ask evidence is required for proof claims. Research backfills, zero-pick migrations, midpoint-only marks, stale marks, daily/EOD prices, last trades, unresolved candidates, and lifecycle-only rows are not live-production proof.

## Sources

- Postgres via `DATABASE_URL`: `tracked_positions` and `position_reviews`
- `data/forward-tracking/scan_picks.jsonl`
- `data/forward-tracking/fill_attempts.jsonl`
- `data/forward-tracking/main_lane_zero_pick_current_algo_audit_latest.json`
- `data/forward-tracking/main_lane_zero_pick_position_migration_latest.json`
- `data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json`
- `docs/bullish-pullback-ticker-audit-2026-05-29.md`
- `python-backend/positions_service.py`
- `python-backend/positions_repository.py`
- `options_chatbot.py`
- `supervised_scan.py`

## Ledger Inventory

Postgres currently has `536` tracked positions: `485` closed and `51` open. Of those, `62` positions belong to `bullish_pullback_observation`.

| Class | Count |
|---|---:|
| Total Bullish Pullback tracked rows | 62 |
| Closed | 38 |
| Open | 24 |
| Positive or flat P&L | 23 |
| Negative P&L | 26 |
| Unknown/unpriced lifecycle P&L | 13 |
| Live exact-contract scan rows | 2 |
| Research/backfill rows | 60 |

Important read: the two live exact-contract Bullish Pullback positions were not negative in the audited store. The negative set is entirely from migrated historical research/backfill paper rows or open migrated paper rows.

## Why These Trades Were Picked

Bullish Pullback is a call vertical-spread lane. The live signal requires a pullback inside an uptrend: `price > sma50`, `ret20 > 2.0`, and `-4.0 < ret5 < 0.25`. The candidate payload records the main explanation fields: `signal_variant`, `signal_family`, `direction_score`, `quality_score`, `tech_score`, `ev_pct`, `ret5`, `signal_ret20`, `rsi14`, `spy_ret5`, `debit_pct_of_width`, selected spread fields, quote evidence, and `signal_reasons`.

The scanner/playbook also requires vertical spreads, call direction, a maximum debit percentage of width, and an executable candidate label for live promotion. Ranking favors exact/promotable contract evidence, dense calibration, calibrated expectancy, then direction/quality/tech scores.

For the negative backfill rows, the immediate reason they were chosen was that the current Bullish Pullback algorithm would have selected them on historical zero-pick days. That does not make them live picks; their stored `pricing_evidence_class` and `profitability_evidence_class` are `research_backfill`, and their `proof_class` is `ineligible`.

## Negative Trade Table

| ID | Ticker | Bucket | Status | Scan Date | P&L % | Exit Basis | Main Read |
|---:|---|---|---|---|---:|---|---|
| 52 | MSFT | research/data | closed | 2026-04-24 | -76.72 | historical_spread_bid_ask | historical time exit, research backfill |
| 53 | COIN | remove | closed | 2026-04-24 | -61.18 | historical_spread_bid_ask | removed ticker bucket |
| 56 | DIA | move lane | closed | 2026-04-27 | -22.86 | historical_spread_bid_ask | ETF/index scout, not current lane |
| 58 | MSTR | research/data | closed | 2026-04-28 | -14.07 | historical_spread_bid_ask | research/data-needed |
| 60 | DIA | move lane | closed | 2026-04-28 | -27.49 | historical_spread_bid_ask | ETF/index scout, not current lane |
| 61 | BAC | remove | closed | 2026-04-29 | -96.36 | historical_spread_bid_ask | removed ticker bucket |
| 62 | COIN | remove | closed | 2026-04-29 | -21.67 | historical_spread_bid_ask | removed ticker bucket |
| 63 | IWM | keep | closed | 2026-04-29 | -39.57 | historical_spread_bid_ask | keep ticker, but backfill paper only |
| 64 | DIA | move lane | closed | 2026-04-29 | -8.93 | historical_spread_bid_ask | ETF/index scout, not current lane |
| 69 | DIA | move lane | closed | 2026-04-30 | -14.92 | historical_spread_bid_ask | ETF/index scout, not current lane |
| 70 | BA | research/data | closed | 2026-05-01 | -80.71 | historical_spread_bid_ask | research/data-needed |
| 71 | MSFT | research/data | closed | 2026-05-01 | -5.86 | historical_spread_bid_ask | research/data-needed |
| 72 | BA | research/data | closed | 2026-05-04 | -82.41 | historical_spread_bid_ask | research/data-needed |
| 73 | MSFT | research/data | closed | 2026-05-04 | -27.41 | historical_spread_bid_ask | research/data-needed |
| 74 | MSFT | research/data | closed | 2026-05-05 | -24.58 | historical_spread_bid_ask | research/data-needed |
| 75 | C | remove | closed | 2026-05-05 | -77.80 | historical_spread_bid_ask | removed ticker bucket |
| 84 | MSTR | research/data | closed | 2026-05-13 | -88.31 | spread_bid_ask | reviewed after already deeply negative |
| 87 | AMZN | move lane | open | 2026-05-14 | -25.96 | spread_bid_ask | high-beta scout, held inside stop/target |
| 88 | SBUX | research/data | open | 2026-05-14 | -100.00 | spread_bid_ask | executable total-loss stop signal stored |
| 92 | AMZN | move lane | open | 2026-05-15 | -0.43 | spread_bid_ask | small open drawdown |
| 93 | GOOGL | keep | closed | 2026-05-18 | -83.61 | spread_bid_ask | reviewed after already deeply negative |
| 101 | UNH | keep | closed | 2026-05-20 | -63.12 | spread_bid_ask | reviewed after already deeply negative |
| 103 | QQQ | move lane | open | 2026-05-20 | -10.72 | spread_bid_ask | ETF/index scout, held inside stop/target |
| 106 | QQQ | move lane | open | 2026-05-22 | -9.72 | spread_bid_ask | ETF/index scout, held inside stop/target |
| 108 | AMD | research/data | open | 2026-05-22 | -7.09 | spread_bid_ask | research/data-needed |
| 109 | GOOGL | keep | closed | 2026-05-22 | -54.27 | spread_bid_ask | reviewed after already deeply negative |

Bucket view of the `26` negatives:

| Bucket | Negative Rows | Read |
|---|---:|---|
| Research/data-needed | 10 | Should not be promoted into the current lane without new evidence |
| Move to different lane | 8 | Strategically interesting, but should be separate scout hypotheses |
| Remove | 4 | Current ticker audit already says these should be out of the lane |
| Keep in current lane | 4 | Needs focused exit/position-management review, but rows are still backfill/paper |

## Exit Behavior

There is no evidence in the stored review history that the system missed an earlier executable positive exit for the negative rows.

For the first `16` closed negative rows, there are no `position_reviews` rows; they were created as historical backfill rows already closed by historical time-exit logic. The audit can say their final historical exit was negative, but it cannot prove when they first went negative or whether an earlier executable exit was available from the tracked-position review system.

For the later reviewed negative rows, the first stored review was already negative. No audited negative row had a prior positive executable review in `position_reviews`.

Some stored review strings still mention an older `50%` effective stop cap. Current source code has `MAX_LIVE_REVIEW_STOP_LOSS_PCT = 90.0`, so those older review strings are stale review evidence, not the current live policy. Rerun review before taking operational action from those stored messages.

## Root Causes

| Root Cause | Evidence | Protection |
|---|---|---|
| Research/backfill rows migrated into paper tracking | 60 of 62 main-lane rows are `proof_class=ineligible`; all 26 negatives are research/backfill or migrated paper | Keep research/backfill visibly separated from live exact picks and avoid treating migrated rows as production proof |
| Ticker-bucket violations for current-lane intent | 22 of 26 negatives are not in the current keep bucket; 4 are already `remove` | Enforce keep/move/remove buckets before auto-tracking current-lane paper rows |
| Removed tickers still appear in historical paper rows | BAC, C, COIN losses are in the removed bucket | Do not create new main-lane tracked rows for removed tickers; keep historical rows labeled research |
| Scout symbols mixed with current-lane rows | DIA, QQQ, AMZN negatives are move-to-different-lane symbols | Route ETF/index and high-beta names into separate frozen scout lanes before tracking |
| No historical intra-life review trail for early closed backfills | 16 closed negatives have no review timeline | Future migrations should optionally generate deterministic historical review snapshots, or explicitly mark missed-exit audit as unavailable |
| Open paper rows held inside current stop/target policy | AMZN, QQQ, AMD open rows were negative but inside stop/target | Do not tighten stops by default; test profit-harvest/trailing/time-exit variants against replay first |
| Stale review-policy artifacts | Some stored review reasons reflect the old 50% cap despite current code using 90% | Add report/UI labeling for review policy version or review code version |

## Recommended Guardrails

1. Enforce ticker buckets for new Bullish Pullback tracking.
   Main-lane auto-tracking should use only `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, and `NEM` unless the row is explicitly scout-tagged. This would have blocked or redirected `22` of the `26` negative rows in this audit.

2. Keep zero-pick and all-lane backfills research-labeled in the UI.
   These rows are useful learning data, but they should not be visually indistinguishable from live exact-contract scan picks.

3. Add a migrated-paper audit state.
   Use labels such as `Research backfill`, `Historical paper`, `Lifecycle-only`, and `Live exact` in any audit/reporting surface. This prevents a false read that all negative rows are live scanner failures.

4. Do not claim missed exits without historical executable review evidence.
   For earlier-close claims, require exact stored contracts or exact spread legs, trusted intraday bid/ask rows, `price_trigger_ok=true`, non-null `exit_execution_price`, and matching timestamp/rule evidence.

5. Test profit-harvest and giveback exits before tightening stops.
   Current durable policy is a profit-first `90%` live-review stop. A tighter stop would have closed some deep losers, but it may also kill the tested edge. The safer next test is an executable-quote replay of trailing giveback, earlier time-exit, and profit-harvest variants.

6. Add review-policy versioning.
   Store the review engine policy version or effective stop policy in `position_reviews.metrics_snapshot`. This audit found stale stored review text with the old 50% cap, while current code uses 90%.

## What Is Proven

- There are `62` tracked Bullish Pullback rows in the canonical Postgres store.
- `26` are negative by stored executable or assigned P&L fields.
- The two live exact-contract Bullish Pullback rows are not negative in the audited store.
- Every negative row is research/backfill or migrated historical paper, not live-production proof.
- Most negative rows come from symbols that the current ticker audit says should be moved, removed, or kept research-only.

## What Is Not Proven

- It is not proven that the live Bullish Pullback scanner has generated a negative live exact-contract trade in this store.
- It is not proven that earlier executable closes were missed for the first 16 closed negatives, because there is no review timeline for those rows.
- It is not proven that a tighter stop improves the strategy; that needs replay against exact bid/ask exits.
- Lifecycle-only/unpriced rows cannot be counted as losses or wins without trusted exit quotes.

## Verification Notes

Read-only audit commands were run against local files and Postgres. No production state-changing review endpoint was called.

Focused verification still recommended before changing behavior:

```powershell
python -m pytest tests\test_positions_review_engine.py -q
python -m pytest tests\test_strategy_audit.py -q
python -m pytest tests\test_zero_pick_all_lanes_audit.py -q
npm run verify:docs
```
