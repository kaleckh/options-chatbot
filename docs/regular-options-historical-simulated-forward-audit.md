# Regular Options Historical Simulated Forward Audit

This report is generated from `scripts/build_regular_options_historical_simulated_forward_audit.py`. It tests whether the current selected exact historical trade source can support an explicit calendar split: calibration on the prior months and a latest-month historical simulated-forward audit. It is read-only and does not create trades, mutate evidence stores, consume protected holdout, or treat historical rows as fresh forward proof.

## Summary

- Status: `blocked_historical_simulated_forward_audit`.
- Requested split: `20` train months + `4` simulated-forward audit months.
- Selected exact history: `24` months, `2671` accepted exact rows after source-quality scope.
- Dedupe: `2840` rows before dedupe, `2671` rows after dedupe, `169` duplicates removed.
- Calendar months available for split: `24` via `source_calendar_coverage_not_proven`.
- Available selected months: `2024-06, 2024-07, 2024-08, 2024-09, 2024-10, 2024-11, 2024-12, 2025-01, 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04, 2026-05`.
- Train months used: `2024-06, 2024-07, 2024-08, 2024-09, 2024-10, 2024-11, 2024-12, 2025-01, 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01`.
- Audit months used: `2026-02, 2026-03, 2026-04, 2026-05`.
- Sufficient months for requested split: `True`.
- Quote-history shared dates: `1061` through `2026-07-02`.
- Candidate materialization basis: `deterministic_local_pit_candidate_materializer_v1`.
- Scanner parity: `False`.
- Production scanner replay: `False`.

## Metrics

| Window | Months | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% | Cluster Confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Combined | 24 | 2671 | 759 | -4.47 | 0.8837 | 0.82 | 0.77 | -127401.6 | 0.7361 | 0.61 | `negative_or_flat` |
| Train | 20 | 2346 | 666 | -5.36 | 0.8614 | 0.79 | 0.74 | -150135.6 | 0.6603 | 0.54 | `negative_or_flat` |
| Simulated forward audit | 4 | 325 | 93 | 1.94 | 1.0524 | 0.86 | 0.72 | 22734.0 | 1.5574 | 1.02 | `negative_or_flat` |

## Audit Months

| Month | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD Cluster PF LB 5% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `2026-02` | 102 | 29 | -24.8 | 0.4829 | 0.33 | 0.23 | -15991.2 | 0.1 |
| `2026-03` | 69 | 22 | -39.38 | 0.2789 | 0.16 | 0.09 | -8528.4 | 0.06 |
| `2026-04` | 112 | 34 | 37.82 | 2.5755 | 1.8 | 1.39 | 35146.8 | 3.56 |
| `2026-05` | 42 | 16 | 39.09 | 3.4288 | 1.9 | 1.66 | 12106.8 | 2.27 |

## Blockers

- `audit_bootstrap_pf_lb_not_above_1`
- `candidate_generation_months_23_below_requested_24`
- `missing_daily_candidate_generation_diagnostics`
- `missing_lane_specific_point_in_time_feature_inputs`

## Boundary

This audit can falsify or support historical robustness. It cannot by itself satisfy fresh forward profitability acceptance because it uses historical selected rows and percent P&L, not post-freeze exact realized USD P&L rows.

