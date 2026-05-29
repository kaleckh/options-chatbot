# Day Trading Current State

Last updated: 2026-05-25

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Snapshot Warning

In this worktree, there is no active day-trading Next route or mounted day-trading React surface. `src/app/api/day-trading/*` contains empty scaffolding folders only.

Use this file as a status note for legacy and sidecar code, not as a current browser route map.

## What Exists

### Legacy equity day-trading engine

Main code:
- `src/lib/day-trading/engine.js`

Coverage:
- `tests/day-trading/engine.test.js`
- `tests/day-trading/fixtures.js`

Package command:

```bash
npm run daytrading:test
```

This lane is deterministic test and research code. It is not exposed through the current App Router shell.

### Crypto options sidecar

Main code:
- `crypto_options/config.py`
- `crypto_options/signals.py`
- `crypto_options/deribit.py`
- `crypto_options/execution.py`

Coverage:
- `tests/test_crypto_options_execution.py`

Package commands:

```bash
npm run crypto:signals
npm run crypto:backtest
npm run crypto:chain
npm run crypto:spread
npm run crypto:scan
npm run crypto:monitor
```

Current configured crypto symbols are `ETHUSDT` and `BTCUSDT` in `crypto_options/config.py`. This is a crypto options sidecar that scans local normalized `1m` data, builds `5m` signals, and can route paper or live spread execution through Deribit helpers. It is not the same thing as a mounted day-trading browser product.

## What Does Not Exist In This Worktree

- `src/app/api/day-trading/*` route files
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `tests/day-trading/crypto-engine.test.js`
- package scripts such as `daytrading:watch`, `daytrading:pilot`, or `daytrading:journal:add`

Older day-trading roadmap docs that mention those files or scripts are historical planning records, not the current state.

## Storage Notes

The crypto options sidecar uses:
- `data/day-trading/crypto/normalized-1m`
- `data/forward-tracking/crypto_options_picks.jsonl`

The old broader BTC-first day-trading pilot artifacts described in dated roadmap files are not present as active browser surfaces here.

## Current Recommendation

Keep day-trading work paused unless the user explicitly asks to reopen, archive, or repair it. For current product work, focus on the supervised options browser lane and the AI commodity exact OPRA proof lane.
