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
3. FastAPI handlers in `python-backend/main.py`

`src/lib/python-bridge.ts` is the contract layer between the Next route handlers and FastAPI.
The actual request helpers now live under `src/lib/backend/*`, while `src/lib/python-bridge.ts` stays as a compatibility barrel.

## Active Browser-Facing Next Route Groups

### Scan And Replay

- `POST /api/scan`
  - live options scan; defaults to `bullish_pullback_observation` / Bullish Pullback Primary when no playbook is supplied
- `POST /api/backtest`
  - run replay
- `GET /api/backtest/summary`
  - combined replay artifact bundle
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
- `PUT /api/profile`
- `GET /api/changelog`
- `GET /api/risk-settings`
- `GET /api/options-profit/status`

### Predictions

- `GET /api/predictions`
- `POST /api/predictions/grade`

### Tracked Positions

- `GET /api/positions`
- `POST /api/positions`
- `POST /api/positions/review`
- `POST /api/positions/{id}/close`

### Suggested Trades

- `GET /api/suggested-trades`
- `POST /api/suggested-trades`
- `POST /api/suggested-trades/review`
- `POST /api/suggested-trades/{id}/close`

### Support

- `POST /api/tools/{name}`
- `GET /api/sectors`

## Snapshot Warning

The current worktree does not include active Next route handlers for `src/app/api/day-trading/*`. The directories exist only as empty scaffolding folders, so any older docs that describe those as current browser endpoints are stale for this snapshot.

## Backend-Only FastAPI Endpoints

These routes exist in `python-backend/main.py` but are not currently mirrored through `src/app/api/*`:

- `GET /api/profiles`
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
- `docs/autoresearch/*`

Used for:
- replay outputs
- imported options truth storage
- canonical and archive forward evidence
- policy artifacts
- truth-gate state
- forward evidence
- research proposals and snapshots

### Market Data Cache

Primary file:
- `market_data.db`

Used for:
- market data caching and historical support workflows

## Ownership Map

- Next route handlers
  - request validation and same-origin proxying only
- `src/lib/python-bridge.ts`
  - compatibility barrel for the backend client modules
- `src/lib/backend/*`
  - backend HTTP transport plus domain-specific request helpers
- `python-backend/main.py`
  - endpoint composition and cache orchestration
- `options_chatbot.py`
  - options scan and profile-era domain logic
- `wfo_optimizer.py`
  - replay and policy generation
- repository modules
  - tracked positions and suggested-trade persistence

## Fast Reading Order

1. `src/components/layout/AppShell.tsx`
2. `src/lib/python-bridge.ts`
3. `src/lib/backend/*`
4. `src/app/api/scan/route.ts`
5. `python-backend/main.py`
6. `python-backend/positions_service.py`
7. `python-backend/positions_repository.py`
8. `options_chatbot.py`
9. `wfo_optimizer.py`
