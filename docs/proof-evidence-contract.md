# Proof Evidence Contract

This is the semantic owner for Trading Desk proof and evidence language. The source contract is `data/contracts/proof-evidence-contract.json`; backend helpers live in `python-backend/proof_contract.py`; the generated frontend policy artifact lives in `src/lib/generated/proofEvidenceContract.ts`; and the human frontend facade lives in `src/lib/trading-desk/proofContract.ts`.

## Canonical Meanings

- `Truth-grade` means a closed row with executable entry, trusted executable exit, calculable P&L, and production-proof evidence group.
- `Production proof` means `proof_class=live_scan_exact_contract`, `proof_eligible=true`, exact contract identity, executable scan entry evidence, OPRA/NBBO source, and verified archived forward-scan lineage.
- `Raw exact` means an exact contract symbol is present. It is not production proof by itself.
- `Realized P&L` can include historical or research rows when entry and exit are trusted executable evidence.
- `Current policy` is product-side replay/operator review, not live-production proof.

Creation-time proof classification and stored-row proof predicates must not trust the proof class string alone. They require exact selection source, source scan session/event/run/timestamp fields, source-scan lineage verification, OPRA source label, executable entry basis, quote timestamp, present acceptable quote freshness, and exact contract symbol. They must reject research/backfill identity markers both on the row and inside source snapshots, including top-level `backfill_audit_id`, `position_migration_id`, and `position_migrated_at_utc`. Closed proof-grade rows, including rows with `closed_at` even if `status` is stale or missing, must also have a trusted executable exit and calculable realized P&L.

Evidence recording health is separate from proof eligibility. A tracked-position create/review/close response can report `position_event_persistence.status=failed` when the row mutation succeeded but the forward-evidence lifecycle event failed to persist. That status is an operational evidence gap, not production proof and not a reason to loosen proof gates.

## Invariant Table

`data/contracts/proof-invariant-cases.json` is the test-only invariant manifest for proof/evidence edge cases. `docs/proof-invariant-table.md` is generated from that manifest by `scripts/generate_proof_invariant_table.py` and is checked by `npm run verify:docs`.

The table is an orientation and regression artifact, not runtime configuration. Backend tests load the same cases to assert raw-exact, production-proof, proof-grade-closed, proof-summary, and profit-metric behavior. Frontend tests load the same cases to assert evidence group, production-proof display, realized-P&L, and Truth-grade filtering behavior.

`data/contracts/proof-replay-golden-readbacks.json` pins aggregate readbacks over the same invariant rows. It is also `runtime_use=false`: a golden regression fixture for `/api/proof-summary` counts, Trading Desk grouped tracked/proof summaries, options-profit realized/candidate metrics, options-profit status overlay counts, and deterministic replay-service readback assembly. It must not be used as proof policy, scanner policy, replay math, or runtime configuration.

## Backend Proof Classes

| Proof class | Meaning | Production proof |
| --- | --- | --- |
| `live_scan_exact_contract` | Verified live scanner row with exact contract, executable entry evidence, trusted OPRA/NBBO source, and verified source scan lineage. | Yes, only when `proof_eligible=true` |
| `manual_broker_exact_contract` | Exact contract identity with manual or broker fill evidence. | No |
| `ineligible` | Missing one or more production-proof gates. | No |

Research/backfill, migrated historical paper, lifecycle-only rows, comparable exact rows, stale `proof_eligible`, midpoint/mark/last/daily/EOD/stale evidence, unresolved candidates, and rows carrying top-level or source-snapshot backfill/migration identity fields are excluded from live-production proof.

## Frontend Evidence Groups

Display precedence is contract knowledge:

1. `lifecycle_only`
2. `historical_paper`
3. `research_backfill`
4. `proof_ineligible`
5. `manual_exact`
6. `live_exact`
7. `legacy_unclassified`

Only `live_exact` is a production-proof display group. Historical paper, research backfill, lifecycle-only, and proof-ineligible rows remain research-learning surfaces. Manual exact rows are visible evidence but not production proof.

## Implementation Anchors

- Creation-time proof classification: `python-backend/positions_service.py`
- Stored-row production-proof predicates: `python-backend/proof_contract.py`
- Proof-summary and grouped tracked summaries: `python-backend/main.py`
- Profit gate and flywheel production metrics: `options_profit_gate.py` and `options_profit_flywheel.py`
- UI projection and closed-view filtering: `src/lib/trading-desk/positionEvidence.ts`
- Contract tests: `tests/test_proof_contract.py`, `tests/test_proof_invariant_cases.py`, `tests/test_golden_proof_replay_readbacks.py`, `tests/trading-desk/proof-invariants.test.js`, and `tests/trading-desk/position-evidence.test.js`
