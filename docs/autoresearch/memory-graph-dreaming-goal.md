# End-To-End Memory Graph And Dreaming Prompt

Use this prompt when building, reviewing, or upgrading the machine-wide memory graph and the options-chatbot memory graph. This is the repo-local copy of `C:\Users\kalec\projects-memory\dreams\end-to-end-memory-graph-prompt.md`.

## Goal

Build or upgrade a safe, useful, self-improving memory system end to end:

1. Debate the architecture with bounded subagents.
2. Distill the winning design into a concrete implementation plan.
3. Implement the computer-wide memory graph under `C:\Users\kalec\projects-memory`.
4. Copy/adapt the same operating prompt into this repo.
5. Add repo-local runtime memory, session logging, dreaming, audit, and verification commands.
6. Record lessons learned in memory files so future agents do not repeat the same mistakes.

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
- Add reject/archive/list/audit paths so stale dream proposals do not accumulate as tempting context.
- Verify the full loop with tests and a real bootstrap/audit command before calling the task complete.

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
npm run memory:dreams
```

If a command cannot run, state the exact reason and the residual risk.

## Completion Checklist

- Debate reports were considered and showstoppers addressed.
- Global memory files exist and verify.
- Target repo has this copied/adapted prompt.
- Runtime graph commands exist and are documented.
- Dreaming has propose, accept, reject, and list lifecycle.
- Accepted dreams remain marked non-authoritative.
- Tests prove safety boundaries.
- Living docs, decisions, worklog, and next steps were updated.
- Final handoff names changed files, verification, and remaining risks.

