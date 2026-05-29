# Architecture Audit

Last updated: 2026-05-29

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

The active non-browser proof lane is the AI commodity / commodity-infrastructure lane:

- `scripts/run_ai_commodity_opra_progress.py`
- `data/ai-commodity-infra/universe.json`
- `data/ai-commodity-infra/progress/latest.md`

It is gated on exact Alpaca SIP/OPRA bid/ask snapshot history and is not claim-ready.

The active regular-options proof work is the `bullish_pullback_observation` ThetaData intraday OPRA/NBBO branch. Its route/product shape is unchanged, but current performance state now lives in `docs/bullish-pullback-ticker-audit-2026-05-29.md`, `data/profitability-lab/bullish-pullback-observation/confidence/latest.json`, and `data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json`.

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
- `scripts/run_ai_commodity_opra_progress.py`
  - active research/proof sidecar, not a browser route

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
- `scripts/run_ai_commodity_opra_progress.py`
  - very large AI commodity proof-lane orchestration script
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
- reduce `scripts/run_ai_commodity_opra_progress.py` into:
  - capture guard and calendar logic
  - proof-source audit
  - live scan recovery readback
  - report rendering
  - provider probe adapters

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

The repo is now easier to orient than before, but it is still a mixed-product codebase with one active browser options surface plus proof/research sidecars. The biggest remaining work is reducing the Python monoliths, splitting `PredictionsView.tsx`, and turning the AI commodity proof script into smaller testable modules.
