# Monthly All-Lanes Profitability Goal

Use this prompt when running a `/goal` loop to make every active regular supervised options lane profitable through monthly evidence iteration.

This goal exists because the repo now has a command center that can answer where profitability is working, where it is broken, and what evidence work is next. The loop must use that command center as the monthly operating surface instead of arguing from memory, isolated PF, raw trade count, or stale reports.

## Objective

Move the active regular supervised options lane family toward durable profitability across all lanes.

The goal is complete only when the monthly command center and its source gates show:

- every active regular lane is either profitable enough for its current stage or intentionally quarantined/diagnostic
- no live-validation or auto-track lane has negative unaddressed monthly drift
- candidate rules are entry-time-only, survive later-date/fresh-paper validation, and do not cause unacceptable winner damage
- execution realism, open-risk, portfolio, sizing, and promotion gates no longer block the chosen lane family
- exact OPRA/NBBO realized P&L and point-in-time replay support the claim
- no paper, research, midpoint, daily/EOD, stale, display-only, or backfill evidence is promoted to production proof

This is an iteration goal, not a single broad policy change. Each loop must improve one measured blocker, retire one bad rule/lane branch, or produce a concrete new replay/readback that changes the next-action queue.

## Start Every Run

Before editing code or docs:

1. Read `README.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, and `package.json`.
2. Check the worktree:

```bash
git status --short --branch
```

3. Refresh the profitability control surfaces:

```bash
npm run options:gateboard
npm run options:replay:minute-exit-readiness
npm run options:plan:minute-exit-quote-import
npm run options:replay:execution-alternatives
npm run options:replay:execution-alternative-coverage
npm run options:plan:execution-alternative-quote-import
npm run options:plan:open-risk-resolution
npm run options:audit:overfit-rule-archive
npm run options:audit:lane-quarantine-archive
npm run options:replay:risk-budget-sizing
npm run options:replay:lane-outcomes
npm run options:replay:exact-candidate-repair
npm run options:replay:chain-native-filter-relaxation
npm run options:replay:chain-native-exit-outcomes
npm run options:audit:chain-native-relaxation-archive
npm run options:profitability-layer-stack
npm run options:audit:monthly-profitability
```

4. Read the generated monthly report:

- `docs/monthly-all-lanes-profitability-audit.md`
- `data/forward-tracking/monthly_all_lanes_profitability_audit_latest.json`

If any required monthly input is missing, corrupt, stale, or reports `live_policy_change=true`, stop the profitability loop and repair the input/readback first.

## Command Center Interpretation

Use the monthly audit as the source of truth for this loop:

- `lane_leaderboard`: choose which lanes need quarantine, earn-back, or focused retest.
- `lane_dispositions`: use the required lane operating status (`profitable_candidate`, `paper_shadow`, `retest`, `needs_replay_engine`, `quarantine`, or `archive`) before spending another iteration on a lane.
- `monthly_drift`: decide whether recent performance is broken even when historical averages look good.
- `worst_buckets`: rank ticker, lane, debit-width, DTE, and fill-degradation damage.
- `candidate_rules`: reject overfit rules and keep only paper-candidate-only rules that pass the stated checks.
- `execution_realism`: treat fill attempts, no-fill, not-submitted, paper-fill, fill-discipline coverage, and replay gaps as blockers.
- `risk_portfolio`: treat open-risk governor, multilane quality, zero-bid/liquidity, sizing, and portfolio blockers as blockers.
- `oracle_ceiling`: do not claim maximum possible P&L until a trusted MFE/MAE artifact exists.
- `next_evidence_queue`: pick the next implementation slice from the top actionable items.

Do not skip the command center because another report looks more optimistic. Optimistic artifacts must be reconciled through the monthly audit before they influence lane promotion.

## Current Baseline

As of the 2026-06-08 monthly readback:

- overall status: `profitability_iteration_ready_blocked_for_promotion`
- baseline missed-pick economics: `206` rows, PF `0.34`, avg `-15.28%`
- recent month: `2026-05`, `paper_only_recent_break`
- execution realism: `ready`
- minute-exit replay readiness: `minute_exit_replay_coverage_ready`, `12` exact OPRA entry seeds, `1` position-linked seed, full minute quote coverage, and `12` true minute-exit P&L rows
- minute-exit quote import plan: `no_minute_exit_quote_seeds_to_plan`, `0` parsed demands, `0` unparsed demands, and `0` grouped ThetaData command groups because source minute readiness has full coverage
- execution-alternative coverage: `execution_alternative_replay_coverage_ready`, `12` top-spread candidates, `12` contract-replacement candidates, selected/top/replacement entry and exit quote coverage all `full`, `12` true top-spread replay P&L rows, `12` true contract-replacement P&L rows, and `0` missing quote demands
- execution-alternative quote import plan: `no_quote_demands_to_plan`, `0` command groups, `0` entry demands, `0` exit demands, and `source_quote_demand_manifest_status=no_missing_quote_demands`
- open-risk resolution plan: `open_risk_resolution_plan_ready_blocked_for_market_window`, `2` market-window review rows, live-exact negative QQQ `id=537`, display-only SELL SBUX `id=104`, `12` open regular rows, `10` negative rows, avg open P&L `-44.14%`, median `-47.58%`, and `live_policy_change=false`
- risk/portfolio: `blocked`
- risk-budget sizing replay: baseline `-$16,314.00` at PF `0.34`; `paper_shadow_only` research sizing `+$972.30` at PF `1.84`; tiered paper-shadow plus retest-quarter `+$355.19` at PF `1.16`; all blocked from live sizing by open risk and missing fresh exact realized sizing evidence
- lane outcome replay: `13` active regular lanes audited, `8` lanes with exact priced monthly outcomes, `5` missing outcome lanes, `4` no-signal lanes, and `1` lane with signals but `0` exact chain-native spread candidates
- exact-candidate selection repair: `1` target lane/date for `regular_bearish_put_primary` on `2026-05-22`, `4` signals, `0` exact candidates, META/COIN/SBUX/DIS signal tickers, and `no_chain_native_spread_passed_current_filters=4`
- chain-native filter relaxation replay: `chain_native_filter_relaxation_replay_candidates_found_diagnostic_only`, `7` diagnostic scenarios, `28` scenario rows, `4` current selected entry spreads, `24` relaxed selected entry spreads, and `0` remaining entry quote demands after the trusted `2026-05-22` META/DIS/SBUX/COIN put quote import
- chain-native exit outcome replay: `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only`, all `28` selected scenario rows exact-priced with trusted exits, `0` exit quote demands, current filters PF `0.00` / avg `-27.93%`, and best relaxed scenario PF `0.62` / avg `-9.26%`
- chain-native relaxation archive: `negative_chain_native_relaxation_branches_archived`, all `6` relaxed scenarios archived as exact-priced negative diagnostic branches with `0` unarchived negative branches
- promotion: blocked with `25` blockers
- candidate rules: `0` paper candidates, `10` rejected/overfit, `10` archived, `0` unarchived rejected rules
- lane dispositions: `1` paper-shadow lane, `4` quarantine lanes, `3` retest lanes, `5` needs-replay-engine lanes, `0` profitable-candidate lanes; all `4` quarantine lanes are archived read-only, leaving `0` unarchived quarantine lanes
- oracle ceiling: `not_available_replay_gap`
- next-evidence queue: `11` actions after removing stale candidate archive, structure/event build, execution-alternative quote-import, and minute-exit quote-import items
- live policy change: `false`

Treat this baseline as a starting snapshot, not a permanent truth. Every run must refresh the audit before relying on these counts.

## Loop Rules

1. Pick exactly one monthly blocker or lane family from the latest `next_evidence_queue`.
2. State the selected blocker, why it is higher leverage than the next two alternatives, and which command-center section proves it.
3. Implement only the smallest read-only replay, audit, repair, monitor, or test change needed to move that blocker.
4. Do not change scanner policy, stop policy, sizing, lane promotion, broker behavior, DB state, or proof thresholds unless the user explicitly asks for a separate policy-change proposal after the evidence passes.
5. If the work creates a new profitability artifact, wire it into the monthly command center rather than leaving it as an orphan report.
6. If the work changes existing artifact semantics, update focused tests and living docs.
7. Regenerate the monthly audit and compare before/after status.
8. Keep the change only if it improves a blocker, proves a lane/rule should stay rejected, or creates a replay artifact that materially sharpens the next monthly queue.

## Preferred Iteration Order

Follow the latest command-center priority, but default to this ordering when priorities tie:

1. `execute_open_risk_resolution_review_plan`: refresh row-specific open-risk reviews for live-exact negative/open-risk and display-only SELL blockers before any promotion discussion.
2. `execute_suggested_trade_review_plan`: refresh explicit suggested-trade review for rows missing current executable review.
3. `collect_exact_exit_evidence`: convert missing exact realized P&L into trusted readbacks.
4. `execute_fill_attempt_evidence_capture_plan`: capture durable no-fill/fill-attempt evidence for fresh selections.
5. `collect_fresh_paper_rows`: add fresh exact entry/exit evidence for paper/probation lanes.
6. `build_risk_budget_sizing_replay`: prove sizing from exact evidence and open-risk history before changing size tiers.
7. `build_lane_outcome_replay`: separate no-signal, no-exact-candidate, unselected, and unpriced lane blockers before making lane profitability claims.
8. `archive_overfit_rule`: explicitly retire high-PF tiny or winner-damaging rules.
9. `retest_filter`: freeze entry-time-only candidate rules and rerun later-date/point-in-time/fresh-paper validation.
10. `build_or_repair_lane_scan_hypothesis_before_pnl_replay`: repair no-signal lane coverage before treating missing outcome lanes as unprofitable.

## Direction Check

Every `3` goal iterations, and at every new month-end, pause normal lane tuning and check whether the loop is actually moving toward profitability.

Answer:

- are PF, average P&L, net dollars, or monthly drift improving for any lane?
- are blockers decreasing or becoming more specific?
- are we producing fresh exact evidence or only rearranging old research?
- is the next-evidence queue changing in useful ways?
- are we stuck behind the same blocker after multiple loops?
- is the command center missing a metric needed to choose the next best action?
- should any lane or rule be quarantined, archived, or moved to `needs_replay_engine`?

If two direction checks in a row show no measurable progress, stop lane tuning and improve the command center, replay machinery, or lane decision framework before continuing.

## Lane Profitability Acceptance

A lane can move forward only when its current evidence clears all relevant gates:

- exact marked sample is sufficient for its stage
- PF and average net P&L are positive enough for the stage
- unpriced rows are `0`
- recent monthly drift is not broken or is explained by an approved paper-only circuit breaker
- candidate rules are entry-time-only
- later-date/OOS and point-in-time replay pass
- fresh exact paper rows include exact realized P&L
- fill-attempt evidence is durable enough to judge execution realism
- open-risk governor allows live entry
- multilane portfolio quality and zero-bid/liquidity blockers pass
- lane-promotion state explicitly allows the next stage

No lane reaches `promotion_ready` from this goal alone. Promotion remains governed by the existing lane-promotion, paper-monitor, point-in-time replay, open-risk, portfolio, and proof gates.

## Rule Scoring

Classify rules exactly as the monthly audit does:

- `reject_overfit`: overfit status, non-entry-time feature, lost winners exceed deep losses avoided, thin holdout, failed later-date split, or winner-damage warning.
- `paper_candidate_only`: entry-time-only, positive PF and average, `0` unpriced rows, later-date survival, sufficient holdout, and no winner-damage warning.
- never `promotion_ready` unless all existing promotion gates already pass.

Do not rescue a rejected rule by adding post-entry, future, realized-outcome, display-mark, or manually curated features.

## Verification Ladder

Use focused checks first, then widen based on blast radius:

```bash
uv run --locked python -m py_compile scripts/build_monthly_all_lanes_profitability_audit.py tests/test_monthly_all_lanes_profitability_audit.py
uv run --locked python -m unittest tests.test_monthly_all_lanes_profitability_audit -v
uv run --locked python scripts/build_regular_options_execution_alternative_replay_readiness.py --no-write --json
uv run --locked python scripts/build_regular_options_execution_alternative_replay_coverage.py --no-write --json
uv run --locked python scripts/build_regular_options_lane_outcome_replay.py --no-write --json
uv run --locked python scripts/build_regular_options_exact_candidate_selection_repair.py --no-write --json
uv run --locked python scripts/build_regular_options_chain_native_filter_relaxation_replay.py --no-write --json
uv run --locked python scripts/build_regular_options_chain_native_exit_outcome_replay.py --no-write --json
uv run --locked python scripts/build_regular_options_chain_native_relaxation_archive.py --no-write --json
uv run --locked python scripts/build_regular_options_minute_exit_quote_import_plan.py --no-write --json
uv run --locked python scripts/build_monthly_all_lanes_profitability_audit.py --no-write --json
npm run verify:profitability-paper-gates
uv run --locked python scripts/check_living_docs_hygiene.py
git diff --check
```

If the change touches a replay engine, lane gate, scanner creation path, proof contract, repository, or frontend operator flow, add the focused tests owned by that surface. If `npm run verify:docs` fails on known unrelated stale generated artifacts, record the exact files and do not rewrite them unless the goal slice owns them.

## Done Gate

Every loop must end with:

- refreshed monthly command-center output or a clear reason it could not be refreshed
- before/after summary of the selected blocker
- files and artifacts changed
- verification commands and results
- updated `docs/WORKLOG.md`
- updates to `docs/NEXT_STEPS.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, or `docs/index.md` when their owned facts changed

Before accepting a major lane/profitability iteration, run a six-review debate:

1. Profitability strategy reviewer.
2. Proof/evidence reviewer.
3. Execution realism reviewer.
4. Risk/portfolio reviewer.
5. Overfit/statistical validation reviewer.
6. Operator workflow/readability reviewer.

Accept only if at least `4` of `6` agree and no severe blocker remains. Severe blockers include proof-source contamination, lookahead, stale/midpoint/daily/display proof claims, live-promotion leakage, unintended DB mutation, broker action, incorrect P&L, broken risk governor, or a hidden scanner policy change.

## Non-Goals

This goal does not authorize:

- live trades
- broker orders
- auto-track release
- DB mutation
- scanner policy changes
- stop-policy changes
- sizing changes
- lane promotion changes
- lower proof bars
- midpoint/daily/EOD/stale/display-only proof claims
- crypto options, Polymarket, or day-trading work
- AI commodity strategy work, except to preserve its separate boundary
