# Regular Options Point-in-Time Dispersion/Concentration Proxy

This report is generated from `scripts/build_regular_options_point_in_time_dispersion_concentration_proxy.py`. It is a read-only input materializer for future dispersion-proxy hybrid research. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.

## Summary

- Status: `point_in_time_dispersion_concentration_proxy_available`.
- Accepted profitability: `false`.
- Covered months: `24` / `24`.
- Date coverage: `100.0`.
- Accepted source rows: `6422`.
- Proxy rows: `494`.

## Source Inventory

```json
{
  "feature_store": {
    "available_symbols": [
      "AAPL",
      "COP",
      "CVX",
      "DIA",
      "GOOGL",
      "IWM",
      "JNJ",
      "LLY",
      "NEM",
      "QQQ",
      "SPY",
      "UNH",
      "XOM"
    ],
    "error": null,
    "exists": true,
    "generated_at_utc": "2026-06-27T03:50:44Z",
    "inventory_status": "feature_store_return_fields_present",
    "missing_symbols": [],
    "path": "data/profitability-lab/regular-options-feature-store/latest.json",
    "proxy_source_rows_provide_return_fields": true,
    "report_id": "regular_options_feature_store",
    "requested_date_count": 494,
    "required": true,
    "return_fields_available": true,
    "status": "loaded",
    "status_value": "feature_store_built",
    "underlying_price_row_count": 0
  },
  "source_rows": {
    "error": null,
    "exists": true,
    "path": "data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/source_rows.jsonl",
    "required": false,
    "row_count": 6422,
    "status": "loaded"
  },
  "status": "ready"
}
```

## Formula Policy

```json
{
  "broadening_or_narrowing_state": "concentrated_leadership when concentration_proxy >= 0.35 and leadership_skew_proxy > 0, else broad_or_mixed; blocked rows stay blocked",
  "concentration_proxy": "max(abs(constituent_return_pct)) / sum(abs(constituent_return_pct))",
  "cross_section_return_dispersion": "population standard deviation of same-known-at constituent return_pct values for the proxy date",
  "leadership_skew_proxy": "index_carrier_return_pct - median(constituent_return_pct)",
  "thresholds_outcome_tuned": false
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
- `canonical_evidence_store_mutation`
- `forward_cohort_append`
- `protected_holdout_consumption`
- `promotion`
- `using_realized_pnl_or_selected_winners_to_define_thresholds`
