# Proposal

## Slug

`ev7-momentum070-control-refresh`

## Hypothesis

Re-run the current best entry cohort on the current code and date so the exit-only variants can be judged against a same-day control instead of yesterday's champion snapshot.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["filters"]["min_calibrated_expectancy_pct"]` to `7.0`
- Rule: `STRATEGY_PROFILES["equity"]["entry"]["entry_momentum_pct"]` to `0.70`
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `scripts/run_research_variant_cycle.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/run_research_variant_cycle.py --variant-config docs/autoresearch/variants/exit-followup/ev7-momentum070-control-refresh.json -- --slug ev7-momentum070-control-refresh --proposal docs/autoresearch/proposals/exit-followup/ev7-momentum070-control-refresh.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive`

## Success Metrics

- Produce a same-day control artifact for honest comparison only.

## Rollback Condition

Reject as a promotion candidate by default. This run exists to anchor comparison, not to propose a new live change.

## Notes

- No changes to pessimistic fills, expectancy calibration internals, or watch/block policy.
- This is a diagnostic control run for the exit follow-up batch.
