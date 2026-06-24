# Regular Options Macro-Event Calendar

This report is generated from `scripts/build_regular_options_macro_event_calendar.py`. It is a read-only point-in-time calendar validator for scheduled macro-event research. It does not run option replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, consume protected holdout, or promote any lane.

## Summary

- Status: `blocked_macro_event_calendar_source_missing`.
- Accepted events: `0`.
- Source rows: `0`.
- Leakage rejects: `0`.

## Categories

- Required: `["fomc_rate_decision", "fomc_minutes", "cpi", "pce", "nonfarm_payrolls", "scheduled_fed_chair_testimony"]`.
- Covered: `[]`.
- Missing: `["cpi", "fomc_minutes", "fomc_rate_decision", "nonfarm_payrolls", "pce", "scheduled_fed_chair_testimony"]`.

## Blockers

- `macro_event_calendar_source_missing`
- `missing_required_macro_event_categories`

## Rejected Rows

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
- `options_history_db_mutation`
- `forward_or_evidence_store_mutation`
- `protected_holdout_consumption`
- `promotion`
- `historical_option_replay`
- `treating_calendar_rows_as_profitability_proof`
