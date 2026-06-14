# Regular Options Source-Quality Scope Policy

This document describes `data/contracts/regular-options-source-quality-scope-policy.json`. The policy is a manually maintained runtime contract consumed by `scripts/build_regular_options_robust_search_evaluation.py` for historical robust-search nomination only.

## Active Rules

| Rule | Action | Scope | Reason | Evidence |
|---|---|---|---|---|
| `cvx_zero_bid_tradability_candidate_scope_v1` | `exclude_matching_trades_from_historical_candidate_scope` | `CVX` rows in `bullish_pullback_core` / `bullish_pullback_observation` | `zero_bid_tradability_floor_failure` | `docs/regular-options-cvx-executable-coverage.md` |

## Boundary

The CVX rule does not lower the `90%` executable quote floor, synthesize bids, use midpoint fills, change scanner policy, change broker or Alpaca paper behavior, or turn historical rows into fresh forward promotion proof. It only prevents a historical candidate from relying on selected CVX rows after the source-quality diagnostic found observed zero-bid tradability rather than missing provider data.
