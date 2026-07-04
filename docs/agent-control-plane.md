# Agent Control Plane

This document owns the local CEO/worker control-plane workflow and the first runtime memory graph. It does not replace `docs/agent-memory-graph.md`; that file is generated, static navigation metadata with `runtime_use=false`.

The runtime implementation is `scripts/agent_control.py`. It stores local operator memory under ignored `data/agent-control/` by default:

- `agent_control.db`: SQLite task/message/graph ledger using WAL mode
- `events.jsonl`: append-only event mirror for agent-readable audit trails
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

Do not use raw `graph remember` for accepted operating memory. `graph remember` stores raw graph context only; durable reviewed memory goes through `memory remember`, accepted task writeback, or accepted dreams.

## Memory Graph V2 Guardrails

The runtime graph uses a shared policy contract, `memory_graph_v2_2026_06_28`, on accepted operating memory, dream promotion, retrieval documents, context manifests, operator-dashboard output, and research provenance.

Every accepted memory is stamped with:

- `authority_scope=orchestration_only`
- `does_not_authorize_trading_or_evidence_mutation=true`
- `capability_label=coordination_only`
- `source_quality=<source class>`
- `memory_policy_version=memory_graph_v2_2026_06_28`

The write paths reject memory or dream entries that try to approve live trading, broker action, evidence mutation, scanner/strategy changes, proof-bar changes, promotion, stop/sizing changes, append readiness, or treating historical rows as forward proof. This is intentionally stricter than ordinary graph notes: accepted memory can improve coordination and retrieval, but it cannot become an authority surface for options actions.

Graph queries index nodes into `retrieval_documents` and use SQLite FTS/BM25 before the older substring fallback. Prompt-ready graph context includes the non-authorization banner plus retrieval explanations with `source_quality`, `authority_scope`, `capability_label`, `freshness_status`, and source hash metadata. Focused context packs write manifests under `data/agent-control/context-packs/` so future agents can audit exactly which nodes were loaded.

`npm run memory:operator-dashboard` is the no-management audit view. It checks memory lifecycle health, automated dreaming, startup/context manifest presence, retrieval index counts, event outbox hash-chain activity, and deterministic memory eval status. `npm run memory:research-priorities` reads research-only provenance, including zero-candidate episodes, to help select the next diagnostic task without changing scanners, evidence stores, proof gates, live validation, broker behavior, or append state.

`npm run memory:profit-learning-sync` is the options-profitability learning intake. It reads only the allowlisted generated readbacks from `data/forward-tracking/` and `data/profitability-lab/`, then writes research-only provenance rows into `data/agent-control/agent_control.db`. It records source hashes, generated timestamps, denominator context, zero-candidate episodes, diagnostic hypotheses, and experiment readbacks for future agents. It strips or sanitizes action-authority-shaped metric/status fields, requires valid generated timestamps, uses tenant-prefixed semantic IDs, rejects cross-tenant ID overwrites, and requires the explicit `APPROVE_PROFIT_LEARNING_MEMORY_SYNC` token in the package alias. It does not append cohort rows, import quotes, mutate evidence stores, change scanners/strategies/proof bars, open broker/live paths, consume holdout, or promote lanes.

The agent run ledger is the local observability layer for autonomous work. `npm run memory:run-ledger` audits the tenant-scoped run-event hash chain and summarizes recent runs. `npm run memory:anchor-ledger` writes a local hash anchor for the current run ledger, `npm run memory:backup` copies the ignored memory DB and JSONL sidecars with a hashed manifest, and `npm run memory:doctor` runs ledger, anchor, outbox, lifecycle, dashboard, eval, and latest-backup restore checks together. `npm run memory:maintenance` records its own run-ledger start/completion or failure events, creates a backup, runs doctor, writes a final maintenance anchor, and re-runs doctor so routine memory-health work leaves auditable history while keeping the anchor current. `npm run memory:auto-maintenance` is the live local memory guard: it checks latest successful maintenance age, backup freshness, anchor status, and doctor status, then either skips cleanly or runs `memory:maintenance`. `npm run memory:schedule-maintenance` registers the Windows task that calls the auto-maintenance guard repeatedly; the guard does the necessity check, not the scheduler. The control-plane file lock uses a non-destructive Windows process probe; do not reintroduce `os.kill(pid, 0)` as a Windows liveness check because it can terminate the probed process. `npm run memory:daily-brief` combines the ledger, operator dashboard, and research-priority report into one prompt-ready daily handoff. `npm run memory:agent-eval` runs the existing memory eval plus temp-backed self-tests for ledger redaction, blocked-run surfacing, and non-authoritative approval notes. `npm run memory:blocker-autopsy` groups repeated blocked/failed run reasons, and `npm run memory:inbox` shows pending approval notes, blockers/failures, and stale running runs.

Approval notes in the ledger, daily brief, and inbox are not authorization. A recorded approval note is only local orchestration context; it does not approve cohort append, evidence mutation, quote import, scanner/strategy changes, proof-bar changes, live validation, auto-track, broker action, stop/sizing changes, promotion, protected-holdout use, or treating historical rows as forward proof.

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
- gateboard artifacts: `docs/project-operator-gateboard.md`, `data/forward-tracking/project_operator_gateboard_latest.json`
- package scripts: `package.json`
- visible repo text files from `git ls-files --cached --others --exclude-standard`, capped by file count, byte size, excerpt length, and memory-safe path filters

The seed creates deterministic graph nodes instead of copying hidden state into source control:

- `knowledge:<path>` for checked docs/manifests, with path, source type, authority, line count, and content hash metadata
- `repo_file:<path>` for each indexed visible repo file, with `source_type=repo_file_index`, category, extension, `git_state=tracked|untracked`, content hash, line count, byte size, and truncation metadata. Repo-file indexing refuses obvious secrets, credential files, databases, ignored runtime control-plane state, and high-risk generated evidence/data paths.
- `static:<id>` for nodes from the generated static memory graph
- `knowledge:gateboard:latest`, `entity:gateboard:pathway:*`, `blocker:gateboard:*`, and `evidence_artifact:gateboard:*` for the current gateboard, no-chase blockers, pathway statuses, and source artifacts

Each seed refresh prunes prior seed-owned current-state nodes for static graph nodes, gateboard pathway/blocker/source-artifact nodes, and `repo_file_index` nodes before reseeding them. That keeps graph queries aligned with the current visible workspace and current gateboard instead of returning removed files or cleared blockers.

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

Manual `memory remember` defaults to `confidence=inferred`; use `confidence=accepted` only when the caller is intentionally recording reviewed operator memory. Generic `graph remember` cannot create `source_type=operating_memory` nodes. Typed operating memory must go through `memory remember`, accepted worker-report writeback, or accepted dream entries so future context packs do not confuse raw graph notes with reviewed memory.

When the CEO accepts a task that has worker reports, `task accept` writes back the latest submitted report as accepted operating memory:

- `memory:worker_report:<task_id>:<report_id>` for the accepted finding
- `memory:verification:<task_id>:<report_id>` when verification text exists
- `memory:blocker:<task_id>:<report_id>` when blocker text exists
- `memory:artifact:<task_id>:<report_id>:<n>` for reported artifacts
- edges from the accepting decision to the raw report and accepted worker-report memory, from the accepted worker-report memory to the raw report and task, from verification and artifact memories through the accepted worker report, and direct `verifies` / `documents` links from verification and artifact memories back to the task

This is a review gate, not a trading gate. Accepting a worker report records that the CEO integrated the context; it does not prove profitability, authorize evidence mutation, open a broker path, or promote a lane. Task lifecycle transitions use guarded status updates: `claim`, `report`, and `accept` update only if the task is still in an allowed source state, and stale concurrent writers roll back instead of regressing terminal state. After a task reaches `accepted`, `blocked`, or `cancelled`, late `task report` submissions are rejected so terminal task state cannot regress.

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

The pack keeps accepted operating memory pathway-scoped when `--pathway` is provided, but always includes current fail-closed gateboard blockers from every pathway so an operator-scoped handoff still sees evidence and promotion blockers.

Audit lifecycle health:

```powershell
npm run agent:control -- memory audit --prompt-only
```

The audit checks stale or expired active memory and supersession consistency. A superseded memory must point at an existing operating-memory target through `superseded_by`, and the superseding node must carry the matching `supersedes` edge.

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

The command records a `session:<id>` episode node and appends a compact row to `data/agent-control/sessions.jsonl`. It refuses obvious secret, database, generated evidence, broker, and high-risk data paths. The SHA-256 guard is optimistic provenance: if `--expected-sha256` is supplied and the source file changed, the write fails and the caller must reread before logging.

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

The auto policy accepts only session-transcript-graph-evidence-backed `lesson`, `constraint`, and `open_question` entries with inferred/unknown confidence, no supersession, and no high-risk options-action wording. Evidence refs must be non-empty graph node IDs for existing same-tenant `session_transcript` nodes, and a dream cannot cite itself as evidence. It rejects decisions, blockers, superseded facts, observed-confidence claims, entries without real session evidence, fabricated evidence refs, supersession attempts, and anything that appears to approve or authorize trading, broker paths/orders, live validation, evidence-store mutation, quote import, auto-track, scanner policy changes, proof-bar changes, promotion, stop/sizing changes, or protected-holdout use. If a session transcript source is unreadable, the run does not mark that session as fully processed.

Every automated run writes:

- `data/agent-control/dream-runs/latest.json`
- `data/agent-control/dream-runs/latest.md`
- `data/agent-control/dream-runs/scheduler.log` when run from Task Scheduler
- a `dream_run:<id>` graph node
- a `dream.auto_run` event

Audit the loop with `npm run memory:dream-audit`. Use `npm run memory:review-dreams` when you want to inspect accepted/rejected dream state in prompt-ready form.

Dream proposal JSON contains a title, summary, optional evidence, and entries with `type`, `title`, `body`, optional `confidence`, optional `evidence`, optional `supersedes`, optional `freshness_days`, and optional review-routing fields: `target_project`, `pathway`, `intended_consumer`, `promotion_target`, `review_question`, `acceptance_criteria`, `reject_if`, and `retrieval_keywords`. Proposals must contain at least one entry, and duplicate `(type, id)` entries are rejected. Accepted entries flow through the existing operating-memory path as `origin=dreaming`, `proposal_origin=dream`, `accepted_by`, `accepted_at`, `source_sha256`, `non_authoritative=true`, and `does_not_authorize_trading_or_evidence_mutation=true`. Dream entries default to `confidence=inferred`; `confidence=observed` is accepted only when the entry carries evidence.

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

The CEO integrates reports, accepts or reopens tasks, and stops worker terminals after their task is integrated unless a terminal is hosting an explicitly needed long-running service.

## Fail-Closed Permissions

Task permission modes:

- `context_only`
- `read_only_workers`
- `code_docs`
- `evidence_mutation`
- `broker_paper_discussion`
- `live_capital_discussion`

The high-risk modes require `--ack-high-risk` when creating a task. That acknowledgement only records intent in the control plane. It does not authorize broker orders, evidence-store mutation, scanner policy changes, stop/sizing changes, proof-bar changes, or live-capital actions.

Default autonomy remains `read_only_workers` for options operations unless repo gates and the user-approved release path say otherwise.

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
