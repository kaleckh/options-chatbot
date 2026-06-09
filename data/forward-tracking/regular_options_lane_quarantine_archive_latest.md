# Regular Options Lane Quarantine Archive

This report is generated from `scripts/build_regular_options_lane_quarantine_archive.py`. It is a read-only archive for lanes the monthly command center has already classified as `quarantine` from trusted exact outcome economics.

## Summary

- Status: `lane_quarantine_archive_readback`.
- Overall status: `lane_quarantines_archived`.
- Archived quarantine lanes: `4` / `4`.
- Archived lane IDs: `["bullish_momentum", "bullish_pullback_observation", "short_term", "swing"]`.
- Live policy change: `false`.

## Archived Lanes

| Lane | Reason | Priced | PF | Avg Net | Promotion State | Source Decision | Next Step |
|---|---|---:|---:|---:|---|---|---|
| swing | negative_sufficient_sample_lane | 49 | 0.3 | -14.31 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| short_term | negative_sufficient_sample_lane | 54 | 0.28 | -18.93 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| bullish_pullback_observation | severe_negative_average_pnl | 15 | 0.29 | -22.81 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |
| bullish_momentum | severe_negative_average_pnl | 16 | 0.1 | -48.45 | diagnostic | diagnostic_only_until_earn_back | keep diagnostic/no-chase and require earn-back or a frozen entry-time retest |

## Boundary

This archive is read-only. It does not delete or disable lanes, create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote quarantined lanes.

