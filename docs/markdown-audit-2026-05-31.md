# Markdown Audit - 2026-05-31

## Scope

Audited only global agent Markdown and `options-chatbot` Markdown.

Included global files:
- `C:\Users\kalec\AGENTS.md`
- `C:\Users\kalec\CLAUDE.md`

Included repo scope:
- `C:\Users\kalec\options-chatbot\**\*.md`

Excluded dependency/build folders such as `.git`, `node_modules`, `.next`, `dist`, `build`, virtualenv folders, and `__pycache__`. An inaccessible stale temp folder, `tmp8zf11ul3`, was not needed for the audit.

## Objective

Keep truthfulness and challenge behavior global, keep repo-specific operating rules in the repo root, and keep options research evidence separated from living product memory.

## Inventory

After this audit, the unrestricted repo Markdown inventory is expected to be `905` files:

- `559` generated or artifact Markdown files under `data/`
- `216` generated or artifact Markdown files under `research_runs/`
- `60` autoresearch grid proposal files under `docs/autoresearch/proposals/sixty-run-grid/`
- `27` living or dated report files directly under `docs/`
- `21` other autoresearch proposal files under `docs/autoresearch/proposals/`
- `11` autoresearch control files under `docs/autoresearch/`
- `8` historical files under `docs/archive/`
- `2` repo-root Markdown files: `README.md` and `AGENTS.md`
- `1` profit-loop contract under `docs/profit-loop/`

## Findings

- Global behavior rules belong in global files, not scattered throughout project reports. Added the Truthfulness And Challenge Rules to both `C:\Users\kalec\AGENTS.md` and `C:\Users\kalec\CLAUDE.md`.
- `options-chatbot` had the required repo memory docs but no repo-level `AGENTS.md`. Added one so agents get the repo reading order, active lane scope, evidence rules, and documentation placement rules before touching code.
- `docs/index.md` remains the correct entry point for living repo docs. It now points to the new repo `AGENTS.md` and this current audit.
- The current split makes sense for the stated objectives: living docs stay in `docs/`, durable memory stays in `PROJECT_CONTEXT` / `DECISIONS` / `WORKLOG` / `NEXT_STEPS`, generated evidence stays under `data/` and `research_runs/`, old planning stays under `docs/archive/`, and experiment prompts/results stay under `docs/autoresearch/`.
- No broad moves are recommended. Moving generated reports out of `data/` or autoresearch proposals out of `docs/autoresearch/` would make traceability worse.

## Placement Rules Going Forward

- Add new agent behavior rules globally unless they are specific to `options-chatbot`.
- Add current product state to `docs/PROJECT_CONTEXT.md`, not to a dated report.
- Add durable policy changes to `docs/DECISIONS.md`.
- Add completed work evidence to `docs/WORKLOG.md`.
- Add active blockers and next commands to `docs/NEXT_STEPS.md`.
- Add generated research output beside its JSON or source artifact under `data/` or `research_runs/`; link or summarize it from living docs only when it changes the current decision surface.

## Verification

Commands used for the audit inventory:

```powershell
rg --files -u "C:\Users\kalec\options-chatbot" -g "*.md" -g "!tmp8zf11ul3" -g "!tmp8zf11ul3/**" -g "!**/.git/**" -g "!**/node_modules/**" -g "!**/.next/**" -g "!**/dist/**" -g "!**/build/**" -g "!**/.venv/**" -g "!**/venv/**" -g "!**/__pycache__/**"
```

Run after documentation edits:

```powershell
npm run verify:docs
```
