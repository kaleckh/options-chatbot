# Current State

Last updated: 2026-07-02

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

### Regular options historical filtered-audit state

The current regular-options historical audit chain is the frozen 13-symbol deterministic materializer, not the old `wfo_results.json` broad replay. The relevant generated sources are:
- `data/contracts/regular-options-frozen-filtered-policy-v1.json`
- `data/contracts/regular-options-audit-window-consumption-registry.json`
- `data/contracts/regular-options-filtered-forward-evidence-bar-v1.json`
- `data/profitability-lab/regular-options-historical-simulated-forward-audit/latest.json`
- `data/profitability-lab/regular-options-historical-profitability-filter-iteration/latest.json`
- `data/profitability-lab/regular-options-historical-filtered-simulated-forward-audit/latest.json`
- `data/profitability-lab/regular-options-historical-frozen-scanner-replay-adapter/latest.json`

The frozen filtered policy is `historical_filtered_candidate_policy_v1`, filter `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906`, with condition hash `3b10d0306800e1a203480b80e4fafda03d5e1b6443d8d294cbf8ff7f20324967`. It is the forward tracker's matching authority; the latest filtered-audit artifact is context/drift readback only.

The audit window `2026-02` through `2026-05` is recorded as consumed. Rerunning the historical profitability filter iteration over that overlapping audit window cannot mint a new accepted filter. The latest iteration reports `selection_permitted=false`, `accepted_filter_count=0`, and status `blocked_audit_window_already_consumed_for_selection`.

The corrected statistics are stricter than the original filtered-audit readback:
- broad historical audit: `2,680` deduped exact rows after removing `171` duplicates; latest-audit percent cluster PF lower bound `0.72`; USD cluster PF lower bound `1.02`; status `blocked_historical_simulated_forward_audit`
- frozen filtered audit: train `237` rows, percent cluster PF lower bound `0.93`, USD cluster PF lower bound `0.80`; audit `57` rows, percent cluster PF lower bound `1.15`, USD cluster PF lower bound `1.89`; status `blocked_historical_filtered_simulated_forward_audit`
- adapter economics: `2,972` selected candidates with fee-adjusted USD fields, `$0.65` per contract-leg fee default, and `267` floored exit-value rows

The filtered audit's positive audit-window labels are selection-conditioned because the v1 filter was selected using train-and-audit success over a searched family of `162` filters. Those audit metrics are not unbiased out-of-sample estimates and do not constitute accepted profitability, fresh forward proof, scanner parity, live validation, auto-track permission, broker permission, proof-bar change, or promotion.

### Regular options forward state

Prospective matching for the frozen v1 filtered policy is tracked by `docs/regular-options-filtered-forward-paper-shadow-tracker.md`. The tracker is dashboard/reporting evidence only; it currently has `0` matched/open rows and cannot approve trades or profitability.

The prospective tracker now reports against `data/contracts/regular-options-filtered-forward-evidence-bar-v1.json`. Current progress is `0` / `30` completed forward paper-shadow rows, `0` / `8` ticker-week clusters, `0` / `3` calendar months, and `evaluation_permitted=false`, so no bootstrap evaluation is run. The tracker also discloses that historical rows came from the deterministic materializer while forward rows come from production scheduled scan sessions plus scanner gates; these are a new distribution, not a continuation of the historical sample.

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
