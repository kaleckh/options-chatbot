# Proposal

## Slug

`ev7-momentum070-exit-time33`

## Hypothesis

The current best entry cohort may still be giving back too much edge to time decay. Shortening the time exit from `50%` of original DTE to `33%` may improve replay quality by cutting stalled momentum trades earlier.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Rule: `STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"]` to `33.0`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `wfo_optimizer.py`
- `scripts/run_research_variant_cycle.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/run_research_variant_cycle.py --variant-config docs/autoresearch/variants/exit-followup/ev7-momentum070-exit-time33.json -- --slug ev7-momentum070-exit-time33 --proposal docs/autoresearch/proposals/exit-followup/ev7-momentum070-exit-time33.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_233407_equity-ev-7-plus-momentum-0p70`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the primary `2y + pessimistic + broad` cell does not improve or if `bullish_momentum / 2y / pessimistic` regresses materially.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- This is an exit-only experiment layered on top of the current best entry cohort.
