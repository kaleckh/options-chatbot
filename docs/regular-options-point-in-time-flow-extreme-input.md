# Regular Options Point-in-Time Flow-Extreme Input

This report is generated from `scripts/build_regular_options_point_in_time_flow_extreme_input.py`. It is a read-only input materializer for the flow-extreme ratio/backspread research branch. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.

## Summary

- Status: `blocked_point_in_time_flow_extreme_input`.
- Accepted profitability: `false`.
- Covered months: `0` / `24`.
- Date coverage: `0.0`.
- Accepted source rows: `0`.
- Proxy basis: `[]`.

## Source Inventory

```json
{
  "feature_store": {
    "available_symbols": [
      "QQQ",
      "SPY"
    ],
    "error": null,
    "exists": true,
    "generated_at_utc": "2026-06-18T06:09:35Z",
    "inventory_status": "feature_store_loaded_for_underlyings",
    "missing_symbols": [],
    "path": "data/profitability-lab/regular-options-feature-store/latest.json",
    "report_id": "regular_options_feature_store",
    "requested_date_count": 494,
    "required": true,
    "status": "loaded",
    "status_value": "feature_store_built"
  },
  "options_history_db": {
    "error": null,
    "exists": true,
    "flow_columns": {
      "ask_size": false,
      "bid_size": false,
      "open_interest": true,
      "quote_depth": false,
      "volume": true
    },
    "path": "data/options-validation/options_history.db",
    "status": "loaded",
    "tables": {
      "import_batches": [
        "id",
        "source_label",
        "dataset_kind",
        "data_trust",
        "input_path",
        "file_hash",
        "imported_at_utc",
        "total_rows",
        "imported_rows",
        "duplicate_rows",
        "rejected_rows",
        "warnings_json"
      ],
      "option_quote_snapshots": [
        "id",
        "as_of_utc",
        "quote_date_et",
        "quote_minute_et",
        "snapshot_kind",
        "underlying",
        "contract_symbol",
        "expiry",
        "option_type",
        "strike",
        "bid",
        "ask",
        "last",
        "iv",
        "underlying_price",
        "volume",
        "open_interest",
        "source_batch_id"
      ],
      "sqlite_sequence": [
        "name",
        "seq"
      ]
    }
  },
  "plain_bid_ask_only_is_not_flow": true,
  "preregistered_playbook": {
    "error": null,
    "exists": true,
    "generated_at_utc": "2026-06-23T05:51:48Z",
    "path": "data/profitability-lab/regular-options-preregistered-flow-extreme-ratio-backspread-playbook/latest.json",
    "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
    "required": true,
    "status": "loaded",
    "status_value": "preregistered_design_only"
  },
  "schema_declared_flow_basis": {
    "bid_ask_size_imbalance": false,
    "quote_depth_pressure": false,
    "volume_open_interest": true
  },
  "source_rows": {
    "error": null,
    "exists": false,
    "path": "data/profitability-lab/regular-options-point-in-time-flow-extreme-input/source_rows.jsonl",
    "required": false,
    "row_count": 0,
    "status": "missing"
  },
  "status": "missing_flow_source_rows"
}
```

## Threshold Policy

```json
{
  "description": "Rows must carry predeclared flow/extreme scores and known-at timestamps. Plain bid/ask price availability is not a flow input.",
  "future_outcomes_used": false,
  "outcome_tuned": false,
  "policy_id": "point_in_time_flow_extreme_static_proxy_policy_v1",
  "realized_pnl_used": false,
  "selected_winners_used": false
}
```

## Blockers

- `missing_point_in_time_flow_extreme_source`
- `missing_required_flow_fields`
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
- `canonical_evidence_store_mutation`
- `forward_cohort_append`
- `protected_holdout_consumption`
- `promotion`
- `using_realized_pnl_or_selected_winners_to_define_thresholds`
- `relabeling_plain_bid_ask_prices_as_flow`
