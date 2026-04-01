# Proposal

## Slug

`equity-tech-72-plus-direction-75`

## Hypothesis

Combining the strongest broad-book technical floor with the cleanest direction floor may remove weak setups using only already-proven entry quality filters, without relying on a tighter expectancy floor.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_tech_score"]` to `72.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_direction_score"]` to `75.0`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-tech-72-plus-direction-75 --proposal docs/autoresearch/proposals/combo-followup/equity-tech-72-plus-direction-75.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_154734_baseline-playbook-decomposition`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the dual entry gate mostly recreates the over-pruning pattern seen in the high single-knob direction or tech sweeps.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- Compare the result both to the baseline decomposition run and to the parent single-knob winners `tech=72` and `direction=75`.
