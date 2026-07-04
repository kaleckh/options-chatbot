# Regular Options Strict Forward 30 Market-Window Collector

Status: `waiting_for_valid_market_window`.

- Strict completed forward rows: `0/30`.
- Remaining rows: `30`.
- Accepted profitability: `false`.
- Market-window status: `closed`.
- Attempt count: `1/3`.
- Sleep seconds: `300.0`.
- Run scan sweep requested: `false`.
- Candidate rows staged: `0`.
- Candidate JSONL exists: `false`.
- Cohort append performed: `false`.
- Latest goal-loop status: `waiting_for_valid_market_window`.
- Latest capture status: `market_window_not_confirmed_no_capture_started`.
- Latest throughput status: `blocked_no_same_day_phase2_natural_selections`.
- Latest candidate-starvation evidence status: `raw_symbol_drop_reasons_recorded`.
- Latest scheduled Phase 2 drop-count total: `2398`.
- Latest scheduled Phase 2 symbol drop reasons: `2398`.
- Latest readiness status: `blocked_stale_readbacks`.
- Latest scan-task health status: `scan_tasks_ready_for_next_market_window`.
- Latest scan-task health blockers: `[]`.
- Safe no-append collector command: `npm run options:goal-loop:strict-forward-30-collector -- --selection-date 2026-07-06 --market-window-confirmed --market-window-status open --run-scan-sweep --max-attempts 3 --sleep-seconds 300 --json`.
- Next action: `wait_for_valid_market_window_then_run_safe_no_append_collector_command`.

This collector only repeats the existing strict-forward goal-loop coordinator during a confirmed open market window. It is bounded by `max_attempts`, defaults to no append, and stops on candidate review, guarded append, safety violations, scan failure, or goal completion.

## Attempts

- `1` status=`waiting_for_valid_market_window` strict_rows=`0/30` candidates=`0` append=`false`
