# Regular Options Flow-Extreme Ratio/Backspread Replay Readiness

This report is generated from `scripts/build_regular_options_flow_extreme_ratio_backspread_replay_readiness.py`. It is a read-only readiness audit for a preregistered defined-risk ratio/backspread concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, allow naked or undefined-risk structures, or promote any lane.

## Summary

- Status: `blocked_flow_extreme_ratio_backspread_replay_readiness`.
- Concept: `index_flow_extreme_mean_reversion_ratio_backspread_v1`.
- Structure: `defined_risk_ratio_spreads_or_backspreads_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Replay performed: `false`.
- Smallest next blocker-clearing slice: `missing_point_in_time_flow_extreme_input`.

## Preregistration Validation

- Valid: `true`.
- Reasons: `[]`.

## Critical Prerequisites

| Prerequisite | Status | Blocker | Evidence |
| --- | --- | --- | --- |
| Point-in-time flow or overextension inputs | `blocked` | `missing_point_in_time_flow_extreme_input` | `data/profitability-lab/regular-options-point-in-time-flow-extreme-input/latest.json` |
| Point-in-time VIX bucket | `ready` | `None` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
| Side-aware ratio/backspread all-leg pricing | `ready` | `None` | `data/profitability-lab/regular-options-multi-leg-side-aware-pricing-capability/latest.json` |
| Defined-risk max-loss and collateral convention | `ready` | `None` | `scripts/build_regular_options_vrp_credit_spread_structure_harness.py`, `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py` |
| Assignment, expiration, and settlement classifier | `ready` | `None` | `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py` |
| Trusted OPRA/NBBO quote surface for SPY/QQQ | `ready` | `None` | `data/profitability-lab/regular-options-feature-store/latest.json` |
| Full denominator mapping | `ready` | `None` | `data/profitability-lab/regular-options-flow-extreme-denominator-dedupe-bridge/latest.json` |
| Strict-new dedupe versus the clean base stack | `ready` | `None` | `data/profitability-lab/regular-options-flow-extreme-denominator-dedupe-bridge/latest.json` |
| Protected-holdout guard | `ready` | `None` | `data/contracts/forward-holdout-contract.json` |
| Proof-boundary labeling | `ready` | `None` | `scripts/build_regular_options_feature_store.py`, `scripts/build_regular_options_structure_specific_harness.py`, `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py`, `python-backend/proof_contract.py` |

## Blockers

- `missing_point_in_time_flow_extreme_input`

## Boundary

Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.

## Forbidden Actions

- `do_not_run_replay`
- `do_not_generate_trades`
- `do_not_import_quotes`
- `do_not_fetch_external_data`
- `do_not_mutate_options_history_db`
- `do_not_append_forward_cohort_rows`
- `do_not_overwrite_canonical_evidence_stores`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_allow_naked_short_option_structures`
- `do_not_allow_undefined_or_uncapped_ratio_backspread_structures`
- `do_not_invent_point_in_time_flow_vix_breadth_event_known_at_or_threshold_inputs`
