# Options Memory Graph v5 Upgrade Audit - 2026-07-10

## Scope And Authority

This audit records the final options-local memory/control-plane hardening and live schema-v5 rollout. It covers orchestration memory only. It does not authorize trading, evidence mutation, scanner-policy activation, proof or promotion decisions, broker/live-capital action, protected-holdout use, cohort append, or stop/sizing changes.

## Final Schema-v5 Contract

- Backup restore requires declared-present members, exact tenant identity, canonical outbox integrity, and DB/session-sidecar parity; migration, WAL setup/retry, event writes, mirror repair, and backup serialize per DB.
- Session delivery is durable and retry-reconcilable. Observed dream evidence requires reserved trusted-writer attestation plus a durable session/outbox or authoritative artifact source/hash cross-check.
- WORKLOG and DECISIONS class expectations are stable (`episode` and `decision`), and expectation activation is recorded by hash-chained events.
- Ghost graph/retrieval/expectation cleanup is transactional.
- Required freshness always includes canonical `PROJECT_SEED_FILES`, independent of mutable expectation rows.
- Gateboard pathway, blocker, and source-artifact nodes bind to one coherent gateboard byte snapshot. Seed validates and hashes safe `available=true` artifacts as snapshot provenance; `available=false` remains explicitly unavailable and cannot satisfy an available-source expectation.

## Verification

- Agent-control: `119/119` passed.
- Memory graph: `17/17` passed.
- Combined: `136/136`, reproduced from the repository root.

## Live Rollout And Recovery Chain

- Live schema-v5 migration and session repair completed.
- Live transactional ghost repair and bootstrap completed.
- Final living-history ingest/bootstrap completed, and doctor, memory audit, retrieval, operator-dashboard, eval, outbox/mirror/anchor, backup-restore, and dream-audit checks passed.
- Preserved recovery points:
  - copied v3: `data/agent-control/pre-v4-safety/20260708T070051Z-ebd6cf54`
  - post-v4: `data/agent-control/post-v4-safety/20260710T035321Z-e254fd94`
  - repaired-session v4: `data/agent-control/pre-v5-safety/20260710T035321Z-e254fd94-repaired-sessions`
  - verified v5: `data/agent-control/verified-v5-safety/20260710T063210Z-ac899ea5`
  - pre-repair v5: `data/agent-control/backups/20260710T141639Z-ed16ac30`; restore-check passed
- Preserve v4 event-mirror repair provenance at `events-20260710T035315Z-83bdd25613ce-ca01f9a1.jsonl`.

## Final Operational Proof

- Maintenance run `RUN-20260710-c1aae9a5` passed.
- Latest options dream `DREAMRUN-20260710-d64378a5` completed and its dream audit passed.
- The machine-wide dreaming runner pins canonical audit-contract SHA-256 `eb867cc4f8641f5a5085e059f9c6c15c84ade2e4894361bae23e1d53581da0d9`.
- Canonical manual run `PMDREAM-20260710-150315388-4dc9366af849` (sequence 2) completed, followed by scheduled latest `PMDREAM-20260710-150505551-ddd8389b9bee` (sequence 3), also complete.
- `\ProjectsMemoryDreaming`, `\OptionsMemoryDreaming`, and `\OptionsMemoryMaintenance` were observed `Ready` with `LastTaskResult=0`. Options dreaming retains its raised 45-minute execution limit.

## Remaining Nonblocking Debt

- Cache shared living-history source snapshots once per refresh instead of rereading the same source bytes for every referencing node. The current path can approach `O(nodes x source-read)` CPU, but scheduled maintenance still finishes in about six minutes within its 30-minute task limit.
- Extracting `scripts/agent_control/legacy.py` into real domain modules remains maintainability debt.

## Verdict

The schema-v5 implementation, live repair, final history ingest, doctor/recovery surface, and real scheduler proof are complete with named safety points and passing deterministic suites. Remaining work is nonblocking scale and maintainability debt. Memory remains non-authoritative for trading and evidence decisions.
