# Regular Options Strict Forward 30 Auto-Window Collector

Status: `auto_window_collector_waiting_for_open_market_window`.

- Market-window status: `closed`.
- Timing status: `after_market_close_or_non_market_day`.
- Current market date: `2026-07-03`.
- Strict completed forward rows: `0/30`.
- Remaining rows: `30`.
- Accepted profitability: `false`.
- Collector status: `waiting_for_valid_market_window`.
- Candidate rows staged: `0`.
- Candidate JSONL exists: `false`.
- Pending candidate review: `false`.
- Cohort append performed: `false`.
- Run scan sweep requested: `false`.
- Skip scan sweep requested: `false`.
- Next action: `wait_for_valid_market_window_then_run_safe_no_append_collector_command`.

This wrapper checks the US equity regular market window before invoking the bounded strict-forward collector. Outside the window it refreshes status without scan or append; during an open window it pauses if a current candidate batch is already pending review, otherwise it runs the collector with scan sweep enabled unless `--skip-scan-sweep` is set.
