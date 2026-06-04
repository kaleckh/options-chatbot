# Living Docs Hygiene

This doc owns the rules for keeping the current reading path useful for LLM agents and senior engineers. It explains which Markdown files own current facts, which artifacts are generated, and which historical reports are evidence records rather than source-of-truth documents.

## Living Owners

| Owner | Responsibility |
| --- | --- |
| `docs/index.md` | Living reading order, generated artifact links, historical-context warning, and freshness checklist. |
| `docs/PROJECT_CONTEXT.md` | Product scope, lane boundaries, architecture summary, current proof posture, and active/out-of-scope lanes. |
| `docs/DECISIONS.md` | Durable product and technical decisions only. |
| `docs/NEXT_STEPS.md` | Active blockers, current commands, and next actions. |
| `docs/WORKLOG.md` | Dated summaries of meaningful local work and verification evidence. |
| `docs/architecture-overview.md` | Current system map and subsystem ownership. |
| `docs/architecture-best-practices.md` | Target architecture/readability rubric. |
| `docs/architecture-audit.md` | Current architecture risk snapshot and remaining monoliths. |

`README.md` and `AGENTS.md` are startup/orientation docs. They must point agents into the living docs rather than replacing them.

## Evidence Records

Dated reports in `docs/`, generated reports under `data/`, `research_runs/`, `docs/autoresearch/`, and `docs/archive/` are evidence records. They are useful context, but they are not the source of truth when they disagree with code, generated check artifacts, or the living owner docs above.

Generated readability artifacts should stay generated. Handwritten docs may link or summarize their purpose, but they should not copy generated route, storage, schema, proof, or memory-graph inventories into a second stale table.

## Generated Artifacts

The detailed generated-artifact inventory is generated in `docs/generated-artifact-governance.md`, with machine-readable data in `data/contracts/generated-artifact-governance.json`.

Generated JSON check artifacts that participate in docs-readability ownership must expose `generated_by` and `runtime_use=false` when they are not runtime configuration. Generated Markdown or TypeScript artifacts must state which generator produced them and that they should not be hand-edited. The generated governance map owns the command/check table, runtime posture, stale-handling rule, and excluded volatile artifact classes.

Key generated maps for agent navigation are `docs/final-remediation-closure-pack.md` with `data/contracts/final-remediation-closure-pack.json`, `docs/agent-memory-graph.md`, `docs/remediation-loop-map.md` with `data/contracts/remediation-loop-map.json`, and `docs/backend-route-ownership-map.md`. Keep this section as pointers only; the generated governance map owns the complete inventory.

## Hygiene Rules

- Read code and owner docs before answering architecture questions.
- Update `docs/index.md` only for living docs, current orientation docs, generated readability artifacts, or reports that change the current decision surface.
- Update `docs/WORKLOG.md` after meaningful local work.
- Update `docs/PROJECT_CONTEXT.md`, `docs/NEXT_STEPS.md`, or `docs/DECISIONS.md` only when their owned facts change.
- Keep durable decisions in `docs/DECISIONS.md`, not in daily worklog entries.
- Keep current blockers and commands in `docs/NEXT_STEPS.md`, not in dated reports.
- Do not hand-edit generated artifacts when their owner generator can be run.
- Do not treat archive, autoresearch, research-run, or generated evidence records as more authoritative than code and living owner docs.

## Verification

Use `npm run verify:docs` before handoff after docs ownership, generated artifact, route, storage, proof-contract, schema-bridge, remediation-loop-map, memory-graph, or final-closure changes. The command checks generated artifacts and runs the living-docs hygiene check.

For focused docs-hygiene work, run:

```bash
uv run --locked python scripts/check_living_docs_hygiene.py
uv run --locked python -m unittest tests.test_living_docs_hygiene -v
```

## Non-Goals

This doc and its checker are not broad Markdown lint, stale-data governance for all research reports, runtime behavior, route behavior, auth, proof, scanner, replay, DB, schema, or frontend policy. They do not require every dated report to be linked from `docs/index.md`, and they do not validate volatile proof counts or market-data dates.
