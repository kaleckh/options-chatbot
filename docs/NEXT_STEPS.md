# Next Steps

Last updated: 2026-07-10

This is the prioritized current-action source of truth. Historical queues are preserved in the verified 2026-07-10 project-memory archive; dedicated owner docs and current generated artifacts remain authoritative for their domains.

## 0. Profitability Operating Objective

Drive the system toward defensible, prospectively verified profitability. Existing lanes may be repaired, replaced, parked, or removed; new lanes may be added. Prefer the path with the strongest causal evidence and realistic deployable economics, not the path that preserves current strategy assumptions.

Near-term execution order:

1. Preserve each audited tranche in Git. Baseline `885b1cf4471a31574820f1d0e19544be48c5d171` and authoritative-verifier `d311f157` are complete; checkpoint the momentum evidence-integrity tranche after final verification.
2. Park momentum continuation after its repaired 340-row sample failed conservative PF robustness (0.92); do not tune on this consumed window.
3. Repair the VRP surface with synchronized 15:55 calls and puts for SPY/QQQ/IWM/DIA across the frozen window, then implement the native denominator/candidate engine; do not infer economics from the valid but nonmatching 10:25 put rows.
4. Allocate research effort to robust positive-expectancy lanes and kill or park falsified lanes quickly.
5. Advance a lane only after executable forward evidence clears its proof and promotion bars.

This objective does not itself authorize broker orders or live-capital deployment. Those actions require current release evidence and separate explicit user authorization.

## 1. Keep Schema-v5 Green And Remove Refresh CPU Debt

Schema v5 is complete and green at 119 agent-control plus 17 memory-graph tests (`136` total), reproduced from the root. Final living-history ingest/bootstrap, doctor, audit, retrieval, operator-dashboard, eval, outbox/mirror/anchor, backup-restore, and dream-audit checks passed. Maintenance `RUN-20260710-c1aae9a5` passed and latest options dream `DREAMRUN-20260710-d64378a5` completed. Global manual sequence 2 `PMDREAM-20260710-150315388-4dc9366af849` and scheduled sequence 3 `PMDREAM-20260710-150505551-ddd8389b9bee` completed under canonical audit-contract SHA-256 `eb867cc4f8641f5a5085e059f9c6c15c84ade2e4894361bae23e1d53581da0d9`. `\ProjectsMemoryDreaming`, `\OptionsMemoryDreaming`, and `\OptionsMemoryMaintenance` each have observed `LastTaskResult=0`; options dreaming retains its 45-minute limit.

Remaining memory debt:

- Cache each shared living-history source snapshot once per refresh instead of rereading the same source for every node. This avoids `O(nodes x source-read)` CPU; it is nonblocking because the current maintenance task still finishes in about six minutes within its 30-minute limit.
- Extract the large `scripts/agent_control/legacy.py` implementation into real domain modules without changing the compatibility CLI or schema semantics.
- `C:\Users\kalec\shopbot` remains intentionally outside the curated 14-project global registry, and the other 71 immediate directories remain only an aggregate boundary warning until explicitly reviewed.

## 2. Maintain Agent-Control Backup Health

Completed through final live v5 validation: the duplicate/conflicting event mirror was archived and rebuilt, sessions and ghosts were repaired, final ingest/doctor passed, a verified-v5 safety copy was retained, and `20260710T141639Z-ed16ac30` passed restore-check. Earlier retention removed 25 redundant bundles and reclaimed 1,737,699,418 bytes while preserving calendar and forensic points. Preserve the named v3/v4/v5 safety chain unless a later explicitly reviewed retention pass establishes an equal or stronger strictly restore-valid replacement.

For future maintenance, run `npm run memory:prune-backups` first. Apply only with the documented acknowledgement after a newest retained bundle fully passes. Calendar-retained and invalid/in-progress directories remain preserved; mirror-degraded deletion is limited to the separate narrow acknowledgement and only the explicitly regenerable mirror-only failure class.

## 3. Keep The Pre-Vacuum Backup

Current blockers:

- `data/options-validation/fresh_window_2018_2021_import.log` does not contain `FRESH_WINDOW_IMPORTS_COMPLETE`.
- `data/options-validation/fresh_window_pipeline.log` does not contain `PIPELINE_COMPLETE`.
- No distinct exact strong-hash replacement backup has been supplied.

Do not delete `data/options-validation/options_history.db.pre_vacuum_backup`. Once imports and the pipeline finish, create an exact verified replacement and rerun the retirement report. Retirement must hold the shared import lock across fresh DB hashes, identity checks, and atomic staged deletion.

## 4. Preserve Raw Import Evidence

The raw import seal currently reconciles 1,257 files (about 4.07 GiB) to import-batch hashes and row counts. This is evidence of ingestion, not authorization to delete. Keep the artifacts until a separate replacement database or immutable replacement archive is created, strongly verified, and explicitly acknowledged.

## 5. Complete Safe Project Cleanup

After all concurrent windows and test processes are idle:

1. Rerun storage dry-run reports.
2. Remove regenerated Python caches and stale rebuildable `.next` output if allowed by age policy.
3. Run a read-only final size audit and record before/after bytes by category.
4. Do not remove `node_modules`, `.venv`, databases, JSONL ledgers, raw import artifacts, or authoritative evidence merely to improve the headline size.

## 6. Options Research And Proof

Current posture is `safe_blocked_no_live_release`.

- Treat `docs/regular-options-main-lane-audit-2026-07-10.md` as the current main-lane audit. The old 2,671-row snapshot is a stale diagnostic record under the repaired-or-explicitly-blocked contract, not current proof output.
- Profile and repair the full historical adapter before rerunning it. The last pre-fix process ran about 9.5 hours without writing an artifact; do not start another unprofiled full run.
- Establish a versioned manifest-bound point-in-time entry/exit quote corpus and per-row earnings/feature lineage, then regenerate the historical population under the repaired denominator contract.
- Implement production scanner, spread-selection, slippage, path-dependent exit, ranking, one-new/two-open allocation, and historical-policy-snapshot parity before interpreting historical economics as production economics.
- Complete the fresh import with provider-exhaustive chain proof, then implement preregistered F2 alignment, frozen top-three selection, formal one-shot validation, and atomic consumption-registry append.
- The non-self-asserted forward-entry verifier is implemented: each completion requires one preceding matched entry bound by exact session/event/run/recorded locator to one authoritative `scan_pick`, verified through a coherent read-only SQLite snapshot with exact metadata, contract, synchronized timestamp, fresh provider, and Decimal price equality. Rows created before locator emission or with unsynchronized legs remain fail-closed; do not backfill them fuzzily.
- Accumulate 30 untouched exact forward completions under the lifecycle/contract/policy/scan-health/signal-lineage/quote-store contract. Current strict forward remains 0/30 and the paper shortlist has zero eligible candidates; implementation of the verifier does not itself establish proof.
- Momentum continuation is parked: trusted batch 3122 expanded it to 340 exact rows and 98.02% quote coverage, but conservative clustered-bootstrap PF LB fell to 0.92 despite raw PF 1.5008. Do not spend the remaining research budget filling seven gaps or tuning stress assumptions unless a separately preregistered fresh hypothesis changes the branch.
- Continue only preregistered research, source repair, paper-shadow capture, and exact evidence collection allowed by current contracts.
- Treat consumed evaluation windows as unavailable for tuning or family selection.
- Keep historical/materializer/tracker rows separate from prospective forward proof.
- Require non-self-asserted, content-revalidated executable bid/ask provenance, timestamps, costs, denominator status, and net USD economics for exact proof.
- Do not change scanner production policy, proof bars, live validation, auto-track, broker behavior, stops, sizing, protected holdout, or promotion without a separate explicit operator decision.
- Read `docs/project-operator-gateboard.md` and its latest JSON before any release or profitability claim.

## 7. Concurrent-Work Discipline

- Inspect locks, processes, file mtimes, and diffs before editing shared control-plane, package, or core memory files.
- If another window resumes writing, stop and work on isolated files or wait.
- Preserve unrelated dirty-worktree changes. Never use destructive Git resets to simplify the tree.

## Verification Ladder

```powershell
uv run --locked ruff check scripts tests
uv run --locked python -m unittest tests.test_manage_project_storage tests.test_manage_project_storage_safety
uv run --locked python -m unittest tests.test_archive_inactive_project_data tests.test_archive_project_memory
uv run --locked python -m unittest tests.test_build_import_artifact_seal tests.test_prune_agent_memory_backups
uv run --locked python -m unittest tests.test_agent_memory_graph tests.test_agent_control
npm run verify:docs
npm run verify:memory
git diff --check
```

Run broader frontend/backend suites only after checking that they will not interfere with active imports, browser sessions, or other audit windows.
