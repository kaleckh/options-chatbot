# Agent Control Plane

This document owns the local CEO/worker control-plane workflow and the first runtime memory graph. It does not replace `docs/agent-memory-graph.md`; that file is generated, static navigation metadata with `runtime_use=false`.

The runtime implementation is `scripts/agent_control.py`. It stores local operator memory under ignored `data/agent-control/` by default:

- `agent_control.db`: SQLite task/message/graph ledger using WAL mode
- `events.jsonl`: append-only event mirror for agent-readable audit trails

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
| Hybrid retrieval | Text/metadata query plus graph-neighborhood expansion for now |
| Graph context | Returned nodes, edges, and `source -> relation -> target` triplets |

Future embedding/vector retrieval can be added behind the query command, but the first slice is deliberately deterministic and local.

## Repo-Wide Seed Layer

The runtime graph can seed a repo-wide current-workspace context layer from checked artifacts, visible tracked and untracked files, and current readbacks:

- startup and living docs: `AGENTS.md`, `README.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`
- runtime-memory docs: `docs/agent-control-plane.md`, `docs/agent-memory-graph.md`, `data/contracts/agent-memory-graph.json`
- gateboard artifacts: `docs/project-operator-gateboard.md`, `data/forward-tracking/project_operator_gateboard_latest.json`
- package scripts: `package.json`
- visible repo text files from `git ls-files --cached --others --exclude-standard`, capped by file count, byte size, and excerpt length

The seed creates deterministic graph nodes instead of copying hidden state into source control:

- `knowledge:<path>` for checked docs/manifests, with path, source type, authority, line count, and content hash metadata
- `repo_file:<path>` for each indexed visible repo file, with `source_type=repo_file_index`, category, extension, `git_state=tracked|untracked`, content hash, line count, byte size, and truncation metadata
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
npm run agent:control -- graph query "open risk" `
  --metadata source_type=gateboard_blocker `
  --max-depth 1 `
  --context `
  --json
```

Or print only the prompt-ready query context:

```powershell
npm run agent:control -- graph query "open risk" `
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

Each operating memory carries `memory_type`, `memory_status`, `confidence`, `recorded_at`, optional `freshness_days`, optional `expires_at`, and optional supersession metadata. Valid memory statuses are `active`, `resolved`, `superseded`, `expired`, and `archived`. Valid confidence values are `accepted`, `observed`, `inferred`, and `unknown`.

When the CEO accepts a task that has worker reports, `task accept` writes back the latest submitted report as accepted operating memory:

- `memory:worker_report:<task_id>:<report_id>` for the accepted finding
- `memory:verification:<task_id>:<report_id>` when verification text exists
- `memory:blocker:<task_id>:<report_id>` when blocker text exists
- `memory:artifact:<task_id>:<report_id>:<n>` for reported artifacts
- edges from the accepting decision to the raw report and accepted worker-report memory, from the accepted worker-report memory to the raw report and task, from verification and artifact memories through the accepted worker report, and direct `verifies` / `documents` links from verification and artifact memories back to the task

This is a review gate, not a trading gate. Accepting a worker report records that the CEO integrated the context; it does not prove profitability, authorize evidence mutation, open a broker path, or promote a lane. After a task reaches `accepted`, `blocked`, or `cancelled`, late `task report` submissions are rejected so terminal task state cannot regress.

Store a manual typed memory:

```powershell
npm run agent:control -- memory remember `
  --type lesson `
  --title "Bootstrap first" `
  --body "Future CEO windows should run bootstrap before graph queries." `
  --confidence accepted `
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
```

Dream proposal JSON contains a title, summary, optional evidence, and entries with `type`, `title`, `body`, optional `confidence`, optional `evidence`, optional `supersedes`, and optional `freshness_days`. Accepted entries flow through the existing operating-memory path as `origin=dreaming`, `proposal_origin=dream`, `non_authoritative=true`, and `does_not_authorize_trading_or_evidence_mutation=true`. Dream entries default to `confidence=inferred`; `confidence=observed` is accepted only when the entry carries evidence.

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
