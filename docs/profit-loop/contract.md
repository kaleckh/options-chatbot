# Profit Loop Contract

The unattended profit loop is separate from `scripts/autoresearch_cycle.py`.

## Purpose

- `Hourly Operational Health` records system-health blockers and evidence-quality issues.
- `Weekday Truth Holdout` appends forward-truth evidence and records holdout blockers.
- `Daily Profit Validation` consumes the shared queue, captures baseline evidence, and either:
  - records a deferred blocker with an explicit next action, or
  - lands a verified deterministic fix and records the pushed branch + commit.

## Shared State

Live automation state is stored outside repo worktrees:

- `%CODEX_HOME%/automations/shared/options-chatbot/profit-loop-state.json`
- `%CODEX_HOME%/automations/shared/options-chatbot/profit-loop-runs.jsonl`

The repo copy at `docs/autoresearch/automation-handoff.json` is documentation only.

## Mutation Policy

`Daily Profit Validation` may patch, branch, commit, and push, but only for safe deterministic fixes in these classes:

- infra or scheduler parity
- data freshness or persistence
- truth-lane or calibration integrity
- fail-closed guardrails
- replay or report integrity
- storage or API reliability

It must not:

- loosen default strategy behavior
- loosen bearish-defensive behavior
- free-search for new strategy rules
- claim profitability improvement without baseline-vs-after evidence

## Freshness Gates

Before daily validation may attempt a code change:

- `latest_operational_health` must be no older than 2 hours
- `latest_truth_holdout` must be same-day on weekdays
- weekend validation may use the most recent weekday holdout snapshot within 3 days

If freshness fails, validation must write a blocker and stop before any code edit.

## Validation Outcome Rules

- Read-only runs may only open or refresh issues.
- Validation may `claim`, `defer`, or `resolve` issues.
- Deferred issues must carry `deferred_reason` and `next_action`.
- Resolved issues must carry `resolution_branch` and `resolution_commit`.
- A fix is only counted as profitability-positive when replay or forward evidence improves without weakening safety gates.

## Canonical Manual Test

Use `python scripts/run_profit_loop_canary.py` to simulate:

1. `Hourly Operational Health`
2. `Weekday Truth Holdout`
3. `Daily Profit Validation`

Use `--temp-state-dir` to isolate state and `--dry-run` when you only want to validate sequencing.
