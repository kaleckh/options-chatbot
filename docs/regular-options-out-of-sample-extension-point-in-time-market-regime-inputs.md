# Regular Options Point-in-Time Market Regime Inputs

This report is generated from `scripts/build_regular_options_point_in_time_market_regime_inputs.py`. It is a read-only materializer for SPY momentum, QQQ momentum, and 13-symbol breadth confirmations. It reads local daily close history only, uses prior trading-day rows for candidate dates, and does not run replay, create trades, import quotes, mutate evidence stores, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.

## Summary

- Status: `blocked_point_in_time_market_regime_inputs`.
- Accepted profitability: `false`.
- Requested dates: `541`.
- Covered dates: `0`.
- Covered months: `0` / `29`.
- Date coverage: `0.0`.
- Confirmation counts: `{"breadth_confirmed": 0, "qqq_momentum_confirmed": 287, "spy_momentum_confirmed": 285}`.

## Formula Policy

```json
{
  "breadth_confirmed": "at least 60% of available eligible universe symbols are above prior 50-trading-day SMA and available_symbol_count >= 10",
  "missing_symbol_policy": "SPY and QQQ are key symbols. Non-key missing symbols are tolerated only while breadth available_symbol_count remains at least 10.",
  "option_marks_used": false,
  "outcome_tuned": false,
  "prior_close_rule": "input_date_et joins only to daily_history rows with bar_date < input_date_et",
  "qqq_momentum_confirmed": "prior QQQ 20-trading-day return > 0 and prior QQQ close > prior 50-trading-day SMA",
  "realized_pnl_used": false,
  "selected_winners_used": false,
  "source_time_rule": "verified source_rows rows must have point_in_time_valid=true, proof_eligible=false, source_family match, precomputed prior_20_trading_day_return_pct and prior_50_trading_day_sma from importer-known prior bars, SHA-256 source hashes, prior_bar_date_et < input_date_et, and known_at_utc before the candidate decision. market_data.db is fallback reconstruction only.",
  "spy_momentum_confirmed": "prior SPY 20-trading-day return > 0 and prior SPY close > prior 50-trading-day SMA"
}
```

## Source Inventory

```json
{
  "feature_store": {
    "error": null,
    "exists": true,
    "generated_at_utc": "2026-07-02T16:20:53Z",
    "path": "data/profitability-lab/regular-options-out-of-sample-extension/feature-store/latest.json",
    "report_id": "regular_options_feature_store",
    "required": true,
    "status": "loaded",
    "status_value": "feature_store_built"
  },
  "market_data_db": {
    "adjustment_mode": "adjusted",
    "error": null,
    "exists": true,
    "path": "market_data.db",
    "rejected_row_counts": {},
    "source": "alpaca_sip",
    "status": "loaded",
    "symbols": {
      "AAPL": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:41Z",
        "row_count": 1012
      },
      "COP": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:56Z",
        "row_count": 1012
      },
      "CVX": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:54Z",
        "row_count": 1012
      },
      "DIA": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:30:30Z",
        "row_count": 1012
      },
      "GOOGL": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:30:18Z",
        "row_count": 1012
      },
      "IWM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:30:29Z",
        "row_count": 1012
      },
      "JNJ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:52Z",
        "row_count": 1012
      },
      "LLY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:52Z",
        "row_count": 1012
      },
      "NEM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:30:05Z",
        "row_count": 1012
      },
      "QQQ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T08:25:55Z",
        "row_count": 1012
      },
      "SPY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T08:25:54Z",
        "row_count": 1012
      },
      "UNH": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:51Z",
        "row_count": 1012
      },
      "XOM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2024-05-31",
        "latest_fetched_at_utc": "2026-06-05T07:29:54Z",
        "row_count": 1012
      }
    }
  },
  "missing_key_symbols": [],
  "missing_non_key_symbols": [],
  "missing_symbols": [],
  "source_filter": {
    "adjustment_mode": "adjusted",
    "source": "alpaca_sip"
  },
  "source_mode": "historical_prior_bar_reconstruction",
  "underlying_source_rows": {
    "error": null,
    "exists": false,
    "path": "data/profitability-lab/regular-options-out-of-sample-extension/underlying-daily-history/source_rows.jsonl",
    "status": "missing"
  }
}
```

## Blockers

- `missing_or_invalid_verified_underlying_source_rows`
- `market_regime_inputs_using_historical_reconstruction`
- `point_in_time_market_regime_row_validation_failed`
- `insufficient_month_coverage`
- `insufficient_date_coverage`

## Forbidden Actions

- `broker_orders`
- `broker_order_preparation`
- `live_validation`
- `auto_track`
- `production_scanner_changes`
- `strategy_logic_changes`
- `stop_changes`
- `sizing_changes`
- `proof_bar_changes`
- `quote_import`
- `external_market_data_fetch`
- `options_history_db_mutation`
- `market_data_db_mutation`
- `canonical_evidence_store_mutation`
- `forward_cohort_append`
- `protected_holdout_consumption`
- `promotion`
- `using_realized_pnl_or_selected_winners_to_define_thresholds`
- `using_option_marks_midpoints_eod_display_last_manual_synthetic_or_lookahead_rows_as_proof`
