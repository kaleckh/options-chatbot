# Next Steps

Last updated: 2026-06-14

## Current Sprint Blockers From June 9 Audit

Current read:
- metric truth repairs are implemented: WFO charges slippage/commission, expiry settlement uses expiry-day close, unknown evidence quarantines, PF sentinels are removed, headline win rate separates full hits from directional accuracy, and dormant lenient quote/leg-fee footguns are defused.
- WFO friction replay diff is documented at `docs/wfo-friction-replay-diff-2026-06-09.md`.
- fresh executable evidence is still blocked at `0` exact realized P&L rows and `0` promotion-ready rows; the named defect report is `docs/fresh-executable-evidence-defect-report-2026-06-09.md`.
- the specific fresh-evidence gate is `scripts/build_regular_options_fresh_evidence_loop.py`: `summary.entry_evidence_status_counts.fill_attempt_missing=28`, `summary.evidence_bridge_status_counts.non_executable_entry_blocked=20`, `summary.evidence_bridge_status_counts.paper_probation_exact_entry_required=8`, and `summary.evidence_bridge_status_counts.exact_exit_pnl_required=1`.
- the linked exact-entry row needing exit evidence is QQQ `position_id=537`, with `evidence_bridge_status=exact_exit_pnl_required` and `realized_pnl_status=missing_realized_pnl`.
- open risk is no longer blocked: ThetaTerminal was reachable, a targeted ThetaData exact-expiration import wrote batch `2124` for 2026-06-08 QQQ/SBUX rows, Alpaca OPRA latest snapshots supplied the current QQQ/SBUX quote window, SBUX `id=104` closed from exact side-aware executable exit evidence, and QQQ `id=537` has a fresh exact executable HOLD review. `scripts/build_regular_options_open_risk_resolution_plan.py` now reports `open_risk_resolution_plan_clear`.
- the regular profit-loop broad intraday artifact is still blocked for policy use by weak quote coverage: `quote_coverage_pct=20.7`. Treat this as a mechanical data-pipeline repair during the strategy-iteration moratorium, not a reason to tune strategy gates or promote profitability.

Next actions:

1. Collect legitimate exact OPRA/NBBO exit evidence for QQQ `id=537` only when stop, target, time-exit, or another policy-defined exit condition fires; do not close a current HOLD row to manufacture realized evidence.
2. Capture durable fill-attempt evidence for the `4` missing fresh-selection rows and exact entry evidence for the `8` paper/probation rows without loosening guardrails.
3. Resume fresh-evidence collection until there are at least `20` exact realized rows, or keep the named-gate defect report current if the funnel remains blocked after 10 trading sessions.
4. Repair the broad intraday profit-loop quote coverage path until the active artifact clears the policy coverage blocker; do not count low-coverage broad artifacts as proof.
5. Run a ThetaData history-depth check for the trusted intraday OPRA/NBBO cache before interpreting missing older regime buckets as strategy behavior.
6. Decide whether to buy or build a cheap EOD long-history falsification dataset for broad pre-screening only; EOD evidence must stay below the production proof bar.
7. Pre-register the next `6`-week frozen paper cohort dates and champion family before any protected holdout consumption.

## Documentation Hygiene

Current read:
- global agent behavior rules live in `C:\Users\kalec\AGENTS.md` and `C:\Users\kalec\CLAUDE.md`
- repo-specific agent startup and evidence rules live in `AGENTS.md`
- living-doc ownership, generated-artifact, and source-of-truth hygiene rules live in `docs/living-docs-hygiene.md`
- project orientation now starts with the generated pathway map at `docs/project-operating-map.md` and machine-readable registry at `data/contracts/project-pathway-registry.json`
- current "where are we blocked?" readback lives in `docs/project-operator-gateboard.md` and `data/forward-tracking/project_operator_gateboard_latest.json`
- `npm run verify:docs` now runs generated artifact checks, including the candidate lifecycle contract, the final remediation closure pack check, and `scripts/check_living_docs_hygiene.py`
- latest Markdown placement audit: `docs/markdown-audit-2026-05-31.md`

1. When adding new Markdown, update `docs/index.md` only for living docs or reports that change the current decision surface. Keep generated research reports beside their source artifacts under `data/` or `research_runs/`.

## Operational Survivability

Current read:
- `docs/evidence-operations.md` owns the authoritative evidence-host, backup, heartbeat, daily-ops, and retention runbook.
- `data/contracts/evidence-host-policy.json` declares `KaesDevice` as the current authoritative host for Postgres tracked positions, `chat_history.db`, `data/options-validation/forward_tracking_authoritative.db`, and `data/options-validation/options_history.db`.
- scheduled scans now write host/commit/run provenance and a local heartbeat at `data/forward-tracking/scheduled_scan_heartbeat_latest.json`; scan logging fails closed before evidence writes on a non-authoritative host.
- the gateboard and monthly profitability audit surface `days_since_last_scheduled_scan` and fail after more than `2` market days without a completed scheduled scan.
- backups write ignored bundles under `data/backups/` with `14`-day local retention; weekly off-machine copy requires `OPTIONS_BACKUP_WEEKLY_COPY_DIR`.
- FastAPI startup asserts the single-worker assumption unless `OPTIONS_ALLOW_MULTI_WORKER_BACKEND` is explicitly set.

1. Add these commands to the scheduled Windows task or the operator routine:

```powershell
npm run evidence:backup
npm run daily-ops
npm run options:gateboard
```

2. Add weekly off-machine copy after setting a target:

```powershell
$env:OPTIONS_BACKUP_WEEKLY_COPY_DIR = "D:\options-evidence-backups"
npm run evidence:backup:weekly
```

3. Before interpreting missing fresh rows as strategy behavior, check scheduler health:

```powershell
npm run scan:heartbeat
```

4. Keep non-authoritative machines read-only for the named evidence stores. If the authoritative host changes, update `data/contracts/evidence-host-policy.json`, the scheduled task, and the off-machine backup target in the same operator change.

## Project Operating Map And Gateboard

Current read:
- `scripts/generate_project_pathway_registry.py` owns the stable six-pathway model: Data, Candidate, Evidence, Profitability, Promotion, and Operator.
- `npm run docs:project-pathway-registry` writes `docs/project-operating-map.md` and `data/contracts/project-pathway-registry.json`; `npm run verify:docs` checks these generated artifacts for drift.
- `npm run options:gateboard` writes the current read-only gateboard at `docs/project-operator-gateboard.md` and `data/forward-tracking/project_operator_gateboard_latest.json`.
- latest gateboard status is `safe_blocked_no_live_release`: Data Path `pass`, Candidate Path `pass`, Evidence Path `blocked`, Profitability Path `blocked`, Promotion Path `blocked`, Operator Path `blocked`.
- latest gateboard data/profit split: repository integrity is clean (`0` hard violations, `0` diagnostics), candidate lifecycle is visible (`34` fresh candidates), but fresh exact realized P&L is `0`, promotion-ready rows are `0`, broad untracked missed-pick economics are `206` rows / PF `0.32` / avg `-16.54%`, lane state is `13` diagnostic / `1` paper-probation / `0` live-validation / `0` auto-track, open-risk governor is passing, suggested-trade review has attention on `id=138`, and paper-shortlist eligible count is `0`.
- latest candidate outcome ledger status is `ledger_collect_exact_evidence` with `104` ledger rows: `1` suggested-trade review refresh, `1` exact-exit evidence row for QQQ `id=537`, `5` paper-review create/link rows, `8` paper/probation exact-entry rows, `4` missing fill-attempt evidence rows, `16` no-longer-matched/archive rows, `21` Tier A fresh-bridge waits, `39` historical repair rows, and `9` guardrail/lane-mismatch rows. It is read-only and has `live_policy_change=false`.
- latest stale candidate archive is `stale_candidates_archived`: all `16` no-longer-matched/archive ledger rows are archived as read-only stale branches, with `0` archive exceptions, lane counts `quality90_debit55_canary=2`, `swing=9`, `tracked_winner_observation=1`, `tracked_winner_primary=1`, and `volatility_expansion_observation=3`, ticker counts `QQQ=7` and `SPY=9`, `0` production proof-ready rows, and `live_policy_change=false`. It is generated by `npm run options:audit:stale-candidate-archive` at `docs/regular-options-stale-candidate-archive.md` and `data/forward-tracking/regular_options_stale_candidate_archive_latest.json`; it removes the generic `wait_for_fresh_match_or_archive_candidate` monthly queue item without creating trades, mutating DB rows, changing scanner policy, or reactivating stale candidates.
- latest open-risk resolution plan is `open_risk_resolution_plan_clear`: `0` row-specific review actions, `0` display-only SELL rows, live-exact QQQ `id=537` resolved as a fresh exact HOLD, `5` open regular rows, `5` negative rows, avg open P&L `-54.51%`, median `-57.66%`, and `live_policy_change=false`. It is generated by `npm run options:plan:open-risk-resolution` at `docs/regular-options-open-risk-resolution-plan.md` and `data/forward-tracking/regular_options_open_risk_resolution_plan_latest.json`; it does not submit orders or auto-close display-only marks.
- latest suggested-trade review plan is `suggested_trade_review_plan_ready_blocked_for_market_window`: `1` row-specific review action for open suggested trade `id=138` / ticker `AAA`, `1` missing review row, `0` executable close-ready rows, `1` market-window-required row, and `live_policy_change=false`. It is generated by `npm run options:plan:suggested-trade-review` at `docs/regular-options-suggested-trade-review-plan.md` and `data/forward-tracking/regular_options_suggested_trade_review_plan_latest.json`; it replaces the generic `refresh_suggested_trade_review` monthly queue item but does not create trades, submit orders, mutate `chat_history.db`, or auto-close from missing/stale/display-only review marks.
- latest fill-attempt evidence capture plan is `fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection`: `4` row-specific actions from `2026-06-05`, all missing durable fill-attempt evidence, with lanes `short_term=1`, `swing=2`, `volatility_expansion_observation=1`, tickers `QQQ=2` and `SPY=2`, `497` source fill-attempt rows, and `live_policy_change=false`. It is generated by `npm run options:plan:fill-attempt-evidence-capture` at `docs/regular-options-fill-attempt-evidence-capture-plan.md` and `data/forward-tracking/regular_options_fill_attempt_evidence_capture_plan_latest.json`; it replaces the generic missing-fill bucket but does not create trades or backfill broker fills.
- latest ThetaTerminal runbook is `docs/thetadata-terminal-runbook.md`: local v3 terminal runs from `C:\Users\kalec\Downloads\ThetaTerminalv3.jar` on `http://127.0.0.1:25503`, and quote-import loops must treat connection-refused / `WinError 10061` as feed-down rather than evidence exhaustion. Start/probe the terminal before archiving no-match contract branches.
- latest all-20 profitability layer stack is `all_20_layers_wired_research_blocked`: `20` / `20` layers wired, `7` ready, `7` collecting, `6` blocked, and `13` blocked-or-collecting. Implementation readback is `5` built, `4` built-blocked, `8` built-collecting, `2` built-replay-coverage blocked, and `1` built-replay-coverage ready; top-spread, contract-replacement, and minute-exit replay coverage are now ready. It is generated by `npm run options:profitability-layer-stack` at `docs/regular-options-profitability-layer-stack.md` and `data/forward-tracking/regular_options_profitability_layer_stack_latest.json`, with `live_policy_change=false`.
- latest minute-exit replay readiness is `minute_exit_replay_coverage_ready`: `12` exact OPRA entry seeds, `1` position-linked seed, full minute quote coverage, read-only side-aware engine status `read_only_side_aware_engine_partial`, `12` true minute-exit P&L rows, and decision counts `hold_for_current_open_risk_review=1` plus `reject_production_use_without_fill_or_position_link=11`. It is generated by `npm run options:replay:minute-exit-readiness` at `docs/regular-options-minute-exit-replay-readiness.md` and `data/forward-tracking/regular_options_minute_exit_replay_readiness_latest.json`, with `live_policy_change=false`.
- latest minute-exit quote import plan is `no_minute_exit_quote_seeds_to_plan`: source minute readiness has full quote coverage and `12` true minute-exit P&L rows, so there are `0` parsed demands, `0` unparsed demands, and `0` grouped ThetaData command groups. It is generated by `npm run options:plan:minute-exit-quote-import` at `docs/regular-options-minute-exit-quote-import-plan.md` and `data/forward-tracking/regular_options_minute_exit_quote_import_plan_latest.json`; it does not change stops, scanner policy, sizing, broker behavior, proof bars, promotion, or open-risk status.
- latest execution-alternative replay readiness is `blocked_ready_seed_missing_execution_alternative_replay_engine`: `12` top-spread replay seeds, `12` contract-replacement seeds, `0` true top-spread/contract-replacement P&L rows, and `live_policy_change=false`. It is generated by `npm run options:replay:execution-alternatives` at `docs/regular-options-execution-alternative-replay-readiness.md` and `data/forward-tracking/regular_options_execution_alternative_replay_readiness_latest.json`.
- latest execution-alternative replay coverage is `execution_alternative_replay_coverage_ready`: `12` top-spread candidates and `12` contract-replacement candidates, selected/top/replacement entry and exit quote coverage all `full`, `12` true top-spread replay P&L rows, `12` true contract-replacement P&L rows, and `0` missing quote demands. It is generated by `npm run options:replay:execution-alternative-coverage` at `docs/regular-options-execution-alternative-replay-coverage.md` and `data/forward-tracking/regular_options_execution_alternative_replay_coverage_latest.json`, with `live_policy_change=false`.
- latest execution-alternative quote import plan is `no_quote_demands_to_plan`: the source execution-alternative coverage manifest has `0` missing quote demands, `0` command groups, `0` entry demands, `0` exit demands, and `source_quote_demand_manifest_status=no_missing_quote_demands`. It is generated by `npm run options:plan:execution-alternative-quote-import` at `docs/regular-options-execution-alternative-quote-import-plan.md` and `data/forward-tracking/regular_options_execution_alternative_quote_import_plan_latest.json`, with `live_policy_change=false`.
- latest structure-specific harness is `structure_specific_harness_built_collecting`: `12` candidate-shown rows are separated as `vertical_spread`, `10` proof-live exact entry rows, `1` paper-fill-recorded row, and `12` true structure-specific P&L rows consumed from trusted ThetaData OPRA/NBBO minute-exit replay. Decisions are `hold_for_current_open_risk_review=1` and `reject_production_use_without_fill_or_position_link=11`; the remaining blocker is `single_leg_or_other_multileg_samples_missing`. It is generated by `npm run options:replay:structure-specific-harness` at `docs/regular-options-structure-specific-harness.md` and `data/forward-tracking/regular_options_structure_specific_harness_latest.json`; it remains diagnostic/proof-only and does not become production proof, promotion, broker-fill proof, or open-risk resolution.
- latest event data spine is `event_data_spine_built_collecting`: `12` candidate-shown rows over `3` tickers (`QQQ=6`, `SPY=5`, `IWM=1`) and `4` playbooks, `10` proof-live exact entry rows, `1` paper-fill-recorded row, `0` event-annotated rows, `12` missing event annotations, `0` true event replay P&L rows, and `0` post-event vol-crush replay P&L rows. It is generated by `npm run options:replay:event-data-spine` at `docs/regular-options-event-data-spine.md` and `data/forward-tracking/regular_options_event_data_spine_latest.json`; it removes the generic monthly `build_event_data_spine` action but remains diagnostic/proof-only until durable event-calendar annotations and exact executable entry/fill/exit P&L exist.
- latest overfit rule archive is `overfit_rules_archived`: `10` / `10` rejected candidate rules archived, `0` unarchived rejected rules, `0` paper-candidate rules, and `live_policy_change=false`. It is generated by `npm run options:audit:overfit-rule-archive` at `docs/regular-options-overfit-rule-archive.md` and `data/forward-tracking/regular_options_overfit_rule_archive_latest.json`.
- latest lane quarantine archive is `lane_quarantines_archived`: `4` / `4` quarantined negative lanes archived (`bullish_momentum`, `bullish_pullback_observation`, `short_term`, and `swing`), `0` unarchived quarantine lanes, and `live_policy_change=false`. It is generated by `npm run options:audit:lane-quarantine-archive` at `docs/regular-options-lane-quarantine-archive.md` and `data/forward-tracking/regular_options_lane_quarantine_archive_latest.json`.
- latest risk-budget sizing replay is `sizing_replay_built_collect_fresh_exact_evidence`: `206` priced untracked source rows, baseline one-contract net `-$18,755.00` at PF `0.32`, best research scenario `paper_shadow_only` net `+$971.30` at PF `1.83`, and tiered paper-shadow/full plus retest-quarter net `+$381.69` at PF `1.17`. Promotion remains false because rows are historical research/backfill rather than production sizing proof, fresh exact realized sizing evidence is required, and any sizing change needs a separate promotion gate. It is generated by `npm run options:replay:risk-budget-sizing` at `docs/regular-options-risk-budget-sizing-replay.md` and `data/forward-tracking/regular_options_risk_budget_sizing_replay_latest.json`, with `live_policy_change=false`.
- latest lane outcome replay is `lane_outcome_replay_built_collecting`: `13` active regular supervised lanes audited, `8` have exact priced monthly outcomes, and `5` still lack monthly outcome economics. Of the `5`, `4` have no signal candidates in the monthly window (`bearish_defensive`, `bearish_index_put_observation`, `quality90_debit55_canary`, and `range_breakout_observation`), while `regular_bearish_put_primary` has `4` signals but `0` exact chain-native spread candidates. It is generated by `npm run options:replay:lane-outcomes` at `docs/regular-options-lane-outcome-replay.md` and `data/forward-tracking/regular_options_lane_outcome_replay_latest.json`, with `live_policy_change=false`.
- latest lane scan hypothesis repair is `lane_scan_hypothesis_repair_built_collecting`: it covers the `4` no-signal lanes, finds `3` predeclared proof-only replacement candidates across `2` lanes (`bearish_index_put_observation` and `range_breakout_observation`), and leaves `2` lanes (`bearish_defensive` and `quality90_debit55_canary`) without a predeclared causal replacement candidate. Production proof-ready replacement candidates remain `0`, fresh exact scan retest rows remain `0`, true lane outcome P&L rows remain `0`, and blockers are `fresh_exact_scan_retest_rows_missing`, `true_lane_outcome_pnl_rows_missing`, and `some_no_signal_lanes_lack_predeclared_replacement_candidate`. It is generated by `npm run options:plan:lane-scan-hypothesis-repair` at `docs/regular-options-lane-scan-hypothesis-repair.md` and `data/forward-tracking/regular_options_lane_scan_hypothesis_repair_latest.json`, with `live_policy_change=false`.
- latest exact-candidate selection repair is `exact_candidate_selection_repair_targets_ready`: `1` target lane/date, `4` signal candidates, `0` exact candidates, and reject reason `no_chain_native_spread_passed_current_filters=4` for `regular_bearish_put_primary` on `2026-05-22` with signal tickers META, COIN, SBUX, and DIS. It is generated by `npm run options:replay:exact-candidate-repair` at `docs/regular-options-exact-candidate-selection-repair.md` and `data/forward-tracking/regular_options_exact_candidate_selection_repair_latest.json`, with `live_policy_change=false`.
- latest chain-native filter relaxation replay is `chain_native_filter_relaxation_replay_candidates_found_diagnostic_only`: after importing trusted ThetaData OPRA/NBBO `2026-05-22` put entry-window quotes for META, DIS, SBUX, and COIN, the `regular_bearish_put_primary` target has `4` signal candidates, `7` predeclared scenarios, `28` scenario rows, `4` current selected entry spreads, `24` relaxed selected entry spreads, `0` remaining entry quote demands, and all `28` scenario rows selected. It is generated by `npm run options:replay:chain-native-filter-relaxation` at `docs/regular-options-chain-native-filter-relaxation-replay.md` and `data/forward-tracking/regular_options_chain_native_filter_relaxation_replay_latest.json`, with `live_policy_change=false`.
- latest chain-native exit outcome replay is `chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only`: all `28` selected scenario rows have trusted OPRA/NBBO exact exit P&L, `0` exit quote demands remain, current filters priced `4` rows at PF `0.00` / avg `-27.93%`, and the best relaxed scenario is `widen_dte_window_only` with PF `0.62`, avg `-9.26%`, and net `-$1,154.00`. It is generated by `npm run options:replay:chain-native-exit-outcomes` at `docs/regular-options-chain-native-exit-outcome-replay.md` and `data/forward-tracking/regular_options_chain_native_exit_outcome_replay_latest.json`, with `live_policy_change=false`.
- latest chain-native relaxation archive is `negative_chain_native_branches_archived`: `7` / `7` exact-negative diagnostic branches are archived (`1` current and `6` relaxed), `0` unarchived negative branches remain, and `live_policy_change=false`. It is generated by `npm run options:audit:chain-native-relaxation-archive` at `docs/regular-options-chain-native-relaxation-archive.md` and `data/forward-tracking/regular_options_chain_native_relaxation_archive_latest.json`.
- latest exhausted contract archive is `exhausted_contract_target_archived`: `8` current-source exhausted exact contract/date targets are archived after repeated exact-date no-match attempts, with `1` newly archived in the latest run and `38` eligible exhausted targets remaining. Archived targets include `GOOGL260102C00355000` and `GOOGL260102C00360000` on `2025-12-22`, `GOOGL260102C00365000` on `2025-12-23`, `GOOGL260213C00350000` on `2026-02-12`, `GOOGL260306C00365000` on `2026-02-27`, and `GOOGL260306C00360000` on `2026-03-02` from `tracked_winner_chain_native_qqq_time80_intraday`, plus `GOOGL260102C00355000` and `GOOGL260102C00360000` on `2025-12-22` from `tracked_winner_cheap_debit_continuity_v1`; archived attempts have `0` exact rows and `0` total rows. It is generated by `npm run options:audit:exhausted-contract-archive` at `docs/regular-options-exhausted-contract-archive.md` and `data/profitability-lab/regular-options-exhausted-contract-archive/latest.json`; it does not count no-match evidence as proof and does not change scanner policy, contract selection, stops, sizing, lane promotion, broker behavior, or trading rows.
- latest monthly all-lanes profitability audit is `profitability_iteration_ready_blocked_for_promotion`: baseline missed-pick economics are `206` rows, PF `0.32`, avg `-16.54%`; recent month `2026-05` is `paper_only_recent_break`; execution realism is `ready` with no execution blockers. Top/contract execution-alternative replay has `12` true top-spread rows and `12` true contract-replacement rows, minute-exit has `12` true minute-exit P&L rows, structure-specific replay has `12` true read-only structure P&L rows, and exact realized P&L rows remain `0`. Open risk is `open_risk_governor_pass`, promotion is blocked with `24` blockers, oracle ceiling remains `not_available_replay_gap`, `0` / `10` candidate rules are paper candidates, `10` are rejected/overfit, `10` are archived, and `0` rejected rules remain unarchived. Lane dispositions are classified for all `13` active regular supervised lanes: `1` `paper_shadow`, `4` `quarantine`, `3` `retest`, `5` `needs_replay_engine`, `0` `profitable_candidate`, and `0` `archive`; all `4` quarantine lanes are read-only archived. The execution-alternative, minute-exit quote-import, stale-candidate, and open-risk resolution actions are gone after exact quote consumption and open-risk review, and the next-evidence queue is now `10` actions. Top queue items are `execute_suggested_trade_review_plan`, `collect_exact_exit_evidence`, and `collect_paper_shadow_exact_evidence`. It is generated by `npm run options:audit:monthly-profitability` at `docs/monthly-all-lanes-profitability-audit.md` and `data/forward-tracking/monthly_all_lanes_profitability_audit_latest.json`, with `live_policy_change=false`.
- latest monthly audit now also consumes the suggested-trade review plan: the generic `refresh_suggested_trade_review` candidate-ledger queue item is replaced by `execute_suggested_trade_review_plan` with `1` missing-review row for suggested trade `id=138`. It remains market-window review coordination, not a trade, broker order, DB mutation, auto-close, or production-proof artifact.
- latest monthly audit now also consumes the fill-attempt evidence capture plan: the generic `capture_missing_fill_attempt_evidence` queue item is replaced by `execute_fill_attempt_evidence_capture_plan` with `4` QQQ/SPY fresh-selection rows. It remains market-window/fresh-selection work, not a trade, broker order, DB mutation, or broker-fill backfill.
- latest no-chase manifest is `no_chase_active`: do not open live/auto-track rows from blocked readbacks, do not chase paper or historical signatures without a fresh exact bridge, and do not use stale/midpoint/EOD/manual/display-only marks as proof.

1. Before answering "is data good?", "why no picks?", "what are we blocked on?", or "what next?", run:

```powershell
npm run options:gateboard
npm run options:replay:execution-alternative-coverage
npm run options:plan:execution-alternative-quote-import
npm run options:replay:minute-exit-readiness
npm run options:plan:minute-exit-quote-import
npm run options:replay:execution-alternatives
npm run options:plan:open-risk-resolution
npm run options:plan:fill-attempt-evidence-capture
npm run options:plan:suggested-trade-review
npm run options:audit:overfit-rule-archive
npm run options:audit:lane-quarantine-archive
npm run options:audit:stale-candidate-archive
npm run options:replay:risk-budget-sizing
npm run options:replay:lane-outcomes
npm run options:plan:lane-scan-hypothesis-repair
npm run options:replay:exact-candidate-repair
npm run options:replay:chain-native-filter-relaxation
npm run options:replay:chain-native-exit-outcomes
npm run options:audit:chain-native-relaxation-archive
npm run options:replay:structure-specific-harness
npm run options:replay:event-data-spine
npm run options:profitability-layer-stack
npm run options:audit:monthly-profitability
```

2. Treat the gateboard as readback only. If it says Data Path is blocked, repair data integrity first. If Data passes but Profitability, Evidence, or Promotion is blocked, do not describe that as a data issue or a live-pick permission.

3. For the volatility lane specifically, run:

```powershell
npm run options:audit:volatility-probation
```

Current read: `paper_probation_blocked`, `6` legacy pre-promotion volatility rows, `0` current paper exact pending rows, `0` promotion-ready rows excluding legacy, `open_risk_governor_pass`, and QQQ `id=537` still listed as a live-exact negative row but resolved by the governor as a fresh executable HOLD.

## CI And Verification

Current read:
- `npm run verify:ci:local` runs dependency integrity, generated docs/contracts, lint, typecheck, frontend node suites, full Python tests, day-trading/Polymarket sidecar tests, smoke, and build.
- `npm run verify:e2e:local` now runs `verify:ci:local` plus non-strict proof-readiness readbacks through `npm run verify:proof-readbacks`; this is the passable local CI-equivalent command for regular-options PR work.
- `npm run verify:e2e:strict`, `npm run verify:accuracy:no-write`, and `npm run verify:profit-loop:dry` remain explicit strict proof-readiness diagnostics. Current strict blockers are documented evidence blockers, not code-test regressions: AI commodity still has `alpaca_opra_daily_snapshot` shared quote dates at `3` / `100`. The regular profit-loop truth-lane and forward-holdout blockers were repaired on 2026-06-05; fresh dry and non-dry strict canaries pass with the active `historical_imported` intraday truth lane.
- Sprint 2 verification debt: isolate Python tests with per-test temp state dirs and env cleanup. The 2026-06-09 triage fixed the three root-cause failures called out in Sprint 1, but the broader cross-test state contamination class still needs a harness-level cleanup before treating one full-suite run as authoritative.

1. Keep strict proof-readiness gates visible in CI readbacks, but do not make them required blockers for regular-options PRs until their owned evidence blockers are repaired or the PR explicitly targets that gate.

## Data Integrity Gate

Current read:
- `npm run options:audit:data-integrity` is the strict Trading Desk repository data-integrity gate. It runs `scripts/audit_repository_constraints.py --strict --json` after loading local env, so Postgres is audited when `DATABASE_URL` is configured in `.env.local`.
- latest strict readback is `pass_or_skipped`: SQLite suggested trades `pass`, Postgres tracked positions `pass`, hard violations `0`, and diagnostics `0`.
- the June 5 repair backed up and fixed local SQLite suggested trade `id=137`, repaired the first `27` Postgres historical research/backfill rows with missing realized P&L, imported missing late-day trusted ThetaData OPRA/NBBO close clusters, then repaired the remaining `34` diagnostics (`24` missing late-day quote rows plus `10` exact zero-bid close rows). Backup artifacts include `data/chat_history.pre-data-integrity-repair-20260605T124724Z.db`, `data/tracked_positions.pre-historical_suggested_close_realized_pnl_repair_v1-20260605-124843.json`, `data/tracked_positions.pre-historical_suggested_close_realized_pnl_repair_v1-20260605-132525.json`, and `data/tracked_positions.pre-historical_suggested_close_realized_pnl_repair_v1-20260605-133431.json`; latest repair report: `data/forward-tracking/historical_suggested_close_realized_pnl_repair_v1_latest.json`.
- the hard blocker was false missing/non-executable handling for exact `bid=0, ask>0` OPRA/NBBO rows. Those rows now remain in the importer/store and can price historical close/mark paths side-aware at long bid and short ask. They still do not count as clean executable coverage for paid-data readiness or live entry quality.
- `supervised_scan.load_open_position_context()` now ignores explicitly identified research/backfill rows in live exposure and realized-loss math while reporting raw and ignored counts, so historical paper inventory cannot contaminate auto-track decisions.

1. Run this gate after any repository, scanner creation, tracked-position, suggested-trade, historical repair, or data-import change:

```powershell
npm run options:audit:data-integrity
```

2. Treat any `violations_found` status or any unexpected diagnostics as a project-wide blocker before trusting picks, P&L, exposure, or dashboards. `pass_or_skipped` with both stores at `pass` is the clean local state.

3. If future diagnostics appear, import the exact missing exit-leg OPRA/NBBO quotes for the listed contract/date pairs, then rerun:

```powershell
uv run --locked python scripts\repair_historical_backfill_realized_pnl.py --as-of-date 2026-06-05 --only-missing-realized --apply
npm run options:audit:data-integrity
```

Do not fill rows from midpoint, last trade, daily/EOD, stale marks, or display-only reviews.

## Architecture And Auth Hardening

Current read:
- browser-facing state-changing and tool routes now call `requireLocalOperator(req)` before body parsing
- `OPTIONS_LOCAL_OPERATOR_TOKEN` is the local operator secret; callers can use `x-options-operator-token`, `Authorization: Bearer ...`, or the HttpOnly session cookie opened by `POST /api/operator/session`
- `OPTIONS_BACKEND_API_TOKEN` is a separate Next-to-FastAPI bridge token and is forwarded only by the server-side backend transport
- Trading Desk and Strategy Lab mutation-intent headers are still required for audited writes, but they are not authorization
- `docs/route-parity.md` now includes a generated route auth/mutation inventory covering mounted browser routes and backend-only FastAPI routes
- `tests/ui/operator-auth.test.js` fails if a future browser-facing mutation route lacks the operator guard, except the explicit operator session endpoint, and it directly proves scan, prediction grading, and tool routes reject missing or wrong auth before body parsing or bridge calls and allow valid auth through to mocked bridge calls with lifecycle headers
- `tests/ui/operator-auth.test.js` also directly proves `POST /api/operator/session` rejects unconfigured or invalid unlock attempts and sets only the expected HttpOnly SameSite=Strict local session cookie on valid unlock
- `npm run verify:docs` also fails if a mutating mounted Next route is missing local operator auth
- `src/components/predictions/OperatorSessionPanel.tsx` now gives the archive-gated scanner a browser unlock affordance for `POST /api/operator/session` without storing the operator token client-side

1. Keep local operator auth and the backend bridge token separate when adding new scanner or Trading Desk routes. Any new browser-facing mutation must still call `requireLocalOperator(req)` before body parsing.

## Proof/Evidence Contract

Current read:
- proof/evidence semantics are versioned at `data/contracts/proof-evidence-contract.json` and explained in `docs/proof-evidence-contract.md`
- `python-backend/proof_contract.py` owns the backend proof predicates used by `positions_service.py` and `/api/proof-summary`
- `options_profit_gate.py` and `options_profit_flywheel.py` consume the same closed-row proof-grade predicate for production readiness metrics
- generated `src/lib/generated/proofEvidenceContract.ts`, `src/lib/trading-desk/proofContract.ts`, and `src/lib/trading-desk/positionEvidence.ts` consume the same proof classes, entry-proof gates, display groups, quote evidence classes, research/backfill markers, quote-freshness tokens, and exit-basis tokens
- production evidence remains limited to fresh live scanner exact-contract proof; creation-time classification, stored-row predicates, and frontend display re-check exact selection source, verified scan lineage, OPRA source, executable entry, present acceptable quote freshness, trusted closed exit, calculable P&L, and absence of row-level or source-snapshot backfill/migration identity fields such as `backfill_audit_id`, `position_migration_id`, and `position_migrated_at_utc` rather than trusting stale proof flags
- live OPRA entry rows may carry profitability-calibration labels such as `research_profitability_calibration`, `pricing_proof_profitability_research`, or `research_bootstrap`; those labels alone are not research/backfill identity and must not block otherwise proof-eligible scanner-origin creates
- compact tracked-position and suggested-trade rows now emit read-time `compact_evidence` labels from the proof contract: `evidence_group`, `proof_contract_version`, row proof booleans, `quote_evidence_class`, source/readback details, and `production_proof_source_eligible`. These labels are diagnostics, not persisted authority; stale frontend labels fail closed by contract version.
- read-only audit/research reports now use `scripts/quote_evidence_readback.py` for the same quote-class vocabulary. Current local readbacks: active quote store is `data/options-validation/options_history.db` (`38,939,237` quote rows, `1,938` batches, `2024-01-02` through `2026-06-04`), root `options_history.db` is refused as a placeholder, paid readiness for SPY/QQQ on `thetadata_opra_nbbo_1m` is `ready_for_exact_replay` with `quote_evidence_class=trusted_intraday_opra_nbbo`, one-lane all-lanes zero-pick no-write coverage reported `row_evidence_group=research_backfill`, `production_proof=False`, and `quote_evidence_class=trusted_intraday_opra_nbbo`, and Lane Lab defaults are `source_quality=legacy_research_only` with `quote_evidence_class=trusted_daily_eod`.
- missed regular selected-pick outcome/failure/filter readbacks now carry both axes: mark source `quote_evidence_class=trusted_intraday_opra_nbbo`, row policy `evidence_group=research_backfill`, and `production_claim=false`. The trusted quote source is suitable for research marks, but those historical missed-pick rows are still not broker fills or production proof.

1. When auditing source-of-truth confusion, run the fast storage and label readbacks before interpreting profitability:

```powershell
uv run --locked python scripts/audit_options_data_store.py --skip-data-roots --json
uv run --locked python scripts/audit_paid_data_readiness.py --snapshot-kind intraday --source-labels thetadata_opra_nbbo_1m --required-underlyings SPY,QQQ --min-quote-dates 1 --min-shared-quote-dates 1 --output-dir tmp/evidence-audit/paid-readiness --force
uv run --locked python scripts/audit_zero_pick_days_all_lanes.py --playbooks quality90_debit55_canary --date-from 2026-06-04 --date-to 2026-06-04 --no-write-report
uv run --locked python scripts/audit_missed_regular_picks_outcomes.py --no-write
uv run --locked python scripts/analyze_missed_regular_picks_failure_modes.py --no-write
uv run --locked python scripts/analyze_missed_regular_picks_filter_matrix.py --no-write
uv run --locked python scripts/run_lane_lab.py --no-write
```

## Live Scanner And Creation Safety

Current read:
- scanner creation safety semantics are versioned at `data/contracts/scanner-creation-safety-contract.json` and explained in `docs/scanner-creation-safety-contract.md`
- candidate lifecycle status/outcome semantics are generated by `scripts/candidate_lifecycle.py` at `data/contracts/candidate-lifecycle-contract.json`, `docs/candidate-lifecycle-contract.md`, and `src/lib/generated/candidateLifecycleContract.ts`; `npm run verify:docs` checks the generated artifacts for drift
- regular playbooks now carry `fresh_live_validation_enabled`, `position_tracking_mode`, and `proof_scope` metadata; every regular supervised options playbook defaults to `position_tracking_mode=auto_track`, while AI Commodity remains separate with scanner/tracked-position tracking disabled
- browser/API/scheduled production scans default to portfolio caps on; caps-off production scan requests are rejected unless marked diagnostic or explicitly allowed
- scheduled auto-track requires the environment kill switch to be on, `market_open_at_run=true`, a regular auto-track playbook, `exposure_snapshot.available=true`, `exposure_snapshot.portfolio_caps_enforced=true`, and per-pick creation metadata with no `creation_blockers`
- scanner-origin tracked-position and suggested-trade creation requires verified archived forward-scan lineage, caps-enforced source scan state, source `creation_eligible=true`, a current guardrail rerun that still has caps-enforced `creation_eligible=true` and no blockers, and proof-eligible exact-contract evidence
- explicit `manual_paper` and `manual_broker` creation modes remain available for research/backfill or broker/manual rows, but those rows do not become production proof without exact OPRA/NBBO evidence and verified lineage
- portfolio guardrails include existing-position exposure, max concurrent positions, cost-risk, open executable drawdown, daily/weekly loss, sector/regime caps, and correlated-index exposure. When portfolio caps are enforced, breached caps are hard blockers for auto-track and scanner-origin creation; near-cap notes and sizing reductions may remain visible cautions.
- side-aware zero-bid replay now stores entry/exit quote evidence plus stable hashes so replay rows can be audited without relying on implicit quote reconstruction
- the June 4 pending-candidate validation did log live OPRA SPY/QQQ spreads, but auto-track skipped them with `research_backfill_not_live_proof` because the proof contract treated generic `research` calibration labels as backfill identity; that false-positive marker is fixed, and a read-only reproduction against a June 4 SPY spread now classifies it as `live_scan_exact_contract`
- future fill-attempt rows now preserve detailed `auto_track_skip_reason` values for creation blockers, missing fill price, and proof-gate exceptions; the pending-validation disposition report and `/api/options-profit/status` compact rows surface that reason instead of collapsing proof failures to only `auto_track_skipped_or_missing_fill_price`
- optional Alpaca paper execution now runs through the existing scanner-origin tracked-position creation gate, is disabled unless `OPTIONS_ALPACA_PAPER_TRADING_ENABLED=1` and paper credentials are configured, submits exactly `1` contract/order to the Alpaca paper endpoint, appends submit/fill/link events to `data/forward-tracking/alpaca_paper_order_events.jsonl`, and stores broker-paper metadata under `source_pick_snapshot.alpaca_paper_order` without counting paper broker fills as production OPRA/NBBO proof
- local scheduler audit on 2026-06-05 confirmed `OptionsScanPicks` and `OptionsScanPicksSafetyNet` are enabled for weekdays at `11:00` and `11:30` Mountain time, last exited `0` on 2026-06-04, and are next scheduled for 2026-06-05; `OptionsRegimeObservationLanes` is also enabled for weekdays at `11:45`, but its 2026-06-04 run exited `1` after the core daily audit because the worktree contained merge-conflict text at that time. Current code has no conflict markers and `scripts/run_regime_observation_lanes.py --dry-run` enumerates the four configured observation playbooks.
- the May 26 through June 4 regular-options historical exact-quote gap is repaired in local `data/options-validation/options_history.db`: import batch `1928` added `3,265,791` trusted intraday ThetaData OPRA/NBBO rows for all `59` regular symbols at `10:10`-`10:25` ET, with `0` duplicates and `0` rejects. The all-lanes audit now emits quote-store coverage so local data gaps are explicit. The report-only missed-pick rerun through June 5 completed `13` / `13` regular playbooks, found `405` signals, `389` exact candidates, `206` would-track selections, removed the old `no_exact_option_quotes_for_date` blocker, and reported quote-store coverage `9` / `10` market days with only `2026-06-05` missing. June 5 itself was not a valid full-session no-pick audit at repair time because the run happened before market/historical data availability.
- the missed-pick outcome audit now gates regular lane promotion. `scripts/audit_missed_regular_picks_outcomes.py` priced `210` raw missed rows with trusted intraday exact-contract marks through `2026-06-04`, found `4` tracked rows with stored P&L and `206` untracked rows with `72` winners / `134` losers, avg net `-16.54%`, median `-12.64%`, profit factor `0.32`, and `-$18,755.00` one-spread net dollars. `scripts/analyze_missed_regular_picks_failure_modes.py` confirms the read is `clean_for_failure_analysis`, not a remaining quote/P&L blocker, and classifies the result as `data_clean_strategy_unprofitable`: `41` rows were `<= -50%`, `15` were `<= -80%`, seven lanes remain diagnostic-only, XLK/SPY/TSLA/IWM are the largest damage clusters, and debit `>=45%` of width plus DTE `>=36` are retest-required diagnostic guardrail candidates. `scripts/analyze_missed_regular_picks_filter_matrix.py` adds the frozen counterfactual matrix: only `volatility_expansion_observation` passes lane promotion (`24` rows, PF `1.83`, avg `+6.74%`), and lane gate plus self-guardrails keeps `10` rows at PF `69.14`, avg `+34.87%`, and later-date split pass, but loses `63` historical winners. `scripts/lane_promotion_state.py` now turns those reads plus fresh evidence, open risk, and circuit-breaker state into the shared promotion artifact: current state is `13` diagnostic lanes, `1` paper/probation lane, `0` live-validation lanes, `0` auto-track lanes, `1` current live-exact negative open row, and `open_risk_governor_pass`. Passed lanes therefore route to paper/probation, not live validation. The daily all-lanes safety net loads a fresh gate and fresh promotion-state report before queueing and routes clear candidates to diagnostics or paper/probation if either report is missing, malformed, future-dated, missing `generated_at_utc`, stale, has unpriced rows, has incomplete tracked P&L, lacks lane rows, lacks walk-forward/fresh-paper depth, has unresolved live-exact negative risk, or is under a lane-specific circuit breaker; exact duplicate spreads selected by multiple lanes are suppressed to one risk owner. Pending validation rechecks the same gates before any auto-track rerun, writes paper-only rows for blocked/probation candidates, and fails closed if either report is unusable. Scanner validation reruns enforce them with `OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1`.
- the June 5 end-to-end rerun after the lane gate, stale-report check, volatility execution caps, and hard portfolio cap blockers completed with `14` / `14` playbooks, `0` candidates, `0` queued rows, `0` pending validations, and `lane_gate_usable=True`. A direct market-hours volatility validation scan with auto-track and portfolio caps enabled reviewed `12` open positions, created `0` positions, and returned `No picks today`.
- the June 5 live exact QQQ row (`id=537`, `volatility_expansion_observation`) remains open under the existing stop policy and is currently a fresh executable negative mark (`-39.86%` in the latest open-risk readback). The fix prevents additional auto-track entries while exposure/drawdown/cost caps are breached; it does not auto-close this existing row or change stop policy.
- the regular profit-loop data path is back on the trusted intraday lane: `.env.local` now points `HISTORICAL_OPTIONS_DB_PATH` at `data/options-validation/options_history.db`, paid-readiness audits load local env and print the effective DB path, live scan/profit-loop policy uses `historical_imported`, daily truth refresh rebuilds the active intraday artifact, and strict dry plus non-dry canaries pass. The latest non-dry strict canary rebuilt `data/options-validation/runs/20260605_022559_broad_intraday.json`, saw `20,048,707` trusted intraday rows through `2026-06-04`, recorded forward holdout candidate flow through `quality90_debit55_canary`, and ended with no open profit-loop issues.

1. During the next market-hours scan, rerun `npm run options:audit:lane-promotion-state`, `npm run options:audit:all-lanes`, and `npm run options:validate:pending-candidates` with the lane gate present. Expect losing lanes to route to diagnostic dispositions, passed lanes to route to paper/probation dispositions, duplicate exact spreads to suppress to one risk owner, and no live validation or auto-track until the promotion-state report shows enough walk-forward depth, fresh exact realized paper rows, and clean current live-exact risk.

2. For the first live Alpaca paper submission, configure only paper credentials and `OPTIONS_ALPACA_PAPER_TRADING_ENABLED=1`, keep the base URL on `https://paper-api.alpaca.markets/v2`, submit a single proof-eligible scanner pick through the archive-gated Live Scan form, then verify the new Paper Track row, event ledger, order status, and tracked-position entry basis before repeating.

3. After the June 5 market session and provider historical window are available, import/capture June 5 trusted intraday OPRA/NBBO rows, rerun `npm run options:audit:missed-outcomes`, then rerun `npm run options:audit:missed-failures` before treating that day as a real zero-pick day or changing scanner policy.

4. Confirm the next `OptionsRegimeObservationLanes` scheduled run exits `0` in `data/forward-tracking/observation_lanes_log.txt`; if it fails again, repair that candidate-lane scheduler before relying on side-lane daily coverage.

5. Rerun the point-in-time scanner candidate replay after new regular candidate/outcome rows mature, and add minute-level OPRA/NBBO stop/target/profit-harvest replay before promoting any exit rule.

## Frontend Makeover Follow-Up

Current read:
- the main UI now uses `Trading Desk` / `Strategy Lab` naming
- `Trading Desk` prioritizes open/closed tracked positions and the all-tracked-stock rollup, while live scan picks, paper ideas, and legacy prediction analytics are de-emphasized behind the archive toggle
- tracked trades now expose clickable lane-family filters near the top of the view, and `bullish_pullback_observation` is displayed as `Bullish Pullback` rather than split by source/provenance variants
- tracked-trade evidence mix, lane-quality, and guardrail-readback card decks were removed from the primary Open/Closed surface; row-level evidence badges and scanner/archive diagnostics remain available
- `FinTable` now renders mobile cards below tablet width, while desktop tables retain horizontal density
- shared `FinTable` mobile cards now use explicit per-table mobile title, subtitle, priority-field, and optional hidden-field contracts instead of relying on object key order; `tests/ui/fin-table.test.js` scans production TSX so new `FinTable` call sites must declare the core mobile hierarchy
- `FinTable` now renders only one responsive surface at a time: desktop table at wide viewports, mobile cards below the table breakpoint. It no longer mounts duplicate desktop and mobile row trees for every visible row.
- the tracked-stock rollup is now split into `src/components/predictions/TrackedStocksTab.tsx`, shared Trading Desk formatters live in `src/components/predictions/tradingDeskFormat.ts`, and `PredictionsView.tsx` computes the tracked-stock summary once for both the tab label and tab body.
- Paper Ideas is now split into `src/components/predictions/SuggestedTradesTab.tsx` and loaded dynamically from the archive-gated tab; shared position/suggested-trade row cells live in `src/components/predictions/tradingDeskCells.tsx`.
- tracked positions are now split into `src/components/predictions/TrackedPositionsTab.tsx`, with shared date, lane, contract, and ticker helpers in `src/components/predictions/trackedPositionUtils.tsx`.
- the archive-gated live scanner is now split into `src/components/predictions/ScannerTab.tsx` and dynamically loaded; scanner rows/column contracts are memoized inside that focused component.
- tracked-position and suggested-trade data/review/paging state now live in `src/components/predictions/useTradingDeskRecords.ts`, keeping `PredictionsView.tsx` focused on tab orchestration, scanner/trade-entry state, and modal wiring. Current line read: `PredictionsView.tsx` `1283` lines, `useTradingDeskRecords.ts` `510` lines.
- Closed Trades now page-scrolls its loaded rows and loads tracked closed history in `50`-row batches, fetching the next batch when the operator reaches the bottom or presses `Load More` instead of pulling the full archive at once.
- fresh runtime smoke on temporary Next `3015` and backend `8115` exercised Open, Tracked Stocks, and archive-gated Paper on desktop `1440x1000` and mobile `390x844`; console/page errors were `0`, page-level horizontal overflow was `0`, and Paper still surfaced `Needs Review` / `Review needed` for the stale suggested trade. Artifact: `tmp/trading-desk-hook-qa-20260601T0711Z/browser-hook-qa-summary.json`.
- fresh browser QA on temporary Next `3014` and backend `8114` opened Archive > Live Scan and expanded `Evidence & guardrails` on desktop `1440x1000` and mobile `390x844`; console/page errors were `0`, page-level horizontal overflow was `0`, and the expanded truth-health card showed `TRACKED DB READY`. Artifacts: `tmp/browser-qa-20260601T0646Z/browser-qa-expanded-summary.json`, `desktop-1440x1000-live-scan-expanded.png`, and `mobile-390x844-live-scan-tracked-db.png`.

1. Treat the scanner evidence-drawer QA pass as complete for the current code. Repeat desktop/mobile visual QA after the next Trading Desk tab, drawer, row-detail, or route-contract change.

2. Continue reducing the remaining `src/components/predictions/PredictionsView.tsx` surface by extracting scanner/truth-health state, trade-entry form state, or close-modal state only where the split lowers verification burden without changing route contracts.

3. Continue responsive polish around trade row details and drawers, but keep the shared table mobile hierarchy explicit through `mobileTitleCol`, `mobileSubtitleCol`, `mobilePriorityCols`, and optional `mobileHiddenCols` when adding new dense tables.

## Tracked Position Profit Controls

Current read:
- the UI-backed tracked-position store contains historical paper rows with raw `stop_loss_pct=90`
- Closed Trades now defaults to a current-policy data view: promoted repair-lane rows that clear today's entry guardrails and have trusted realized P&L
- Closed Trades keeps separate filters for current policy, learned-away rows, raw realized P&L, truth-grade production proof, all closed rows, historical paper, lifecycle-only, unpriced, and legacy rows so proof claims stay separate from historical-learning review
- closed-position summary cards now foreground current-policy row count, learned-away row count, shown-row win rate, shown-row average P&L, and strict truth-grade average P&L
- Closed Trades uses `50`-row tracked closed-history batches with page-level scrolling and bottom-of-list lazy loading, because the first `50` newest rows can be a materially worse recent slice than the full historical policy replay and should not be the only reachable window
- live review intentionally honors `90%` configured stops for profit-first paper/live-shadow behavior
- configured stops wider than `90%` are capped to `90%`, while retaining both `configured_stop_loss_pct` and `effective_stop_loss_pct` in review metrics
- verified executable zero exits can now auto-close paper positions at `0.0` instead of leaving total-loss options open
- display-only last-price marks still suppress stop/target triggers and do not auto-close positions
- passive positions/suggestions polling in the UI is now read-only; explicit refresh/review actions are required before the UI POSTs review requests
- `POST /api/positions/review` is still state-changing: it saves reviews and can auto-close executable `SELL` recommendations
- closed-position realized P&L is now canonicalized from entry/exit execution prices when an exit price exists, and create-time pre-closed rows preserve gross/net P&L columns
- local tracked-position audit after the repair: `87` closed rows, `75` priced rows with canonical realized P&L, and `12` historical lifecycle-only closed rows with no trusted exit quote and therefore no assigned P&L; backup: `data/tracked_positions.pre-realized-pnl-repair-20260531T184725Z.json`
- open-position risk audit now writes `data/forward-tracking/regular_open_position_risk_latest.json` and feeds the regular operating scorecard. Current read: `12` open regular rows, `11` fresh executable reviews, `1` fresh unpriced review, `0` executable close-ready rows, `1` review-required non-executable display-only `SELL` row (`id=104`, SBUX), and one live exact volatility row (`id=537`, QQQ) with a fresh executable negative mark still under the stored stop policy.
- suggested-trade close-risk audit now writes `data/forward-tracking/suggested_trade_close_risk_latest.json` and feeds the regular operating scorecard. Current read: `1` open suggested trade (`id=138`, AAA), `0` executable close-ready rows, `0` non-executable close-risk rows, and `1` stale/missing-review row. Refresh explicit review before relying on suggested-trade P&L or close state.
- Postgres tracked-position requests now reuse successful connections through a small in-process pool in `python-backend/positions_repository.py`; failed requests roll back and discard the connection before the next request.
- FastAPI responses now include `x-python-backend-duration-ms` so local Trading Desk/API checks can compare route latency before and after payload or query changes.
- Trading Desk and proof-status Next read routes now forward `x-python-backend-duration-ms` from the Python backend, so route probes can compare Next elapsed time against backend handler time without changing response bodies.
- `/api/positions` and `/api/suggested-trades` now accept `limit` and `offset`, forward those windows through the Next API layer, and return page metadata so the UI can lazy-load closed/history-heavy tables.
- `PredictionsView.tsx` now fetches open tracked positions and open suggested trades by default; Closed Trades requests tracked closed rows in `50`-row batches while Closed Ideas still requests the first `100` rows on demand, and both page older closed rows through `Load More`, so Open and Tracked Stocks refreshes no longer pull the full closed/research archive.
- Tracked Stocks now receives the parent-level tracked-stock summary and renders through a focused memoized component, avoiding a duplicate summary build while continuing to show closed-row totals as on-demand until the archive is loaded.
- Paper Ideas now lives outside the default `PredictionsView.tsx` body and is dynamically loaded only when the archive-gated paper tab is opened.
- the default Open/Closed tracked-position board now renders through `TrackedPositionsTab.tsx`, and shared tracked-position helper logic lives in `trackedPositionUtils.tsx` for reuse by scanner, close dialogs, and tracked-stock summaries.
- the archive-gated live scanner now lives outside the default `PredictionsView.tsx` body as dynamically loaded `ScannerTab.tsx`, with memoized scanner table rows and stable column contracts.
- open Trading Desk status cells now distinguish executable `SELL` reviews from non-executable/display-only `SELL` marks. A non-executable `SELL` shows `Review quote` instead of `Close now`, matching the current position `104` safety rule.
- Paper Ideas open rows now use the same review-action status model. Missing, stale, or non-executable suggested-trade reviews surface through the row `Status`, a `Needs Review` summary count, and a separate `Close-ready` count, so suggested trade `138` cannot read as executable-close-ready before refresh.
- browser-to-Next JSON handling now lives in `src/lib/client-json.ts`; `PredictionsView.tsx` uses it for Trading Desk fetches and mutations so HTML/proxy failures report as explicit non-JSON response diagnostics instead of raw `Unexpected token '<'` parse errors.
- tracked-position and suggested-trade list/review/paging state now lives in `src/components/predictions/useTradingDeskRecords.ts`; static mutation-intent tests read both the parent component and hook so explicit mutation headers and paged read routes stay covered after the extraction.
- read-only API performance audit script `scripts/audit_trading_desk_api_performance.py` writes `data/forward-tracking/trading_desk_api_performance_latest.json` and now feeds the active operating scorecard. Latest full local route run against fresh temporary Next `3013` and backend `8113`: `11` / `11` probes succeeded, frontend max elapsed `230.6 ms`, frontend payload total `321,783` bytes, backend max duration header `49.1 ms`, open tracked positions are down to `139,603` backend bytes / `139,105` Next bytes, and the first `100` compact closed tracked positions remain the largest measured payload at `171,667` backend bytes / `170,715` Next bytes.
- `/api/options-profit/status` now overlays the current tracked-position health check from the same runtime repository used by `/api/positions`, instead of trusting the stale `data/options-profit/status.json` tracked-DB sub-check. The route uses a narrow tracked-position profit-status snapshot rather than loading full position rows; current-code FastAPI TestClient evidence reports tracked positions available with `48` open rows, `488` total closed rows, and `1` proof-eligible realized closed row while preserving the stored options-profit gate state as `blocked`.
- scanner evidence-drawer browser QA is complete on temporary Next `3014` and backend `8114`: desktop `1440x1000` and mobile `390x844` expanded `Evidence & guardrails`, reported `0` console/page errors, no page-level horizontal overflow, and visually confirmed `TRACKED DB READY`.
- Paper Track now has its own primary Trading Desk tab for Alpaca paper-linked tracked positions, with a selected-position SVG P&L timeline that separates executable exit P&L, paper mark values, and closed realized exits.

1. Use the default Current Policy Closed Trades view for product iteration and operator review. Switch to Realized P&L when intentionally inspecting raw historical/backfill outcomes; switch to Truth-grade only when making live-production accuracy claims; switch to historical paper, lifecycle-only, unpriced, learned-away, or legacy filters when auditing research/backfill data quality.

2. Audit the currently open historical paper positions before running the state-changing review endpoint, then decide whether to let executable `SELL` recommendations auto-close or close selected rows manually.

3. Repeat scanner evidence-drawer QA only after changes to the Trading Desk scanner, `/api/options-profit/status`, `/api/positions`, `/api/proof-summary`, or tracked-position repository availability.

4. Continue the performance pass from the new API performance artifact: compact closed list payload pruning, closed-row/open-row `compact_evidence`, compact open provenance pruning, tracked-stock extraction, tracked-position extraction, dynamic Paper Ideas loading, dynamic Scanner loading, shared client JSON handling, the tracked-health status overlay, the narrow profit-status tracked snapshot, and the Trading Desk records hook are in place. Next hot paths are any further shared open/closed row payload reductions that preserve review/evidence semantics, scanner/truth-health state extraction, and trade-entry/close-modal extraction only if it reduces verification burden.

## Trading Desk Profitability Repair

Current artifacts:
- all-row guardrail replay script: `scripts/analyze_trading_desk_profitability_guardrails.py`
- latest JSON: `data/forward-tracking/trading_desk_profitability_guardrails_latest.json`
- report: `docs/trading-desk-profitability-guardrails-2026-05-31.md`
- negative decision audit script: `scripts/audit_trading_desk_negative_trade_decisions.py`
- negative decision latest JSON: `data/forward-tracking/trading_desk_negative_trade_decision_audit_latest.json`
- negative decision latest CSV: `data/forward-tracking/trading_desk_negative_trade_decision_audit_latest.csv`
- negative decision report: `docs/trading-desk-negative-trade-decision-audit-2026-05-31.md`
- exit-policy replay script: `scripts/replay_trading_desk_exit_policies.py`
- exit-policy latest JSON: `data/forward-tracking/trading_desk_exit_policy_replay_latest.json`
- exit-policy latest CSV: `data/forward-tracking/trading_desk_exit_policy_replay_latest.csv`
- exit-policy report: `docs/trading-desk-exit-policy-replay-2026-05-31.md`
- legacy missed-close audit script: `scripts/audit_trading_desk_legacy_missed_closes.py`
- legacy missed-close latest JSON: `data/forward-tracking/trading_desk_legacy_missed_close_audit_latest.json`
- legacy missed-close report: `docs/trading-desk-legacy-missed-close-audit-2026-06-01.md`
- guardrail starvation audit script: `scripts/audit_regular_guardrail_starvation.py`
- guardrail starvation latest JSON: `data/forward-tracking/regular_guardrail_starvation_latest.json`
- guardrail starvation report: `docs/regular-guardrail-starvation-audit.md`
- daily all-lanes audit safety net script: `scripts/ensure_daily_all_lanes_audit_ran.py`
- daily all-lanes audit command: `npm run options:audit:all-lanes`
- missed regular picks outcome audit script: `scripts/audit_missed_regular_picks_outcomes.py`
- missed regular picks outcome audit command: `npm run options:audit:missed-outcomes`
- missed regular picks outcome latest JSON: `data/forward-tracking/missed_regular_picks_outcome_latest.json`
- missed regular picks outcome report: `docs/missed-regular-picks-outcome-audit.md`
- missed regular picks failure-mode audit script: `scripts/analyze_missed_regular_picks_failure_modes.py`
- missed regular picks failure-mode audit command: `npm run options:audit:missed-failures`
- missed regular picks failure-mode latest JSON: `data/forward-tracking/missed_regular_picks_failure_modes_latest.json`
- missed regular picks failure-mode report: `docs/missed-regular-picks-failure-modes.md`
- missed regular picks filter matrix script: `scripts/analyze_missed_regular_picks_filter_matrix.py`
- missed regular picks filter matrix command: `npm run options:audit:missed-filter-matrix`
- missed regular picks filter matrix latest JSON: `data/forward-tracking/missed_regular_picks_filter_matrix_latest.json`
- missed regular picks filter matrix report: `docs/missed-regular-picks-filter-matrix.md`
- lane promotion state script: `scripts/lane_promotion_state.py`
- lane promotion state command: `npm run options:audit:lane-promotion-state`
- lane promotion state latest JSON: `data/forward-tracking/lane_promotion_state_latest.json`
- lane promotion state report: `docs/lane-promotion-state.md`
- pending selected-candidate queue: `data/forward-tracking/pending_scan_candidates.jsonl`
- pending candidate live validator: `scripts/validate_pending_scan_candidates.py`
- pending candidate live validator command: `npm run options:validate:pending-candidates`
- pending candidate validation disposition latest JSON: `data/forward-tracking/pending_scan_candidate_validation_latest.json`
- regular options fresh evidence loop script: `scripts/build_regular_options_fresh_evidence_loop.py`
- regular options fresh evidence loop latest JSON: `data/forward-tracking/regular_options_fresh_evidence_loop_latest.json`
- regular options fresh evidence loop report: `docs/regular-options-fresh-evidence-loop.md`
- regular options candidate outcome ledger script: `scripts/build_regular_options_candidate_outcome_ledger.py`
- regular options candidate outcome ledger latest JSON: `data/forward-tracking/regular_options_candidate_outcome_ledger_latest.json`
- regular options candidate outcome ledger report: `docs/regular-options-candidate-outcome-ledger.md`
- open-position risk audit script: `scripts/audit_regular_open_position_risk.py`
- open-position risk latest JSON: `data/forward-tracking/regular_open_position_risk_latest.json`
- suggested-trade close-risk audit script: `scripts/audit_suggested_trade_close_risk.py`
- suggested-trade close-risk latest JSON: `data/forward-tracking/suggested_trade_close_risk_latest.json`
- Trading Desk API performance audit script: `scripts/audit_trading_desk_api_performance.py`
- Trading Desk API performance latest JSON: `data/forward-tracking/trading_desk_api_performance_latest.json`
- AI commodity progress source for the active scorecard: `data/ai-commodity-infra/progress/latest.json`
- current-policy historical picks audit script: `scripts/build_current_policy_historical_picks_audit.py`
- current-policy historical picks latest JSON: `data/forward-tracking/current_policy_historical_picks_latest.json`
- current-policy historical picks report: `docs/current-policy-historical-picks-audit.md`
- current-policy cohort health script: `scripts/build_current_policy_cohort_health.py`
- current-policy cohort health latest JSON: `data/forward-tracking/current_policy_cohort_health_latest.json`
- current-policy cohort health report: `docs/current-policy-cohort-health.md`
- current-policy circuit breaker script: `scripts/build_current_policy_circuit_breaker.py`
- current-policy circuit breaker latest JSON: `data/forward-tracking/current_policy_circuit_breaker_latest.json`
- current-policy circuit breaker report: `docs/current-policy-circuit-breaker.md`
- current-policy historical stop-grid script: `scripts/replay_current_policy_historical_stop_grid.py`
- current-policy historical stop-grid latest JSON: `data/forward-tracking/current_policy_historical_stop_grid_latest.json`
- current-policy historical stop-grid latest CSV: `data/forward-tracking/current_policy_historical_stop_grid_latest.csv`
- current-policy historical stop-grid report: `docs/current-policy-historical-stop-grid.md`
- current-policy entry-filter lab script: `scripts/analyze_current_policy_entry_filters.py`
- current-policy entry-filter lab latest JSON: `data/forward-tracking/current_policy_entry_filter_lab_latest.json`
- current-policy entry-filter lab latest CSV: `data/forward-tracking/current_policy_entry_filter_lab_latest.csv`
- current-policy entry-filter lab report: `docs/current-policy-entry-filter-lab.md`
- current-policy entry-filter walk-forward script: `scripts/validate_current_policy_entry_filter_walkforward.py`
- current-policy entry-filter walk-forward latest JSON: `data/forward-tracking/current_policy_entry_filter_walkforward_latest.json`
- current-policy entry-filter walk-forward latest CSV: `data/forward-tracking/current_policy_entry_filter_walkforward_latest.csv`
- current-policy entry-filter walk-forward report: `docs/current-policy-entry-filter-walkforward.md`
- current-policy entry-filter paper-monitor script: `scripts/monitor_current_policy_entry_filter_paper.py`
- current-policy entry-filter paper-monitor latest JSON: `data/forward-tracking/current_policy_entry_filter_paper_monitor_latest.json`
- current-policy entry-filter paper-monitor latest CSV: `data/forward-tracking/current_policy_entry_filter_paper_monitor_latest.csv`
- current-policy entry-filter paper-monitor report: `docs/current-policy-entry-filter-paper-monitor.md`
- current-policy entry-filter point-in-time replay script: `scripts/replay_short_term_filter_point_in_time.py`
- current-policy entry-filter point-in-time replay command: `npm run options:replay:short-term-filter`
- current-policy entry-filter point-in-time replay latest JSON: `data/forward-tracking/short_term_filter_point_in_time_replay_latest.json`
- current-policy entry-filter point-in-time replay latest CSV: `data/forward-tracking/short_term_filter_point_in_time_replay_latest.csv`
- current-policy entry-filter point-in-time replay report: `docs/current-policy-entry-filter-point-in-time.md`
- profit capture queue script: `scripts/build_regular_options_profit_capture_queue.py`
- profit capture queue latest JSON: `data/profitability-lab/regular-options-profit-capture-queue/latest.json`
- profit capture queue latest Markdown: `data/profitability-lab/regular-options-profit-capture-queue/latest.md`
- profit capture queue report: `docs/regular-options-profit-capture-queue.md`
- paper-shortlist release gate script: `scripts/build_regular_options_paper_shortlist.py`
- paper-shortlist release gate command: `npm run verify:profitability-paper-gates`
- paper-shortlist latest JSON: `data/profitability-lab/regular-options-paper-shortlist/latest.json`
- paper-shortlist report: `docs/regular-options-paper-shortlist.md`
- repair-attempt readback script: `scripts/build_regular_options_repair_attempt_readback.py`
- repair-attempt readback latest JSON: `data/profitability-lab/regular-options-repair-attempts/latest.json`
- repair-attempt readback report: `docs/regular-options-repair-attempts.md`
- shared repair-target parser: `scripts/regular_options_repair_targets.py`
- exact missing replay importer: `scripts/import_missing_replay_quotes_from_thetadata.py`
- exact missing replay classifier: `scripts/classify_missing_replay_contracts.py`
- profitability paper-gate goal prompt: `docs/autoresearch/profitability-paper-gate-goal.md`
- monthly all-lanes profitability goal prompt: `docs/autoresearch/monthly-all-lanes-profitability-goal.md`

Profitability Paper Gate Operator Workflow sprint backlog:

1. Paper Gate Release Pack: done. Generated paper-shortlist readback, focused bridge tests, negative tests for non-eligible evidence classes, strict fail-closed source/invariant checks, and the dedicated `npm run verify:profitability-paper-gates` release command are implemented. Six-subagent done debate cleared with `6` / `6` no-blocker verdicts after the strict-gate blocker patch. Current readback is `eligible_count=0`, `invariant_violation_count=0`, `release_gate_status=no_paper_shortlist_candidates`, and `live_policy_change=false`.

2. Fresh Exact Evidence Loop: done. `scripts/build_regular_options_fresh_evidence_loop.py` now reconciles pending validation candidates, fill-attempt snapshots, tracked-position linkage, exact exit P&L status, and readback counts for missing realized P&L, no-longer-matched, proof-ineligible, stale, and non-executable states without merging proof semantics. The proof-boundary patch removed permissive exit-basis matching, rejects contaminated `spread_bid_ask*` / `expired_auto_close` exit evidence, preserves `0.0` realized P&L, and clarifies that entry evidence is scanner quote/limit evidence, not a broker fill. Verification passed with `npm run verify:profitability-paper-gates`, `npm run verify:docs`, and `git diff --check`; the final six-subagent done debate cleared with `6` / `6` no-blocker verdicts. Current readback has `34` candidates, including `22` validation-attempted, `8` paper-validation-only, and `4` diagnostic candidates; outcomes are `1` created, `16` no-longer-matched, `8` paper-only, `5` proof-ineligible, and `4` diagnostic-only. It has `1` linked position, `0` exact realized P&L rows, `1` missing realized-P&L row, `8` paper/probation exact-entry bridges, `1` exact-exit bridge, and `0` promotion-discussion-ready rows.

3. Recent-Cohort Circuit Breaker: done. `scripts/build_current_policy_circuit_breaker.py` now reads cohort health, short-term point-in-time replay, and the paper monitor to route affected `short_term` and `bullish_pullback_observation` pending candidates to `paper_validation_only` while recovery gates fail. `scripts/validate_pending_scan_candidates.py` consumes the breaker before auto-track validation and writes a `paper_only` validation disposition for affected lanes instead of silently rerunning them with auto-track enabled. The blocker patches now keep affected lanes held when the cohort label recovers but forward gates still fail, treat all-gates-passed recovery as `recovery_review_required` rather than automatic live release, and fail closed when the breaker artifact is missing, malformed, or has empty `lane_routes`. Verification passed with `npm run verify:profitability-paper-gates`, `npm run verify:docs`, and `git diff --check`; final six-subagent done debate cleared with `6` / `6` no-blocker verdicts after the fail-open patches. Current readback has `2` paper-validation-only lanes, `0` lane deletions, `live_policy_change=false`, and recovery blockers `recent_cohort_recovered`, `fresh_current_policy_rows`, `fresh_champion_matched_rows`, `trusted_exact_realized_pnl_rows`, `point_in_time_replay_pass`, and `paper_monitor_pass`.

4. Operator Workflow: done. `OperatorSessionPanel.tsx` now opens the local operator session from the scanner surface, `/api/options-profit/status` overlays `paper_gate_operator_workflow`, and `PaperGateOperatorPanel.tsx` surfaces release status, bridge blockers, matched Tier A lanes, pending outcomes, no-fill/skipped auto-track explanations, and paper-only circuit-breaker routes without presenting paper gates as trade recommendations. The done debate cleared with `6` / `6` no-blocker verdicts; the proof-boundary follow-up tightened invariant-bad paper-shortlist artifacts into `paper_gate_invariant_violations` instead of relying on `eligible_count`. Verification passed with focused backend/UI/type checks, docs verification, release-gate verification, `git diff --check`, and desktop/mobile browser QA of Archive > Live Scan > Evidence & guardrails with local operator unlock.

5. Exact Repair Queue Burn-Down: done. `scripts/build_regular_options_repair_burndown.py` now turns the evidence repair queue plus repair-attempt readback into a deduped exact-date repair burn-down at `docs/regular-options-repair-burndown.md`, targeting only unexhausted exact-date repairs, treating lookahead-only rows as diagnostic, requiring source replay before graduation, and avoiding repeated exhausted provider no-match loops. Missing or unreadable repair-attempt memory fails closed with `0` active repair targets and no provider commands. Current readback has `145` deduped targets, `11` active unattempted exact targets, `5` source-replay-required targets, `32` diagnostic lookahead-only targets, `97` exhausted current-source targets, and `live_policy_change=false`. Verification passed with focused burn-down tests, `py_compile`, `npm run verify:profitability-paper-gates` (`69` tests plus no-write scripts), `npm run verify:docs`, and `git diff --check`; final six-subagent done debate cleared with `6` / `6` no-blocker verdicts after the aggregate-evidence, missing-memory, living-doc-count, and corrupt-memory patches.

6. Scorecard And Agent Memory: done. `scripts/build_regular_profitability_operating_scorecard.py` now adds a `paper_gate_readiness` block and Markdown section that summarizes the paper-shortlist release gate, fresh evidence loop, current-policy circuit breaker, profit-capture queue, and exact repair burn-down in one readback. Current status is `paper_only_no_live_release` with `0` eligible paper-review candidates, `0` invariant violations, `34` fresh candidates, `0` exact realized-P&L rows, `0` promotion-ready rows, `2` paper-validation-only lanes, and repair counts `11` active / `5` source replay / `32` diagnostic / `97` exhausted. `scripts/generate_agent_memory_graph.py` now adds the paper-gate scorecard, queue, shortlist, fresh loop, circuit breaker, operator workflow, repair-attempt, and burn-down path for future agents. The scorecard loader fails closed on corrupt/non-object JSON, and the paper-gate verify command includes scorecard, memory-graph, and candidate-ledger tests plus no-write readbacks. Verification passed with focused scorecard/memory tests, `py_compile`, scorecard no-write, memory graph `--check`, `npm run verify:profitability-paper-gates`, `npm run verify:docs`, and `git diff --check`; final six-subagent done debate cleared with `6` / `6` no-blocker verdicts.

7. Candidate Outcome Ledger: done. `scripts/build_regular_options_candidate_outcome_ledger.py` consumes the fresh-evidence loop, paper shortlist, profit-capture queue, open-risk governor, and suggested-trade close-risk readbacks into one read-only next-evidence queue at `docs/regular-options-candidate-outcome-ledger.md` and `data/forward-tracking/regular_options_candidate_outcome_ledger_latest.json`. Current status is `ledger_live_entry_blocked_collect_evidence` with `106` rows and `live_policy_change=false`: first priority is the QQQ `id=537` open-risk governor blocker, followed by SBUX `id=104` executable-review refresh, AAA suggested-trade review refresh, QQQ `id=537` exact-exit evidence collection, `5` paper-review create/link rows, `8` paper/probation exact-entry rows, `4` missing fill-attempt evidence rows, `16` no-longer-matched/archive rows, `21` Tier A fresh-bridge waits, `39` historical repair rows, and `9` guardrail/lane-mismatch rows. This ledger does not create trades, submit broker orders, change scanner policy, change stops, change DB schema, lower proof bars, or promote paper/research rows.

Done gate for each sprint: finish implementation, run focused verification, update living docs and generated reports when owned facts change, then spawn or resume six independent subagents to review and debate the fix. Required review lenses are profitability strategy, proof/evidence, data lifecycle/storage, Trading Desk operator workflow/auth, tests/regression, and LLM readability/maintainability. A sprint is done only with at least `4` of `6` agreement and no credible severe blocker involving data loss, proof-source contamination, unintended state mutation, incorrect P&L, auth bypass, live-promotion leakage, broker action, or a broken primary Trading Desk flow.

Current read:
- repair scope is the regular supervised Trading Desk lanes: `short_term`, `swing`, `bullish_momentum`, and Bullish Pullback
- baseline replay: `429` rows, `383` priced, `193` negative, `190` positive/flat, `46` unknown, average P&L `5.21%`, median P&L `-1.58%`
- promoted combined kept subset: `130` rows, `116` priced, `29` negative, `87` positive/flat, average P&L `53.08%`, median P&L `46.4%`
- current-policy closed-row replay: `488` closed rows audited, `400` current-policy scope rows, raw realized scope `355` priced at avg `+4.87%`, median `-6.53%`, negative rate `51.8%`; `would_take_today` has `112` priced rows at avg `+53.54%`, median `+50.6%`, negative rate `25.9%`; `blocked_by_current_policy` has `274` rows / `243` priced at avg `-17.56%`, median `-30.41%`, negative rate `63.8%`
- current-policy cohort health: overall current-policy rows are still positive (`112` priced, avg `+53.54%`, median `+50.6%`), but the showable edge is concentrated in `2026-04` (`70` priced, avg `+81.17%`, median `+71.82%`, `8.6%` negative rate). Recent `2026-05` degraded to avg `+7.49%`, median `-4.6%`, `54.8%` negative rate, and latest week `2026-W21` is avg `-82.06%`, median `-83.61%`, `100.0%` negative rate. Current state is `paper_only_recent_week_break`.
- missed-pick outcome gate: the May 22 through June 5 report-only all-lanes selected set is not profitable as a whole, and the companion failure-mode audit says the data status is `clean_for_failure_analysis`. The latest outcome audit has `210` fully priced rows, including `4` already tracked rows with stored P&L and `206` untracked priced rows; the untracked slice has `72` winners, `134` losers, avg net `-16.54%`, median `-12.64%`, PF `0.32`, and `-$18,755.00` one-spread net dollars. The failure-mode read adds `41` rows `<= -50%`, `15` rows `<= -80%`, largest damage clusters in XLK/SPY/TSLA/IWM, debit `>=45%` of width at PF `0.05`, and DTE `>=36` at PF `0.12`. `bullish_momentum`, `bullish_pullback_observation`, `short_term`, `speculative`, `swing`, `tracked_winner_observation`, and `tracked_winner_primary` are diagnostic-only until a fresh exact-contract outcome audit proves otherwise. `volatility_expansion_observation` is the only lane currently allowed into candidate flow, and only after self-guardrails block SPY/IWM and debit above `45%` of width.
- scanner guardrails now block debit over `45%` of width, fill degradation `>=20%`, worst-leg bid/ask spread `>=20%`, lane-specific ticker quarantines, Bullish Pullback non-keep tickers, and Bullish Pullback `ret5 < -2`
- fill-attempt logs now persist fill-discipline snapshots with selected spread evidence, leg bid/ask/mids, spread mid/entry debit, fill degradation versus mid, top alternatives, and quote freshness. These are paper/review forensics only; they do not change scanner gates, broker action, or proof promotion.
- momentum-chase blocking is rejected for now because it removed too many winners in the all-row replay
- negative decision audit: `213` negative tracked rows, with `208` limited research/backfill rows and `5` limited legacy exact-like rows
- current promoted entry guardrails hit `167` negative rows; the biggest guardrail hits are lane ticker quarantine (`101`), fill degradation (`79`), worst-leg spread (`73`), and debit over `45%` width (`46`)
- executable-exit audit: `1` negative row had non-negative executable evidence before the first negative review; legacy rows `26`, `39`, and `44` had positive executable `SELL` reviews before the final negative outcome and need a separate legacy missed-auto-close audit before any current policy change
- `186` negative rows have no stored intra-life review timeline, so missed-close claims are explicitly unavailable for those rows
- exit-policy replay found `107` regular Trading Desk rows with stored executable review timelines; baseline on that replayable subset is already positive at avg `+39.06%`, median `+43.72%`, `23` negatives, and deep-loss buckets of `14` rows `<= -50%`, `11` `<= -70%`, `9` `<= -80%`, `2` `<= -90%`, `1` `<= -95%`, and `1` `<= -99%`
- no tested broad exit rule is promotable: the new executable stop grid (`stop_60`, `stop_70`, `stop_80`, `stop_90`) can reduce the stored-review `<= -90%` bucket from `2` to `1`, but the positive-delta stop shapes still increase negatives to `24` and flip `2` stored winners to losses; `stop_50` increases negatives to `25` and flips `3` winners, while global profit harvest, global trailing giveback, shorter time exits, and stored-SELL following still reduce average executable P&L
- current-policy exact-contract daily close-check stop grid replayed all `112` Postgres current-policy realized rows with `0` unresolved rows across all `17` tickers. Because that tracked slice is only Apr/May 2026, the same stop-grid report now also carries an annual replay-backed exact cohort from the regular multi-lane stack: `234` rows, entry window `2025-08-14` to `2026-03-24`, exit window `2025-09-09` to `2026-04-27`, and `0` unresolved rows across all `37` tickers. The annual cohort is audit evidence, not inserted tracked rows or broker/live fills. The tracked baseline is avg `+53.54%`, median `+50.60%`, `29` negatives, and `8` rows `<= -90%`; `stop_80` is the only non-destructive daily close-check candidate on that slice, with avg `+53.69%`, `29` negatives, `7` rows `<= -90%`, `9` stop hits, and `0` winner flips. The annual replay-backed grid argues against a broad stop change: every tested stop from `50%` through `90%` reduces average P&L and flips winners. The tracked `<= -50%` loss cohort is all historical paper, concentrated in `short_term` (`11` of `16`), with `6` rows at fill degradation `>=15%`, `4` quality scores below `60`, and repeat clusters in `TSLA`, `MSTR`, and `QQQ`.
- current-policy entry-filter lab found one paper-only candidate: `short_term_fill_degradation_ge_15`. It blocks `9` historical current-policy rows, avoids `5` rows `<= -50%`, avoids `3` rows `<= -90%`, loses `2` winners, and improves the kept historical cohort to avg `+61.01%` and median `+53.33%`; broader quality/ticker/fill filters removed too many winners.
- current-policy entry-filter walk-forward validated all regular repair lanes. Status is `mixed_walkforward_watch_not_promoted`: the frozen `short_term_fill_degradation_ge_15` rule is a `historical_pass_candidate` overall and on the `2026-05` holdout, but `2026-04` is `winner_damage_too_high`. A broad all-lane fill-degradation `>=15%` rule is rejected as `winner_damage_too_high` after losing `10` winners. Lane statuses: `short_term=historical_pass_candidate`, `swing=no_deep_loss_reduction`, `bullish_momentum=winner_damage_too_high`, `bullish_pullback_observation=no_coverage`.
- current-policy entry-filter paper monitor is now collecting forward evidence since `2026-06-02`. Current read: `0` fresh rows and `0` champion-matched rows, so it is not eligible for scanner promotion. Required gates are at least `20` fresh current-policy rows, at least `5` fresh champion-matched candidate-blocked rows, trusted executable realized P&L, and monitor pass status.
- current-policy entry-filter point-in-time replay is now available for `short_term_fill_degradation_ge_15`. Latest readback is `paper_only_collecting`: `5` scanner candidate rows, `0` champion-matched rows, `0` exact-priced rows, `5` unpriced/non-executable rows, and promotion blockers `insufficient_exact_priced_candidate_rows`, `insufficient_champion_matched_blocked_rows`, `matched_rows_not_net_harmful_or_deep_loss`, and `unpriced_or_non_executable_rows_present`.
- profit capture queue is now the visibility layer for profitable evidence before scanner changes. Current read after the fresh-match bridge and repair-actionability wiring: `97` research/paper queue rows, `15` Tier A clean exact rows, `82` Tier B profitable watch/repair rows, `16` high-priority evidence repairs with missing quote-date/contract summaries, `15` fresh scan signature matches, `9` blocked-but-interesting candidates, and `173` quarantine/do-not-chase rows. Selection readiness is explicit: `15` `paper_review_candidate`, `82` `watch_repair_only`, `6` `historical_signature_only`, `9` `blocked_guardrail_only`, and `173` `do_not_chase`. Repair actionability counts are `15` `no_repair_needed_clean_exact`, `3` `needs_status_or_forward_validation_after_repair`, `13` `current_source_exhausted`, `23` `lookahead_only_not_exact_proof`, and `43` `not_applicable` low-priority Tier B rows. The exact repair burn-down now reports `145` deduped targets, `11` active unattempted exact targets, `5` source-replay-required targets, `32` diagnostic lookahead-only targets, and `97` exhausted current-source targets; source replay is the next step before more imports. The Tier A fresh-match paper bridge currently has `0` eligible rows, with all `15` fresh matches counted as `not_bridge_eligible`; no live pick is promoted from this artifact. Clear fresh signature matches are SPY/QQQ swing/range/volatility historical signatures only; GOOGL remains high-priority Tier B repair/watch or quarantine evidence, not Tier A proof. NEM is the cleanest Tier A paper-review evidence, but it has no fresh executable match in this artifact.
- first targeted exact repair pass: NEM `bullish_pullback_observation`, LLY `bullish_pullback_observation`, and AAPL `bullish_pullback_observation` were probed through exact ThetaData OPRA/NBBO imports and focused per-ticker reruns. NEM imported `807` trusted later-date rows for `NEM251107C00093000`, but no row for required `2025-10-27`, and rerun stayed `15` / `16` priced. LLY imported `1164` later-date rows for `LLY260109C01155000`, but no row for required `2025-12-10`, and rerun stayed `9` / `10` priced. AAPL imported `111` trusted rows for the first missing dates, but the rerun advanced to `2026-01-13` / `2026-03-16`; a follow-up import found `0` rows through expiry, so AAPL stayed `11` / `13` priced. Treat these as proof-preserving no-promote outcomes, not failures to lower bars.
- second targeted exact repair pass: UNH `bullish_pullback_observation` was probed from `data/options-validation/runs/20260602_102557_sleeve_ticker_unh_intraday.json`. The first import added `561` new trusted rows and the follow-up added `1461` new trusted rows for the moving `UNH251128` leg gaps, but the focused rerun stayed `8` / `10` priced at PF `2.08`. Latest classifier readback is still `provider_no_match_exact_contract_with_same_expiry_chain` for `UNH251128C00410000` on `2025-11-10` and `UNH251205C00390000` on `2025-11-20`; no Tier B row graduated and the queue stayed `97` rows, `15` Tier A, `82` Tier B, and `16` high-priority repairs.
- exact replay importer hardening is now in place. The importer emits a de-duplicated repair manifest with source occurrences, supports `--ticker`, `--contract-symbol`, and `--quote-date` target filters, supports `--plan-only` without ThetaData requests or writes, and treats `--dry-run` as a true no-write fetch/normalize mode. It now records per-base-target `repair_attempts` with exact-date row count, lookahead row count, available dates, first available later date, exact missing-date status, and proof repair status. The classifier supports the same shared target parser and filters so planning and local exact-row classification can be run against the same scoped target set. Latest scoped WMT read from `data/options-validation/runs/20260602_110317_relative_strength_pullback_ex_clean_universe_v1_intraday.json` produced `3` base targets, `12` expanded request targets with `--lookahead-calendar-days 5`, and `3` source occurrences without writing artifacts.
- repair-attempt readback is now available. `scripts/build_regular_options_repair_attempt_readback.py` turns importer summaries into latest keyed attempts and legacy-inferred exact-repair memory at `docs/regular-options-repair-attempts.md`. Current baseline scanned `156` ThetaData exact-missing summaries and has `7,212` keyed latest attempts: `4,754` exact no-match/current-source-exhausted rows, `517` imported-pending-replay rows that require source replay, and `1,941` lookahead-only diagnostic rows. Legacy summaries without per-contract/per-date CSV evidence now treat aggregate date counts conservatively instead of claiming exact-date repair. After any new importer summary is written, rebuild the readback, rebuild the profit-capture queue, and rebuild `docs/regular-options-repair-burndown.md` so future agents do not repeat exhausted provider loops or treat lookahead-only rows as proof repair.
- scoped WMT dry-run result: with `--ticker WMT --lookahead-calendar-days 5 --start-time 09:30:00 --end-time 16:00:00 --interval 1m --dry-run --json`, ThetaData returned `3` normalized rows for `WMT260402C00138000` on lookahead date `2026-03-27`, while `WMT260402C00140000` on `2026-03-25` and `WMT260402C00139000` / `WMT260402C00138000` on `2026-03-26` remained no-match. No CSV, summary, DB import, source replay, or queue rebuild was written from this dry-run.
- legacy rows `26`, `39`, and `44` were audited directly. All three diagnose as `stale_or_non_autoclosing_review_path`, and `current_action_required_count=0`; preserve them as historical stale-policy diagnostics, not a current auto-close bug or global exit-policy change.
- latest guardrail-starvation audit completed `14` / `14` supervised playbooks, included AI Commodity, and audited every configured ticker scope with default `watchlist_size=59`. It returned `13` read-only diagnostics after-hours: `6` clear pending candidates across Swing, Volatility Expansion, and Quality90 canary, plus `7` blocked candidates across Short Term, Speculative, Bullish Momentum, and Range Breakout. The `6` clear regular auto-track rows are queued as `pending_live_validation`, not dropped and not positions. Status is `guardrail_starvation_detected`, led by direction filters (`109`), momentum (`99`), option liquidity (`94`), history/liquidity (`54`), and tech score (`33`).
- latest open-position risk audit reports `12` open regular rows, `11` fresh executable reviews, `1` fresh unpriced review, `0` executable close-ready rows, and `1` review-required non-executable display-only `SELL` row (`id=104`, SBUX). It also shows the live exact QQQ volatility row (`id=537`) as a fresh executable negative HOLD under the stored stop policy. Do not auto-close display-only marks; rerun explicit review during a fresh executable quote window or close only with separate executable evidence.
- the open Trading Desk row for that class of state now shows `Review quote` rather than `Close now` unless the stored `SELL` review includes executable exit evidence.
- latest suggested-trade close-risk audit reports `1` open suggested trade (`id=138`, AAA) with no stored review. There are `0` close-risk suggested rows and `0` executable close-ready suggested rows; refresh explicit review before relying on that paper-idea P&L or close state.
- the Paper Ideas row for that class of state now shows `Review needed`, increments `Needs Review`, and keeps `Close-ready` at `0` unless the latest suggested-trade review has executable `SELL` evidence.
- latest full Trading Desk API performance audit reports `11` / `11` read-only route probes succeeded after compact open-row provenance pruning. Frontend payload total is now `321,783` bytes, backend max duration header is `49.1 ms`, open tracked positions are `139,603` backend bytes / `139,105` Next bytes, and the first `100` compact closed tracked positions remain the largest measured payload at `171,667` backend bytes / `170,715` Next bytes.

1. Treat current-policy picks as paper-only until the recent cohort revalidates. The April current-policy cohort is showable as a discovered edge, but do not showcase May/current rows as a working live algorithm while the latest week is `paper_only_recent_week_break`.

2. Keep the daily all-lanes audit mandatory for no-pick explanations. A scheduled scan route may still run Bullish Pullback when no playbook is supplied, but `scripts/ensure_daily_all_lanes_audit_ran.py` must confirm the all-supervised artifact, include AI Commodity as a separate strategy lane, cover all configured ticker scopes each market day, and queue clear regular auto-track candidates. During a live executable quote window, run the pending validator so selected candidates can be re-quoted with portfolio caps before promotion:

```powershell
uv run --locked python scripts\validate_pending_scan_candidates.py
```

3. Do not change the broad exit policy based on legacy rows `26`, `39`, and `44`, the stored-review stop grid, the tracked current-policy stop grid, or the annual replay-backed stop grid. The focused audits found no current action required. `stop_80` is a tracked-slice research candidate only, because it trims one near-total daily close-check loss but is not minute-level intraday evidence and the annual replay-backed cohort rejects broad stop tightening.

4. Keep `short_term_fill_degradation_ge_15` lane-scoped and paper-only. Do not promote a broad all-lane fill-degradation rule. Rerun the point-in-time scanner replay after new candidate rows and tracked outcomes mature, because the promotion gate must use as-of scanner candidates rather than only realized current-policy rows:

```powershell
uv run --locked python scripts\replay_short_term_filter_point_in_time.py --no-write
```

For the current forward monitor, after fresh rows mature run:

```powershell
uv run --locked python scripts\monitor_current_policy_entry_filter_paper.py --no-write
```

Then run the same command without `--no-write` only when the readback is worth publishing. Do not promote until the monitor has at least `20` fresh current-policy rows, at least `5` champion-matched candidate-blocked rows, trusted executable realized P&L, and passing gates.

5. Use the profit capture queue before lowering proof bars or chasing hidden profitable sleeves:

```powershell
uv run --locked python scripts\build_regular_options_profit_capture_queue.py --no-write
```

Then run without `--no-write` when the readback changes. Use the Evidence Repair Queue table and repair-attempt readback to repair exact missing quote dates/contracts before treating Tier B rows as clean:

```powershell
uv run --locked python scripts\build_regular_options_repair_attempt_readback.py --no-write
uv run --locked python scripts\build_regular_options_profit_capture_queue.py --no-write
uv run --locked python scripts\build_regular_options_repair_burndown.py --no-write
```

The next useful repair work must start from the exact repair burn-down: rerun source replays for `source_replay_required_before_graduation` rows before importing more data, target only `active_unattempted_exact_repair` rows for new exact-provider checks, treat Tier B as `watch_repair_only`, Tier C as `historical_signature_only`, and keep GOOGL blocked from chase/promotion while unresolved or zero-bid issues remain.

Do not repeat the same NEM, LLY, AAPL, UNH, or WMT exact-date repair loop unless the burn-down shows an active unexhausted exact target or a new provider/source can produce positive bid/ask rows for the still-missing dates. Before any next import, run the importer with `--plan-only --json` plus the narrowest useful `--ticker`, `--contract-symbol`, or `--quote-date` filters to inspect the de-duplicated target manifest and source occurrences, then use `--dry-run --json` if a provider fetch is needed before writing CSVs or importing rows. A lookahead-only result is useful memory but not proof repair.

Latest high-priority verification pass after importer hardening: remaining UNH gaps still classify as provider exact-contract no-matches, symbol-sleeve / profit-capture queue / operating scorecard no-write readbacks stayed unchanged, proof/scanner regressions and Trading Desk route tests passed, pending candidate validation returned no candidates for `2026-06-04`, and the AI commodity strict no-write accuracy gate intentionally failed because profitability remains unverified (`3` / `100` exact shared dates, replay locked, `0` live candidates, automation inactive). Keep AI commodity proof-lane checks separate from regular-options ThetaData repair.

6. Treat position `104` as the current open-position safety follow-up: it is not executable-close-ready, so the next action is a fresh explicit executable review, not a display-only auto-close.

7. Treat suggested trade `138` as a paper-idea refresh follow-up, not a close claim: the UI now flags it as review-needed, but it still has no stored review and no executable close evidence.

## Regular Options Multi-Lane Portfolio

Current artifact:
- per-symbol sleeve builder: `scripts/build_regular_options_symbol_sleeves.py`
- per-symbol sleeve latest JSON: `data/profitability-lab/regular-options-symbol-sleeves/latest.json`
- per-symbol sleeve latest Markdown: `data/profitability-lab/regular-options-symbol-sleeves/latest.md`
- per-symbol sleeve report: `docs/regular-options-symbol-sleeves.md`
- profit capture queue script: `scripts/build_regular_options_profit_capture_queue.py`
- profit capture queue latest JSON: `data/profitability-lab/regular-options-profit-capture-queue/latest.json`
- profit capture queue latest Markdown: `data/profitability-lab/regular-options-profit-capture-queue/latest.md`
- profit capture queue report: `docs/regular-options-profit-capture-queue.md`
- repair-attempt readback latest JSON: `data/profitability-lab/regular-options-repair-attempts/latest.json`
- repair-attempt readback report: `docs/regular-options-repair-attempts.md`
- runner: `scripts/run_regular_options_multilane_portfolio.py`
- latest JSON: `data/profitability-lab/regular-options-multilane/latest.json`
- latest Markdown: `data/profitability-lab/regular-options-multilane/latest.md`
- report: `docs/regular-options-multilane-2026-05-30.md`
- frozen autoresearch evaluator: `scripts/evaluate_regular_options_autoresearch.py`
- autoresearch goal prompt: `docs/autoresearch/regular-options-goal.md`
- active options operating scorecard: `scripts/build_regular_profitability_operating_scorecard.py`
- operating scorecard latest JSON: `data/profitability-lab/regular-options-operating-scorecard/latest.json`
- operating scorecard latest Markdown: `docs/regular-options-operating-scorecard.md`
- guardrail starvation audit: `scripts/audit_regular_guardrail_starvation.py`
- guardrail starvation latest JSON: `data/forward-tracking/regular_guardrail_starvation_latest.json`
- guardrail starvation latest Markdown: `docs/regular-guardrail-starvation-audit.md`
- daily all-lanes audit safety net: `scripts/ensure_daily_all_lanes_audit_ran.py`
- daily all-lanes audit command: `npm run options:audit:all-lanes`
- pending selected-candidate queue: `data/forward-tracking/pending_scan_candidates.jsonl`
- pending candidate live validator: `scripts/validate_pending_scan_candidates.py`
- pending candidate live validator command: `npm run options:validate:pending-candidates`
- pending candidate validation disposition latest JSON: `data/forward-tracking/pending_scan_candidate_validation_latest.json`
- open-position risk audit: `scripts/audit_regular_open_position_risk.py`
- open-position risk latest JSON: `data/forward-tracking/regular_open_position_risk_latest.json`
- suggested-trade close-risk audit: `scripts/audit_suggested_trade_close_risk.py`
- suggested-trade close-risk latest JSON: `data/forward-tracking/suggested_trade_close_risk_latest.json`
- Trading Desk API performance audit: `scripts/audit_trading_desk_api_performance.py`
- Trading Desk API performance latest JSON: `data/forward-tracking/trading_desk_api_performance_latest.json`
- autoresearch latest JSON: `data/profitability-lab/regular-options-autoresearch/latest.json`
- autoresearch latest Markdown: `data/profitability-lab/regular-options-autoresearch/latest.md`
- autoresearch ledger: `data/profitability-lab/regular-options-autoresearch/ledger.jsonl`
- autoresearch goal experiment harness: `scripts/run_regular_options_goal_experiment.py`
- autoresearch goal experiment latest JSON: `data/profitability-lab/regular-options-autoresearch/experiments/latest.json`
- latest Lane A memory experiment batch: `data/profitability-lab/regular-options-autoresearch/experiments/20260601T020317Z/summary.json`
- all-planned sleeves runner: `scripts/run_regular_options_all_planned_sleeves.py`
- all-planned latest JSON: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/latest.json`
- all-planned latest full batch: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/20260602T163750Z/summary.json`
- targeted tracked-winner zero-bid batch: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/20260531T074502Z/summary.json`
- latest IWM all-planned partial batch: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/20260531T185035Z/summary.json`
- latest liquidity-first all-planned partial batch: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/20260531T185933Z/summary.json`
- sector ETF import planner: `scripts/plan_regular_sector_etf_imports.py`

Current read:
- per-symbol sleeve matrix: `60` tracked symbols and `343` symbol-lane rows. Classification counts are `keep=25`, `watch=59`, `quarantine=91`, `rejected=82`, and `needs-paper=86`; this is a queue/evidence readback, not a production-promotion claim.
- Bullish Pullback carrier symbols remain `AAPL`, `COP`, `CVX`, `GOOGL`, `IWM`, `JNJ`, `LLY`, `NEM`, `UNH`, and `XOM`. Current Bullish Pullback remove recommendations remain `ABBV`, `BAC`, `C`, `COIN`, `FCX`, `JPM`, `PLTR`, `RTX`, and `SLB`.
- high-beta "crushing" is not proven by the current symbol-sleeve matrix: no high-beta symbol-lane row clears the real-crusher sample/coverage bar; thin positives stay watch/noisy and broad high-beta failures stay quarantined or rejected.
- profit capture queue status: `research_paper_capture_queue`, with `15` Tier A clean exact rows, `82` Tier B profitable watch/repair rows, `16` high-priority evidence repairs, `15` fresh scan matches, `9` blocked-but-interesting rows, and `173` quarantine/do-not-chase rows. Selection readiness is `15` paper-review candidates, `82` watch/repair-only rows, `6` historical-signature-only matches, `9` blocked guardrail rows, and `173` do-not-chase rows. The queue now exposes missing quote-date/contract summaries for medium/high repair rows, intentionally restores profitable evidence visibility without changing scanner guardrails or proof gates, and does not justify live picks from GOOGL, SPY, or QQQ by itself.
- operating scorecard status: `visible_product_profitability_progress_but_proof_still_blocked`. Trading Desk product progress is visible, but proof-grade readiness remains blocked.
- scorecard paper-gate readiness status: `paper_only_no_live_release`. Current read has `0` eligible paper-review candidates, release gate `no_paper_shortlist_candidates`, `0` invariant violations, `20` fresh validation candidates (`15` no-longer-matched and `5` proof-ineligible), `0` exact realized-P&L rows, `0` promotion-ready rows, `2` current-policy paper-validation-only lanes, and repair burn-down counts `11` active / `5` source replay / `32` diagnostic / `97` exhausted. This is readback/navigation only, not live scanner or broker permission.
- Trading Desk promoted guardrails kept subset: `130` rows, `116` priced, avg `+53.08%`, median `+46.4%`, negative rate `25.0%`, versus baseline `429` rows, `383` priced, avg `+5.21%`, median `-1.58%`, negative rate `50.4%`. This is product-side progress, not historical proof-grade promotion.
- live-scan starvation status: `guardrail_starvation_detected` from the all-supervised read-only audit. The latest daily artifact completed `14` / `14` playbooks, included AI Commodity as a separate strategy lane, audited every configured ticker scope with configured `watchlist_size=59`, and returned `13` diagnostics after-hours (`6` clear pending rows across Swing, Volatility Expansion, and Quality90 canary; `7` blocked rows across Short Term, Speculative, Bullish Momentum, and Range Breakout). The clear regular auto-track rows are preserved in `pending_scan_candidates.jsonl` as pending validation candidates. Treat them as selected candidates, not positions, until `scripts/validate_pending_scan_candidates.py` reruns the lane during a live executable quote window with portfolio caps enabled.
- suggested-trade close-risk status: `1` open paper idea (`AAA`, id `138`) has no stored review, no executable close-ready evidence, and no close-risk SELL evidence. Refresh explicit review before using its P&L or close state.
- API performance status: latest local read-only audit passed all `11` probes; the route layer now forwards backend duration headers for Trading Desk/proof-status reads, `/api/options-profit/status` uses a narrow tracked-position snapshot, the largest measured payload remains the first `100` closed tracked rows at `275,004` backend bytes / `273,882` Next bytes, and the full frontend probe payload total is now `466,024` bytes.
- AI commodity status is now visible in the same scorecard: `3` / `100` exact shared Alpaca OPRA dates, `0` live/proof candidates, failed/no-progress fresh scan and `2026-05-29` capture events, and production filters locked until exact Alpaca OPRA replay gates unlock.
- operator read: `200 good trades` is misframed. The multi-lane count gate is passed, but the frozen clean-promotion gate is still blocked.
- combined proof-grade regular stock-options portfolio: `234` trusted intraday exact trades after strict entry-date + ticker + direction dedupe
- PF: `2.16`
- avg PnL: `+26.76%`
- gap to `200`: `0`
- quality gate: `quality_pending`
- count gate: `passed`
- coverage gate: `blocked`
- robustness gate: `blocked`
- paper-shadow gate: `pending`
- counted proof source: trusted intraday OPRA/NBBO exact rows only
- daily/EOD artifacts remain research-only and are not counted toward the proof target
- the `234` stack comes from `sleeve_pf59_coverage_a_refill_v1` plus the latest `lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1`
- latest Lane A read: `155` exact trades, `137` unpriced candidates, `53.1%` quote coverage, PF `3.59`, avg `+42.34%`, 5%/side stress PF `2.65`
- latest Lane A classifier read: `111` missing exact leg/date items still classify as provider no-match exact contracts in the trusted local store, but a raw ThetaData probe found all `111` exact short-leg rows at `15:55` with `bid=0` and `ask>0`; before the June 5 zero-bid repair, the importer/classifier dropped them because it required `bid > 0`
- side-aware Lane A zero-bid replay: `data/profitability-lab/side-aware-zero-bid/latest_lane_a_side_aware_zero_bid.json` priced `126` of `127` missing-exit candidates in conservative long-bid/short-ask mode; `118` priced rows used at least one zero-bid exit quote, the side-aware rows alone were PF `0.11` and avg `-66.59%`, and combined Lane A falls to `281` priced trades at PF `0.85`, avg `-6.51%`, and `96.2%` coverage. Midpoint zero-bid mode is also weak at combined PF `1.11`, avg `+3.79%`.
- contrarian count scan: existing trusted intraday artifacts can reach a raw `300+` exact-priced scenario only by adding low-coverage research artifacts, especially older `tracked_winner_chain_native_qqq_time80_research` artifacts; a current trusted-intraday rerun now makes that scout explicit at `102` strict-new exact trades over the current stack, PF `1.36`, `51.8%` coverage, and `95` unpriced candidates, so it is not production-clean evidence
- latest tracked-winner classifier read: `77` missing exact leg/date items classify as provider no-match exact contracts with same-expiry chain rows present
- clean/high-coverage existing artifacts do not solve the `300` target: clean coverage>=97.5 and unpriced=0 artifacts union to only `134` strict keys, and the clean bullish-pullback reference adds only `17` strict-new rows over the current stack
- frozen autoresearch baseline, from the ledger rather than current `latest.json`: `score: 0.00`, `research_score: 177.74`, status `scout_or_blocked`, clean count `0`, scout count `234`, PF `2.16`, avg `+26.76%`, effective side-aware coverage `96.71%`, unresolved `14`, stress PF `1.53`, zero-bid exit rate `41.99%`, Lane A conservative PF `0.85`
- current autoresearch `latest.json`: latest global evaluator result, not the immutable baseline. The goal experiment harness now writes evaluator outputs experiment-scoped by default, and only overwrites global latest when run with explicit `--write-global-latest`; use the ledger or `python scripts/evaluate_regular_options_autoresearch.py --no-write --score-line` for baseline/current-stack truth.
- first Lane A goal-loop result: simple entry survivability filters were not enough. The best entry-filter variant, `lane_a_goal_stop200_time75_shortprior3_shortbid10_backfill`, improved effective coverage to `99.09%` and unresolved candidates to `3`, but left Lane A conservative PF at `0.88` and zero-bid exit rate above `42%`.
- second Lane A goal-loop result: the bad-zero-ticker/debit repair proved the economics can be improved but not at enough count. `lane_a_goal_bad_zero_ticker_exclusion_debit45_npicks8` reached `research_score: 236.19` and Lane A conservative PF `1.30`, but only `81` exact Lane A trades, so Lane A was not counted and the stack fell back to the `130`-trade core.
- third Lane A goal-loop result: causal exit-failure and symbol-health memory improved coverage but not clean profitability. The latest experiment-scoped batch `20260601T020317Z` kept evaluator outputs local with `--no-append-ledger`; the best branch, `lane_a_goal_stop200_time75_symbol_health90_backfill`, had effective coverage `99.06%`, unresolved `3`, PF `2.13`, avg `+27.22%`, scout count `191`, zero-bid exit rate `43.24%`, and Lane A conservative PF `0.92`. It is better than the raw baseline but still below the Lane A conservative PF gate and below the `200` clean count requirement.
- replacement-sleeve check: core plus the clean exact reference reaches only `157` strict-deduped trades; core plus clean reference plus all high-PF/coverage cluster artifacts reaches only `158` because of overlap. Current trusted-intraday tracked-winner replacements failed profitability (`tracked_winner_chain_native_qqq_time65_research` reran at `109` exact trades but PF `1.04`).
- all-planned sleeve audit: the latest full batch tested `30` implemented planned regular stock-options variants with `0` run failures, and the current code now exposes `44` implemented variants after adding IWM, liquidity-first tracked-winner, and regular sector ETF probes. The audit still does not show a clean gap-closer. The previous near-gap tracked-winner candidates are rejected by side-aware zero-bid economics: the targeted batch priced the missing exits and marked no-SPY `not_worth_after_zero_bid_replay` at conservative combined PF `0.62`, and GOOGL/NVDA `not_worth_after_zero_bid_replay` at conservative combined PF `0.67`. The first regular sector ETF partial batch `20260601T015109Z` rejected the simple sector shapes: SMH PF `0.49`, regular sector stack PF `0.27`, and TLT/XLE/XLF/KRE no current candidates.
- multi-lane quality gate now makes side-aware Lane A zero-bid economics an explicit blocker instead of leaving it as narrative evidence. Current read still passes the raw count target with `234` strict-deduped exact trades, but production readiness remains `quality_pending`: conservative combined Lane A zero-bid PF is `0.85` below the `1.30` gate, conservative combined unpriced exits are `11`, and zero-bid exit rate is `41.99%` above the `2%` gate.
- IWM conversion result: `iwm_small_cap_risk` is no longer just a stale readiness row. The current partial run tested `sleeve_ticker_iwm`, `iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves`, and `iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves`. The per-ticker sleeve has PF `2.47` but only `11` exact trades, `73.3%` coverage, and `0` strict-new trades over the `157` stack; the WFO call probe has `18` exact trades, PF `1.25`, `100.0%` coverage, `7` strict-new rows, and stress PF `0.87`; the put probe is unprofitable at PF `0.0` with `20.0%` coverage. Do not promote IWM's current shapes.
- planned-but-not-tested ledger: the runner now keeps same-`lane_id` lane-lab rows visible when an implemented replay variant exists but the lane-lab spec still needs paper/forward evidence. Current code reports `32` non-AI lane-lab rows needing follow-up: `14` pending forward/paper logs, `9` blocked by instrumentation, `6` blocked by missing data, `1` partial fill-discipline paper result, `1` scored high-debit control, and `1` ready/paper-backtest row now represented by runnable IWM diagnostics.
- replay-side fill diagnostics: historical WFO chain-native spread rows now persist `selected_spread`, `top_spread_alternatives`, `fill_degradation_vs_mid`, `entry_spread_mid_debit`, and `entry_spread_ask_bid_debit` as `diagnostic_only`. The first causal liquidity-first tracked-winner contract-hygiene probe failed and should not be promoted: `tracked_winner_liquidity_first_contract_hygiene_v1` had `102` strict-new exact trades and closed the count gap on paper, but standalone PF was `0.81`, avg `-5.22%`, coverage `58.0%`, stress PF `0.53`, and worth status `not_worth_current_shape`.
- sector ETF data blocker: cleared. Current trusted intraday `options_history.db` readiness is `IWM=252` quote dates, and `GLD`, `TLT`, `XLE`, `XLF`, `SMH`, and `KRE` each have `252` trusted shared quote dates from `2025-05-22` through `2026-05-22`. Bounded 2026-05-31/2026-06-01 imports created batches `1832` through `1920`, totaling `2,651,299` trusted intraday sector ETF rows with `0` rejects. The latest planner readback returned `ready_for_sector_replay`; there are no remaining sector data-depth blockers. GLD data is ready, but no GLD/commodity-lane sleeve was added in the regular-lane-only pass.

1. Use the operating scorecard before answering whether we are seeing results:

```powershell
python scripts/build_regular_profitability_operating_scorecard.py --json
```

It separates product-side Trading Desk profitability progress from proof-grade historical readiness.

2. Use the starvation audit when current live scan output is empty:

```powershell
python scripts/audit_regular_guardrail_starvation.py --top-limit 8
```

It separates guardrail-blocked candidates from upstream scanner/data/liquidity zero-candidate pressure.

3. Use the multi-lane runner before arguing trade count. It separates portfolio-candidate lanes, intraday scouts, daily/EOD research, blocked lane specs, and the Lane A side-aware zero-bid quality gate.

4. Use the per-symbol sleeve builder before making ticker-specific queue claims:

```powershell
python scripts/build_regular_options_symbol_sleeves.py --json
```

It separates symbol-lane status from evidence class and keeps queue removals/quarantines as recommendations unless scanner config is explicitly changed.

5. Use the frozen autoresearch evaluator before running `/goal` loops or accepting strategy changes. The evaluator's hard `promotable_clean` gates are: `>=200` clean trades, PF `>=1.50`, avg PnL `>0`, effective coverage `>=97.5%`, unresolved candidates `0`, 5%/side stress PF `>=1.25`, rolling/OOS pass, side-aware conservative Lane A replay if Lane A is counted, Lane A conservative PF `>=1.30`, and zero-bid exit rate `<=2%`. Paper-shadow pass is still required for production readiness.

6. Keep the explicit tracked-winner intraday scout in the multi-lane runner before saying the existing artifact set cannot reach `300`. It has enough strict-new rows to matter for raw count, but the current rerun fails PF and coverage gates, so it should stay behind the quality gate unless a redesigned causal/contract-selection version clears them.

7. Stop treating simple Lane A filter tuning, Lane A causal memory tuning, tracked-winner GOOGL/NVDA survivability, or the first regular sector ETF shapes as the best route to `200` clean trades. Lane A entry short-bid, prior-quote, liquidity-score, tradability, early-exit, debit/width, broad bad-zero-ticker, selected-contract exit-failure memory, and symbol-health memory probes either leave conservative PF below gate or reduce the lane below the `100` exact-trade portfolio-candidate threshold. GOOGL/NVDA/no-SPY tracked-winner misses have now failed side-aware zero-bid economics. IWM is runnable but not promotable in the current shapes. The first liquidity-first tracked-winner contract-hygiene rule also failed PF, coverage, and stress gates. Sector ETF data is now ready, but the first XLE/XLF/KRE/SMH/TLT/sector-rotation probes were rejected or starved; the next implementation target should be a materially different causal liquidity/exit rule or non-overlapping sleeve construction rather than tuning these failed simple shapes.

8. Do not promote the newly tested bearish put, range-breakout, or volatility-expansion probes. Put-chain data was imported and exact exits were filled where possible; the bearish time-exit lane priced `73` exact trades at PF `0.21`, and range/volatility probes remained negative or below breakeven.

9. It is now fair to say every currently implemented planned sleeve in the all-planned runner has either full-batch coverage or a focused partial artifact, including IWM. It is not fair to say every planned lane-lab spec is fully tested: `32` non-AI lane-lab rows still need data imports, paper logs, or structure/instrumentation support before they can produce promotion-grade replay metrics. Keep those specs visible and burn them down systematically rather than ranking them away.

10. Sector ETF replay status: the import plan is complete. Rerun the planner before any future sector work and require `ready_for_sector_replay`:

```powershell
.venv\Scripts\python.exe scripts/plan_regular_sector_etf_imports.py --json
```

The first implemented regular-sector variants live in `scripts/run_regular_options_all_planned_sleeves.py` and can be rerun with `--only tlt_duration_shock_call_chain_native_timeexit_all_sleeves tlt_duration_shock_put_chain_native_timeexit_all_sleeves xle_energy_inflation_call_chain_native_timeexit_all_sleeves xle_energy_inflation_put_chain_native_timeexit_all_sleeves xlf_financials_call_chain_native_timeexit_all_sleeves xlf_financials_put_chain_native_timeexit_all_sleeves kre_regional_bank_call_chain_native_timeexit_all_sleeves kre_regional_bank_put_chain_native_timeexit_all_sleeves smh_semiconductor_call_chain_native_timeexit_all_sleeves sector_rotation_regular_etf_call_stack_v1`. Current partial batch `20260601T015109Z` rejected the simple shapes: SMH PF `0.49`, sector stack PF `0.27`, and TLT/XLE/XLF/KRE no current candidates. Do not promote them or count them toward the clean gap.

## Bullish Pullback Observation Lane

Current full active-universe exact-contract status:
- active universe: `59` symbols from `data/options-lanes/universes/bullish_pullback_observation.json`
- `CMCSA` excluded from the active universe
- trusted ThetaData intraday OPRA/NBBO coverage: all active symbols, `252` shared dates from `2025-05-22` through `2026-05-22`
- preserved baseline artifact: `data/options-validation/runs/20260527_211058_bullish_pullback_observation_intraday.json`
- current high-PF cluster artifact: `data/options-validation/runs/20260528_013544_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1_intraday.json`
- current high-PF cluster robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1.json`
- current high-coverage cluster artifact: `data/options-validation/runs/20260528_014057_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1_intraday.json`
- current high-coverage cluster robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1.json`
- current clean quoted subset artifact: `data/options-validation/runs/20260528_014353_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1_intraday.json`
- current count-expanded all-59 refill artifact: `data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json`
- current count-expanded all-59 refill robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_pf59_coverage_a_refill_v1.json`
- current frozen layer-stack artifact: `data/profitability-lab/bullish-pullback-observation/layer-stack/latest.json`
- current frozen layer-stack report: `docs/bullish-pullback-layer-stack-2026-05-29.md`
- latest next-layer report: `docs/bullish-pullback-next-layer-profitability-2026-05-29.md`
- latest next-layer sleeve round: `data/profitability-lab/bullish-pullback-observation/sleeves/sleeve_round_20260529T052213Z.json`
- latest next-layer scoreboard: `data/profitability-lab/bullish-pullback-observation/next-layer-summary-2026-05-29.json`
- latest next-layer import artifacts: `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T050747Z.json` and `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T051508Z.json`
- current confidence-tier report: `data/profitability-lab/bullish-pullback-observation/confidence/latest.json`
- current per-ticker keep/move/remove audit: `docs/bullish-pullback-ticker-audit-2026-05-29.md` and `data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json`
- previous strict quoted-exit lead artifact: `data/options-validation/runs/20260528_005918_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_v1_intraday.json`
- current fully priced mixed/settlement artifact: `data/options-validation/runs/20260528_010301_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly75_v1_intraday.json`
- sleeve sweep artifacts: cluster/all-59 rounds under `data/profitability-lab/bullish-pullback-observation/sleeves/`, including `sleeve_round_20260528T025450Z.json`
- best clean 100% exact branch: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`
- best 130-trade PF branch: `data/options-validation/runs/20260528_013904_sleeve_winner_cluster_exit_balanced_quoted_v1_intraday.json`
- latest defensive refill scout rerun: `data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json`
- latest defensive refill exact-fill attempt: `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json`
- zero-pick all-lanes current-algorithm audit script: `scripts/audit_zero_pick_days_all_lanes.py`
- zero-pick all-lanes current-algorithm audit report: `data/forward-tracking/all_lanes_zero_pick_current_algo_audit_latest.json`
- zero-pick all-lanes latest report-only repair status: the 2026-06-05 missed-pick rerun excluded AI commodity, completed `13` / `13` regular scan lanes, found `405` signal candidates, `389` exact historical candidates, and `206` would-track selections with `apply=false`, `0` scan rows appended, no `no_exact_option_quotes_for_date` blocker, and quote-store coverage `9` / `10` market days with only `2026-06-05` missing before session data existed.
- zero-pick all-lanes latest applied status: the 2026-05-31 applied run completed `14` / `14` supervised scan lanes and appended `425` exact historical research/backfill picks to the forward scan/fill logs.
- zero-pick all-lanes paper-position migration report: `data/forward-tracking/all_lanes_zero_pick_position_migration_v1_latest.json`
- zero-pick all-lanes paper-position migration status: `425` historical paper positions created; after suggested-close P&L repair, `400` are closed and `25` are open as of `2026-05-31`; all `425` scan rows and fill-attempt rows are linked to tracked position IDs. Lane counts are `short_term=159`, `swing=157`, `bullish_momentum=51`, `tracked_winner_observation=35`, `tracked_winner_primary=12`, `volatility_expansion_observation=10`, and `range_breakout_observation=1`.
- historical suggested-close P&L repair report: `data/forward-tracking/historical_suggested_close_realized_pnl_repair_v1_latest.json`
- historical suggested-close P&L repair status: the June 5 safe missing-only repairs updated the first `27` rows, imported missing late-day exact OPRA/NBBO close clusters, then repaired the remaining `34` diagnostics (`24` missing quote rows and `10` zero-bid close rows). Final strict repository audit now reports `0` hard violations and `0` diagnostics. Do not synthesize future unresolved exits from midpoint, last trade, daily/EOD, or stale marks.
- zero-pick explicit single-lane diagnostic script: `scripts/audit_zero_pick_days_current_main_lane.py`
- zero-pick explicit single-lane diagnostic report: `data/forward-tracking/main_lane_zero_pick_current_algo_audit_latest.json`
- zero-pick paper-position migration script: `scripts/migrate_main_lane_backfills_to_positions.py`
- zero-pick paper-position migration report: `data/forward-tracking/main_lane_zero_pick_position_migration_latest.json`
- zero-pick audit tracking status: `60` exact historical legacy single-lane picks appended as `research_backfill` / `backfilled_historical_track` and explicitly migrated into UI-backed Postgres paper tracked positions; after suggested-close P&L repair, final audit-position state is `23` open and `37` closed. These are historical paper positions, not live-production proof.

1. Use `sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1` as the high-PF profitability-first paper/live-shadow branch: `120` candidates, `113` exact quoted trades, `7` unresolved candidates, `94.2%` quote coverage, PF `4.34`, avg `+49.78%`, median `+54.20%`, win rate `72.6%`, and all priced exits are bid/ask `time_exit` fills. It excludes `CAT`, `PM`, `PLD`, and `XLK`, uses 60% DTE exits for energy/GOOGL/JNJ/LLY, 55% for NEM/IWM, and 50% for AAPL/UNH.

2. Use `sleeve_pf59_coverage_a_refill_v1` as the count-expanded all-59 paper-shadow candidate when the goal is enough trades rather than max PF: latest rerun `data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json` has `133` candidates, `130` exact quoted trades, `3` unresolved WMT/JNJ provider no-match candidates, `97.7%` quote coverage, PF `2.04`, avg `+24.54%`, rolling test `34` exact trades at PF `2.35`, and 5%/side stress PF `1.53`. Its robustness status is still `blocked` only because the `3` full-sample unpriced candidates remain unresolved.

Latest 2026-05-29 next-layer stop state:
- Do not promote `sleeve_next_move_bucket_refill_v1`: after successful ThetaData imports it is the highest new move-bucket count scout at `135` exact trades and PF `2.03`, but quote coverage is only `91.2%`, `13` candidates remain unpriced, and 5%/side stress PF is `1.49`.
- Do not promote `sleeve_next_defensive_refill_v1`: after a post-layer exact-fill attempt and rerun it remains `130` exact trades at PF `2.15`, but coverage is only `94.2%`, `8` candidates remain unpriced, and the incremental WMT/PM refill tier is only `22` exact trades at PF `1.36` and avg `+7.66%`.
- Do not continue high-beta bullish-pullback or momentum variants without a new causal hypothesis: `sleeve_next_high_beta_survival_v1` was `16` exact trades at PF `0.11`, and `sleeve_next_high_beta_momentum_fast_v1` was `44` exact trades at PF `0.20`.
- Treat ETF/index, PM, PLD, and CAT as small scout lanes only. Their isolated exact samples are too thin to close the `70` to `92` annual-trade gap.
- ThetaTerminal v3 is available and the missing-contract import loop was rerun. Further count-expansion work should start from the new exact import artifacts, rerun replay/classifier/robustness after any additional import, and treat remaining provider no-match exact contracts as non-proof unless ThetaData returns executable bid/ask rows for the exact OCC contract.

3. Use `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1` when coverage/count cleanliness matters more than raw PF and before adding the lower-PF refill block: `116` candidates, `115` exact quoted trades, `1` unresolved JNJ provider no-match, `99.1%` quote coverage, PF `2.57`, avg `+34.29%`, and rolling test `36` exact trades at PF `2.59` with `0` unpriced test candidates. It stays positive under 5%/side stress at PF `1.95`, top-5 winner removal at PF `2.08`, worst-ticker removal at PF `2.08`, and worst-month removal at PF `2.06`.

4. Keep `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1` as the clean quoted proof subset: `95` candidates, `95` exact quoted trades, `0` unresolved, `100.0%` quote coverage, PF `3.36`, avg `+44.07%`, 5%/side stress PF `2.56`, top-5 winner removal PF `2.66`, worst-ticker removal PF `2.71`, and worst-month removal PF `2.61`. It is below the `100`-trade target and lacks a full rolling window, so treat it as a clean component sleeve rather than the main paper family.

5. Use the confidence-tier report and per-ticker audit as the picking queue rather than forcing a pick for every tracked stock. Current S/A/B has `108` exact quoted trades across `10` keep symbols at PF `4.86` and avg `+53.22%`: `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, and `NEM`.

6. Route positive or strategic but non-promoted symbols to separate frozen hypotheses before allowing picks: ETF/index (`QQQ`, `DIA`, `XLK`), high-beta (`NVDA`, `AMZN`, `TSLA`), defensive/refill (`WMT`, `PM`), industrial scout (`CAT`), and REIT/rate-sensitive (`PLD`). Remove `JPM`, `BAC`, `C`, `ABBV`, `SLB`, `RTX`, `FCX`, `COIN`, and `PLTR` from the current bullish-pullback tradable queue.

7. Do not call the 100+ quoted cluster or expanded refill sleeves strict proof-complete yet. Bounded exact-fill/classification for the cluster branches wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260528T074150Z.json`; the refreshed count-expanded imports wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T042128Z.json` and `20260529T042332Z.json` and returned `0` exact rows for the WMT/JNJ misses. The WMT/JNJ gaps remain provider no-match exact-contract gaps with same-expiry chain rows present.

8. Do not keep tuning broad all-59 refill variants or the 2026-05-29 move-bucket scouts as the next route. The tested broader refills added exact trades but failed the reliability tradeoff: the highest-count branch reached `165` exact trades but PF fell to `1.49`, coverage remained near `90%`, broad C/Blocked evidence is not tradable, and the best move-bucket scout added only `5` exact trades while missing the coverage/stress gates. The desired `200+` annual exact-trade cadence is blocked by lack of a repeatable exact pattern, not by an unattempted local ThetaData import.

9. Next concrete implementation target: wire `data/profitability-lab/bullish-pullback-observation/layer-stack/latest.json` into paper-shadow reporting/harness selection, then add an assignment/expiration-safe live-shadow harness for the quoted cluster and `sleeve_pf59_coverage_a_refill_v1` branches. Add trailing partial-window robustness and leg-level bid/ask execution audit/stress before sizing beyond paper. Separate scout lanes should resume only after a new data import or causal hypothesis, not by rerunning the exhausted 2026-05-29 variants.

10. Keep the broad baseline as the control. The current baseline remains weak (`21` exact trades, PF `0.83`), so sleeve profitability is coming from allocation/selection/execution changes rather than a silent baseline behavior change.

## AI Commodity / Commodity-Infrastructure Lane

Current readback source: `data/ai-commodity-infra/progress/latest.md`, generated `2026-06-03T20:22:59Z`.

Current state:
- proof source: `alpaca:sip:opra` / `alpaca_opra_daily_snapshot`
- exact shared quote dates: `3` / `100`, from `2026-05-20` through `2026-05-22`
- scan/proof universe: `24` aligned symbols
- latest live scan candidates: `0`; the `2026-06-01` fresh scan had quote freshness `fresh_or_not_age_limited` and still recorded raw drop reasons for `24` symbols
- latest guarded capture target: `2026-05-29`, attempted again on `2026-06-03` with latest generated artifact `2026-06-03T20:22:59Z`
- latest capture result: failed/no material progress again; capture status was `no_rows_captured`, all `24` target symbols remained missing for `2026-05-29`, shared quote dates stayed `3`, `exact_capture_progress_outcome.status` is `exact_capture_progress_failed_or_not_observed`, local exact store already matches the proof window, local refresh cannot advance history depth, `snapshot_updated_since_is_backfill_capability=false`, and missed capture dates since the latest shared date are `2026-05-26`, `2026-05-27`, and `2026-05-28`
- next guarded event: the runbook still reports `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-29` as ready, but this target has repeatedly failed with no rows captured and now points the next evidence action at `repair_full_scan_universe_capture_and_proof_alignment`; inspect/repair the full-universe capture path before looping it
- full replay unlock projection: `2026-10-15` if one shared OPRA date is captured per market day

1. Wait until the next guarded event and rerun the generated runbook readback before using any stale command:

```powershell
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
```

Current guard state after the failed capture: `run_next_execution_command=true`, `guarded_command_decision_status=ready_to_run_primary_next_execution`, and `guarded_command_decision_safe_to_execute_now=true`, but this is the same repeated no-progress `2026-05-29` capture target and the next evidence action is repair, not replay or filter work.

2. If that readback opens the fresh-scan guard, run exactly the allowed command:

```powershell
python scripts/run_ai_commodity_opra_progress.py --skip-capture
```

Then immediately run the readback again:

```powershell
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
```

3. Repair the full-universe capture failure before replay or filter work. The current target is `2026-05-29`, and the lane also reports missed capture dates `2026-05-26`, `2026-05-27`, and `2026-05-28`. The 24-symbol capture universe remains `FCX`, `SLV`, `VRT`, `VST`, `ETN`, `GEV`, `PWR`, `CCJ`, `CEG`, `SCCO`, `COPX`, `URA`, `ALB`, `SQM`, `MP`, `RIO`, `BHP`, `TECK`, `AA`, `XME`, `NRG`, `NVT`, `CARR`, and `TT`.

4. If the local store changed and the readback says derived evidence is stale, refresh deterministic readiness without recapturing or rescanning:

```powershell
python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan
```

5. Continue daily guarded captures until the shared-date gate reaches `100` and exact replay unlocks. Run full replay only when the generated runbook says the exact replay unlock contract is ready:

```powershell
python scripts/run_ai_commodity_opra_progress.py
```

6. Keep production filters locked until exact OPRA replay has enough shared bid/ask history, a completed replay with trades, positive profitability metrics, and a live candidate inside the exact proof universe.

7. If a licensed ThetaData Standard/Pro terminal is available on port `25503`, use `scripts/import_thetadata_options_nbbo.py` to import at least 100 shared market days for the full 24-symbol AI commodity universe, then run `scripts/audit_paid_data_readiness.py` against that source label before using it in replay.

8. Treat OnclickMedia EOD chains and Alpaca historical option bars/trades as research support only. They are not final proof-grade bid/ask replay sources for this lane.
