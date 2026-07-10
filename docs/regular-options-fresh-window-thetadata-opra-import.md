# Regular Options Fresh-Window ThetaData OPRA Import

- Status: `blocked_fresh_window_thetadata_opra_import`.
- Dry run: `false`.
- Approval token valid: `true`.
- Window: `2026-07-03` through `2026-07-07`.
- Latest completed market day: `2026-07-07`.
- Store max before: `2026-07-02`.
- Store max after: `2026-07-06`.
- Symbols: `13`.
- Missing symbol-dates: `26`.
- Active store writer processes: `0`.
- Import attempted: `true`.
- Imported rows: `18052`.
- Rejected rows: `0`.
- Outside-universe import rows: `0`.
- Protected holdout overlap rows: `0`.
- Refresh after import: `true`.

This tokened import only refreshes trusted quote/source coverage through the guarded importer. It does not change scanner policy, filters, proof bars, stops, sizing, live validation, auto-track, broker behavior, holdout policy, or promotion.

## Blockers

- `provider_or_import_errors`
