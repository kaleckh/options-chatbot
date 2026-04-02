# Options AI

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

This repository is currently:
- a supervised options-trading assistant for regular markets
- a crypto spot day-trading research lab for systematic intraday strategy discovery

The live product loop is:
1. Run a live options scan.
2. Filter the scan through a replay-backed policy.
3. Apply short-term or swing playbook guardrails against actual open tracked positions.
4. Let the user choose which trade they actually took.
5. Track only those taken positions and return `HOLD` or `SELL` on demand.

The project still contains older prediction surfaces, but the active systematic research focus is now crypto day trading because the real-data loop is cheaper and easier to run honestly there than in listed options.

The day-trading side is currently a research lab, not a production workflow:
- the active lane is now a crypto spot profitability pilot in `src/lib/day-trading/crypto-engine.js`
- the older SPY/QQQ Yahoo lab remains available as `equities_legacy` in `src/lib/day-trading/engine.js`
- the UI surface is `Day Trading` under Strategy with a market selector
- deterministic replay coverage now exists via `npm run daytrading:test`
- crypto history can be backfilled via `npm run daytrading:import:crypto`
- a live crypto watchlist now exists via `npm run daytrading:watch`
- a control-first crypto experiment loop now exists via `npm run daytrading:experiments`
- the profitability pilot status can be printed via `npm run daytrading:pilot`
- manual pilot journal entries can be appended via `npm run daytrading:journal:add -- --timestamp=...`

## Current Status

- `Sprint 1` is complete: replay-backed trade policy on the scanner.
- `Sprint 2` is complete in practical form: playbooks, portfolio guardrails, simple size tiers, and a playbook exit-audit report.
- `Sprint 3` is complete: the options truth-first pass that tightened tracked-position integrity and aligned the docs/UI to the real saved artifacts.
- Live cohort scorecards are intentionally deferred until tracked outcomes and replay truth are stronger.

The important reality check:
- The full saved options replay is still weak overall.
- The latest imported-daily broad options truth in `data/options-validation/runs/latest_daily.json` has `237` priced trades, `100%` quote coverage, `0.66` profit factor, and `-10.65%` average trade P&L.
- The current replay-backed scanner policy is watch/block-oriented, not promote-ready.
- Broad options optimization is paused; options remain the manual supervised sidecar.
- The crypto research lane now has `90` days of trusted spot data and a control-first replay loop, but no strategy family is profitable yet.

## What Works Now

- Live options scan from `options_chatbot.py`.
- Replay-backed scanner policy from `wfo_optimizer.py`.
- `Short-Term` and `Swing` playbooks on the scanner.
- Portfolio guardrails using tracked open positions.
- Suggested size tiers: `starter`, `half`, `full`, or `blocked`.
- Tracked positions in local Postgres with manual entry, review, and close flows.
- Exact-contract-aware tracked-position reviews with no silent nearest-strike substitution.
- Suggested trades in local SQLite with hypothetical review and close flows.
- Current options truth bundle:
  - `wfo_results.json`
  - experiment matrix
  - metric truth report
  - live trade policy
  - playbook exit audit
- Replay reports:
  - grouped replay report
  - experiment matrix
  - metric truth report
  - live trade policy
  - playbook exit audit
- FastAPI backend plus Next.js frontend.
- Regression coverage for scan, backtest, policy, guardrails, and tracked-position review flows.
- Deterministic day-trading coverage for both the crypto lane and the older equity lane.
- A crypto spot day-trading lab with imported `1m` bars, derived `5m` strategy bars, and scheduled ET alert windows.
- An equities legacy day-trading lab that keeps the older SPY/QQQ Yahoo workflow available for comparison.
- A day-trading experiment runner that sweeps crypto and legacy equity variants while disqualifying untrusted data in strict mode.

## What Is Explicitly Not Built

- No broker integration.
- No autonomous order placement.
- No autonomous exit execution.
- No background alerts or polling loop in production form.
- No execution-grade historical options chain replay yet.

## Architecture

- `options_chatbot.py`
  - core live options scan logic
  - strategy profiles
  - market/regime logic
  - option selection
  - prediction-era utilities
- `wfo_optimizer.py`
  - historical replay
  - grouped replay reports
  - experiment matrix
  - live policy builder
  - playbook exit audit
- `python-backend/main.py`
  - FastAPI app
  - scanner API
  - backtest/report/policy/exit-audit APIs
  - tracked position APIs
  - suggested trade APIs
- `python-backend/positions_repository.py`
  - tracked-position storage
  - Postgres repo
  - in-memory repo for tests
- `python-backend/positions_service.py`
  - tracked-position creation
  - exact-contract-aware review engine
  - `HOLD` / `SELL` logic
- `python-backend/suggested_trades_repository.py`
  - suggested-trade storage
  - SQLite repo
- `src/components/predictions/PredictionsView.tsx`
  - scanner UI
  - tracked positions UI
  - suggested trades UI
  - playbook controls
  - replay policy and guardrail display
- `tests/`
  - API E2E coverage
  - strategy audit coverage
  - tracked-position review coverage

## Storage

- `chat_history.db`
  - SQLite for suggested trades and local workflow state.
- `predictions.json`
  - legacy prediction/paper-scan records.
- `wfo_results.json`
  - latest saved historical replay.
- Postgres via `DATABASE_URL`
  - tracked positions and position reviews only.

Tracked positions are intentionally isolated in Postgres. Legacy JSON prediction storage has not been migrated.

## Local Development

Frontend + backend:

```bash
npm install
uv sync
npm run dev
```

Optional local Postgres for tracked positions:

```bash
npm run db:up
```

Example local `DATABASE_URL`:

```text
postgresql://options_chatbot:options_chatbot@localhost:5432/options_chatbot
```

The backend loads `.env` and `.env.local` from the repo root when available.

## Useful Commands

Run the app:

```bash
npm run dev
```

Bring Postgres up/down:

```bash
npm run db:up
npm run db:down
```

Run the options smoke check:

```bash
npm run options:smoke
```

Run the options experiment summary:

```bash
npm run options:experiments
```

Run one local autoresearch cycle:

```bash
python scripts/autoresearch_cycle.py --slug sample --proposal docs/autoresearch/proposal-template.md
```

Run one truth-first validation pass against imported history:

```bash
python scripts/autoresearch_cycle.py --slug truth-pass --proposal docs/autoresearch/proposal-template.md --truth-lane historical_imported --watchlist-set docs/autoresearch/truth-first-champions.json --window-mode rolling_6m --require-quote-coverage 70
```

Record the daily forward-truth holdout for the current live defaults:

```bash
python scripts/record_options_forward_truth.py --source truth-first-forward --use-recommended-policy
```

Shadow-record the frozen champion cohorts only when explicitly auditing them:

```bash
python scripts/record_options_forward_truth.py --source truth-first-forward-frozen --use-recommended-policy --record-frozen-cohorts --champion-manifest docs/autoresearch/truth-first-champions.json
```

Run the day-trading deterministic harness:

```bash
npm run daytrading:test
```

Import crypto history:

```bash
npm run daytrading:import:crypto -- --days=90
```

Run the crypto validation matrix:

```bash
npm run daytrading:validate -- --bars=all --window-mode=scheduled_windows
npm run daytrading:validate -- --bars=all --window-mode=us_morning
npm run daytrading:validate -- --bars=all --window-mode=asia_open
npm run daytrading:validate -- --bars=all --window-mode=all_hours
```

Run the day-trading live watchlist:

```bash
npm run daytrading:watch
npm run daytrading:watch -- --market=equities_legacy
```

Run the control-first crypto experiment loop:

```bash
npm run daytrading:experiments
npm run daytrading:experiments -- --window-mode=us_morning
npm run daytrading:experiments -- --market=equities_legacy
```

Run tests:

```bash
npm run verify
```

## Documentation

- `docs/current-state.md`
  - current supervised options workflow, saved replay reality, and next recommended move.
- `docs/api-and-storage.md`
  - key backend endpoints, scripts, storage layers, and file map.
- `docs/options-trading-sprints.md`
  - sprint history and next planned work.
- `docs/autoresearch/`
  - local research constraints, queue, roles, proposal template, and decision log.
- `docs/autoresearch/truth-first-champions.json`
  - frozen validation cohorts, replay watchlist universe, and research-only parameter overrides for the truth-first phase.
- `docs/day-trading-current-state.md`
  - current ETF morning strategy slate, live watcher behavior, experiment evidence, and day-trading guidance.

## Recommended Next Move

Continue improving the crypto strategy research, not the product plumbing.

The options workflow is wired and truthful enough to use paper-first now, but broad options optimization is not the best place to spend primary R&D time. The highest-value next work is:
1. redesign the crypto strategy slate after the 90-day control-first results
2. keep logging options forward holdout and supervised manual usage
3. only revisit futures/perps or broader options optimization after one narrow pocket survives a stricter truth gate
