# Regular Options Fresh-Window Import Scheduler Health

- Status: `fresh_window_import_scheduler_runtime_blocked`.
- Config status: `fresh_window_import_scheduler_ready`.
- Runtime status: `scheduler_runtime_failed`.
- Task name: `\OptionsFreshWindowThetaDataOPRAImport`.
- Scheduled task state: `Enabled`.
- Windows task state: `Running`.
- Next run time: `7/8/2026 5:30:00 PM`.
- Last run time: `7/7/2026 5:30:00 PM`.
- Last result: `267009`.
- Task to run: `cmd.exe /c "C:\Users\kalec\options-chatbot\scripts\run_fresh_window_thetadata_opra_import.bat"`.

This report verifies the weekday post-close fresh-window quote-import scheduler and wrapper contents. It does not run scanners, append rows, enable live validation, enable auto-track, submit broker orders, change proof bars, or promote lanes.

## Blockers

- `scheduler_runtime_blocking:scheduler_runtime_failed`
