# Options AI

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Snapshot

This repo is a mixed Next.js plus FastAPI system for supervised options research and trade review.

The mounted browser product is the regular supervised options lane:
- live scan
- replay and truth diagnostics
- tracked positions
- paper ideas

The active non-browser proof lane is the AI commodity / commodity-infrastructure options lane. It lives under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`, and is currently gated on exact Alpaca SIP/OPRA bid/ask snapshot history rather than profitability claims.

The default supervised options scanner playbook is `bullish_pullback_observation`, shown in the UI as Bullish Pullback. The `_observation` suffix is legacy cohort ID wording, not watch-only behavior; eligible scheduled picks are allowed to auto-track. The lane scans a broad liquid options universe, with SPY/QQQ currently marked as the historical-ready subset.

Current bullish-pullback profitability work uses trusted ThetaData intraday OPRA/NBBO exact-contract evidence. The latest per-ticker audit keeps `10` symbols in the current queue, routes `10` to separate scout lanes, removes `9` from the current queue, and leaves `30` research/data-needed. See `docs/bullish-pullback-ticker-audit-2026-05-29.md`.

Important snapshot caveats:
- the App Router shell is the real browser entrypoint; `src/app/page.tsx` is intentionally a stub
- the Next API routes are thin proxies into the Python backend
- the old app-facing day-trading routes and UI components are not present in this worktree
- `src/lib/day-trading/engine.js` and related tests still exist, but that lane currently reads as legacy or CLI-only in this snapshot
- `src/lib/polymarket/*` is adjacent tooling, not part of the current main UI flow

## Runtime Architecture

Browser flow:
1. `src/app/layout.tsx` mounts `src/components/layout/AppShell.tsx`
2. `AppShell` dynamically loads the active client surfaces
3. client components call Next route handlers under `src/app/api/*`
4. those routes proxy through the backend client modules under `src/lib/backend/*`
5. the bridge talks to `python-backend/main.py` at `PYTHON_BACKEND_URL` (`http://localhost:8100` by default)
6. the backend fans out into the domain modules such as `options_chatbot.py`, `wfo_optimizer.py`, `supervised_scan.py`, and the repository/service modules

The fastest files to read for orientation are:
- `src/components/layout/AppShell.tsx`
- `src/components/predictions/PredictionsView.tsx`
- `src/components/strategy/StrategyView.tsx`
- `src/lib/python-bridge.ts`
- `src/lib/backend/*`
- `python-backend/main.py`
- `options_chatbot.py`
- `wfo_optimizer.py`

For a fuller map, read:
- `docs/architecture-overview.md`
- `docs/api-and-storage.md`

## Storage

The repo uses multiple stores on purpose:

- `chat_history.db`
  - SQLite for suggested trades and local workflow state
- Postgres via `DATABASE_URL`
  - tracked positions and tracked-position reviews
- `predictions.json`
  - legacy prediction history
- `wfo_results.json`
  - latest replay output
- `data/options-profit/*`
  - profit-cycle and truth-gate artifacts
- `data/forward-tracking/*`
  - forward scan evidence
- `data/options-validation/*`
  - imported options truth stores, Alpaca OPRA captures, and replay run artifacts
- `data/ai-commodity-infra/*`
  - AI commodity universe, progress readbacks, and proof-lane acquisition artifacts
- `data/alpaca-options-strategy-lab/*`
  - research-only exact bid/ask lab artifacts; not final promotion proof by itself
- `market_data.db`
  - market data cache and research support data

## Local Development

Frontend plus backend:

```bash
npm install
uv sync --locked
npm run dev
```

Frontend only:

```bash
npm run dev:next
```

Backend only:

```bash
npm run dev:python
```

Optional Postgres for tracked positions:

```bash
npm run db:up
```

Example local `DATABASE_URL`:

```text
postgresql://options_chatbot:options_chatbot@localhost:5432/options_chatbot
```

## Verification

Core checks:

```bash
npm run build
npm run verify:docs
npm run verify
npm run verify:python:full
```

Research and support scripts:

```bash
npm run options:smoke
npm run options:experiments
npm run options:record
npm run profit-loop:health
npm run profit-loop:holdout
npm run profit-loop:validate
npm run profit-loop:canary
npm run accuracy:report
npm run verify:accuracy:no-write
```

AI commodity proof-lane readback:

```bash
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
```

The repo still contains legacy day-trading tests and engine code, but the corresponding app-facing routes and UI are absent in this worktree. Treat that lane as separate from the current browser product unless and until it is restored deliberately.

## Docs

- `AGENTS.md`
  - repo-specific agent startup, evidence rules, and documentation placement
- `docs/architecture-overview.md`
  - runtime map, request flow, subsystem ownership
- `docs/index.md`
  - living-doc starting point and archive map
- `docs/api-and-storage.md`
  - active Next routes, backend-only support endpoints, storage map, and artifact ownership
- `docs/route-parity.md`
  - browser route to Next route to FastAPI parity map
- `docs/architecture-audit.md`
  - live audit of dead surfaces, sidecars, and remaining monoliths
- `docs/current-state.md`
  - current options product status
- `docs/day-trading-current-state.md`
  - current status of the day-trading research lane with a snapshot warning
- `docs/PROJECT_CONTEXT.md`
  - active work scope and lane boundaries
- `docs/NEXT_STEPS.md`
  - current time-gated lane actions
- `docs/lane-lab-lanes.md`
  - lane registry and promotion bars
- `docs/bullish-pullback-ticker-audit-2026-05-29.md`
  - current per-ticker keep/move/research/remove decisions for the 59-symbol bullish-pullback universe
- `docs/markdown-audit-2026-05-31.md`
  - latest Markdown placement audit for global and options-chatbot docs
- `docs/WORKLOG.md`
  - recent local evidence and doc changes
- `docs/weekly-bug-audit-loop.md`
  - recurring six-agent bug audit runbook and automation prompt
- `docs/agent-worktree-hygiene.md`
  - agent branch, push, untracked-file, and clean-worktree rules

Treat the files above as the living docs for this worktree.

Historical planning and audit docs:
- dated roadmap or audit files under `docs/archive/`
- `docs/autoresearch/*`
- `research_runs/*`

Those files are useful context, but they are records, not the source of truth for the current route map. If a dated doc disagrees with the code or the living docs above, trust the code first.
