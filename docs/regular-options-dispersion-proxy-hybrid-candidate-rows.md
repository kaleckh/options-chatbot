# Regular Options Dispersion-Proxy Hybrid Candidate Rows

This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_candidate_rows.py`. It is a read-only trial ledger for the preregistered dispersion-proxy hybrid branch. It writes derived research candidate rows only; it does not import quotes, mutate the options database, append cohorts, change scanner or strategy logic, enable live validation or auto-track, submit broker orders, consume protected holdout, lower proof bars, or promote a lane.

## Summary

- Status: `dispersion_proxy_hybrid_candidate_rows_classified_no_pairs`.
- Denominator rows: `494`.
- Candidate rows selected: `0`.
- Rejected or blocked rows: `494`.
- Candidate rows path: `data/profitability-lab/regular-options-dispersion-proxy-hybrid-bounded-replay/candidate_rows.jsonl`.

## Denominator Status Counts

- `blocked_pair_contract_selection`: `54`.
- `rejected_pair_candidate`: `440`.

## Blocker Counts

- `missing_constituent_eligible_expiry`: `27`.
- `missing_constituent_underlying_price`: `27`.
- `missing_eligible_index_expiry`: `27`.
- `missing_entry_date_after_proxy`: `1`.
- `missing_index_underlying_price`: `27`.
- `missing_policy_exit_date`: `6`.
- `rejected_not_concentrated_leadership`: `439`.

## Boundary

- Selected rows are research candidates for bounded replay only.
- They are not dashboard trades, paper-shadow trades, live trades, broker orders, accepted profitability, promotion evidence, or forward proof.
- Pricing and profitability remain blocked until the separate bounded replay consumes these rows and passes its own strict gates.

## Forbidden Actions

- `do_not_import_quotes`
- `do_not_mutate_options_history_db`
- `do_not_append_forward_cohort_rows`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_submit_broker_orders`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_historical_rows_as_forward_proof`
- `do_not_use_midpoint_last_eod_manual_synthetic_or_lookahead_prices`
