# Proposal

## Slug

`equity-direction-floor-70`

## Hypothesis

Raising the equity `min_direction_score` floor to `70` will test whether much stricter directional confidence is necessary for replay viability under unchanged fills and policy gates.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_direction_score"]` to `70.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-direction-floor-70 --proposal docs/autoresearch/proposals/equity-direction-floor-70.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the primary pessimistic broad cell remains unprofitable or if the trade-count loss makes the result too thin to trust.

## Notes

- No changes to pessimistic fills, expectancy calibration logic, or watch/block policy.
