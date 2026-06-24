# Regular Options Historical Simulated Forward Audit

This report is generated from `scripts/build_regular_options_historical_simulated_forward_audit.py`. It tests whether the current selected exact historical trade source can support an explicit calendar split: calibration on the prior months and a latest-month historical simulated-forward audit. It is read-only and does not create trades, mutate evidence stores, consume protected holdout, or treat historical rows as fresh forward proof.

## Summary

- Status: `blocked_historical_simulated_forward_audit`.
- Requested split: `20` train months + `4` simulated-forward audit months.
- Selected exact history: `0` months, `0` accepted exact rows after source-quality scope.
- Calendar months available for split: `0` via `selected_row_months_only`.
- Available selected months: `none`.
- Train months used: `none`.
- Audit months used: `none`.
- Sufficient months for requested split: `False`.
- Quote-history shared dates: `505` through `2026-06-04`.

## Metrics

| Window | Months | Rows | Avg % | PF | PF LB 5% | Confidence |
|---|---:|---:|---:|---:|---:|---|
| Combined | 0 | 0 | None | None | None | `negative_or_flat` |
| Train | 0 | 0 | None | None | None | `negative_or_flat` |
| Simulated forward audit | 0 | 0 | None | None | None | `negative_or_flat` |

## Audit Months

| Month | Rows | Avg % | PF | PF LB 5% |
|---|---:|---:|---:|---:|

## Blockers

- `audit_avg_pnl_not_positive`
- `audit_bootstrap_pf_lb_not_above_1`
- `audit_calendar_months_0_below_4`
- `audit_exact_trades_0_below_30`
- `candidate_generation_months_0_below_requested_24`
- `missing_daily_candidate_generation_diagnostics`
- `missing_historical_scanner_point_in_time_inputs`
- `missing_historical_scanner_replay_adapter`
- `selected_trade_months_0_below_required_24`
- `train_calendar_months_0_below_20`

## Boundary

This audit can falsify or support historical robustness. It cannot by itself satisfy fresh forward profitability acceptance because it uses historical selected rows and percent P&L, not post-freeze exact realized USD P&L rows.

