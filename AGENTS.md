# Options Chatbot Agent Guide

This repository inherits the global operating manual at `C:\Users\kalec\AGENTS.md`, including the Truthfulness And Challenge Rules. Use this file for repo-specific orientation and guardrails only.

## Startup

Before changing code or docs in this repo:

1. Read `README.md`.
2. Read `docs/index.md`.
3. Read `docs/PROJECT_CONTEXT.md`.
4. Read `docs/DECISIONS.md`.
5. Check `docs/NEXT_STEPS.md` for current blockers and active work.
6. Confirm commands in `package.json` before running verification.

## Coding Style: Minimal Senior-Dev Mode

Prefer the smallest correct change.

Before writing code, check this ladder:

1. Does this need to exist at all?
2. Does the standard library already solve it?
3. Does the platform/framework already solve it?
4. Does an installed dependency already solve it?
5. Can this be one line or one small function?
6. Only then write the minimum code that works.

Rules:

- No new abstractions unless explicitly needed.
- No new dependencies unless clearly justified.
- No boilerplate nobody asked for.
- Prefer deletion over addition.
- Prefer boring, obvious code over clever code.
- Use the fewest files possible.
- For complex requests, challenge scope before building.
- Mark intentional shortcuts with a comment explaining the ceiling and upgrade path.

Do not cut corners on:

- security
- trust-boundary validation
- data-loss prevention
- accessibility
- explicitly requested requirements
- tests for non-trivial logic

## Active Scope

The active browser product is the regular supervised options lane family: live scan, replay diagnostics, suggested trades, and tracked-position review across peer regular-options lanes.

AI commodity / commodity-infrastructure options validation is a separate non-browser proof-first strategy lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`.

Do not spend implementation or documentation effort on crypto options, Polymarket, or day-trading lanes unless the user explicitly asks to archive, remove, repair, or reopen those lanes.

## Evidence Rules

- Treat trusted intraday OPRA/NBBO exact-contract evidence as the standard for regular options proof claims.
- Do not present daily/EOD, midpoint-only, stale snapshot, last-trade, or unresolved candidate evidence as production proof.
- Treat zero-pick audit rows and migrated historical paper positions as research/backfill tracking, not live-production proof or broker fills.
- For tracked positions, distinguish executable exit P&L from paper/mark P&L.

## Documentation Placement

- `docs/index.md` is the living Markdown map and reading order.
- `docs/PROJECT_CONTEXT.md` owns product scope, lane boundaries, architecture summary, and current proof posture.
- `docs/DECISIONS.md` owns durable technical and product decisions.
- `docs/WORKLOG.md` owns dated summaries of meaningful local work.
- `docs/NEXT_STEPS.md` owns active blockers, commands, and next actions.
- Dated reports in `docs/`, generated reports under `data/`, `research_runs/`, `docs/autoresearch/`, and `docs/archive/` are evidence records. Do not treat them as the source of truth when they disagree with code or living docs.

## Verification

Use the smallest relevant check for the change. Common commands:

```bash
npm run verify:docs
npm run lint
npm run verify:typecheck
npm run verify
python -m pytest <tests> -q
```

Update `docs/WORKLOG.md` after meaningful work, and update `docs/DECISIONS.md`, `docs/PROJECT_CONTEXT.md`, or `docs/NEXT_STEPS.md` when their owned facts change.
