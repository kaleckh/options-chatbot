# Regular Options Strict Forward 30 Market-Window Collector

Status: `collector_attempts_exhausted_waiting_for_more_rows`.

- Strict completed forward rows: `0/30`.
- Remaining rows: `30`.
- Accepted profitability: `false`.
- Market-window status: `open`.
- Attempt count: `3/3`.
- Sleep seconds: `300.0`.
- Run scan sweep requested: `true`.
- Candidate rows staged: `0`.
- Candidate JSONL exists: `false`.
- Cohort append performed: `false`.
- Latest goal-loop status: `blocked_no_phase2_natural_selections`.
- Latest capture status: `no_phase2_natural_selections_no_append`.
- Latest throughput status: `blocked_no_same_day_phase2_natural_selections`.
- Latest candidate-starvation evidence status: `raw_symbol_drop_reasons_recorded`.
- Latest scheduled Phase 2 drop-count total: `1008`.
- Latest scheduled Phase 2 symbol drop reasons: `992`.
- Latest readiness status: `blocked_stale_readbacks`.
- Latest scan-task health status: `scan_task_runtime_blocked`.
- Latest scan-task health blockers: `["\\OptionsScanPicks:scan_task_runtime_blocking:scan_task_runtime_failed", "\\OptionsScanPicks:scan_task_runtime_last_result_nonzero", "\\OptionsScanPicksSafetyNet:scan_task_runtime_blocking:scan_task_runtime_failed", "\\OptionsScanPicksSafetyNet:scan_task_runtime_last_result_nonzero"]`.
- Safe no-append collector command: `npm run options:goal-loop:strict-forward-30-collector -- --selection-date 2026-07-10 --market-window-confirmed --market-window-status open --run-scan-sweep --max-attempts 3 --sleep-seconds 300 --json`.
- Next action: `keep_bounded_collector_available_for_next_confirmed_open_market_window`.

This collector only repeats the existing strict-forward goal-loop coordinator during a confirmed open market window. It is bounded by `max_attempts`, defaults to no append, and stops on candidate review, guarded append, safety violations, scan failure, or goal completion.

## Attempts

- `1` status=`blocked_no_phase2_natural_selections` strict_rows=`0/30` candidates=`0` append=`false`
- `2` status=`blocked_no_phase2_natural_selections` strict_rows=`0/30` candidates=`0` append=`false`
- `3` status=`blocked_no_phase2_natural_selections` strict_rows=`0/30` candidates=`0` append=`false`
