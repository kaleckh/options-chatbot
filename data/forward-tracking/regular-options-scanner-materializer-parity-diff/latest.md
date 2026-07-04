# Regular Options Scanner Materializer Parity Diff

This generated readback compares the deterministic materializer chain with scheduled scan-session output. It is diagnostic only and does not run or change the scanner.

## Summary

- Status: `scanner_materializer_parity_diff_ready`.
- Window: `2026-06-14` to `2026-07-02`.
- Materializer rows in window: `182`.
- Filter-matched materializer selected rows: `0`.
- Matching scheduled scan-pick rows: `0`.
- Matching scheduled scan-pick rate: `None`.
- Scheduled sessions loaded: `344`.
- Top starvation gate: `None` (`no_starvation_gate_observed`, `0` rows).
- Divergence counts: `{"materializer_no_pick_scanner_pick": 1}`.

## Boundary

- Diagnostic only; scan config changes remain forbidden until the frozen-cohort evaluation/refreeze decision.
- Any refreeze or scanner-policy change requires an explicit operator decision.
- This script writes only its own generated report/artifacts and does not import quotes, mutate evidence stores, append cohorts, enable live validation, enable auto-track, submit broker orders, change proof bars, or consume protected holdout.
- Materializer entry window ET: `10:10-10:25`.
- Scheduled session times ET observed: `341` distinct times; sample `["09:36:29", "09:36:35", "09:37:38", "09:38:28", "09:38:31", "09:38:38", "09:40:47", "09:41:23", "09:44:53", "09:45:10", "09:46:50", "09:47:11", "09:48:06", "09:48:52", "09:50:51", "09:51:41", "09:53:17", "09:53:45", "09:55:12", "09:55:43"]`.

## Materializer Coverage

- Total materializer rows loaded: `7280`.
- Earliest materializer date: `2024-06-03`.
- Latest materializer date: `2026-07-02`.
- Current default-window note: n/a.

## Daily Divergence Table

| Date | Materializer Rows | Filter-Matched Selected | Scheduled Sessions | Scheduled Picks | Divergences |
|---|---:|---:|---:|---:|---|
| 2026-06-15 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-16 | 14 | 0 | 2 | 1 | `{"materializer_no_pick_scanner_pick": 1}` |
| 2026-06-17 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-18 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-22 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-23 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-24 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-25 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-26 | 14 | 0 | 2 | 0 | `{}` |
| 2026-06-29 | 14 | 0 | 83 | 0 | `{}` |
| 2026-06-30 | 14 | 0 | 83 | 0 | `{}` |
| 2026-07-01 | 14 | 0 | 83 | 0 | `{}` |
| 2026-07-02 | 14 | 0 | 77 | 0 | `{}` |

## Divergence Rows

| Date | Lane | Symbol | Materializer | Scanner | Class |
|---|---|---|---|---|---|
| 2026-06-16 | volatility_expansion_observation | SPY | not_selected | scanner_pick | `materializer_no_pick_scanner_pick` |
