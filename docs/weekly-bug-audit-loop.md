# Weekly Bug Audit Loop

Use this runbook for the recurring six-agent bug audit. The goal is to catch correctness, reliability, proof, and release risks before they stack up.

## Goal Prompt

```text
Audit the options-chatbot project for bugs, inefficiencies, and correctness risks using iterative rounds with six subagents per round.

In each round:
1. Spawn 6 subagents with distinct ownership areas.
2. Have each agent independently inspect its slice for high-confidence actionable bugs, inefficiencies, correctness risks, missing tests, stale docs that affect execution, and release/delivery hazards.
3. Cross-check each agent's findings against the other agents' findings and the current workspace.
4. Implement confirmed safe fixes directly, keeping changes scoped and preserving existing behavior unless the bug requires a behavior change.
5. Add or update focused regression tests for every code fix where practical.
6. Run targeted verification for each fix.
7. Continue another six-agent round after fixes until all agents report no remaining high-confidence actionable code bugs.

Stop only when:
- all six agents are satisfied on code correctness,
- any remaining issue is explicitly reported as a delivery/process note rather than a code bug,
- broad verification passes or any verification gap is clearly explained.
```

## Agent Slices

Use these six slices unless the project has obviously shifted:

1. API and backend transport: Next route handlers, FastAPI endpoints, request parsing, timeout/error handling, environment normalization.
2. Proof and profit gates: proof-source eligibility, finite metrics, position lifecycle, profit loop and flywheel logic.
3. Position identity and backfill: contract aliases, spread legs, scan provenance, storage migrations, comparable-contract repair paths.
4. WFO, replay, and playbooks: replay provider selection, playbook IDs, readiness gates, rolling windows, calibration, non-finite metrics.
5. Polymarket and sidecar execution: order placement/cancel failure handling, risk reservations, dry-run/live separation, setup readiness.
6. Delivery and release hygiene: untracked required files, generated docs parity, build/test commands, dirty artifacts, stale documentation that can mislead operators.

## Verification Ladder

Run focused tests after each fix, then finish with the broad ladder:

```powershell
npm run verify:docs
npm run lint
npm run verify:typecheck
npm run verify:full
git diff --check
git status --short
```

When a fix touches only Python, still finish with the JS checks if route, docs, or transport behavior might be affected. When a fix touches JS, rerun `npm run verify:full` after typecheck/lint because the build is part of the full gate.

## Delivery Rules

- Do not revert unrelated user changes.
- Follow `docs/agent-worktree-hygiene.md` for branch, push, untracked-file, and cleanup rules.
- Push big verified fix sets when publishing is allowed: create a `codex/` branch, commit the required tracked and untracked files, push, and report the branch or PR.
- Small local fixes can remain unstaged when the run was explicitly scoped as investigation or local-only patching.
- Treat required untracked files as a release blocker note. They are not "fixed" until included in the intended commit or PR.
- Call out any generated file that changed during verification.
- Prefer worktree-based automation for weekly runs so active local edits are not disturbed.

## Weekly Automation Prompt

```text
Run the Weekly Bug Audit Loop for options-chatbot. First read docs/weekly-bug-audit-loop.md, docs/agent-worktree-hygiene.md, docs/index.md, docs/current-state.md, docs/NEXT_STEPS.md, docs/PROJECT_CONTEXT.md, and git status.

Create an explicit audit goal with the Goal Prompt from docs/weekly-bug-audit-loop.md. Use six subagents per round with the documented slices. Keep looping: after any confirmed code fix, run the relevant targeted tests and then start another six-agent satisfaction pass. Stop only when all six agents report no remaining high-confidence actionable code bugs.

Implement safe, scoped fixes directly in the automation worktree. Add focused regression coverage for each code fix where practical. Do not loosen trading/proof/risk gates to make tests pass. Follow docs/agent-worktree-hygiene.md: push broad verified fix sets on a codex/ branch when publishing is allowed, and otherwise clearly report why changes remain local.

Before finalizing, run npm run verify:docs, npm run lint, npm run verify:typecheck, npm run verify:full, git diff --check, and git status --short. If any command fails, either fix the root cause and rerun the relevant checks or report the blocker clearly.

Final output must include: bugs fixed, files changed by category, tests/verification run, all remaining delivery notes, required untracked files, whether changes were pushed or intentionally left local, and whether all six agents were satisfied.
```

## Last Known Audit Count

The 2026-05-25 full audit fixed about 27 distinct bugs/inefficiencies, including API validation, proof-source gating, spread contract aliases, WFO/playbook readiness, market data/calendar edge cases, Polymarket execution safety, and delivery hygiene.
