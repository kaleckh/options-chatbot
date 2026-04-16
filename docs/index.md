# Docs Index

## Start Here

These are the living docs for the current worktree:

- `README.md`
  - top-level product and runtime summary
- `docs/architecture-overview.md`
  - system map, subsystem ownership, and reading order
- `docs/api-and-storage.md`
  - active route groups, backend-only endpoints, and storage ownership
- `docs/route-parity.md`
  - browser route to Next route to FastAPI mapping
- `docs/architecture-audit.md`
  - live audit of dead surfaces, sidecars, and remaining monoliths
- `docs/current-state.md`
  - current options product state
- `docs/day-trading-current-state.md`
  - current day-trading and crypto sidecar snapshot, with archive warnings

## What To Treat As Historical

These files are still useful, but they are records rather than the source of truth for the current app shape:

- dated roadmap and audit files under `docs/`
- `docs/autoresearch/*`
- `research_runs/*`

If a dated doc disagrees with the code or with the living docs above, trust the code first.

## Quick Orientation For A Senior Engineer

Read in this order:

1. `src/components/layout/AppShell.tsx`
2. `src/components/predictions/PredictionsView.tsx`
3. `src/components/strategy/StrategyView.tsx`
4. `src/lib/python-bridge.ts`
5. `src/lib/backend/*`
6. `python-backend/main.py`
7. `options_chatbot.py`
8. `wfo_optimizer.py`

## Snapshot Warnings

- `src/app/page.tsx` is intentionally a stub; the real browser entrypoint is the layout plus app shell.
- `src/app/api/day-trading/*` exists only as empty scaffolding folders in this worktree.
- `src/lib/polymarket/*` and `crypto_options/*` are sidecar lanes, not the mounted browser product.
