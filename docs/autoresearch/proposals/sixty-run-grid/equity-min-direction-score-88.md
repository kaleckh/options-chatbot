# Proposal

## Slug

`equity-min-direction-score-88`

## Hypothesis

Tightening equity `entry.min_direction_score` to `88.0` may improve replay quality under the fixed matrix without changing fills, watch/block policy, or stability rules.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_direction_score"]` to `88.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-min-direction-score-88 --proposal docs/autoresearch/proposals/sixty-run-grid/equity-min-direction-score-88.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the primary `2y + pessimistic + broad` cell does not improve or if the result only looks better because it becomes too sparse to trust.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- Batch: `Equity direction floor sweep`.
