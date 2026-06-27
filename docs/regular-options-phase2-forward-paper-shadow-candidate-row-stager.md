# Phase 2 Forward Paper-Shadow Candidate Row Stager

This artifact stages append-only candidate rows only. It does not append the cohort log or authorize live trading.

- Status: `candidate_rows_staged_validation_passed`.
- Source mode: `scan_picks`.
- Source path: `C:\Users\kalec\AppData\Local\Temp\tmpppuj57pe\scan_picks.jsonl`.
- Candidate rows staged: `1`.
- Candidate JSONL written: `true`.
- Cohort append performed: `false`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Rejected counts: `{}`.
- Validation: `{"append_allowed": true, "append_ready_rows": 1, "append_reject_counts": {"blocked_by_required_contracts": 0, "duplicate_row_id": 0, "exact_entry_missing_entry_quote_provenance": 0, "exact_entry_missing_exact_entry_evidence": 0, "exact_exit_missing_entry_quote_provenance": 0, "exact_exit_missing_exact_entry_evidence": 0, "exact_exit_missing_exact_exit_evidence": 0, "exact_exit_missing_exit_quote_provenance": 0, "exact_exit_missing_net_pnl_usd": 0, "exact_exit_missing_policy_exit_condition": 0, "exact_row_uses_non_executable_mark": 0, "fixture_rows_not_append_eligible": 0, "lookahead_source": 0, "market_window_not_open": 0, "missing_real_source_provenance": 0, "missing_required_schema_fields": 0, "missing_source_provenance_fields": 0, "non_frozen_lane": 0, "non_preregistered_symbol": 0, "pre_freeze_not_append_eligible": 0, "scanner_hash_drift": 0, "unknown_denominator_status": 0}, "append_rejected_rows": 0, "overall_status": "candidate_rows_append_validation_passed_no_append_performed", "total_natural_selections": 1}`.

Fresh real-mode rows require a confirmed open market window and same-day natural selections. Fixture mode is the closed-market test path.
