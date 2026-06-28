# Regular Options Term Structure Calendar Replay Readiness

This report is generated from `scripts/build_regular_options_term_structure_calendar_replay_readiness.py`. It is a read-only readiness audit. It does not implement a scanner or playbook, run historical replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `blocked_term_structure_calendar_replay_readiness`.
- Concept: `low_mid_vix_index_calendar_term_structure_dislocation_v1`.
- Structure: `defined_risk_calendar_or_diagonal_debit_spreads_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Lane implementation performed: `false`.

## Preregistration Validation

- Valid: `true`.
- Reasons: `[]`.

## Critical Prerequisites

| Prerequisite | Status | Blocker | Evidence |
| --- | --- | --- | --- |
| Calendar/diagonal side-aware bid/ask entry pricing | `partial` | `missing_calendar_diagonal_side_aware_pricing_engine` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/run_regular_options_multilane_portfolio.py`, `scripts/run_side_aware_zero_bid_replay.py`, `python-backend/positions_service.py` |
| Calendar/diagonal side-aware exit, expiry, or roll pricing | `partial` | `missing_calendar_diagonal_exit_or_expiry_engine` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/run_side_aware_zero_bid_replay.py`, `python-backend/positions_service.py`, `python-backend/positions_repository.py` |
| Full denominator status mapping | `missing` | `missing_full_denominator_status_mapping` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/run_side_aware_zero_bid_replay.py` |
| Front-leg assignment and expiration classification | `partial` | `missing_front_leg_assignment_expiration_classifier` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/run_side_aware_zero_bid_replay.py` |
| Roll or front-leg expiry policy | `partial` | `missing_roll_or_expiry_policy` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/run_regular_options_multilane_portfolio.py`, `scripts/run_side_aware_zero_bid_replay.py`, `python-backend/positions_service.py` |
| Contract multiplier, fees, slippage, and net USD P&L | `ready` | `None` | `scripts/build_regular_options_structure_specific_harness.py`, `scripts/run_side_aware_zero_bid_replay.py`, `python-backend/positions_service.py`, `python-backend/positions_repository.py` |
| Point-in-time VIX and term-structure inputs | `partial` | `missing_point_in_time_term_structure_inputs` | `scripts/build_regular_options_feature_store.py`, `docs/regular-options-feature-store.md` |
| Trusted OPRA/NBBO multi-expiry quote surface for SPY/QQQ | `partial` | `missing_index_calendar_quote_surface` | `scripts/run_alpaca_options_strategy_lab.py`, `scripts/build_regular_options_structure_specific_harness.py`, `scripts/run_regular_options_multilane_portfolio.py`, `scripts/build_regular_options_feature_store.py` |
| Protected-holdout guard | `ready` | `None` | `data/contracts/forward-cohort-preregistration.json`, `data/contracts/forward-holdout-contract.json` |
| Strict-new dedupe versus the clean base stack | `missing` | `missing_strict_new_dedupe` | - |
| Proof-boundary labeling | `ready` | `None` | `scripts/build_regular_options_structure_specific_harness.py`, `scripts/run_regular_options_multilane_portfolio.py`, `scripts/build_regular_options_feature_store.py`, `python-backend/positions_service.py` |

## Blockers

- `missing_calendar_diagonal_side_aware_pricing_engine`
- `missing_calendar_diagonal_exit_or_expiry_engine`
- `missing_full_denominator_status_mapping`
- `missing_front_leg_assignment_expiration_classifier`
- `missing_roll_or_expiry_policy`
- `missing_point_in_time_term_structure_inputs`
- `missing_index_calendar_quote_surface`
- `missing_strict_new_dedupe`

## Research-Only Task Boundary

A later bounded research-only implementation/replay harness must stay inside the current non-live, non-broker research posture and must still forbid live, broker, quote import, evidence mutation, protected-holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.

## Forbidden Actions

- `do_not_implement_scanner_or_playbook_logic`
- `do_not_run_historical_calendar_diagonal_replay`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
