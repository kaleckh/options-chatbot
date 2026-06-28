# Regular Options Dispersion-Proxy Hybrid Replay Readiness

This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_replay_readiness.py`. It is a read-only readiness audit for a preregistered index-versus-constituent defined-risk hybrid pair concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.

## Summary

- Status: `dispersion_proxy_hybrid_replay_readiness_ready`.
- Concept: `index_constituent_dispersion_proxy_defined_risk_hybrid_v1`.
- Structure: `defined_risk_index_constituent_debit_credit_hybrid_pairs_only`.
- Accepted profitability: `false`.
- Historical replay performed: `false`.
- Replay performed: `false`.
- Smallest next blocker-clearing slice: `None`.

## Preregistration Validation

- Valid: `true`.
- Reasons: `[]`.

## Critical Prerequisites

| Prerequisite | Status | Blocker | Evidence |
| --- | --- | --- | --- |
| Point-in-time dispersion or concentration proxy inputs | `ready` | `None` | `data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/latest.json` |
| Point-in-time VIX bucket requirement | `ready` | `None` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
| Index/constituent pair construction and universe rules | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| Side-aware all-leg pair pricing | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| Pair max-loss and required collateral convention | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| Assignment, expiration, and settlement classifier | `ready` | `None` | `scripts/build_regular_options_term_structure_calendar_structure_harness.py`, `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py`, `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| Trusted OPRA/NBBO quote surface for index and constituent legs | `ready` | `None` | `data/profitability-lab/regular-options-feature-store/latest.json` |
| Full denominator mapping | `ready` | `None` | `scripts/build_regular_options_term_structure_calendar_structure_harness.py`, `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py`, `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| Strict-new dedupe versus the clean base stack | `ready` | `None` | `scripts/build_regular_options_term_structure_calendar_structure_harness.py`, `data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json` |
| CVX source-quality handling | `ready` | `None` | `data/contracts/regular-options-source-quality-scope-policy.json` |
| Protected-holdout guard | `ready` | `None` | `data/contracts/forward-holdout-contract.json` |
| Proof-boundary labeling | `ready` | `None` | `scripts/build_regular_options_feature_store.py`, `scripts/build_regular_options_structure_specific_harness.py`, `scripts/run_regular_options_multilane_portfolio.py`, `scripts/build_regular_options_skew_broken_wing_put_fly_structure_harness.py` |

## Blockers

- None.

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
- `do_not_allow_undefined_or_uncapped_pair_structures`
- `do_not_invent_point_in_time_dispersion_vix_or_known_at_inputs`
