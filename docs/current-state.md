# Current State

Last updated: 2026-04-15

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Goal

The active browser product is still the supervised options lane:
- surface live options ideas
- let the user log the trades they actually took
- keep tracked positions and suggested trades separate
- review and close positions manually with explicit pricing context

This remains supervised decision support, not autonomous trading.
The default supervised options scanner playbook is `bullish_pullback_observation`, surfaced as Bullish Pullback Primary. That legacy `_observation` cohort ID is not watch-only; eligible scheduled picks can auto-track under the current guardrails. The lane scans a broad liquid options universe, with SPY/QQQ currently marked as the historical-ready subset.

## Snapshot

- The mounted browser surface is still the options lane in `AppShell`, with `PredictionsView` and `StrategyView`.
- The Next route layer under `src/app/api/*` is the only browser-facing API surface in this worktree.
- The repo still contains crypto and legacy day-trading research code, but the old day-trading route files and `DayTradingLab` UI are not present in this checkout. `src/app/api/day-trading/*` exists only as empty scaffolding folders right now.
- Tracked positions are the real supervised lane and live in Postgres via `DATABASE_URL`.
- Suggested trades are the hypothetical lane and live in `chat_history.db`.
- FastAPI exposes support endpoints such as `/api/proof-summary` and `/api/positions/{position_id}/close-prefill`, but those are backend-only right now and are not mirrored through the Next proxy layer.

## Primary Workflow

### 1. Scanner

The scanner runs from `options_chatbot.py` and is exposed through `POST /api/scan`.

The active options workflow in the UI is ordered around:
1. live scan
2. tracked positions
3. suggested trades
4. replay and truth diagnostics

Current scanner behavior is still conservative:
- picks can carry `policy_decision` and `guardrail_decision`
- size and risk hints are surfaced when available
- replay-backed policy output is still fail-closed or watch-oriented, not trust-by-default

### 2. Tracked Positions

Tracked positions are the truth source for real supervised usage.

The current tracked-position flow is:
1. choose a live scan pick
2. enter the actual fill price and contracts
3. save it as a tracked position in Postgres
4. review open positions manually
5. get `HOLD` or `SELL` guidance plus explicit pricing context
6. close the position manually

Tracked-position reviews still prefer exact contract identity:
- exact contract symbols are stored and used first when available
- proof-lane position creation can require exact-contract metadata
- review responses now include explicit pricing-state output instead of silently substituting the nearest strike

### 3. Suggested Trades

Suggested trades are still the hypothetical lane.

They are:
- created manually from scanner picks
- stored separately in SQLite
- reviewed separately
- intentionally not mixed with real tracked positions

## Validation And Proof Snapshot

### Replay state

The latest saved `wfo_results.json` artifact in this worktree was generated on `2026-04-07T13:15:05` and reflects a `2` year `historical_imported_daily` broad replay. It remains unprofitable:
- `total_trades`: `227`
- `directional_accuracy_pct`: `63.4`
- `profit_factor`: `0.57`
- `avg_pnl_pct`: `-14.27`

That means the current saved replay artifact is still useful for supervision and diagnostics, but it does not justify a profitability claim.

### Profit-cycle state

The bounded options profit cycle is currently blocked.

As of `2026-04-15`, `evaluate_measurement_gate()` reports:
- imported-daily quote coverage below the current gate floor
- trusted truth inputs are stale
- zero matured eligible forward events
- zero closed tracked positions for profitability supervision

`data/options-profit/live_profile.json` still shows the incumbent managed candidates as `baseline_broad_control` for `SPY` and `QQQ` on both the call and put sides.

### Proof-lane state

`evaluate_claim_readiness()` is currently `not_claim_ready`.

The current blockers are straightforward:
- `0` matured eligible forward events, versus a `40` event claim threshold
- `0` closed exact-contract tracked positions, versus a `20` position claim threshold
- no realized net profitability evidence yet
- exact-contract capture is still `0%` in the current canonical proof summary

The canonical proof summary exists in FastAPI at `/api/proof-summary`, but the browser app does not proxy it yet.

## What Is Ready vs Not Ready

### Ready

- supervised `scan -> take -> review -> close` workflow
- tracked-position storage and exact-contract-aware review
- suggested-trade storage and review
- replay and truth diagnostics in the strategy surface
- options profit-cycle state artifacts under `data/options-profit/*`

### Not ready

- trust-by-default options deployment
- profitability claims from the current replay artifacts
- claim-ready forward evidence for `SPY` and `QQQ`
- a mounted day-trading browser surface in this worktree

## Current Recommendation

Use the options system as supervised maintenance infrastructure, not as a solved strategy.

That means:
1. scan live ideas
2. log real tracked positions only when they were actually taken
3. use suggested trades for hypothetical evaluation
4. review and close positions manually
5. treat policy output as conservative until the truth inputs are fresh again and the proof lane accumulates real exact-contract evidence

For the separate day-trading research lane, read `docs/day-trading-current-state.md`, but treat it as code and research context rather than the current browser product.
