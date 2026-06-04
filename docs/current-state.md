# Current State

Last updated: 2026-05-31

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

## Goal

The active browser product is still the supervised options lane family:
- surface live options ideas
- let the user log the trades they actually took
- keep tracked positions and suggested trades separate
- review and close positions manually with explicit pricing context

This remains supervised decision support, not autonomous trading.
When no playbook is supplied to a scheduled scan command, the routing fallback is `bullish_pullback_observation`, surfaced as Bullish Pullback. That fallback is not a product-priority statement; all configured regular-options lanes are peer lanes and need lane-specific profitability, risk, and proof validation. Regular supervised options playbooks default to auto-track eligibility; fresh row creation still requires market-open validation, caps-enforced scan state, `creation_eligible=true`, current guardrail rerun, and exact executable OPRA/NBBO evidence. AI Commodity remains outside this browser/tracked-position default.

AI commodity / commodity-infrastructure options is a separate non-browser proof-first strategy lane. It is not claim-ready; it waits on exact Alpaca SIP/OPRA bid/ask snapshot history before any production filter changes or profitability claims.

## Snapshot

- The mounted browser surface is still the options lane in `AppShell`, with `PredictionsView` and `StrategyView`.
- The Next route layer under `src/app/api/*` is the only browser-facing API surface in this worktree.
- The repo still contains crypto and legacy day-trading research code, but the old day-trading route files and `DayTradingLab` UI are not present in this checkout. `src/app/api/day-trading/*` exists only as empty scaffolding folders right now.
- Tracked positions are the real supervised lane and live in Postgres via `DATABASE_URL`.
- Suggested trades are the hypothetical lane and live in `chat_history.db`.
- FastAPI exposes support endpoints such as `/api/proof-summary` and `/api/positions/{position_id}/close-prefill`, but those are backend-only right now and are not mirrored through the Next proxy layer.
- FastAPI also exposes `DELETE /api/predictions/{pred_id}` without a matching Next route.

## Primary Workflow

### 1. Scanner

The scanner runs from `options_chatbot.py` and is exposed through `POST /api/scan`.

The active options workflow in the UI is ordered around:
1. live scan
2. tracked positions
3. suggested trades
4. replay and truth diagnostics

Current scanner behavior is still conservative:
- picks can carry `policy_decision` and `guardrail_decision`
- size and risk hints are surfaced when available
- replay-backed policy output is still fail-closed or watch-oriented, not trust-by-default

### 2. Tracked Positions

Tracked positions are the truth source for real supervised usage.

The current tracked-position flow is:
1. choose a live scan pick
2. enter the actual fill price and contracts
3. save it as a tracked position in Postgres
4. review open positions manually
5. get `HOLD` or `SELL` guidance plus explicit pricing context
6. close the position manually

Tracked-position reviews still prefer exact contract identity:
- exact contract symbols are stored and used first when available
- proof-lane position creation can require exact-contract metadata
- review responses now include explicit pricing-state output instead of silently substituting the nearest strike

### 3. Suggested Trades

Suggested trades are still the hypothetical lane.

They are:
- created manually from scanner picks
- stored separately in SQLite
- reviewed separately
- intentionally not mixed with real tracked positions

## Validation And Proof Snapshot

### Replay state

The latest saved `wfo_results.json` artifact in this worktree was generated on `2026-04-07T13:15:05` and reflects a `2` year `historical_imported_daily` broad replay. It remains unprofitable:
- `total_trades`: `227`
- `directional_accuracy_pct`: `63.4`
- `profit_factor`: `0.57`
- `avg_pnl_pct`: `-14.27`

That saved broad replay artifact is still useful for supervision and diagnostics, but it does not justify a profitability claim by itself.

### Bullish pullback ThetaData state

The regular `bullish_pullback_observation` lane now has newer exact trusted ThetaData intraday OPRA/NBBO research artifacts that supersede `wfo_results.json` for current profitability work:

- active universe: `59` symbols, with `CMCSA` excluded
- trusted coverage: `252` shared dates from `2025-05-22` through `2026-05-22`
- high-confidence S/A/B evidence: `108` exact quoted trades, PF `4.86`, avg `+53.22%`
- count-expanded all-59 branch: `130` exact quoted trades, PF `2.04`, avg `+24.56%`, `97.7%` quote coverage
- per-ticker audit: `docs/bullish-pullback-ticker-audit-2026-05-29.md`

This is paper-shadow research evidence, not strict proof-complete or live-capital approval. Scoped to bullish-pullback-only artifacts, the count issue remains real: the count-expanded branch is `130` exact trades and still short of a clean `200+` annual cadence.

### Regular multi-lane stock-options count state

The broader regular stock-options count question is no longer answered by bullish-pullback-only artifacts. The current multi-lane runner is `scripts/run_regular_options_multilane_portfolio.py`, with latest artifacts under `data/profitability-lab/regular-options-multilane/`.

Current read:
- combined count stack: `234` trusted intraday exact trades after strict entry-date + ticker + direction dedupe
- gap to `200`: `0`
- count gate: `passed`
- overall quality gate: `quality_pending`
- counted stack: `130` bullish-pullback core rows plus `104` strict-new Lane A rows
- important blocker: Lane A priced-only economics do not survive conservative side-aware zero-bid replay; combined Lane A falls to PF `0.85`, avg `-6.51%`, and `96.2%` coverage

Therefore, `200` is achieved only as count feasibility. It is not achieved as `200 good trades`, promotable-clean proof, production readiness, or live-capital approval.

The frozen autoresearch evaluator is the clean-promotion judge. Its baseline saw the `234` stack as scout evidence with `0` clean trades. Its latest experiment output currently falls back to the `130`-trade bullish-pullback core because the tested Lane A repair shrank Lane A below the portfolio-candidate threshold. The clean replacement baseline is `157` strict-deduped rows from core plus clean reference, leaving a `43`-trade clean gap to `200`.

### Regular options profit-cycle state

The bounded regular options profit cycle is currently blocked.

The latest saved `data/options-profit/status.json` artifact was generated on `2026-04-03T22:44:56.929432Z`. It reports:
- mandatory imported-daily truth refresh failed because source truth is stale
- zero matured eligible forward events
- zero closed tracked positions for profitability supervision

`data/options-profit/live_profile.json` still shows the incumbent managed candidates as `baseline_broad_control` for `SPY` and `QQQ` on both the call and put sides.

### AI commodity exact OPRA proof lane

The latest generated AI commodity progress readback is `data/ai-commodity-infra/progress/latest.md`, generated on `2026-06-03T20:22:59Z`.

Current state:
- lane: `ai_commodity_infra_observation`
- proof provider: `alpaca:sip:opra`
- proof source label: `alpaca_opra_daily_snapshot`
- scan/proof universe: `24` symbols from `data/ai-commodity-infra/universe.json`
- exact proof window: `3` of `100` shared quote dates, `2026-05-20` through `2026-05-22`
- verification gate: `not_verified`
- live scan candidates in the latest readback: `0`
- latest guarded capture target: `2026-05-29`, attempted again on `2026-06-03`; capture returned `no_rows_captured`, all `24` target symbols remained missing, the exact proof window stayed at `3` / `100`, local exact store refresh cannot advance history depth, and the next evidence action is `repair_full_scan_universe_capture_and_proof_alignment`

The current blocker is history depth, not a failed profitability result. Exact replay is blocked until enough shared OPRA bid/ask dates exist. Production filter changes and variant promotion remain locked until exact OPRA replay can measure the changes.

The generated runbook's current selected step is:
1. guarded capture with `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-29`
2. readback with `python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest`
3. repair capture gaps before any replay or filter work if shared quote dates do not advance from `3` to `4`

### Proof-lane state

`evaluate_claim_readiness()` is currently `not_claim_ready`.

The current blockers are straightforward:
- `0` matured eligible forward events, versus a `40` event claim threshold
- `0` closed exact-contract tracked positions, versus a `20` position claim threshold
- no realized net profitability evidence yet
- exact-contract capture is still `0%` in the current canonical proof summary

The canonical proof summary exists in FastAPI at `/api/proof-summary`, but the browser app does not proxy it yet.

## What Is Ready vs Not Ready

### Ready

- supervised `scan -> take -> review -> close` workflow
- tracked-position storage and exact-contract-aware review
- suggested-trade storage and review
- replay and truth diagnostics in the strategy surface
- options profit-cycle state artifacts under `data/options-profit/*`
- AI commodity OPRA proof-lane tracking with full scan/proof universe alignment
- regular stock-options count feasibility: the current multi-lane stack clears `200` trusted intraday exact rows, but remains quality-gated

### Not ready

- trust-by-default options deployment
- promotable-clean or production-ready regular stock-options profitability claims
- claim-ready forward evidence for `SPY` and `QQQ`
- AI commodity profitability claims or filter tuning before exact OPRA replay unlocks
- a mounted day-trading browser surface in this worktree

## Current Recommendation

Use the options system as supervised maintenance infrastructure, not as a solved strategy.

That means:
1. scan live ideas
2. log real tracked positions only when they were actually taken
3. use suggested trades for hypothetical evaluation
4. review and close positions manually
5. treat policy output as conservative until the truth inputs are fresh again and the proof lane accumulates real exact-contract evidence

For the separate day-trading research lane, read `docs/day-trading-current-state.md`, but treat it as code and research context rather than the current browser product.

For the AI commodity proof lane, follow `docs/NEXT_STEPS.md` and the generated `data/ai-commodity-infra/progress/latest.md` runbook. Keep the lane locked to exact Alpaca OPRA proof until the shared-date gate and replay gates pass.
