# Day Trading Current State

Last updated: 2026-04-01

## Goal

The active day-trading goal is now:
- use the easiest free data source we can trust well enough for research
- test a small set of intraday strategies honestly
- only notify when trusted live data says a replay-backed setup is active
- keep the user in control of the actual trade decision

This is still not an autonomous execution system.

## Active Market Split

The day-trading system now has two lanes:

### `crypto`

This is the default active research track.

- universe: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`
- market type: spot
- exchange/data adapter: `binance_us` first, then global Binance fallback if available
- raw bars: `1m`
- strategy bars: derived `5m`
- monitoring windows:
  - `US Morning` = `08:00-11:00 ET`
  - `Asia Open` = `20:00-23:00 ET`

Main code:
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/index.js`

Managed crypto strategies:
- `BTCUSDT 5m VWAP Reclaim`
- `ETHUSDT 5m VWAP Reclaim`
- `SOLUSDT 5m VWAP Reclaim`
- `BTCUSDT 5m Range Breakout`
- `ETHUSDT 5m EMA Pullback Continuation`
- `SOLUSDT 5m EMA Pullback Continuation`

### `equities_legacy`

This is the older ETF morning lab kept for comparison.

- symbols: `SPY`, `QQQ`
- data source: Yahoo intraday bars
- logic is still morning-session specific

Main code:
- `src/lib/day-trading/engine.js`

## Public Surfaces

Routes:
- `GET /api/day-trading?market=crypto|equities_legacy`
- `POST /api/day-trading?market=crypto|equities_legacy`
- `GET /api/day-trading/watchlist?market=crypto|equities_legacy`

Scripts:
- `npm run daytrading:import:crypto`
- `npm run daytrading:validate`
- `npm run daytrading:watch`
- `npm run daytrading:experiments`
- `npm run daytrading:test`

`crypto` is now the default market for the scripts and the UI.

## Data Stack

### Crypto

The crypto lane uses a free-data-first stack:

- historical backfill via public exchange klines
- local normalized `1m` store
- derived local `5m` bars
- optional live poll merge for watchlist freshness

Storage lives under:
- `data/day-trading/crypto/raw-downloads`
- `data/day-trading/crypto/normalized-1m`
- `data/day-trading/crypto/derived-5m`
- `data/day-trading/crypto/backtests`
- `data/day-trading/crypto/experiments`

Important implementation detail:
- on this U.S. machine, `api.binance.com` returned `HTTP 451`
- the active adapter now prefers `api.binance.us`, which works for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`

### Equities Legacy

The legacy lane still uses:
- Yahoo chart data
- synthetic fallback only for tests/exploration

## Deterministic Coverage

There is now deterministic Node coverage for both lanes.

Legacy equity coverage remains in:
- `tests/day-trading/engine.test.js`

New crypto coverage lives in:
- `tests/day-trading/crypto-engine.test.js`

Crypto tests cover:
- `1m -> 5m` aggregation
- CSV/import path
- validation with trusted fixtures
- watchlist blocking on untrusted data
- router defaulting to crypto while keeping equities legacy reachable

## Current Live Crypto Evidence

### Import

Latest command:

```bash
npm run daytrading:import:crypto -- --days=90
```

Result on 2026-04-01:
- imported `129,600` `1m` bars each for:
  - `BTCUSDT`
  - `ETHUSDT`
  - `SOLUSDT`
- derived `25,921` `5m` bars per symbol
- data window:
  - start: `2026-01-01T21:03:00Z`
  - end: `2026-04-01T21:03:00Z`

### Validation

Latest command pattern:

```bash
npm run daytrading:validate -- --bars=all --window-mode=<mode>
```

Result on 2026-04-01 across the full imported history:
- `6` strategies scanned in every mode
- all `6` remained `backtest_failed`
- no paper positions opened
- all modes used the full `90` day imported span

Window-mode summary:
- `all_hours`
  - `1,143` total trades
  - still clearly negative
  - best leader: `SOLUSDT 5m VWAP Reclaim`
  - `-0.0745%` total net return
  - `34.8%` win rate
  - `0.53` profit factor
- `scheduled_windows`
  - `546` total trades
  - still clearly negative
  - best leader: `SOLUSDT 5m VWAP Reclaim`
  - `-0.0412%` total net return
  - `40.3%` win rate
  - `0.68` profit factor
- `us_morning`
  - `277` total trades
  - least bad mode, but still negative
  - best leader: `SOLUSDT 5m VWAP Reclaim`
  - `-0.0111%` total net return
  - `43.3%` win rate
  - `0.83` profit factor
- `asia_open`
  - `269` total trades
  - still negative
  - best leader: `BTCUSDT 5m Range Breakout`
  - `-0.0265%` total net return
  - `27.6%` win rate
  - `0.52` profit factor

Takeaway:
- the extra data did not uncover a hidden winner
- `us_morning` is less bad than `all_hours`
- the problem is now clearly strategy edge, not data depth or bar scarcity

### Experiments

Latest command:

```bash
node scripts/run_day_trading_experiments.js --market=crypto --bars=all --top=10
```

Result on 2026-04-01:
- research mode: `control_first`
- window modes evaluated:
  - `all_hours`
  - `scheduled_windows`
  - `us_morning`
  - `asia_open`
- `24` trusted control evaluations
- `0` narrow challenger variants unlocked
- recommendation: `strategy_redesign_next_sprint`

What the control-first loop found:
- every family/window review was still `clearly_negative`
- no family qualified for the `20`-trade, “not clearly negative” challenger gate
- the least bad family/window was `crypto_range_breakout` in `us_morning`
  - `42` trades
  - `-0.0107%` aggregate net P&L fraction
  - `0.88` profit factor
- the biggest losers were the all-hours variants, especially:
  - `crypto_ema_pullback_continuation`
    - `731` trades
    - `-0.7718%` aggregate net P&L fraction
    - `0.49` profit factor
  - `crypto_vwap_reclaim`
    - `285` trades
    - `-0.2974%` aggregate net P&L fraction
    - `0.51` profit factor

### Watchlist

Latest command:

```bash
npm run daytrading:watch -- --bars=720 --limit=4
```

Result on 2026-04-01:
- trusted live data loaded successfully from `binance_spot_imported_plus_live`
- `notifyNowCount: 0`
- current evaluation was outside both scheduled windows
- live watchlist stayed locked to `scheduled_windows`
- no notify decisions came from fallback or untrusted data

## Product Shape

The day-trading UI now:
- defaults to `crypto`
- exposes `equities_legacy` as a selector, not the main lane
- shows market/exchange/session metadata
- shows the active scheduled windows for crypto
- keeps real notify decisions blocked when data is stale or untrusted

## Current Recommendation

The crypto pivot is real, usable, and now evidence-rich enough to guide the next sprint honestly.

What is solved:
- easier free data access than equity options or equity intraday research
- honest local research loop
- import, validation, experiments, and live watchlist all run on real crypto data
- full-history `bars=all` validation works
- window-mode sensitivity is measurable instead of assumed
- the broad sweep has been replaced with a tighter control-first loop

What is not solved:
- no crypto strategy is good enough yet
- no live alerts should be enabled
- this is still spot-only research, not futures/perps validation

The next best move is:
1. keep crypto as the active day-trading research lane
2. redesign the crypto strategy slate before adding more challengers
3. keep the watchlist on `scheduled_windows` only
4. only validate futures/perps mechanics after a spot setup survives the stricter replay gate
