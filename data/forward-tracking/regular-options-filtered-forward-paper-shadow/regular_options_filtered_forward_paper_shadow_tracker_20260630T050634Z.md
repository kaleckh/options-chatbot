# Regular Options Filtered Forward Paper-Shadow Tracker

This generated readback tracks prospective scan-pick rows that match the frozen historical filtered candidate policy. It is dashboard/reporting evidence, not broker execution.

## Summary

- Status: `filtered_forward_paper_shadow_tracking_active`.
- Tracking policy: `historical_filtered_candidate_v1`.
- Tracking start date: `2026-06-30`.
- Filter: `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906`.
- Conditions: ticker in NEM,JNJ,GOOGL,AAPL,IWM,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 10.990605.
- Source scan rows: `550`.
- Evaluated scan rows: `0`.
- Matched forward paper-shadow candidates: `0`.
- Open candidates: `0`.
- Completed candidates: `0`.
- Rejected counts: `{"missing_prior_20_trading_day_return_pct": 285, "pre_tracking_start_date": 265}`.

## Historical Context

- Historical filtered audit status: `historical_filtered_simulated_forward_audit_passed`.
- Latest-four historical audit rows: `65`.
- Latest-four historical audit PF: `2.4729`.
- Latest-four historical audit PF LB 5%: `1.54`.
- Historical rows are forward proof: `False`.

## Candidate Rows

| Scan Date | Ticker | Lane | Strategy | Expiry | Prior 20% | State |
|---|---|---|---|---|---:|---|

## Boundary

Rows here are forward paper-shadow tracking rows for dashboard/reporting. They are not live trades, Alpaca paper orders, scanner-policy approval, promotion, quote import, evidence mutation, protected-holdout use, or proof-bar changes.
