## Crypto Day-Trading Strategy Roadmap

Last updated: 2026-04-03

### Status Note

This strategy roadmap is historical planning context for the day-trading lane.

The strategy ideas below may still be relevant to the code under `src/lib/day-trading/*`, but any implied browser routes or mounted UI should not be assumed to exist in the current worktree.

### Decision

- The crypto lane is the right place to test new intraday strategies first.
- Keep the options lane focused on measurement truth and live evidence until its gate is healthy again.
- Add new strategy ideas as BTC-first research candidates before cloning them to ETH or SOL.

### Added Now

- `BTCUSDT 5m Bottom Reclaim`
  - family: `crypto_bottom_reclaim`
  - purpose: catch lower-band sweeps that refuse to fully break down
  - core checks:
    - sweep of session or prior-session low
    - lower Bollinger band touch
    - bullish RSI divergence versus a prior confirmed swing low
    - Stoch RSI recovery
    - three-bar volume ramp into the reclaim
    - rejection candle
    - no event-shock lockout

Why this one first:
- BTC is already the anchor for the profitability pilot.
- Current market context is still range-like enough for reversal research to make sense.
- The existing range-mean-reversion pilot already points in the same direction, so this is an additive refinement instead of a brand-new lane.

Initial sanity check on local imported BTC history:
- 90-day replay over imported 1m data aggregated to 5m
- 11 trades
- negative aggregate return
- keep as research-only until it earns a better shape in the control-first loop

- `BTCUSDT 5m Failed Breakdown Reclaim`
  - family: `crypto_failed_breakdown_reclaim`
  - purpose: separate true stop-run reversals from softer lower-band sweeps
  - core checks:
    - break below session, prior-session, or prior swing support
    - close back above the broken level on the reclaim bar
    - next-bar hold above the broken level
    - usable volume and no event-shock lockout

- `BTCUSDT 5m Opening Range Breakout 15m Close`
  - family: `crypto_opening_range_breakout`
  - purpose: test immediate Denver Core breakout continuation after a tight 15-minute range

- `BTCUSDT 5m Opening Range Breakout 30m Retest`
  - family: `crypto_opening_range_breakout`
  - purpose: test Denver Core breakout-retest continuation after a 30-minute range

### Already Tested Locally And Not Worth Re-Adding Unchanged

- `crypto_vwap_reclaim`
- `crypto_range_breakout`
- `crypto_ema_pullback_continuation`

Why they are low priority:
- The latest local experiment sweep still showed `eligibleVariantCount = 0`.
- The repo-level recommendation is still `strategy_redesign_next_sprint`.
- Re-running the same families with the same features is unlikely to unlock a winner.

### Next Testable Strategy Families

1. `BTCUSDT 5m Bollinger Compression Breakout`
- look for low realized range and narrow Bollinger width, then only trade the first real expansion with volume
- use case: clean directional days after compression
- needed features:
  - Bollinger width percentile
  - pre-break compression window
  - post-break volume confirmation

2. `BTCUSDT 5m Session-Reference Mean Reversion`
- reclaim back above a session reference such as VWAP or prior-session close instead of using generic oversold logic
- use case: cleaner intraday reversion than raw RSI fades
- needed features:
  - session reference selector
  - reclaim-close confirmation
  - rotation veto when price never re-enters value

3. `BTCUSDT 5m Trend Day Pullback Continuation (strict)`
- do not bring back the older EMA pullback family unchanged
- only allow it after an opening drive proves trend structure first
- needed features:
  - opening drive filter
  - higher low above VWAP
  - trend persistence score
  - regime veto when the day stays rotational

4. `BTCUSDT 5m Downside Exhaustion Reversal`
- use downside-only intraday pressure instead of generic RSI alone
- use case: late-session washes that reverse without a full event shock
- needed features:
  - downside semivariance or downside return clustering
  - sell-pressure exhaustion score
  - rebound confirmation above short-term structure

### Implemented Research Sequence

1. `BTCUSDT 5m Failed Breakdown Reclaim`
- separate from the bottom-reclaim setup by requiring a real support break, immediate reclaim, and next-bar hold

2. `BTCUSDT 5m Opening Range Breakout (volatility-gated)`
- only active after a tight opening range and an early high-volatility expansion
- use case: trend days, not chop
- needed features:
  - opening-range high/low
  - range compression score
  - volume expansion
  - session trend filter

### Deployment Order

1. Keep all new work BTC-only until one family survives paper review.
2. Run control-first validation on scheduled windows before any wider experiment sweep.
3. Only clone to ETH after BTC clears the 30-trade review checkpoint.
4. Keep SOL as paper-only event research until BTC and ETH prove edge.

### Source Notes

Local repo evidence:
- `data/day-trading/crypto/experiments/latest.json`
- `docs/day-trading-current-state.md`

External research and market context used for prioritization:
- Opening range breakout literature:
  - https://www.diva-portal.org/smash/get/diva2%3A1084388/FULLTEXT01.pdf
  - https://www.diva-portal.org/smash/get/diva2%3A732318/FULLTEXT02.pdf
- Crypto intraday momentum patterns:
  - https://arxiv.org/abs/2009.04200
- Intraday semivariance / momentum reversal idea source:
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3584014
- Current BTC range context on April 1-2, 2026:
  - https://crypto.com/us/market-updates/btc-price-april-2026-macro-data
