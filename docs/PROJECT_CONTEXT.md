# Project Context

This repository is a mixed Next.js and FastAPI options research system. The active product lane is supervised options scanning, replay diagnostics, suggested trades, and tracked-position review.

The current AI commodity / commodity-infrastructure lane is a proof-first options lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`. Its preferred final proof path is Alpaca SIP/OPRA bid/ask snapshot replay using `alpaca_opra_daily_snapshot` rows in `data/options-validation/options_history.db`.

The lane must not claim profitability from underlying bars, option OHLC bars, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, or in-sample-only sweeps. Final promotion requires point-in-time bid/ask or NBBO replay with realistic costs and validation splits.

## Active Lane Scope

Until this document is updated or the user explicitly reopens a lane, project work should stay focused on:

- Regular supervised options lane: live scan, replay diagnostics, forward evidence, suggested trades, and tracked-position review.
- AI commodity / commodity-infrastructure options lane: proof-first OPRA/SIP/NBBO validation and related automation.

The following lanes are out of scope for active work:

- Crypto options lane under `crypto_options/*`.
- Polymarket lane under `src/lib/polymarket/*` and related scripts.
- Day-trading lane under `src/lib/day-trading/*`, day-trading tests, and legacy day-trading docs. This lane is paused, not deleted.

Do not spend implementation, performance, research, documentation, or automation effort on out-of-scope lanes unless the user explicitly asks to archive, remove, repair, or reopen one of them. Shared infrastructure changes may touch adjacent files only when required for the regular options lane or the AI commodity lane.

Relevant commands:

```bash
npm run build
npm run verify
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
python scripts/audit_paid_data_readiness.py --json
```
