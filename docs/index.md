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
- `docs/regular-options-profitability-blocker-inventory.md`
  - current whole-surface regular-options profitability blocker inventory, separating cleared stale VIX blockers from remaining forward, source, input, quote-surface, engine, provider, approval, and market-window blockers
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
- `docs/agent-control-plane.md`
  - local CEO/worker orchestration flow and runtime memory graph backed by ignored SQLite/JSONL state
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
- `docs/regular-options-existing-input-surface-atlas.md`
  - generated read-only inventory of existing point-in-time input/source surfaces; current status is `research_only_input_surfaces_exhausted_under_current_repository`
- `docs/regular-options-phase2-forward-paper-shadow-market-window-capture.md`
  - generated audit of the approved Phase 2 forward paper-shadow capture gate; current status is `no_phase2_natural_selections_no_append`
- `docs/regular-options-59-symbol-thetadata-opra-import-repair.md`
  - generated scoped 59-symbol ThetaData OPRA/NBBO source-repair preflight; current status is `blocked_thetaterminal_source_unavailable`
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
- `docs/evidence-operations.md`
  - operational survivability contract for authoritative evidence host, backups, scheduled-scan heartbeat, daily operator command, and retention policy
- `docs/forward-holdout-contract.md`
  - generated protected forward-holdout contract for regular-options autoresearch and one-shot champion final evaluation consumption
- `data/contracts/forward-holdout-contract.json`
  - generated machine-readable protected forward-holdout contract consumed by the regular-options autoresearch harness
- `docs/forward-cohort-preregistration.md`
  - generated frozen forward-cohort preregistration for the regular-options six-week validation window and parked-lane readback
- `data/contracts/forward-cohort-preregistration.json`
  - generated machine-readable frozen cohort contract consumed by lane promotion and all-lanes scan selectors
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
- `docs/regular-options-multi-leg-side-aware-pricing-capability.md`
  - generated read-only multi-leg bid/ask pricing capability artifact for bounded ratio/backspread fixtures
- `docs/regular-options-base-clean-stack-identity-ledger.md`
  - generated read-only row-level identity ledger for the 157-row clean base stack, used for strict-new duplicate control without creating replay/proof/profitability rows
- `docs/regular-options-flow-extreme-denominator-dedupe-bridge.md`
  - generated read-only full-denominator and strict-new dedupe bridge for the flow-extreme ratio/backspread branch, now consuming the base clean stack identity ledger
- `docs/regular-options-all-local-quote-minute-structure-capability-atlas.md`
  - generated read-only all-local quote-minute structure capability atlas; current status exhausts local quote-surface-only replayability under current data because all selected surfaces fail the 20-train-month feasibility gate despite dense latest-four quote depth
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
- `docs/regular-options-trade-qualification.md`
  - generated read-only trade qualification and profitability triage report combining gateboard, lane promotion, fresh evidence, candidate ledger, paper shortlist, repair, open-risk, suggested-review, historical walk-forward, and robust-search readbacks
- `docs/regular-options-paper-shadow-evidence-plan.md`
  - generated read-only row-level plan for collecting paper-shadow/probation exact entry, policy-defined exact exit, fill-attempt, suggested-review, repair-only, and no-chase evidence without creating trades or changing proof, scanner, broker, stop, sizing, live-validation, auto-track, promotion, or database state
- `docs/bullish-pullback-layer-shadow-selection.md`
  - generated read-only selector that routes the frozen bullish-pullback layer stack into future paper-shadow harness requirements while preserving no-live, no-broker, no-import, and no-mutation boundaries
- `docs/regular-options-bullish-pullback-layer-execution-safety-audit.md`
  - generated read-only preflight for the selected bullish-pullback layer harness, currently blocked because the historical run lacks leg-level entry/exit bid-ask provenance
- `docs/regular-options-bullish-pullback-layer-executable-economics.md`
  - generated read-only side-aware executable-economics falsification report for the selected bullish-pullback layer harness, recomputing trusted bid/ask USD P&L without importing quotes or mutating evidence stores
- `docs/regular-options-bullish-pullback-layer4-forward-capture-protocol.md`
  - generated read-only future paper-shadow capture protocol for bullish-pullback `layer_4_clean_exact`, with validator and approval-packet boundaries before any market-window evidence row collection
- `docs/bullish-pullback-layer4-forward-paper-shadow-approval-packet.md`
  - approval packet template for future bullish-pullback layer4 full-denominator paper-shadow rows; informational only until a valid market-data window and separate operator approval
- `docs/regular-options-market-window-approval-preflight.md`
  - generated read-only fail-closed approval preflight for future bullish-pullback layer4 market-window paper-shadow candidate rows, validating current readbacks, market-window state, explicit operator approval, and optional candidate JSONL without appending rows
- `docs/regular-options-market-window-evidence-checklist.md`
  - generated read-only market-window checklist that orders safe refresh commands, exact-entry waits, policy-exit waits, fill-attempt capture, suggested-review-only rows, repair-only rows, and no-chase blocks without creating trades or mutating evidence stores
- `docs/regular-options-strict-forward-operator-queue.md`
  - generated read-only strict-forward operator queue for the current profitability loop; reports `0/30` strict forward rows, keeps profitability readiness false, parks stale cleanup branches, and routes the next natural-market paper-shadow step through bullish-pullback `layer_4_clean_exact` market-window/operator-approval gates
- `docs/regular-options-strict-forward-market-window-readiness-refresh.md`
  - generated no-write readiness refresh for the strict-forward queue; consolidates current readbacks, market-window/preflight state, candidate JSONL existence, append permission, safety flags, and the one-screen operator decision table
- `docs/regular-options-forward-candidate-throughput-audit.md`
  - generated read-only throughput audit for Phase 2 scan picks; distinguishes missing frozen-lane scheduled sessions from true same-day candidate starvation
- `docs/regular-options-strict-forward-30-goal-loop.md`
  - generated coordinator report for the active `30` strict completed forward-row goal; runs/checks the safe sweep/capture/throughput/readiness sequence while preserving no-fabrication, no-live, no-broker, no-autotrack, no-proof-change, and guarded-append boundaries
- `docs/regular-options-strict-forward-30-market-window-collector.md`
  - generated bounded collector for the active `30` strict completed forward-row goal; repeats the strict-forward coordinator only during confirmed open market windows and stops on candidate review, guarded append, safety violation, scan failure, or goal completion
- `docs/regular-options-strict-forward-30-auto-window-collector.md`
  - generated scheduler-friendly auto-window wrapper report for the active `30` strict completed forward-row goal; checks the market window before invoking the bounded collector and persists latest wrapper state without appending rows
- `docs/regular-options-strict-forward-30-scheduler-health.md`
  - generated Windows Task Scheduler health readback for `\OptionsStrictForward30Collector`; verifies the repeated no-append auto-window collector task is enabled, ready, correctly pointed, and repeating on the expected cadence
- `docs/regular-options-strict-forward-30-candidate-review-packet.md`
  - generated read-only candidate handoff packet for the strict-forward `30`-row goal; consolidates capture, collector, scheduler health, candidate JSONL validation, and guarded operator commands without appending rows
- `docs/regular-options-strict-forward-30-completion-monitor.md`
  - generated read-only completion monitor for the strict-forward `30`-row goal; recomputes strict completed rows from the Phase 2 cohort report and cross-checks scheduler, candidate-review, collector, and safety state
- `docs/regular-options-strict-forward-30-lifecycle-audit.md`
  - generated read-only lifecycle audit for the strict-forward `30`-row goal; separates entry rows waiting for policy exits from strict exact-exit completion rows and documents the append-only completion policy
- `docs/regular-options-strict-forward-30-exit-completion-stager.md`
  - generated no-append stager for exact-exit completion candidates; converts open Phase 2 cohort rows plus trusted exit evidence JSONL into guarded-append-ready exact-exit candidate rows
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
- `docs/regular-options-feature-store.md`
  - generated read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO rows, with `tradable_after_time <= candidate_entry_time` join policy
- `docs/regular-options-cvx-executable-coverage.md`
  - generated read-only CVX executable quote coverage diagnostic separating observed zero-bid tradability failure from missing provider data
- `docs/regular-options-source-quality-scope-policy.md`
  - manually maintained historical robust-search source-quality scope policy for candidate-specific exclusions such as CVX zero-bid tradability
- `data/contracts/regular-options-source-quality-scope-policy.json`
  - machine-readable runtime source-quality scope policy consumed by the robust-search evaluator
- `docs/regular-options-robust-search-evaluation.md`
  - generated read-only chronological train/validation/final-holdout robust-search report for historical exact rows, failing closed on missing regime, ablation, winner-damage, quality, or sample evidence
- `docs/regular-options-historical-simulated-forward-audit.md`
  - generated read-only calendar split audit that tests whether current selected historical exact rows support a 20-month train plus latest-4-month simulated-forward audit, while separating quote-history depth from selected-trade depth
- `docs/regular-options-historical-depth-selected-trades.md`
  - generated read-only selected-trade calendar-depth readback for the older trusted quote-history window, separating proven selected-entry months from unproven raw quote availability
- `docs/regular-options-historical-walk-forward.md`
  - generated read-only operator workflow that refreshes feature-store and robust-search readbacks, ingests all-planned peer sleeve results, and reports historical walk-forward blockers without consuming protected holdout
- `docs/regular-options-robust-edge-discovery.md`
  - generated read-only robust edge discovery and falsification report that ranks historical, paper-shadow, repair, and quarantine candidates against execution-realistic proof, split/holdout, stress, concentration, and forward-freeze gates
- `docs/regular-options-hypothesis-tournament.md`
  - generated read-only hypothesis tournament that applies a bounded search budget to current robust-edge, walk-forward, and missed-pick filter candidates, preserving execution-realistic proof, holdout, stress, concentration, and no-live gates
- `docs/regular-options-current-regime-lane-incubator.md`
  - generated read-only current-regime lane incubator that preregisters lane concepts for current market conditions, ranks proof feasibility, and names approval requirements without creating scanners, changing policy, importing quotes, or promoting lanes
- `docs/regular-options-current-regime-momentum-edge.md`
  - generated read-only current-regime momentum edge/throughput test that checks existing momentum-compatible artifacts against the 200-row strict-new count target, economics, coverage, and stress gates without aggregating raw overlapping counts
- `docs/regular-options-countable-throughput-frontier.md`
  - generated read-only all-planned throughput frontier and stop-verdict report that separates raw count from strict-new, execution-clean, stress-safe, independently profitable add-on rows
- `docs/regular-options-causal-falsification-slice.md`
  - generated read-only preregistered causal falsification slice that stops exhausted raw-count, tracked-winner, clean index/IWM refill, and existing momentum-compatible artifact branches before the next GPT-5.5 Pro loop decision
- `docs/regular-options-preregistered-momentum-continuation-playbook.md`
  - generated read-only preregistered design artifact for `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`, defining causal inputs, permitted universe, exclusions, and future proof path without implementing or replaying the playbook
- `docs/regular-options-preregistered-vrp-credit-spread-playbook.md`
- `docs/regular-options-vrp-credit-spread-replay-readiness.md`
  - generated read-only preregistered design artifact for `low_mid_vix_index_put_credit_spread_vrp_v1`, defining low/mid-VIX index put-credit spread rules, side-aware credit-spread proof formulas, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-vrp-credit-spread-quote-surface.md`
  - generated read-only trusted OPRA/NBBO quote-surface proof for the VRP put-credit-spread geometry, checking same-minute same-expiry put strike availability without replay, P&L, quote import, evidence mutation, or promotion
- `docs/regular-options-preregistered-term-structure-calendar-playbook.md`
  - generated read-only preregistered design artifact for `low_mid_vix_index_calendar_term_structure_dislocation_v1`, defining low/mid-VIX index calendar/diagonal rules, multi-expiry side-aware formulas, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-term-structure-calendar-replay-readiness.md`
  - generated read-only replay-readiness audit for `low_mid_vix_index_calendar_term_structure_dislocation_v1`, classifying calendar/diagonal entry/exit/expiry pricing, denominator, assignment, roll, term-structure input, quote-surface, holdout, strict-new, and proof-boundary prerequisites without implementing or replaying the playbook
- `docs/regular-options-term-structure-calendar-structure-harness.md`
  - generated read-only structure harness for `low_mid_vix_index_calendar_term_structure_dislocation_v1`, now clearing frozen geometry and strict-new dedupe while preserving point-in-time term-structure input and index calendar quote-surface blockers
- `docs/regular-options-term-structure-calendar-bounded-replay.md`
  - generated read-only bounded replay gate for `low_mid_vix_index_calendar_term_structure_dislocation_v1`, currently blocked on point-in-time term-structure inputs and index calendar quote surface without running replay or claiming profitability
- `docs/regular-options-preregistered-skew-broken-wing-playbook.md`
  - generated read-only preregistered design artifact for `low_mid_vix_index_skew_broken_wing_put_fly_v1`, defining low/mid-VIX downside-skew broken-wing put butterfly rules, all-leg side-aware formulas, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-preregistered-macro-event-long-strangle-playbook.md`
  - generated read-only preregistered design artifact for `low_mid_vix_macro_event_long_strangle_v1`, defining scheduled macro-event long straddle/strangle rules, event-calendar requirements, all-long-leg side-aware formulas, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-macro-event-calendar.md`
  - generated read-only point-in-time macro-event calendar validator for scheduled-event research, requiring known-at and source provenance, rejecting outcome/realized/future/P&L leakage fields, and currently blocking because no trusted local source rows exist
- `docs/regular-options-point-in-time-vix-bucket.md`
  - generated read-only point-in-time VIX low/mid bucket validator for regular-options research; current VIX is ready with trusted local source rows, frozen threshold policy, full requested-date coverage, known-at discipline, and no leakage blockers
- `docs/regular-options-macro-event-long-strangle-replay-readiness.md`
  - generated read-only replay-readiness audit for `low_mid_vix_macro_event_long_strangle_v1`, consuming the macro-event calendar and point-in-time VIX bucket artifacts while defining side-aware long-premium formulas, denominator statuses, strict-new identity, holdout guard, and future replay proof conventions without running replay
- `docs/regular-options-13-symbol-candidate-generation-surface-audit.md`
  - generated read-only audit of the narrower trusted 13-symbol candidate-generation surface, separating all-month quote availability from missing candidate-generation/no-pick proof, broad 59-symbol source artifacts, non-13 selected rows, CVX scope handling, and validated no-write/as-of/universe-filter runner support
- `docs/regular-options-13-symbol-candidate-generation-no-write.md`
  - generated read-only no-write/as-of/universe-filter runner-support artifact for the frozen 13-symbol candidate-generation surface; it proves runner controls only and does not count quote-history-only months or historical rows as profitability proof
- `docs/regular-options-13-symbol-frozen-daily-candidate-decisions.md`
  - generated read-only frozen daily candidate/no-pick/blocker decision materializer; it rejects broad or mismatched source artifacts at the materializer boundary and requires explicit `proof_safe=true` before accepted rows can become proof-safe
- `docs/regular-options-historical-frozen-scanner-replay-adapter.md`
  - generated bounded read-only historical scanner replay adapter for the frozen Phase 2 lane/symbol/date denominator; it currently emits 6,916 blocked rows and names missing point-in-time scanner inputs instead of inventing selected/no-pick rows
- `docs/regular-options-13-symbol-frozen-candidate-generation-source-surface.md`
  - generated read-only frozen 13-symbol candidate-generation source-surface materializer; it consumes the frozen entrypoint, keeps broad selected rows out of proof, and currently proves 0/24 candidate-generation months and 0 selected rows
- `docs/regular-options-13-symbol-frozen-candidate-generation-entrypoint.md`
  - generated read-only reusable frozen daily candidate/no-pick entrypoint; it currently emits 6,916 blocked lane/symbol/date rows because daily candidate-generation diagnostics are missing
- `docs/regular-options-13-symbol-frozen-candidate-generation-denominator-v2.md`
  - generated read-only daily candidate/no-pick/blocker denominator for the frozen 13-symbol source surface; it currently parks the branch with 494 blocked market-date rows, 0 latest-four strict-new candidates, and smallest blocker `missing_frozen_13_symbol_candidate_generation_engine`
- `docs/regular-options-13-symbol-frozen-candidate-generation-engine.md`
  - generated read-only frozen 13-symbol candidate-generation engine/daily diagnostics artifact; it consumes the frozen entrypoint and currently parks on incomplete daily diagnostics with 6,916 blocked lane/symbol/date rows and no selected candidates
- `docs/regular-options-59-symbol-thetadata-opra-import-resume.md`
  - generated tokened resume retry for the approved scoped 59-symbol ThetaData OPRA/NBBO source repair; it currently parks on local ThetaTerminal availability with no import attempted, 260 shared trusted dates, and 11,565 remaining symbol-date gaps
- `docs/regular-options-direct-vix-source-repair-packet.md`
  - generated read-only direct VIX source repair packet; current status is superseded by the materialized VIX source and ready point-in-time VIX bucket, with no current VIX blockers or replay/profitability claim
- `docs/regular-options-macro-event-calendar-source-repair-packet.md`
  - generated read-only macro-event calendar source repair packet; it defines scheduled-event schema, known-at/tradable-after policy, frozen categories, future tokened import/materialization command, and macro-event/post-event branch implications without importing event rows or running replay
- `docs/regular-options-flow-extreme-source-repair-packet.md`
  - generated read-only flow-extreme volume/OI source repair packet; it defines SPY/QQQ trusted daily volume/open-interest schema, known-at policy, prior-row percentile threshold policy, future tokened import/materialization command, and flow-extreme branch implications without importing flow rows or running replay
- `docs/regular-options-underlying-daily-source-repair-packet.md`
  - generated read-only underlying daily OHLCV/adjusted-close source repair packet; it defines the 13-symbol point-in-time daily source schema, strict known-at policy, local `market_data.db:daily_history` insufficiency, future tokened materialization path, and downstream market-regime/frozen-scanner unlock commands without importing source rows or running replay
- `docs/regular-options-underlying-daily-source-acquisition.md`
  - generated read-only staged-source acquisition preflight for the underlying daily OHLCV/adjusted-close source; it currently blocks on missing `data/import-staging/underlying_daily` trusted CSV files and refuses local DB/reconstructed/inferred-known-at shortcuts without writing source rows or running replay
- `docs/regular-options-underlying-daily-source-import.md`
  - generated tokened underlying daily OHLCV/adjusted-close source import report; sample fixture materialization writes generated source rows only, preserves no-replay/no-live/no-broker/no-proof boundaries, and does not clear the full 13-symbol blocker without a trusted full-window source CSV
- `docs/regular-options-quote-surface-opening-range-reversal-replay.md`
  - generated read-only quote-surface-only opening-range reversal replay for SPY/QQQ/IWM/DIA; it currently parks the branch with 1,976 blocked daily denominator rows, 0 candidate rows, and smallest blocker `blocked_missing_quote_surface_underlying_price`
- `docs/regular-options-quote-derived-synthetic-forward-surface.md`
  - generated read-only synthetic-forward opening-bucket source surface for SPY/QQQ/IWM/DIA; it currently parks the branch with 1,976 symbol-date rows, 7,904 requested bucket checks, 0 ready buckets, and missing same-minute call-put-pair coverage
- `docs/regular-options-local-quote-structure-capability-matrix.md`
  - generated read-only local OPRA/NBBO structure capability matrix for the 13-symbol proof set; it currently emits 0 replay-feasible structures because dense latest-four quote-surface rows fail the required 20 train-month coverage gate
- `docs/regular-options-preregistered-post-event-iv-crush-iron-condor-playbook.md`
  - generated read-only preregistered design artifact for `post_event_iv_crush_index_iron_condor_v1`, defining scheduled macro-event post-event IV-crush iron condor/butterfly rules, event and IV-premium requirements, four-leg side-aware formulas, max-loss/margin requirements, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-post-event-iv-crush-replay-readiness.md`
  - generated read-only replay-readiness audit for `post_event_iv_crush_index_iron_condor_v1`, checking macro-event calendar, IV/event-premium proxy, VIX bucket, four-leg quote surface, side-aware formula contracts, denominator mapping, strict-new dedupe, and holdout guard without running replay
- `docs/regular-options-preregistered-flow-extreme-ratio-backspread-playbook.md`
  - generated read-only preregistered design artifact for `index_flow_extreme_mean_reversion_ratio_backspread_v1`, defining point-in-time flow/overextension ratio-spread and backspread rules, defined-risk/max-loss requirements, multi-leg side-aware formulas, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-point-in-time-flow-extreme-input.md`
  - generated read-only point-in-time flow-extreme input materializer; currently fails closed because no trusted local flow source rows exist, so plain bid/ask quote availability is not relabeled as flow and the flow-extreme branch remains blocked on explicit input-source coverage
- `docs/regular-options-flow-extreme-volume-oi-source-rows.md`
  - generated read-only trusted volume/open-interest source-row generator for the flow-extreme ratio/backspread branch; currently fails closed because trusted ThetaData intraday rows have no usable volume/OI aggregates and no point-in-time source rows are written
- `docs/regular-options-base-clean-stack-identity-ledger.md`
  - generated read-only row-level identity ledger for the 157-row clean base stack; current status is ready with 157 unique identities and no duplicate/missing/leaky/holdout-overlap rows
- `docs/regular-options-flow-extreme-denominator-dedupe-bridge.md`
  - generated read-only denominator/dedupe bridge that now clears flow-extreme full denominator mapping and strict-new dedupe after consuming the base clean stack identity ledger
- `docs/regular-options-all-local-quote-minute-structure-capability-atlas.md`
  - generated read-only all-local quote-minute structure capability atlas; current status exhausts local quote-surface-only replayability under current data because all selected surfaces fail the 20-train-month feasibility gate despite dense latest-four quote depth
- `docs/regular-options-flow-extreme-ratio-backspread-replay-readiness.md`
  - generated read-only replay-readiness audit for `index_flow_extreme_mean_reversion_ratio_backspread_v1`, checking point-in-time flow/extreme inputs, VIX bucket readiness, side-aware ratio/backspread pricing, max-loss/collateral, assignment/expiration, SPY/QQQ quote surface, denominator mapping, strict-new dedupe, holdout guard, and proof-boundary labeling without running replay
- `docs/regular-options-preregistered-dispersion-proxy-hybrid-playbook.md`
  - generated read-only preregistered design artifact for `index_constituent_dispersion_proxy_defined_risk_hybrid_v1`, defining index-versus-constituent dispersion-proxy debit/credit hybrid pair rules, CVX source-quality handling, pair-level side-aware formulas, collateral/max-loss requirements, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-point-in-time-dispersion-concentration-proxy.md`
  - generated read-only point-in-time dispersion/concentration proxy materializer; currently fails closed because no trusted local proxy source rows exist and the feature store has no underlying return fields, so the dispersion branch remains blocked on explicit input-source coverage
- `docs/regular-options-dispersion-proxy-hybrid-replay-readiness.md`
  - generated read-only replay-readiness audit for `index_constituent_dispersion_proxy_defined_risk_hybrid_v1`, currently blocked only on point-in-time dispersion/concentration inputs after clearing VIX, pair construction, all-leg side-aware pricing, max-loss/collateral, denominator mapping, strict-new dedupe, CVX scope, holdout guard, and proof-boundary prerequisites without running replay
- `docs/regular-options-preregistered-pmcc-diagonal-playbook.md`
  - generated read-only preregistered design artifact for `low_mid_vix_index_pmcc_diagonal_income_v1`, defining PMCC-style call diagonal rules, side-aware entry/roll/exit/expiry formulas, short-call assignment/ex-dividend handling, collateral/max-loss requirements, denominator statuses, engine requirements, and falsification gates without implementing or replaying the playbook
- `docs/regular-options-pmcc-diagonal-replay-readiness.md`
  - generated read-only replay-readiness audit for `low_mid_vix_index_pmcc_diagonal_income_v1`, currently parked on missing point-in-time trend/regime inputs and missing trusted long-DTE SPY/QQQ PMCC quote surface; the VIX bucket is ready
- `docs/regular-options-preregistered-playbook-readiness-selector.md`
  - generated read-only selector across completed preregistered playbooks, now consuming the momentum bounded replay gate and reporting no blocker-free research implementation candidate without implementing, replaying, importing quotes, mutating evidence, or promoting
- `docs/regular-options-momentum-continuation-research-replay.md`
  - generated operator-approved research-only replay harness for `breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1`, separating full denominator rows, proof-qualified rows, and diagnostic-only old-artifact marks without changing scanner policy, importing quotes, mutating evidence, or promoting
- `docs/regular-options-momentum-continuation-proof-blocker-resolution.md`
  - generated read-only proof-blocker resolution audit for the approved momentum-continuation branch, resolving existing trusted side-aware quote pairs where possible while preserving missing point-in-time breadth/SPY/QQQ momentum blockers and keeping all rows historical research only; current VIX is cleared
- `docs/regular-options-momentum-continuation-bounded-replay.md`
  - generated read-only bounded replay gate for the approved momentum-continuation branch, consuming the replay/proof-blocker artifacts and parking the branch at `0` strict rows until point-in-time breadth/SPY/QQQ momentum inputs or approved data repair change the blocker; current VIX is cleared
- `docs/research-decisions/options_oracle_profit_loop_packet_latest.md`
  - generated same-session GPT-5.5 Pro loop packet that requires a continue/stop/significant-upgrade decision, selected branch, concrete Codex task, commands, acceptance criteria, and stop condition
- `docs/regular-options-evidence-blocker-burndown.md`
  - generated read-only proof-preserving repair planner that ranks source-quality, unpriced, zero-bid/tradability, exhausted-source, lookahead-only, holdout-depth, PF lower-bound, and no-chase blockers without mutating evidence stores
- `docs/regular-options-source-replay-pass.md`
  - generated read-only readback for bounded source-replay-first passes over high-value exact repair blockers, separating derived replay attempts from unsafe/no scoped replay commands, unresolved unpriced rows, and unchanged robust-candidate gates
- `docs/regular-options-robust-candidate-source-quality-manifest.md`
  - generated read-only manifest classifying high-priority historical robust-candidate source-quality blockers into missing-quote, zero-bid/tradability, chain-native selection, paper-shadow evidence, and statistical/sample gates
- `docs/regular-options-exact-target-plan.md`
  - generated read-only exact target plan for robust-candidate source-quality missing-exit quote rows and Lane A no-chain-native-spread selection gaps, with protected-holdout and duplicate accounting
- `docs/regular-options-exact-target-import-approval-packet.md`
  - read-only approval packet for staged plan-only and dry-run decisions over the regular-options exact-target quote-import scope
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
- `docs/regime-stratified-replay-report.md`
  - generated read-only regime stratification of current exact replay rows by VIX tercile, SPY 50-day trend state, and entry month, surfaced in the monthly audit without changing scanner, broker, proof, or promotion behavior
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
- `docs/autoresearch/memory-graph-dreaming-goal.md`
  - reusable end-to-end prompt for the computer-wide memory graph and options-local dreaming/control-plane loop
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
