# Docs Index

## Start Here

These are the living docs for the current worktree:

- `AGENTS.md`
  - repo-specific agent startup, evidence rules, and documentation placement
- `README.md`
  - top-level product and runtime summary
- `docs/architecture-overview.md`
  - system map, subsystem ownership, and reading order
- `docs/architecture-best-practices.md`
  - target architecture/readability rubric for future remediation loops
- `docs/remediation-loop-map.md`
  - generated 44-point remediation handoff ledger for loop status, owner artifacts, planned points, and verification anchors
- `data/contracts/remediation-loop-map.json`
  - generated machine-readable remediation loop map
- `docs/final-remediation-closure-pack.md`
  - generated final readback proving all 44 remediation points are complete, checked, discoverable, and within active scope
- `data/contracts/final-remediation-closure-pack.json`
  - generated machine-readable final remediation closure pack
- `docs/legacy-lane-boundaries.md`
  - generated active/separate/legacy/paused lane boundary map for regular options, AI commodity, day-trading, crypto options, and Polymarket
- `data/contracts/legacy-lane-boundaries.json`
  - generated machine-readable lane-boundary contract and guard results
- `docs/ai-commodity-isolation.md`
  - generated AI commodity non-browser proof-lane isolation map for scanner, proof-source, route, tool, and storage boundaries
- `data/contracts/ai-commodity-isolation.json`
  - generated machine-readable AI commodity isolation contract and guard results
- `docs/living-docs-hygiene.md`
  - living docs ownership, generated-artifact, and source-of-truth hygiene rules
- `docs/agent-memory-graph.md`
  - generated where-to-go graph for owner docs, code, contracts, and generated artifacts
- `data/contracts/agent-memory-graph.json`
  - generated machine-readable owner/navigation graph
- `docs/generated-artifact-governance.md`
  - generated trust-boundary and stale-handling inventory for checked generated artifacts
- `data/contracts/generated-artifact-governance.json`
  - generated machine-readable generated-artifact governance map
- `docs/api-and-storage.md`
  - active route groups, backend-only endpoints, and storage ownership
- `docs/route-parity.md`
  - generated browser route to Next route to FastAPI mapping, plus route auth/mutation inventory
- `data/contracts/route-mutation-inventory.json`
  - generated machine-readable route auth/mutation, lifecycle, store, backend-only, and client-fetch inventory
- `docs/backend-route-ownership-map.md`
  - generated FastAPI adapter ownership, router extraction, service delegation, and backend-only surface map
- `data/contracts/backend-route-ownership-map.json`
  - generated machine-readable backend route ownership map
- `docs/storage-ownership-map.md`
  - generated route, repository, local DB, artifact, and virtual storage ownership map
- `data/contracts/storage-ownership-map.json`
  - generated machine-readable storage ownership map for route/store/readability checks
- `docs/route-lifecycle-contracts.md`
  - canonical descriptive lifecycle headers for mounted generic Next route groups, implemented by `src/lib/route-lifecycle/routeContracts.ts`
- `docs/proof-evidence-contract.md`
  - canonical Trading Desk proof/evidence definitions and implementation anchors, including generated frontend policy artifact ownership
- `data/contracts/proof-invariant-cases.json`
  - test-only proof invariant matrix consumed by backend and frontend proof regression tests
- `docs/proof-invariant-table.md`
  - generated human-readable proof invariant table for raw exact, production proof, Truth-grade, and realized-P&L boundaries
- `data/contracts/proof-replay-golden-readbacks.json`
  - test-only golden aggregate readbacks for proof-summary, options-profit metrics, grouped tracked/proof summaries, and replay-service assembly
- `docs/scanner-creation-safety-contract.md`
  - canonical scanner pipeline stage map, scanner-origin creation, scheduled auto-track, and pending-validation safety rules
- `docs/replay-profit-contract.md`
  - canonical replay/profit ownership map for replay readbacks, scanner policy, proof/profit gates, and options-profit status
- `docs/repository-contract.md`
  - canonical Trading Desk repository ownership map and structural repository interface contract
- `docs/trading-desk-record-parity.md`
  - canonical tracked-position versus suggested-trade parity and separation contract, implemented by `python-backend/repository_parity.py`
- `docs/trading-desk-api-models.md`
  - canonical narrow Pydantic model boundary for Trading Desk mutation bodies and top-level envelopes, implemented by `python-backend/trading_desk_api_models.py`
- `docs/typescript-api-contracts.md`
  - canonical narrow TypeScript API contract and runtime response-envelope validation boundary for Trading Desk request/response envelopes, implemented by `src/lib/trading-desk/apiContracts.ts` and `src/lib/trading-desk/apiResponseValidation.ts`
- `docs/trading-desk-schema-bridge.md`
  - generated documentation/check bridge mapping Trading Desk route contracts, manual TypeScript names, and narrow Pydantic adapter JSON Schemas
- `data/contracts/trading-desk-api-schema-bridge.json`
  - generated machine-readable Trading Desk schema bridge
- `src/lib/generated/proofEvidenceContract.ts`
  - generated frontend proof/evidence policy artifact
- `docs/local-db-hardening.md`
  - canonical local SQLite DB safety and read-only audit contract, implemented by `python-backend/local_db_hardening.py`
- `docs/repository-migrations.md`
  - canonical Trading Desk repository migration manifest and ledger contract, implemented by `python-backend/repository_migrations.py`
- `docs/repository-constraints.md`
  - canonical Trading Desk repository constraint ownership map, implemented by `python-backend/repository_constraints.py`
- `docs/repository-indexes.md`
  - canonical Trading Desk repository index ownership map, implemented by `python-backend/repository_indexes.py`
- `docs/architecture-audit.md`
  - live audit of dead surfaces, sidecars, and remaining monoliths
- `docs/current-state.md`
  - current options product state
- `docs/day-trading-current-state.md`
  - current day-trading and crypto sidecar snapshot, with archive warnings
- `docs/PROJECT_CONTEXT.md`
  - active work scope and lane boundaries
- `docs/NEXT_STEPS.md`
  - current time-gated commands and guardrails
- `docs/lane-lab-lanes.md`
  - lane registry, pass bars, and AI commodity lane placement
- `docs/bullish-pullback-ticker-audit-2026-05-29.md`
  - current per-ticker keep/move/research/remove decisions for the 59-symbol bullish-pullback universe
- `docs/main-lane-negative-trade-audit-2026-05-31.md`
  - legacy single-lane Bullish Pullback negative-trade audit, with research/backfill versus live-exact separation and guardrail recommendations
- `docs/main-product-lane-negative-trade-audit-2026-05-31.md`
  - broader Trading Desk tracked-position negative audit across all regular supervised product-lane playbooks
- `docs/main-product-lane-quality-system-2026-05-31.md`
  - repair backlog and guardrail taxonomy derived from the all-lanes negative-trade audit
- `docs/trading-desk-profitability-guardrails-2026-05-31.md`
  - all-row replay of Trading Desk profitability guardrails promoted into scanner entry-quality rules
- `docs/current-policy-historical-picks-audit.md`
  - current-policy replay of historical closed Trading Desk rows, separating would-take-today rows from learned-away backfill
- `docs/current-policy-cohort-health.md`
  - current-policy cohort health report separating the April showcase edge from the broken recent paper-only cohort
- `docs/current-policy-historical-stop-grid.md`
  - current-policy exact-contract daily close-check stop grid, plus annual replay-backed exact cohort coverage, separating stop-policy candidates from entry-filter problems
- `docs/current-policy-entry-filter-lab.md`
  - current-policy entry-filter lab for avoiding deep loss cohorts without changing live scanner guardrails
- `docs/current-policy-entry-filter-walkforward.md`
  - all-regular-lanes walk-forward validation for the frozen entry-filter candidate and broad fill-degradation rejection
- `docs/current-policy-entry-filter-paper-monitor.md`
  - forward paper monitor for the best entry-filter candidate and its fresh-sample promotion gates
- `docs/current-policy-entry-filter-point-in-time.md`
  - scanner candidate point-in-time replay for the short-term fill-degradation filter promotion gate
- `docs/trading-desk-negative-trade-decision-audit-2026-05-31.md`
  - reproducible negative-trade decision audit with entry rationale, guardrail coverage, evidence quality, and executable-exit separation
- `docs/trading-desk-exit-policy-replay-2026-05-31.md`
  - read-only executable-review replay of Trading Desk exit policy variants and legacy missed-close cases
- `docs/trading-desk-legacy-missed-close-audit-2026-06-01.md`
  - focused read-only audit of legacy rows 26/39/44 and whether they imply a current auto-close bug
- `docs/regular-options-operating-scorecard.md`
  - active options scorecard separating visible Trading Desk profitability progress, open/suggested close risk, starvation, API performance, proof-grade autoresearch readiness, and AI commodity OPRA proof status
- `docs/regular-options-profit-capture-queue.md`
  - generated research/paper capture queue that tiers profitable regular-options symbol/lane evidence, fresh scan signature matches, evidence-repair priorities, and quarantine/do-not-chase rows without changing scanner policy
- `docs/regular-options-repair-attempts.md`
  - generated exact-repair attempt memory/readback for regular-options replay gaps, including exact-date versus lookahead-only proof posture
- `docs/regular-options-symbol-sleeves.md`
  - generated per-symbol sleeve matrix for regular supervised options, separating lane-symbol keep/watch/quarantine/rejected/needs-paper status from proof evidence class
- `docs/regular-guardrail-starvation-audit.md`
  - latest regular-lane live-scan guardrail starvation audit and upstream zero-candidate readback
- `docs/markdown-audit-2026-05-31.md`
  - latest Markdown placement audit, scope, and verification evidence
- `docs/WORKLOG.md`
  - recent local evidence and documentation changes
- `docs/DECISIONS.md`
  - active governance decisions and lane scope
- `docs/runtime-request-flow.md`
  - narrative request-flow map, complementing generated route parity
- `docs/paid-options-data-import-checklist.md`
  - current paid-data import and proof-source checklist
- `docs/weekly-bug-audit-loop.md`
  - recurring six-agent bug audit runbook and automation prompt
- `docs/autoresearch/code-audit-remediation-goal.md`
  - reusable six-subagent goal prompt for code audit remediation and long-term fixes
- `docs/autoresearch/active-options-performance-goal.md`
  - reusable multi-lane goal prompt for improving Trading Desk runtime, profitability, live-scan, proof, AI commodity, and architecture performance
- `docs/agent-worktree-hygiene.md`
  - agent branch, push, untracked-file, and clean-worktree rules

## What To Treat As Historical

These files are still useful, but they are records rather than the source of truth for the current app shape:

- roadmap and audit records under `docs/archive/`
- `docs/autoresearch/*`
- `research_runs/*`
- generated progress files under `data/ai-commodity-infra/progress/*`

If a dated doc disagrees with the code or with the living docs above, trust the code first.

## Freshness Checklist

When routes, storage, proof-lane state, or active lane scope changes:

1. Run `npm run docs:route-parity`.
2. Update `docs/current-state.md`, `docs/NEXT_STEPS.md`, and `docs/PROJECT_CONTEXT.md` when proof-lane dates, blockers, or commands change.
3. Update `docs/WORKLOG.md` with the evidence source and date.
4. Run `npm run verify:docs` before handing off; it checks generated route parity, storage ownership, the Trading Desk schema bridge, the generated frontend proof/evidence artifact, the generated proof invariant table, lane-boundary and AI commodity isolation artifacts, the remediation loop map, the agent memory graph, generated artifact governance, the final remediation closure pack, and living-docs hygiene.

## Quick Orientation For A Senior Engineer

Read in this order:

1. `src/components/layout/AppShell.tsx`
2. `src/lib/navigation/tabs.ts`
3. `src/components/predictions/PredictionsView.tsx`
4. `src/components/predictions/tradingDeskTabs.ts`
5. `src/components/predictions/useTradingDeskCloseDialogs.ts`
6. `src/components/predictions/CloseTradeModal.tsx`
7. `src/components/predictions/TrackedPositionsTab.tsx`
8. `src/components/predictions/TrackedStocksTab.tsx`
9. `src/components/predictions/ScannerTab.tsx`
10. `src/components/predictions/ScannerEvidencePanel.tsx`
11. `src/components/predictions/ScannerPickRecordForm.tsx`
12. `src/components/predictions/SuggestedTradesTab.tsx`
13. `src/components/predictions/trackedPositionUtils.tsx`
14. `src/components/predictions/tradingDeskCells.tsx`
15. `src/components/predictions/tradingDeskFormat.ts`
16. `src/components/ui/FinTable.tsx`
17. `src/components/strategy/StrategyView.tsx`
18. `src/lib/client-json.ts`
19. `src/lib/python-bridge.ts`
20. `src/lib/backend/*`
21. `python-backend/main.py`
22. `python-backend/backend_route_context.py`
23. `python-backend/profile_routes.py`
24. `python-backend/predictions_routes.py`
25. `python-backend/tools_routes.py`
26. `python-backend/proof_summary_service.py`
27. `python-backend/replay_profit_service.py`
28. `python-backend/repository_contracts.py`
29. `python-backend/repository_parity.py`
30. `python-backend/trading_desk_api_models.py`
31. `src/lib/trading-desk/apiContracts.ts`
32. `src/lib/trading-desk/apiResponseValidation.ts`
33. `src/lib/generated/proofEvidenceContract.ts`
34. `src/lib/trading-desk/proofContract.ts`
35. `src/lib/trading-desk/positionEvidence.ts`
36. `scripts/generate_trading_desk_schema_bridge.py`
37. `scripts/generate_proof_evidence_contract.py`
38. `scripts/generate_storage_ownership_map.py`
39. `src/lib/route-lifecycle/routeContracts.ts`
40. `python-backend/local_db_hardening.py`
41. `python-backend/repository_migrations.py`
42. `python-backend/repository_constraints.py`
43. `python-backend/repository_indexes.py`
44. `options_chatbot.py`
45. `wfo_optimizer.py`

## Snapshot Warnings

- `src/app/page.tsx` is intentionally a stub; the real browser entrypoint is the layout plus app shell.
- `src/app/api/day-trading/*` exists only as empty scaffolding folders in this worktree.
- `src/lib/polymarket/*` and `crypto_options/*` are sidecar lanes, not the mounted browser product.
- `data/ai-commodity-infra/progress/latest.md` is generated lane evidence. Read it for the latest AI commodity proof state, but update the living docs manually when the project state changes.
