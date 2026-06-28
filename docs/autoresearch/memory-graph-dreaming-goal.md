# End-To-End Memory Graph And Dreaming Prompt

Use this prompt when building, reviewing, testing, or upgrading the machine-wide memory graph and the options-chatbot memory graph. This is the repo-local copy of `C:\Users\kalec\projects-memory\dreams\end-to-end-memory-graph-prompt.md`.

## Goal

Build or upgrade a safe, useful, self-improving memory system end to end:

1. Debate the architecture with bounded subagents.
2. Distill the winning design into a concrete implementation plan.
3. Implement the computer-wide memory graph under `C:\Users\kalec\projects-memory`.
4. Copy/adapt the same operating prompt into this repo.
5. Add repo-local runtime memory, session logging, dreaming, audit, and verification commands.
6. Record lessons learned in memory files so future agents do not repeat the same mistakes.

When the system already exists, run this as an assurance goal instead:

1. Spawn bounded subagents to test each memory-graph layer independently.
2. Fix or explicitly record every real defect, missing guard, stale doc, or ambiguous authority boundary.
3. Run the full verification ladder.
4. Hold a six-subagent final debate.
5. Do not call the system ready unless the debate agrees there are no known unresolved bugs or purpose-fit blockers after reviewing primary evidence.

No review can prove the absence of all possible bugs. The acceptable completion claim is: no known bugs, missing tests, stale-doc conflicts, or purpose-fit blockers remain after the required evidence-backed checks.

## Non-Negotiable Lessons From The First Pass

- Do not confuse infrastructure with the user-facing deliverable. If the user asks for an end-to-end prompt/runbook, create that artifact explicitly.
- The global memory graph is an index and provenance layer, not a second authority source.
- The target repo remains authoritative for its own living docs, code, generated readbacks, tests, and runtime graph.
- For `options-chatbot`, `data\agent-control\agent_control.db` is authoritative for runtime memory.
- Dream output is non-authoritative until accepted through the repo-local review path.
- Accepted dream memories should default to `confidence=inferred`; require concrete evidence before using `observed`.
- Dream-origin memory must be visibly marked with `origin=dreaming`, `proposal_origin=dream`, `non_authoritative=true`, `accepted_by`, `accepted_at`, and `source_sha256`.
- A dream acceptance is a memory-review action only. It must not authorize trading, evidence mutation, broker action, scanner policy changes, proof-bar changes, stop/sizing changes, promotion, live validation, or holdout use.
- Session capture must refuse secrets, credentials, auth files, browser state, private tool DBs, broker/account data, and broad generated trading/evidence stores.
- Hashes are useful only when they guard a write or preserve provenance. If a source changed, reread and re-evaluate before writing.
- Add reject/list/audit paths so stale dream proposals do not accumulate as tempting context. Add archive only if the control-plane implementation documents and verifies it.
- Verify the full loop with tests and a real bootstrap/audit command before calling the task complete.
- Make the memory graph obviously usable by future agents, not just technically present. Startup docs should say when to run bootstrap/context, how to write back reviewed worker reports, when to use `memory remember`, and how to review dreams.
- All operating memory should be machine-labeled as orchestration-only and explicitly not authorization for trading, evidence mutation, broker action, promotion, live validation, scanner policy, proof bars, stop/sizing, or protected holdout.
- Accepted dream lessons and constraints should appear in normal context packs so agents benefit without remembering a special `origin=dreaming` query.
- Provide agent-facing aliases or shortcuts for bootstrap, focused context, audit, eval, dream review, and reviewed report writeback.

## Debate Rounds

Run at least three bounded subagent passes when tools are available:

1. Architecture scout:
   - Inspect the current repo memory/control-plane files.
   - Identify existing graph, memory, transcript, and task primitives.
   - Propose the smallest design that avoids a duplicate system.
2. Safety/concurrency scout:
   - Review hash guards, redaction, authority boundaries, and fail-closed behavior.
   - Identify ways memory could accidentally become proof, approval, or policy.
   - Require tests for the highest-risk failure modes.
3. Global-memory scout:
   - Inspect `C:\Users\kalec\projects-memory`.
   - Propose the machine-wide layout and pointer strategy.
   - Make sure repo-local facts remain authoritative.

After round one, synthesize the design. If any reviewer finds a showstopper, fix the design before implementation.

## Assurance Test Rounds

When validating an existing memory graph, spawn the smallest useful set of independent auditors. Suggested slices:

1. Global filesystem graph auditor:
   - Inspect `C:\Users\kalec\projects-memory`.
   - Run `verify-memory-graph.ps1`.
   - Check schema, node/edge/alias/hash coherence, provenance rows, and authority boundaries.
2. Repo runtime CLI auditor:
   - Inspect `scripts/agent_control.py`, `tests/test_agent_control.py`, `package.json`, and `docs/agent-control-plane.md`.
   - Test bootstrap, focused context packs, graph query, memory audit/eval, reviewed report writeback, session logging, dream review, dream lifecycle, SHA guards, path refusal, and metadata semantics.
3. End-to-end behavior auditor:
   - Run the live operator path: bootstrap -> dream list -> dream-origin graph query -> hash-guarded session ingest -> session graph query -> memory audit.
   - Use a unique session ID and report any ignored runtime state it creates.
4. Documentation/source-of-truth auditor:
   - Check `AGENTS.md`, this prompt, the global prompt, docs index, project context, decisions, next steps, worklog, and control-plane docs.
   - Confirm the docs distinguish global pointer memory from repo-local authority.
5. Fail-closed safety auditor:
   - Verify memory, dreams, and sessions cannot authorize trading, evidence mutation, scanner policy changes, proof-bar changes, broker action, promotion, live validation, stop/sizing changes, or protected-holdout use.
   - Check that dream-origin memory is visibly non-authoritative.

Each auditor must report files read, commands run, findings, bugs/gaps, and a purpose-fit verdict. Worker reports are leads; the Prime agent must verify important claims against primary files or command output.

## Per-Piece Subagent Test Matrix

Before completion, assign subagents so every computer-wide and repo-local memory graph/control-plane piece is tested or explicitly marked blocked.

Required coverage:

- Computer-wide graph files: `MEMORY_GRAPH.md`, `SCHEMA.md`, `projects\<target-project>.md`, `graph\nodes.jsonl`, `graph\edges.jsonl`, `graph\aliases.jsonl`, `graph\hashes.jsonl`, `transcripts\INDEX.md`, `dreams\INDEX.md`, `dreams\end-to-end-memory-graph-prompt.md`, `scripts\hash-memory-target.ps1`, and `scripts\verify-memory-graph.ps1`.
- Repo-local docs and runtime state: `AGENTS.md`, `docs\agent-control-plane.md`, `docs\autoresearch\memory-graph-dreaming-goal.md`, `docs\PROJECT_CONTEXT.md`, `docs\DECISIONS.md`, `docs\WORKLOG.md`, `docs\NEXT_STEPS.md`, `data\agent-control\agent_control.db`, `events.jsonl`, and `sessions.jsonl`.
- Runtime commands: `bootstrap`, `checkpoint latest/write`, `graph query`, `context pack`, `memory remember/supersede/audit/eval`, `session log`, `dream propose/accept/reject/list`, and available package aliases.

Each subagent report must include:

- piece(s) tested
- purpose expected
- files/artifacts read
- commands run
- observed result
- bugs or gaps found
- source-of-truth verdict
- purpose-fit verdict
- residual risk

No untested piece may be treated as passing.

## Target Architecture

Computer-wide memory:

```text
C:\Users\kalec\projects-memory\
  MEMORY_GRAPH.md
  SCHEMA.md
  projects\options-chatbot.md
  graph\nodes.jsonl
  graph\edges.jsonl
  graph\aliases.jsonl
  graph\hashes.jsonl
  transcripts\INDEX.md
  dreams\INDEX.md
  dreams\end-to-end-memory-graph-prompt.md
  scripts\hash-memory-target.ps1
  scripts\verify-memory-graph.ps1
```

Repo-local memory:

```text
C:\Users\kalec\options-chatbot\AGENTS.md
C:\Users\kalec\options-chatbot\docs\agent-control-plane.md
C:\Users\kalec\options-chatbot\docs\autoresearch\memory-graph-dreaming-goal.md
C:\Users\kalec\options-chatbot\docs\PROJECT_CONTEXT.md
C:\Users\kalec\options-chatbot\docs\DECISIONS.md
C:\Users\kalec\options-chatbot\docs\WORKLOG.md
C:\Users\kalec\options-chatbot\docs\NEXT_STEPS.md
C:\Users\kalec\options-chatbot\data\agent-control\agent_control.db
C:\Users\kalec\options-chatbot\data\agent-control\events.jsonl
C:\Users\kalec\options-chatbot\data\agent-control\sessions.jsonl
```

## Implementation Requirements

- Use plain Markdown for human memory and JSONL/SQLite for machine memory.
- Add or preserve a bootstrap command that emits prompt-ready context.
- Add session logging with source SHA-256 and safe-path refusal.
- Add dream proposal, accept, reject, and list commands.
- Store accepted dream entries through the existing operating-memory path.
- Keep proposed dreams as proposal nodes until accepted.
- Add a memory audit command that flags stale or inconsistent memory.
- Add deterministic tests for session logging, hash mismatch, safe-path refusal, dream accept, dream reject, observed-without-evidence rejection, bootstrap recovery, and authority boundaries.
- Add package/script aliases for common memory operations.
- Update living docs and worklog after meaningful changes.

## Options Bot Safety Contract

- Run `npm run agent:control -- bootstrap --prompt-only` before planning.
- Treat the gateboard and generated readbacks as current operating evidence.
- Keep autonomy at `read_only_workers` unless the user explicitly approves a higher-risk path and repo gates pass.
- Any missing, stale, contradictory, or dream-derived trading-sensitive claim forces `observe_only`.
- Never let memory graph status clear evidence, proof, promotion, broker, live, holdout, stop, sizing, or scanner-policy gates.

## Dream Proposal JSON Shape

```json
{
  "title": "Nightly memory cleanup",
  "summary": "Distilled lessons from recent sessions.",
  "evidence": ["session:S-20260626-example"],
  "entries": [
    {
      "id": "bootstrap-first",
      "type": "lesson",
      "title": "Run bootstrap before graph queries",
      "body": "Fresh agent sessions should recover checkpoint and gateboard context before assigning workers.",
      "confidence": "inferred",
      "evidence": ["session:S-20260626-example"],
      "freshness_days": 30
    }
  ]
}
```

Allowed dream entry types in this repo are `lesson`, `constraint`, `decision`, `blocker`, `open_question`, and `superseded_fact` unless `docs/agent-control-plane.md` changes that contract.

## Verification

Minimum verification before handoff:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\kalec\projects-memory\scripts\verify-memory-graph.ps1
npm run verify:agent-control
npm run verify:memory
npm run verify:docs
npm run memory:bootstrap
npm run memory:audit
npm run memory:dreams
```

End-to-end behavior verification:

```powershell
$path = 'docs/autoresearch/memory-graph-dreaming-goal.md'
$hash = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLowerInvariant()
npm run agent:control -- session log --transcript $path --session-id memory-graph-e2e-<yyyymmdd>-<shortid> --title "Memory graph E2E assurance ingest" --summary "Hash-guarded session ingest for memory graph assurance." --actor codex --expected-sha256 $hash --json
npm run agent:control -- graph query "Memory graph E2E assurance ingest" --metadata source_type=session_transcript --max-depth 1 --prompt-only
npm run agent:control -- graph query "end-to-end prompt artifact" --metadata origin=dreaming --memory-type lesson --max-depth 1 --prompt-only
npm run agent:control -- memory audit --prompt-only
```

If a command cannot run, state the exact reason and the residual risk.

## Six-Subagent Final Debate

After all tests and fixes, run a final six-subagent debate with distinct roles:

1. Completeness reviewer: Did the delivered system satisfy the user's requested end-to-end goal prompt, computer-wide graph, options-local copy, runtime memory, and dreaming loop?
2. Runtime correctness reviewer: Do CLI commands, SQLite/JSONL state, graph query, session logging, dream lifecycle, and audit behavior work from primary evidence?
3. Safety reviewer: Can any memory or dream path be mistaken for trading, broker, proof, promotion, scanner-policy, evidence-mutation, stop/sizing, live-validation, or holdout approval?
4. Hash/concurrency reviewer: Are SHA guards, mismatch behavior, provenance hashes, and remaining compare-and-swap limitations accurately documented?
5. Documentation reviewer: Are living docs, decisions, worklog, index entries, and global/local prompt copies coherent and non-stale?
6. Operator usefulness reviewer: Would a future Codex/Claude/options operator recover the right context and know the next safe command without re-prompting?

Ask each reviewer for one of these verdicts: `ready`, `ready_with_minor_risks`, or `blocked`. A `blocked` verdict requires fixing or explicitly deferring the issue with evidence before handoff. The final answer may say the system is ready only if all reviewers return `ready` or `ready_with_minor_risks`, and every minor risk is named.

## Completion Checklist

- Debate reports were considered and showstoppers addressed.
- Assurance auditor reports were considered and showstoppers addressed.
- Every memory graph/control-plane piece has a subagent test result or explicit blocker.
- Six-subagent final debate completed with no `blocked` verdicts.
- Global memory files exist and verify.
- Target repo has this copied/adapted prompt.
- Runtime graph commands exist and are documented.
- Dreaming has propose, accept, reject, and list lifecycle.
- Accepted dreams remain marked non-authoritative.
- Tests prove safety boundaries.
- End-to-end session ingest and retrieval were tested with a live SHA guard.
- The six-subagent final debate found no known unresolved local bugs and confirmed purpose-fit, or the goal remains incomplete.
- Living docs, decisions, worklog, and next steps were updated.
- Final handoff names changed files, verification, final debate verdicts, and remaining risks.
