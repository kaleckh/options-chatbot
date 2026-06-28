# Regular Options Strict Forward 30 Goal Loop

Status: `waiting_for_valid_market_window`.

- Strict completed forward rows: `0/30`.
- Remaining rows: `30`.
- Accepted profitability: `false`.
- Market-window status: `unknown`.
- Next window trade date: `2026-06-29`.
- Next window start ET: `2026-06-29T09:30:00-04:00`.
- Safe no-append collection command: `npm run options:goal-loop:strict-forward-30 -- --selection-date 2026-06-29 --market-window-confirmed --market-window-status open --run-scan-sweep --json`.
- Scan sweep started: `false`.
- Scan sweep exit code: `None`.
- Candidate rows staged: `0`.
- Candidate JSONL exists: `false`.
- Cohort append performed: `false`.
- Capture status: `market_window_not_confirmed_no_capture_started`.
- Throughput status: `blocked_no_same_day_phase2_natural_selections`.
- Candidate-starvation evidence status: `stage_counts_only_waiting_for_symbol_drop_reasons`.
- Scheduled Phase 2 drop-count total: `63`.
- Scheduled Phase 2 symbol drop reasons: `0`.
- Readiness status: `market_window_blocked_no_candidate_jsonl`.
- Scan-task health status: `scan_tasks_ready_for_next_market_window`.
- Scan-task health blockers: `[]`.
- Scheduled Phase 2 scan picks: `0`.
- Next action: `wait_for_valid_market_window_then_run_with_--market-window-confirmed_--market-window-status_open_--run-scan-sweep`.

This coordinator preserves the existing proof rules. It does not fabricate rows, lower proof bars, count historical rows as forward proof, submit broker orders, enable live validation, enable auto-track, import quotes, or mutate evidence stores outside the existing guarded append path.
