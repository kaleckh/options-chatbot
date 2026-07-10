# Decisions

This live file contains current durable decisions only. The complete pre-compaction decision record is preserved byte-for-byte in the verified 2026-07-10 project-memory archive and remains available to archive-aware living-history retrieval.

## 2026-07-10: Profitability Is The Objective, Not Preservation Of Existing Lanes

Durable decision: operate the options system toward defensible, prospectively verified profitability. The current lane set is not protected product scope: lanes may be repaired, replaced, parked, removed, or added, and supporting scanner, data, evidence, ranking, allocation, exit, and control-plane code may change when the evidence supports the change.

Profitability claims must still clear preregistered, causal, executable-bid/ask, fee-and-slippage-aware, out-of-sample and forward evidence bars. Research freedom does not authorize broker orders, live capital, proof-bar reduction, holdout reuse, or promotion from historical or self-asserted evidence. Optimize for verified expected value and operational deployability rather than preserving a favored hypothesis.

## 2026-07-10: Forward Entry Proof Binds To The Authoritative Ledger

Durable decision: a forward completion may count only when its single preceding matched entry has an exact locator into `forward_tracking_authoritative.db` and content-revalidates against exactly one `scan_pick` event. The scan logger writes the authoritative ledger before any projected scan, fill-attempt, near-miss, or auto-track work and rejects malformed ledger acknowledgements. The tracker verifies all candidates for one report through one read-only SQLite snapshot, caches by immutable locator, requires session/event metadata parity, exact contract/timestamp/Decimal price equality, synchronized legs, and uniformly fresh `alpaca_opra` source lineage. Legacy or ambiguous rows remain fail-closed; no fuzzy backfill is allowed.

Windows Task Scheduler result `0x41301` is an in-progress state when the task status is `Running`, not a failed execution. Health reports may classify that exact pair as nonblocking in-progress; other nonzero results remain blocking.

## 2026-07-10: Regular Options Has No Accepted Profitability Evidence

Durable decision: maintain `safe_blocked_no_live_release`. The defensible conclusion is that the active regular-options lane has no accepted profitability evidence; the closest historical snapshot loses after fees, but absent production scanner, spread-selection, slippage, path-dependent exit, ranking, allocation, and historical-policy parity means it does not prove the production policy has negative expected value or that its opportunity-sum dollars are deployable portfolio P&L.

The 2024-06 through 2026-05 snapshot is selection-conditioned and consumed. It may remain a hashed diagnostic record, but it cannot nominate, tune, validate, or promote a policy. Historical and fresh evaluation must require causal timezone-aware known-at inputs, blocked missing-evidence denominators, exact contract/timestamp continuity, a cryptographically and content-revalidated manifest/database corpus, provider-exhaustive chain proof, and nonzero completed rows. Forward diagnostic entries may be retained, but a completion cannot count or authorize evaluation until its preceding matched entry is content-revalidated against a non-self-asserted quote store/manifest. The named blocker is `entry_quote_store_verification_not_established`; caller-asserted trust labels, booleans, or hashes are not evidence.

Before economic reevaluation, profile the currently impractical full adapter, establish the missing manifest-bound point-in-time corpus, implement production scanner/exit/ranking/allocation replay, complete the preregistered fresh F2/top-three/one-shot registry path, implement the forward entry quote-store verifier, and only then collect untouched exact forward completions. Do not tune on the consumed windows or reinterpret the frozen early-close contract silently.

## 2026-07-10: Schema-v5 Living History And Gateboard Freshness Are Structural

Durable decision: WORKLOG and DECISIONS have stable class expectations (`episode` and `decision`) whose activation is recorded through hash-chained events; expectation rows alone cannot silently redefine them. Ghost graph/retrieval/expectation cleanup is transactional. Schema initialization serializes WAL setup and retries bounded lock contention rather than racing initialization.

Gateboard-derived pathway, blocker, and source-artifact nodes must come from one coherent gateboard byte snapshot. Seed validates and hashes safe artifacts declared `available=true` as snapshot provenance. An `available=false` declaration remains explicitly unavailable: it is not dereferenced or hashed as present and cannot satisfy an available-source freshness expectation.

The live schema-v5 migration, session and ghost repair, final living-history ingest/bootstrap, doctor, audit, retrieval, dashboard, eval, outbox/mirror/anchor checks, backup restore, and dream audit completed green. Preserve `data/agent-control/post-v4-safety/20260710T035321Z-e254fd94`, `data/agent-control/pre-v5-safety/20260710T035321Z-e254fd94-repaired-sessions`, `data/agent-control/verified-v5-safety/20260710T063210Z-ac899ea5`, and pre-ghost-repair bundle `data/agent-control/backups/20260710T141639Z-ed16ac30`; the last bundle passed restore-check. Maintenance `RUN-20260710-c1aae9a5` passed and options dream `DREAMRUN-20260710-d64378a5` completed. Global dreaming manual sequence 2 (`PMDREAM-20260710-150315388-4dc9366af849`) and scheduled sequence 3 (`PMDREAM-20260710-150505551-ddd8389b9bee`) completed under canonical audit-contract SHA-256 `eb867cc4f8641f5a5085e059f9c6c15c84ade2e4894361bae23e1d53581da0d9`. `\ProjectsMemoryDreaming`, `\OptionsMemoryDreaming`, and `\OptionsMemoryMaintenance` each have observed `LastTaskResult=0`; options dreaming retains its 45-minute limit.

Shared living-history source bytes should be cached once per refresh instead of reread for every referencing node. This is nonblocking performance debt: the current behavior can approach `O(nodes x source-read)` CPU, but the observed maintenance task still finishes in about six minutes within its 30-minute limit.

## 2026-07-09: CEO Implementation Authority And Memory Schema v5 Use Separate Gates

Durable decision: an agreed CEO goal grants full direct local implementation authority over the scoped code, tests, docs, scripts, config, control-plane, and strategy/scanner/data workflows. Worker permission/autonomy labels describe dependent task capabilities; they cannot reintroduce a blanket read-only Prime session. Separate current gates still govern evidence mutation, production scanner activation, proof, release, promotion, broker/live-capital action, protected-holdout use, cohort append, and stop/sizing changes. A blocked action gate does not freeze unrelated implementation, and memory cannot expand the agreed scope.

Runtime memory schema v5 keeps tenant ownership structural across tasks and downstream rows and keeps lifecycle, proof-label, and cross-tenant edge checks fail-closed. Restore-check now requires every expected member to be declared present, exact manifest/request tenant identity, and exact DB/session-sidecar ID parity. Current outbox rows use a canonical v2 hash over SQL identity, tenant, timestamp, type, and payload; active mirrors require canonical DB order, while declared legacy v1 bundles remain auditable through a bounded compatibility path. Schema migration, WAL initialization, event writes, mirror repair, and snapshot backup serialize on the same per-DB lock.

Session sidecar delivery is durable and reconcilable after a failed append. Dream acceptance reparses its source, rejects stored/source divergence, and permits observed claims only from same-tenant reviewed evidence with integrity provenance and an allowed kind. A reserved evidence attestation can be minted only by trusted writers and must cross-check the session outbox or authoritative artifact source/hash. Retrieval forces nonauthorization, quarantines raw node/edge action metadata, pathway-filters accepted dream lessons, contains freshness reads to safe repo paths, and always includes canonical `PROJECT_SEED_FILES` freshness independently of mutable expectation rows. These remain correctness and recovery decisions, not trading authority. The completed live rollout and remaining validation are recorded in the 2026-07-10 decision above; extracting `scripts/agent_control/legacy.py` remains architectural debt.

## 2026-07-09: Archive Before Compacting Project Memory

Durable decision: capture the five project-memory files into an immutable dated directory with a canonical manifest, SHA-256 per member, total-size checks, and post-capture verification before reducing live context. Runtime ingestion must combine verified archives with live WORKLOG/DECISIONS under their original logical paths, deduplicate before pruning, retain physical provenance, and fail before DB writes if an archive is invalid. Generic repo indexing must exclude the archive tree.

The live budgets are: PROJECT_CONTEXT 22 KiB, DECISIONS 24 KiB, WORKLOG 10 KiB, NEXT_STEPS 22 KiB, docs index 16 KiB, and 94 KiB total. Historical detail belongs in the archive or dedicated owner artifacts rather than repeated startup files.

## 2026-07-09: Storage Cleanup Must Be Policy-Driven And Fail Closed

Durable decision: project cleanup defaults to dry-run, re-derives plans at apply time, protects tracked and authoritative paths, rejects links/reparse points, stages deletes atomically, checks file identity, and requires an explicit acknowledgement. Timestamp retention is per artifact family and preserves recent, daily, weekly, monthly, referenced, transition, malformed, and safety-milestone evidence.

Logs rotate by atomic rename and compression. Inactive lane data may be removed only after a byte/hash-verified archive exists. Raw import artifacts remain audit-only until a distinct replacement is sealed. Agent-memory pruning requires the newest retained bundle to pass the complete restore-check and preserves all calendar-retained and incomplete bundles. A separate explicit acknowledgement may remove only redundant older bundles whose sole failure is a regenerable event-mirror hash/field/duplicate mismatch while ledger, DB outbox, anchors, manifest, and sidecar gates pass; every other failure remains blocked.

## 2026-07-09: Pre-Vacuum Backup Retirement Requires All Gates

Durable decision: `options_history.db.pre_vacuum_backup` remains protected until all required vacuum markers, fresh-window import completion, downstream pipeline completion, SQLite integrity/table checks, absence or ownership of the shared import lock, and an exact strong-hash replacement backup pass in one apply-time critical section. The retirement tool holds the shared importer lock through verification and deletion. Missing evidence means retain the backup.

## 2026-07-09: Browser Smoke Tests Are Read-Only Product Checks

Durable decision: Playwright smoke tests may verify navigation, keyboard behavior, responsive layout, and serious/critical automated accessibility findings with deterministic GET-only fixtures. They do not validate live backend state, profitability, proof, evidence quality, auth enforcement, orders, or broker state and cannot clear release gates.

## 2026-07-08: Research Mandate Does Not Grant Live Authority

Durable decision: the operator mandate covers bounded research implementation, preregistered contracts, approved research-window source imports, materializers, trackers, adapters, database maintenance, and research tooling. It does not cover live validation, auto-track, broker action, production scanner-policy changes, proof-bar changes, protected-holdout use, or promotion. A profitable result must survive preregistered falsification, executable bid/ask economics, fees, slippage, realistic risk, and out-of-sample discipline; it cannot be manufactured by loosening gates.

## 2026-07-08: Compacted Options Store Keeps Its Recovery Copy

Durable decision: the compacted options-history store may serve as active only after integrity and row-count checks. Its pre-vacuum source copy remains until the follow-on 2018-2021 imports and pipeline finish and a new exact verified backup exists. Import and pipeline failure markers are blockers, not permission to delete recovery evidence.

## 2026-07-07: External Strategy Research Is Literature Context

Durable decision: recovered options-strategy research can rank hypotheses and inform a new preregistered design, but it does not prove current retail profitability. Defined-risk index volatility-risk-premium structures remain a research candidate; event volatility is conditional/cost-sensitive; short-DTE premium selling and directional debit-spread deployment remain unproven. Any follow-up must predefine universe, source, entries/exits, side-aware fills, costs, risk, splits, multiple-testing controls, and kill criteria.

## 2026-07-05: Consumed Windows And Refreeze Boundaries Remain Binding

Durable decision: a consumed evaluation window cannot become a tuning or selection surface. One data-repaired rerun is allowed only where the original evaluation inspected zero usable rows because the fixed input chain was broken, and only with the unchanged frozen contract and gates. Future refreeze/filter-family work remains a separate preregistered research contract; design work does not change the active frozen policy.

## 2026-07-02: Quote Imports Coordinate Through One Shared Lock

Durable decision: all writers to the shared option-history store must coordinate on the same import lock. A fresh-window job, historical job, vacuum, backup retirement, or repair process must fail closed rather than compete with another writer. Approved imports remain bounded to their token, universe, dates, and provenance rules and do not authorize proof, scanner, or promotion changes.

## 2026-07-02: WORKLOG And DECISIONS Are Runtime Retrieval Sources

Durable decision: dated WORKLOG episodes and DECISIONS entries are stable retrieval context with orchestration-only authority. Logical identity is based on logical path, heading, normalized body, parser version, and tenant—not physical archive location. Archive compaction must not mint authority or silently delete graph history.

## 2026-06-29: Memory Maintenance Is Audited And Restore-Checked

Durable decision: routine memory maintenance self-logs, anchors the ledger, creates relocatable in-bundle backups, validates the DB/outbox/event mirror/anchors/JSONL sidecars, and records failure. Locks use ownership tokens and Windows-safe liveness checks. Memory metadata and retrieval are tenant-scoped and sanitize authority, secret-shaped content, and targeted order imperatives.

## Standing Proof Decision

Durable decision: only prospective, policy-qualified, executable evidence can clear options proof gates. Historical simulations, research/backfill rows, stale or indicative quotes, generated dashboards, memory nodes, worker reports, browser checks, and operator notes remain context or evidence records at their declared class. They never authorize trades, broker actions, evidence mutation, live release, or promotion by themselves.
