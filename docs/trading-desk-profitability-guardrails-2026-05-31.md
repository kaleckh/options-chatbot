# Trading Desk Profitability Guardrails - 2026-05-31

This is an all-row replay over the regular supervised Trading Desk repair lanes. It measures candidate entry guardrails against both avoided losers and lost winners before any scanner rule is promoted.

## Baseline

| Rows | Priced | Negative | Positive/Flat | Unknown | Avg P&L | Median P&L |
|---:|---:|---:|---:|---:|---:|---:|
| 429 | 383 | 193 | 190 | 46 | 5.21% | -1.58% |

## Probe Results

| Probe | Promote | Blocked | Neg Avoided | Winners Lost | Unknown | Kept Avg | Kept Median |
|---|---|---:|---:|---:|---:|---:|---:|
| `debit_gt_45_width` | yes | 76 | 45 | 26 | 5 | 12.3% | 6.53% |
| `fill_degradation_ge_20` | yes | 140 | 78 | 43 | 19 | 19.31% | 12.02% |
| `worst_leg_spread_ge_20` | yes | 137 | 71 | 48 | 18 | 16.78% | 8.93% |
| `momentum_chase` | no | 129 | 56 | 63 | 10 | -1.38% | -4.81% |
| `lane_ticker_quarantine` | yes | 172 | 101 | 62 | 9 | 19.03% | 11.84% |
| `bullish_pullback_not_keep_bucket` | yes | 50 | 23 | 19 | 8 | 7.68% | 1.09% |
| `bullish_pullback_ret5_lt_minus_2` | yes | 6 | 6 | 0 | 0 | 6.24% | 1.38% |

## Promoted Combined Effect

Promoted guardrails: `debit_gt_45_width, fill_degradation_ge_20, worst_leg_spread_ge_20, lane_ticker_quarantine, bullish_pullback_not_keep_bucket, bullish_pullback_ret5_lt_minus_2`

| Set | Rows | Priced | Negative | Positive/Flat | Unknown | Avg P&L | Median P&L |
|---|---:|---:|---:|---:|---:|---:|---:|
| Blocked | 299 | 267 | 164 | 103 | 32 | -15.59% | -25.08% |
| Kept | 130 | 116 | 29 | 87 | 14 | 53.08% | 46.4% |

## Implementation Read

- Promote high debit, fill degradation, wide-leg, lane/ticker quarantine, Bullish Pullback keep-bucket, and Bullish Pullback ret5 floor guardrails.
- Reject momentum-chase blocking: in this all-row replay, the blocked set had positive average P&L, so the rule would remove too many winners.
- These guardrails block or research-tag future picks; they do not hide historical rows and do not change the `90%` stop policy.
