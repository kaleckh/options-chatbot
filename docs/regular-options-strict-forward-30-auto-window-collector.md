# Regular Options Strict Forward 30 Auto-Window Collector

Status: `auto_window_collector_ran_open_window`.

- Market-window status: `open`.
- Timing status: `market_window_open`.
- Current market date: `2026-07-10`.
- Strict completed forward rows: `0/30`.
- Remaining rows: `30`.
- Accepted profitability: `false`.
- Collector status: `collector_attempts_exhausted_waiting_for_more_rows`.
- Candidate rows staged: `0`.
- Candidate JSONL exists: `false`.
- Pending candidate review: `false`.
- Cohort append performed: `false`.
- Run scan sweep requested: `true`.
- Skip scan sweep requested: `false`.
- Next action: `keep_bounded_collector_available_for_next_confirmed_open_market_window`.

This wrapper checks the US equity regular market window before invoking the bounded strict-forward collector. Outside the window it refreshes status without scan or append; during an open window it pauses if a current candidate batch is already pending review, otherwise it runs the collector with scan sweep enabled unless `--skip-scan-sweep` is set.
