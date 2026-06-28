# Regular Options Alpaca Underlying Minute Price Surface Import

- Status: `alpaca_underlying_minute_price_surface_source_import_materialized`.
- Source rows written: `true`.
- Source rows: `141699`.
- Covered symbol-dates: `1996`.

This import writes generated Alpaca SIP underlying minute source rows only. It does not import option quotes, mutate `options_history.db`, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Blockers

- None.
