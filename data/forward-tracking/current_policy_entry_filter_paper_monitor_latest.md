# Current-Policy Entry Filter Paper Monitor

Read-only forward monitor for the entry-filter champion. It does not change live scanner behavior.

- Generated: `2026-06-04T21:43:39Z`
- Since date: `2026-06-02`
- Champion: `short_term_fill_degradation_ge_15`
- Gate status: `collecting`
- Gate failures: `insufficient_fresh_rows, insufficient_candidate_blocked_rows, blocked_rows_not_net_negative_or_deep_loss`

## Fresh Cohort

| Rows | Open | Closed | Priced | Avg | Median | Negatives | <= -50% | <= -90% |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | n/a | n/a | 0 | 0 | 0 |

## Threshold Shadows

| Filter | Matched | Matched Closed | Matched Avg | Deep Losses | Near Total | Winners Lost | Kept Avg | Kept Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `short_term_fill_degradation_ge_10` | 0 | 0 | n/a | 0 | 0 | 0 | n/a | n/a |
| `short_term_fill_degradation_ge_12_5` | 0 | 0 | n/a | 0 | 0 | 0 | n/a | n/a |
| `short_term_fill_degradation_ge_15` | 0 | 0 | n/a | 0 | 0 | 0 | n/a | n/a |
| `short_term_fill_degradation_ge_17_5` | 0 | 0 | n/a | 0 | 0 | 0 | n/a | n/a |
| `short_term_fill_degradation_ge_20` | 0 | 0 | n/a | 0 | 0 | 0 | n/a | n/a |

## Decision Read

Champion matched `0` fresh rows and `0` closed rows.

Keep this monitor in collection mode until the minimum fresh-row and candidate-blocked sample gates are met.

