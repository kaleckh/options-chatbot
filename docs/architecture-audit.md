# Architecture Audit

Last updated: 2026-04-15

## Purpose

This file is the shortest honest answer to:

- what is the active product
- what is sidecar or legacy
- where the dead or confusing surfaces are
- which files are still too large

## Active Product Surface

The mounted browser product is the supervised options lane:

- scanner
- tracked positions
- suggested trades
- replay and truth diagnostics

The real browser entrypoint is:

- `src/app/layout.tsx`
- `src/components/layout/AppShell.tsx`

`src/app/page.tsx` is intentionally a stub.

## Architecture Shape

Current request path:

1. client view under `src/components/*`
2. Next App Router proxy route under `src/app/api/*`
3. backend client helper under `src/lib/backend/*`
4. FastAPI handler in `python-backend/main.py`
5. domain engine or repository

This is the live path a senior engineer should follow first.

## Sidecar And Legacy Lanes

These exist in the repo, but they are not the mounted browser product:

- `src/lib/day-trading/engine.js`
  - legacy equity day-trading research engine
- `crypto_options/*`
  - crypto research and execution sidecar
- `src/lib/polymarket/*`
  - adjacent market tooling, not wired into the main app shell

## Dead Or Misleading Surfaces

- `src/app/api/day-trading/*`
  - empty scaffolding folders only, not live routes
- historical docs that still describe mounted day-trading browser routes
  - archive context only
- removed duplicate Next alias:
  - `GET /api/predictions/history`

## Structural Improvements Already Applied

- `src/lib/python-bridge.ts` is now a small compatibility barrel over `src/lib/backend/*`
- `src/components/strategy/StrategyView.tsx` was reduced into a coordinator over:
  - `src/components/strategy/BrainTab.tsx`
  - `src/components/strategy/OptimizerTab.tsx`
  - `src/components/strategy/shared.tsx`
- legacy analytics tabs were extracted from `src/components/predictions/PredictionsView.tsx` into:
  - `src/components/predictions/legacy-tabs.tsx`
- the stale duplicate Next route `src/app/api/predictions/history/route.ts` was removed
- `run_scan.bat` no longer points at an old machine-specific path

## Largest Remaining Monoliths

These are still the main architecture risks:

- `wfo_optimizer.py`
  - oversized replay and optimization engine
- `options_chatbot.py`
  - oversized scanner and domain logic surface
- `profit_loop_automation.py`
  - oversized automation and policy orchestration surface
- `python-backend/main.py`
  - oversized FastAPI composition layer
- `src/components/predictions/PredictionsView.tsx`
  - still the heaviest active client component
- `src/lib/day-trading/engine.js`
  - legacy monolith kept for deterministic tests and research

## Recommended Next Splits

### Frontend

- split `PredictionsView.tsx` further into:
  - scanner surface
  - tracked positions surface
  - suggested trades surface
  - shared pricing and contract formatting helpers

### Backend

- reduce `python-backend/main.py` into routers by domain:
  - scan
  - backtest and truth
  - positions
  - suggested trades
  - profile and status

### Core Python Domain

- reduce `options_chatbot.py` into:
  - scan assembly
  - policy evaluation
  - profile loading and persistence
  - formatting and artifact helpers
- reduce `wfo_optimizer.py` into:
  - replay engine
  - pricing lane logic
  - report building
  - calibration and truth helpers

## What A Senior Engineer Should Read First

1. `src/components/layout/AppShell.tsx`
2. `docs/route-parity.md`
3. `src/lib/backend/*`
4. `python-backend/main.py`
5. `src/components/predictions/PredictionsView.tsx`
6. `src/components/strategy/StrategyView.tsx`
7. `options_chatbot.py`
8. `wfo_optimizer.py`

## Bottom Line

The repo is now easier to orient than before, but it is still a mixed-product codebase with one active options surface plus multiple sidecar research lanes. The biggest remaining work is reducing the Python monoliths and finishing the split of `PredictionsView.tsx`.
