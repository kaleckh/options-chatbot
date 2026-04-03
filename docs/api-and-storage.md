# API And Storage

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Options Endpoints That Matter Most

### Scanner and replay truth

- `POST /api/scan`
  - runs the live options scan
  - can apply replay-backed focus or broader all-qualifying mode
  - can apply playbook guardrails
  - returns policy decisions, guardrail decisions, and size guidance
- `GET /api/backtest/live-policy`
  - returns the current replay-backed policy bundle
  - carries source metadata including replay run time, lookback, pricing lane, playbook, and promotion status
- `GET /api/backtest/exit-audit`
  - returns the playbook cohort audit
  - carries source metadata and current promotion status
- `GET /api/backtest/metric-truth`
  - returns score calibration and metric-health diagnostics
- `POST /api/backtest/experiments`
  - returns the ranked experiment matrix

### Tracked positions

- `POST /api/positions`
  - creates a tracked position from a scan pick and real fill data
  - persists exact contract identity when the scan pick includes it
- `GET /api/positions`
  - lists tracked positions
- `POST /api/positions/review`
  - reviews open tracked positions and returns `HOLD` or `SELL`
  - exact contract matching comes first
  - nearest-strike substitution is disabled for tracked positions
  - unpriceable contracts return warnings instead of synthetic substitutes
- `POST /api/positions/{id}/close`
  - closes a tracked position
  - rejects invalid exit prices
  - rejects already-closed positions clearly

### Suggested trades

- `POST /api/suggested-trades`
  - saves a hypothetical scanner idea
- `GET /api/suggested-trades`
  - lists hypothetical trades
- `POST /api/suggested-trades/review`
  - reviews hypothetical trades
- `POST /api/suggested-trades/{id}/close`
  - closes a hypothetical trade

Suggested trades stay separate from tracked positions by design.

## Day-Trading Endpoints

The day-trading lab is read-heavy with a single validation write surface.

- `GET /api/day-trading?market=crypto|equities_legacy`
  - returns the current snapshot for the selected market
  - crypto snapshots now include the operating plan, milestone state, today-gate state, journal schema, and execution summary
- `POST /api/day-trading?market=crypto|equities_legacy`
  - runs a validation cycle and refreshes the snapshot artifacts
- `GET /api/day-trading/watchlist?market=crypto|equities_legacy`
  - returns the current watchlist
  - crypto watchlist items now expose regime state, tradeability, blocker reasons, and approval-slot visibility

The BTC pilot approval and journal flows remain CLI-first in v1:
- `npm run daytrading:preflight`
- `npm run daytrading:journal:add`

There is intentionally no browser write route for preflight tickets or pilot journal entries yet.

## Frontend Surfaces

The main supervised options workflow lives in:
- `src/components/predictions/PredictionsView.tsx`

The day-trading surface lives in:
- `src/components/strategy/DayTradingLab.tsx`

The main application shell lives in:
- `src/components/layout/AppShell.tsx`

The intended top-level product split is:
1. options scanner and supervised position review
2. research lab surfaces, including crypto day trading
3. legacy analytics after the core supervised workflow

Bridge helpers and shared frontend types live in:
- `src/lib/python-bridge.ts`
- `src/lib/types.ts`

## Storage Layers

### SQLite

File:
- `chat_history.db`

Purpose:
- suggested trades and suggested-trade reviews
- local workflow state used by the scanner and research surfaces

### JSON

Important options artifacts:
- `wfo_results.json`
- `predictions.json`
- `strategy_profile.json`
- `sim_settings.json`

Important crypto day-trading artifacts:
- `data/day-trading/crypto/strategies.json`
- `data/day-trading/crypto/backtests/`
- `data/day-trading/crypto/trading_validation_report.json`
- `data/day-trading/crypto/watchlist_latest.json`
- `data/day-trading/crypto/profitability_journal.json`
- `data/day-trading/crypto/profitability_preflight_tickets.json`

Important legacy day-trading artifacts:
- `data/day-trading/strategies.json`
- `data/day-trading/backtests/`
- `data/day-trading/trading_validation_report.json`

Purpose:
- replay and prediction-era artifacts
- configuration and profile state
- day-trading validation, watchlist, and pilot state

### Postgres

Configured by:
- `DATABASE_URL`
- `compose.yaml`

Purpose:
- tracked positions
- tracked-position reviews

The tracked-position schema stores exact contract identity when available, alongside the original scanner snapshot.

## Important Commands

Core app:
- `npm run dev`
- `npm run dev:next`
- `npm run dev:python`
- `npm run build`
- `npm run build:clean`

Verification:
- `npm run verify`
- `npm run verify:fast`
- `npm run verify:full`
- `python -m unittest discover -s tests -p "test_*.py" -v`

Options research:
- `python scripts/options_algorithm_smoke.py`
- `python scripts/options_experiment_matrix.py`
- `python scripts/options_metric_truth_report.py`
- `python scripts/options_experiment_scoreboard.py`

Crypto day trading:
- `npm run daytrading:test`
- `npm run daytrading:import:crypto -- --days=90`
- `npm run daytrading:validate -- --bars=all --window-mode=scheduled_windows`
- `npm run daytrading:watch`
- `npm run daytrading:preflight -- --setup-match-confirmed=true --headline-lockout-checked=true --maker-limit-plan-confirmed=true`
- `npm run daytrading:pilot`

Profit loop:
- `npm run profit-loop:health`
- `npm run profit-loop:holdout`
- `npm run profit-loop:validate`
- `npm run profit-loop:canary`

## Most Important Files For Future Context

- `options_chatbot.py`
- `wfo_optimizer.py`
- `python-backend/main.py`
- `python-backend/positions_service.py`
- `python-backend/positions_repository.py`
- `src/components/predictions/PredictionsView.tsx`
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `docs/current-state.md`
- `docs/day-trading-current-state.md`

Start there before reading older prediction-era or experiment-only surfaces.
