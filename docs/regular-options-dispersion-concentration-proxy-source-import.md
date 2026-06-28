# Regular Options Dispersion/Concentration Proxy Source Import

- Status: `dispersion_concentration_proxy_source_import_materialized`.
- Source family: `alpaca_sip_underlying_daily_dispersion_concentration_proxy_v1`.
- Approval token valid: `true`.
- Source rows written: `true`.
- Source rows: `6422`.
- Requested market dates: `494`.
- Downstream proxy status: `point_in_time_dispersion_concentration_proxy_available`.
- Covered months: `24` / `24`.
- Date coverage: `100.0`.
- Historical replay performed: `false`.
- Accepted profitability: `false`.

This import writes generated point-in-time dispersion/concentration proxy source rows from the already-materialized Alpaca SIP underlying daily source rows. It does not run replay, import option quotes, mutate trusted evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Blockers

- None.

## Next Command

```powershell
npm run options:research:dispersion-proxy-hybrid-replay-readiness -- --json
```
