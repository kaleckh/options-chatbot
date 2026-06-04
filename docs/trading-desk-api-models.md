# Trading Desk API Models

This file, `docs/trading-desk-api-models.md`, is the semantic owner for the Point 16 Pydantic API model boundary. The code owner is `python-backend/trading_desk_api_models.py`.

The current model layer is intentionally narrow. It names and validates the top-level request shape for Trading Desk mutation bodies while preserving the existing route parsers, status codes, proof rules, scanner creation safety, storage ownership, and response JSON.

## Modeled Now

The model manifest covers these active Trading Desk mutation routes:

| Route | Request model | Response envelope model |
| --- | --- | --- |
| `POST /api/positions` | `CreateTradingDeskRecordBody` | `TrackedPositionEnvelope` |
| `POST /api/positions/review` | `ReviewTradingDeskRecordsBody` | `TrackedPositionsEnvelope` |
| `POST /api/positions/{id}/close` | `CloseTradingDeskRecordBody` | `TrackedPositionEnvelope` |
| `POST /api/suggested-trades` | `CreateTradingDeskRecordBody` | `SuggestedTradeEnvelope` |
| `POST /api/suggested-trades/review` | `ReviewTradingDeskRecordsBody` | `SuggestedTradesEnvelope` |
| `POST /api/suggested-trades/{id}/close` | `CloseTradingDeskRecordBody` | `SuggestedTradeEnvelope` |

The FastAPI handlers still receive `dict[str, Any]` request bodies. They parse those dictionaries through the internal Pydantic models inside the existing `try` blocks and then continue with the existing helper parsers.

The TypeScript companion contract is `docs/typescript-api-contracts.md` and `src/lib/trading-desk/apiContracts.ts`. It names the browser/Next/backend-helper request and response envelopes manually; it is not generated from these Pydantic models.

The generated schema bridge is `data/contracts/trading-desk-api-schema-bridge.json` with generated Markdown at `docs/trading-desk-schema-bridge.md`. It maps the Pydantic adapter schemas to manual TypeScript names for documentation and drift checks only. It is not runtime validation, OpenAPI, FastAPI `response_model`, automatic `422`, or generated TypeScript.

## Preserved Semantics

- Invalid Trading Desk mutation bodies continue to return route-owned `400` responses instead of automatic FastAPI `422` responses.
- Numeric and boolean semantics remain owned by `_parse_positive_price`, `_parse_positive_int`, `_parse_nonnegative_price`, `_parse_position_ids`, and `_parse_optional_iso_datetime`.
- Scanner-origin creation safety remains owned by `docs/scanner-creation-safety-contract.md` and the existing scanner guard helpers.
- Proof and evidence semantics remain owned by `docs/proof-evidence-contract.md` and `python-backend/proof_contract.py`.
- Pydantic response envelope models are drift guards for tests and docs only; routes do not use `response_model=`.
- Suggested-trade envelopes intentionally do not include `position_event_persistence`.
- Tracked-position envelopes may include `position_event_persistence`.

## Deferred

Do not add these in Point 16:

- FastAPI endpoint body annotations that trigger automatic 422 validation.
- `response_model=` decorators.
- Deep tracked-position row models.
- Full scan-pick, proof, scanner, replay, or repository schemas.
- Query parameter models.
- OpenAPI or TypeScript generation.
- Runtime JSON Schema, Zod, or AJV validation.
- All-route Pydantic sweeps.

Those belong to later API and generated-schema points.

## Implementation Anchors

- API model manifest: `python-backend/trading_desk_api_models.py`
- FastAPI route adapter use: `python-backend/main.py`
- Generated documentation/check bridge: `docs/trading-desk-schema-bridge.md`, `data/contracts/trading-desk-api-schema-bridge.json`, and `scripts/generate_trading_desk_schema_bridge.py`
- Store/record parity: `docs/trading-desk-record-parity.md`
- Route/store lifecycle headers: `src/lib/trading-desk/storeOwnership.ts`
- Mutation intent: `src/lib/trading-desk/mutationIntent.ts`
- Scanner creation safety: `docs/scanner-creation-safety-contract.md`
- Proof/evidence contract: `docs/proof-evidence-contract.md`
- Contract tests: `tests/test_trading_desk_api_models.py`
