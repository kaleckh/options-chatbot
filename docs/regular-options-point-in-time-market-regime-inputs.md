# Regular Options Point-in-Time Market Regime Inputs

This report is generated from `scripts/build_regular_options_point_in_time_market_regime_inputs.py`. It is a read-only materializer for SPY momentum, QQQ momentum, and 13-symbol breadth confirmations. It reads local daily close history only, uses prior trading-day rows for candidate dates, and does not run replay, create trades, import quotes, mutate evidence stores, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.

## Summary

- Status: `blocked_point_in_time_market_regime_inputs`.
- Accepted profitability: `false`.
- Requested dates: `494`.
- Covered dates: `0`.
- Covered months: `0` / `24`.
- Date coverage: `0.0`.
- Confirmation counts: `{"breadth_confirmed": 0, "qqq_momentum_confirmed": 324, "spy_momentum_confirmed": 349}`.

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
  "source_time_rule": "daily_history.fetched_at must be before input_date_et; otherwise rows are historical prior-bar reconstruction only",
  "spy_momentum_confirmed": "prior SPY 20-trading-day return > 0 and prior SPY close > prior 50-trading-day SMA"
}
```

## Source Inventory

```json
{
  "feature_store": {
    "error": null,
    "exists": true,
    "generated_at_utc": "2026-06-18T06:09:35Z",
    "path": "data/profitability-lab/regular-options-feature-store/latest.json",
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
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:39Z",
        "row_count": 1515
      },
      "COP": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:41Z",
        "row_count": 1515
      },
      "CVX": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:41Z",
        "row_count": 1515
      },
      "DIA": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:47:18Z",
        "row_count": 1515
      },
      "GOOGL": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:39Z",
        "row_count": 1515
      },
      "IWM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:47:18Z",
        "row_count": 1515
      },
      "JNJ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:40Z",
        "row_count": 1515
      },
      "LLY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:40Z",
        "row_count": 1515
      },
      "NEM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:42Z",
        "row_count": 1515
      },
      "QQQ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:47:18Z",
        "row_count": 1515
      },
      "SPY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:47:18Z",
        "row_count": 1515
      },
      "UNH": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:40Z",
        "row_count": 1515
      },
      "XOM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-23T17:04:41Z",
        "row_count": 1515
      }
    }
  },
  "missing_key_symbols": [],
  "missing_non_key_symbols": [],
  "missing_symbols": [],
  "source_filter": {
    "adjustment_mode": "adjusted",
    "source": "alpaca_sip"
  }
}
```

## Blockers

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
