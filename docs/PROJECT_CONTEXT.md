# Project Context

Last updated: 2026-07-10

This is the concise current-state source of truth for the options-chatbot repository. The byte-exact pre-compaction context is preserved by the verified project-memory archive captured on 2026-07-10 UTC. Historical records explain prior work; code, contracts, current generated readbacks, and the owner docs below determine current behavior.

## Product And Architecture

- The product is a supervised options research and operator-review system, not an autonomous trading authority.
- The frontend is Next.js/TypeScript. The browser product centers on Trading Desk and Strategy Lab surfaces.
- FastAPI/Python owns backend composition, research pipelines, scanner orchestration, evidence readbacks, and local repositories. `python-backend/main.py` remains the composition root; focused routers and services own bounded concerns.
- Canonical architecture owners are `docs/architecture-overview.md`, `docs/architecture-best-practices.md`, `docs/api-and-storage.md`, and `docs/runtime-request-flow.md`.
- Local database classification is owned by `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`. Narrow Trading Desk request models are owned by `docs/trading-desk-api-models.md` and `python-backend/trading_desk_api_models.py`. Tracked-versus-suggested row boundaries are owned by `docs/trading-desk-record-parity.md` and `python-backend/repository_parity.py`.
- Route, storage, proof, lifecycle, and generated-artifact ownership are machine-checked. Start from `docs/index.md` rather than searching every dated report.

## Proof And Safety Boundary

- Backend proof predicates and versioned contracts are authoritative. Frontend labels are display/readability projections, never independent proof.
- Historical, research, backfill, synthetic, midpoint-only, stale, last-trade, or incomplete rows do not become forward proof through naming or display.
- Current gateboard status is `safe_blocked_no_live_release`. Memory, research, and maintenance work do not authorize live validation, auto-track, broker orders, cohort append, evidence mutation, scanner or strategy policy changes, proof-bar changes, protected-holdout use, promotion, stop changes, or sizing changes.
- Active, separate, and paused lane boundaries are generated in `docs/legacy-lane-boundaries.md` from `data/contracts/legacy-lane-boundaries.json`.
- The canonical proof owners are `data/contracts/proof-evidence-contract.json`, `docs/proof-evidence-contract.md`, and generated `docs/proof-invariant-table.md`.
- Scanner-origin creation must pass the lane-wide safety and lifecycle contracts. See `docs/scanner-creation-safety-contract.md` and `docs/candidate-lifecycle-contract.md`.

## Active Options State

- The standing product objective is defensible, prospectively verified profitability. Existing lanes may be repaired, replaced, parked, or removed, and new lanes may be added when evidence warrants them. The current proof, promotion, broker, and live-capital gates remain binding; strategy freedom does not turn research output into release authority.
- Regular options remains research/paper-shadow only. The prospective strict-forward denominator and exact realized-P&L evidence remain insufficient for promotion.
- The final main-lane audit is `docs/regular-options-main-lane-audit-2026-07-10.md`. Its narrow verdict is that the lane has no defensible profitability evidence: the closest historical snapshot loses after fees, while absent scanner/exit/ranking/allocation parity prevents interpreting that snapshot as production expected value or portfolio P&L.
- Historical, forward, fresh-window, and VRP proof paths fail closed on late/duplicate point-in-time inputs, missing or non-causal evidence, incomplete lifecycle/policy/contract continuity, unbound corpora, unproved chains, unknown close metadata, and zero-trade readiness. Exact non-self-asserted forward entry-to-ledger verification is implemented; legacy rows without authoritative locators or synchronized provider legs remain excluded. These controls create no positive evidence: strict forward remains 0/30 and the paper shortlist remains empty.
- The momentum-continuation branch is rejected/underpowered after exact source repair. Batch 3122 imported 24,573 trusted one-minute rows for 63 exact contract/date targets with zero duplicates/rejects/errors. The resulting 340 historical exact rows have net +$31,796, PF 1.5008, but conservative clustered-bootstrap PF lower bound 0.92; 98.02% quote coverage and seven residual gaps do not rescue the failed robustness bar. No historical row counts toward forward proof.
- The VRP put-credit-spread quote surface is ready after bounded trusted batches 3123-3124 added 115,417 rows with zero rejects/provider errors. SPY/QQQ/IWM/DIA each cover all 24 research months and all latest-four months. The bounded runner now fails closed on `missing_native_vrp_candidate_generation_engine`; surface readiness is not an economic result.
- The current operator decision surface is `docs/project-operator-gateboard.md` plus `data/forward-tracking/project_operator_gateboard_latest.json`.
- Phase 2/frozen-cohort work remains bounded by its preregistration and consumed-window rules. Historical and out-of-sample windows already inspected for selection cannot be recycled as fresh proof.
- AI commodity / commodity-infrastructure options is a separate proof-first lane. Its isolation owner is `docs/ai-commodity-isolation.md`; it cannot borrow proof or authority from regular options.
- Parked or falsified branches are summarized by the consolidated parked-branch ledger. Revive one only when its documented source-coverage or contract condition changes.

## Data And Storage

- Authoritative trading/evidence stores are governed by `data/contracts/evidence-host-policy.json` and `docs/evidence-operations.md`.
- `data/options-validation/options_history.db` is the active compacted option-history store. Its large pre-vacuum backup is protected until the fresh 2018-2021 imports, downstream pipeline, SQLite verification, and an exact verified replacement backup all pass.
- The full historical adapter regeneration is not operationally acceptable yet: a pre-final read-only run remained CPU-active for about 9.5 hours without producing an artifact and was terminated after its loaded code became stale. Profile and batch/index its quote path before another full-corpus run.
- Raw import artifacts and authoritative SQLite/JSONL ledgers are audit-only unless a distinct replacement is sealed and verified. Cleanup tools must fail closed.
- Rebuildable caches, generated timestamp families, stale logs, inactive lane data, and redundant memory backups follow `data/contracts/project-storage-retention-policy.json` and the guarded scripts under `scripts/`.

## Agent Memory And Durable History

- An agreed CEO goal grants the Prime agent full local implementation authority for the scoped code, tests, docs, scripts, config, control-plane, and strategy/scanner/data-workflow work. Worker permission labels bind dependent task actions, while separate evidence, production activation, proof, promotion, broker/live, holdout, cohort-append, and stop/sizing gates bind those actions only. A blocked dependent gate does not freeze unrelated scoped implementation.
- `scripts/agent_control.py` is the compatibility entrypoint; `scripts/agent_control/legacy.py` currently owns the frozen schema-v5 implementation and ignored state under `data/agent-control/`. Extracting the large legacy module into real domain modules remains maintainability debt.
- Schema v5 preserves tenant-safe task lifecycle and adds strict recovery: every required backup member must be declared present, the manifest tenant must exactly match the requested tenant, and DB session IDs must match `sessions.jsonl`. Current outbox rows use a canonical v2 hash that binds SQL identity, tenant, timestamp, event type, and payload; active mirrors require canonical DB order, while declared legacy v1 outbox bundles retain bounded audit compatibility.
- One per-DB lock serializes schema initialization/migration, WAL setup with bounded retry, event writes, mirror repair, and snapshot backup. Session graph/event commits are durable before sidecar delivery; a `session_sidecar_outbox` keeps an append failure retryable, and retrying the same immutable ID/hash reconciles `sessions.jsonl` without duplicating the session event.
- Dream acceptance reparses the verified source and rejects stored-entry divergence. Observed claims require same-tenant, reviewed, provenanced, integrity-bearing evidence of an allowed kind; only a trusted writer may set the reserved attestation, and acceptance cross-checks that attestation against either the durable session/outbox record or the authoritative artifact source/hash. Query output forces nonauthorization metadata, raw node/edge action metadata is quarantined, and accepted dream lessons are pathway-filtered in focused context packs.
- Retrieval mutations reindex in the same transaction. `--fresh-only` applies across retrieval stages; refresh reads only contained safe repo paths, treats outside/protected paths as missing, and always unions the canonical code-owned `PROJECT_SEED_FILES` set with durable expectation rows. Missing or deleted expectation rows therefore cannot hide a required seed. Missing required living/startup/gateboard sources are fatal; tier-3 repo-mirror gaps remain nonfatal and opt-in.
- Stable living-history expectations bind WORKLOG entries to `episode` and DECISIONS entries to `decision`; activation changes are hash-chained events. Ghost node/retrieval/expectation cleanup is one transaction. Gateboard pathway/blocker/source-artifact nodes derive from one coherent gateboard byte snapshot; seeding validates and hashes each safe `available=true` artifact as snapshot provenance, while `available=false` remains an explicit unavailable declaration and cannot satisfy an available-source expectation.
- Runtime memory is retrieval and orchestration context only. It cannot grant trading, evidence, release, or broker authority. Agent-control tests passed 119/119 and memory-graph tests passed 17/17, 136 total, with an independent root-level reproduction. Live schema-v5 migration, session and ghost repair, final living-history ingest/bootstrap, doctor, audit, retrieval, operator-dashboard, eval, outbox/mirror/anchor checks, backup restore, and dream audit are green. Maintenance run `RUN-20260710-c1aae9a5` passed and latest options dream `DREAMRUN-20260710-d64378a5` completed. Preserve verified-v5 copy `data/agent-control/verified-v5-safety/20260710T063210Z-ac899ea5` and pre-ghost-repair bundle `data/agent-control/backups/20260710T141639Z-ed16ac30`, which passed restore-check.
- Machine-wide dreaming uses canonical audit-contract SHA-256 `eb867cc4f8641f5a5085e059f9c6c15c84ade2e4894361bae23e1d53581da0d9`. Manual run `PMDREAM-20260710-150315388-4dc9366af849` (sequence 2) and scheduled latest `PMDREAM-20260710-150505551-ddd8389b9bee` (sequence 3) completed. `\ProjectsMemoryDreaming`, `\OptionsMemoryDreaming`, and `\OptionsMemoryMaintenance` each have observed `LastTaskResult=0`; the options dreaming task retains its 45-minute limit.
- Nonblocking scale debt remains in living-history refresh: cache shared source snapshots so multiple nodes do not reread the same source bytes (`O(nodes x source-read)` CPU). The current scheduled maintenance still finishes in about six minutes inside its 30-minute task limit.
- WORKLOG and DECISIONS ingestion validates and combines immutable project-memory archives with concise live files, deduplicates by stable node identity, records physical provenance, and prunes only after the full corpus is known.
- Generic repo indexing excludes `docs/archive/project-memory/`; historical entries remain available through living-history ingestion instead of duplicate tier-3 file mirrors.
- Memory backup pruning requires a newest fully passing recovery point. Calendar-retained bundles and invalid/in-progress directories are preserved. Redundant older bundles may be removed only after full assessment; the separate degraded acknowledgement accepts solely regenerable event-mirror mismatch/duplicate failures when the bundle ledger, DB outbox, anchors, manifest, and sidecars otherwise pass.
- The computer-wide graph at `C:\Users\kalec\projects-memory` is a curated 14-project pointer/provenance layer, not repo authority or a user-profile crawl. `shopbot` remains an intentionally unmanaged diagnostic candidate pending curated review.
- Control-plane workflow and commands are documented in `docs/agent-control-plane.md`; the dated implementation/readiness record is `docs/memory-graph-v5-upgrade-audit-2026-07-10.md`.

## Normal Workflow

1. Read `AGENTS.md`, this file, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, and the relevant owner doc.
2. Read the current gateboard before options research or release claims.
3. Use narrow package scripts and focused tests first; then run the relevant verification aggregate.
4. Preserve concurrent work. Do not edit files actively owned by another window.
5. After meaningful work, update the concise live memory files. Historical detail belongs in the immutable archive or dedicated evidence artifacts, not repeated startup context.

Common verification commands:

```powershell
npm run verify:docs
npm run verify:agent-control
npm run verify:memory
npm run verify:frontend
uv run --locked python -m unittest
```

Use narrower commands when the full suite would touch active imports, browser processes, or concurrently owned files.

## Current Size Posture

- Timestamped profitability/forward snapshots use family-aware recent/daily/weekly/monthly retention while preserving referenced runs, state transitions, malformed evidence, and safety milestones.
- Large inactive day-trading data has a verified compressed archive; active authoritative options data remains in place.
- The pre-vacuum backup and raw import corpus are intentionally retained until their independent safety gates pass.
- The five startup memory files have explicit size budgets enforced by the living-doc hygiene check. The full pre-compaction corpus remains hash-verifiable in the project-memory archive.
