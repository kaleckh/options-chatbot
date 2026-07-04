# Regular Options Scanner Materializer Parity Diff

This generated readback compares the deterministic materializer chain with scheduled scan-session output. It is diagnostic only and does not run or change the scanner.

## Summary

- Status: `materializer_window_has_no_rows`.
- Window: `2026-06-14` to `2026-07-01`.
- Materializer rows in window: `0`.
- Filter-matched materializer selected rows: `0`.
- Matching scheduled scan-pick rows: `0`.
- Matching scheduled scan-pick rate: `None`.
- Scheduled sessions loaded: `267`.
- Top starvation gate: `None` (`no_starvation_gate_observed`, `0` rows).
- Divergence counts: `{}`.

## Boundary

- Diagnostic only; scan config changes remain forbidden until the frozen-cohort evaluation/refreeze decision.
- Any refreeze or scanner-policy change requires an explicit operator decision.
- This script writes only its own generated report/artifacts and does not import quotes, mutate evidence stores, append cohorts, enable live validation, enable auto-track, submit broker orders, change proof bars, or consume protected holdout.
- Materializer entry window ET: `10:10-10:25`.
- Scheduled session times ET observed: `265` distinct times; sample `["09:36:29", "09:36:35", "09:38:28", "09:38:31", "09:38:38", "09:41:23", "09:44:53", "09:45:10", "09:46:50", "09:47:11", "09:48:52", "09:51:41", "09:53:17", "09:53:45", "09:55:12", "09:55:43", "09:59:13", "10:02:09", "10:06:29", "10:06:32"]`.

## Materializer Coverage

- Total materializer rows loaded: `6916`.
- Earliest materializer date: `2024-06-03`.
- Latest materializer date: `2026-05-29`.
- Current default-window note: Current materializer artifact ends before the default post-freeze window; no rows are invented..

## Daily Divergence Table

| Date | Materializer Rows | Filter-Matched Selected | Scheduled Sessions | Scheduled Picks | Divergences |
|---|---:|---:|---:|---:|---|
| 2026-06-15 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-16 | 0 | 0 | 2 | 1 | `{}` |
| 2026-06-17 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-18 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-22 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-23 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-24 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-25 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-26 | 0 | 0 | 2 | 0 | `{}` |
| 2026-06-29 | 0 | 0 | 83 | 0 | `{}` |
| 2026-06-30 | 0 | 0 | 83 | 0 | `{}` |
| 2026-07-01 | 0 | 0 | 83 | 0 | `{}` |

## Divergence Rows

No divergence rows were classifiable in this window.
