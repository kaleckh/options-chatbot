# Scanner Creation Safety Contract

This is the semantic owner for scanner-origin row creation. The source contract is `data/contracts/scanner-creation-safety-contract.json`.

## Canonical Meanings

- `Scanner-origin creation` means `creation_mode=scanner` for `POST /api/positions` or `POST /api/suggested-trades`.
- `Scheduled auto-track` means `scripts/log_scan_picks.py` creates or confirms a tracked position from a market-hours scan.
- `Pending validation` means `scripts/validate_pending_scan_candidates.py` reruns queued regular candidates during a live quote window before any row can be created.
- `Manual paper` and `manual broker` modes are explicit non-scanner creation modes. They may store research, backfill, manual, or broker rows, but they do not bypass proof/evidence rules.

## Canonical Scanner Stage Map

The machine-readable stage list is `scannerPipelineStages` in `data/contracts/scanner-creation-safety-contract.json`. These stages are descriptive boundaries over current behavior; they do not add public API response fields.

| Stage | Owner | Key emitted fields |
| --- | --- | --- |
| `playbook_resolution` | `supervised_scan.get_scan_playbook` | `playbook`, `playbooks`, `data_readiness`, `truth_lane` |
| `raw_candidate_generation` | `supervised_scan.run_supervised_scan` | `candidate_count` |
| `scan_drop_diagnostics` | `supervised_scan.run_supervised_scan` | `scan_drop_reasons`, `scan_funnel.drop_counts` |
| `policy_gate` | `supervised_scan.run_supervised_scan` | `policy`, `policy_error`, `policy_fail_closed`, `playbook_exit_audit`, `playbook_exit_audit_error` |
| `policy_filter` | `supervised_scan.apply_trade_policy_to_scan` | `policy_decision_counts`, `scan_funnel.policy_counts` |
| `guardrail_annotation` | `supervised_scan.apply_playbook_guardrails` | `guardrail_decision_counts`, `exposure_snapshot`, `guardrail_decision`, `portfolio_caps_enforced`, `creation_eligible`, `creation_blockers` |
| `managed_selection` | `supervised_scan.run_supervised_scan` | `picks`, `watch_picks`, `ranked_picks`, `candidate_audit_picks`, `managed_lane_status` |
| `payload_assembly` | `supervised_scan.run_supervised_scan` | `scan_funnel`, `candidate_count`, `returned_count` |
| `forward_lineage_capture` | `python-backend/main.py` | `source_scan_session_id`, `source_scan_event_key`, `source_scan_run_id`, `source_scan_recorded_at_utc` |
| `proof_classification` | `python-backend/positions_service.py` | `proof_class`, `proof_eligible`, `proof_ineligibility_reason` |
| `creation_or_validation_disposition` | `python-backend/main.py`, `scripts/validate_pending_scan_candidates.py` | `position_id`, `auto_track_outcome`, `candidates[].outcome`, `summary.outcome_counts` |

Stage ownership matters. `supervised_scan.py` can make a pick visible, guardrail-annotated, and creation-eligible, but it does not create rows or classify final proof. Scanner-origin row creation still requires forward lineage verification, current guardrail rerun, and proof-eligible payload construction.

## Hard Rules

Scanner-origin creates must fail closed unless all of these are true:

1. The submitted source pick verifies against archived forward-scan lineage.
2. The submitted source pick has `portfolio_caps_enforced=true`.
3. The submitted source pick has `creation_eligible=true`.
4. The submitted source pick has no `creation_blockers`.
5. A current guardrail rerun with caps enabled returns a non-blocked pick.
6. The current rerun pick still has `portfolio_caps_enforced=true`.
7. The current rerun pick still has `creation_eligible=true`.
8. The current rerun pick still has no `creation_blockers`.
9. The final payload is proof-eligible under `docs/proof-evidence-contract.md`.

Scheduled auto-track must fail closed unless all of these are true:

1. `OPTIONS_SCAN_AUTO_TRACK` is enabled.
2. `market_open_at_run` is exactly `true`.
3. The playbook metadata resolves to `position_tracking_mode=auto_track`.
4. `exposure_snapshot.available` is exactly `true`.
5. `exposure_snapshot.portfolio_caps_enforced` is exactly `true`.
6. The pick has `creation_eligible=true`, no `creation_blockers`, and is not guardrail-blocked.

Unknown market-open state, missing exposure state, caps-off scans, unavailable exposure, diagnostic-only lanes, blocked guardrails, unpriced/fallback execution labels, and proof-ineligible rows are not creation events. They remain diagnostics or validation dispositions.

AI commodity uses the separate proof scope `ai_commodity_separate`; its generated isolation owner is `docs/ai-commodity-isolation.md`. The `ai_commodity_infra_observation` playbook must keep `position_tracking_mode=disabled`, `scan_playbook_allows_auto_track(...) == false`, and `fresh_live_validation_enabled=false`, so visible AI commodity scan diagnostics do not become Trading Desk auto-track or scanner-origin creation events.

## Lineage Mutation Guard

Scanner-origin creates compare the submitted `scan_pick` against the archived forward-scan pick event before any row is created. The comparison protects the lineage IDs, contract identity, execution price and basis, source/proof labels, and guardrail creation flags; mutating any protected source field makes the create fail with `source_scan_lineage_unverified`. `tests/test_tracked_positions_api.py` and `tests/test_suggested_trades_api.py` cover route-level tamper rejection for tracked and suggested creates, while `tests/test_options_api_e2e.py` keeps one full scan-to-create mutation smoke test.

## Implementation Anchors

- Playbook metadata and per-pick `creation_eligible` / `creation_blockers`: `supervised_scan.py`
- Scanner-origin route validation: `python-backend/main.py`
- Proof-eligible payload creation: `python-backend/positions_service.py`
- Scheduled auto-track gate and fill-attempt audit rows: `scripts/log_scan_picks.py`
- Pending candidate queue and disposition report: `scripts/pending_audit_candidates.py`
- Market-hours validation runner: `scripts/validate_pending_scan_candidates.py`
- Browser and API types: `src/lib/types.ts`
- Contract tests: `tests/test_scanner_creation_contract.py`, `tests/test_tracked_positions_api.py`, `tests/test_suggested_trades_api.py`, `tests/test_log_scan_picks.py`, and `tests/test_daily_all_lanes_audit.py`

## Disposition Outcomes

Every validation-attempted pending candidate should end in one of the contract outcomes:

- `created`
- `duplicate`
- `blocked`
- `no_longer_matched`
- `paper_only`
- `proof_ineligible`

This keeps selected candidates visible even when they cannot become tracked positions.
