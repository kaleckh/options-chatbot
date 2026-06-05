# Regular Options Operator Workflow

This is the Trading Desk visibility layer for the profitability paper gate. It is an operator readback, not a trade recommendation, scanner promotion, broker action, proof-bar change, auth change, or DB mutation.

## Runtime Surface

- `src/components/predictions/OperatorSessionPanel.tsx`
  - reads `GET /api/operator/session`
  - opens the local HttpOnly operator session through `POST /api/operator/session`
  - clears the typed token after successful unlock
  - refreshes the scanner surface after unlock so stale unauthorized scan state is not left on screen
- `src/components/predictions/PaperGateOperatorPanel.tsx`
  - renders `paper_gate_operator_workflow` from `GET /api/options-profit/status`
  - shows release status, eligible count, pending validation count, no-fill/skipped auto-track count, and current-policy breaker state
  - shows bridge rows with blockers and matched Tier A lanes
  - shows pending-validation and no-fill rows with fill-discipline explanations
- `src/components/predictions/ScannerEvidencePanel.tsx`
  - keeps the paper gate inside `Evidence & guardrails` with the rest of the scanner truth context

## Read Model

`python-backend/main.py` adds `paper_gate_operator_workflow` to the read-only `/api/options-profit/status` payload by reading these artifacts:

- `data/profitability-lab/regular-options-paper-shortlist/latest.json`
- `data/forward-tracking/regular_options_fresh_evidence_loop_latest.json`
- `data/forward-tracking/pending_scan_candidate_validation_latest.json`
- `data/forward-tracking/current_policy_circuit_breaker_latest.json`

If any artifact is missing or unreadable, the readback reports `primary_state=paper_gate_artifacts_missing` and the scanner should be treated as paper-review-only. Missing artifacts must not look like proof readiness.

## Operator Semantics

- `paper_review_candidates_available` means a row is available for supervised paper review only.
- `no_paper_shortlist_candidates` means no fresh executable Tier A bridge candidate is eligible.
- `paper_gate_artifacts_missing` means the readback cannot prove the gate state.
- `paper_gate_invariant_violations` means the paper-shortlist artifact failed its own invariants and must stay paper-review-only.
- no-fill, missing fill-attempt, duplicate, and skipped auto-track states are fill-discipline evidence only.
- promotion discussion still requires fresh executable entry evidence, verified linkage, exact realized OPRA/NBBO exit P&L, and `live_policy_change=false`.

## Verification

Focused checks:

```powershell
uv run --locked python -m unittest tests.test_options_api_e2e.OptionsAlgorithmApiE2ETests.test_options_profit_status_endpoint_overlays_paper_gate_operator_workflow -v
node --test tests\trading-desk\scanner-tab-readability.test.js
npm run verify:typecheck
```

Wider sprint checks should also include `npm run lint`, `npm run verify:docs`, `npm run verify:profitability-paper-gates`, and desktop/mobile browser QA of Archive > Live Scan > Evidence & guardrails.
