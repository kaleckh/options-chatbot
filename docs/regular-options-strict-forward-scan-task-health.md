# Regular Options Strict Forward Scan Task Health

Status: `scan_task_runtime_blocked`.
Config readiness status: `scan_tasks_config_ready`.
Scan-task runtime telemetry status: `scan_task_runtime_blocked`.

This read-only report verifies the two scheduled scan tasks that feed strict-forward collection. It does not run scans, append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.

## Tasks

### `\OptionsScanPicks`

- Status: `ready`.
- Config status: `ready`.
- Runtime telemetry status: `scan_task_runtime_observed_ok`.
- Runtime status: `Ready`.
- Scheduled state: `Enabled`.
- Next run time: `7/13/2026 11:00:00 AM`.
- Last run time: `7/10/2026 11:00:00 AM`.
- Last result: `0`.
- Number of missed runs: ``.
- Task to run: `C:\Users\kalec\options-chatbot\scripts\run_scan_picks.bat`.
- Start date: `4/22/2026`.
- Start time: `11:00:00 AM`.
- Batch status: `batch_chain_ready`.

### `\OptionsScanPicksSafetyNet`

- Status: `blocked`.
- Config status: `ready`.
- Runtime telemetry status: `scan_task_runtime_failed`.
- Runtime status: `Ready`.
- Scheduled state: `Enabled`.
- Next run time: `7/10/2026 11:30:00 AM`.
- Last run time: `7/9/2026 8:21:36 PM`.
- Last result: `-1073741510`.
- Number of missed runs: ``.
- Task to run: `C:\Users\kalec\options-chatbot\scripts\run_scan_picks_safety_net.bat`.
- Start date: `5/5/2026`.
- Start time: `11:30:00 AM`.
- Batch status: `batch_chain_ready`.

- Blocker: `scan_task_runtime_blocking:scan_task_runtime_failed`.
- Blocker: `scan_task_runtime_last_result_nonzero`.

## Blockers

- `\OptionsScanPicksSafetyNet:scan_task_runtime_blocking:scan_task_runtime_failed`
- `\OptionsScanPicksSafetyNet:scan_task_runtime_last_result_nonzero`

## Runtime Blockers

- `\OptionsScanPicksSafetyNet:scan_task_runtime_blocking:scan_task_runtime_failed`
- `\OptionsScanPicksSafetyNet:scan_task_runtime_last_result_nonzero`
