# Profit Loop Contract

The unattended profit loop is separate from `scripts/autoresearch_cycle.py`.

Snapshot note: this contract describes the profit-loop automation sidecar. It is not the mounted browser product, and it does not reopen paused day-trading, crypto, or Polymarket lanes by itself. Active project scope is governed by `docs/DECISIONS.md` and `docs/PROJECT_CONTEXT.md`.

## Purpose

- The loop optimizes for `Truthful Improvement`, not forced win rate.
- `profitability_verdict=improved` is a precision claim:
  - `100% precision on emitted improved claims`
  - `0 false-improved claims`
- `Hourly Operational Health` records system-health blockers and evidence-quality issues.
- `Weekday Truth Holdout` appends forward-truth evidence and records holdout blockers.
- `Daily Profit Validation` consumes the shared queue, captures baseline evidence, and either:
  - records a deferred blocker with an explicit next action, or
  - lands or stages a verified deterministic fix and records the branch + commit metadata when a resolution is claimed.

## Shared State

Live automation state is stored outside repo worktrees:

- `%CODEX_HOME%/automations/shared/options-chatbot/profit-loop-state.json`
- `%CODEX_HOME%/automations/shared/options-chatbot/profit-loop-runs.jsonl`

The repo copy at `docs/autoresearch/automation-handoff.json` is documentation only.

Shared state is schema-versioned and now tracks:

- `active_run` with run lease, heartbeat, proof bundle directory, commit SHA, and environment hash
- `latest_operational_health`
- `latest_truth_holdout`
- `latest_profit_validation`
- `open_issues`
- `resolved_issues`

Historical note: the repo has carried a separate BTC profitability pilot surface. Treat that pilot as paused sidecar context unless the user explicitly reopens day-trading work. Its docs and scripts have surfaced:

- `dailyTradeCap`
- `todayGate`
- `reviewCheckpointTrades`
- `advanceGateTrades`
- `milestones`
- `disqualificationReasons`
- `executionStats`
- `ticketPath`

Each snapshot carries separate verdicts for:

- `loop_execution_status`: did the loop step run correctly?
- `evidence_status`: is the evidence trustworthy, inconclusive, or untrusted?
- `profitability_verdict`: has profitability actually improved, regressed, or remained unproven?

## Mutation Policy

`Daily Profit Validation` may patch, branch, and commit, and may push when the execution environment explicitly allows it, but only for safe deterministic fixes in these classes:

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
- failed or blocked truth refresh/holdout evidence blocks validation even if timestamps are recent
- an active leased validation run blocks a second validation run until the lease expires

If freshness fails, validation must write a blocker and stop before any code edit.

## Validation Outcome Rules

- Read-only runs may only open or refresh issues.
- Validation may `claim`, `defer`, or `resolve` issues.
- Deferred issues must carry `deferred_reason` and `next_action`.
- Resolved issues must carry `resolution_branch`, `resolution_commit`, proof commands, and a `before_after_comparison`.
- A fix is only counted as profitability-positive when replay or forward evidence improves without weakening safety gates.
- Sparse or worse forward evidence downgrades the result to `inconclusive`, even if replay improved.
- `recorded-no-candidates` is an evidence blocker, not a successful holdout.
- Validation proof must be issue-class-specific and may reuse recent operational-health smoke/tests only when the commit, environment, truth lane, and playbook fingerprint match.
- The first honest `improved` verdict additionally requires:
  - `latest_operational_health.verdict = healthy`
  - `latest_truth_holdout.verdict = recorded` with nonzero candidate flow
  - `measurement_gate.state = healthy`
  - before/after comparison on the exact same playbook, truth lane, pricing lane, lookback, `n_picks`, and `iv_adj`
  - replay PF and avg PnL both improve without material drawdown, truth-quality, or safety regressions

## BTC Pilot Boundary

The BTC profitability pilot is documented and exercised separately from the unattended profit loop, and is currently out of active scope unless the user explicitly reopens it.

- profit-loop automation should not rewrite the BTC pilot contract
- BTC pilot state is read through the day-trading scripts and docs, not this automation contract
- if the BTC approval cap, gate, or milestone semantics change, update the day-trading docs first and only mirror the shared-state implications here

## Canonical Manual Test

Use `python scripts/run_profit_loop_canary.py` to simulate:

1. `Hourly Operational Health`
2. `Weekday Truth Holdout`
3. `Daily Profit Validation`

Use `--temp-state-dir` to isolate state and `--dry-run` when you only want to validate sequencing.

Canary exit codes:

- `0`: all three steps completed and the shared state plus ledger are internally consistent
- `2`: a step was mechanically blocked, prerequisites were stale/failed, or state and ledger do not line up
- `3`: unrecoverable shared-state corruption or driver inconsistency
