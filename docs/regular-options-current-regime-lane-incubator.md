# Regular Options Current-Regime Lane Incubator

This report is generated from `scripts/build_regular_options_current_regime_lane_incubator.py`. It preregisters lane concepts only. It does not implement scanner logic, create trades, import quotes, mutate evidence stores, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.

## Summary

- Status: `current_regime_lane_incubator_ready_for_operator_review`.
- Accepted profitability: `false`.
- Concepts: `6`.
- Concept status counts: `{"blocked_by_event_data_missing": 1, "blocked_by_missing_exact_opra_nbbo_coverage": 1, "blocked_by_missing_replay_engine": 1, "duplicate_of_existing_candidate": 1, "read_only_research_design_ready": 1, "requires_operator_approval_for_strategy_implementation": 1}`.
- Existing profitable candidate lanes: `0`.
- Existing paper-shadow lanes: `1`.
- Forward strict rows: `0` / `30`.

## Current-Regime Snapshot

- strong broad/index momentum.
- strong QQQ/SMH technology and semiconductor leadership.
- low-to-mid VIX.
- elevated dispersion and rotation risk.
- weak energy relative to growth leadership.

## Concept Rankings

| Rank | Concept | Status | Structure | Universe | Approval Before Implementation | Approval Before Quote Import |
|---:|---|---|---|---|---|---|
| 1 | `regime_momentum_continuation_debit_spread` | `read_only_research_design_ready` | defined_risk_debit_call_spread | SPY, QQQ, IWM, SMH | `true` | `false` |
| 2 | `regime_rotation_dispersion_hedge` | `requires_operator_approval_for_strategy_implementation` | defined_risk_put_or_relative_rotation_spread | SPY, QQQ, IWM, sector_etfs | `true` | `true` |
| 3 | `regime_low_mid_vix_defined_risk_credit_income` | `blocked_by_missing_replay_engine` | defined_risk_credit_spread_or_iron_condor | SPY, QQQ, IWM | `true` | `false` |
| 3 | `regime_weak_sector_relative_weakness` | `blocked_by_missing_exact_opra_nbbo_coverage` | defined_risk_put_debit_spread_or_relative_weakness_spread | XLE, weak_recent_ticker_clusters | `true` | `true` |
| 4 | `regime_event_catalyst_defined_risk` | `blocked_by_event_data_missing` | defined_risk_event_debit_or_credit_spread | earnings_or_macro_event_symbols | `true` | `true` |
| 4 | `regime_volatility_expansion_breakout_hedge` | `duplicate_of_existing_candidate` | defined_risk_debit_spread_breakout_or_hedge | SPY, QQQ, IWM | `true` | `false` |

## Concept Details

### `regime_momentum_continuation_debit_spread`

- Status: `read_only_research_design_ready`.
- Regime thesis: Strong broad/index momentum and strong QQQ/SMH leadership can justify a preregistered debit-spread continuation concept.
- Why not already covered: Existing index/refill and SMH variants appear in prior tournaments, but no current concept is preregistered as a current-regime lane with explicit proof feasibility and approval gates.
- Existing data: SPY/QQQ/IWM are present in current proof surfaces; SMH appears in candidate history.
- Evaluation path: Use existing trusted ThetaData OPRA/NBBO exact-contract replay only after a separately approved research playbook exists.
- Expected blockers: `sample_size, winner_concentration, recent_2026_05_break, holdout_depth`.

### `regime_rotation_dispersion_hedge`

- Status: `requires_operator_approval_for_strategy_implementation`.
- Regime thesis: High dispersion and concentration risk can justify a hedged rotation concept rather than another one-way momentum chase.
- Why not already covered: Existing bearish/sector variants were mostly rejected or fragile; this would be a new preregistered hedge thesis.
- Existing data: Index underlyings are covered; sector ETF coverage must be checked concept by concept.
- Evaluation path: Read-only historical replay if candidate generation can be expressed through existing exact-contract chain-native engine.
- Expected blockers: `missing_sector_coverage, thin_hedge_samples, negative_existing_bearish_put_shapes`.

### `regime_low_mid_vix_defined_risk_credit_income`

- Status: `blocked_by_missing_replay_engine`.
- Regime thesis: Low-to-mid VIX can make defined-risk credit income attractive, but only if assignment, margin, and side-aware credit spread execution are modeled.
- Why not already covered: Current proof stack is debit-spread centric; credit-spread margin, assignment, and expiration risk are not proven as production gates.
- Existing data: Underlying option quotes may exist, but credit-spread proof semantics are not established by current reports.
- Evaluation path: Blocked until side-aware credit entry/exit, assignment/expiration, max loss, and margin conventions are implemented and tested.
- Expected blockers: `missing_credit_replay_engine, assignment_risk, margin_model_missing`.

### `regime_weak_sector_relative_weakness`

- Status: `blocked_by_missing_exact_opra_nbbo_coverage`.
- Regime thesis: Weak energy or other laggards can justify bearish or relative-weakness structures, but existing bearish/sector variants are fragile.
- Why not already covered: Existing XLE and bearish variants show no current candidates or weak/fragile proof in current reports.
- Existing data: XLE appears in prior candidate surfaces but needs exact OPRA/NBBO coverage and candidate-generation confirmation.
- Evaluation path: Blocked until exact coverage and current candidate-generation path are confirmed for the selected weak-sector universe.
- Expected blockers: `existing_bearish_shapes_negative, missing_exact_opra_nbbo_coverage, no_current_candidates`.

### `regime_event_catalyst_defined_risk`

- Status: `blocked_by_event_data_missing`.
- Regime thesis: Events can create options opportunity, but event lanes need reliable event annotation and a no-lookahead data spine.
- Why not already covered: The current monthly audit shows event-data-spine work as collecting, not proof-ready.
- Existing data: Event annotations are not a complete proof path in current readbacks.
- Evaluation path: Blocked until event data is point-in-time, no-lookahead, and joined to exact OPRA/NBBO replay.
- Expected blockers: `event_data_missing, lookahead_risk, small_sample`.

### `regime_volatility_expansion_breakout_hedge`

- Status: `duplicate_of_existing_candidate`.
- Regime thesis: Dispersion and possible volatility expansion support a breakout/hedge concept, but the repo already has a volatility expansion paper-shadow candidate.
- Why not already covered: It is already partially covered by volatility_expansion_observation; new work must not duplicate or promote that lane.
- Existing data: Existing volatility expansion artifacts are available, but forward proof remains 0/30.
- Evaluation path: Use existing paper-shadow evidence path first; do not create duplicate active lane behavior.
- Expected blockers: `duplicate_existing_candidate, fresh_forward_rows_missing, no_exact_realized_pnl_rows`.

## Boundary

- New lanes are research concepts only: `true`.
- Operator approval required before implementation: `true`.
- Historical rows are not forward proof: `true`.

## Best Next Operator Question

Approve implementation of one read-only research playbook for `regime_momentum_continuation_debit_spread`, writing only derived research artifacts, with no live validation, no auto-track, no broker, no quote import, no evidence-store mutation, no protected-holdout use, and no promotion.

## Prohibited Actions

- `do_not_create_trades_from_current_regime_lane_incubator`
- `do_not_submit_broker_orders_from_current_regime_lane_incubator`
- `do_not_enable_auto_track_from_current_regime_lane_incubator`
- `do_not_enable_live_validation_from_current_regime_lane_incubator`
- `do_not_change_scanner_policy_from_current_regime_lane_incubator`
- `do_not_change_strategy_logic_from_current_regime_lane_incubator`
- `do_not_change_stops_from_current_regime_lane_incubator`
- `do_not_change_sizing_from_current_regime_lane_incubator`
- `do_not_lower_proof_bars_from_current_regime_lane_incubator`
- `do_not_import_quotes_from_current_regime_lane_incubator`
- `do_not_mutate_evidence_databases_from_current_regime_lane_incubator`
- `do_not_consume_protected_holdout_from_current_regime_lane_incubator`
- `do_not_treat_historical_rows_as_forward_proof`
