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

The currently active app-facing product surface is the options lane:
- live scan
- replay and truth diagnostics
- tracked positions
- suggested trades

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
4. those routes proxy through `src/lib/python-bridge.ts`
5. the bridge talks to `python-backend/main.py` at `PYTHON_BACKEND_URL` (`http://localhost:8100` by default)
6. the backend fans out into the domain modules such as `options_chatbot.py`, `wfo_optimizer.py`, `supervised_scan.py`, and the repository/service modules

The fastest files to read for orientation are:
- `src/components/layout/AppShell.tsx`
- `src/components/predictions/PredictionsView.tsx`
- `src/components/strategy/StrategyView.tsx`
- `src/lib/python-bridge.ts`
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
- `market_data.db`
  - market data cache and research support data

## Local Development

Frontend plus backend:

```bash
npm install
uv sync
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
npm run verify
python -m unittest discover -s tests -p "test_*.py" -v
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
```

The repo still contains legacy day-trading tests and engine code, but the corresponding app-facing routes and UI are absent in this worktree. Treat that lane as separate from the current browser product unless and until it is restored deliberately.

## Docs

- `docs/architecture-overview.md`
  - runtime map, request flow, subsystem ownership
- `docs/api-and-storage.md`
  - active routes, bridge layer, storage map, and artifact ownership
- `docs/current-state.md`
  - current options product status
- `docs/day-trading-current-state.md`
  - legacy or CLI-oriented day-trading context with a snapshot warning
