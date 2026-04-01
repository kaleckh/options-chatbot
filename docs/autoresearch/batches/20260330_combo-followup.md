# Combo Follow-Up Batch

Generated: 2026-03-30

Common baseline: `research_runs/20260330_154734_baseline-playbook-decomposition`

## Focus

Test pairwise combinations around the strongest single-knob winners from the sixty-run grid:

- `tech = 72`
- `direction = 75`
- `min_calibrated_expectancy_pct = 7`
- `entry_momentum_pct = 0.70`

## Batch

- `equity-tech-72-plus-ev-7`
  `entry.min_tech_score = 72`, `filters.min_calibrated_expectancy_pct = 7`
- `equity-tech-72-plus-momentum-0p70`
  `entry.min_tech_score = 72`, `entry.entry_momentum_pct = 0.70`
- `equity-direction-75-plus-ev-7`
  `entry.min_direction_score = 75`, `filters.min_calibrated_expectancy_pct = 7`
- `equity-tech-72-plus-direction-75`
  `entry.min_tech_score = 72`, `entry.min_direction_score = 75`
- `equity-ev-7-plus-momentum-0p70`
  `filters.min_calibrated_expectancy_pct = 7`, `entry.entry_momentum_pct = 0.70`

## Evaluation Notes

- Keep the same fixed matrix: `1y/2y`, `n_picks=1`, `iv_adj=1.2`, `mid` and `pessimistic`
- Keep the playbooks: `broad`, `bullish_momentum`, `bearish_defensive`
- Judge mainly on `broad / 2y / pessimistic`
- Confirm `broad / 2y / mid` and `bullish_momentum / 2y / pessimistic` agree
- Reject any result that only looks better because it becomes too sparse
