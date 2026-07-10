# Regular Options Historical Profitability Filter Iteration

This generated artifact evaluates deterministic pre-entry filter families against the frozen 13-symbol historical selected candidates. Filters and thresholds are generated from train rows only, then scored on the latest simulated-forward audit months. It is read-only and cannot change scanner policy.

## Summary

- Status: `blocked_audit_window_already_consumed_for_selection`.
- Accepted filters: `0` / `162`.
- Selection permitted: `False`.
- Accepted exact rows: `2671`.
- Dedupe: `2840` rows before dedupe, `2671` rows after dedupe, `169` duplicates removed.
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
| Train | 2346 | 666 | -5.36 | 0.8614 | 0.8 | 0.74 | -150135.6 | 0.6603 | 0.54 |
| Simulated forward audit | 325 | 93 | 1.94 | 1.0524 | 0.86 | 0.71 | 22734.0 | 1.5574 | 1.01 |

## Accepted Filters

| Filter | Conditions | Train rows/cluster PF LB/USD LB | Audit rows/cluster PF LB/USD LB |
|---|---|---:|---:|
| None | none | 0 / n/a | 0 / n/a |

## Top Audit Diagnostics

| Filter | Conditions | Train IID/Cluster/USD PF LB | Audit IID/Cluster/USD PF LB | Blockers |
|---|---|---:|---:|---|
| `lane_volatility_expansion_observation` | lane_id eq volatility_expansion_observation | 0.5 / 0.41 / 0.43 | 2.26 / 1.78 / 2.55 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.53507` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 8.535068 | 1.0 / 0.87 / 0.67 | 1.82 / 1.5 / 2.17 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_9_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.53507` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY; signal_evidence.prior_20_trading_day_return_pct gte 8.535068 | 0.87 / 0.75 / 0.41 | 1.79 / 1.42 / 2.03 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_11_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.53507` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY,XOM,UNH; signal_evidence.prior_20_trading_day_return_pct gte 8.535068 | 0.82 / 0.73 / 0.41 | 1.7 / 1.31 / 2.17 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `signal_evidence_prior_20_trading_day_return_pct_gte_8.53507` | signal_evidence.prior_20_trading_day_return_pct gte 8.535068 | 0.79 / 0.71 / 0.41 | 1.53 / 1.25 / 1.94 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.67023` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 6.670229 | 1.0 / 0.89 / 0.67 | 1.46 / 1.18 / 1.75 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_9_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.67023` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY; signal_evidence.prior_20_trading_day_return_pct gte 6.670229 | 0.89 / 0.79 / 0.45 | 1.5 / 1.14 / 1.73 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_10_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_8.53507` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY,XOM; signal_evidence.prior_20_trading_day_return_pct gte 8.535068 | 0.83 / 0.74 / 0.4 | 1.39 / 1.13 / 1.76 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `train_ranked_top_11_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_6.67023` | ticker in NEM,JNJ,IWM,GOOGL,AAPL,CVX,SPY,QQQ,LLY,XOM,UNH; signal_evidence.prior_20_trading_day_return_pct gte 6.670229 | 0.81 / 0.74 / 0.45 | 1.37 / 1.11 / 1.78 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |
| `signal_evidence_prior_20_trading_day_return_pct_gte_6.67023` | signal_evidence.prior_20_trading_day_return_pct gte 6.670229 | 0.78 / 0.7 / 0.44 | 1.36 / 1.11 / 1.74 | train_bootstrap_pf_lb_not_above_1, train_usd_bootstrap_pf_lb_not_above_1, train_avg_pnl_not_positive, train_total_net_pnl_usd_not_positive |

## Blockers

- `audit_window_already_consumed_for_selection`
- `no_preregistered_train_selected_filter_passes_train_and_audit`

## Boundary

This report can nominate or reject historical pre-entry filters for the next research pass. It does not change scanners, authorize paper/live trading, import quotes, mutate evidence stores, lower proof bars, promote lanes, or make historical rows fresh forward proof.
