# Proposal

## Slug

`equity-tech-floor-80`

## Hypothesis

Raising the equity `min_tech_score` floor to `80` will test whether only the strongest technical setups are worth keeping under pessimistic replay, even if it sharply reduces trade count.

## Exact Rule Change

- Rule: `STRATEGY_PROFILES["equity"]["entry"]["min_tech_score"]` to `80.0`.
- Scope: Equity profile only. Index profile unchanged.
- Replay-only or live-scan affecting later: Research override for this cycle only.

## Allowed Files

- `options_chatbot.py`

## Fixed Evaluation Bundle

- `python -m unittest tests.test_strategy_audit -v`
- `python -m unittest tests.test_options_api_e2e -v`
- `python scripts/autoresearch_cycle.py --slug equity-tech-floor-80 --proposal docs/autoresearch/proposals/equity-tech-floor-80.md --playbook broad --playbook bullish_momentum --playbook bearish_defensive --compare-to <baseline decomposition run dir>`

## Success Metrics

- `profit_factor`
- `avg_pnl_pct`
- `directional_accuracy_pct`
- `total_trades`
- `max_drawdown_pct`
- `stability.overall_status`
- `scan_policy.promotion_status`

## Rollback Condition

Reject if the result only improves via severe trade starvation, or if the primary pessimistic broad cell remains unprofitable.

## Notes

- No changes to pessimistic fills, expectancy calibration logic, or watch/block policy.
