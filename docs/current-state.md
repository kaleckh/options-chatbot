# Current State

Last updated: 2026-04-03

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Goal

The active product goal is still simple:
- show live options trades
- let the user mark which one they actually took
- track only those taken positions
- review them manually and return `HOLD` or `SELL`

This is supervised decision support, not autonomous trading.

## Repository Split

The repo now has a deliberate split:
- options are the supervised product lane and remain in maintenance mode
- crypto day trading is the active systematic research lane

For the crypto side, read:
- `docs/day-trading-current-state.md`

## Primary Workflow

### 1. Scanner

The scanner runs from `options_chatbot.py` and is exposed through `POST /api/scan`.

The real options workflow now starts here and is ordered this way in the UI:
1. `Scanner`
2. `Tracked Positions`
3. `Suggested Trades`
4. legacy analytics tabs after that

The scanner supports:
- `Replay-Backed Focus` vs `All Qualifying`
- playbooks such as `short_term` and `swing`
- portfolio guardrails based on actual open tracked positions

Every scan pick can carry:
- `policy_decision`: `approved`, `watch`, or `blocked`
- `guardrail_decision`: `clear`, `caution`, or `blocked`
- `suggested_size_tier`
- replay rationale and warnings

The important truth: the current replay-backed policy is not in promote mode. It is block/watch-oriented.

### 2. Tracked Positions

Tracked positions are the truth source for real supervised usage.

The current tracked-position flow is:
1. choose a live scan pick
2. enter the actual fill price and contracts
3. save it as a tracked position in Postgres
4. review open positions manually
5. get `HOLD` or `SELL`
6. mark the position closed manually

Tracked-position reviews now prefer exact contract identity:
- if the scan pick included an exact contract symbol, that is persisted and used first
- if not, the review falls back to the exact stored strike only
- silent nearest-strike substitution is disabled
- if the exact contract cannot be priced, the review stays unpriced and returns warnings

### 3. Suggested Trades

Suggested trades are still the hypothetical lane.

They are:
- created manually from scanner picks
- stored separately in SQLite
- reviewed separately
- intentionally not mixed with real tracked positions

This is the paper-evaluation lane, not the real-position truth lane.

## Active Truth-First Validation Phase

Autoresearch is now in `truth-first-validation-phase`:
- mode: `validation`
- search: frozen
- required baseline control: `baseline_broad_control`
- active validation scope: `SPY`, `QQQ`

That narrowed scope is intentional. Imported real-data validation currently exists only for `SPY` and `QQQ`, so broader-watchlist strategy ideas are historical context, not validated truth, until more real coverage exists.

## Current Truth Bundle

These artifacts are the source of truth for options messaging right now:
- `wfo_results.json`
- imported daily validation results
- options experiment matrix
- options metric truth report
- live trade policy
- playbook exit audit

### Saved synthetic baseline

The current saved synthetic baseline in `wfo_results.json` is:
- `run_at`: `2026-03-31T02:26:26`
- `lookback_years`: `1`
- `pricing_lane`: `pessimistic`
- `playbook`: `broad`
- `total_trades`: `7`
- `priced_trade_count`: `7`
- `truth_source`: `synthetic_research`
- `directional_accuracy_pct`: `14.3`
- `profit_factor`: `0.14`
- `avg_pnl_pct`: `-56.94`
- calibration state: `bootstrap_only`

That means the current synthetic baseline is not strong enough to guide broad strategy redesign by itself.

### Imported daily validation reality

The current imported daily validation in `data/options-validation/runs/latest_daily.json` is:
- `truth_source`: `historical_imported_daily`
- validation universe: `SPY`, `QQQ`
- `priced_trades`: `237`
- `unpriced_trades`: `0`
- `quote_coverage_pct`: `100.0`
- exact target-contract matches: `57`
- nearest-listed substitutions: `180`
- `directional_accuracy_pct`: `53.6`
- `profit_factor`: `0.66`
- `avg_pnl_pct`: `-10.65`
- `promotion_status`: `block`

That means free daily real-data validation is now adequately covered for the broad imported-daily lane, and it still says the broad options strategy is weak. This is no longer just a support-gap story for the broad baseline.

### Live policy reality

The current live trade policy should be treated as conservative:
- imported-daily policy: `block`
- replay-backed scanner framing: `watch / blocked`, not `approved by default`

### Forward holdout reality

Forward holdout recording has started, but the live truth tape is still too thin to matter yet:
- the ledger is readable
- there are `2` recorded sessions so far
- both sessions produced `0` candidates
- there are still no taken or closed holdout positions

So forward holdout should be collected daily, but not interpreted as meaningful strategy evidence yet.

Daily maintenance should record the current live defaults by default. Shadow-recording the full frozen cohort set is still supported, but it is now an explicit audit action rather than the default daily workflow.

### Frozen cohort validation reality

The frozen truth-first cohort pack has now been run under the narrowed `SPY` / `QQQ` scope.

Current outcome:
- all frozen cohorts currently resolve to `historical_imported_daily` as the authoritative lane
- all frozen cohorts still end in `validation_outcome = insufficient_support`
- `baseline_broad_control` and `broad_ev7_momentum070` only have `5` priced imported trades, with `1` exact contract match and `4` nearest-listed substitutions
- the broader frozen challengers clear more trades, but imported-daily quote coverage is still only `66.0%`, below the `70.0%` sufficiency floor

That means no frozen cohort has earned promotion or even a clean “strategy redesign is next” verdict yet. The current blocker is still support quality.

## What Is Ready vs Not Ready

### Ready

- supervised `scan -> take -> review -> close` workflow
- replay-backed policy labels in the scanner
- tracked-position storage and review
- imported daily real-data validation for `SPY` and `QQQ`
- Autoresearch truth guards and closure workflow

### Not ready

- trust-by-default options deployment
- replay-approved short-term or swing playbooks
- broad-watchlist real-data validation
- execution-grade intraday options pricing realism
- a cohort that survives synthetic screening, imported truth, and forward holdout

## Current Recommendation

Use the options system as supervised maintenance infrastructure, not as a solved strategy.

That means:
1. scan live ideas
2. optionally log real tracked positions or hypothetical suggested trades
3. review and close them manually
4. treat current policy output as block/watch-oriented
5. validate only the frozen `SPY` / `QQQ` cohorts until better truth coverage exists

The next best repository-wide strategy step is no longer broad options optimization. The primary systematic research lane is crypto spot day trading, where we now have cheap trusted data, a 90-day replay window, and a control-first research loop. Options should stay in maintenance mode:
1. keep recording options forward holdout daily
2. keep the current options truth bundle honest and current
3. use the options product manually and supervised
4. only revisit options strategy optimization if a narrower repeatable pocket appears in real or forward evidence
