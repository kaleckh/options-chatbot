# Runtime Request Flow

## Browser To Backend

The browser never talks directly to FastAPI from the client components. The request path is:

1. client component under `src/components/*`
2. Next route handler under `src/app/api/*`
3. `src/lib/python-bridge.ts`
4. FastAPI handler in `python-backend/main.py`
5. domain module or repository

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
- `GET /api/backtest/live-policy`
  - Next: `src/app/api/backtest/live-policy/route.ts`
  - FastAPI: `/api/backtest/live-policy`
- `GET /api/backtest/report`
  - Next: `src/app/api/backtest/report/route.ts`
  - FastAPI: `/api/backtest/report`
- `GET /api/backtest/metric-truth`
  - Next: `src/app/api/backtest/metric-truth/route.ts`
  - FastAPI: `/api/backtest/metric-truth`
- `GET /api/backtest/comparison`
  - Next: `src/app/api/backtest/comparison/route.ts`
  - FastAPI: `/api/backtest/comparison`
- `POST /api/backtest`
  - Next: `src/app/api/backtest/route.ts`
  - FastAPI: `/api/backtest`

### Profiles, Predictions, And Status

- `GET /api/profile`
  - Next: `src/app/api/profile/route.ts`
  - FastAPI: `/api/profile`
- `PUT /api/profile`
  - Next: `src/app/api/profile/route.ts`
  - FastAPI: `/api/profile`
- `GET /api/changelog`
  - Next: `src/app/api/changelog/route.ts`
  - FastAPI: `/api/changelog`
- `GET /api/predictions`
  - Next: `src/app/api/predictions/route.ts`
  - FastAPI: `/api/predictions`
- `GET /api/predictions/history`
  - Next: `src/app/api/predictions/history/route.ts`
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

## Snapshot Warning

The current worktree does not include the old `src/app/api/day-trading/*` route files. Any document that still describes those as active browser endpoints is stale for this snapshot.
