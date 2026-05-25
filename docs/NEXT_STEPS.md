# Next Steps

1. At or after `2026-05-22T14:20:00-06:00`, run `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-22`.
2. Immediately run `python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest` and confirm shared quote dates advance from `2` to `3`.
3. If a licensed ThetaData Standard/Pro terminal is available, start the v3 terminal on port `25503` and run `scripts/import_thetadata_options_nbbo.py` for the 24-symbol commodity universe and at least 100 shared trading days.
4. After any non-Alpaca OPRA import, run `scripts/audit_paid_data_readiness.py` with the imported source label and do not promote until the replay path explicitly isolates that proof source.
5. If Alpaca support or plan docs expose an account-specific historical OPRA quote endpoint, rerun `python scripts/probe_alpaca_options_history_access.py --json` and add an importer only after the endpoint returns point-in-time bid/ask rows.
6. Keep production filter variants locked until exact bid/ask replay has enough history, closed trades, positive expectancy, acceptable drawdown, and out-of-sample or walk-forward validation.
7. Do not use `--skip-scan` as the last artifact refresh for this lane unless immediately followed by a fresh scan; it intentionally removes current scan/proof-universe evidence from the latest report.
