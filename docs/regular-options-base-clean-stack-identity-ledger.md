# Regular Options Base Clean Stack Identity Ledger

This generated artifact is a read-only row-level identity ledger for the current clean base stack. It is duplicate-control infrastructure only and does not create proof rows, run replay, or claim profitability.

## Summary

- Status: `base_clean_stack_identity_ledger_ready`.
- Expected base clean rows: `157`.
- Ledger rows: `157`.
- Unique identities: `157`.
- Duplicate identities: `0`.
- Missing identity rows: `0`.
- Future/outcome identity dependencies: `0`.
- Protected holdout overlaps: `0`.
- Accepted profitability: `false`.

## Required Identity Fields

- `lane_id`
- `source_playbook`
- `ticker`
- `entry_date`
- `direction`
- `strategy_type`
- `long_contract_symbol`
- `short_contract_symbol`
- `entry_policy`
- `exit_policy`
- `candidate_source_id`

## Blockers

- None.

## Forbidden Actions

- `do_not_run_replay`
- `do_not_create_trades`
- `do_not_prepare_or_submit_broker_orders`
- `do_not_enable_live_validation`
- `do_not_enable_auto_track`
- `do_not_change_scanner_policy`
- `do_not_change_strategy_logic`
- `do_not_change_stops`
- `do_not_change_sizing`
- `do_not_lower_proof_bars`
- `do_not_import_quotes`
- `do_not_mutate_evidence_stores`
- `do_not_append_forward_cohort_rows`
- `do_not_consume_protected_holdout`
- `do_not_promote_any_lane`
- `do_not_count_ledger_rows_as_profitability_or_forward_proof`
