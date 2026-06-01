# Runtime Request Flow

## Browser To Backend

The browser never talks directly to FastAPI from the client components. The request path is:

1. client component under `src/components/*`
2. Next route handler under `src/app/api/*`
3. `src/lib/backend/*` through `src/lib/python-bridge.ts`
4. FastAPI handler in `python-backend/main.py`
5. domain module or repository

FastAPI also exposes backend-only support endpoints, but the browser app only reaches the endpoints that are mirrored through `src/app/api/*`.

`docs/route-parity.md` is generated from source and now includes a client fetch surface extracted from active components. `npm run verify:docs` fails when a client component fetches an `/api/*` path without a matching Next route, or when a mirrored Next route has no matching FastAPI decorator.

## Active Route Map

### Options Scan And Diagnostics

- `POST /api/scan`
  - Next: `src/app/api/scan/route.ts`
  - FastAPI: `/api/scan`
  - backend domain: `options_chatbot.py`, `supervised_scan.py`, positions and evidence helpers
- `GET /api/backtest/summary`
  - Next: `src/app/api/backtest/summary/route.ts`
  - FastAPI: `/api/backtest/summary`
  - backend domain: cached builders around `wfo_optimizer.py` and `metric_truth_audit.py`
  - Strategy Lab lifecycle: `latest_replay_artifacts` / `read` / `backtest_artifact_bundle`
- `GET /api/backtest/live-policy`
  - Next: `src/app/api/backtest/live-policy/route.ts`
  - FastAPI: `/api/backtest/live-policy`
- `GET /api/backtest/last`
  - Next: `src/app/api/backtest/last/route.ts`
  - FastAPI: `/api/backtest/last`
- `GET /api/backtest/report`
  - Next: `src/app/api/backtest/report/route.ts`
  - FastAPI: `/api/backtest/report`
- `GET /api/backtest/metric-truth`
  - Next: `src/app/api/backtest/metric-truth/route.ts`
  - FastAPI: `/api/backtest/metric-truth`
- `GET /api/backtest/comparison`
  - Next: `src/app/api/backtest/comparison/route.ts`
  - FastAPI: `/api/backtest/comparison`
- `GET /api/backtest/forward-evidence`
  - Next: `src/app/api/backtest/forward-evidence/route.ts`
  - FastAPI: `/api/backtest/forward-evidence`
- `GET /api/backtest/exit-audit`
  - Next: `src/app/api/backtest/exit-audit/route.ts`
  - FastAPI: `/api/backtest/exit-audit`
- `POST /api/backtest`
  - Next: `src/app/api/backtest/route.ts`
  - FastAPI: `/api/backtest`
  - Strategy Lab lifecycle: requires `x-strategy-lab-mutation: run_replay_backtest`; writes `latest_replay_artifacts` / `replay_run` / `backtest_result`

### Profiles, Predictions, And Status

- `GET /api/profile`
  - Next: `src/app/api/profile/route.ts`
  - FastAPI: `/api/profile`
  - Strategy Lab lifecycle: `strategy_profile_files` / `read` / `strategy_profile`
- `PUT /api/profile`
  - Next: `src/app/api/profile/route.ts`
  - FastAPI: `/api/profile`
  - Strategy Lab lifecycle: requires `x-strategy-lab-mutation: save_strategy_profile`; writes `strategy_profile_files` / `profile_save` / `strategy_profile`
- `GET /api/changelog`
  - Next: `src/app/api/changelog/route.ts`
  - FastAPI: `/api/changelog`
  - Strategy Lab lifecycle: `strategy_profile_files` / `read` / `strategy_profile`
- `GET /api/predictions`
  - Next: `src/app/api/predictions/route.ts`
  - FastAPI: `/api/predictions`
- `POST /api/predictions/grade`
  - Next: `src/app/api/predictions/grade/route.ts`
  - FastAPI: `/api/predictions/grade`
- `GET /api/risk-settings`
  - Next: `src/app/api/risk-settings/route.ts`
  - FastAPI: `/api/risk`
- `GET /api/options-profit/status`
  - Next: `src/app/api/options-profit/status/route.ts`
  - FastAPI: `/api/options-profit/status`

### Tracked Positions

- `GET /api/positions`
  - Next: `src/app/api/positions/route.ts`
  - FastAPI: `/api/positions`
- `POST /api/positions`
  - Next: `src/app/api/positions/route.ts`
  - FastAPI: `/api/positions`
- `POST /api/positions/review`
  - Next: `src/app/api/positions/review/route.ts`
  - FastAPI: `/api/positions/review`
- `POST /api/positions/[id]/close`
  - Next: `src/app/api/positions/[id]/close/route.ts`
  - FastAPI: `/api/positions/{id}/close`

### Suggested Trades

- `GET /api/suggested-trades`
  - Next: `src/app/api/suggested-trades/route.ts`
  - FastAPI: `/api/suggested-trades`
- `POST /api/suggested-trades`
  - Next: `src/app/api/suggested-trades/route.ts`
  - FastAPI: `/api/suggested-trades`
- `POST /api/suggested-trades/review`
  - Next: `src/app/api/suggested-trades/review/route.ts`
  - FastAPI: `/api/suggested-trades/review`
- `POST /api/suggested-trades/[id]/close`
  - Next: `src/app/api/suggested-trades/[id]/close/route.ts`
  - FastAPI: `/api/suggested-trades/{id}/close`

### Tools And Support

- `POST /api/tools/[name]`
  - Next: `src/app/api/tools/[name]/route.ts`
  - FastAPI: `/api/tools/{tool_name}`
- `GET /api/sectors`
  - Next: `src/app/api/sectors/route.ts`
  - FastAPI: `/api/sectors`

## Backend-Only Support Endpoints

These FastAPI routes exist today but do not have matching Next route handlers in this worktree:

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

Backend-only backtest support endpoints are not mounted browser Strategy Lab routes. They should stay direct research/support surfaces unless a future change adds a Next route plus a `src/lib/strategy-lab/replayIntent.ts` contract entry that declares whether the endpoint is passive read, replay artifact write, or profile mutation.

## Snapshot Warning

The current worktree does not include the old `src/app/api/day-trading/*` route files. The folders are still present as empty scaffolding only. Any document that still describes those as active browser endpoints is stale for this snapshot.
