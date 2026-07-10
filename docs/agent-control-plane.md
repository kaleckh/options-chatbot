# Agent Control Plane

This document owns the local CEO/worker control-plane workflow and the first runtime memory graph. It does not replace `docs/agent-memory-graph.md`; that file is generated, static navigation metadata with `runtime_use=false`.

`scripts/agent_control.py` is a compatibility CLI shim. The current implementation remains in `scripts/agent_control/legacy.py`; the small files under `scripts/agent_control/` re-export bounded domains from that module. Splitting the 10k-line legacy module into real domain modules is maintainability debt, not part of the schema-v5 correctness upgrade. Local operator memory is stored under ignored `data/agent-control/` by default:

- `agent_control.db`: SQLite tenant-scoped task, graph, retrieval, run-ledger, and event-outbox state using WAL mode; WAL setup is serialized and retried under bounded lock contention
- `events.jsonl`: active event-outbox mirror for agent-readable audit trails; it is repairable from SQLite, not an independent authority source
- `agent_run_events`: append-only-ish SQLite ledger for agent/subagent run events, hash-chain audit, blocked/failed run summaries, approval notes, and local inbox views
- `sessions.jsonl`: compact session transcript provenance records
- `context-packs/*.json`: generated context-pack manifests with node IDs, retrieval explanations, policy banner, and gateboard hash
- `dream-runs/latest.*`: automated dreaming audit output

## Fresh Agent Quickstart

For meaningful multi-step work, resumed work, CEO/worker orchestration, or subagent debates, treat the runtime graph as on by default:

```powershell
npm run memory:bootstrap
npm run memory:context -- --goal "current task" --pathway operator --prompt-only
```

Use the graph to recover context and write back reviewed lessons, not to replace repo facts. Living docs, generated readbacks, code, exact evidence artifacts, and gateboard state remain authoritative.

| Need | Command |
| --- | --- |
| Recover current checkpoint and gateboard blockers | `npm run memory:bootstrap` |
| Build a focused prompt pack | `npm run memory:context -- --goal "<goal>" --pathway operator --prompt-only` |
| Query targeted graph context | `npm run agent:control -- graph query "<query>" --metadata KEY=VALUE --prompt-only` |
| Accept a reviewed worker/subagent report into operating memory | `npm run memory:writeback -- <task-id> --summary "Accepted after review."` |
| Record a reviewed durable lesson directly | `npm run agent:control -- memory remember --type lesson --title "..." --body "..." --confidence inferred --json` |
| Review dream proposals and dream-origin lessons | `npm run memory:review-dreams` |
| Run automated dreaming now | `npm run memory:dream-run` |
| Audit automated dreaming | `npm run memory:dream-audit` |
| Audit the whole memory system | `npm run memory:operator-dashboard` |
| Review recent agent/subagent run history | `npm run memory:run-ledger` |
| Anchor the agent run ledger hash chain | `npm run memory:anchor-ledger` |
| Back up local runtime memory state | `npm run memory:backup` |
| Strictly restore-check the latest runtime bundle | `npm run memory:restore-check` |
| Dry-run/repair the event mirror | `npm run agent:control -- memory repair-event-mirror --json` / add `--apply` after backup and review |
| Run full memory integrity/backup/eval checks | `npm run memory:doctor` |
| Run self-logging memory maintenance | `npm run memory:maintenance` |
| Run memory maintenance only when needed | `npm run memory:auto-maintenance` |
| Read the daily operator brief | `npm run memory:daily-brief` |
| Run deterministic agent eval checks | `npm run memory:agent-eval` |
| Group repeated agent blockers | `npm run memory:blocker-autopsy` |
| Review local pending attention items | `npm run memory:inbox` |
| Review research-only provenance priorities | `npm run memory:research-priorities` |
| Sync allowlisted profitability readbacks into research-only memory | `npm run memory:profit-learning-sync` |
| Audit the profit-learning memory sync | `npm run memory:profit-learning-audit` |
| Register the nightly Windows dreaming task | `npm run memory:schedule-dreams` |
| Register the Windows memory auto-maintenance task | `npm run memory:schedule-maintenance` |
| Audit memory lifecycle health | `npm run memory:audit` |
| Backfill authority metadata on legacy operating memory rows | `npm run memory:repair-authority` |
| Run deterministic memory recovery checks | `npm run memory:eval` or `npm run verify:memory` |

Do not use raw `graph remember` for accepted operating memory. `graph remember` is create-only, reserves operating-memory IDs, and stores raw graph context only; durable reviewed memory goes through `memory remember`, accepted task writeback, or accepted dreams. Query output always forces the nonauthorization contract, and unsafe raw node or edge metadata is quarantined rather than surfaced as capability.

## Memory Graph V2 Guardrails

The runtime graph uses a shared policy contract, `memory_graph_v2_2026_06_28`, on accepted operating memory, dream promotion, retrieval documents, context manifests, operator-dashboard output, and research provenance.

Every accepted memory is stamped with:

- `authority_scope=orchestration_only`
- `does_not_authorize_trading_or_evidence_mutation=true`
- `capability_label=coordination_only`
- `source_quality=<source class>`
- `memory_policy_version=memory_graph_v2_2026_06_28`

The write paths reject memory or dream entries that try to approve live trading, broker action, evidence mutation, scanner/strategy changes, proof-bar changes, promotion, stop/sizing changes, append readiness, or treating historical rows as forward proof. They also reject narrowly recognized executable order imperatives and real token/private-key shapes, while allowing ordinary technical prose and redacted placeholders. Session capture refuses environment/auth/tool config, `.npmrc`, `.netrc`, `.aws`, `.ssh`, private-key, browser-cookie/login/profile, database, and generated trading/evidence paths. This is intentionally stricter than ordinary graph notes: accepted memory can improve coordination and retrieval, but it cannot become an authority surface for options actions.

Graph queries index nodes into `retrieval_documents` and use SQLite FTS/BM25 before the older substring fallback. Every graph body/metadata mutation reindexes in the same transaction, and `memory audit` checks graph/retrieval content and metadata parity. `--fresh-only` excludes stale or missing documents in both retrieval paths. Freshness reads must resolve inside the repo and pass memory-safe path guards; outside or protected paths are classified missing, never read. The audit always unions the canonical code-owned `PROJECT_SEED_FILES` set with durable expectation rows, so deleting an expectation or graph node cannot hide a required seed. Tier-3 repo mirrors remain explicitly classified, nonfatal diagnostics. Retrieval and graph output force nonauthorization, recursively quarantine prohibited node and edge action flags, and expose counts instead of unsafe values. Prompt-ready graph context includes the policy banner plus retrieval explanations with `source_quality`, `authority_scope`, `capability_label`, `freshness_status`, and source hash metadata. Focused context packs write manifests under `data/agent-control/context-packs/`, pathway-filter accepted dream lessons, and exclude repo-index hits unless `context pack --include-repo-index` is explicitly supplied.

Living-history class expectations are code-stable: WORKLOG headings activate `episode` nodes and DECISIONS headings activate `decision` nodes. Expectation activation is recorded as a hash-chained control-plane event, so mutable rows cannot silently change the class contract. Ghost graph nodes, retrieval documents, and expectations are removed in one transaction or not at all.

`npm run memory:operator-dashboard` is the no-management audit view. It checks memory lifecycle health, automated dreaming, startup/context manifest presence, retrieval index counts, event outbox hash-chain activity, and deterministic memory eval status. `npm run memory:research-priorities` reads research-only provenance, including zero-candidate episodes, to help select the next diagnostic task without changing scanners, evidence stores, proof gates, live validation, broker behavior, or append state.

`npm run memory:profit-learning-sync` is the options-profitability learning intake. It reads only the allowlisted generated readbacks from `data/forward-tracking/` and `data/profitability-lab/`, then writes research-only provenance rows into `data/agent-control/agent_control.db`. It records source hashes, generated timestamps, denominator context, zero-candidate episodes, diagnostic hypotheses, and experiment readbacks for future agents. It strips or sanitizes action-authority-shaped metric/status fields, requires valid generated timestamps, uses tenant-prefixed semantic IDs, rejects cross-tenant ID overwrites, and requires the explicit `APPROVE_PROFIT_LEARNING_MEMORY_SYNC` token in the package alias. It does not append cohort rows, import quotes, mutate evidence stores, change scanners/strategies/proof bars, open broker/live paths, consume holdout, or promote lanes.

The agent run ledger is the local observability layer for autonomous work. `npm run memory:run-ledger` audits the tenant-scoped run-event hash chain and summarizes recent runs. `npm run memory:anchor-ledger` writes a local hash anchor, and `npm run memory:backup` writes a relocatable manifest-v2 bundle with relative members.

Schema-v5 restore requires every expected member to be declared present, exact equality between manifest and requested tenant, and exact parity between DB session IDs and `sessions.jsonl`. Current event-outbox rows use canonical hash v2, binding SQL identity, tenant, timestamp, type, and payload; the active mirror must match full rows in canonical DB order. Declared older bundles without v2 columns remain auditable through the legacy-v1 compatibility path, but arbitrary legacy rows in an active mirror are quarantined. Schema migration, WAL setup/retry, event writes, mirror repair, and snapshot backup share the per-DB ownership-token lock, so they serialize instead of racing.

`memory repair-event-mirror` dry-runs by default; `--apply` archives the original with a unique name, rebuilds from the validated DB outbox, and verifies the replacement. Write a fresh ledger anchor and backup after an applied repair. Non-default DBs derive sibling mirrors and locks instead of touching live defaults. `npm run memory:doctor` runs ledger, anchor, outbox, active mirror, session, lifecycle, freshness, dashboard, eval, and latest-backup restore checks together. `npm run memory:maintenance` self-logs, backs up, runs doctor, anchors, and re-runs doctor. `npm run memory:auto-maintenance` checks successful-maintenance age, backup freshness, anchor status, and doctor status before skipping or running maintenance; `npm run memory:schedule-maintenance` only schedules that guard. Lock liveness uses a Windows-safe PID probe, permission failures are controlled errors, and a process unlinks only its own ownership token. `npm run memory:daily-brief`, `memory:agent-eval`, `memory:blocker-autopsy`, and `memory:inbox` retain their observability-only roles.

Approval notes in the ledger, daily brief, and inbox are not authorization. A recorded approval note is only local orchestration context; it does not approve cohort append, evidence mutation, quote import, scanner/strategy changes, proof-bar changes, live validation, auto-track, broker action, stop/sizing changes, promotion, protected-holdout use, or treating historical rows as forward proof.

The frozen schema-v5 code passed 119 agent-control tests plus 17 memory-graph tests, 136 total, and the Prime reproduced both suites from the repo root. Live migration, session and transactional ghost repair, final living-history ingest/bootstrap, doctor, audit, retrieval, operator-dashboard, eval, outbox/mirror/anchor checks, backup restore, and dream audit are green. Preserve `post-v4-safety/20260710T035321Z-e254fd94`, `pre-v5-safety/20260710T035321Z-e254fd94-repaired-sessions`, `verified-v5-safety/20260710T063210Z-ac899ea5`, and pre-ghost-repair bundle `backups/20260710T141639Z-ed16ac30`; the last passed restore-check. Maintenance `RUN-20260710-c1aae9a5` passed and latest options dream `DREAMRUN-20260710-d64378a5` completed. Machine-wide manual sequence 2 `PMDREAM-20260710-150315388-4dc9366af849` and scheduled sequence 3 `PMDREAM-20260710-150505551-ddd8389b9bee` completed under canonical audit-contract SHA-256 `eb867cc4f8641f5a5085e059f9c6c15c84ade2e4894361bae23e1d53581da0d9`. See `docs/memory-graph-v5-upgrade-audit-2026-07-10.md` and `docs/NEXT_STEPS.md`.

One nonblocking scalability follow-up remains: cache each shared living-history source snapshot once during refresh instead of rereading its bytes for every referencing node. The current path can approach `O(nodes x source-read)` CPU, but scheduled maintenance still finishes in about six minutes within its 30-minute limit.

Audit that intake with:

```powershell
npm run memory:profit-learning-audit
```

Use the raw dry-run when you want to inspect proposed records without writing:

```powershell
npm run agent:control -- memory profit-learning-sync --prompt-only
```

## Design Model

The local model copies the useful parts of HydraDB's public architecture without depending on HydraDB credentials or network calls. HydraDB separates Memories from Knowledge, scopes data by tenant/sub-tenant, enriches retrieval through metadata filters and graph context, and models graph context as directional triplets. See:

- https://docs.hydradb.com/get-started/v2/core-concepts
- https://docs.hydradb.com/essentials/v2/architecture
- https://docs.hydradb.com/essentials/v2/context-graphs
- https://docs.hydradb.com/essentials/v2/semantic-search

Local mapping:

| Hydra-style concept | Local control-plane concept |
| --- | --- |
| Tenant | Default `options-chatbot` workspace scope |
| Sub-tenant | Pathway, worker, project, or focused sprint scope |
| Memory | Dynamic operator/session facts, preferences, lessons learned |
| Knowledge | Shared docs, runbooks, reports, or artifact summaries |
| Context graph | SQLite `graph_nodes` and `graph_edges` triplets |
| Hybrid retrieval | SQLite `retrieval_documents` FTS/BM25, metadata filters, explanations, and graph-neighborhood expansion |
| Graph context | Returned nodes, edges, and `source -> relation -> target` triplets |

Future embedding/vector retrieval can be added behind the query command, but the first slice is deliberately deterministic and local.

## Repo-Wide Seed Layer

The runtime graph can seed a repo-wide current-workspace context layer from checked artifacts, visible tracked and untracked files, and current readbacks:

- startup and living docs: `AGENTS.md`, `README.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`
- runtime-memory docs: `docs/agent-control-plane.md`, `docs/agent-memory-graph.md`, `data/contracts/agent-memory-graph.json`
- gateboard artifacts: one coherent byte snapshot of `docs/project-operator-gateboard.md` and `data/forward-tracking/project_operator_gateboard_latest.json`, plus source artifacts declared by that snapshot
- package scripts: `package.json`
- visible repo text files from `git ls-files --cached --others --exclude-standard`, capped by file count, byte size, excerpt length, and memory-safe path filters

The seed creates deterministic graph nodes instead of copying hidden state into source control:

- `knowledge:<path>` for checked docs/manifests, with path, source type, authority, line count, and content hash metadata
- `repo_file:<path>` for each indexed visible repo file, with `source_type=repo_file_index`, category, extension, `git_state=tracked|untracked`, content hash, line count, byte size, and truncation metadata. Repo-file indexing refuses obvious secrets, credential files, databases, ignored runtime control-plane state, and high-risk generated evidence/data paths.
- `static:<id>` for nodes from the generated static memory graph
- `knowledge:gateboard:latest`, `entity:gateboard:pathway:*`, `blocker:gateboard:*`, and `evidence_artifact:gateboard:*` for the current gateboard, no-chase blockers, pathway statuses, and source artifacts. All derived nodes bind to the same gateboard byte hash. Safe artifacts declared `available=true` are validated and hashed during seed as immutable snapshot provenance; `available=false` remains an explicit unavailable declaration, is not dereferenced as present, and cannot satisfy an available-source expectation.

Each seed refresh transactionally prunes prior seed-owned current-state nodes for static graph nodes, gateboard pathway/blocker/source-artifact nodes, `repo_file_index` nodes, retrieval mirrors, and stale expectations before reseeding them. A failure rolls back the whole ghost cleanup. That keeps graph queries aligned with one coherent visible workspace/gateboard snapshot instead of returning removed files or cleared blockers.

Seed the local graph:

```powershell
npm run agent:control -- seed project --json
```

For the normal CEO startup handoff, use the one-command bootstrap. It seeds the graph, returns the runtime digest, and includes a compact `prompt_context` for current gateboard blockers:

```powershell
npm run agent:control -- bootstrap --json
```

For the lowest-noise handoff into a fresh context window, print only the prompt-ready context:

```powershell
npm run agent:control -- bootstrap --prompt-only
```

Record a CEO session checkpoint whenever the objective, scope, current status, or next actions change:

```powershell
npm run agent:control -- checkpoint write `
  --objective "Build repo-wide HydraDB-like memory graph" `
  --scope "options-chatbot repo-wide local runtime graph" `
  --status in_progress `
  --autonomy-level read_only_workers `
  --summary "Seed and bootstrap are complete; checkpoint recovery is next." `
  --success-criteria "Future context can recover objective and next actions." `
  --constraint "No trading store mutation." `
  --next-action "Continue end-to-end verification." `
  --verification "npm run verify:agent-control" `
  --prompt-only
```

Read the latest checkpoint without reseeding:

```powershell
npm run agent:control -- checkpoint latest --prompt-only
```

Query by text plus metadata and emit prompt-ready context:

```powershell
npm run agent:control -- graph query "gateboard" `
  --metadata source_type=gateboard_blocker `
  --max-depth 1 `
  --context `
  --json
```

Or print only the prompt-ready query context:

```powershell
npm run agent:control -- graph query "gateboard" `
  --metadata source_type=gateboard_blocker `
  --max-depth 1 `
  --prompt-only
```

Recover indexed code/docs by file meaning, category, and git state:

```powershell
npm run agent:control -- graph query "agent control checkpoint bootstrap" `
  --metadata source_type=repo_file_index `
  --max-depth 0 `
  --context `
  --json
```

Use this after startup docs and the CEO startup digest, then paste or read the `prompt_context` field when a future context window needs the current graph state quickly. Seeded runtime data is still ignored local state under `data/agent-control/`; it does not replace living docs, generated readbacks, or the gateboard.

## Operating Memory Layer

The operating-memory layer is the durable part of the runtime graph. Raw task reports, task nodes, seeded repo files, and gateboard readbacks stay queryable as orchestration artifacts, but only accepted memory uses `source_type=operating_memory`.

Typed operating memory:

- `objective`
- `constraint`
- `decision`
- `blocker`
- `verification`
- `artifact`
- `worker_report`
- `lesson`
- `open_question`
- `superseded_fact`

Each operating memory carries `memory_type`, `memory_status`, `confidence`, `recorded_at`, `authority_scope=orchestration_only`, `does_not_authorize_trading_or_evidence_mutation=true`, optional `freshness_days`, optional `expires_at`, and optional supersession metadata. Valid memory statuses are `active`, `resolved`, `superseded`, `expired`, and `archived`. Valid confidence values are `accepted`, `observed`, `inferred`, and `unknown`.

Manual `memory remember` defaults to `confidence=inferred`; use `confidence=accepted` only when the caller is intentionally recording reviewed operator memory. Generic `graph remember` cannot create or replace `source_type=operating_memory` nodes and is create-only by default. Typed operating memory must go through `memory remember`, accepted worker-report writeback, or accepted dream entries so future context packs do not confuse raw graph notes with reviewed memory.

When the CEO accepts a task that has worker reports, `task accept` writes back the latest submitted report as accepted operating memory:

- `memory:worker_report:<task_id>:<report_id>` for the accepted finding
- `memory:verification:<task_id>:<report_id>` when verification text exists
- `memory:blocker:<task_id>:<report_id>` when blocker text exists
- `memory:artifact:<task_id>:<report_id>:<n>` for reported artifacts
- edges from the accepting decision to the raw report and accepted worker-report memory, from the accepted worker-report memory to the raw report and task, from verification and artifact memories through the accepted worker report, and direct `verifies` / `documents` links from verification and artifact memories back to the task

This is a review gate, not a trading gate. Accepting a worker report records that the CEO integrated the context; it does not prove profitability, authorize evidence mutation, open a broker path, or promote a lane. `task accept` requires `reported` state, so an open or merely claimed task cannot fabricate an acceptance decision without a reviewed report. Schema v5 retains tenant identity on tasks and downstream claim/report/run/decision rows, derives every related graph node and edge from the task tenant, rejects cross-tenant edges, and tenant-filters task lists, checkpoints, context packs, digests, and audits. A report requires the current active claim-owner label; labels are audit context, not identity authentication. Reporting closes the active claim and worker run, and terminal transitions close any remaining activity. Guarded status updates roll back stale concurrent writers instead of regressing state.

`proof_gate_status` is orchestration context only and must be one of `not_applicable`, `not_applicable_observe_only`, `observe_only`, `pass`, `passed`, `blocked`, or `failed`. No value grants trading authority.

The agent-facing shortcut for accepting a reviewed worker report is:

```powershell
npm run memory:writeback -- T-20260614-abcdef12 --summary "Accepted after review."
```

Store a manual typed memory:

```powershell
npm run agent:control -- memory remember `
  --type lesson `
  --title "Bootstrap first" `
  --body "Future CEO windows should run bootstrap before graph queries." `
  --confidence inferred `
  --freshness-days 30 `
  --json
```

Supersede stale memory instead of deleting it:

```powershell
npm run agent:control -- memory supersede `
  --old memory:lesson:old `
  --new memory:lesson:new `
  --reason "Replaced by the accepted checkpoint workflow." `
  --json
```

Typed graph search hides inactive, superseded, and expired operating memory by default:

```powershell
npm run agent:control -- graph query "bootstrap first" `
  --memory-type lesson `
  --max-depth 1 `
  --context `
  --json
```

Use `--include-inactive` when auditing history and `--fresh-only` when the prompt should exclude stale accepted memory.

Build a focused prompt pack for a future context window:

```powershell
npm run agent:control -- context pack `
  --goal "continue operating memory work" `
  --pathway operator `
  --prompt-only
```

The pack keeps accepted operating memory and accepted dream lessons pathway-scoped when `--pathway` is provided, but always includes current fail-closed gateboard blockers from every pathway so an operator-scoped handoff still sees evidence and promotion blockers.

Add `--include-repo-index` only when the goal needs repo-file discovery. The default intentionally excludes tier-3 file mirrors.

Audit lifecycle health:

```powershell
npm run agent:control -- memory audit --prompt-only
```

The audit exits nonzero on issues. It checks stale/expired active memory, supersession consistency, graph/retrieval parity, canonical `PROJECT_SEED_FILES` plus durable required-source expectations, stable WORKLOG/DECISIONS classes and activation hash chain, coherent gateboard/artifact snapshot provenance, and recursively prohibited legacy node/edge action flags while reporting tier-3 repo gaps separately as nonfatal. Unsafe metadata values remain quarantined from the result.

Run deterministic recovery checks:

```powershell
npm run agent:control -- memory eval --prompt-only
npm run verify:memory
```

The eval verifies current gateboard blocker recovery when blockers exist and treats a seeded clean gateboard with no no-chase reasons as a passing no-blocker state.

## Sessions And Dreaming

The control plane supports an out-of-band self-improvement loop without making dream output authoritative by default.

Session transcript capture records provenance for a local transcript file:

```powershell
npm run agent:control -- session log `
  --transcript data/agent-control/transcripts/2026-06-26-memory-sprint.md `
  --title "Memory sprint" `
  --summary "Implemented runtime memory graph dreaming." `
  --expected-sha256 "<sha256>" `
  --json
```

The command records a `session:<id>` episode node and a durable session-sidecar outbox record before appending the compact row to `data/agent-control/sessions.jsonl`. If that append fails, the graph/event commit remains durable and the same ID/hash retry reconciles the sidecar idempotently without duplicating `session.logged`. It refuses obvious secret, database, generated evidence, broker, and high-risk data paths. The SHA-256 guard is optimistic provenance: if `--expected-sha256` is supplied and the source file changed, the write fails and the caller must reread before logging.

Dreaming is a reviewable proposal workflow:

```powershell
npm run agent:control -- dream propose `
  --file data/agent-control/dreams/2026-06-26-nightly.json `
  --expected-sha256 "<sha256>" `
  --json

npm run agent:control -- dream accept DREAM-20260626-abcdef12 --accepted-by CEO --json
npm run agent:control -- dream reject DREAM-20260626-abcdef12 --reason "Weak evidence." --json
npm run agent:control -- dream list --json
npm run memory:review-dreams
```

Automated dreaming is the default low-maintenance loop:

```powershell
npm run memory:dream-run
npm run memory:dream-audit
npm run memory:schedule-dreams
```

`memory:dream-run` does three bounded things:

- scans unprocessed `session_transcript` graph nodes and their transcript files for explicit `Lesson:`, `Constraint:`, and `Open question:` lines
- creates an auto dream proposal from those explicit lines only
- auto-accepts or auto-rejects proposed dreams under `auto_dream_v1`

The auto policy accepts only session-transcript-graph-evidence-backed `lesson`, `constraint`, and `open_question` entries with inferred/unknown confidence, no supersession, and no high-risk options-action wording. Evidence refs must be non-empty graph node IDs for existing same-tenant `session_transcript` nodes, and a dream cannot cite itself as evidence. It rejects decisions, blockers, superseded facts, observed-confidence claims, entries without real session evidence, fabricated evidence refs, supersession attempts, and anything that appears to approve or authorize trading, broker paths/orders, live validation, evidence-store mutation, quote import, auto-track, scanner policy changes, proof-bar changes, promotion, stop/sizing changes, or protected-holdout use. If a session transcript source is unreadable or its current hash differs from capture, the run records an explicit skip and does not mark that session as processed, so a corrected source remains retryable.

Every automated run writes:

- `data/agent-control/dream-runs/latest.json`
- `data/agent-control/dream-runs/latest.md`
- `data/agent-control/dream-runs/scheduler.log` when run from Task Scheduler
- a `dream_run:<id>` graph node
- a `dream.auto_run` event

Windows task `\OptionsMemoryDreaming` has a 45-minute execution limit instead of 20 minutes. An observed scheduled run completed as `DREAMRUN-20260710-d64378a5`, dream audit passed, and the task reports `LastTaskResult=0`. `\ProjectsMemoryDreaming` and `\OptionsMemoryMaintenance` also report `LastTaskResult=0`.

Audit the loop with `npm run memory:dream-audit`. Use `npm run memory:review-dreams` when you want to inspect accepted/rejected dream state in prompt-ready form.

Dream proposal JSON contains a title, summary, optional evidence, and entries with `type`, `title`, `body`, optional `confidence`, optional `evidence`, optional `supersedes`, optional `freshness_days`, and optional review-routing fields: `target_project`, `pathway`, `intended_consumer`, `promotion_target`, `review_question`, `acceptance_criteria`, `reject_if`, and `retrieval_keywords`. Proposals must contain at least one entry and reject duplicate `(type, id)` entries. Acceptance reparses and rehashes the source, requires stored entries and their digest to match that source, and never trusts a mutated proposal node. Session IDs are immutable: the same ID/hash is idempotent, while changed content is rejected. Accepted entries flow through the existing operating-memory path as `origin=dreaming`, `proposal_origin=dream`, `accepted_by`, `accepted_at`, `source_sha256`, `non_authoritative=true`, and `does_not_authorize_trading_or_evidence_mutation=true`. Dream entries default to `confidence=inferred`; manual `confidence=observed` requires same-tenant reviewed, provenanced, integrity-bearing evidence whose kind is `episode` or `evidence_artifact` and whose source class is allowlisted. Arbitrary metadata cannot mint that trust: only a trusted writer can set the reserved attestation, and acceptance cross-checks it against the durable session/outbox record or the authoritative artifact source and hash.

Dream proposal parsing accepts PowerShell-created UTF-8 BOM JSON and rejects malformed JSON with a controlled `agent_control:` error instead of a traceback.

Dream acceptance is a memory review gate only. It does not prove profitability, approve evidence mutation, change scanner policy, promote lanes, open broker-paper or live-capital paths, or override living docs, generated readbacks, gateboard state, exact OPRA/NBBO evidence, or code. Reject stale or weak dream proposals instead of letting speculative context accumulate.

Computer-wide memory lives at `C:\Users\kalec\projects-memory`. That directory is an index, schema, transcript/dream catalog, and project pointer layer for tools across the machine. For options facts, `data/agent-control/agent_control.db`, living docs, generated readbacks, and repo code remain authoritative.

## CEO Workflow

The CEO session owns integration. Worker terminals are allowed when the CEO judges the task large enough to benefit from them; the user does not need to approve each terminal.

Before spawning workers:

1. Read startup docs and the gateboard.
2. Run the CEO startup digest.
3. Write a scoped sprint plan with goal, non-goals, success criteria, risks, worker roster, task order, allowed commands, verification, and stop conditions.
4. Create one control-plane task per worker pathway.

Worker pathways:

- `data`
- `candidate`
- `evidence`
- `profitability`
- `promotion`
- `operator`
- `general`

Each worker gets one pathway, one command allowance, hard prohibitions, and the standard report format:

```text
Role:
Task:
Files/artifacts read:
Commands run:
Artifacts written:
Finding:
Proof/gate status:
Recommendation:
Verification:
Blockers:
```

The CEO integrates reports, accepts reported tasks, creates a new scoped follow-up task when more work is needed, and stops worker terminals after their task is integrated unless a terminal is hosting an explicitly needed long-running service.

## Fail-Closed Permissions

Task permission modes:

- `context_only`
- `read_only_workers`
- `code_docs`
- `evidence_mutation`
- `broker_paper_discussion`
- `live_capital_discussion`

The high-risk modes require `--ack-high-risk` when creating a task. That acknowledgement only records intent in the control plane. It does not authorize broker orders, evidence-store mutation, scanner policy changes, stop/sizing changes, proof-bar changes, or live-capital actions.

An agreed CEO goal grants local implementation authority for `code_docs`; evidence and trading gates constrain only their dependent evidence mutation, promotion, broker, or live-capital actions. Memory eval therefore treats `context_only`, `read_only_workers`, and `code_docs` as trading-fail-closed. `evidence_mutation`, `broker_paper_discussion`, and `live_capital_discussion` fail that check. Memory never grants trading authority.

## Commands

Create a read-only worker task:

```powershell
uv run --locked python scripts/agent_control.py task create `
  --title "Refresh open-risk readback" `
  --pathway evidence `
  --permission-mode read_only_workers `
  --json
```

Claim a task:

```powershell
uv run --locked python scripts/agent_control.py task claim T-20260614-abcdef12 `
  --worker-id evidence-steward `
  --json
```

Report back:

```powershell
uv run --locked python scripts/agent_control.py task report T-20260614-abcdef12 `
  --worker-id evidence-steward `
  --finding "QQQ id 537 remains the open-risk blocker." `
  --proof-gate-status blocked `
  --recommendation "Stay observe-only until a valid market-data window." `
  --verification "Read gateboard and open-risk plan." `
  --json
```

Accept a task:

```powershell
uv run --locked python scripts/agent_control.py task accept T-20260614-abcdef12 `
  --accepted-by CEO `
  --summary "Integrated into sprint state." `
  --json
```

Remember a runtime graph node:

```powershell
uv run --locked python scripts/agent_control.py graph remember `
  --kind blocker `
  --node-id blocker:qqq-537-open-risk `
  --title "QQQ id 537 open-risk blocker" `
  --body "Needs fresh executable exact review during a valid market-data window." `
  --sub-tenant-id evidence `
  --json
```

Link graph context:

```powershell
uv run --locked python scripts/agent_control.py graph link `
  --source blocker:qqq-537-open-risk `
  --relation requires `
  --target knowledge:open-risk-plan `
  --json
```

Query graph context:

```powershell
uv run --locked python scripts/agent_control.py graph query "QQQ open risk" `
  --sub-tenant-id evidence `
  --max-depth 2 `
  --json
```

Digest:

```powershell
uv run --locked python scripts/agent_control.py digest --json
```

## Boundaries

The control plane is local runtime memory and orchestration state only.

It must not:

- replace checked living docs or generated readbacks
- mutate trading/evidence stores
- create, submit, or close broker orders
- change scanner policy, proof bars, stops, sizing, lane promotion, or holdout policy
- treat task status as proof or release approval
- treat graph memories as more authoritative than code, living docs, current gateboard readbacks, or exact evidence artifacts

Use it to coordinate work, recover context after compaction, and preserve worker reports in a queryable graph.
