# Current-Policy Entry Filter Walk-Forward

Read-only all-regular-lanes validation for frozen entry filters. It does not change scanner guardrails.

- Generated: `2026-06-02T05:53:20Z`
- Status: `mixed_walkforward_watch_not_promoted`
- Candidate: `short_term_fill_degradation_ge_15`
- Live policy change: `False`
- Rows / months / lanes: `112` / `2026-04, 2026-05` / `short_term, swing, bullish_momentum, bullish_pullback_observation`
- Interpretation: The frozen short-term rule improves the total and latest-month current-policy realized cohort, but the calibration slice is thin or mixed, and the same fill-degradation rule is not safe as a global all-lane guardrail.

## Portfolio Read

| Read | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept <= -90% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Frozen short-term filter | `historical_pass_candidate` | 112 | 9 | 5 | 3 | 2 | +287.42% | +61.01% | +53.33% | 5 |
| Diagnostic all-lane fill >= 15% | `winner_damage_too_high` | 112 | 19 | 6 | 4 | 10 | -469.30% | +59.43% | +51.21% | 4 |

Baseline: `112` rows, avg `+53.54%`, median `+50.60%`, negatives `29`, `<= -50%` `16`, `<= -90%` `8`.

## Chronological Holdout

- Train months: `2026-04`
- Holdout month: `2026-05`

| Slice | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept <= -90% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | `winner_damage_too_high` | 70 | 3 | 1 | 0 | 1 | +84.80% | +86.07% | +75.30% | 1 |
| Latest holdout | `historical_pass_candidate` | 42 | 6 | 4 | 3 | 1 | +202.62% | +14.37% | +2.80% | 4 |

## Lane Matrix

| Lane | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `short_term` | `historical_pass_candidate` | 43 | 9 | 5 | 3 | 2 | +287.42% | +51.90% | +40.55% |
| `swing` | `no_deep_loss_reduction` | 42 | 6 | 0 | 0 | 5 | -616.90% | +46.45% | +46.22% |
| `bullish_momentum` | `winner_damage_too_high` | 22 | 4 | 1 | 1 | 3 | -139.82% | +119.85% | +140.03% |
| `bullish_pullback_observation` | `no_coverage` | 5 | 0 | 0 | 0 | 0 | -0.00% | -13.39% | +20.87% |

## Month Folds

| Month | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2026-04` | `winner_damage_too_high` | 70 | 3 | 1 | 0 | 1 | +84.80% | +86.07% | +75.30% |
| `2026-05` | `historical_pass_candidate` | 42 | 6 | 4 | 3 | 1 | +202.62% | +14.37% | +2.80% |

## Decision Read

Recommended next action: Keep the frozen short-term fill-degradation filter paper-only; expand point-in-time scanner candidate replay before promotion, and keep collecting the forward paper monitor.

Evidence boundary: this is current-policy realized-row walk-forward, not full point-in-time scanner candidate replay.

