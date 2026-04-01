# Proposal

## Slug

`equity-calibrated-expectancy-floor-10`

## Hypothesis

Raising the equity `min_calibrated_expectancy_pct` floor to `10` will test whether much stronger replay-backed expectancy filtering can improve pessimistic-lane results enough to justify the trade-count reduction.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `10.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-calibrated-expectancy-floor-10 --proposal docs/autoresearch/proposals/equity-calibrated-expectancy-floor-10.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the result only looks better because the sample collapses, or if the primary pessimistic broad cell remains below a useful threshold.

## Notes

- This is a tightening-only calibrated gate; do not loosen or bypass calibration behavior.
