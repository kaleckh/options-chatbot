# Regular Options VRP Credit Spread Quote Surface

This generated report is read-only. It checks whether existing trusted local OPRA/NBBO rows contain same-minute, same-expiry put quote surfaces for the preregistered VRP credit-spread geometry. It does not run replay, compute P&L, import quotes, mutate evidence, consume holdout, or promote any lane.

## Summary

- Status: `blocked_vrp_credit_spread_quote_surface`.
- Surface ready: `false`.
- Accepted profitability: `false`.
- Symbols ready: `-`.

## Blockers

- `missing_index_credit_spread_quote_surface`

## Symbol Coverage

| Symbol | Status | Covered Months | Latest-Four Months | Covered Dates | Spread Groups | Blockers |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `SPY` | `blocked` | 3 / 24 | 2 / 4 | 31 | 40 | insufficient_month_coverage, insufficient_latest_four_month_coverage |
| `QQQ` | `blocked` | 4 / 24 | 3 / 4 | 31 | 47 | insufficient_month_coverage, insufficient_latest_four_month_coverage |
| `IWM` | `blocked` | 4 / 24 | 2 / 4 | 23 | 27 | insufficient_month_coverage, insufficient_latest_four_month_coverage |
| `DIA` | `blocked` | 2 / 24 | 0 / 4 | 9 | 14 | insufficient_month_coverage, insufficient_latest_four_month_coverage |

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
