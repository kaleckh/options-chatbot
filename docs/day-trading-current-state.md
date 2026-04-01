# Day Trading Current State

Last updated: 2026-03-30

## Goal

The day-trading goal is a supervised morning setup assistant:
- keep a small set of intraday strategies
- rank them by historical hit rate and profitability
- check whether the setup is live during the morning session
- notify the user only when a replay-approved setup is actually active
- keep the user in control of the buy decision

This is not an autonomous execution system.

## What Exists Now

### Strategy slate

The managed day-trading slate is now four ETF morning setups:
- `SPY 5m Opening Range Breakout`
- `QQQ 5m Opening Range Breakout`
- `SPY 5m VWAP Reclaim`
- `QQQ 5m VWAP Reclaim`

These live in:
- `src/lib/day-trading/engine.js`
- `data/day-trading/strategies.json`

Managed strategies are versioned. When the repo strategy slate changes, older managed specs are replaced by the newer default version so stale `backtest_failed` states do not linger forever.

### Validation flow

The day-trading lab can:
- fetch intraday Yahoo bars
- enrich bars with opening-range and VWAP reclaim signals
- run a deterministic backtest model
- simulate paper-trade opens/closes
- score and stage strategies
- sweep parameter variants without mutating the managed strategy slate

Public surfaces:
- `GET /api/day-trading`
- `POST /api/day-trading`
- `GET /api/day-trading/watchlist`

CLI:
- `npm run daytrading:validate`
- `npm run daytrading:watch`
- `npm run daytrading:experiments`
- `npm run daytrading:test`

### Watchlist behavior

The live watchlist now:
- ranks strategies by replay evidence
- checks live morning trigger status on current intraday data
- only marks `notifyNow` when the setup is live and the strategy is replay-eligible

Important implication:
- a strategy can be `triggered_now` without being notification-worthy if its replay evidence is too weak

## Deterministic Coverage

There is now deterministic Node coverage for:
- profitable replay summaries
- risk gating
- validation persistence
- watchlist ranking and live trigger detection
- experiment ranking and strict market-data gating

Main test file:
- `tests/day-trading/engine.test.js`

Fixture helpers:
- `tests/day-trading/fixtures.js`

## Current Live Evidence

Latest live validation command:

```bash
node scripts/run_day_trading_validation.js --bars=3120
```

Current result on 2026-03-30:
- all 4 strategies are `backtest_failed`
- no strategy is alert-eligible
- no paper activity was opened

Most important live summaries:
- `SPY VWAP Reclaim`
  - 17 trades
  - `-0.0074%` total net return
  - `29.4%` win rate
  - `0.56` profit factor
- `SPY Opening Range Breakout`
  - 15 trades
  - `-0.0091%` total net return
  - `40.0%` win rate
  - `0.39` profit factor
- `QQQ VWAP Reclaim`
  - 14 trades
  - `-0.0029%` total net return
  - `35.7%` win rate
  - `0.75` profit factor
- `QQQ Opening Range Breakout`
  - 14 trades
  - `-0.0090%` total net return
  - `35.7%` win rate
  - `0.38` profit factor

Latest live watchlist command:

```bash
node scripts/run_day_trading_watchlist.js --bars=3120 --limit=4
```

Current result on 2026-03-30:
- `notifyNowCount: 0`
- `morningWindow.activeNow: false`
- every ranked setup is `alertEligible: false`

Latest live experiment command:

```bash
node scripts/run_day_trading_experiments.js --bars=3120 --top=12
```

Current result on 2026-03-30:
- `324` trusted variants tested
- `0` promotion-eligible variants
- recommendation: `continue_strategy_iteration`
- the best current pocket is `QQQ 5m VWAP Reclaim` with a stricter threshold and faster exits

Top live experiment leaders:
- `QQQ VWAP Reclaim`
  - threshold `0.74`
  - take profit `0.75%`
  - stop loss `0.45%`
  - max hold `8` bars
  - `12` trades
  - `0.0056%` total net return
  - `58.3%` win rate
  - `2.32` profit factor
  - still vetoed for `insufficient_trades:12<16`
- `SPY VWAP Reclaim`
  - best visible leader in the top set used threshold `0.74`
  - take profit `0.75%`
  - stop loss `0.35%`
  - max hold `12` bars
  - `12` trades
  - `0.0025%` total net return
  - `50.0%` win rate
  - `1.31` profit factor
  - still vetoed for `insufficient_trades:12<16`

Interpretation:
- the current edge looks more promising in `QQQ VWAP Reclaim` than in either opening-range breakout
- the main blocker is sample depth, not just outright unprofitability
- this is still not enough evidence to enable live alerts

Latest focused experiment command:

```bash
node scripts/run_day_trading_experiments.js --bars=3120 --top=16 --preset=focus16
```

Current result on 2026-03-30:
- `16` trusted variants tested
- `0` promotion-eligible variants
- the focused preset also favors `QQQ` and `SPY` VWAP reclaim over both opening-range breakouts
- the best focused leaders still only produced `11` to `12` trades, so the live gate remains correctly blocked

## Important Logic Changes

### Research reliability

The lab now uses more intraday history by default:
- default bars: `3120`

Yahoo intraday fetch now attempts a wider range for 5m and 15m data before falling back to narrower history.

The experiment runner uses strict market-data mode by default:
- real Yahoo bars are accepted
- synthetic fallback bars are marked untrusted
- untrusted runs cannot promote a strategy

### Promotion gate

A strategy is no longer considered promotion-eligible just because it has enough trades.

Current veto logic also blocks:
- non-positive total return
- profit factor below `1`
- win rate below `50%`

This is intentionally conservative because the product goal is "few high-quality morning alerts," not "always have something to trade."

## Data Quality Reality Check

Yahoo intraday data is useful for:
- research
- supervised watchlists
- rough morning setup detection

Yahoo intraday data is not enough by itself for:
- execution-grade alerts
- autonomous trading
- precise fill-quality assumptions

Why:
- exchange timing can be delayed or inconsistent
- this lab uses chart bars, not broker-grade tick or order-book data
- if Yahoo fails, the lab can fall back to synthetic bars, which is now explicitly disqualified in experiment strict mode

The safe posture is:
- use Yahoo to narrow the field
- confirm a live setup against a broker or real-time market source before acting

## Current Recommendation

Do not enable notifications yet.

The watchlist and experiment infrastructure are now real enough to support notifications, but the current strategy slate has not earned that right. The right next step is to keep iterating through replay-backed parameter sweeps until at least one setup is:
- replay-eligible
- positive return
- profit factor above `1`
- win rate above `50%`
- supported by trusted intraday market data

The current best next move is:
1. extend the experiment runner to a focused 16-variant morning sweep for the most promising ETF setups
2. prioritize `QQQ VWAP Reclaim` variants before opening-range breakout variants
3. increase the evidence window with a better intraday source before enabling notifications

Only after that should we add an actual notification transport layer.
