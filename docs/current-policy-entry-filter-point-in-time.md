# Current-Policy Entry Filter Point-In-Time Replay

Read-only scanner candidate replay for the short-term fill-degradation champion. It does not change live guardrails.

- Generated: `2026-06-04T05:26:13Z`
- Status: `paper_only_collecting`
- Filter: `short_term_fill_degradation_ge_15`
- Live policy change: `False`
- Promotion blockers: `insufficient_exact_priced_candidate_rows, insufficient_champion_matched_blocked_rows, matched_rows_not_net_harmful_or_deep_loss, unpriced_or_non_executable_rows_present`

## Candidate Read

| Slice | Rows | Exact priced | Avg | Median | Negatives | <= -50% | <= -90% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 5 | 0 | n/a | n/a | 0 | 0 | 0 |
| Matched | 0 | 0 | n/a | n/a | 0 | 0 | 0 |
| Kept | 5 | 0 | n/a | n/a | 0 | 0 | 0 |

## Effect Read

- Avoided losses: `0`
- Avoided deep losses: `0`
- Avoided near-total losses: `0`
- Lost winners: `0`
- Blocked sum delta if skipped: `-0.00%`

## Coverage

- Zero-pick days: `1`
- Unpriced or non-executable rows: `5`
- Unpriced reasons: `{"missing_realized_pnl": 5}`

Recommended next action: Keep the champion filter paper-only; continue fresh monitor collection and only revisit promotion after this replay has enough exact priced rows with no winner damage.

