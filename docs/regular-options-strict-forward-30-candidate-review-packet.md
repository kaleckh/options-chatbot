# Regular Options Strict Forward 30 Candidate Review Packet

Status: `candidate_review_waiting_for_scheduler_health`.

- Strict forward rows: `0/30`.
- Candidate JSONL exists: `false`.
- Candidate rows: `0`.
- Append allowed by validation: `false`.
- Append ready rows: `0`.
- Append rejected rows: `0`.
- Capture status: `no_phase2_natural_selections_no_append`.
- Capture freshness: `capture_latest_fresh_for_candidate_review`.
- Collector status: `collector_attempts_exhausted_waiting_for_more_rows`.
- Scheduler status: `scheduler_runtime_blocked`.
- Scheduler freshness: `scheduler_health_fresh_for_candidate_review`.
- Scan-task health status: `scan_tasks_ready_for_next_market_window`.
- Scan-task health freshness: `scan_task_health_fresh_for_candidate_review`.
- Throughput status: `blocked_no_same_day_phase2_natural_selections`.
- Candidate-starvation evidence status: `raw_symbol_drop_reasons_recorded`.
- Zero-candidate diagnostics status: `zero_candidate_diagnosis_ready_symbol_drop_reasons_recorded`.
- Zero-candidate throughput evidence: `zero_candidate_evidence_blocks_candidate_review`.
- Candidate batch provenance: `candidate_batch_not_present`.

This packet is review-only. It validates the candidate handoff and renders guarded commands, but it does not append rows or authorize live validation, auto-track, broker orders, quote import, proof-bar changes, promotion, or historical rows as forward proof.

## Operator Commands

- `refresh_scheduler_health`: `npm run options:goal-loop:strict-forward-30-scheduler-health -- --json`
- `refresh_scan_task_health`: `npm run options:goal-loop:strict-forward-scan-task-health -- --json`
- `refresh_candidate_throughput_audit`: `npm run options:audit:forward-candidate-throughput -- --json`
- `refresh_collector_status`: `npm run options:goal-loop:strict-forward-30-auto-window -- --json`
- `validate_candidate_jsonl`: `npm run options:validate:phase2-forward-paper-shadow-candidate -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl`
- `guarded_append_template`: `npm run options:append:phase2-forward-paper-shadow -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl --approval-token <EXPLICIT_OPERATOR_APPROVAL_TOKEN> --market-window-confirmed`

## Candidate Throughput Blockers

- `zero_candidate_diagnosis_ready_symbol_drop_reasons_recorded`
