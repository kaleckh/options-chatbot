# Current-Policy Entry Filter Lab

Read-only current-policy filter lab. Candidate filters are research-only unless they pass fresh paper validation.

- Generated: `2026-06-02T02:02:39Z`
- Source rows: `112`
- Repeat deep-loss tickers: `MSTR, QQQ, TSLA`

## Baseline

| Rows | Avg | Median | Negatives | <= -50% | <= -90% |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 112 | +53.54% | +50.60% | 29 | 16 | 8 |

Baseline with daily close-check `stop_80`: avg `+53.69%`, median `+50.60%`, `29` negatives, `7` rows `<= -90%`.

## Candidate Filters

| Filter | Status | Blocked | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept+80 avg | Kept+80 <= -90% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `short_term_fill_degradation_ge_15` | `paper_research_candidate` | 9 | 5 | 3 | 2 | +287.42% | +61.01% | +53.33% | +61.17% | 4 |
| `short_term_fill_degradation_ge_16` | `paper_research_candidate_recent_unproven` | 6 | 4 | 2 | 1 | +347.87% | +59.85% | +52.27% | +60.01% | 5 |
| `short_term_loss_cohort_combo_v1` | `winner_damage_too_high` | 32 | 10 | 6 | 16 | -402.67% | +69.92% | +64.53% | +69.92% | 2 |
| `short_term_fill_degradation_ge_10` | `winner_damage_too_high` | 26 | 9 | 6 | 14 | -357.92% | +65.56% | +67.37% | +65.56% | 2 |
| `short_term_fill_degradation_ge_12_5` | `winner_damage_too_high` | 18 | 7 | 5 | 9 | -204.04% | +61.62% | +52.27% | +61.62% | 3 |
| `short_term_fill15_or_quality60` | `winner_damage_too_high` | 27 | 7 | 4 | 16 | -688.08% | +62.45% | +51.21% | +62.65% | 3 |
| `short_term_fill_degradation_ge_14` | `winner_damage_too_high` | 14 | 6 | 4 | 6 | +148.79% | +62.71% | +59.08% | +62.88% | 3 |
| `fill_degradation_ge_15` | `winner_damage_too_high` | 19 | 6 | 4 | 10 | -469.30% | +59.43% | +51.21% | +59.61% | 3 |
| `repeat_deep_loss_ticker` | `winner_damage_too_high` | 31 | 7 | 3 | 20 | -875.51% | +63.22% | +51.21% | +63.22% | 5 |
| `short_term_repeat_deep_loss_ticker` | `winner_damage_too_high` | 20 | 6 | 3 | 11 | -472.36% | +60.04% | +51.18% | +60.04% | 5 |
| `quality_lt_60` | `winner_damage_too_high` | 21 | 4 | 2 | 15 | -978.41% | +55.14% | +50.03% | +55.33% | 5 |
| `short_term_quality_lt_60` | `winner_damage_too_high` | 20 | 3 | 2 | 15 | -1062.02% | +53.63% | +46.40% | +53.82% | 5 |
| `short_term_fill_degradation_ge_17_5` | `winner_damage_too_high` | 3 | 1 | 1 | 1 | +108.46% | +56.01% | +51.21% | +56.16% | 6 |
| `short_term_fill_degradation_ge_20` | `no_coverage` | 0 | 0 | 0 | 0 | -0.00% | +53.54% | +50.60% | +53.69% | 7 |

## Latest Month Kept Read

| Filter | Latest Month | Kept Rows | Kept Avg | Kept Median | Kept Negatives |
| --- | --- | ---: | ---: | ---: | ---: |
| `short_term_fill_degradation_ge_15` | `2026-05` | 36 | +14.37% | +2.80% | 18 |
| `short_term_fill_degradation_ge_16` | `2026-05` | 39 | +14.81% | -1.58% | 20 |
| `short_term_loss_cohort_combo_v1` | `2026-05` | 25 | +20.95% | +7.52% | 11 |
| `short_term_fill_degradation_ge_10` | `2026-05` | 31 | +23.46% | +7.52% | 14 |
| `short_term_fill_degradation_ge_12_5` | `2026-05` | 33 | +18.85% | +7.18% | 16 |
| `short_term_fill15_or_quality60` | `2026-05` | 30 | +7.95% | -2.05% | 16 |
| `short_term_fill_degradation_ge_14` | `2026-05` | 34 | +15.40% | +2.80% | 17 |
| `fill_degradation_ge_15` | `2026-05` | 35 | +15.16% | +7.18% | 17 |
| `repeat_deep_loss_ticker` | `2026-05` | 27 | +14.60% | -1.58% | 14 |
| `short_term_repeat_deep_loss_ticker` | `2026-05` | 32 | +12.72% | +2.80% | 16 |
| `quality_lt_60` | `2026-05` | 33 | +1.00% | -6.69% | 19 |
| `short_term_quality_lt_60` | `2026-05` | 34 | -1.49% | -9.95% | 20 |
| `short_term_fill_degradation_ge_17_5` | `2026-05` | 41 | +10.10% | -2.51% | 22 |
| `short_term_fill_degradation_ge_20` | `2026-05` | 42 | +7.49% | -4.60% | 23 |

## Decision Read

Status: `paper_research_candidates_found`

Best filter: `short_term_fill_degradation_ge_15`

Recommended next action: Paper-test the best candidate filters on fresh scans before changing promoted scanner guardrails.

## Paper Validation Plan

- Candidate: `short_term_fill_degradation_ge_15`
- Live policy change: `False`
- Minimum fresh rows: `20` current-policy rows and `5` candidate-blocked rows.
- Operator action: Tag matching paper candidates for review/monitoring; do not block live scanner output yet.

