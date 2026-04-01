# Proposal

## Slug

`equity-ev-7-plus-momentum-0p70`

## Hypothesis

Combining the strongest broad-safe calibrated expectancy floor with the best balanced momentum confirmation threshold may improve broad replay quality while giving the bullish-momentum slice its cleanest path toward viability.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-ev-7-plus-momentum-0p70 --proposal docs/autoresearch/proposals/combo-followup/equity-ev-7-plus-momentum-0p70.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_154734_baseline-playbook-decomposition`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the result only improves `bullish_momentum` while broad `2y + pessimistic` remains weaker than `ev=7` alone.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- Compare the result both to the baseline decomposition run and to the parent single-knob winners `ev=7` and `momentum=0.70`.
