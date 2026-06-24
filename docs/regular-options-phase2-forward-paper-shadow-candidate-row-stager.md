# Phase 2 Forward Paper-Shadow Candidate Row Stager

This artifact stages append-only candidate rows only. It does not append the cohort log or authorize live trading.

- Status: `no_phase2_natural_selections`.
- Source mode: `scan_picks`.
- Source path: `data/forward-tracking/scan_picks.jsonl`.
- Candidate rows staged: `0`.
- Candidate JSONL written: `false`.
- Cohort append performed: `false`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Rejected counts: `{"non_phase2_lane": 468, "non_preregistered_symbol": 50, "not_current_market_window_selection": 1, "pre_freeze_selection": 31}`.
- Validation: `{}`.

Fresh real-mode rows require a confirmed open market window and same-day natural selections. Fixture mode is the closed-market test path.
