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
  - now carries source metadata including replay run time, lookback, pricing lane, playbook, and promotion status
- `GET /api/backtest/exit-audit`
  - returns the playbook cohort audit
  - now carries source metadata and current promotion status
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

## Truth Bundle

The options truth bundle is the canonical artifact set for messaging and debugging:
- `wfo_results.json`
- `python scripts/options_experiment_matrix.py`
- `python scripts/options_metric_truth_report.py`
- `GET /api/backtest/live-policy`
- `GET /api/backtest/exit-audit`

The current options UI should be interpreted through that bundle, not through older handoff summaries.

## Frontend Surfaces

The main supervised options workflow lives in:
- `src/components/predictions/PredictionsView.tsx`

The intended order is now:
1. scanner
2. tracked positions
3. suggested trades
4. legacy analytics tabs after that

The main bridge helpers live in:
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

Important files:
- `wfo_results.json`
- `predictions.json`
- `strategy_profile.json`
- `sim_settings.json`

Purpose:
- replay and prediction-era artifacts
- configuration and profile state

### Postgres

Configured by:
- `DATABASE_URL`
- `compose.yaml`

Purpose:
- tracked positions
- tracked-position reviews

The tracked-position schema now stores exact contract identity when available, alongside the original scanner snapshot.

## Important Commands

- `python -m unittest discover -s tests -v`
  - core Python regression suite
- `npx tsc --noEmit`
  - frontend type check
- `npm run verify`
  - full repo verification gate
- `python scripts/options_algorithm_smoke.py`
  - live-ish options smoke check
- `python scripts/options_experiment_matrix.py`
  - experiment ranking summary
- `python scripts/options_metric_truth_report.py`
  - score calibration and truth summary
- `python scripts/options_experiment_scoreboard.py`
  - cached replay-variant scoreboard

## Most Important Files For Future Context

- `options_chatbot.py`
- `wfo_optimizer.py`
- `python-backend/main.py`
- `python-backend/positions_service.py`
- `python-backend/positions_repository.py`
- `src/components/predictions/PredictionsView.tsx`
- `docs/current-state.md`

Start there before reading legacy prediction or day-trading surfaces.
