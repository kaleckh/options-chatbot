# TypeScript API Contracts

This file, `docs/typescript-api-contracts.md`, is the semantic owner for the Point 17 TypeScript API contract boundary. The code owner for the current Trading Desk slice is `src/lib/trading-desk/apiContracts.ts`.

The current TypeScript contract layer is manual and narrow. It names the browser/Next/FastAPI request and response shapes that the active Trading Desk UI already uses. It does not generate TypeScript or change backend JSON.

Point 20 adds a generated documentation/check bridge at `data/contracts/trading-desk-api-schema-bridge.json` and `docs/trading-desk-schema-bridge.md`. The bridge maps these manual TypeScript names to the narrow Pydantic adapter schemas from `python-backend/trading_desk_api_models.py`; it has `runtime_use=false` and does not add runtime JSON Schema validation, Zod/AJV, OpenAPI, or generated TypeScript.

## Modeled Now

`src/lib/trading-desk/apiContracts.ts` covers the active tracked-position and suggested-trade route families:

| Route family | Named request contracts | Named response contracts |
| --- | --- | --- |
| `GET /api/positions` | `TradingDeskListWindow` | `TrackedPositionsListResponse`, `GroupedTrackedPositionsResponse` |
| `POST /api/positions` | `CreateTrackedPositionRequest` | `CreateTrackedPositionResponse` |
| `POST /api/positions/review` | `ReviewTrackedPositionsRequest` | `ReviewTrackedPositionsResponse` |
| `POST /api/positions/{id}/close` | `CloseTrackedPositionRequest` | `CloseTrackedPositionResponse` |
| `GET /api/suggested-trades` | `TradingDeskListWindow` | `SuggestedTradesListResponse`, `GroupedSuggestedTradesResponse` |
| `POST /api/suggested-trades` | `CreateSuggestedTradeRequest` | `CreateSuggestedTradeResponse` |
| `POST /api/suggested-trades/review` | `ReviewSuggestedTradesRequest` | `ReviewSuggestedTradesResponse` |
| `POST /api/suggested-trades/{id}/close` | `CloseSuggestedTradeRequest` | `CloseSuggestedTradeResponse` |

`src/lib/backend/positions.ts` uses those names for exported helper signatures. The six Next mutation routes parse JSON through `readJsonObject<T>()` using the same request names. `PredictionsView.tsx` and `useTradingDeskRecords.ts` use the named response envelopes when reading Trading Desk mutation and list responses.

## Runtime Response Validation

`src/lib/trading-desk/apiResponseValidation.ts` adds hand-written, shallow response-envelope validation at the Trading Desk Next boundary. The six Next Trading Desk route handlers return through `jsonWithValidatedTradingDeskStore()`, which checks backend payloads before they cross from the FastAPI bridge into the browser product.

Validation is intentionally limited to critical envelope shape:

- unavailable `{ error: string }` sentinels pass through unchanged
- tracked list/review envelopes must use `positions`
- tracked create/close envelopes must use `position`
- tracked mutation envelopes must include object-shaped `position_event_persistence`
- suggested list/review envelopes must use `trades`
- suggested create/close envelopes must use `trade`
- suggested envelopes must reject top-level `position_event_persistence`
- row arrays are checked shallowly for object rows with finite numeric `id` and `status` of `open` or `closed`
- optional `page` metadata must use numeric `limit`, `offset`, and `returned`

Validation failures return `502` from the Next route with `Trading Desk backend response failed validation`, the route contract id, path, reason, and the same Trading Desk store/lifecycle headers. Valid payloads are returned unchanged.

## Preserved Semantics

- Compile-time request/response names and runtime response-envelope validation are manual and Trading Desk scoped.
- `readJsonObject<T>()` still only checks that the body is a JSON object, then returns the typed shape for the route/helper boundary.
- `src/lib/backend/transport.ts` remains the generic transport owner; generic error payloads, tool arguments, and search params can still use open record shapes.
- Suggested trades remain paper/hypothetical workflow state. Their response contracts intentionally use `trade` / `trades` and `position_event_persistence?: never`.
- Tracked-position mutation response contracts may include `position_event_persistence` because lifecycle-event persistence is tracked-only operational observability.
- `SuggestedTrade = TrackedPosition` in `src/lib/types.ts` remains a display-row alias only. Request and response envelopes are no longer aliased.

## Deferred

Still deferred from this TypeScript boundary:

- Pydantic-to-TypeScript generation.
- Zod or other runtime validation at the Next boundary.
- Runtime request-body validation at the Next boundary.
- Deep `TrackedPosition`, `ScanPick`, proof, scanner-lineage, `latest_review`, quote, P&L, or replay validation.
- Full replay, scan, proof, profile, tool, AI commodity, day-trading, crypto, or Polymarket contract sweeps.
- Public route payload reshaping.

Those belong to later API-generation, runtime-validation, and sidecar-cleanup points.

## Implementation Anchors

- TypeScript contract owner: `src/lib/trading-desk/apiContracts.ts`
- Runtime response-envelope validator: `src/lib/trading-desk/apiResponseValidation.ts`
- Backend helper boundary: `src/lib/backend/positions.ts`
- Next JSON object helper: `src/app/api/_utils.ts`
- Python request model companion: `docs/trading-desk-api-models.md` and `python-backend/trading_desk_api_models.py`
- Generated documentation/check bridge: `docs/trading-desk-schema-bridge.md`, `data/contracts/trading-desk-api-schema-bridge.json`, and `scripts/generate_trading_desk_schema_bridge.py`
- Store/lifecycle headers: `src/lib/trading-desk/storeOwnership.ts`
- Mutation intent headers: `src/lib/trading-desk/mutationIntent.ts`
- Display row types: `src/lib/types.ts`
- Static contract tests: `tests/trading-desk/api-contracts.test.js`
- Runtime validation tests: `tests/trading-desk/api-response-validation.test.js`
