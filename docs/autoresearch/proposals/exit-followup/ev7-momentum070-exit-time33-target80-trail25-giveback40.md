# Proposal

## Slug

`ev7-momentum070-exit-time33-target80-trail25-giveback40`

## Hypothesis

The current best entry cohort may need a fully faster de-risking profile, not just a single exit tweak. Combining an earlier time exit, a smaller target, and earlier trailing protection may keep the cohort from giving back too many open profits.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Rule: `STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"]` to `33.0`
- Rule: `STRATEGY_PROFILES["equity"]["risk"]["profit_target_pct"]` to `80.0`
- Rule: `STRATEGY_PROFILES["equity"]["early_exit"]["trailing_profit_pct"]` to `25.0`
- Rule: `STRATEGY_PROFILES["equity"]["early_exit"]["trailing_giveback_pct"]` to `40.0`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `wfo_optimizer.py`
- `scripts/run_research_variant_cycle.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/run_research_variant_cycle.py --variant-config docs/autoresearch/variants/exit-followup/ev7-momentum070-exit-time33-target80-trail25-giveback40.json -- --slug ev7-momentum070-exit-time33-target80-trail25-giveback40 --proposal docs/autoresearch/proposals/exit-followup/ev7-momentum070-exit-time33-target80-trail25-giveback40.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to research_runs/20260330_233407_equity-ev-7-plus-momentum-0p70`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the combined faster-exit profile worsens the primary broad lane or if the apparent improvement comes only from over-pruning rather than better realized trade outcomes.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- This is the most aggressive exit-only branch in the batch and should be judged against the single-change exit variants, not just the original combo baseline.
