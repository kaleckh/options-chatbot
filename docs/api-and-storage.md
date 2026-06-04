# API And Storage

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Runtime Layers

There are three runtime layers in the active browser app:

1. client components under `src/components/*`
2. same-origin Next route handlers under `src/app/api/*`
3. FastAPI app composition in `python-backend/main.py`, with extracted routers such as `python-backend/profile_routes.py`

`src/lib/python-bridge.ts` is the contract layer between the Next route handlers and FastAPI.
The actual request helpers now live under `src/lib/backend/*`, while `src/lib/python-bridge.ts` stays as a compatibility barrel.

## Active Browser-Facing Next Route Groups

### Scan And Replay

- `POST /api/scan`
  - live options scan; uses `bullish_pullback_observation` / Bullish Pullback only as the technical fallback when no playbook is supplied
  - when forward evidence recording succeeds, returned picks carry `source_scan_session_id`, `source_scan_event_key`, `source_scan_run_id`, and `source_scan_recorded_at_utc` so a browser-created tracked position can preserve its scan lineage
- `POST /api/backtest`
  - run replay
  - state-changing Strategy Lab replay run; requires `x-strategy-lab-mutation: run_replay_backtest`
  - response lifecycle headers identify the write as `latest_replay_artifacts` / `replay_run` / `backtest_result`
- `GET /api/backtest/summary`
  - combined replay artifact bundle
  - passive read; response lifecycle headers identify `latest_replay_artifacts` / `read` / `backtest_artifact_bundle`
- `GET /api/backtest/last`
  - most recent saved replay result
- `GET /api/backtest/live-policy`
  - replay-backed policy
- `GET /api/backtest/report`
  - grouped replay report
- `GET /api/backtest/metric-truth`
  - truth or calibration report
- `GET /api/backtest/comparison`
  - synthetic vs imported comparison
- `GET /api/backtest/forward-evidence`
  - forward evidence health
- `GET /api/backtest/exit-audit`
  - playbook exit audit

### Profile And Status

- `GET /api/profile`
  - passive Strategy Lab profile read; response lifecycle headers identify `strategy_profile_files` / `read` / `strategy_profile`
- `PUT /api/profile`
  - state-changing Strategy Lab profile save; requires `x-strategy-lab-mutation: save_strategy_profile`
  - response lifecycle headers identify `strategy_profile_files` / `profile_save` / `strategy_profile`
- `GET /api/changelog`
  - passive Strategy Lab profile changelog read; response lifecycle headers identify `strategy_profile_files` / `read` / `strategy_profile`
- `GET /api/risk-settings`
- `GET /api/options-profit/status`

### Predictions

- `GET /api/predictions`
- `POST /api/predictions/grade`

FastAPI also exposes `DELETE /api/predictions/{pred_id}`, but there is no matching Next route handler in this worktree.

### Tracked Positions

- `GET /api/positions`
- `POST /api/positions`
- `POST /api/positions/review`
- `POST /api/positions/{id}/close`

Store ownership:
- route contracts live in `src/lib/trading-desk/storeOwnership.ts`
- responses carry `x-trading-desk-store: postgres_tracked_positions`
- responses carry `x-trading-desk-record-class: tracked_position`
- lifecycle is exposed through `x-trading-desk-lifecycle`
- mutation routes also require the matching `x-trading-desk-mutation` intent header
- live-scan proof classification requires exact contract identity, executable scan entry evidence, and source scan lineage verified against the forward-evidence ledger; verification checks the recorded event's contract identity and execution fields, and exact-looking payloads with missing, fabricated, or price-mutated scan provenance remain proof-ineligible

### Suggested Trades

- `GET /api/suggested-trades`
- `POST /api/suggested-trades`
- `POST /api/suggested-trades/review`
- `POST /api/suggested-trades/{id}/close`

Store ownership:
- route contracts live in `src/lib/trading-desk/storeOwnership.ts`
- responses carry `x-trading-desk-store: sqlite_suggested_trades`
- responses carry `x-trading-desk-record-class: suggested_trade`
- lifecycle is exposed through `x-trading-desk-lifecycle`
- mutation routes also require the matching `x-trading-desk-mutation` intent header

### Support

- `POST /api/tools/{name}`
- `GET /api/sectors`

## Snapshot Warning

The current worktree does not include active Next route handlers for `src/app/api/day-trading/*`. The directories exist only as empty scaffolding folders, so any older docs that describe those as current browser endpoints are stale for this snapshot.

## Backend-Only FastAPI Endpoints

These FastAPI routes are not currently mirrored through `src/app/api/*`:

- `GET /api/profiles`
- `DELETE /api/predictions/{pred_id}`
- `GET /api/positions/{position_id}/close-prefill`
- `POST /api/scan/recommendations`
- `POST /api/scan/roll`
- `POST /api/backtest/archived-forward`
- `POST /api/backtest/experiments`
- `GET /api/backtest/profitability-forensics`
- `GET /api/backtest/stability`
- `GET /api/market-data/cache-stats`
- `POST /api/market-data/cache-stats/reset`
- `GET /api/daily-performance`
- `GET /api/health`
- `GET /api/proof-summary`

The browser Strategy Lab route contract lives in `src/lib/strategy-lab/replayIntent.ts`. It intentionally covers the mounted Next routes only: replay artifact reads, explicit replay runs, and explicit strategy profile saves. Backend-only backtest support endpoints remain direct FastAPI research/support surfaces and should not be treated as browser UX entrypoints until a matching Next route and Strategy Lab contract are added.

## Storage Layers

### SQLite

Primary file:
- `chat_history.db`

Used for:
- suggested trades
- local workflow state

### Postgres

Configured by:
- `DATABASE_URL`
- `compose.yaml`

Used for:
- tracked positions
- tracked-position reviews

### JSON And Artifact Files

Common files:
- `predictions.json`
- `wfo_results.json`
- `strategy_profile.json`
- `brain_changelog.json`

Artifact directories:
- `data/options-validation/*`
- `data/options-profit/*`
- `data/forward-tracking/*`
- `data/ai-commodity-infra/*`
- `data/alpaca-options-strategy-lab/*`
- `docs/autoresearch/*`

Used for:
- replay outputs
- imported options truth storage
- canonical and archive forward evidence
- policy artifacts
- truth-gate state
- forward evidence
- AI commodity OPRA capture progress and lane proof-readiness evidence
- research-only exact bid/ask lab output
- research proposals and snapshots

### Market Data Cache

Primary file:
- `market_data.db`

Used for:
- market data caching and historical support workflows

## Ownership Map

- Next route handlers
  - request validation and same-origin proxying only
- `src/lib/trading-desk/storeOwnership.ts`
  - executable Trading Desk route-to-store lifecycle contract for tracked positions and suggested trades
- `src/lib/python-bridge.ts`
  - compatibility barrel for the backend client modules
- `src/lib/backend/*`
  - backend HTTP transport plus domain-specific request helpers
- `python-backend/main.py`
  - FastAPI app composition, router mounting, and cache orchestration
- `python-backend/profile_routes.py`
  - profile, profile changelog, `/api/profiles`, and risk settings routes
- `options_chatbot.py`
  - options scan and profile-era domain logic
- `wfo_optimizer.py`
  - replay and policy generation
- `scripts/run_ai_commodity_opra_progress.py`
  - AI commodity OPRA proof-lane orchestration and generated readbacks
- repository modules
  - tracked positions and suggested-trade persistence

## Fast Reading Order

1. `src/components/layout/AppShell.tsx`
2. `src/lib/python-bridge.ts`
3. `src/lib/backend/*`
4. `src/app/api/scan/route.ts`
5. `python-backend/main.py`
6. `python-backend/profile_routes.py`
7. `python-backend/positions_service.py`
8. `python-backend/positions_repository.py`
9. `options_chatbot.py`
10. `wfo_optimizer.py`
