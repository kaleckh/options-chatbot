# API And Storage

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Runtime Layers

There are three runtime layers in the active browser app:

1. client components under `src/components/*`
2. same-origin Next route handlers under `src/app/api/*`
3. FastAPI app composition in `python-backend/main.py`, with extracted routers such as `python-backend/profile_routes.py`, `python-backend/predictions_routes.py`, and `python-backend/tools_routes.py`

`src/lib/python-bridge.ts` is the contract layer between the Next route handlers and FastAPI.
The actual request helpers now live under `src/lib/backend/*`, while `src/lib/python-bridge.ts` stays as a compatibility barrel.
`docs/route-parity.md` is the generated human route inventory, and `data/contracts/route-mutation-inventory.json` is its generated machine-readable sibling. Together they list mounted browser routes, backend-only FastAPI routes, auth boundaries, mutation-intent labels, lifecycle contracts, stores, owning modules, and active client fetches.
`docs/backend-route-ownership-map.md` and `data/contracts/backend-route-ownership-map.json` are generated readability/check artifacts that map FastAPI decorator files, handler names, router extraction state, service delegation, backend-only surfaces, and owner docs without importing the backend app or changing runtime behavior.
`docs/storage-ownership-map.md` and `data/contracts/storage-ownership-map.json` are generated readability/check artifacts that join route store usage with repository migrations, constraints, indexes, local DB roles, route artifacts, and virtual stores without changing runtime behavior.
`docs/route-lifecycle-contracts.md` owns the descriptive response lifecycle headers for mounted generic Next route groups such as scan, predictions, risk/status, local operator session, sectors, and tools; `src/lib/route-lifecycle/routeContracts.ts` is the registry, and `jsonWithRouteLifecycle()` applies the headers without changing response JSON.
`docs/proof-evidence-contract.md` owns proof/evidence definitions such as truth-grade, production proof, raw exact, manual exact, research/backfill, and lifecycle-only; frontend proof display constants come from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts`. `docs/proof-invariant-table.md` is generated from `data/contracts/proof-invariant-cases.json` as a test/readability matrix for raw exact, production proof, Truth-grade, and realized-P&L boundaries.
`docs/scanner-creation-safety-contract.md` owns the scanner pipeline stage map, scanner-origin creation, scheduled auto-track, and pending-validation safety rules.
`docs/replay-profit-contract.md` owns replay/profit responsibility boundaries for replay readbacks, scanner policy readbacks, proof/profit gates, and options-profit status.
`docs/repository-contract.md` owns Trading Desk repository ownership and structural repository method contracts.
`docs/trading-desk-record-parity.md` owns tracked-position versus suggested-trade route/row parity and separation; `python-backend/repository_parity.py` names the executable manifest.
`docs/trading-desk-api-models.md` owns the narrow Pydantic model boundary for Trading Desk mutation request bodies and top-level response-envelope drift guards; `python-backend/trading_desk_api_models.py` names the six modeled mutation routes without changing FastAPI endpoint annotations or public response JSON.
`docs/typescript-api-contracts.md` owns the narrow TypeScript API contract and runtime response-envelope validation boundary for Trading Desk request/response envelopes; `src/lib/trading-desk/apiContracts.ts` names the browser/Next/backend helper shapes, and `src/lib/trading-desk/apiResponseValidation.ts` validates shallow Trading Desk response envelopes at the Next boundary without generated schemas.
`docs/trading-desk-schema-bridge.md` and `data/contracts/trading-desk-api-schema-bridge.json` are generated documentation/check artifacts from the Trading Desk store, TypeScript, and Pydantic contract owners; they are not OpenAPI, runtime JSON Schema validation, generated TypeScript, or FastAPI `response_model` metadata.
`docs/local-db-hardening.md` owns local SQLite safety, backup discipline, and the read-only local DB audit; `python-backend/local_db_hardening.py` names the local DB role manifest.
`docs/repository-migrations.md` owns Trading Desk repository schema migration rules; `python-backend/repository_migrations.py` owns the versioned manifest and ledger helpers.
`docs/repository-constraints.md` owns Trading Desk repository constraint boundaries; `python-backend/repository_constraints.py` separates DB-enforced, API-enforced, proof-contract-owned, and deferred invariants.
`docs/repository-indexes.md` owns Trading Desk repository index boundaries; `python-backend/repository_indexes.py` separates existing read-path indexes from deferred candidates.

## Authorization Boundaries

There are two separate auth layers:

1. Local operator auth protects browser-facing state-changing and tool routes before body parsing. `src/lib/operator-auth.ts` reads the server-only `OPTIONS_LOCAL_OPERATOR_TOKEN` secret and accepts `x-options-operator-token`, `Authorization: Bearer ...`, or an HttpOnly `options_local_operator_session` cookie opened by `POST /api/operator/session`.
2. Backend bridge auth protects direct FastAPI `/api/*` calls when `OPTIONS_BACKEND_API_TOKEN` is configured. `src/lib/backend/transport.ts` forwards `x-options-backend-token`, and `python-backend/main.py` checks it with a constant-time comparison.

Mutation-intent headers remain separate. `x-trading-desk-mutation` and `x-strategy-lab-mutation` prove caller intent for audited writes, but they are not authorization and must run after local operator auth.

Auth verification map:

- `tests/ui/operator-auth.test.js` proves local operator auth fail-closed behavior, private header / bearer / signed session-cookie allowance, the static guard requirement for browser-facing mutations/tools, generic scan / prediction-grade / tool dispatch rejection and allowance, direct operator-session unlock rejection/cookie flags, and generated route-inventory coverage anchors.
- `tests/trading-desk/mutation-intent.test.js` proves Trading Desk writes require local operator auth before mutation intent, reject intent-only requests, and reach the mocked bridge only with valid auth plus the matching `x-trading-desk-mutation` intent.
- `tests/strategy-lab/replay-intent.test.js` proves Strategy Lab replay/profile writes require local operator auth before mutation intent, reject intent-only requests, and reach the mocked bridge only with valid auth plus the matching `x-strategy-lab-mutation` intent.
- `tests/ui/backend-transport.test.js` and `tests/test_backend_bridge_auth.py` prove the separate Next-to-FastAPI backend bridge token forwarding and direct FastAPI reject/allow behavior.
- `tests/ui/route-lifecycle.test.js` proves local operator session lifecycle headers and generic route lifecycle headers stay attached to successful responses.

## Active Browser-Facing Next Route Groups

### Scan And Replay

- `POST /api/scan`
  - requires local operator auth
  - live options scan; uses `bullish_pullback_observation` / Bullish Pullback only as the technical fallback when no playbook is supplied
  - when forward evidence recording succeeds, returned picks carry `source_scan_session_id`, `source_scan_event_key`, `source_scan_run_id`, and `source_scan_recorded_at_utc` so a browser-created tracked position can preserve its scan lineage
- `POST /api/backtest`
  - run replay
  - requires local operator auth
  - state-changing Strategy Lab replay run; requires `x-strategy-lab-mutation: run_replay_backtest`
  - response lifecycle headers identify the write as `latest_replay_artifacts` / `replay_run` / `backtest_result`
- `GET /api/backtest/summary`
  - combined replay artifact bundle
  - passive read; response lifecycle headers identify `latest_replay_artifacts` / `read` / `backtest_artifact_bundle`
  - FastAPI readback assembly lives in `python-backend/replay_profit_service.py`
- `GET /api/backtest/last`
  - most recent saved replay result
- `GET /api/backtest/live-policy`
  - replay-backed policy
  - ownership boundaries are documented in `docs/replay-profit-contract.md`; scanner still applies policy in `supervised_scan.py`
- `GET /api/backtest/report`
  - grouped replay report
- `GET /api/backtest/metric-truth`
  - truth or calibration report
- `GET /api/backtest/comparison`
  - synthetic vs imported comparison
- `GET /api/backtest/forward-evidence`
  - forward evidence health, including scan capture recording failures and tracked-position lifecycle event recording failures
- `GET /api/backtest/exit-audit`
  - playbook exit audit

### Profile And Status

- `GET /api/profile`
  - passive Strategy Lab profile read; response lifecycle headers identify `strategy_profile_files` / `read` / `strategy_profile`
- `PUT /api/profile`
  - requires local operator auth
  - state-changing Strategy Lab profile save; requires `x-strategy-lab-mutation: save_strategy_profile`
  - response lifecycle headers identify `strategy_profile_files` / `profile_save` / `strategy_profile`
- `GET /api/changelog`
  - passive Strategy Lab profile changelog read; response lifecycle headers identify `strategy_profile_files` / `read` / `strategy_profile`
- `GET /api/risk-settings`
  - passive generic read; response lifecycle headers identify `strategy_profile_files` / `read` / `risk_settings`
- `GET /api/options-profit/status`
  - read-only options-profit status; not a proof owner or row creation path
  - response lifecycle headers identify `options_profit_state_artifacts` / `read` / `options_profit_status` while preserving backend timing headers

### Predictions

- `GET /api/predictions`
  - passive generic read; response lifecycle headers identify `predictions_json` / `read` / `prediction_history`
- `POST /api/predictions/grade`
  - requires local operator auth
  - response lifecycle headers identify `predictions_json` / `prediction_grade` / `prediction_history`

FastAPI also exposes `DELETE /api/predictions/{pred_id}`, but there is no matching Next route handler in this worktree.

### Operator Auth

- `GET /api/operator/session`
  - Next-only local operator session status
  - response lifecycle headers identify `local_operator_session_cookie` / `session_status` / `operator_session`
- `POST /api/operator/session`
  - Next-only local operator unlock; accepts the server-only `OPTIONS_LOCAL_OPERATOR_TOKEN` in the request body and sets an HttpOnly SameSite=Strict session cookie
  - response lifecycle headers identify `local_operator_session_cookie` / `session_unlock` / `operator_session`

### Tracked Positions

- `GET /api/positions`
- `POST /api/positions`
- `POST /api/positions/review`
- `POST /api/positions/{id}/close`

Store ownership:
- route contracts live in `src/lib/trading-desk/storeOwnership.ts`
- repository interfaces live in `python-backend/repository_contracts.py` and are explained in `docs/repository-contract.md`
- tracked/suggested route and row-shape parity lives in `python-backend/repository_parity.py` and is explained in `docs/trading-desk-record-parity.md`
- mutation body adapters live in `python-backend/trading_desk_api_models.py` and are explained in `docs/trading-desk-api-models.md`; handlers keep `dict[str, Any]` bodies and route-owned `400` validation
- TypeScript request/response envelopes and shallow response-envelope validation live in `src/lib/trading-desk/apiContracts.ts` and `src/lib/trading-desk/apiResponseValidation.ts`; this is a manual Trading Desk boundary, not generated OpenAPI or JSON Schema
- the generated schema bridge lives in `data/contracts/trading-desk-api-schema-bridge.json` and `docs/trading-desk-schema-bridge.md`; it cross-checks manual TypeScript names with narrow Pydantic adapter schemas and has `runtime_use=false`
- frontend proof display constants come from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts`, keeping UI evidence groups aligned with `data/contracts/proof-evidence-contract.json`
- repository schema migrations live in `python-backend/repository_migrations.py` and are explained in `docs/repository-migrations.md`
- repository constraints live in `python-backend/repository_constraints.py` and are explained in `docs/repository-constraints.md`
- repository indexes live in `python-backend/repository_indexes.py` and are explained in `docs/repository-indexes.md`
- responses carry `x-trading-desk-store: postgres_tracked_positions`
- responses carry `x-trading-desk-record-class: tracked_position`
- lifecycle is exposed through `x-trading-desk-lifecycle`
- mutation routes also require the matching `x-trading-desk-mutation` intent header
- mutation routes require local operator auth before the intent header is checked
- live-scan proof classification requires exact contract identity, executable scan entry evidence, and source scan lineage verified against the forward-evidence ledger; verification checks the recorded event's contract identity and execution fields, and exact-looking payloads with missing, fabricated, or price-mutated scan provenance remain proof-ineligible
- scanner-origin creates follow `docs/scanner-creation-safety-contract.md`: source and current rerun picks must both have verified lineage, caps-enforced creation state, `creation_eligible=true`, no `creation_blockers`, and final proof eligibility
- scanner-origin create tamper rejection is covered by tracked and suggested route-level lineage mutation tests, with a full scan-to-create smoke test in `tests/test_options_api_e2e.py`
- tracked-position create/review/close responses include `position_event_persistence`; `status=failed` means the primary row mutation succeeded but the forward-evidence lifecycle event did not persist and is visible in `/api/backtest/forward-evidence` recording health

### Suggested Trades

- `GET /api/suggested-trades`
- `POST /api/suggested-trades`
- `POST /api/suggested-trades/review`
- `POST /api/suggested-trades/{id}/close`

Store ownership:
- route contracts live in `src/lib/trading-desk/storeOwnership.ts`
- repository interfaces live in `python-backend/repository_contracts.py` and are explained in `docs/repository-contract.md`
- tracked/suggested route and row-shape parity lives in `python-backend/repository_parity.py` and is explained in `docs/trading-desk-record-parity.md`
- mutation body adapters live in `python-backend/trading_desk_api_models.py` and are explained in `docs/trading-desk-api-models.md`; handlers keep `dict[str, Any]` bodies and route-owned `400` validation
- TypeScript request/response envelopes and shallow response-envelope validation live in `src/lib/trading-desk/apiContracts.ts` and `src/lib/trading-desk/apiResponseValidation.ts`; this is a manual Trading Desk boundary, not generated OpenAPI or JSON Schema
- the generated schema bridge lives in `data/contracts/trading-desk-api-schema-bridge.json` and `docs/trading-desk-schema-bridge.md`; it cross-checks manual TypeScript names with narrow Pydantic adapter schemas and has `runtime_use=false`
- frontend proof display constants come from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts`, keeping UI evidence groups aligned with `data/contracts/proof-evidence-contract.json`
- repository schema migrations live in `python-backend/repository_migrations.py` and are explained in `docs/repository-migrations.md`
- repository constraints live in `python-backend/repository_constraints.py` and are explained in `docs/repository-constraints.md`
- repository indexes live in `python-backend/repository_indexes.py` and are explained in `docs/repository-indexes.md`
- responses carry `x-trading-desk-store: sqlite_suggested_trades`
- responses carry `x-trading-desk-record-class: suggested_trade`
- lifecycle is exposed through `x-trading-desk-lifecycle`
- mutation routes also require the matching `x-trading-desk-mutation` intent header
- mutation routes require local operator auth before the intent header is checked
- scanner-origin suggested trades use the same source/rerun creation-safety contract as tracked positions; explicit manual modes are the only non-scanner creation path
- suggested scanner-origin creates share the same archived-lineage mutation rejection tests as tracked creates, but remain local paper/hypothetical rows rather than production proof rows
- suggested trades are local paper/hypothetical workflow state; responses use `trade` / `trades`, must not include `position_event_persistence`, and must not feed production proof or options-profit truth

### Support

- `POST /api/tools/{name}`
  - requires local operator auth
- `GET /api/sectors`

## Snapshot Warning

The current worktree does not include active Next route handlers for `src/app/api/day-trading/*`. The directories exist only as empty scaffolding folders, so any older docs that describe those as current browser endpoints are stale for this snapshot.

## Backend-Only FastAPI Endpoints

These FastAPI routes are not currently mirrored through `src/app/api/*`:

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

`GET /api/proof-summary` reports tracked closed-row counts as both `raw_exact_contract_closed_count` and `proof_grade_exact_contract_closed_count`. The compatibility field `exact_contract_closed_count` follows proof-grade semantics from `docs/proof-evidence-contract.md` and excludes manual exact, research/backfill, historical paper, lifecycle-only, and stale `proof_eligible` rows that are not `proof_class=live_scan_exact_contract`.

The browser Strategy Lab route contract lives in `src/lib/strategy-lab/replayIntent.ts`. It intentionally covers the mounted Next routes only: replay artifact reads, explicit replay runs, and explicit strategy profile saves. Backend-only backtest support endpoints remain direct FastAPI research/support surfaces and should not be treated as browser UX entrypoints until a matching Next route and Strategy Lab contract are added.

## Storage Layers

### SQLite

Primary file:
- `chat_history.db`

Used for:
- suggested trades
- local workflow state

Schema evolution:
- Trading Desk repository migrations are versioned in `python-backend/repository_migrations.py` and documented in `docs/repository-migrations.md`.
- Local SQLite hardening is documented in `docs/local-db-hardening.md` and represented by `python-backend/local_db_hardening.py`; `scripts/audit_local_databases.py --json` opens existing DBs read-only and must not repair, vacuum, delete, or initialize schema.
- `sqlite_suggested_trades` is the browser/local paper-idea store.
- `sqlite_tracked_positions_test_legacy` is explicit test/legacy storage only and must not become a silent browser fallback.
- Constraint ownership is documented in `docs/repository-constraints.md` and represented by `python-backend/repository_constraints.py`; suggested-trade review foreign keys are DB-enforced because the repository enables `PRAGMA foreign_keys=ON`, while SQLite table-level `CHECK` constraints remain deferred until a table-rebuild migration is approved.
- Index ownership is documented in `docs/repository-indexes.md` and represented by `python-backend/repository_indexes.py`; current SQLite suggested-trade indexes support status filters, list ordering, and latest-review lookup, while composite page indexes remain deferred candidates.

### Postgres

Configured by:
- `DATABASE_URL`
- `compose.yaml`

Used for:
- tracked positions
- tracked-position reviews

Schema evolution:
- `postgres_tracked_positions` migrations are versioned in `python-backend/repository_migrations.py` and documented in `docs/repository-migrations.md`.
- Missing or failing `DATABASE_URL` fails closed through the unavailable sentinel; it does not migrate or fall back to SQLite.
- Constraint ownership is documented in `docs/repository-constraints.md` and represented by `python-backend/repository_constraints.py`; broad Postgres `CHECK ... NOT VALID` constraints are deferred until the read-only audit proves existing rows are clean or intentionally exempt.
- Index ownership is documented in `docs/repository-indexes.md` and represented by `python-backend/repository_indexes.py`; current Postgres tracked-position indexes support status filters, chronological list ordering, and latest-review lookup, while composite and closed-at indexes remain deferred candidates.

### JSON And Artifact Files

Common files:
- `predictions.json`
- `wfo_results.json`
- `strategy_profile.json`
- `brain_changelog.json`

Artifact directories:
- `data/options-validation/*`
- `data/options-profit/*`
- `data/forward-tracking/*`
- `data/ai-commodity-infra/*`
- `data/alpaca-options-strategy-lab/*`
- `docs/autoresearch/*`

Used for:
- replay outputs
- imported options truth storage
- canonical and archive forward evidence
- policy artifacts
- truth-gate state
- forward evidence
- pending selected-candidate validation dispositions
- current-policy entry-filter point-in-time replay readbacks
- AI commodity OPRA capture progress and lane proof-readiness evidence
- research-only exact bid/ask lab output
- research proposals and snapshots

### Market Data Cache

Primary file:
- `market_data.db`

Used for:
- market data caching and historical support workflows

## Ownership Map

- Next route handlers
  - request validation and same-origin proxying only
- `src/lib/trading-desk/storeOwnership.ts`
  - executable Trading Desk route-to-store lifecycle contract for tracked positions and suggested trades
- `src/lib/python-bridge.ts`
  - compatibility barrel for the backend client modules
- `src/lib/backend/*`
  - backend HTTP transport plus domain-specific request helpers
- `python-backend/main.py`
  - FastAPI app composition, router mounting, and cache orchestration
- `docs/backend-route-ownership-map.md`
  - generated route adapter ownership map for FastAPI handlers, extracted routers, service delegation, and backend-only surfaces
- `python-backend/backend_route_context.py`
  - late-bound router context so extracted handlers see the currently loaded backend module globals
- `python-backend/repository_contracts.py`
  - structural Protocols for tracked-position, suggested-trade, shared review-shaped, and optional repository capabilities
- `python-backend/local_db_hardening.py`
  - local SQLite role manifest and read-only hardening/audit ownership
- `python-backend/profile_routes.py`
  - profile, profile changelog, `/api/profiles`, and risk settings routes
- `python-backend/predictions_routes.py`
  - prediction history, grading, and backend-only prediction delete routes
- `python-backend/tools_routes.py`
  - generic tool dispatch route
- `python-backend/proof_summary_service.py`
  - decorator-free `/api/proof-summary` workflow assembly; reads late-bound gate, claim-readiness, forward-evidence, and tracked-position count dependencies
- `python-backend/replay_profit_service.py`
  - decorator-free replay/profit readback assembly for cached backtest reports, metric truth, forensics, stability, live policy, exit audit, comparison, and summary
- `options_chatbot.py`
  - options scan and profile-era domain logic
- `wfo_optimizer.py`
  - replay and policy generation
- `scripts/run_ai_commodity_opra_progress.py`
  - AI commodity OPRA proof-lane orchestration and generated readbacks
- repository modules
  - tracked positions and suggested-trade persistence

## Fast Reading Order

1. `src/components/layout/AppShell.tsx`
2. `src/lib/python-bridge.ts`
3. `src/lib/backend/*`
4. `src/app/api/scan/route.ts`
5. `python-backend/main.py`
6. `python-backend/backend_route_context.py`
7. `python-backend/repository_contracts.py`
8. `python-backend/profile_routes.py`
9. `python-backend/predictions_routes.py`
10. `python-backend/tools_routes.py`
11. `python-backend/proof_summary_service.py`
12. `python-backend/replay_profit_service.py`
13. `python-backend/positions_service.py`
14. `python-backend/positions_repository.py`
15. `options_chatbot.py`
16. `wfo_optimizer.py`
