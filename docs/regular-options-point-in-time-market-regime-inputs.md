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
        "latest_fetched_at_utc": "2026-06-24T17:04:41Z",
        "row_count": 1515
      },
      "COP": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
        "row_count": 1515
      },
      "CVX": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
        "row_count": 1515
      },
      "DIA": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:47:01Z",
        "row_count": 1515
      },
      "GOOGL": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:41Z",
        "row_count": 1515
      },
      "IWM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:47:01Z",
        "row_count": 1515
      },
      "JNJ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
        "row_count": 1515
      },
      "LLY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
        "row_count": 1515
      },
      "NEM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:45Z",
        "row_count": 1515
      },
      "QQQ": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:47:00Z",
        "row_count": 1515
      },
      "SPY": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:47:00Z",
        "row_count": 1515
      },
      "UNH": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
        "row_count": 1515
      },
      "XOM": {
        "first_bar_date": "2020-05-26",
        "latest_bar_date": "2026-06-04",
        "latest_fetched_at_utc": "2026-06-24T17:04:43Z",
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
  },
  "source_mode": "historical_prior_bar_reconstruction",
  "underlying_source_rows": {
    "coverage_ready": false,
    "default_source_rows_path": true,
    "duplicate_symbol_input_date_count": 0,
    "error": null,
    "exists": true,
    "malformed_line_count": 0,
    "min_date_coverage_required_pct": 90.0,
    "min_symbol_date_coverage_pct": 0.0,
    "path": "data/profitability-lab/regular-options-point-in-time-underlying-daily-history/source_rows.jsonl",
    "per_symbol_coverage": {
      "AAPL": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "COP": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "CVX": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "DIA": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "GOOGL": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "IWM": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "JNJ": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "LLY": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "NEM": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "QQQ": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "SPY": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "UNH": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      },
      "XOM": {
        "coverage_pct": 0.0,
        "coverage_ready": false,
        "covered_date_count": 0,
        "requested_date_count": 494
      }
    },
    "reject_count": 1,
    "reject_counts": {
      "default_source_rows_fixture_or_sample_contamination": 1,
      "invalid_prior_bar_date": 1,
      "invalid_source_file_hash": 1,
      "invalid_source_row_hash": 1,
      "missing_close": 1,
      "missing_input_date_et": 1,
      "missing_known_at_utc": 1,
      "missing_or_invalid_close": 1,
      "missing_or_invalid_known_at_utc": 1,
      "missing_or_invalid_prior_20_trading_day_return_pct": 1,
      "missing_or_invalid_prior_50_trading_day_sma": 1,
      "missing_or_invalid_source_timestamp_utc": 1,
      "missing_prior_20_trading_day_return_pct": 1,
      "missing_prior_50_trading_day_sma": 1,
      "missing_prior_bar_date_et": 1,
      "missing_source_file_hash": 1,
      "missing_source_row_hash": 1,
      "missing_source_timestamp_utc": 1,
      "missing_symbol": 1,
      "outside_requested_universe": 1,
      "outside_requested_window": 1,
      "point_in_time_valid_false": 1,
      "source_file_hash_not_bound_to_import_report": 1,
      "source_import_report_not_materialized": 1,
      "source_import_report_source_rows_not_written": 1,
      "source_row_count_not_bound_to_import_report": 1
    },
    "rejected_rows": [
      {
        "index": 1,
        "input_date_et": null,
        "prior_bar_date_et": null,
        "reasons": [
          "default_source_rows_fixture_or_sample_contamination",
          "invalid_prior_bar_date",
          "invalid_source_file_hash",
          "invalid_source_row_hash",
          "missing_close",
          "missing_input_date_et",
          "missing_known_at_utc",
          "missing_or_invalid_close",
          "missing_or_invalid_known_at_utc",
          "missing_or_invalid_prior_20_trading_day_return_pct",
          "missing_or_invalid_prior_50_trading_day_sma",
          "missing_or_invalid_source_timestamp_utc",
          "missing_prior_20_trading_day_return_pct",
          "missing_prior_50_trading_day_sma",
          "missing_prior_bar_date_et",
          "missing_source_file_hash",
          "missing_source_row_hash",
          "missing_source_timestamp_utc",
          "missing_symbol",
          "outside_requested_universe",
          "outside_requested_window",
          "point_in_time_valid_false"
        ],
        "symbol": null
      }
    ],
    "row_count": 1,
    "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
    "source_import_report_binding": {
      "bound": false,
      "expected_source_file_hash": "5e34832ad578880c90870a95cd2d412f15a5b7fc09e0723bbe9da19fb786770a",
      "expected_source_row_count": 0,
      "expected_source_rows_path": "data/profitability-lab/regular-options-point-in-time-underlying-daily-history/source_rows.jsonl",
      "observed_source_file_hashes": [],
      "observed_source_row_count": 1,
      "path": "data/profitability-lab/regular-options-underlying-daily-source-import/latest.json",
      "report": {
        "error": null,
        "exists": true,
        "generated_at_utc": "2026-06-24T05:12:59Z",
        "path": "data/profitability-lab/regular-options-underlying-daily-source-import/latest.json",
        "report_id": "regular_options_underlying_daily_history_source_import",
        "required": false,
        "status": "loaded",
        "status_value": "blocked_underlying_daily_history_source_import"
      },
      "status": "binding_failed"
    },
    "source_mode": null,
    "status": "loaded_invalid",
    "valid_row_count": 0
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
