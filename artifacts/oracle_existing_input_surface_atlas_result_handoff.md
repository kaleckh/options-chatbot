# Same-Session Oracle Handoff: Existing Input Surface Atlas Result

We are continuing the same regular-options profitability goal loop in the existing ChatGPT session.

User standing instruction: continue until we either reach at least 30 profitable strict latest-four/forward-style completed rows or a real stop_exception is earned. Treat research-only implementation/replay/artifact approvals as YES. Still forbidden without explicit approval: broker/live/order prep, live validation, auto-track, production scanner/strategy/stop/sizing/proof-bar changes, quote import, evidence DB/store mutation, protected holdout consumption, and promotion.

## Completed Codex Task

Implemented exactly the selected task: `existing_repository_point_in_time_input_surface_atlas_v1`.

Files added/updated:
- `scripts/build_regular_options_existing_input_surface_atlas.py`
- `tests/test_regular_options_existing_input_surface_atlas.py`
- `package.json` script `options:research:existing-input-surface-atlas`
- `docs/regular-options-existing-input-surface-atlas.md`
- `data/profitability-lab/regular-options-existing-input-surface-atlas/latest.json`
- `data/profitability-lab/regular-options-existing-input-surface-atlas/latest.md`
- `data/profitability-lab/regular-options-existing-input-surface-atlas/source_surface_candidates.jsonl`
- memory docs: `docs/WORKLOG.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`

## Verification Commands

Passed:
- `uv run --locked python -m py_compile scripts/build_regular_options_existing_input_surface_atlas.py tests/test_regular_options_existing_input_surface_atlas.py`
- `uv run --locked python -m unittest tests.test_regular_options_existing_input_surface_atlas -v`
- `npm run options:research:existing-input-surface-atlas -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --latest-four-months 2026-02,2026-03,2026-04,2026-05 --no-write --json`
- `npm run options:research:existing-input-surface-atlas -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --latest-four-months 2026-02,2026-03,2026-04,2026-05`
- `npm run verify:docs`
- `git diff --check` exited 0 with CRLF conversion warnings only.

## Real Result

Latest artifact:
- `docs/regular-options-existing-input-surface-atlas.md`
- `data/profitability-lab/regular-options-existing-input-surface-atlas/latest.json`
- `data/profitability-lab/regular-options-existing-input-surface-atlas/source_surface_candidates.jsonl`

Key fields:
- `status`: `research_only_input_surfaces_exhausted_under_current_repository`
- `atlas_id`: `existing_repository_point_in_time_input_surface_atlas_v1`
- `read_only_db_open`: `true`
- `accepted_profitability`: `false`
- `current_forward_or_latest_four_strict_rows`: `0`
- `target_latest_four_strict_rows`: `30`
- `ready_source_surface_count`: `0`
- `next_research_branch`: `null`
- `no_research_only_input_surface_upgrade_remaining`: `true`
- `stop_exception_candidate`: `true`
- `quotes_imported`: `false`
- `evidence_stores_mutated`: `false`
- `protected_holdout_consumed`: `false`
- `scanner_policy_changed`: `false`
- `strategy_logic_changed`: `false`
- `stops_changed`: `false`
- `sizing_changed`: `false`
- `proof_bars_changed`: `false`
- `live_validation_enabled`: `false`
- `auto_track_enabled`: `false`
- `broker_order_allowed`: `false`
- `promotion_ready`: `false`
- `p_l_replay_performed`: `false`
- `realized_pnl_used_for_ranking`: `false`

Candidate surface findings:
- `underlying_or_opening_bucket`: `underlying_price` exists only for 3 dates in 2026-05; train months 0, latest-four months 1, date coverage 0.58%.
- `trend_or_regime`: only the same undercovered `underlying_price` proxy exists; train months 0, latest-four months 1, date coverage 0.58%.
- `direct_vix_or_volatility_regime`: source missing / threshold missing; coverage 0.
- `option_iv_proxy_volatility_regime`: `iv` exists only for 3 dates in 2026-05; proxy cannot clear direct VIX blocker.
- `flow_or_liquidity_pressure`: missing; plain bid/ask availability remains not flow input.
- `volume_open_interest`: volume/OI exists only for 3 dates in 2026-05; train months 0, latest-four months 1.
- `macro_event_calendar`: missing required source/categories.
- `earnings_event_calendar`: missing.
- `term_structure_or_skew`: quote-derived bid/ask/expiry/strike/option_type surface has 20 train months, 4 latest-four months, 95.0% date coverage, 96.47% latest-four coverage, and 26,579,741 usable rows, but it is blocked as `already_parked_quote_surface_only`.
- `dispersion_or_concentration_proxy`: missing source/return fields.
- `candidate_generation_diagnostics`: missing daily diagnostics/known-at safe source.
- `fresh_forward_collection_readiness`: approval-required append, not allowed in this no-mutation slice.

Interpretation:
- This task did not make the system profitable.
- It did make a stronger stop-exception candidate under current repository data: no existing read-only input/source surface clears the gates, and the only full-coverage source is the already-parked quote surface.
- The remaining gates listed by the artifact are approval-required: fresh forward cohort append during valid market window, scoped source repair/replay, quote import/new data surface, protected holdout decision, or promotion review.

## Do Not Repeat

Do not select:
- fixed 13-symbol quote structure matrix
- all-local quote-minute structure capability atlas
- opening-range quote-surface replay
- synthetic-forward source surface
- PMCC/flow/macro/VIX/dispersion source-readiness repeats without a changed source artifact
- dashboard-only visibility
- raw overlap aggregation
- historical rows as forward proof
- any P&L replay over the same already-parked quote surface unless you identify a new valid point-in-time input/source surface or a user-approved data/source mutation gate.

## Required GPT-5.5 Pro Response

Return JSON only. Decide whether this result earns `stop_exception` under the current approvals, or whether a significant research-only upgrade remains that does not require quote import, evidence mutation, protected holdout, forward append, live validation, broker action, production scanner/strategy/proof-bar changes, or promotion.

If `verdict=continue`, provide exactly one next Codex task with:
- `objective`
- exact scope
- implementation steps
- allowed files/artifacts
- commands to run
- acceptance criteria
- failure criteria
- forbidden actions
- stop condition after task

If `verdict=stop_exception`, be explicit that this is not profitability and that the target remains `0/30`; list the smallest approval-required next gate that could still move toward the user target.
