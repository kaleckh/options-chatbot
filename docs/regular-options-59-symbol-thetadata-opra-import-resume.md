# Regular Options 59-Symbol ThetaData OPRA Import Resume

- Status: `blocked_59_symbol_import_repair`
- Dry run: `false`
- Resume missing only: `true`
- Provider recheck: `true`
- ThetaTerminal: `available_status_endpoint_gone`
- Shared trusted imported quote dates: `260`
- Missing symbol-date rows: `11565`
- Protected holdout overlap rows: `0`
- Outside-universe import rows: `0`
- Import attempted: `false`
- Imported rows: `0`
- Accepted profitability: `false`

This is a scoped source-repair preflight. It does not create trades, prepare orders, enable live validation, enable auto-track, promote a lane, consume protected holdout, or treat historical rows as forward proof.

## Blockers

- `bulk_import_execution_not_started_by_preflight_wrapper`
