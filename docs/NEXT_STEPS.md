# Next Steps

Last updated: 2026-06-04

## Documentation Hygiene

Current read:
- global agent behavior rules live in `C:\Users\kalec\AGENTS.md` and `C:\Users\kalec\CLAUDE.md`
- repo-specific agent startup and evidence rules live in `AGENTS.md`
- living-doc ownership, generated-artifact, and source-of-truth hygiene rules live in `docs/living-docs-hygiene.md`
- `npm run verify:docs` now runs generated artifact checks, the final remediation closure pack check, and `scripts/check_living_docs_hygiene.py`
- latest Markdown placement audit: `docs/markdown-audit-2026-05-31.md`

1. When adding new Markdown, update `docs/index.md` only for living docs or reports that change the current decision surface. Keep generated research reports beside their source artifacts under `data/` or `research_runs/`.

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

1. Add a small browser unlock affordance for `POST /api/operator/session` so local operators do not need to use curl or scripts to open the HttpOnly session cookie.

## Proof/Evidence Contract

Current read:
- proof/evidence semantics are versioned at `data/contracts/proof-evidence-contract.json` and explained in `docs/proof-evidence-contract.md`
- `python-backend/proof_contract.py` owns the backend proof predicates used by `positions_service.py` and `/api/proof-summary`
- `options_profit_gate.py` and `options_profit_flywheel.py` consume the same closed-row proof-grade predicate for production readiness metrics
- generated `src/lib/generated/proofEvidenceContract.ts`, `src/lib/trading-desk/proofContract.ts`, and `src/lib/trading-desk/positionEvidence.ts` consume the same proof classes, entry-proof gates, display groups, research/backfill markers, quote-freshness tokens, and exit-basis tokens
- production evidence remains limited to fresh live scanner exact-contract proof; creation-time classification, stored-row predicates, and frontend display re-check exact selection source, verified scan lineage, OPRA source, executable entry, present acceptable quote freshness, trusted closed exit, calculable P&L, and absence of row-level or source-snapshot backfill/migration identity fields such as `backfill_audit_id`, `position_migration_id`, and `position_migrated_at_utc` rather than trusting stale proof flags

1. Consider emitting `evidence_group` and `proof_contract_version` from backend compact rows so frontend display can stop inferring display groups from mixed historical fields.

## Live Scanner And Creation Safety

Current read:
- scanner creation safety semantics are versioned at `data/contracts/scanner-creation-safety-contract.json` and explained in `docs/scanner-creation-safety-contract.md`
- regular playbooks now carry `fresh_live_validation_enabled`, `position_tracking_mode`, and `proof_scope` metadata; every regular supervised options playbook defaults to `position_tracking_mode=auto_track`, while AI Commodity remains separate with scanner/tracked-position tracking disabled
- browser/API/scheduled production scans default to portfolio caps on; caps-off production scan requests are rejected unless marked diagnostic or explicitly allowed
- scheduled auto-track requires the environment kill switch to be on, `market_open_at_run=true`, a regular auto-track playbook, `exposure_snapshot.available=true`, `exposure_snapshot.portfolio_caps_enforced=true`, and per-pick creation metadata with no `creation_blockers`
- scanner-origin tracked-position and suggested-trade creation requires verified archived forward-scan lineage, caps-enforced source scan state, source `creation_eligible=true`, a current guardrail rerun that still has caps-enforced `creation_eligible=true` and no blockers, and proof-eligible exact-contract evidence
- explicit `manual_paper` and `manual_broker` creation modes remain available for research/backfill or broker/manual rows, but those rows do not become production proof without exact OPRA/NBBO evidence and verified lineage
- portfolio guardrails still include existing-position exposure, max concurrent positions, cost-risk, open executable drawdown, and correlated-index exposure, but these surface as visible cautions/sizing notes rather than hard blockers for otherwise proof-eligible trades
- side-aware zero-bid replay now stores entry/exit quote evidence plus stable hashes so replay rows can be audited without relying on implicit quote reconstruction

1. During the next market-hours scan, verify `scripts/validate_pending_scan_candidates.py` processes all pending regular validation-enabled lanes and that all regular auto-track lanes can create rows after fresh executable evidence, while blocked/stale/unpriced/proof-ineligible rows receive explicit validation dispositions.

2. Rerun the point-in-time scanner candidate replay after new regular candidate/outcome rows mature, and add minute-level OPRA/NBBO stop/target/profit-harvest replay before promoting any exit rule.

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
- Current Policy and Learned Away views keep loading closed-history pages until the policy read is complete, because the first `100` newest closed rows can be a materially worse recent slice than the full historical policy replay
- live review intentionally honors `90%` configured stops for profit-first paper/live-shadow behavior
- configured stops wider than `90%` are capped to `90%`, while retaining both `configured_stop_loss_pct` and `effective_stop_loss_pct` in review metrics
- verified executable zero exits can now auto-close paper positions at `0.0` instead of leaving total-loss options open
- display-only last-price marks still suppress stop/target triggers and do not auto-close positions
- passive positions/suggestions polling in the UI is now read-only; explicit refresh/review actions are required before the UI POSTs review requests
- `POST /api/positions/review` is still state-changing: it saves reviews and can auto-close executable `SELL` recommendations
- closed-position realized P&L is now canonicalized from entry/exit execution prices when an exit price exists, and create-time pre-closed rows preserve gross/net P&L columns
- local tracked-position audit after the repair: `87` closed rows, `75` priced rows with canonical realized P&L, and `12` historical lifecycle-only closed rows with no trusted exit quote and therefore no assigned P&L; backup: `data/tracked_positions.pre-realized-pnl-repair-20260531T184725Z.json`
- open-position risk audit now writes `data/forward-tracking/regular_open_position_risk_latest.json` and feeds the regular operating scorecard. Current read: `48` open regular rows, `47` fresh executable reviews, `1` fresh unpriced review, `0` executable close-ready rows, and `1` review-required non-executable display-only `SELL` row (`id=104`, SBUX).
- suggested-trade close-risk audit now writes `data/forward-tracking/suggested_trade_close_risk_latest.json` and feeds the regular operating scorecard. Current read: `1` open suggested trade (`id=138`, AAA), `0` executable close-ready rows, `0` non-executable close-risk rows, and `1` stale/missing-review row. Refresh explicit review before relying on suggested-trade P&L or close state.
- Postgres tracked-position requests now reuse successful connections through a small in-process pool in `python-backend/positions_repository.py`; failed requests roll back and discard the connection before the next request.
- FastAPI responses now include `x-python-backend-duration-ms` so local Trading Desk/API checks can compare route latency before and after payload or query changes.
- Trading Desk and proof-status Next read routes now forward `x-python-backend-duration-ms` from the Python backend, so route probes can compare Next elapsed time against backend handler time without changing response bodies.
- `/api/positions` and `/api/suggested-trades` now accept `limit` and `offset`, forward those windows through the Next API layer, and return page metadata so the UI can lazy-load closed/history-heavy tables.
- `PredictionsView.tsx` now fetches open tracked positions and open suggested trades by default; Closed Trades and Closed Ideas request the first `100` rows on demand and page older closed rows through `Load More`, so Open and Tracked Stocks refreshes no longer pull the full closed/research archive.
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
- pending selected-candidate queue: `data/forward-tracking/pending_scan_candidates.jsonl`
- pending candidate live validator: `scripts/validate_pending_scan_candidates.py`
- pending candidate live validator command: `npm run options:validate:pending-candidates`
- pending candidate validation disposition latest JSON: `data/forward-tracking/pending_scan_candidate_validation_latest.json`
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

Current read:
- repair scope is the regular supervised Trading Desk lanes: `short_term`, `swing`, `bullish_momentum`, and Bullish Pullback
- baseline replay: `429` rows, `383` priced, `193` negative, `190` positive/flat, `46` unknown, average P&L `5.21%`, median P&L `-1.58%`
- promoted combined kept subset: `130` rows, `116` priced, `29` negative, `87` positive/flat, average P&L `53.08%`, median P&L `46.4%`
- current-policy closed-row replay: `488` closed rows audited, `400` current-policy scope rows, raw realized scope `355` priced at avg `+4.87%`, median `-6.53%`, negative rate `51.8%`; `would_take_today` has `112` priced rows at avg `+53.54%`, median `+50.6%`, negative rate `25.9%`; `blocked_by_current_policy` has `274` rows / `243` priced at avg `-17.56%`, median `-30.41%`, negative rate `63.8%`
- current-policy cohort health: overall current-policy rows are still positive (`112` priced, avg `+53.54%`, median `+50.6%`), but the showable edge is concentrated in `2026-04` (`70` priced, avg `+81.17%`, median `+71.82%`, `8.6%` negative rate). Recent `2026-05` degraded to avg `+7.49%`, median `-4.6%`, `54.8%` negative rate, and latest week `2026-W21` is avg `-82.06%`, median `-83.61%`, `100.0%` negative rate. Current state is `paper_only_recent_week_break`.
- scanner guardrails now block debit over `45%` of width, fill degradation `>=20%`, worst-leg bid/ask spread `>=20%`, lane-specific ticker quarantines, Bullish Pullback non-keep tickers, and Bullish Pullback `ret5 < -2`
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
- profit capture queue is now the visibility layer for profitable evidence before scanner changes. Current read after the high-priority repair pass: `97` research/paper queue rows, `15` Tier A clean exact rows, `82` Tier B profitable watch/repair rows, `16` high-priority evidence repairs with missing quote-date/contract summaries, `15` fresh scan signature matches, `9` blocked-but-interesting candidates, and `173` quarantine/do-not-chase rows. Selection readiness is explicit: `15` `paper_review_candidate`, `82` `watch_repair_only`, `6` `historical_signature_only`, `9` `blocked_guardrail_only`, and `173` `do_not_chase`. Clear fresh signature matches are SPY/QQQ swing/range/volatility historical signatures only; GOOGL remains high-priority Tier B repair/watch or quarantine evidence, not Tier A proof. NEM is the cleanest Tier A paper-review evidence, but it has no fresh executable match in this artifact.
- first targeted exact repair pass: NEM `bullish_pullback_observation`, LLY `bullish_pullback_observation`, and AAPL `bullish_pullback_observation` were probed through exact ThetaData OPRA/NBBO imports and focused per-ticker reruns. NEM imported `807` trusted later-date rows for `NEM251107C00093000`, but no row for required `2025-10-27`, and rerun stayed `15` / `16` priced. LLY imported `1164` later-date rows for `LLY260109C01155000`, but no row for required `2025-12-10`, and rerun stayed `9` / `10` priced. AAPL imported `111` trusted rows for the first missing dates, but the rerun advanced to `2026-01-13` / `2026-03-16`; a follow-up import found `0` rows through expiry, so AAPL stayed `11` / `13` priced. Treat these as proof-preserving no-promote outcomes, not failures to lower bars.
- legacy rows `26`, `39`, and `44` were audited directly. All three diagnose as `stale_or_non_autoclosing_review_path`, and `current_action_required_count=0`; preserve them as historical stale-policy diagnostics, not a current auto-close bug or global exit-policy change.
- latest guardrail-starvation audit completed `14` / `14` supervised playbooks, included AI Commodity, and audited every configured ticker scope with default `watchlist_size=59`. It returned `13` read-only diagnostics after-hours: `6` clear pending candidates across Swing, Volatility Expansion, and Quality90 canary, plus `7` blocked candidates across Short Term, Speculative, Bullish Momentum, and Range Breakout. The `6` clear regular auto-track rows are queued as `pending_live_validation`, not dropped and not positions. Status is `guardrail_starvation_detected`, led by direction filters (`109`), momentum (`99`), option liquidity (`94`), history/liquidity (`54`), and tech score (`33`).
- latest open-position risk audit reports `48` open regular rows, `47` fresh executable reviews, `1` fresh unpriced review, `0` executable close-ready rows, and `1` review-required non-executable display-only `SELL` row (`id=104`, SBUX). Do not auto-close that row from the display-only mark; rerun explicit review during a fresh executable quote window or close only with separate executable evidence.
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

Then run without `--no-write` when the readback changes. Use the Evidence Repair Queue table to repair exact missing quote dates/contracts before treating Tier B rows as clean. The next useful work after that is a strict Tier A fresh-match bridge: only `paper_review_candidate` rows can enter a paper shortlist, and only after a fresh executable quote-window scanner match. Treat Tier B as `watch_repair_only`, Tier C as `historical_signature_only`, and GOOGL as blocked from chase/promotion while unresolved or zero-bid issues remain.

Do not repeat the same NEM, LLY, or AAPL exact-date repair loop unless a new provider/source can produce positive bid/ask rows for the still-missing dates. The next repair attempt should either target a different high-priority row with untested exact-date rows or improve the importer/reporting path with a de-duplicated repair manifest and true no-write mode.

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
- latest Lane A classifier read: `111` missing exact leg/date items still classify as provider no-match exact contracts in the trusted local store, but a raw ThetaData probe found all `111` exact short-leg rows at `15:55` with `bid=0` and `ask>0`; the current importer/classifier drops them because it requires `bid > 0`
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

3. Use the multi-lane runner before arguing trade count. It separates portfolio-candidate lanes, intraday scouts, daily/EOD research, and blocked lane specs.

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
- zero-pick all-lanes latest applied status: `14` / `14` supervised scan lanes completed with `425` exact historical research/backfill picks appended to the forward scan/fill logs.
- zero-pick all-lanes paper-position migration report: `data/forward-tracking/all_lanes_zero_pick_position_migration_v1_latest.json`
- zero-pick all-lanes paper-position migration status: `425` historical paper positions created; after suggested-close P&L repair, `400` are closed and `25` are open as of `2026-05-31`; all `425` scan rows and fill-attempt rows are linked to tracked position IDs. Lane counts are `short_term=159`, `swing=157`, `bullish_momentum=51`, `tracked_winner_observation=35`, `tracked_winner_primary=12`, `volatility_expansion_observation=10`, and `range_breakout_observation=1`.
- historical suggested-close P&L repair report: `data/forward-tracking/historical_suggested_close_realized_pnl_repair_v1_latest.json`
- historical suggested-close P&L repair status: `98` tracked rows updated across two passes to first executable historical suggested close, final dry-run idempotence reported `369` already-correct executable suggested closes, and `61` closed backfill rows remain missing realized P&L because no trusted exact exit-leg quote was available (`54` all-lanes rows and `7` legacy single-lane rows). Do not synthesize these unresolved exits from midpoint, last trade, daily/EOD, or stale marks.
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
