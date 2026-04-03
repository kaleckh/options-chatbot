# Day Trading Current State

Last updated: 2026-04-03

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Goal

The active day-trading goal is now:
- prove a repeatable BTC-first edge net of fees and slippage
- keep the user in control of execution
- block low-quality or untrusted live signals instead of forcing trades
- treat research honesty as more important than trade frequency

This is still a research and supervision system, not an autonomous execution stack.

## Active Market Split

The day-trading system has two lanes:

### `crypto`

This is the default active research track.

- universe: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`
- market type: spot
- exchange/data adapter: `binance_us` first, then global Binance fallback when available
- raw bars: `1m`
- strategy bars: derived `5m`
- active session:
  - `Denver Core` = `07:00-11:00 America/Denver` = `09:00-13:00 ET`
- trading days for the profitability pilot:
  - Monday through Friday only

Main code:
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/index.js`

Current managed crypto slate:
- `BTCUSDT 5m Bottom Reclaim`
  - paper-candidate reversal challenger
- `BTCUSDT 5m Failed Breakdown Reclaim`
  - paper-candidate stop-run reversal challenger
- `BTCUSDT 5m Range Mean Reversion`
  - active phase-1 BTC setup
- `BTCUSDT 5m Opening Range Breakout 15m Close`
  - paper-candidate Denver Core breakout challenger
- `BTCUSDT 5m Opening Range Breakout 30m Retest`
  - paper-candidate Denver Core breakout-retest challenger
- `BTCUSDT 5m Trend Continuation`
  - locked until the BTC advance gate passes
- `ETHUSDT 5m Trend Continuation`
  - locked until BTC clears the advance gate
- `SOLUSDT 5m Event Watch`
  - paper-only and disabled for live unlocks until BTC and ETH prove out

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
- `npm run daytrading:preflight`
- `npm run daytrading:pilot`
- `npm run daytrading:journal:add`
- `npm run daytrading:test`

`crypto` is now the default market for the scripts and the UI.

## BTC Profitability Guardrails

The active BTC pilot is enforced in the engine and CLI, not just described in docs.

Current defaults:
- `2` approved BTC entries per `America/Denver` trading day
- unused approvals expire at `11:00 America/Denver`
- every eligible BTC entry needs a same-day ticket plus all three manual confirmations:
  - `setup_match_confirmed`
  - `headline_lockout_checked`
  - `maker_limit_plan_confirmed`
- only ticket-linked BTC entries count toward the pilot sample
- `<30` eligible BTC trades = sample building
- `30-49` eligible BTC trades = review checkpoint
- `50+` eligible BTC trades with all gates passing = ETH unlock candidate

Explicit no-trade blockers for BTC range mean reversion:
- `mid_range`
- `expansion`
- `event_shock_lockout`

Watchlist alerts are also suppressed when:
- data is stale or untrusted
- the fixed session is closed
- the daily approval cap is exhausted

## Data Stack

### Crypto

The crypto lane uses a free-data-first stack:

- public exchange klines for backfill
- local normalized `1m` store
- derived local `5m` bars
- optional live poll merge for watchlist freshness

Storage lives under:
- `data/day-trading/crypto/raw-downloads`
- `data/day-trading/crypto/normalized-1m`
- `data/day-trading/crypto/derived-5m`
- `data/day-trading/crypto/backtests`
- `data/day-trading/crypto/experiments`
- `data/day-trading/crypto/profitability_journal.json`
- `data/day-trading/crypto/profitability_preflight_tickets.json`

Implementation detail that matters on this machine:
- `api.binance.com` has returned `HTTP 451` in this environment
- the active adapter prefers `api.binance.us`, which works for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`

### Equities Legacy

The legacy lane still uses:
- Yahoo chart data
- synthetic fallback only for tests and exploration

## Deterministic Coverage

There is deterministic Node coverage for both lanes.

Legacy equity coverage:
- `tests/day-trading/engine.test.js`

Crypto coverage:
- `tests/day-trading/crypto-engine.test.js`

Crypto tests cover:
- `1m -> 5m` aggregation
- CSV/import path
- validation with trusted fixtures
- watchlist blocking on untrusted data
- BTC preflight ticket cap and expiry behavior
- pilot disqualification accounting
- explicit `mid_range`, `expansion`, and `event_shock_lockout` blockers
- `30`-trade review vs `50`-trade advance milestones
- router defaulting to crypto while keeping equities legacy reachable

## Current UI And API Shape

The day-trading UI now:
- defaults to `crypto`
- keeps `equities_legacy` available behind a selector
- shows the BTC operating plan, checklist, daily cap state, and milestone progress
- shows disqualified-vs-eligible journal counts
- shows compact execution-quality stats from the pilot journal
- shows watchlist blocker states such as `blocked_mid_range`, `blocked_expansion`, and `blocked_event_shock`
- keeps live notify decisions blocked when data is stale, untrusted, or regime-blocked

The snapshot and watchlist payloads now expose:
- operating plan metadata
- today-gate state
- milestone state
- eligibility and disqualification counts
- execution-quality summary fields
- regime state, tradeability, and blocker lists on watchlist items

## Historical Context That Led Here

The current BTC-first guardrails were a response to earlier broad crypto validation, not a random pivot.

What the earlier control-first work established:
- a broad 90-day crypto replay loop was feasible with trusted spot data
- the broad family/window sweep remained negative overall
- more data did not reveal a hidden winner
- the right next move was to narrow the live lane, not widen it

What changed after that work:
- the live workflow standardized on `scheduled_windows`, `denver_core`, and `all_hours`
- the active pilot stopped pretending every family was ready for live comparison
- BTC range mean reversion became the only live phase-1 setup
- ETH and SOL stayed locked behind explicit evidence gates

## Current Recommendation

Keep the crypto lane narrow and honest.

That means:
1. keep BTC spot as the only live pilot lane
2. use the fixed Denver session and the approval ticket flow
3. log execution quality, not just outcome PnL
4. treat the `30`-trade checkpoint as review only
5. only consider ETH after the `50`-trade gate passes cleanly

The older equities lab still has value as a reference surface, but it is no longer the repository’s main day-trading research path.
