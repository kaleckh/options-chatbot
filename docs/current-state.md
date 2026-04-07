# Current State

Last updated: 2026-04-06

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
- active broad cohort directions: `call` only

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

Exactness rule for current validation semantics:
- keep aggregate replay metrics for research context
- judge profitability and promotion from the exact-contract subset only
- nearest-listed substitutions are research-only and cannot rescue weak exact-contract evidence
- current exact-contract promotion bar: at least `25` exact-contract trades, `profit_factor >= 1.05`, `avg_pnl_pct > 0`, and `directional_accuracy_pct >= 50.0`

### Live policy reality

The current live trade policy should be treated as conservative:
- imported-daily policy: `block`
- replay-backed scanner framing: `watch / blocked`, not `approved by default`
- profitability and promotion claims now fail closed unless the exact-contract subset itself clears the bar

### Forward holdout reality

Forward holdout recording has started, but the live truth tape is still too thin to matter yet:
- the ledger is readable
- there are `2` recorded sessions so far
- both sessions produced `0` candidates
- there are still no taken or closed holdout positions

So forward holdout should be collected daily, but not interpreted as meaningful strategy evidence yet.

Authoritative forward rule:
- when archived `/api/scan` picks exist, profitability is judged from `exact_archived_contract` results first
- model-exact fallback remains useful for research and gap analysis, but it does not promote the managed lane by itself

Daily maintenance should record the current live defaults by default. Shadow-recording the full frozen cohort set is still supported, but it is now an explicit audit action rather than the default daily workflow.

### Frozen cohort validation reality

The frozen truth-first cohort pack has now been narrowed to call-only `SPY` / `QQQ` broad challengers.

Current outcome:
- the old pooled broad pack is still weak on imported-daily truth and does not justify more unconstrained tuning
- put-side broad evidence is not earning the right to stay in the active challenger pack
- EV relaxation and exit-only tweaks have not separated on exact-contract imported-daily proof
- the active frozen pack is now limited to tighter entry-quality challengers with unchanged exits and unchanged exact-contract promotion requirements

That means broad pooled profitability is no longer the active target. The only question worth spending time on is whether a call-only, higher-quality index slice can beat the broad control on exact-contract imported-daily truth.

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
5. validate only the frozen `SPY` / `QQQ` call-first cohorts until better truth coverage exists

The only broad challengers still worth testing are:
1. `baseline_broad_control` as the call-side control
2. `broad_tech72`
3. `broad_direction75`
4. `broad_tech72_direction75`
5. `broad_momentum070`

Stop spending time on:
1. put-side broad challengers
2. `broad_ev7` and every `ev7` combination
3. exit-only broad tweaks such as `time_exit_pct = 33`
4. pooled broad profitability claims that depend on nearest-listed substitutions or bootstrap-only calibration

The next best repository-wide strategy step is no longer broad options optimization. The primary systematic research lane is crypto spot day trading, where we now have cheap trusted data, a 90-day replay window, and a control-first research loop. Options should stay in maintenance mode:
1. keep recording options forward holdout daily
2. keep the current options truth bundle honest and current
3. use the options product manually and supervised
4. only revisit options strategy optimization if the call-only constrained pack produces exact-contract imported-daily proof that beats the broad control

## Proof Lane Status (as of 2026-04-06)

### Canonical Evidence State

- Authoritative forward ledger: empty (no live production evidence yet)
- Archive forward ledger: empty
- Closed tracked positions: zero
- Profitability claim: **not ready** — evidence plumbing was just repaired

### What Changed (Profit Proof Sprint)

Sprint 1 (Canonical Linkage):
- Tracked positions now store explicit scan provenance (`source_scan_session_id`, `source_scan_event_key`, `source_scan_run_id`)
- `position_opened` forward ledger events are now recorded when a user takes a scan pick
- Scan-to-position matching prefers explicit provenance ids before falling back to heuristic matching
- Proof eligibility is computed at position creation time

Sprint 2 (Starvation Observability):
- `drop_counts` are now preserved through forward ledger scan funnel normalization
- Per-symbol gate diagnostics (`symbol_diagnostics`) are persisted in session notes
- Zero-candidate days without diagnostics are classified as `scanner_starvation_unresolved` instead of `no_candidates_from_scan`

Sprint 3 (Strict Proof Lane):
- `build_position_payload()` supports `require_proof_eligible=True` to block proof-lane positions missing exact-contract metadata
- Review results now include an explicit `pricing_state` field (`priced_exact`, `priced_display_only_last`, `unpriced_*`)
- A close-prefill endpoint (`GET /api/positions/{id}/close-prefill`) returns executable exit context from the latest review

Sprint 4 (Claim Readiness):
- Loop-health and claim-readiness are now distinct evaluators in `options_profit_gate.py`
- `GET /api/proof-summary` returns the canonical summary: loop-health verdict, claim-readiness verdict, evidence counts, realized metrics
- `profit_loop_automation.py` now uses the two-tier gate split for `profitability_verdict`

### Frozen SPY/QQQ Canary Procedure

Keep the following fixed for the 90-day canary run:

- **Symbols**: SPY, QQQ
- **Control cohort**: `baseline_broad_control`
- **Challenger cohort**: `broad_ev7_momentum070_exit_time33`
- **Fixed windows**: 10:00 ET, 13:30 ET
- **At most one new position per symbol per day**
- **Review once daily at a fixed time**

Daily routine:
1. Verify canonical truth bundle is present
2. Run fixed SPY/QQQ control scan
3. Run fixed raw audit scan
4. Run fixed challenger shadow scan
5. If a proof-eligible pick appears, user may take it
6. Ensure `position_opened` was written
7. Review all open canary positions at the fixed review time
8. If user closes, ensure close event was written
9. Inspect canonical summary (`GET /api/proof-summary`), not temp artifacts

### Gate Thresholds

**Loop-Health** (required for the optimizer to run):
- 10 matured eligible forward events total
- 3 matured eligible forward events per symbol
- 3 closed tracked positions total

**Claim-Readiness** (required for a profitability claim):
- 40 matured eligible forward events total
- 15 matured eligible forward events per symbol
- 20 closed exact-contract tracked positions total
- 8 closed exact-contract tracked positions per symbol
- Net profit factor >= 1.20
- Average net PnL after fees > 0
- Exact-contract capture >= 95%
