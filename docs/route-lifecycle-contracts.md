# Route Lifecycle Contracts

This document owns the descriptive lifecycle headers for mounted Next routes that are not already covered by the Trading Desk or Strategy Lab route-contract registries.

Implementation anchors:

- `src/lib/route-lifecycle/routeContracts.ts`
- `src/app/api/_utils.ts` `jsonWithRouteLifecycle()`
- `scripts/generate_route_parity.py`
- `docs/route-parity.md`
- `tests/ui/route-lifecycle.test.js`

## Purpose

These contracts make generic browser routes easier for agents and senior engineers to classify without reading every handler first. They describe the route family, backing store or artifact owner, lifecycle, and record class.

They are response headers only. They do not authorize a request, validate a payload, change response JSON, change scanner/proof rules, create rows, or replace the domain-specific Trading Desk and Strategy Lab contracts.

## Headers

`jsonWithRouteLifecycle()` adds:

- `x-options-route-contract`
- `x-options-route-family`
- `x-options-route-store`
- `x-options-route-lifecycle`
- `x-options-route-record-class`

Existing domain-specific headers remain authoritative for their domains:

- Trading Desk routes keep `x-trading-desk-*` headers from `src/lib/trading-desk/storeOwnership.ts`.
- Strategy Lab routes keep `x-strategy-lab-*` headers from `src/lib/strategy-lab/replayIntent.ts`.

The generated Trading Desk schema bridge in `docs/trading-desk-schema-bridge.md` is separate. It reads Trading Desk contracts and narrow Pydantic adapter schemas only; generic lifecycle routes stay metadata-only.

## Covered Routes

The generic registry currently covers:

| Contract | Route | Store | Lifecycle | Record class |
| --- | --- | --- | --- | --- |
| `scan_run` | `POST /api/scan` | `forward_evidence_artifacts` | `live_scan_run` | `scan_result` |
| `predictions_read` | `GET /api/predictions` | `predictions_json` | `read` | `prediction_history` |
| `predictions_grade` | `POST /api/predictions/grade` | `predictions_json` | `prediction_grade` | `prediction_history` |
| `risk_settings_read` | `GET /api/risk-settings` | `strategy_profile_files` | `read` | `risk_settings` |
| `options_profit_status_read` | `GET /api/options-profit/status` | `options_profit_state_artifacts` | `read` | `options_profit_status` |
| `operator_session_status` | `GET /api/operator/session` | `local_operator_session_cookie` | `session_status` | `operator_session` |
| `operator_session_unlock` | `POST /api/operator/session` | `local_operator_session_cookie` | `session_unlock` | `operator_session` |
| `sectors_read` | `GET /api/sectors` | `market_data_cache` | `read` | `sector_sentiment_snapshot` |
| `tool_dispatch` | `POST /api/tools/[name]` | `backend_tool_dispatch` | `tool_dispatch` | `tool_result` |

## Generation

`scripts/generate_route_parity.py` reads this registry along with the Trading Desk and Strategy Lab registries. `npm run docs:route-parity` regenerates `docs/route-parity.md`, and `npm run verify:docs` fails when the generated route inventory is stale or route governance rules are violated.

## Non-Goals

Do not use these headers to make proof claims, infer broker fills, validate response bodies, bypass local operator auth, or merge stores. Backend-only FastAPI routes, AI commodity proof artifacts, crypto options, Polymarket, and paused day-trading lanes are outside this generic browser route lifecycle registry unless explicitly reopened by a later decision.
