# Code Audit Remediation Run - 2026-06-01

This run follows `docs/autoresearch/code-audit-remediation-goal.md`.

## Report Completeness Matrix

This matrix records the cross-section fields required by the goal prompt that are otherwise spread through each section narrative.

| Section | Primary files changed | Why the solution is long-term |
| --- | --- | --- |
| 1. Runtime architecture and request flow | `scripts/generate_route_parity.py`, `tests/test_route_parity_generator.py`, `docs/route-parity.md`, `docs/runtime-request-flow.md`, `docs/architecture-audit.md`, `docs/WORKLOG.md` | Converts the request-flow map into an executable verification gate that catches missing Next routes, missing FastAPI mirrors, and absolute browser API bypasses before future UI changes can land. |
| 2. Trading Desk UX monolith | `src/lib/trading-desk/positionEvidence.ts`, `src/components/predictions/PredictionsView.tsx`, `tests/trading-desk/position-evidence.test.js`, docs/run report | Moves proof, evidence, and P&L semantics into a pure tested module so later Trading Desk UI work can change layout without rewriting production-proof classification or outcome math. |
| 3. Read versus mutate semantics | `src/lib/trading-desk/mutationIntent.ts`, Trading Desk Next routes under `src/app/api/positions*` and `src/app/api/suggested-trades*`, `src/components/predictions/PredictionsView.tsx`, `tests/trading-desk/mutation-intent.test.js`, `package.json` | Adds explicit mutation-intent headers at route boundaries so passive polling and explicit user mutations are enforced by code rather than component convention. |
| 4. Data lifecycle and store ownership | `src/lib/trading-desk/storeOwnership.ts`, Trading Desk Next routes, `python-backend/positions_repository.py`, `tests/test_positions_repository_schema.py`, Trading Desk tests, `docs/api-and-storage.md`, `docs/architecture-overview.md` | Makes storage ownership observable at route boundaries and removes the writable SQLite fallback for tracked positions, preserving Postgres ownership as an invariant. |
| 5. Proof and evidence integrity | `python-backend/positions_service.py`, `python-backend/main.py`, `tests/test_positions_repository_schema.py`, `tests/test_tracked_positions_api.py`, Trading Desk evidence tests, run report | Adds backend proof guards that demote research/backfill/migration rows before exact-looking evidence can promote them, with grouped summaries hardened against stale proof flags. |
| 6. Live scan to position flow | `python-backend/main.py`, `python-backend/positions_service.py`, `src/lib/types.ts`, `tests/test_options_api_e2e.py`, `tests/test_tracked_positions_api.py`, docs | Requires tracked-position live-scan proof to verify the submitted pick against the recorded forward-evidence ledger, preventing forged or price-mutated lineage from becoming production proof. |
| 7. Replay, Strategy Lab, and research pipelines | `src/lib/strategy-lab/replayIntent.ts`, Strategy Lab Next routes under `src/app/api/backtest*`, `src/app/api/profile/route.ts`, `src/app/api/changelog/route.ts`, `src/components/strategy/StrategyView.tsx`, `tests/strategy-lab/replay-intent.test.js`, docs | Gives Strategy Lab read/write routes explicit lifecycle headers and mutation intents, making replay artifact reads, replay runs, profile reads, and profile saves distinct executable contracts. |
| 8. Monolithic Python files | `python-backend/profile_routes.py`, `python-backend/main.py`, `tests/test_backend_profile_routes.py`, `scripts/generate_route_parity.py`, `docs/route-parity.md`, architecture docs | Extracts profile/changelog/risk handlers into a bounded FastAPI router and teaches route parity about extracted routers, creating a repeatable migration path out of the backend monolith. |
| 9. Shared UI components and mobile UX | `src/components/ui/FinTable.tsx`, `src/app/globals.css`, `src/components/predictions/PredictionsView.tsx`, `src/components/strategy/BrainTab.tsx`, `src/components/strategy/OptimizerTab.tsx`, `tests/ui/fin-table.test.js`, `package.json`, docs | Replaces object-key-order mobile card inference with explicit per-table mobile hierarchy contracts, so dense future tables declare their mobile UX instead of inheriting brittle desktop ordering. |
| 10. Verification gaps | `tests/test_options_api_e2e.py`, `docs/WORKLOG.md`, run report | Repairs stale E2E fixtures to assert the current scanner guardrail contract, so broader verification protects default blocked-pick filtering instead of failing against outdated expectations. |

## Section 1 - Runtime Architecture And Request Flow

Status: addressed; six-reviewer gate passed.

Root cause: the repo had generated Next-to-FastAPI route parity, but the browser side of the runtime request path was still partly convention-based. The docs said active client components should only fetch mounted Next routes, yet `npm run verify:docs` did not inspect client fetch calls. A future component could fetch a backend-only or nonexistent `/api/*` path and the route-parity check would still pass.

Long-term implementation:

- Extended `scripts/generate_route_parity.py` with client fetch discovery for active source under `src/components`.
- Added normalization for query strings and template-literal dynamic segments, so calls such as `/api/profile?type=equity` and `/api/positions/${id}/close` are checked against mounted Next route patterns.
- Added validation errors for:
  - mirrored Next routes with no matching FastAPI decorator
  - active client-component `/api/*` fetches with no matching Next route
  - active client-component absolute `/api/*` fetches that would bypass the mounted Next route contract
- Regenerated `docs/route-parity.md` with a `Client Fetch Surface` section listing the active browser fetches and their source files.
- Updated `docs/runtime-request-flow.md` and `docs/architecture-audit.md` so the request-flow contract is described as executable verification, not only a diagram.
- Added `tests/test_route_parity_generator.py` for client fetch extraction and dynamic route matching.

Behavior changed:

- Intended: documentation verification now fails if the active browser app fetches a missing Next route.
- Intended: documentation verification now fails if a mirrored Next route has no corresponding FastAPI route decorator.
- Intended: route docs now show the browser fetch surface from active components alongside Next/FastAPI parity.
- No intended runtime behavior change to scan, replay, positions, suggested trades, proof/evidence classification, or P&L math.

Verification so far:

- `uv run --locked python -m unittest tests.test_route_parity_generator -v` passed (`2` tests).
- `npm run docs:route-parity` regenerated `docs/route-parity.md`.
- `npm run verify:docs` passed.
- After reviewer hardening, `uv run --locked python -m unittest tests.test_route_parity_generator -v` passed (`4` tests).
- After reviewer hardening, `uv run --locked python -m py_compile scripts/generate_route_parity.py tests/test_route_parity_generator.py` passed.
- After reviewer hardening, `npm run verify:docs` passed.

Six-reviewer gate:

- Architecture: `agree_addressed`.
- UX/workflow: `agree_addressed`; method-aware validation remains a minor future hardening item.
- Data lifecycle: `agree_with_minor_followups`; source scanning is intentionally scoped to active client components for this pass.
- Proof/evidence: `agree_with_minor_followups`; the absolute `/api/*` bypass concern was hardened before closing.
- Test/regression: `agree_with_minor_followups`; synthetic missing-route validation was added before closing.
- Maintainability: `agree_with_minor_followups`; method-aware validation and broader source scanning stay as minor future hardening if API calls move into hooks/libs.

Result: `6` / `6` reviewers agreed Section 1 is addressed. No blockers.

## Section 2 - Trading Desk UX monolith

Status: addressed with `6` of `6` reviewer agreement after reviewer-blocking proof fix.

Root cause: `src/components/predictions/PredictionsView.tsx` mixed table rendering, evidence/proof classification, executable exit trust, and options P&L math in one large component. That made product-facing layout work able to accidentally change proof semantics or headline P&L metrics.

Long-term implementation:

- Added `src/lib/trading-desk/positionEvidence.ts` as a pure Trading Desk evidence/outcome module.
- Moved evidence descriptors, production/research grouping, closed-data view matching, trusted exit detection, entry/mark/close/realized price selection, fee-aware P&L math, win-rate/average summaries, and truth-grade closed filtering out of `PredictionsView.tsx`.
- Updated `PredictionsView.tsx` to consume the module and keep rendering-specific helpers local.
- Tightened the default closed `truth_grade` path so only production-proof rows enter headline truth rows, truth win rate, and truth average P&L.
- Classified lifecycle-only, migrated historical paper, research backfill, comparable, and proof-ineligible rows before any `proof_eligible`/live promotion so stale flags cannot elevate research/backfill rows into production-proof counts.
- Added focused executable coverage in `tests/trading-desk/position-evidence.test.js` for live exact truth-grade inclusion, migrated/research exclusion from truth-grade, lifecycle/mark-exit exclusion, and fee-adjusted P&L.

Behavior changed:

- Intended: the closed Trading Desk default accuracy view now requires production-proof evidence, not merely executable research/backfill exits.
- Intended: evidence grouping uses stable ids in the descriptor, so display labels are no longer the semantic source of proof grouping.
- No intended mutation-path change. Passive polling remains read-only; review and close actions remain explicit button/modal flows.

Verification:

- `npm run verify:typecheck` passed.
- `npm run lint` passed.
- `node --test tests\trading-desk\position-evidence.test.js` passed (`5` tests).

Six-reviewer result:

- Architecture: `agree_with_minor_followups`.
- UX/workflow: `agree_with_minor_followups`.
- Data lifecycle: `agree_with_minor_followups`.
- Proof/evidence: initially `disagree_blocking`; blocker fixed by production-proof-only truth-grade filtering and classification priority tests; re-review returned `agree_addressed`.
- Test/regression: `agree_with_minor_followups`.
- Maintainability: `agree_with_minor_followups`.

Acceptance tally: `6` of `6` reviewers agree Section 2 is addressed. No P0/P1 blocker remains.

Minor followups retained:

- Add broader component/integration coverage for the closed Trading Desk default view and alternate closed-data filters.
- Rename table copy such as `Signal` to better separate lane/evidence metadata from current recommendation status.
- Continue extracting hooks and table subcomponents from `PredictionsView.tsx` after the proof/P&L boundary is stable.

## Section 3 - Read versus mutate semantics

Status: addressed with `6` of `6` reviewer agreement.

Root cause: Trading Desk passive reads and explicit mutations were mostly separated by component convention. The list/polling path used a boolean `showToast` flag that also implied review/reprice permission, and the create/review/close API routes accepted ordinary POSTs without an explicit caller-declared mutation intent.

Long-term implementation:

- Added `src/lib/trading-desk/mutationIntent.ts` with typed Trading Desk mutation intents and a shared `x-trading-desk-mutation` header helper.
- Added `requireTradingDeskMutationIntent` and enforced it before body parsing or Python bridge calls in all Trading Desk tracked-position and suggested-trade create/review/close routes.
- Updated `PredictionsView.tsx` so passive loads/polling call `fetchPositions()` and `fetchSuggestedTrades()` as read-only grouped GETs, while manual refresh passes `{ notify: true, review: "force" }`.
- Updated all explicit create/review/close component POSTs to use `tradingDeskMutationHeaders(...)`.
- Added `npm run trading-desk:test` and behavioral route tests for missing intent, wrong intent, and correct-intent bridge reachability.

Behavior changed:

- Intended: Trading Desk mutating routes now return `428` unless the request carries the exact expected `x-trading-desk-mutation` value.
- Intended: passive page load and background polling remain headerless reads and cannot accidentally reprice/review through the guarded routes.
- Intended: explicit user actions still create, review, and close rows because they supply the matching mutation intent.

Verification:

- `npm run trading-desk:test` passed (`10` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.

Six-reviewer result:

- Architecture: `agree_with_minor_followups`.
- UX/workflow: `agree_with_minor_followups`.
- Data lifecycle: `agree_with_minor_followups`.
- Proof/evidence: `agree_with_minor_followups`.
- Test/regression: `agree_with_minor_followups`.
- Maintainability: `agree_with_minor_followups`.

Acceptance tally: `6` of `6` reviewers agree Section 3 is addressed. No P0/P1 blocker remains.

Minor followups retained:

- Consider moving `requireTradingDeskMutationIntent` into a dedicated Trading Desk API guard module if generic API utilities continue to grow domain-specific rules.
- Add browser-level regression coverage for passive Trading Desk load/polling once the local browser test harness is stable.

## Section 4 - Data Lifecycle And Store Ownership

Status: addressed with `6` of `6` reviewer agreement after reviewer-blocking backend ownership fix.

Root cause: tracked positions, suggested paper ideas, generated research artifacts, and proof stores were documented as separate, but the active route layer did not expose an executable store/lifecycle contract. Worse, the backend tracked-position repository factory could silently fall back to a writable SQLite tracked-position store when `DATABASE_URL` was missing, contradicting the intended Postgres ownership model.

Long-term implementation:

- Added `src/lib/trading-desk/storeOwnership.ts` with typed Trading Desk route contracts for tracked-position and suggested-trade read/create/review/close lifecycles.
- Added `jsonWithTradingDeskStore` so Trading Desk position/suggestion route responses carry `x-trading-desk-store`, `x-trading-desk-lifecycle`, and `x-trading-desk-record-class`.
- Wired tracked-position routes to `postgres_tracked_positions` / `tracked_position`.
- Wired suggested-trade routes to `sqlite_suggested_trades` / `suggested_trade`.
- Updated `docs/api-and-storage.md` and `docs/architecture-overview.md` so the living storage map names the executable contract and response headers.
- Removed the implicit tracked-position SQLite fallback from `python-backend/positions_repository.py`; missing `DATABASE_URL` now fails closed through `UnavailableTrackedPositionsRepository`.
- Added Trading Desk route tests for ownership headers and a Python repository test for the missing-`DATABASE_URL` fail-closed invariant.

Behavior changed:

- Intended: tracked-position endpoints now advertise Postgres ownership at the route boundary.
- Intended: suggested-trade endpoints now advertise SQLite ownership at the route boundary.
- Intended: missing `DATABASE_URL` no longer creates or writes a local SQLite tracked-position store.
- No intended proof relaxation. Research/backfill and suggested paper ideas remain distinct from production-proof tracked-position metrics.

Verification:

- `npm run trading-desk:test` passed (`12` tests).
- `uv run --locked python -m unittest tests.test_positions_repository_schema -v` passed (`6` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.
- `npm run verify:docs` passed.

Six-reviewer result:

- Architecture: `agree_with_minor_followups`.
- UX/workflow: `agree_with_minor_followups`.
- Data lifecycle: initially `blocked` for the missing-`DATABASE_URL` SQLite tracked-position fallback; blocker fixed and re-review returned `agree_addressed`.
- Proof/evidence: `agree_with_minor_followups`.
- Test/regression: `agree_with_minor_followups`.
- Maintainability: `agree_with_minor_followups`.

Acceptance tally: `6` of `6` reviewers agree Section 4 is addressed. No P0/P1 blocker remains.

Minor followups retained:

- Add a parity check that every future Trading Desk route has exactly one matching route contract and response wrapper.
- Add browser-level or higher-level integration coverage for store/lifecycle headers once the local app harness is stable.
- Add explicit catalog coverage for generated research artifacts if the Section 5 proof/evidence work expands the same contract beyond Trading Desk position/suggestion routes.

## Section 5 - Proof And Evidence Integrity

Status: addressed with `6` of `6` reviewer agreement after proof-summary hardening.

Root cause: the UI proof/evidence layer already separated production proof from research/backfill rows, but backend position creation and grouped API summaries still had paths that could trust raw exact-looking fields or stale `proof_eligible` flags without first checking research/backfill and migration markers.

Long-term implementation:

- Added `_scan_pick_has_research_backfill_marker` in `python-backend/positions_service.py`.
- Updated `_classify_position_proof` so research/backfill, historical replay, migration, and historical chain-native markers force `proof_class=ineligible` with `research_backfill_not_live_proof` before live-exact or manual/broker proof classification can run.
- Added backend tests proving exact-looking research/backfill picks are not proof eligible and manual/broker exact classification cannot override research/backfill markers.
- Added `_row_counts_as_production_proof` in `python-backend/main.py` and changed grouped position summaries to exclude stale rows with research/backfill markers even if old stored data still says `proof_eligible=true`.
- Kept the TypeScript Trading Desk evidence module as defense in depth: migrated historical paper, research backfill, lifecycle-only, and untrusted mark exits remain excluded from truth-grade production summaries.

Behavior changed:

- Intended: research/backfill-marked scan picks persist as `proof_class=ineligible`, not `live_scan_exact_contract` or `manual_broker_exact_contract`.
- Intended: grouped API `summary.*.proof` counts are stricter than raw `proof_eligible` and exclude stale contaminated research/backfill rows.
- No intended P&L calculation change beyond preventing proof summaries from counting rows with contaminated provenance.

Verification:

- `uv run --locked python -m unittest tests.test_positions_repository_schema tests.test_tracked_positions_api -v` passed (`26` tests).
- `npm run trading-desk:test` passed (`12` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.

Six-reviewer result:

- Architecture: `agree_with_minor_followups`.
- UX/workflow: `agree_with_minor_followups`.
- Data lifecycle: `agree_with_minor_followups`.
- Proof/evidence: initially `agree_with_minor_followups`; after manual-exact precedence and grouped-summary hardening, re-review returned `agree_addressed`.
- Test/regression: `agree_with_minor_followups`.
- Maintainability: `agree_with_minor_followups`.

Acceptance tally: `6` of `6` reviewers agree Section 5 is addressed. No P0/P1 blocker remains.

Minor followups retained:

- Centralize the research/backfill marker taxonomy so Python creation-time proof classification and TypeScript UI evidence grouping cannot drift.
- Add table-style tests for every marker field/token recognized by the backend proof guard.
- Consider a clearer product term if `manual_exact` should be shown as executable learning evidence rather than production proof in future UI copy.

## Section 6 - Live Scan To Position Flow

Status: addressed with `6` of `6` reviewer agreement after the replacement proof/evidence hardening pass.

Root cause: `POST /api/scan` recorded forward-evidence sessions, but the returned picks did not carry the recorded session/run/event provenance back to the browser. A user could click `Take trade` from a legitimate live scan and create a tracked position whose `source_scan_*` fields were null. Separately, backend proof classification could still call an exact-looking payload `live_scan_exact_contract` without verifying scan-ledger lineage.

Long-term implementation:

- Added `_scan_pick_event_key` and `_annotate_scan_picks_with_forward_provenance` in `python-backend/main.py`.
- Added `_verify_source_scan_lineage` in `python-backend/main.py` so tracked-position creation verifies the submitted pick against the recorded forward-evidence event before proof classification.
- Hardened `_verify_source_scan_lineage` so the submitted pick must match the recorded event's contract identity and execution fields, including short-leg identity when present, quote timestamp, entry execution basis, and entry execution price.
- Extended `_record_forward_truth_for_scan` metadata with `forward_truth_run_id` and `forward_truth_recorded_at_utc`.
- Updated `/api/scan` so returned `picks` carry `source_scan_session_id`, `source_scan_event_key`, `source_scan_run_id`, and `source_scan_recorded_at_utc` when forward-evidence recording succeeds.
- Updated `python-backend/positions_service.py` so `live_scan_exact_contract` proof now requires source scan session, event key, run id, recorded timestamp, and verified forward-event lineage in addition to exact contract and executable entry evidence.
- Added `source_scan_*` fields to both `ScanPick` and top-level `TrackedPosition` TypeScript contracts.
- Updated `docs/api-and-storage.md`, `docs/architecture-overview.md`, and `docs/WORKLOG.md` with the new scan-to-position lineage contract.

Behavior changed:

- Intended: browser-created tracked positions from recorded live scan picks now preserve the exact forward-evidence session/event/run lineage.
- Intended: exact-looking positions without verified scan lineage remain proof-ineligible and cannot enter the live-scan proof class.
- Intended: reusing valid `source_scan_*` fields while mutating the submitted execution price no longer verifies as live-scan lineage.
- Intended: if forward-evidence recording fails, the scan can still return picks, but those picks will not be promoted as live-scan proof when tracked.
- Intended: recorded scan lineage can remove the lineage blocker while other proof gates, such as OPRA source and research/backfill markers, remain stricter than the UI flow.
- No intended P&L, review, or close-path behavior change.

Verification:

- `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_position_created_from_scan_pick_preserves_live_scan_provenance tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_mutated_scan_pick_entry_price_does_not_verify_live_scan_lineage tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_scan_endpoint_returns_sorted_normalized_contract tests.test_tracked_positions_api.TrackedPositionsApiTests.test_create_position_stores_scan_provenance tests.test_tracked_positions_api.TrackedPositionsApiTests.test_exact_looking_position_without_scan_provenance_is_not_live_scan_proof tests.test_tracked_positions_api.TrackedPositionsApiTests.test_verified_scan_lineage_is_required_for_live_scan_proof tests.test_tracked_positions_api.TrackedPositionsApiTests.test_research_backfill_marker_blocks_live_proof_even_with_exact_contract tests.test_tracked_positions_api.TrackedPositionsApiTests.test_research_backfill_marker_takes_precedence_over_manual_exact -v` passed (`8` tests).
- `npm run trading-desk:test` passed (`12` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.
- `npm run verify:docs` passed.
- Broader `uv run --locked python -m unittest tests.test_options_api_e2e tests.test_tracked_positions_api -v` still shows unrelated pre-existing/stale scan-count fixture failures in `test_scan_endpoint_defaults_to_bullish_pullback_primary`, `test_scan_backfills_after_blocked_top_pick`, and `test_fixture_replay_golden_snapshot_stays_stable`; the new scan-to-position provenance tests passed in that run and in focused reruns.

Six-reviewer result:

- Architecture: `agree_with_minor_followups`.
- UX/workflow: `agree_with_minor_followups`.
- Data lifecycle: `agree_addressed`.
- Proof/evidence replacement: `agree_addressed` after blocking on the weak execution-field comparison and confirming the hardening regression.
- Test/regression: `agree_addressed`.
- Maintainability: `agree_addressed`.

Acceptance tally: `6` of `6` reviewer seats returned agreement after the proof/evidence blocker was fixed. Section 6 is addressed.

Minor followups retained:

- Surface forward-evidence recording failures near scan picks or the take-trade flow so users know a row can be tracked but will not count as live-scan proof.
- Add a direct fixture proving the persisted forward-ledger event key and returned `source_scan_event_key` stay matched across future ledger changes.
- Extract scan lineage field names and the event-key convention into a shared helper or constant if they grow beyond the current two backend call sites.
- Resolve the stale broader E2E scan-count fixture failures in Section 10.

## Section 7 - Replay, Strategy Lab, And Research Pipelines

Status: addressed with `6` of `6` reviewer agreement after changelog lifecycle hardening.

Root cause: Strategy Lab mixed passive artifact reads with state-changing replay/profile writes behind ordinary `fetch` calls and thin Next proxies. A passive replay summary read, explicit replay run, profile read, and profile save all crossed the same browser/backend bridge without a durable route contract that named the store, lifecycle, record class, or required user intent. That made it too easy for future Strategy Lab work to blur UX reads with artifact/profile mutations.

Long-term implementation:

- Added `src/lib/strategy-lab/replayIntent.ts` as the Strategy Lab route contract catalog.
- Added `x-strategy-lab-store`, `x-strategy-lab-lifecycle`, and `x-strategy-lab-record-class` response headers for mounted replay/profile/changelog routes.
- Guarded `POST /api/backtest` with `x-strategy-lab-mutation: run_replay_backtest` before request body parsing or backend calls.
- Guarded `PUT /api/profile` with `x-strategy-lab-mutation: save_strategy_profile` before request body parsing or backend calls.
- Updated `StrategyView.tsx` so explicit replay runs and profile saves use typed Strategy Lab mutation headers.
- Marked passive Strategy Lab artifact/profile/changelog GET routes as reads in code and docs.
- Documented that backend-only backtest support endpoints remain FastAPI research/support surfaces until they receive matching Next routes and Strategy Lab contracts.

Behavior changed:

- Intended: background Strategy Lab artifact loads stay passive reads and expose lifecycle headers.
- Intended: replay runs cannot be triggered through the mounted Next route without an explicit replay mutation intent header.
- Intended: profile saves cannot be triggered through the mounted Next route without an explicit profile-save mutation intent header.
- Intended: backend-only research/support endpoints are not accidentally promoted to mounted browser UX routes by documentation wording.
- No intended change to replay math, proof gates, imported-truth rules, profile schema, or backend-only research runners.

Verification so far:

- `npm run strategy-lab:test` passed (`7` tests).
- `npm run trading-desk:test` passed (`12` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.
- `npm run verify:docs` passed.

Six-reviewer result:

- Architecture: `agree_addressed`.
- UX/workflow: `agree_addressed`.
- Data lifecycle: initially `blocked` because `/api/changelog` read profile changelog files but was outside the Strategy Lab route contract; blocker fixed and re-review returned `agree_addressed`.
- Proof/evidence: `agree_addressed`.
- Test/regression: `agree_with_minor_followups`.
- Maintainability: `agree_addressed`.

Acceptance tally: `6` of `6` reviewer seats returned agreement after the changelog read lifecycle gap was fixed. Section 7 is addressed.

Minor followups retained:

- Replace the component source-regex check with a behavioral fetch/mock test when the frontend harness is available.
- Ensure the untracked `src/lib/strategy-lab/` and `tests/strategy-lab/` files are included before publishing.

## Section 8 - Monolithic Python Files

Status: addressed with `6` of `6` reviewer agreement.

Root cause: `python-backend/main.py` still owned too many unrelated FastAPI concerns directly. Even small Strategy Lab/profile changes required editing the same composition file that also owns scan, replay, positions, suggested trades, proof summary, report caches, and support endpoints. That made the recommended "split main into routers by domain" a doc-only aspiration rather than an implemented migration path.

Long-term implementation:

- Added `python-backend/profile_routes.py` with `create_profile_router(...)`.
- Moved `GET /api/profile`, `GET /api/profiles`, `PUT /api/profile`, `GET /api/changelog`, and `GET /api/risk` out of `python-backend/main.py`.
- Mounted the profile router from `main.py`, preserving the same public FastAPI routes and the same strategy-profile/changelog backing stores.
- Added standalone router tests for profile reads, profile updates, invalid profile/update handling, risk settings, and changelog reads.
- Added an integration test proving `main.py` mounts the extracted profile router.
- Updated `scripts/generate_route_parity.py` so docs route parity discovers `@router.*` decorators in extracted FastAPI router modules, not only `@app.*` decorators in `main.py`.
- Updated living architecture docs so the router extraction is a real implemented seam and the remaining backend split backlog no longer lists profile routes as unstarted.

Behavior changed:

- Intended: no external API behavior change for profile, profiles, changelog, or risk routes.
- Intended: future profile/changelog/risk route changes now land in a bounded router module instead of the backend composition monolith.
- No intended change to replay math, live scan behavior, tracked-position persistence, proof/evidence classification, strategy profile schema, or profile save semantics.

Verification so far:

- `uv run --locked python -m unittest tests.test_backend_profile_routes -v` passed (`6` tests).
- `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_backtest_endpoint_accepts_empty_body_and_uses_defaults tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_options_profit_status_endpoint_returns_read_only_status_surface -v` passed (`2` tests).
- `uv run --locked python -m py_compile python-backend/main.py python-backend/profile_routes.py tests/test_backend_profile_routes.py` passed.
- `uv run --locked python -m py_compile scripts/generate_route_parity.py tests/test_backend_profile_routes.py` passed.
- `npm run docs:route-parity` regenerated `docs/route-parity.md`.
- `npm run verify:docs` passed.
- `npm run strategy-lab:test` passed (`7` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.

Six-reviewer result:

- Architecture: `agree_addressed`.
- UX/workflow: `agree_addressed`.
- Data lifecycle: `agree_addressed`.
- Proof/evidence: `agree_addressed`.
- Test/regression: `agree_addressed`.
- Maintainability: `agree_with_minor_followups`.

Acceptance tally: `6` of `6` reviewer seats returned agreement. Section 8 is addressed.

Minor followups retained:

- Add a backend-main integration assertion for `PUT /api/profile` if profile route behavior changes again.
- Before many more routers are split, generalize `scripts/generate_route_parity.py` beyond literal `@router.*` decorators on a variable named `router`, or document that router naming convention explicitly.

## Section 9 - Shared UI Components And Mobile UX

Status: addressed; six-reviewer gate passed.

Root cause: `FinTable` rendered mobile cards, but it inferred the card title/subtitle from raw object key order and rendered every non-action desktop column into mobile cards. That made the active scanner, tracked-position, paper-idea, Strategy Lab replay, and changelog tables vulnerable to mobile hierarchy regressions whenever desktop columns were reordered or expanded.

Long-term implementation:

- Extended `src/components/ui/FinTable.tsx` with an explicit mobile-card contract:
  - `mobileTitleCol`
  - `mobileSubtitleCol`
  - `mobilePriorityCols`
  - `mobileHiddenCols`
  - `mobileActionCol`
- Kept desktop table rendering unchanged while using the mobile contract only for the card layout below tablet width.
- Added CSS guards so mobile card header text wraps inside its container and action controls get stable responsive width.
- Applied mobile hierarchy props to the live scanner, tracked-position, paper-idea, Strategy Lab replay, and profile changelog tables.
- Added `tests/ui/fin-table.test.js` with React server-rendered coverage proving mobile title/subtitle/priority/hidden/action behavior.
- Added `npm run ui:test`.

Behavior changed:

- Intended: mobile cards now show the most useful decision/action fields first instead of inheriting arbitrary desktop column order.
- Intended: desktop tables keep their existing density and sticky columns.
- Intended: desktop-only provenance/detail columns can be omitted from mobile cards without being removed from desktop tables.
- No intended change to data fetching, proof/evidence classification, route behavior, P&L math, or replay output.

Verification so far:

- `npm run ui:test` passed (`1` test).
- `npm run strategy-lab:test` passed (`7` tests).
- `npm run verify:typecheck` passed.
- `npm run lint` passed.
- `npm run verify:docs` passed.
- Browser QA with `npm run dev` passed at mobile viewport `599x662`: the Trading Desk rendered mobile cards, the inspected tracked-position card used the explicit `Ticker` / `Live P&L` hierarchy, action buttons stayed inside the card, and DOM overflow checks found no overflowing children on the inspected card.

Six-reviewer gate:

- Architecture: `agree_addressed`.
- UX/mobile: `agree_addressed`.
- Data lifecycle/proof separation: `agree_addressed`.
- Test/regression: `agree_addressed`.
- Maintainability: `agree_addressed`.
- Product operator workflow: `agree_addressed`.

Result: `6` / `6` reviewers agreed Section 9 is addressed. No blockers.

## Section 10 - Verification Gaps

Status: addressed; six-reviewer gate passed.

Root cause: the broader options API E2E suite had drifted behind the current scanner guardrail contract. Three scan assertions still expected stale behavior: a default Bullish Pullback fixture used `SPY`, which is no longer in the profitability-repair keep set; a backfill fixture used `SPY`, which is quarantined for the Short-Term lane; and the golden replay snapshot expected blocked Short-Term scan candidates to be returned by default even though blocked guardrail picks are now hidden unless explicitly requested.

Long-term implementation:

- Updated `tests/test_options_api_e2e.py` so the default Bullish Pullback route fixture uses a current keep-list ticker (`IWM`) and still verifies the default playbook wiring, allowed direction, signal variant, and forced cohort fields.
- Updated the blocked-top-pick backfill fixture to use a non-quarantined replacement (`BBB`) while keeping the existing open-position setup that blocks the first candidate.
- Updated the golden replay snapshot to assert the current guardrail funnel contract: `2` raw candidates, `1` guardrail-filtered candidate, `1` returned pick, and guardrail counts of `1` clear / `1` blocked.
- Kept the blocked candidate excluded by default instead of loosening scanner behavior or adding `include_blocked_guardrail_picks` to make the old expectation pass.

Behavior changed:

- Intended: no production code behavior changed.
- Intended: the E2E suite now protects the current guardrail default: blocked scan candidates are not returned unless the caller explicitly asks for blocked guardrail picks.
- Intended: test fixtures now use lane-valid symbols for the behavior they are trying to verify, instead of relying on stale symbols that are correctly blocked by newer profitability guardrails.
- No intended change to proof/evidence classification, P&L math, route behavior, or scanner ranking.

Verification so far:

- `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_scan_endpoint_defaults_to_bullish_pullback_primary tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_scan_backfills_after_blocked_top_pick tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_fixture_replay_golden_snapshot_stays_stable -v` passed (`3` tests).
- `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests -v` passed (`38` tests).
- After the golden-funnel assertion hardening, `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_fixture_replay_golden_snapshot_stays_stable -v` passed (`1` test).
- After the golden-funnel assertion hardening, `uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests -v` passed (`38` tests).
- `npm run verify:docs` passed.
- `npm run verify:python:research` passed (`93` tests).
- `git diff --check` passed with line-ending warnings only.

Six-reviewer gate:

- Architecture: `agree_addressed`.
- UX/workflow: `agree_addressed`.
- Data lifecycle: `agree_addressed`.
- Proof/evidence: `agree_addressed`.
- Test/regression: `agree_addressed`.
- Maintainability: `agree_addressed`; minor suggestion to assert more of the funnel was implemented before closing the section.

Result: `6` / `6` reviewers agreed Section 10 is addressed. No blockers.
