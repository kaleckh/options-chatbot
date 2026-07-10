# Docs Index

This index is the concise documentation source of truth and navigation layer. Current behavior belongs to code, contracts, and living owner docs. Dated reports, generated artifacts, archives, and other evidence records retain provenance but do not override their owners.

## Start Here

- `README.md` — product and setup overview
- `AGENTS.md` — repository workflow, proof, and safety rules
- `docs/PROJECT_CONTEXT.md` — concise product, architecture, memory, and storage context
- `docs/DECISIONS.md` — current durable decisions
- `docs/NEXT_STEPS.md` — prioritized active work and blockers
- `docs/WORKLOG.md` — concise dated handoff
- `docs/living-docs-hygiene.md` — source-of-truth, evidence-record, and generated-artifact rules
- `docs/architecture-overview.md` — current architecture
- `docs/architecture-best-practices.md` — target architecture and readability bar
- `docs/architecture-audit.md` — architecture audit record

## Operations And Safety Owners

- `docs/project-operating-map.md` and `data/contracts/project-pathway-registry.json` — pathway navigation
- `docs/project-operator-gateboard.md` and `data/forward-tracking/project_operator_gateboard_latest.json` — current fail-closed status
- `docs/agent-control-plane.md` — canonical schema-v5 CEO/worker workflow, strict restore/outbox/session/retrieval/dream integrity, stable living-history classes, coherent gateboard provenance, and implementation-authority versus action-gate boundary
- `docs/memory-graph-v5-upgrade-audit-2026-07-10.md` — dated schema-v5 hardening, final live ingest/doctor/recovery verification, scheduler proof, and remaining nonblocking scale debt
- `docs/autoresearch/memory-graph-dreaming-goal.md` — reusable global/local memory-graph assurance prompt
- `C:\Users\kalec\projects-memory\MEMORY_GRAPH.md` and `C:\Users\kalec\projects-memory\audits\memory-graph-v2-upgrade-2026-07-09.md` — curated computer-wide pointer/provenance contract and dated v2 verification; neither overrides repo authority
- `docs/evidence-operations.md` — authoritative evidence hosts, backup, and daily operations
- `docs/api-and-storage.md` — API/storage ownership
- `docs/runtime-request-flow.md` — frontend/backend request boundaries
- `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py` — local database roles and read-only hardening audit
- `docs/trading-desk-api-models.md` and `python-backend/trading_desk_api_models.py` — narrow mutation request-model ownership
- `docs/trading-desk-record-parity.md` and `python-backend/repository_parity.py` — tracked/suggested row-shape parity without semantic merging
- `docs/proof-evidence-contract.md` — proof and evidence classes
- `docs/scanner-creation-safety-contract.md` — scanner-origin creation gates
- `docs/candidate-lifecycle-contract.md` — shared candidate lifecycle
- `docs/replay-profit-contract.md` — replay/profitability semantics
- `docs/regular-options-parked-branch-ledger.md` — consolidated parked/falsified branches
- `docs/ai-commodity-isolation.md` — separate AI commodity proof lane
- `docs/forward-holdout-contract.md` and `docs/forward-cohort-preregistration.md` — prospective proof boundaries

## Generated Artifacts

Generated files are evidence/navigation records. Run their owner commands; do not hand-edit them.

- `docs/route-parity.md`
- `data/contracts/route-mutation-inventory.json`
- `docs/backend-route-ownership-map.md`
- `data/contracts/backend-route-ownership-map.json`
- `docs/storage-ownership-map.md`
- `data/contracts/storage-ownership-map.json`
- `docs/trading-desk-schema-bridge.md`
- `data/contracts/trading-desk-api-schema-bridge.json`
- `src/lib/generated/proofEvidenceContract.ts`
- `data/contracts/candidate-lifecycle-contract.json`
- `docs/candidate-lifecycle-contract.md`
- `src/lib/generated/candidateLifecycleContract.ts`
- `docs/proof-invariant-table.md`
- `docs/legacy-lane-boundaries.md`
- `data/contracts/legacy-lane-boundaries.json`
- `docs/ai-commodity-isolation.md`
- `data/contracts/ai-commodity-isolation.json`
- `docs/remediation-loop-map.md`
- `data/contracts/remediation-loop-map.json`
- `docs/project-operating-map.md`
- `data/contracts/project-pathway-registry.json`
- `docs/agent-memory-graph.md`
- `data/contracts/agent-memory-graph.json`
- `docs/generated-artifact-governance.md`
- `data/contracts/generated-artifact-governance.json`
- `docs/final-remediation-closure-pack.md`
- `data/contracts/final-remediation-closure-pack.json`
- `docs/forward-holdout-contract.md`
- `data/contracts/forward-holdout-contract.json`
- `docs/forward-cohort-preregistration.md`
- `data/contracts/forward-cohort-preregistration.json`

## Historical And Generated Records

- The verified project-memory archive preserves the complete pre-compaction PROJECT_CONTEXT, DECISIONS, WORKLOG, NEXT_STEPS, and index files. Archive-aware living-history ingestion exposes historical WORKLOG/DECISIONS without generic repo-index duplication.
- Dated research and audit reports are evidence records at their declared class. Prefer their current `latest` readback and owner contract.
- Parked branch details live behind the consolidated parked-branch ledger; do not make every archived branch a startup dependency.
- Runtime memory, worker reports, dreams, dashboards, browser results, and generated summaries are retrieval or observability context. They do not grant trading, evidence-mutation, broker, proof, or release authority.

## Hygiene Rules

1. Add a document here only when it changes onboarding, ownership, or the current decision surface.
2. Put implementation truth in code/contracts and operator truth in the relevant owner doc.
3. Put dated detail in evidence records or immutable archives, not repeatedly in startup memory.
4. Keep generated files reproducible and covered by `npm run verify:docs`.
5. Preserve the fail-closed distinction between research, historical evidence, forward proof, and live authority.

## Verification

```powershell
npm run verify:docs
npm run verify:agent-control
npm run verify:memory
```

## Non-Goals

- This index does not define runtime behavior, proof predicates, scanner policy, database schema, broker permissions, or release status.
- It does not promote historical or generated records over current owners.
- It does not replace the gateboard, contracts, tests, or authoritative evidence stores.
