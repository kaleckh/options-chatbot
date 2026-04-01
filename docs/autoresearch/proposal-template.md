# Proposal Template

## Slug

`replace-with-short-slug`

## Hypothesis

Describe one narrow deterministic change and the expected outcome.

State the evidence that motivated this proposal:

- parent run or artifact to beat
- expected mechanism
- minimum sample floor that would make the result meaningful

## Exact Rule Change

- Rule:
- Scope:
- Replay-only or live-scan affecting later:

## Allowed Files

- `path/to/file.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug <slug> --proposal <this file> --mode search`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

State the exact condition that makes the idea a `reject`.

## Notes

Add any context or constraints that should be preserved during implementation.

If this idea belongs to a batch, note:

- control run
- batch manifest
- allowed truth lane
- whether this is a challenger or control
