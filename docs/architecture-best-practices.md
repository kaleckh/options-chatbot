# Architecture Best Practices

## Purpose

This doc defines the target architecture bar for future remediation loops. It is written for LLM agents and senior engineers who need to decide whether a change makes the codebase easier to read, safer to modify, and clearer to verify.

This is not the current system map. Use `docs/architecture-overview.md` for the current map and `docs/architecture-audit.md` for the current risk snapshot. This doc is the rubric: what good looks like when a point is claimed complete.

When checking the completed 44-point remediation goal, start with `docs/final-remediation-closure-pack.md`, then use `docs/remediation-loop-map.md` after this rubric to recover per-point status, owner artifacts, and verification anchors without relying on chat context.

## Active Scope

The active browser product is the regular supervised options lane family:

- live scan
- replay diagnostics
- suggested trades
- tracked-position review

AI commodity / commodity-infrastructure options is a separate non-browser proof-first strategy lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`.

Crypto options, Polymarket, and day-trading lanes are out of scope unless the user explicitly asks to archive, remove, repair, or reopen them.

## Architecture Principles

- One concern should have one obvious owner doc and one obvious code owner where practical.
- App-shell and client components should orchestrate workflows, not redefine route, proof, scanner, or storage semantics.
- Next route handlers should stay thin: local auth, mutation-intent checks, shallow response contract checks where owned, and backend proxying.
- FastAPI route handlers should compose services, repositories, and domain modules. They should not become new proof, scanner, replay, or persistence engines.
- Application services should be decorator-free workflow builders between routes and domain modules.
- Domain modules own domain semantics. Repositories own persistence mechanics. Generated artifacts own drift checks only when they explicitly say they are generated and checked.
- Contracts, manifests, and typed identifiers are preferred over implicit string conventions when behavior must stay stable across files.

## Boundary Acceptance Bars

| Category | Target bar | Primary owners |
| --- | --- | --- |
| Runtime request flow | Browser, Next, backend helper, FastAPI, service/domain, and repository ownership are readable without guessing. | `docs/architecture-overview.md`, `docs/runtime-request-flow.md`, `docs/route-parity.md`, `docs/backend-route-ownership-map.md` |
| Read Versus Mutate | Read routes and state-changing routes have explicit auth, intent, lifecycle, and store signals where applicable. | `docs/api-and-storage.md`, `docs/route-lifecycle-contracts.md`, `src/lib/trading-desk/storeOwnership.ts`, `src/lib/strategy-lab/replayIntent.ts` |
| Auth and mutation intent | Local operator auth and backend bridge auth remain separate. Mutation-intent headers prove caller intent, not authorization. | `src/lib/operator-auth.ts`, `src/lib/backend/transport.ts`, `docs/api-and-storage.md` |
| API contracts | Request and response shapes have named contracts at the narrowest useful boundary. Runtime validation is explicit and scoped. | `docs/typescript-api-contracts.md`, `docs/trading-desk-api-models.md`, `docs/trading-desk-schema-bridge.md` |
| Proof and evidence | Proof semantics stay stricter than UI claims. Frontend groups are display wrappers around versioned proof classes and predicates. | `docs/proof-evidence-contract.md`, `data/contracts/proof-evidence-contract.json`, `python-backend/proof_contract.py` |
| Scanner creation | Visibility, candidate selection, and row creation remain separate. Scanner-origin creates require verified lineage and creation eligibility. | `docs/scanner-creation-safety-contract.md`, `data/contracts/scanner-creation-safety-contract.json` |
| Replay and profit | Replay readbacks, scanner policy, proof predicates, and profit-cycle state have separate owners and do not redefine one another. | `docs/replay-profit-contract.md`, `python-backend/replay_profit_service.py` |
| Repository and database | Tracked positions and suggested trades keep explicit store ownership. No silent fallback store or test repository should become production behavior. | `docs/storage-ownership-map.md`, `docs/repository-contract.md`, `docs/trading-desk-record-parity.md`, `docs/repository-migrations.md`, `docs/repository-constraints.md`, `docs/repository-indexes.md` |
| Frontend components | Large components split by workflow and verification boundary. Shared UI contracts stay explicit at call sites. | `src/components/predictions/*`, `src/components/strategy/*`, `src/components/ui/FinTable.tsx` |
| Generated artifacts | Generated artifacts name their source, command, runtime use, and check path. They are deterministic and checked before handoff. | `docs/generated-artifact-governance.md`, `docs/final-remediation-closure-pack.md`, `scripts/generated_artifact_manifest.py`, `scripts/generate_route_parity.py`, `scripts/generate_storage_ownership_map.py`, `scripts/generate_trading_desk_schema_bridge.py`, `scripts/generate_proof_evidence_contract.py`, `scripts/generate_agent_memory_graph.py` |
| Living docs | Current-state docs describe owned facts only. Worklog entries record dated evidence. Decisions record durable decisions, not daily work. | `docs/living-docs-hygiene.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`, `docs/NEXT_STEPS.md`, `docs/WORKLOG.md`, `docs/DECISIONS.md` |

## Readability Rules

- Read code before answering architecture questions.
- Prefer named request, response, store, lifecycle, route, tab, and proof identifiers over anonymous records and repeated strings.
- Split monoliths only when the split lowers cognitive load, reduces verification burden, or matches an established ownership boundary.
- Keep generated inventories and handwritten docs separate. Generated docs should not be paraphrased into a second stale table.
- Use `docs/remediation-loop-map.md` as the generated handoff ledger for the active 44-point loop, not as a replacement for owner docs, route/storage/proof inventories, or generated contract artifacts.
- Use `docs/agent-memory-graph.md` as generated orientation metadata for where to go first, not as a replacement for owner docs or generated inventories.
- Use `docs/backend-route-ownership-map.md` to locate FastAPI adapter ownership and service delegation before backend route edits; do not treat it as route behavior or OpenAPI schema.
- Use `docs/generated-artifact-governance.md` to decide whether a generated file is runtime-consumed, readability-only, a machine-readable check, or a stale output that must be regenerated.
- Use `docs/final-remediation-closure-pack.md` to prove the remediation loop is closed; do not treat it as runtime route, auth, DB, proof, scanner, replay, frontend, profitability, or broker-readiness policy.
- Keep human facades around generated artifacts when they improve import readability, but test that runtime consumers use the intended facade.
- Keep explicit non-goals in docs for points that deliberately avoid behavior changes.
- Avoid mega-registries that hide local ownership. Shared catalogs are useful only when they reduce real duplication and do not erase domain boundaries.

## Verification Expectations

- Run the smallest focused test that proves the changed boundary first.
- Add static or generated drift checks when the point creates a contract, registry, generated artifact, or docs ownership rule.
- Run broader suites only when the touched behavior warrants it.
- For browser UI behavior changes, include desktop and mobile QA when the change can affect layout, navigation, forms, or table rendering.
- For proof, scanner, replay, tracked-position, or data-lifecycle changes, include targeted Python tests and read-only artifact checks where possible.
- For docs-only target work, link the doc from the living reading order and add a focused docs test when the doc is a future-agent anchor.

## Docs Ownership

- `docs/index.md` owns the living reading order.
- `docs/living-docs-hygiene.md` owns living-doc ownership, generated-artifact, and source-of-truth hygiene rules.
- `docs/architecture-overview.md` owns the current architecture map.
- `docs/architecture-audit.md` owns the current architecture risks and remaining monoliths.
- `docs/architecture-best-practices.md` owns the target architecture rubric.
- `docs/PROJECT_CONTEXT.md` owns product scope, lane boundaries, architecture summary, and current proof posture.
- `docs/NEXT_STEPS.md` owns active blockers, commands, and next actions.
- `docs/WORKLOG.md` owns dated evidence of meaningful local work.
- `docs/DECISIONS.md` owns durable decisions only.

## Completion Checklist

Before a remediation point is claimed complete, answer:

1. Which owner doc and code owner now make the boundary easier to find?
2. Which behavior changed, and which important behaviors explicitly did not change?
3. Which auth, mutation, proof, scanner, replay, storage, or UI contract could have drifted?
4. Which focused test, generated check, or static guard pins that boundary?
5. Which living docs changed because their owned facts changed?
6. Which upcoming point is intentionally deferred instead of being half-implemented here?
7. Does `docs/remediation-loop-map.md` still record the point status, owner artifacts, verification anchors, and non-goals for future handoff?
8. When closing a whole remediation loop, does `docs/final-remediation-closure-pack.md` prove the loop map, generated governance, memory graph, living-doc links, and active-scope boundaries agree?

## Non-Goals

This doc does not replace generated route inventory, storage ownership maps, mutation inventory, the remediation loop map, memory graph artifacts, generated artifact governance, final closure pack, or proof/source contracts.

This doc does not authorize code refactors, schema changes, proof loosening, scanner threshold changes, route payload changes, auth changes, DB behavior changes, or sidecar-lane expansion by itself.
