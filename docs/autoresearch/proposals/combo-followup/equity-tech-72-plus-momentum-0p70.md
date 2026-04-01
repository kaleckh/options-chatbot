# Proposal

## Slug

`equity-tech-72-plus-momentum-0p70`

## Hypothesis

Combining the strongest broad-book technical floor with the best balanced momentum confirmation threshold may preserve the broad improvement while cleaning up mid-lane behavior better than either change alone.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_tech_score"]` to `72.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-tech-72-plus-momentum-0p70 --proposal docs/autoresearch/proposals/combo-followup/equity-tech-72-plus-momentum-0p70.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_154734_baseline-playbook-decomposition`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the broad primary lane improves only by starving the broad book or by materially weakening `2y + mid + broad` versus the `tech=72` parent.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- Compare the result both to the baseline decomposition run and to the parent single-knob winners `tech=72` and `momentum=0.70`.
