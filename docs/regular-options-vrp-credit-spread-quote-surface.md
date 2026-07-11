# Regular Options VRP Credit Spread Quote Surface

This generated report is read-only. It checks whether existing trusted local OPRA/NBBO rows contain same-minute, same-expiry put quote surfaces for the preregistered VRP credit-spread geometry. It does not run replay, compute P&L, import quotes, mutate evidence, consume holdout, or promote any lane.

## Summary

- Status: `credit_spread_quote_surface_ready`.
- Surface ready: `true`.
- Accepted profitability: `false`.
- Symbols ready: `SPY, QQQ, IWM, DIA`.

## Blockers

- None.

## Symbol Coverage

| Symbol | Status | Covered Months | Latest-Four Months | Covered Dates | Spread Groups | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `SPY` | `ready` | 24 / 24 | 4 / 4 | 464 | 19644 | - |
| `QQQ` | `ready` | 24 / 24 | 4 / 4 | 464 | 20734 | - |
| `IWM` | `ready` | 24 / 24 | 4 / 4 | 458 | 18573 | - |
| `DIA` | `ready` | 24 / 24 | 4 / 4 | 457 | 13302 | - |

## Forbidden Actions

- `do_not_create_trades`
- `do_not_run_replay`
- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort_rows`
- `do_not_consume_protected_holdout`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_promote_any_lane`
- `do_not_claim_accepted_profitability`
