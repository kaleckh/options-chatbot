# Regular Options Filtered Forward Paper-Shadow Tracker

This generated readback tracks prospective scan-pick rows that match the frozen historical filtered candidate policy. It is dashboard/reporting evidence, not broker execution.

## Summary

- Status: `filtered_forward_paper_shadow_tracking_active`.
- Tracking policy: `historical_filtered_candidate_v1`.
- Tracking start date: `2026-06-30`.
- Tracking start timestamp: `2026-06-30T05:03:45Z`.
- Tracking start source: `frozen_policy_contract`.
- Filter: `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906`.
- Policy contract: `data/contracts/regular-options-frozen-filtered-policy-v1.json`.
- Policy drift status: `latest_filtered_audit_matches_frozen_contract`.
- Conditions: ticker in NEM,JNJ,GOOGL,AAPL,IWM,CVX,SPY,QQQ; signal_evidence.prior_20_trading_day_return_pct gte 10.990605.
- Source scan rows: `550`.
- Evaluated scan rows: `0`.
- Matched forward paper-shadow candidates: `0`.
- Open candidates: `0`.
- Completed candidates: `0`.
- Rejected counts: `{"missing_prior_20_trading_day_return_pct": 285, "pre_tracking_start_date": 265}`.
- Forward evidence bar status: `waiting_for_min_completed_forward_rows`.

## Historical Context

- Historical filtered audit status: `blocked_historical_filtered_simulated_forward_audit`.
- Latest-four historical audit rows: `57`.
- Latest-four historical audit PF: `2.511`.
- Latest-four historical audit PF LB 5%: `1.15`.
- Historical rows are forward proof: `False`.

## Forward Evidence Bar

- Bar ID: `regular_options_filtered_forward_evidence_bar_v1`.
- Completed rows: `0` / `30`.
- Ticker-week clusters: `0` / `8`.
- Calendar months with rows: `0` / `3`.
- Fixture rows: `0` / max `0`.
- Evaluation permitted: `False`.
- Criteria met reporting-only: `False`.
- Approval authority: `False`.
- Percent cluster PF LB 5%: `None`.
- USD cluster PF LB 5%: `None`.
- Total net USD: `None`.

## Parity Disclosure

- Historical materializer entry window ET: `10:10-10:25`.
- Historical materializer: `deterministic_local_pit_candidate_materializer_v1`.
- Forward source: `production_scan_sessions`.
- Scheduled session times: `{"\\OptionsScanPicks": "11:00:00 AM", "\\OptionsScanPicksSafetyNet": "11:30:00 AM"}`.
- Forward results are a new distribution: `True`.
- Expected match-rate note: filtered materializer produced 306 rows / 24 months (~13 per month upper bound before production scanner gates), so months of zero forward matches are expected and are not by themselves a tracker bug.

## Candidate Rows

| Scan Date | Ticker | Lane | Strategy | Expiry | Prior 20% | State |
|---|---|---|---|---|---:|---|

## Boundary

Rows here are forward paper-shadow tracking rows for dashboard/reporting. They are not live trades, Alpaca paper orders, scanner-policy approval, promotion, quote import, evidence mutation, protected-holdout use, or proof-bar changes.
