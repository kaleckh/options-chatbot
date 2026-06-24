# Regular Options PMCC Diagonal Replay Readiness

This report is generated from `scripts/build_regular_options_pmcc_diagonal_replay_readiness.py`. It is a read-only readiness audit for a preregistered PMCC-style defined-risk call diagonal concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, prepare or submit broker orders, allow naked or undefined-risk short calls, or promote any lane.

## Summary

- Status: `blocked_pmcc_diagonal_replay_readiness`.
- Concept: `low_mid_vix_index_pmcc_diagonal_income_v1`.
- Structure: `defined_risk_pmcc_style_call_diagonals_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Replay performed: `false`.
- Smallest next blocker-clearing slice: `missing_point_in_time_trend_or_regime_inputs`.

## Preregistration Validation

- Valid: `true`.
- Reasons: `[]`.

## Critical Prerequisites

| Prerequisite | Status | Blocker | Evidence |
| --- | --- | --- | --- |
| Valid preregistered PMCC playbook | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
| Point-in-time trend or regime inputs | `blocked` | `missing_point_in_time_trend_or_regime_inputs` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json`, `data/profitability-lab/regular-options-feature-store/latest.json` |
| Point-in-time VIX low/mid bucket | `ready` | `None` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
| Trusted OPRA/NBBO long-call and short-call quote surface | `blocked` | `missing_trusted_pmcc_diagonal_quote_surface` | `data/options-validation/options_history.db` |
| Side-aware diagonal entry, roll, exit, and expiry formulas | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
| Short-call roll, assignment, ex-dividend, and expiration handling | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
| Max-loss and collateral convention | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
| Full denominator status mapping | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
| Strict-new dedupe against the 157-row clean base stack | `ready` | `None` | `data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json` |
| Protected-holdout guard | `ready` | `None` | `data/contracts/forward-holdout-contract.json` |
| Proof-boundary labeling | `ready` | `None` | `generated_report` |

## Blockers

- `missing_point_in_time_trend_or_regime_inputs`
- `missing_trusted_pmcc_diagonal_quote_surface`

## Boundary

Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.

## Forbidden Actions

- `do_not_implement_scanner_or_playbook_logic`
- `do_not_run_pmcc_replay`
- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_mutate_evidence_stores`
- `do_not_consume_protected_holdout`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_allow_naked_or_undefined_risk_short_calls`
- `do_not_invent_point_in_time_trend_vix_or_known_at_inputs`
