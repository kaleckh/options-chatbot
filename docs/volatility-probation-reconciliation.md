# Volatility Probation Reconciliation

This report is generated from `scripts/build_volatility_probation_reconciliation.py`. It reconciles the volatility lane's current paper/probation state against legacy live-validation rows, fresh-evidence rows, and open-risk blockers without creating trades or changing policy.

## Summary

- Status: `paper_probation_blocked`.
- Lane: `volatility_expansion_observation`.
- Lane promotion state: `paper_probation`.
- Lane candidate status: `pending_paper_exact_evidence`.
- Context counts: `{"legacy_pre_promotion_state_gate": 6, "no_lane_promotion_state_payload": 3}`.
- Legacy pre-promotion rows: `6`.
- Current paper exact pending rows: `0`.
- Promotion-ready excluding legacy: `0`.
- Open-risk governor: `open_risk_governor_blocked`.
- Open-risk blockers: `["live_exact_negative_open_risk"]`.
- Live exact negative ids: `[537]`.
- Live policy change: `False`.

## Prohibited Actions

- do_not_count_legacy_pre_promotion_rows_as_current_paper_proof
- do_not_run_live_validation_for_paper_probation_candidates
- do_not_create_scanner_origin_rows_until_open_risk_governor_passes

## Reconciliation Rows

| Date | Ticker | Status | Context | Outcome | Entry | P&L | Bridge | Position | Ready |
|---|---|---|---|---|---|---|---|---:|---|
| 2026-06-04 | QQQ | live_validation_attempted | legacy_pre_promotion_state_gate | proof_ineligible | fresh_executable_exact_entry | no_position_link | not_evidence_bridge_candidate |  | False |
| 2026-06-04 | QQQ | live_validation_attempted | legacy_pre_promotion_state_gate | no_longer_matched | fill_attempt_missing | no_position_link | non_executable_entry_blocked |  | False |
| 2026-06-04 | SPY | live_validation_attempted | legacy_pre_promotion_state_gate | no_longer_matched | fill_attempt_missing | no_position_link | non_executable_entry_blocked |  | False |
| 2026-06-04 | SPY | live_validation_attempted | legacy_pre_promotion_state_gate | proof_ineligible | fresh_executable_exact_entry | no_position_link | not_evidence_bridge_candidate |  | False |
| 2026-06-05 | QQQ | live_validation_attempted | legacy_pre_promotion_state_gate | created | fresh_executable_exact_entry | missing_realized_pnl | exact_exit_pnl_required | 537 | False |
| 2026-06-05 | QQQ | live_validation_attempted | legacy_pre_promotion_state_gate | no_longer_matched | fill_attempt_missing | no_position_link | non_executable_entry_blocked |  | False |
| 2026-06-05 | SPY | diagnostic_only_lane_profitability_gate | no_lane_promotion_state_payload | diagnostic_only | fill_attempt_missing | no_position_link | non_executable_entry_blocked |  | False |
| 2026-06-05 | SPY | paper_validation_only_lane_profitability_gate | no_lane_promotion_state_payload | paper_only | fill_attempt_missing | no_position_link | paper_probation_exact_entry_required |  | False |
| 2026-06-05 | SPY | paper_validation_only_lane_profitability_gate | no_lane_promotion_state_payload | paper_only | fill_attempt_missing | no_position_link | paper_probation_exact_entry_required |  | False |
