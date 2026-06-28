# Regular Options Profitability Blocker Inventory

Current as of 2026-06-27 after the direct VIX source materialization, Alpaca SIP underlying daily source import, Alpaca SIP underlying minute price-surface import, Alpaca-backed dispersion/concentration proxy source import, point-in-time market-regime refresh, scoped ThetaData resume recheck, package/runtime repair, refreshed candidate-generation chain, and regenerated Oracle/operator-loop packets.

This inventory is the current whole-surface blocker map for regular-options profitability work. It is not a profitability claim and it does not authorize source-row writes, quote import, cohort-log append, protected-holdout use, live validation, auto-track, broker action, scanner/strategy/stop/sizing/proof-bar changes, or promotion.

## Cleared This Pass

- Direct VIX is no longer a current blocker. `data/profitability-lab/regular-options-direct-vix-source-import/latest.json` reports `direct_vix_source_import_materialized`; `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` reports `point_in_time_vix_bucket_ready` with `505` / `505` coverage, `coverage_pct=100.0`, and no leakage blockers.
- Underlying daily history is no longer a current source-file blocker. Alpaca SIP adjusted daily bars were staged as `point_in_time_underlying_daily_ohlcv_adjusted_v1` under `data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv`, tokened import wrote `6,422` generated source rows to `data/profitability-lab/regular-options-point-in-time-underlying-daily-history/source_rows.jsonl`, and `docs/regular-options-underlying-daily-source-import.md` reports `underlying_daily_history_source_import_materialized`.
- Opening-range underlying minute prices are no longer source-missing for the quote-surface opening-range reversal branch. `docs/regular-options-alpaca-underlying-minute-price-surface-import.md` reports `alpaca_underlying_minute_price_surface_source_import_materialized`: `141,699` Alpaca SIP generated source rows, `1,996` symbol-dates, no quote import, no `options_history.db` mutation, and no evidence-store mutation. `docs/regular-options-quote-surface-opening-range-reversal-replay.md` now consumes those rows and clears `blocked_missing_quote_surface_underlying_price`.
- Point-in-time market-regime inputs sourced from those verified underlying rows are ready. `docs/regular-options-point-in-time-market-regime-inputs.md` reports `point_in_time_market_regime_inputs_ready`, `494` / `494` requested dates covered, `24` / `24` months covered, and no missing SPY/QQQ/13-symbol breadth inputs for that artifact.
- Dispersion/concentration proxy inputs are no longer source-missing. `docs/regular-options-dispersion-concentration-proxy-source-import.md` reports `dispersion_concentration_proxy_source_import_materialized`: `6,422` Alpaca-backed generated proxy source rows, no rejects, no replay, no quote import, no evidence-store mutation, and no broker/live/autotrack/proof-bar/promotion side effects. `docs/regular-options-point-in-time-dispersion-concentration-proxy.md` now reports `point_in_time_dispersion_concentration_proxy_available` with `494` / `494` dates, `24` / `24` months, `100.0%` coverage, and no blockers. `docs/regular-options-dispersion-proxy-hybrid-replay-readiness.md` now reports `dispersion_proxy_hybrid_replay_readiness_ready` with `blockers=[]`.
- The frozen 13-symbol candidate-generation chain was refreshed after the source import. Underlying daily and market-regime blockers are no longer the leading blocker for that chain; current generated artifacts now block on missing entry underlying-price/opening surfaces, missing option-chain selection surface, missing scanner point-in-time inputs, missing lane-specific feature inputs, missing earnings calendar source, and `0/24` candidate-generation months.
- Stale VIX blocker propagation was patched in the skew broken-wing harness, momentum continuation replay, bounded momentum guidance, direct-VIX repair packet, flow source packet, and preregistered playbook selector.
- `data/profitability-lab/regular-options-direct-vix-source-repair-packet/latest.json` now reports `direct_vix_source_repair_packet_superseded_by_materialized_vix`, `blockers=[]`, and empty branch-local `vix_blockers`. The generated markdown now marks the direct-VIX source boundary as superseded rather than a current approval question.
- `data/profitability-lab/regular-options-preregistered-playbook-readiness-selector/latest.json` now reports `candidate_selected_for_research_only_implementation_approval`; its selected blocker-free preregistered branch is `dispersion_proxy_hybrid`, and strict-forward proof remains `0/30`.
- Momentum bounded replay no longer treats selector-control state as a branch replay blocker. `data/profitability-lab/regular-options-momentum-continuation-bounded-replay/latest.json` now validates that the selector inventory contains the momentum design, while current replay blockers remain the real point-in-time input, quote, P&L/stat, duplicate, and strict-row blockers.
- The direct-VIX packet and Oracle packet no longer carry stale momentum selector-control blockers in branch implications. Direct-VIX branch implications prefer `replay_gate_blockers` when present, and Oracle's direct-VIX momentum implication now carries the bounded replay's real non-VIX replay-gate blockers.
- Term-structure calendar/diagonal frozen geometry and strict-new dedupe are no longer current blockers. `data/profitability-lab/regular-options-term-structure-calendar-structure-harness/latest.json` reports `candidate_geometry_ready=true`, `strict_new_dedupe_ready=true`, and marks `missing_preregistered_calendar_diagonal_geometry` plus `missing_strict_new_dedupe` as `satisfied_by_harness`.
- Dispersion proxy hybrid pair mechanics and source inputs are no longer current blockers. `data/profitability-lab/regular-options-dispersion-proxy-hybrid-replay-readiness/latest.json` consumes the preregistered playbook's frozen design/formula/denominator contract plus the Alpaca-backed dispersion/concentration proxy source rows and reports `dispersion_proxy_hybrid_replay_readiness_ready` with `blockers=[]`.
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

- Underlying daily/opening source: adjusted daily OHLCV history is now materialized from Alpaca SIP and market-regime inputs are ready. The quote-surface opening-range reversal branch also has an Alpaca SIP underlying-minute price surface and is no longer blocked by missing `underlying_price`; it is now parked on `0/30` latest-four rows, PF lower bound, and concentration/stat economics. Other scanner-replay and lane-specific intraday underlying surfaces remain blocked until their consuming artifacts prove coverage against this or another trusted source.
- Market regime/trend/breadth/momentum: the base `point_in_time_market_regime_inputs` artifact now clears SPY momentum, QQQ momentum, and 13-symbol breadth confirmations for its requested window. Separate branch-specific trend/regime, breadth/momentum, term-structure, PMCC, downside-skew, and lane-specific feature input surfaces still fail closed until their consuming artifacts prove coverage.
- Macro-event calendar: the source repair packet is ready for a future operator import decision, but no trusted scheduled-event source CSV/source rows exist.
- Flow volume/OI: the source repair packet is ready for a future operator import decision, but no trusted SPY/QQQ daily option volume/open-interest CSV/source rows exist.
- Dispersion/concentration: Alpaca-backed point-in-time dispersion/concentration proxy source rows are materialized and ready. The branch is no longer source/input blocked; its next step is a separate bounded no-write replay decision, not a source repair.
- Skew: the current skew broken-wing branch is blocked on `missing_point_in_time_downside_skew_inputs`.

## Quote-Surface And Engine Blockers

- VRP credit spread: blocked on `missing_index_credit_spread_quote_surface`.
- Skew broken-wing put fly: blocked on `missing_index_broken_wing_quote_surface` plus downside-skew inputs.
- Term-structure calendar/diagonal: blocked on `missing_index_calendar_quote_surface` and `missing_point_in_time_term_structure_inputs`; frozen geometry and strict-new dedupe are satisfied by the current structure harness/bounded gate.
- PMCC diagonal: blocked on `missing_point_in_time_trend_or_regime_inputs` and `missing_trusted_pmcc_diagonal_quote_surface`.
- Flow-extreme ratio/backspread: blocked on `missing_point_in_time_flow_extreme_input`; denominator and strict-new dedupe are cleared.
- Dispersion proxy hybrid: readiness is now clear with `dispersion_proxy_hybrid_replay_readiness_ready` and `blockers=[]`; pair construction, all-leg pair pricing, pair max-loss/collateral convention, full denominator mapping, strict-new dedupe, VIX, and dispersion/concentration inputs are satisfied. No replay has run and no profitability claim is made.
- Post-event IV-crush iron condor: the structure-specific readiness audit now exists at `docs/regular-options-post-event-iv-crush-replay-readiness.md`. Current VIX, preregistration, formulas, denominator mapping, strict-new dedupe, and holdout boundaries are ready; remaining blockers are missing trusted macro-event calendar source/category coverage, missing IV/event-premium proxy, and insufficient full-window/latest-four/train-month quote-surface coverage for the four-leg iron-condor/butterfly surface.
- Local quote-surface-only structure inventories are exhausted under current data because selected surfaces fail the required train-month coverage despite dense latest-four quote depth.

## Provider, Approval, And Market-Window Blockers

- The scoped 59-symbol ThetaData OPRA/NBBO repair is no longer a simple provider-down blocker. ThetaTerminal is reachable through the v3 local service and the resume dry-run preflight is ready, but the non-dry resume wrapper still reports `blocked_59_symbol_import_repair` / `bulk_import_execution_not_started_by_preflight_wrapper` with `import_attempted=false`. A separate direct OPRA quote dry run returned `403 Forbidden` while the loaded terminal subscription banner showed `Options: FREE`, so the current blocker is scoped import execution/entitlement-source state rather than stale connection refusal.
- Macro-event and flow source materialization still require real trusted source files and exact tokened approval boundaries before any write. Underlying daily source materialization is complete, but it is not replay, profitability proof, quote import, evidence mutation, live validation, broker permission, or promotion.
- Bullish-pullback `layer_4_clean_exact` has profitable historical executable economics, but its honest path is future natural market-window forward capture and explicit operator approval, not immediate proof or promotion.

## Goal Completion Criteria

This blocker-removal goal is not done while any current blocker above remains unresolved or uncategorized. Completion requires:

- current artifacts and living docs agree that all locally removable stale blockers are fixed;
- remaining blockers are either removed or explicitly categorized as source-, provider-, approval-, market-window-, data-, or engine-blocked;
- relevant generator/test/doc verification passes; and
- the six-agent debate reaches consensus that the inventory is complete and the done/not-done conclusion is evidence-backed.
