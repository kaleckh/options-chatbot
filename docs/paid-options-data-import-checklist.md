# Paid Options Data Import Checklist

Last updated: 2026-05-31

Use this when a paid historical options dataset arrives. The goal is to prove whether a lane has real edge with executable historical prices, without mutating live tracked positions.

## Current Proof Targets

### Regular supervised options lane

Current exact ThetaData proof work targets the active `bullish_pullback_observation` universe:
- `59` active symbols from `data/options-lanes/universes/bullish_pullback_observation.json`
- `CMCSA` excluded
- trusted ThetaData intraday OPRA/NBBO coverage currently has `252` shared dates from `2025-05-22` through `2026-05-22`

SPY/QQQ remain the manifest's historical-ready subset, but the current profitability work is the broader exact-contract 59-symbol paper-shadow branch.

### AI commodity / commodity-infrastructure lane

The current 24-symbol scan/proof universe comes from `data/ai-commodity-infra/universe.json`:

```text
FCX, SLV, VRT, VST, ETN, GEV, PWR, CCJ, CEG, SCCO, COPX, URA,
ALB, SQM, MP, RIO, BHP, TECK, AA, XME, NRG, NVT, CARR, TT
```

For this lane, the exact proof source currently accepted by the generated runbook is `alpaca_opra_daily_snapshot`. Other sources can be imported for research or acceleration only after they are labeled and audited separately.

## Required Quote Fields

Required:
- underlying symbol
- option contract symbol or enough fields to reconstruct it
- expiration
- strike
- call/put
- quote timestamp or snapshot date/time
- bid
- ask
- source label
- snapshot kind

Strongly preferred:
- bid size and ask size
- volume
- open interest
- underlying price at snapshot time
- exchange or feed condition fields

Expired contracts must be included.

## Canonical Destination

Import paid data into:

```text
data/options-validation/options_history.db
```

Do not put raw paid provider data under `data/profitability-lab`. That folder is for derived audit and research artifacts.

## Existing Import Paths

Daily Parquet manifest:

```powershell
uv run --locked python scripts/import_historical_options_snapshots.py --manifest path\to\manifest.json --json
```

CSV snapshot file:

```powershell
uv run --locked python scripts/import_historical_options_snapshots.py --input path\to\quotes.csv --source vendor_symbol_range --format csv --json
```

ThetaData v3 historical option quote importer:

```powershell
uv run --locked python scripts/import_thetadata_options_nbbo.py --date-from YYYY-MM-DD --date-to YYYY-MM-DD --symbols FCX,SLV,VRT,VST,ETN,GEV,PWR,CCJ,CEG,SCCO,COPX,URA,ALB,SQM,MP,RIO,BHP,TECK,AA,XME,NRG,NVT,CARR,TT --strike-range 10 --snapshot-kind daily_eod --source thetadata_opra_nbbo_1m --json
```

Regular sector ETF import planner:

```powershell
python scripts/plan_regular_sector_etf_imports.py --json
```

The sector planner is read-only. It checks trusted intraday readiness for `GLD`, `TLT`, `XLE`, `XLF`, `SMH`, and `KRE`, treats Theta v3's retired `/v2/system/status` `410 Gone` response as a reachable local terminal, and emits one-day dry-run plus full import commands. Current sector commands use Theta v3's `1h` hourly interval spelling and a `30` second request timeout.

Missing replay-contract quote backfill from an existing run artifact:

```powershell
uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data\options-validation\runs\<run>.json --lookahead-calendar-days 3 --json
```

Provider-specific adapters should normalize into the existing `option_quote_snapshots` schema rather than creating a parallel store.

## Required Validation

After import, run:

```powershell
uv run --locked python scripts/audit_paid_data_readiness.py --force --json
uv run --locked python scripts/summarize_profitability_research.py
```

For a source-specific AI commodity audit, include the source label and all 24 required underlyings:

```powershell
uv run --locked python scripts/audit_paid_data_readiness.py --json --source-labels thetadata_opra_nbbo_1m --required-underlyings FCX,SLV,VRT,VST,ETN,GEV,PWR,CCJ,CEG,SCCO,COPX,URA,ALB,SQM,MP,RIO,BHP,TECK,AA,XME,NRG,NVT,CARR,TT --min-quote-dates 100 --min-shared-quote-dates 100 --min-executable-quote-pct 90
```

The readiness audit should reach `ready_for_exact_replay` before any profitability claim from that dataset.

## Current Baseline Before New Paid Data

- Regular options historical proof for `bullish_pullback_observation` now has trusted ThetaData intraday OPRA/NBBO coverage for all `59` active symbols, but current promoted evidence remains paper-shadow only: S/A/B confidence has `108` exact trades at PF `4.86`, and the count-expanded branch has `130` exact trades at PF `2.04`.
- Regular sector ETF expansion is no longer data-depth blocked: `IWM`, `GLD`, `TLT`, `XLE`, `XLF`, `SMH`, and `KRE` each have `252` trusted intraday quote dates from `2025-05-22` through `2026-05-22`; the latest sector planner readback reports `ready_for_sector_replay`. The first focused regular-sector replay rejected the simple XLE/XLF/KRE/SMH/TLT/sector-rotation shapes, so new sector claims still need a different causal rule and frozen-gate proof.
- The AI commodity lane has `3` / `100` exact Alpaca OPRA shared quote dates as of the latest generated readback on `2026-05-31T09:10:46Z`; its next guarded event is `python scripts/run_ai_commodity_opra_progress.py --skip-capture`, not before `2026-06-01T08:10:00-06:00`.
- Alpaca historical option bars/trades are accessible locally, but historical option quotes returned `404` in the latest probe, so they do not backfill proof-grade bid/ask history.
- OnclickMedia EOD bid/ask chains are research-grade only and are not OPRA-certified final proof.
- ThetaData import support exists, but a licensed Standard/Pro terminal must be available before it can accelerate the proof path.

## Do Not Do

- Do not auto-track positions from data import tests.
- Do not overwrite or delete existing tracked positions.
- Do not count nearest-listed contracts as promotion proof.
- Do not mix source labels when making a proof claim.
- Do not treat midpoint-only, last-trade, bars-only, or stale latest snapshots as executable bid/ask proof.
- Do not tune production filters in the AI commodity lane until exact OPRA replay can measure the changes.
