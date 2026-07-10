# Regular Options Historical Filtered Simulated Forward Audit

This generated artifact is the canonical filtered historical simulated-forward audit for the accepted train-selected filter from the profitability filter iteration. It recomputes metrics from selected candidates and does not search, tune, or change scanner policy.

## Summary

- Status: `blocked_historical_filtered_simulated_forward_audit`.
- Accepted historical filtered audit: `False`.
- Accepted profitability: `False`.
- Filter source mode: `frozen_contract`.
- Filter: `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906`.
- Conditions: ticker in NEM,JNJ,GOOGL,AAPL,IWM,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 10.990605.
- Dedupe: `2840` rows before dedupe, `2671` rows after dedupe, `169` duplicates removed.
- Audit confidence label: `selection_conditioned_positive`.
- Bootstrap draws: `10000`.

## Metrics

| Window | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% | Confidence Label |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Train | 232 | 92 | 12.54 | 1.4567 | 1.13 | 0.94 | 3823.8 | 1.2218 | 0.73 | `underpowered` |
| Simulated forward audit | 57 | 21 | 30.87 | 2.511 | 1.52 | 1.15 | 14599.8 | 4.2739 | 1.89 | `selection_conditioned_positive` |

## Selection And Regime Disclosure

- Raw audit cluster confidence: `confident_positive`.
- Selection-conditioned label: `selection_conditioned_positive`.
- Top two audit-month row share: `70.18`%.
- Direction mix: `{"call": 57}`.

| Audit Month | Rows |
|---|---:|
| `2026-02` | 11 |
| `2026-03` | 6 |
| `2026-04` | 24 |
| `2026-05` | 16 |

## Warnings

- `audit_rows_regime_concentrated`

## Blockers

- `train_bootstrap_pf_lb_not_above_1`
- `train_usd_bootstrap_pf_lb_not_above_1`

## Boundary

This audit accepts or blocks only the historical filtered audit readback. It does not change scanners, authorize paper/live trading, import quotes, mutate evidence stores, lower proof bars, promote lanes, or make historical rows fresh forward proof.
