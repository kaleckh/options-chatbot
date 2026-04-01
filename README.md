# Options AI

This repository is currently a supervised options-trading assistant.

The live product loop is:
1. Run a live options scan.
2. Filter the scan through a replay-backed policy.
3. Apply short-term or swing playbook guardrails against actual open tracked positions.
4. Let the user choose which trade they actually took.
5. Track only those taken positions and return `HOLD` or `SELL` on demand.

The project still contains older prediction and day-trading research surfaces, but the active product focus is supervised options trading.

The day-trading side is currently a research lab, not a production workflow:
- intraday validation lives in `src/lib/day-trading/engine.js`
- the UI surface is `Day Trading` under Strategy
- deterministic replay coverage now exists via `npm run daytrading:test`
- a live morning watchlist now exists via `npm run daytrading:watch`
- a parameter sweep now exists via `npm run daytrading:experiments`

## Current Status

- `Sprint 1` is complete: replay-backed trade policy on the scanner.
- `Sprint 2` is complete in practical form: playbooks, portfolio guardrails, simple size tiers, and a playbook exit-audit report.
- `Sprint 3` is complete: the options truth-first pass that tightened tracked-position integrity and aligned the docs/UI to the real saved artifacts.
- Live cohort scorecards are intentionally deferred until tracked outcomes and replay truth are stronger.

The important reality check:
- The full saved options replay is still weak overall.
- The latest saved replay in `wfo_results.json` is a `2` year, `pessimistic`, `broad` run with `340` trades, `0.77` profit factor, `-9.95%` average trade P&L, and `43.5%` directional accuracy.
- The current replay-backed scanner policy is watch-oriented, not promote-ready.
- The current short-term exit audit has `0` approved trades, so the system should be treated as supervised paper-first infrastructure, not as a solved live strategy.

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
- Deterministic day-trading engine coverage for replay, risk gates, and validation persistence.
- A ranked 4-strategy ETF morning watchlist for SPY/QQQ opening-range and VWAP reclaim setups.
- A day-trading experiment runner that sweeps ETF morning variants and disqualifies synthetic fallback data in strict mode.

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

Record the daily forward-truth holdout for the frozen champion cohorts:

```bash
python scripts/record_options_forward_truth.py --source truth-first-forward --use-recommended-policy --champion-manifest docs/autoresearch/truth-first-champions.json
```

Run the day-trading deterministic harness:

```bash
npm run daytrading:test
```

Run the day-trading live watchlist:

```bash
npm run daytrading:watch
```

Run the day-trading experiment sweep:

```bash
npm run daytrading:experiments
npm run daytrading:experiments -- --preset=focus16
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

Continue improving the options research truth, not the product plumbing.

The supervised workflow is wired and truthful enough to use paper-first now, but the strategy layer is still weak. The highest-value next work is:
1. generate a broader options replay slate with comparable lanes and playbooks
2. keep logging supervised tracked or hypothetical trades manually
3. only revisit cohort promotion logic after the truth bundle finds a slice worth promoting
