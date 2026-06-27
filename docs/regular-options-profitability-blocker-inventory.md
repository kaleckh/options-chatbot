# Regular Options Profitability Blocker Inventory

Current as of 2026-06-26 after the direct VIX source materialization, refreshed momentum/skew/source/selector artifacts, term-structure harness correction, and regenerated Oracle loop packet.

This inventory is the current whole-surface blocker map for regular-options profitability work. It is not a profitability claim and it does not authorize source-row writes, quote import, cohort-log append, protected-holdout use, live validation, auto-track, broker action, scanner/strategy/stop/sizing/proof-bar changes, or promotion.

## Cleared This Pass

- Direct VIX is no longer a current blocker. `data/profitability-lab/regular-options-direct-vix-source-import/latest.json` reports `direct_vix_source_import_materialized`; `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` reports `point_in_time_vix_bucket_ready` with `505` / `505` coverage, `coverage_pct=100.0`, and no leakage blockers.
- Stale VIX blocker propagation was patched in the skew broken-wing harness, momentum continuation replay, bounded momentum guidance, direct-VIX repair packet, flow source packet, and preregistered playbook selector.
- `data/profitability-lab/regular-options-direct-vix-source-repair-packet/latest.json` now reports `direct_vix_source_repair_packet_superseded_by_materialized_vix`, `blockers=[]`, empty branch-local `vix_blockers`, and refreshed dispersion branch implications with only `missing_dispersion_or_concentration_proxy_inputs` remaining. The generated markdown now marks the direct-VIX source boundary as superseded rather than a current approval question.
- `data/profitability-lab/regular-options-preregistered-playbook-readiness-selector/latest.json` now consumes the momentum bounded replay artifact and reports `no_research_implementation_candidate_ready_without_blocker` instead of incorrectly treating momentum as blocker-free.
- Momentum bounded replay no longer treats selector-control state as a branch replay blocker. `data/profitability-lab/regular-options-momentum-continuation-bounded-replay/latest.json` now validates that the selector inventory contains the momentum design, while current replay blockers remain the real point-in-time input, quote, P&L/stat, duplicate, and strict-row blockers.
- The direct-VIX packet and Oracle packet no longer carry stale momentum selector-control blockers in branch implications. Direct-VIX branch implications prefer `replay_gate_blockers` when present, and Oracle's direct-VIX momentum implication now carries the bounded replay's real non-VIX replay-gate blockers.
- Term-structure calendar/diagonal frozen geometry and strict-new dedupe are no longer current blockers. `data/profitability-lab/regular-options-term-structure-calendar-structure-harness/latest.json` reports `candidate_geometry_ready=true`, `strict_new_dedupe_ready=true`, and marks `missing_preregistered_calendar_diagonal_geometry` plus `missing_strict_new_dedupe` as `satisfied_by_harness`.
- Dispersion proxy hybrid pair mechanics are no longer current blockers. `data/profitability-lab/regular-options-dispersion-proxy-hybrid-replay-readiness/latest.json` consumes the preregistered playbook's frozen design/formula/denominator contract and now blocks only on `missing_dispersion_or_concentration_proxy_inputs`.
- The Oracle loop packet now uses the current bounded gates for VRP and term-structure ranking. `data/forward-tracking/options_oracle_profit_loop_packet_latest.json` reports VRP blocked only on `missing_index_credit_spread_quote_surface` and term structure blocked only on `missing_index_calendar_quote_surface` plus `missing_point_in_time_term_structure_inputs`; older replay-readiness engine blockers are no longer current packet blocker arrays.

## Forward Proof Blocker

- Strict completed forward proof remains `0/30`.
- The real Phase 2 capture readback is `no_phase2_natural_selections_no_append`: `0` staged rows, no candidate JSONL, no validation/append, and no real cohort log.
- Historical, replay, simulated-forward, dashboard, research/backfill, midpoint, stale, EOD, last, model, manual, synthetic, lookahead, diagnostic, or repaired historical rows remain hypothesis evidence only. They do not satisfy accepted forward profitability.

## Candidate-Generation And Historical Simulated-Forward Blockers

- The frozen 13-symbol path still proves `0/24` candidate-generation months and `0` selected rows.
- The historical simulated-forward audit remains blocked by missing daily candidate-generation diagnostics, missing proven selected/no-pick rows, `0` train months, `0` audit months, and `0/30` audit exact trades.
- Quote-depth coverage alone is not candidate-generation proof.

## Point-In-Time Source/Input Blockers

- Underlying daily/opening source: no trusted full-window `point_in_time_underlying_daily_ohlcv_adjusted_v1` CSV is staged under `data/import-staging/underlying_daily`; local `market_data.db:daily_history`, fixtures, inferred known-at rows, and historical reconstruction remain insufficient.
- Market regime/trend/breadth/momentum: no verified point-in-time source rows currently clear the required trend, regime, breadth, SPY momentum, and QQQ momentum confirmations for the affected branches.
- Macro-event calendar: the source repair packet is ready for a future operator import decision, but no trusted scheduled-event source CSV/source rows exist.
- Flow volume/OI: the source repair packet is ready for a future operator import decision, but no trusted SPY/QQQ daily option volume/open-interest CSV/source rows exist.
- Dispersion/concentration: no trusted point-in-time dispersion/concentration proxy source rows exist, and the feature store lacks the required return fields.
- Skew: the current skew broken-wing branch is blocked on `missing_point_in_time_downside_skew_inputs`.

## Quote-Surface And Engine Blockers

- VRP credit spread: blocked on `missing_index_credit_spread_quote_surface`.
- Skew broken-wing put fly: blocked on `missing_index_broken_wing_quote_surface` plus downside-skew inputs.
- Term-structure calendar/diagonal: blocked on `missing_index_calendar_quote_surface` and `missing_point_in_time_term_structure_inputs`; frozen geometry and strict-new dedupe are satisfied by the current structure harness/bounded gate.
- PMCC diagonal: blocked on `missing_point_in_time_trend_or_regime_inputs` and `missing_trusted_pmcc_diagonal_quote_surface`.
- Flow-extreme ratio/backspread: blocked on `missing_point_in_time_flow_extreme_input`; denominator and strict-new dedupe are cleared.
- Dispersion proxy hybrid: blocked on `missing_dispersion_or_concentration_proxy_inputs`; pair construction, all-leg pair pricing, pair max-loss/collateral convention, full denominator mapping, and strict-new dedupe are satisfied by the current readiness artifact.
- Post-event IV-crush iron condor: the structure-specific readiness audit now exists at `docs/regular-options-post-event-iv-crush-replay-readiness.md`. Current VIX, preregistration, formulas, denominator mapping, strict-new dedupe, and holdout boundaries are ready; remaining blockers are missing trusted macro-event calendar source/category coverage, missing IV/event-premium proxy, and insufficient full-window/latest-four/train-month quote-surface coverage for the four-leg iron-condor/butterfly surface.
- Local quote-surface-only structure inventories are exhausted under current data because selected surfaces fail the required train-month coverage despite dense latest-four quote depth.

## Provider, Approval, And Market-Window Blockers

- The scoped 59-symbol ThetaData OPRA/NBBO repair remains parked on provider/source availability until the current artifact no longer reports `blocked_thetaterminal_source_unavailable_retry`.
- Macro-event, flow, and underlying source materialization require real trusted source files and exact tokened approval boundaries before any write.
- Bullish-pullback `layer_4_clean_exact` has profitable historical executable economics, but its honest path is future natural market-window forward capture and explicit operator approval, not immediate proof or promotion.

## Goal Completion Criteria

This blocker-removal goal is not done while any current blocker above remains unresolved or uncategorized. Completion requires:

- current artifacts and living docs agree that all locally removable stale blockers are fixed;
- remaining blockers are either removed or explicitly categorized as source-, provider-, approval-, market-window-, data-, or engine-blocked;
- relevant generator/test/doc verification passes; and
- the six-agent debate reaches consensus that the inventory is complete and the done/not-done conclusion is evidence-backed.
