# Proposal

## Slug

`ev7-momentum070-exit-target80`

## Hypothesis

The current `100%` profit target may be letting too many near-profitable momentum trades round-trip. Lowering the target to `80%` may harvest gains earlier without loosening the entry cohort.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Rule: `STRATEGY_PROFILES["equity"]["risk"]["profit_target_pct"]` to `80.0`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `wfo_optimizer.py`
- `scripts/run_research_variant_cycle.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/run_research_variant_cycle.py --variant-config docs/autoresearch/variants/exit-followup/ev7-momentum070-exit-target80.json -- --slug ev7-momentum070-exit-target80 --proposal docs/autoresearch/proposals/exit-followup/ev7-momentum070-exit-target80.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_233407_equity-ev-7-plus-momentum-0p70`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the result improves only by starving trades or if `2y + mid + broad` weakens while the primary lane improvement is negligible.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- This is an exit-only experiment layered on top of the current best entry cohort.
