# Proposal

## Slug

`equity-tech-floor-plus-5`

## Hypothesis

Raising the equity `min_tech_score` floor from `55` to `60` will remove weaker technical setups and improve replay quality in the pessimistic lane without worsening stability or scan-policy outcomes.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_tech_score"]` from `55.0` to `60.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-tech-floor-plus-5 --proposal docs/autoresearch/proposals/equity-tech-floor-plus-5.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if `2y + pessimistic + broad` does not improve, if trade count collapses into a sparse artifact, or if stability / policy status worsens versus baseline.

## Notes

- Do not change pessimistic fills, expectancy calibration, or watch/block policy.
- Compare against the common baseline decomposition run using the same three playbooks so the matrix cells match exactly.
