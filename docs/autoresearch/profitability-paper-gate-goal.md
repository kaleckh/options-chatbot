# Profitability Paper Gate Sprint Goal

Use this prompt when running a `/goal` loop to finish the Profitability Paper Gate Operator Workflow sprint backlog end to end.

This goal exists because the current repo has visible product-side profitability progress, but proof-grade readiness is still blocked. The latest regular-options profit-capture queue has Tier A historical evidence, but the Tier A fresh-match paper bridge currently has `0` eligible rows. The next sprint sequence must convert the new paper gates into an operator workflow that collects fresh executable evidence without weakening proof bars.

## Objective

Finish every sprint in the Profitability Paper Gate Operator Workflow backlog:

1. Paper gate release pack and generated shortlist readback.
2. Fresh exact evidence loop from pending scan candidate to realized paper P&L.
3. Recent-cohort circuit breaker for broken current-policy lanes.
4. Trading Desk operator workflow for bridge status, local unlock, and pending validation outcomes.
5. Exact repair queue burn-down with repair-attempt memory.
6. Scorecard, agent memory graph, and future-agent readability updates.

A sprint is done only when its implementation is complete, focused verification passes, living docs are updated, generated reports are refreshed when owned facts change, and six independent subagents review and debate the result.

## Scope

Active scope:

- Regular supervised options browser product.
- Trading Desk live scan, paper ideas, tracked-position review, and replay diagnostics.
- Regular stock-options profit-capture queue, paper monitor, point-in-time replay, multi-lane quality gate, and operating scorecard.
- Documentation and generated navigation artifacts needed to keep future LLM agents oriented.

Out of scope unless the operator explicitly reopens it:

- AI commodity strategy changes.
- Crypto options.
- Polymarket.
- Day-trading.
- Broker/live auto-promotion.
- Stop-policy changes.
- DB schema changes not directly required by a sprint story.

## Start Every Run

Before editing code or docs:

1. Read `README.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, and `package.json`.
2. Confirm the worktree state with:

```powershell
git status --short --branch
```

3. Read the current profitability artifacts:

```powershell
uv run --locked python scripts\build_regular_profitability_operating_scorecard.py --no-write --json
uv run --locked python scripts\build_regular_options_profit_capture_queue.py --no-write --json
uv run --locked python scripts\run_regular_options_multilane_portfolio.py --no-write --json
uv run --locked python scripts\replay_short_term_filter_point_in_time.py --no-write --json
uv run --locked python scripts\monitor_current_policy_entry_filter_paper.py --no-write --json
```

If a command lacks `--no-write`, use the existing repo command only when the sprint explicitly requires publishing a refreshed artifact.

## Sprint Backlog

### Sprint 1: Paper Gate Release Pack

Goal: make paper-gate eligibility a first-class release surface.

Stories:

- Add a generated paper-shortlist readback that consumes the profit-capture queue and emits eligible rows, blockers, and live-prohibited states.
- Add focused tests proving only Tier A fresh executable lane-signature matches can bridge.
- Add negative tests for Tier B, Tier C, symbol-only matches, blocked guardrails, stale evidence, midpoint-only evidence, EOD evidence, fallback evidence, and manual labels.
- Add or update a release command such as `verify:profitability-paper-gates`.
- Keep the current expected readback explicit: `eligible_count=0` until fresh executable Tier A lane matches exist.

### Sprint 2: Fresh Exact Evidence Loop

Goal: connect pending candidates, fill attempts, paper/tracked linkage, and exact realized P&L.

Stories:

- Reconcile pending validation output with `fill_attempts.jsonl`.
- Ensure fill-attempt records expose the minimum fields needed by paper monitor and point-in-time replay.
- Link paper candidates to tracked or suggested rows without merging proof semantics.
- Ensure exact OPRA/NBBO realized P&L is required before promotion discussion.
- Add readback fields for missing realized P&L, no-longer-matched, proof-ineligible, stale, and non-executable candidates.

### Sprint 3: Recent-Cohort Circuit Breaker

Goal: prevent recently broken lanes from quietly becoming current recommendations.

Stories:

- Add a readback-driven circuit breaker for `paper_only_recent_week_break`.
- Route affected `short_term` and `bullish_pullback_observation` candidates to paper validation only until recovery gates pass.
- Keep the short-term fill-degradation rule lane-scoped and paper-only.
- Require at least `20` fresh current-policy rows, at least `5` champion-matched candidate-blocked rows, trusted executable realized P&L, and no winner damage before promotion.
- Do not permanently delete a lane based only on one recent broken cohort.

### Sprint 4: Operator Workflow

Goal: make the paper gate visible and usable without making it look like a trade recommendation.

Stories:

- Add a local operator unlock/session affordance for `POST /api/operator/session` if still missing.
- Surface bridge status, blockers, matched Tier A lane, and paper-review-only language in the Trading Desk scanner/archive flow.
- Make pending validation outcomes operator-readable.
- Explain every no-fill or skipped auto-track state using fill-discipline evidence.
- Add browser and route tests for auth, scanner UI, and pending-candidate lifecycle changes.

### Sprint 5: Exact Repair Queue Burn-Down

Goal: repair proof gaps only where exact-date evidence can actually improve the queue.

Stories:

- Use the evidence repair queue and repair-attempt readback before importing data.
- Prioritize unexhausted high-priority exact repairs.
- Do not repeat exhausted provider no-match loops unless a new source can answer the exact missing contract/date.
- Treat lookahead-only rows as diagnostic, never exact-date proof.
- Rerun source replay before any Tier B row can graduate.

### Sprint 6: Scorecard And Agent Memory

Goal: make the workflow recoverable by future agents.

Stories:

- Add paper-gate readiness counts to the operating scorecard or a generated companion report.
- Add an agent-memory-graph path for profitability paper gates.
- Keep `docs/NEXT_STEPS.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, and `docs/WORKLOG.md` current when owned facts change.
- Add the prompt and current sprint state to `docs/index.md`.
- Ensure future agents can answer: what is eligible, what is blocked, why it is blocked, and which command proves it.

## Done Gate For Every Sprint

After implementation and local verification, spawn or resume six independent subagents for review and debate:

1. Profitability strategy reviewer.
2. Proof and evidence reviewer.
3. Data lifecycle and storage reviewer.
4. Trading Desk operator workflow and auth reviewer.
5. Tests and regression reviewer.
6. LLM readability and maintainability reviewer.

Each reviewer must return:

- `verdict`: `agree_done`, `agree_with_minor_followups`, or `blocked`.
- `confidence`: `high`, `medium`, or `low`.
- `evidence_reviewed`: files, tests, artifacts, and commands inspected.
- `blockers`: concrete issues that must be fixed before the sprint is accepted.
- `minor_followups`: non-blocking improvements.

Then synthesize the six reviews into a debate summary:

- consensus count
- dissenting risks
- whether any severe blocker exists
- what changed after review, if anything
- final accept or continue decision

A sprint can be marked done only when at least `4` of `6` reviewers return `agree_done` or `agree_with_minor_followups`, and no credible severe blocker remains. Severe blockers include data loss, proof-source contamination, unintended state mutation, incorrect P&L, auth bypass, live-promotion leakage, broker action, or a broken primary Trading Desk flow.

If the active thread cannot run six agents concurrently, run reviews in batches or reuse/resume existing subagents until six distinct reviews are captured. Do not lower the review count.

## Verification Ladder

Use the smallest relevant checks first, then widen based on blast radius:

```powershell
uv run --locked python -m unittest tests.test_regular_options_profit_capture_queue tests.test_log_scan_picks tests.test_regular_options_multilane_portfolio -v
uv run --locked python scripts\build_regular_options_profit_capture_queue.py --no-write --json
uv run --locked python scripts\run_regular_options_multilane_portfolio.py --no-write --json
uv run --locked python scripts\replay_short_term_filter_point_in_time.py --no-write --json
uv run --locked python scripts\monitor_current_policy_entry_filter_paper.py --no-write --json
npm run verify:docs
npm run lint
npm run verify:typecheck
git diff --check
```

For browser/operator changes, run desktop and mobile browser QA against a local dev server and inspect the exact operator flow that changed.

For generated artifacts, run the owner generator and then `npm run verify:docs`.

## Proof Bars

Do not promote or imply live-production readiness from:

- Tier A historical evidence without a fresh executable same-lane scanner match.
- Tier B watch/repair rows.
- Tier C historical-signature-only rows.
- blocked guardrail rows.
- quarantine rows.
- midpoint-only evidence.
- last trade evidence.
- stale snapshots.
- daily/EOD rows.
- lookahead-only repair rows.
- research/backfill paper rows.
- display-only marks.

Production proof still requires trusted intraday OPRA/NBBO exact-contract evidence, verified scanner lineage, caps-enforced fresh validation, executable entry and exit evidence, resolved P&L, and the frozen clean-promotion bars.

## Completion Criteria

The full goal is complete only when all six sprints are complete, each sprint has a six-subagent review/debate summary, verification is recorded, living docs and generated owner reports are current, and the operator can see a clear paper-gate answer:

- what is eligible
- what is blocked
- why it is blocked
- which command proves it
- what remains paper-only
- what remains live-prohibited
