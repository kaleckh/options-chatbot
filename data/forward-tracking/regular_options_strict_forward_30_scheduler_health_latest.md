# Regular Options Strict Forward 30 Scheduler Health

Status: `scheduler_runtime_blocked`.
Config readiness status: `scheduler_ready_for_next_market_window`.
Scheduler runtime telemetry status: `scheduler_runtime_failed`.

- Task name: `\OptionsStrictForward30Collector`.
- Scheduled task state: `Enabled`.
- Windows task state: `Running`.
- Next run time: `7/6/2026 7:35:00 AM`.
- Last run time: `7/3/2026 2:05:01 PM`.
- Last result: `267009`.
- Number of missed runs: ``.
- Task to run: `C:\Users\kalec\options-chatbot\scripts\run_strict_forward_30_auto_window_collector.bat`.
- Repeat every: `0 Hour(s), 30 Minute(s)`.
- Repeat duration: `6 Hour(s), 30 Minute(s)`.
- Execution time limit: `00:45:00`.
- Batch file status: `batch_chain_ready`.

This health report verifies scheduler configuration and the strict-forward batch wrapper contents. It does not append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.

## Blockers

- `scheduler_runtime_blocking:scheduler_runtime_failed`

## Runtime Blockers

- `scheduler_runtime_last_result_nonzero`
