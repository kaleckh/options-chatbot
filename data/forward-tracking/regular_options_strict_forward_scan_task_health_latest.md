# Regular Options Strict Forward Scan Task Health

Status: `scan_tasks_ready_for_next_market_window`.

This read-only report verifies the two scheduled scan tasks that feed strict-forward collection. It does not run scans, append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.

## Tasks

### `\OptionsScanPicks`

- Status: `ready`.
- Runtime status: `Ready`.
- Scheduled state: `Enabled`.
- Next run time: `6/29/2026 11:00:00 AM`.
- Last result: `0`.
- Task to run: `C:\Users\kalec\options-chatbot\scripts\run_scan_picks.bat`.
- Start time: `11:00:00 AM`.
- Batch status: `batch_chain_ready`.

### `\OptionsScanPicksSafetyNet`

- Status: `ready`.
- Runtime status: `Ready`.
- Scheduled state: `Enabled`.
- Next run time: `6/29/2026 11:30:00 AM`.
- Last result: `0`.
- Task to run: `C:\Users\kalec\options-chatbot\scripts\run_scan_picks_safety_net.bat`.
- Start time: `11:30:00 AM`.
- Batch status: `batch_chain_ready`.

## Blockers

- None.
