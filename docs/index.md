# Docs Index

## Start Here

These are the living docs for the current worktree:

- `AGENTS.md`
  - repo-specific agent startup, evidence rules, and documentation placement
- `README.md`
  - top-level product and runtime summary
- `docs/architecture-overview.md`
  - system map, subsystem ownership, and reading order
- `docs/api-and-storage.md`
  - active route groups, backend-only endpoints, and storage ownership
- `docs/route-parity.md`
  - generated browser route to Next route to FastAPI mapping
- `docs/architecture-audit.md`
  - live audit of dead surfaces, sidecars, and remaining monoliths
- `docs/current-state.md`
  - current options product state
- `docs/day-trading-current-state.md`
  - current day-trading and crypto sidecar snapshot, with archive warnings
- `docs/PROJECT_CONTEXT.md`
  - active work scope and lane boundaries
- `docs/NEXT_STEPS.md`
  - current time-gated commands and guardrails
- `docs/lane-lab-lanes.md`
  - lane registry, pass bars, and AI commodity lane placement
- `docs/bullish-pullback-ticker-audit-2026-05-29.md`
  - current per-ticker keep/move/research/remove decisions for the 59-symbol bullish-pullback universe
- `docs/main-lane-negative-trade-audit-2026-05-31.md`
  - current audit of negative Bullish Pullback tracked rows, with research/backfill versus live-exact separation and guardrail recommendations
- `docs/main-product-lane-negative-trade-audit-2026-05-31.md`
  - broader Trading Desk tracked-position negative audit across all regular supervised product-lane playbooks
- `docs/main-product-lane-quality-system-2026-05-31.md`
  - repair backlog and guardrail taxonomy derived from the all-lanes negative-trade audit
- `docs/trading-desk-profitability-guardrails-2026-05-31.md`
  - all-row replay of Trading Desk profitability guardrails promoted into scanner entry-quality rules
- `docs/trading-desk-negative-trade-decision-audit-2026-05-31.md`
  - reproducible negative-trade decision audit with entry rationale, guardrail coverage, evidence quality, and executable-exit separation
- `docs/trading-desk-exit-policy-replay-2026-05-31.md`
  - read-only executable-review replay of Trading Desk exit policy variants and legacy missed-close cases
- `docs/trading-desk-legacy-missed-close-audit-2026-06-01.md`
  - focused read-only audit of legacy rows 26/39/44 and whether they imply a current auto-close bug
- `docs/regular-options-operating-scorecard.md`
  - current CEO-style scorecard separating visible Trading Desk profitability progress from proof-grade autoresearch readiness
- `docs/markdown-audit-2026-05-31.md`
  - latest Markdown placement audit, scope, and verification evidence
- `docs/WORKLOG.md`
  - recent local evidence and documentation changes
- `docs/DECISIONS.md`
  - active governance decisions and lane scope
- `docs/runtime-request-flow.md`
  - narrative request-flow map, complementing generated route parity
- `docs/paid-options-data-import-checklist.md`
  - current paid-data import and proof-source checklist
- `docs/weekly-bug-audit-loop.md`
  - recurring six-agent bug audit runbook and automation prompt
- `docs/autoresearch/code-audit-remediation-goal.md`
  - reusable six-subagent goal prompt for code audit remediation and long-term fixes
- `docs/agent-worktree-hygiene.md`
  - agent branch, push, untracked-file, and clean-worktree rules

## What To Treat As Historical

These files are still useful, but they are records rather than the source of truth for the current app shape:

- roadmap and audit records under `docs/archive/`
- `docs/autoresearch/*`
- `research_runs/*`
- generated progress files under `data/ai-commodity-infra/progress/*`

If a dated doc disagrees with the code or with the living docs above, trust the code first.

## Freshness Checklist

When routes, storage, proof-lane state, or active lane scope changes:

1. Run `npm run docs:route-parity`.
2. Update `docs/current-state.md`, `docs/NEXT_STEPS.md`, and `docs/PROJECT_CONTEXT.md` when proof-lane dates, blockers, or commands change.
3. Update `docs/WORKLOG.md` with the evidence source and date.
4. Run `npm run verify:docs` before handing off.

## Quick Orientation For A Senior Engineer

Read in this order:

1. `src/components/layout/AppShell.tsx`
2. `src/components/predictions/PredictionsView.tsx`
3. `src/components/strategy/StrategyView.tsx`
4. `src/lib/python-bridge.ts`
5. `src/lib/backend/*`
6. `python-backend/main.py`
7. `options_chatbot.py`
8. `wfo_optimizer.py`

## Snapshot Warnings

- `src/app/page.tsx` is intentionally a stub; the real browser entrypoint is the layout plus app shell.
- `src/app/api/day-trading/*` exists only as empty scaffolding folders in this worktree.
- `src/lib/polymarket/*` and `crypto_options/*` are sidecar lanes, not the mounted browser product.
- `data/ai-commodity-infra/progress/latest.md` is generated lane evidence. Read it for the latest AI commodity proof state, but update the living docs manually when the project state changes.
