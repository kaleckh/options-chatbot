# Proposal

## Slug

`baseline-playbook-decomposition`

## Hypothesis

The current `broad` replay may be weak because one existing playbook slice is dragging down the aggregate. Running the fixed matrix for `broad`, `bullish_momentum`, and `bearish_defensive` before changing any thresholds should show whether the weakness is concentrated or universal.

## Exact Rule Change

- Rule: No strategy mutation. Run the existing replay playbooks side by side.
- Scope: Replay-only evaluation.
- Replay-only or live-scan affecting later: Replay-only.

## Allowed Files

- `wfo_optimizer.py`
- `scripts/autoresearch_cycle.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug baseline-playbook-decomposition --proposal docs/autoresearch/proposals/baseline-playbook-decomposition.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

If all three existing slices remain weak or too sparse under `2y + pessimistic`, stop threshold tuning and treat the next mutation batch as low-priority research only.

## Notes

- Keep the matrix fixed at `1y/2y`, `n_picks=1`, `iv_adj=1.2`, `mid/pessimistic`.
- Use this run as the baseline comparison target for the next threshold experiments so matrix cells stay identical.
