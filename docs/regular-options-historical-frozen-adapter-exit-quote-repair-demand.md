# Regular Options Historical Frozen Adapter Exit Quote Repair Demand

- Status: `exit_quote_repair_demand_ready`.
- Repairable selected rows: `18`.
- Target contracts: `35`.
- Target quote dates: `5`.
- Quotes imported: `false`.

## Excluded Unpriced Statuses

- `missing_market_day_for_policy_exit`: `114`

## Commands

```powershell
uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/profitability-lab/regular-options-historical-frozen-adapter-exit-quote-repair-demand/latest.json --plan-only --json
uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/profitability-lab/regular-options-historical-frozen-adapter-exit-quote-repair-demand/latest.json --theta-url http://127.0.0.1:25503 --source thetadata_opra_nbbo_1m --snapshot-kind intraday --interval 1m --start-time 15:55:00 --end-time 15:55:00 --timeout 180 --json
```

## Boundary

Read-only demand artifact only; it does not request ThetaData, import quotes, mutate options_history.db, rerun replay, or make profitability claims.
