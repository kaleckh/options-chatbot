# Regular Options Historical Profitability Filter Iteration

This generated artifact evaluates deterministic pre-entry filter families against the frozen 13-symbol historical selected candidates. Filters and thresholds are generated from train rows only, then scored on the latest simulated-forward audit months. It is read-only and cannot change scanner policy.

## Summary

- Status: `blocked_audit_window_already_consumed_for_selection`.
- Accepted filters: `0` / `162`.
- Selection permitted: `False`.
- Accepted exact rows: `2680`.
- Dedupe: `2851` rows before dedupe, `2680` rows after dedupe, `171` duplicates removed.
- Train months: `2024-06, 2024-07, 2024-08, 2024-09, 2024-10, 2024-11, 2024-12, 2025-01, 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01`.
- Audit months: `2026-02, 2026-03, 2026-04, 2026-05`.
- Source audit status: `blocked_historical_simulated_forward_audit`.
- Accepted profitability: `False`.
- Selection bias: `accepted-filter audit metrics are selection-conditioned upward-biased maxima, not unbiased out-of-sample estimates`.

## Selection Bias Disclosure

- Candidate filters searched: `162`.
- Acceptance gate includes audit-window success: `True`.
- Ranking basis: accepted filters are sorted audit-first after train-and-audit gates; top-audit diagnostics are post-hoc.
- Empirical inversion note: At least one train-best diagnostic filter failed an audit-window gate.

## Baseline

| Window | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Train | 2355 | 670 | -5.33 | 0.8623 | 0.8 | 0.74 | -148192.0 | 0.6662 | 0.54 |
| Simulated forward audit | 325 | 93 | 1.94 | 1.0524 | 0.86 | 0.71 | 22734.0 | 1.5574 | 1.01 |

## Accepted Filters

| Filter | Conditions | Train rows/cluster PF LB/USD LB | Audit rows/cluster PF LB/USD LB |
|---|---|---:|---:|
| None | none | 0 / n/a | 0 / n/a |

## Top Audit Diagnostics

| Filter | Conditions | Train IID/Cluster/USD PF LB | Audit IID/Cluster/USD PF LB | Blockers |
|---|---|---:|---:|---|
| `lane_volatility_expansion_observation` | lane_id eq volatility_expansion_observation | 0.54 / 0.42 / 0.48 | 2.26 / 1.78 / 2.55 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_9_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.552` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY; signal_evidence.prior_20_trading_day_return_pct gte 8.551999 | 0.87 / 0.76 / 0.43 | 1.84 / 1.46 / 2.12 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.552` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 8.551999 | 1.0 / 0.85 / 0.7 | 1.81 / 1.41 / 2.01 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1 |
| `train_ranked_top_11_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.552` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY,XOM,UNH; signal_evidence.prior_20_trading_day_return_pct gte 8.551999 | 0.82 / 0.74 / 0.44 | 1.67 / 1.33 / 2.13 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `signal_evidence_prior_20_trading_day_return_pct_gte_8.552` | signal_evidence.prior_20_trading_day_return_pct gte 8.551999 | 0.81 / 0.71 / 0.43 | 1.55 / 1.26 / 2.06 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 10.990605 | 1.12 / 0.91 / 0.81 | 1.47 / 1.14 / 1.85 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1 |
| `train_ranked_top_9_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.68289` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY; signal_evidence.prior_20_trading_day_return_pct gte 6.682886 | 0.88 / 0.8 / 0.46 | 1.48 / 1.14 / 1.76 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_9_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY; signal_evidence.prior_20_trading_day_return_pct gte 10.990605 | 0.84 / 0.71 / 0.31 | 1.54 / 1.13 / 1.92 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.68289` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 6.682886 | 1.0 / 0.87 / 0.7 | 1.47 / 1.13 / 1.76 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_11_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.68289` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY,XOM,UNH; signal_evidence.prior_20_trading_day_return_pct gte 6.682886 | 0.81 / 0.74 / 0.46 | 1.4 / 1.11 / 1.76 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |

## Blockers

- `audit_window_already_consumed_for_selection`
- `no_preregistered_train_selected_filter_passes_train_and_audit`

## Boundary

This report can nominate or reject historical pre-entry filters for the next research pass. It does not change scanners, authorize paper/live trading, import quotes, mutate evidence stores, lower proof bars, promote lanes, or make historical rows fresh forward proof.
