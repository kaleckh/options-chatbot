# Regular Options Point-in-Time Market Regime Inputs

This report is generated from `scripts/build_regular_options_point_in_time_market_regime_inputs.py`. It is a read-only materializer for SPY momentum, QQQ momentum, and 13-symbol breadth confirmations. It reads local daily close history only, uses prior trading-day rows for candidate dates, and does not run replay, create trades, import quotes, mutate evidence stores, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.

## Summary

- Status: `point_in_time_market_regime_inputs_ready`.
- Accepted profitability: `false`.
- Requested dates: `541`.
- Covered dates: `541`.
- Covered months: `29` / `29`.
- Date coverage: `100.0`.
- Confirmation counts: `{"breadth_confirmed": 268, "qqq_momentum_confirmed": 287, "spy_momentum_confirmed": 285}`.

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
    "exists": true,
    "path": "market_data.db",
    "status": "not_used_source_rows_preferred"
  },
  "missing_key_symbols": [],
  "missing_non_key_symbols": [],
  "missing_symbols": [],
  "source_filter": {
    "adjustment_mode": "adjusted",
    "source": "alpaca_sip"
  },
  "source_mode": "point_in_time_verified_daily_history_source_rows",
  "underlying_source_rows": {
    "coverage_ready": true,
    "default_source_rows_path": false,
    "duplicate_symbol_input_date_count": 0,
    "error": null,
    "exists": true,
    "malformed_line_count": 0,
    "min_date_coverage_required_pct": 90.0,
    "min_symbol_date_coverage_pct": 100.0,
    "path": "data/profitability-lab/regular-options-out-of-sample-extension/underlying-daily-history/source_rows.jsonl",
    "per_symbol_coverage": {
      "AAPL": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "COP": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "CVX": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "DIA": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "GOOGL": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "IWM": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "JNJ": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "LLY": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "NEM": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "QQQ": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "SPY": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "UNH": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      },
      "XOM": {
        "coverage_pct": 100.0,
        "coverage_ready": true,
        "covered_date_count": 541,
        "requested_date_count": 541
      }
    },
    "reject_count": 0,
    "reject_counts": {},
    "rejected_rows": [],
    "row_count": 7033,
    "source_family": "point_in_time_underlying_daily_ohlcv_adjusted_v1",
    "source_import_report_binding": {
      "bound": true,
      "expected_source_file_hash": "34a1ec7749d11e49451ef66aefa65594e79eaa5dfa5b36e04cd9a2d3919ec1a8",
      "expected_source_row_count": 7033,
      "expected_source_rows_path": "data/profitability-lab/regular-options-out-of-sample-extension/underlying-daily-history/source_rows.jsonl",
      "observed_source_file_hashes": [
        "34a1ec7749d11e49451ef66aefa65594e79eaa5dfa5b36e04cd9a2d3919ec1a8"
      ],
      "observed_source_row_count": 7033,
      "path": "data/profitability-lab/regular-options-out-of-sample-extension/underlying-daily-source-import/latest.json",
      "report": {
        "error": null,
        "exists": true,
        "generated_at_utc": "2026-07-06T05:28:32Z",
        "path": "data/profitability-lab/regular-options-out-of-sample-extension/underlying-daily-source-import/latest.json",
        "report_id": "regular_options_underlying_daily_history_source_import",
        "required": false,
        "status": "loaded",
        "status_value": "underlying_daily_history_source_import_materialized"
      },
      "status": "bound"
    },
    "source_mode": "point_in_time_verified_daily_history_source_rows",
    "status": "loaded_ready",
    "valid_row_count": 7033
  }
}
```

## Blockers

- None.

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
