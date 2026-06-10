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
- `docs/project-operating-map.md`
  - generated visual operating model for the project pathways: data, candidates, evidence, profitability, promotion, and operator action
- `data/contracts/project-pathway-registry.json`
  - generated machine-readable project pathway registry
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
- `docs/candidate-lifecycle-contract.md`
  - generated canonical pending-candidate status and validation-outcome contract for all-lanes queueing, paper-only routes, diagnostics, and fresh-evidence readbacks
- `data/contracts/candidate-lifecycle-contract.json`
  - generated machine-readable candidate lifecycle status/outcome contract
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
- `src/lib/generated/candidateLifecycleContract.ts`
  - generated frontend candidate lifecycle status/outcome artifact
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
- `docs/thetadata-terminal-runbook.md`
  - local ThetaTerminal v3 startup, readiness probe, and quote-import failure rules for regular supervised-options evidence loops
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
- `docs/current-policy-circuit-breaker.md`
  - generated recent-cohort paper-validation circuit breaker for `short_term` and Bullish Pullback pending candidates
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
  - active options scorecard separating visible Trading Desk profitability progress, paper-gate readiness, open/suggested close risk, starvation, API performance, proof-grade autoresearch readiness, and AI commodity OPRA proof status
- `docs/project-operator-gateboard.md`
  - current read-only operator gateboard showing whether the active blocker is data, candidate lifecycle, proof/evidence, profitability, promotion, or operator readiness
- `docs/regular-options-profit-capture-queue.md`
  - generated research/paper capture queue that tiers profitable regular-options symbol/lane evidence, fresh scan signature matches, evidence-repair priorities, and quarantine/do-not-chase rows without changing scanner policy
- `docs/regular-options-paper-shortlist.md`
  - generated paper-shortlist release gate for fresh executable Tier A lane matches, with bridge blockers and live-prohibited states
- `docs/regular-options-fresh-evidence-loop.md`
  - generated pending-candidate to fill-attempt/tracked-link/exact-realized-P&L readback for the regular options paper gate
- `docs/fresh-executable-evidence-defect-report-2026-06-09.md`
  - named-gate defect report for the still-empty fresh executable realized-P&L funnel
- `docs/regular-options-candidate-outcome-ledger.md`
  - generated unified next-evidence ledger across fresh candidates, paper shortlist, profit-capture queue, open-risk governor, and suggested-trade review blockers
- `docs/regular-options-stale-candidate-archive.md`
  - generated read-only archive for no-longer-matched fresh candidates so stale branches leave the monthly queue without creating trades or mutating scanner/DB state
- `docs/regular-options-suggested-trade-review-plan.md`
  - generated read-only row plan for suggested-trade attention rows so monthly profitability uses explicit review work instead of stale, missing, or display-only close state
- `docs/regular-options-fill-attempt-evidence-capture-plan.md`
  - generated read-only row plan for fresh candidates missing durable fill-attempt evidence, replacing the generic monthly fill-attempt bucket without creating trades or backfilling broker fills
- `docs/regular-options-structure-specific-harness.md`
  - generated read-only structure split for regular-options fill-attempt evidence, separating vertical, single-leg, and other multi-leg diagnostics without counting production proof until exact executable entry/fill/exit P&L exists
- `docs/regular-options-event-data-spine.md`
  - generated read-only event annotation and post-event vol-crush spine for regular-options candidate rows, separating missing event-calendar coverage from exact executable event P&L proof
- `docs/regular-options-overfit-rule-archive.md`
  - generated read-only archive for rejected/winner-damaging candidate filter rules so overfit branches are retired from the monthly next-evidence queue without changing scanner policy
- `docs/regular-options-lane-quarantine-archive.md`
  - generated read-only archive for quarantined negative regular-options lanes so already-retired lane branches leave the monthly disposition queue without changing scanner policy or lane promotion
- `docs/regular-options-execution-alternative-replay-readiness.md`
  - generated read-only readiness queue for future exact OPRA/NBBO top-spread and contract-replacement replay, separating logged alternative seeds from missing replay engines and exit quote coverage
- `docs/regular-options-execution-alternative-replay-coverage.md`
  - generated read-only exact OPRA/NBBO quote-coverage and side-aware replay availability report for logged top-spread and contract-replacement alternatives
- `docs/regular-options-execution-alternative-quote-import-plan.md`
  - generated read-only import/query plan that turns execution-alternative quote demands into grouped ThetaData commands and exact contract manifests without changing contract-selection policy
- `docs/regular-options-open-risk-resolution-plan.md`
  - generated read-only open-risk resolution review plan that turns live-exact and display-only open-risk blockers into row-specific fresh executable review work without broker, DB, scanner, stop, sizing, proof, or promotion changes
- `docs/regular-options-risk-budget-sizing-replay.md`
  - generated read-only risk-budget sizing replay over priced regular-options research/backfill rows, separating paper-shadow/tiered research P&L from live size-tier permission
- `docs/wfo-friction-replay-diff-2026-06-09.md`
  - deterministic one-sleeve WFO-style before/after diff showing that optimizer-selected parameters change once slippage and per-contract fees are charged
- `docs/regular-options-lane-outcome-replay.md`
  - generated read-only lane-outcome coverage replay that separates active regular lanes with exact priced monthly outcomes from no-signal or no-exact-candidate lanes without synthesizing P&L
- `docs/regular-options-lane-scan-hypothesis-repair.md`
  - generated read-only proof-only repair plan for no-signal regular-options lanes, separating predeclared replacement candidates from lanes that still need causal hypotheses without scanner tuning
- `docs/regular-options-exact-candidate-selection-repair.md`
  - generated read-only exact-candidate selection repair target list for signal lanes that produced zero exact chain-native spread candidates
- `docs/regular-options-chain-native-filter-relaxation-replay.md`
  - generated read-only chain-native filter relaxation replay for exact-candidate repair targets, now surfacing trusted entry quote demands instead of changing contract-selection policy
- `docs/regular-options-chain-native-exit-outcome-replay.md`
  - generated read-only exact-exit outcome replay for selected chain-native diagnostic candidates, separating trusted OPRA/NBBO exit P&L from promotion permission
- `docs/regular-options-chain-native-relaxation-archive.md`
  - generated read-only archive for exact-priced negative chain-native relaxation branches so disproved branches leave the monthly next-evidence queue
- `docs/regular-options-exhausted-contract-archive.md`
  - generated read-only archive for exact contract/date repair targets where the current source repeatedly returned no exact OPRA/NBBO rows
- `docs/regular-options-profitability-layer-stack.md`
  - generated all-20 regular-options profitability iteration control plane, separating ready, collecting, blocked, replay-gap, and data-gap layers without changing scanner, broker, stop, sizing, or proof behavior
- `docs/regular-options-minute-exit-replay-readiness.md`
  - generated read-only readiness queue for future exact OPRA/NBBO minute-level exit replay, separating exact entry seeds, position-linked seeds, missing minute quote coverage, and missing replay-engine proof
- `docs/regular-options-minute-exit-quote-import-plan.md`
  - generated read-only import/query plan that turns minute-exit exact entry seeds into grouped ThetaData OPRA/NBBO minute quote commands without changing stops, scanner policy, sizing, broker behavior, proof bars, or promotion
- `docs/monthly-all-lanes-profitability-audit.md`
  - generated monthly all-lanes profitability command center that unifies lane economics, monthly drift, candidate-rule scoring, execution realism, portfolio risk, oracle replay gaps, and next-evidence actions without changing scanner, broker, stop, sizing, DB, proof, or promotion behavior
- `docs/volatility-probation-reconciliation.md`
  - generated readback separating legacy pre-promotion volatility rows from current paper/probation exact-evidence work and open-risk blockers
- `docs/regular-options-operator-workflow.md`
  - Trading Desk operator workflow for local unlock, paper-gate bridge status, pending validation outcomes, and no-fill/skipped auto-track explanations
- `docs/regular-options-repair-attempts.md`
  - generated exact-repair attempt memory/readback for regular-options replay gaps, including exact-date versus lookahead-only proof posture
- `docs/regular-options-repair-burndown.md`
  - generated exact repair burn-down that ranks unexhausted exact-date targets, separates replay-required rows, and excludes exhausted/lookahead-only loops from active import work
- `docs/regular-options-symbol-sleeves.md`
  - generated per-symbol sleeve matrix for regular supervised options, separating lane-symbol keep/watch/quarantine/rejected/needs-paper status from proof evidence class
- `docs/regular-guardrail-starvation-audit.md`
  - latest regular-lane live-scan guardrail starvation audit and upstream zero-candidate readback
- `docs/missed-regular-picks-outcome-audit.md`
  - latest missed regular selected-pick exact-contract outcome audit and lane profitability gate
- `docs/missed-regular-picks-failure-modes.md`
  - latest failure-mode readback for the May 22 through June 5 missed regular selected-pick audit, including lane earn-back policy and diagnostic guardrail candidates
- `docs/missed-regular-picks-filter-matrix.md`
  - latest frozen counterfactual filter matrix for the May 22 through June 5 missed regular selected-pick audit, including paper/probation and duplicate-spread suppression reads
- `docs/lane-promotion-state.md`
  - generated regular-options lane promotion-state readback, separating diagnostic, paper/probation, live-validation, and future auto-track states across all peer lanes
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
  - retired for profitability strategy loops; still usable for broad product/runtime maintenance
- `docs/autoresearch/regular-options-goal.md`
  - Clean-Proof Goal v2 for regular-options strategy loops under the frozen evaluator and executable-P&L progress score
- `docs/autoresearch/fresh-executable-evidence-goal.md`
  - forward evidence goal for collecting fresh exact realized-P&L rows and feeding realized cohort numbers back into strategy prompts
- `docs/autoresearch/goal-prompt-rotation.md`
  - post-sprint operating-loop rotation for heartbeat evidence collection, weekly strategy hypotheses, monthly lane lifecycle review, execution-quality truth, new-lane incubation, and recurring meta-loop audits
- `docs/autoresearch/profitability-paper-gate-goal.md`
  - reusable six-sprint goal prompt for finishing the profitability paper-gate operator workflow with six-subagent review gates
- `docs/autoresearch/monthly-all-lanes-profitability-goal.md`
  - reusable monthly `/goal` prompt for using the all-lanes profitability command center to drive regular-options lane profitability iteration without changing scanner, broker, proof, stop, sizing, DB, or promotion behavior
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
4. Run `npm run verify:docs` before handing off; it checks generated route parity, storage ownership, the Trading Desk schema bridge, the generated frontend proof/evidence artifact, the generated candidate lifecycle artifact, the generated proof invariant table, lane-boundary and AI commodity isolation artifacts, the remediation loop map, the project pathway registry, the agent memory graph, generated artifact governance, the final remediation closure pack, and living-docs hygiene.

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
10. `src/components/predictions/OperatorSessionPanel.tsx`
11. `src/components/predictions/ScannerEvidencePanel.tsx`
12. `src/components/predictions/PaperGateOperatorPanel.tsx`
13. `src/components/predictions/ScannerPickRecordForm.tsx`
14. `src/components/predictions/SuggestedTradesTab.tsx`
15. `src/components/predictions/trackedPositionUtils.tsx`
16. `src/components/predictions/tradingDeskCells.tsx`
17. `src/components/predictions/tradingDeskFormat.ts`
18. `src/components/ui/FinTable.tsx`
19. `src/components/strategy/StrategyView.tsx`
20. `src/lib/client-json.ts`
21. `src/lib/python-bridge.ts`
22. `src/lib/backend/*`
23. `python-backend/main.py`
24. `python-backend/backend_route_context.py`
25. `python-backend/profile_routes.py`
26. `python-backend/predictions_routes.py`
27. `python-backend/tools_routes.py`
28. `python-backend/proof_summary_service.py`
29. `python-backend/replay_profit_service.py`
30. `python-backend/repository_contracts.py`
31. `python-backend/repository_parity.py`
32. `python-backend/trading_desk_api_models.py`
33. `src/lib/trading-desk/apiContracts.ts`
34. `src/lib/trading-desk/apiResponseValidation.ts`
35. `src/lib/generated/proofEvidenceContract.ts`
36. `src/lib/generated/candidateLifecycleContract.ts`
37. `src/lib/trading-desk/proofContract.ts`
38. `src/lib/trading-desk/positionEvidence.ts`
39. `scripts/generate_trading_desk_schema_bridge.py`
40. `scripts/generate_proof_evidence_contract.py`
41. `scripts/candidate_lifecycle.py`
42. `scripts/generate_storage_ownership_map.py`
43. `src/lib/route-lifecycle/routeContracts.ts`
44. `python-backend/local_db_hardening.py`
45. `python-backend/repository_migrations.py`
46. `python-backend/repository_constraints.py`
47. `python-backend/repository_indexes.py`
48. `options_chatbot.py`
49. `wfo_optimizer.py`

## Snapshot Warnings

- `src/app/page.tsx` is intentionally a stub; the real browser entrypoint is the layout plus app shell.
- `src/app/api/day-trading/*` exists only as empty scaffolding folders in this worktree.
- `src/lib/polymarket/*` and `crypto_options/*` are sidecar lanes, not the mounted browser product.
- `data/ai-commodity-infra/progress/latest.md` is generated lane evidence. Read it for the latest AI commodity proof state, but update the living docs manually when the project state changes.
