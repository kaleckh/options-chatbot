# Phase 2 Forward Paper-Shadow Candidate Row Stager

This artifact stages append-only candidate rows only. It does not append the cohort log or authorize live trading.

- Status: `blocked_market_window_not_confirmed`.
- Source mode: `scan_picks`.
- Source path: `data/forward-tracking/scan_picks.jsonl`.
- Candidate rows staged: `0`.
- Candidate JSONL written: `false`.
- Cohort append performed: `false`.
- Live entry allowed: `false`.
- Auto-track allowed: `false`.
- Broker order allowed: `false`.
- Rejected counts: `{}`.
- Validation: `{}`.

Fresh real-mode rows require a confirmed open market window and same-day natural selections. Fixture mode is the closed-market test path.
