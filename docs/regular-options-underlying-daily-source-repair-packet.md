# Regular Options Underlying Daily Source Repair Packet

- Status: `underlying_daily_source_repair_packet_ready_for_future_source_import_decision`
- Blocker: `underlying_daily_history_source_not_point_in_time`
- Source family: `point_in_time_underlying_daily_ohlcv_adjusted_v1`
- Accepted profitability: `false`
- Strict forward proof: `0/30`
- Frozen scanner blocked rows: `6916`
- Underlying blocker rows: `6916`
- Materialized: `false`

This is a read-only source repair packet. It does not import data, write source rows, mutate trusted evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Why Local daily_history Is Insufficient

Local market_data.db daily_history can reconstruct prior daily closes after the fact, but its fetched_at timestamps are in 2026 for 2024-06-01..2026-05-31 decisions and the table lacks independent published_at/known_at/source-event provenance. Using those rows would infer known-at from bar_date or from a later fetch, which is not point-in-time proof.

## Required Future Source Fields

- `symbol`
- `bar_date`
- `open`
- `high`
- `low`
- `close`
- `adjusted_close or adjustment policy`
- `volume`
- `vendor/source`
- `source_event_time/date`
- `published_at_utc or known_at_utc`
- `fetched_at_utc`
- `adjustment_mode`
- `corporate_action_basis`
- `source_file_hash/provenance id`

## Known-At Policy

A row for bar_date D is usable for candidate date T only if published_at_utc or known_at_utc is strictly before the candidate decision timestamp/date.

Do not infer `known_at` from `bar_date` alone.

## Validation Gates

```json
{
  "coverage_thresholds": {
    "date_coverage_pct_min": 90.0,
    "latest_four_months_required": 4,
    "symbols_required": [
      "SPY",
      "QQQ",
      "IWM",
      "DIA",
      "AAPL",
      "GOOGL",
      "UNH",
      "LLY",
      "JNJ",
      "XOM",
      "CVX",
      "COP",
      "NEM"
    ],
    "train_months_min": 20
  },
  "no_duplicate_conflicting_rows": true,
  "no_future_or_same_day_leakage": true,
  "no_missing_prices_or_volume": true,
  "no_non_monotonic_known_at": true,
  "no_outcome_pnl_winner_fields": [
    "future_return",
    "label",
    "net_pnl",
    "net_pnl_usd",
    "pnl",
    "realized_pnl",
    "return_after_entry",
    "selected_winner",
    "target",
    "trade_outcome",
    "winner"
  ],
  "no_stale_manual_synthetic_source_mark_only_rows": true,
  "protected_holdout_use_allowed": false
}
```

## Downstream Unlocks

- point-in-time market-regime inputs
- historical frozen scanner replay adapter
- frozen daily candidate decisions
- historical simulated-forward audit

## Downstream Commands After Future Source Materialization

```powershell
npm run options:research:point-in-time-market-regime-inputs -- --no-write --json
npm run options:research:historical-frozen-scanner-replay-adapter -- --no-write --json
npm run options:research:13-symbol-frozen-daily-candidate-decisions -- --no-write --json
npm run options:audit:historical-simulated-forward -- --json
```

## Future Approval

- Required token: `APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT`
- Not run now: `true`
- Source rows written now: `false`

Approve future non-live, non-broker materialization of trusted point-in-time underlying daily history rows for the 13-symbol universe and 2024-06-01..2026-05-31 window plus lookback, into a generated source artifact only.

```powershell
npm run options:source-import:underlying-daily-history -- --source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv --lookback-start-date 2024-03-01 --target-start-date 2024-06-01 --target-end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,DIA,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM --source-family point_in_time_underlying_daily_ohlcv_adjusted_v1 --approval-token APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT --no-replay --json
```
