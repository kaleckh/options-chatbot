# Bullish Pullback ThetaData Coverage Status - 2026-05-26

## Scope

Source universe: `data/options-lanes/universes/bullish_pullback_observation.json`

Coverage target:

- 60 symbols
- trusted ThetaData OPRA/NBBO
- `source_label=thetadata_opra_nbbo_1m`
- `dataset_kind=intraday_csv`
- `snapshot_kind=intraday`
- quote dates `2025-05-22` through `2026-05-22`
- quote minutes `610` and `955`

## Result

After removing `CMCSA` from the active lane universe, coverage is complete for all 59 active symbols at both target minutes.

The removed symbol/date gap was:

- `CMCSA`
  - `2026-01-05`
  - missing `quote_minute_et=610`
  - missing `quote_minute_et=955`

All active symbols have 252 dates at both target minutes.

## Evidence

Final audit artifact:

- `data/profitability-lab/bullish-pullback-thetadata-coverage-audit-final-2026-05-26.json`
- `data/profitability-lab/bullish-pullback-thetadata-coverage-audit-post-cmcsa-removal-2026-05-26.json`

ThetaData no-data proof:

- `data/profitability-lab/cmcsa-2026-01-05-thetadata-no-data-proof.json`
- `data/profitability-lab/cmcsa-2026-01-05-thetadata-expanded-probe.json`
- `data/profitability-lab/cmcsa-2026-01-05-exact-contract-probe.json`

ThetaData returned HTTP `472` with `No data found for your request` for `CMCSA` on `2026-01-05` when queried for:

- full regular session, `09:30:00` through `16:00:00`, calls
- exact `10:10:00`, both rights
- exact `15:55:00`, both rights
- exact sampled expirations/strikes/rights across `10:10:00`, `15:55:00`, and the full regular session

ThetaData list endpoints still show `CMCSA` expirations and strikes for the date, so the symbol/contract universe exists. The quote-history endpoint is the missing piece for that symbol/date.

## Backfill Work Completed

Completed one-writer resumable backfills with:

- `scripts/backfill_thetadata_main_lane_last_chance.py`
- canonical source `thetadata_opra_nbbo_1m`
- `snapshot_kind=intraday`
- `right=call`
- `min_dte=0`
- `max_dte=60`
- `strike_range=25`

Passes completed:

- 15:55 ET for the 51 previously thin symbols
- 10:10 ET for the 51 previously thin symbols

## Current Bottleneck

This is no longer a broad data-backfill problem. `CMCSA` had a provider-side no-data hole on `2026-01-05`, so it has been removed from the active lane universe. The remaining active universe is ready for broad testing.
