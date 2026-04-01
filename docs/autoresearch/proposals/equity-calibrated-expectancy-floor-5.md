# Proposal

## Slug

`equity-calibrated-expectancy-floor-5`

## Hypothesis

Raising the equity `min_calibrated_expectancy_pct` floor to `5` will remove the weakest positive-expectancy cohorts and improve pessimistic-lane replay quality without changing fill assumptions or watch/block policy.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `5.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-calibrated-expectancy-floor-5 --proposal docs/autoresearch/proposals/equity-calibrated-expectancy-floor-5.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the improvement comes mainly from trade starvation or if the primary pessimistic broad cell remains clearly unprofitable.

## Notes

- This is a tightening-only calibrated gate; do not loosen or bypass calibration behavior.
