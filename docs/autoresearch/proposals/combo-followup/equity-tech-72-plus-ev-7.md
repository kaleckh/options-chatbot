# Proposal

## Slug

`equity-tech-72-plus-ev-7`

## Hypothesis

Combining the strongest broad-book technical floor found so far with the strongest broad-safe calibrated expectancy floor may improve pessimistic replay quality more cleanly than either change alone.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_tech_score"]` to `72.0`
- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-tech-72-plus-ev-7 --proposal docs/autoresearch/proposals/combo-followup/equity-tech-72-plus-ev-7.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_154734_baseline-playbook-decomposition`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the primary `2y + pessimistic + broad` cell does not improve versus baseline, or if trade count falls enough to make the result less trustworthy than the parent single-knob winners.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- Compare the result both to the baseline decomposition run and to the parent single-knob winners `tech=72` and `ev=7`.
