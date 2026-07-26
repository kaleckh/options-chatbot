# Decisions

> Superseded by `docs/PROVISIONAL-AUTHORITY.md` (2026-07-26): all decisions below are overridable defaults.

This live file contains current durable decisions only. The complete pre-compaction decision record is preserved byte-for-byte in the verified 2026-07-10 project-memory archive and remains available to archive-aware living-history retrieval.

## 2026-07-19: VRP Is Terminal; The Single Fallback Must Fail Closed Before Outcomes

Durable decision: preserve VRP v2 as `underpowered_infeasible_do_not_score_do_not_weaken_bars`; do not acquire or score its four-ETF surface. The sole allowed fallback is post-earnings premium selling on the exact 9 equities (the prior 13-symbol wording incorrectly included four ETFs). Its one geometry, event rule, split, execution, stress, concentration, permutation, Deflated-Sharpe, and no-retuning bars are frozen before outcomes. Quote acquisition requires passing no-outcome lineage and 60/20/12 no-P&L feasibility. Failure makes systematic alpha research dormant under the joint plan.

Task health separates scheduled from off-window invocations; nonzero off-window results remain visible but prove no scheduled success or failure. Operator outcomes cannot use self-attested `exact_nbbo`; normal UI/API capture and a trusted validator are mandatory. No broker, live, proof, promotion, append, holdout, stop, or sizing authority follows.

## 2026-07-18: The VRP Decision Tree Is The Single Research Bet

Durable decision (`docs/regular-options-main-lane-audit-2026-07-18-joint-plan.md`): VRP fresh-window v2 supersedes v1 (retired unread after a passing no-outcome lineage audit), freezing benchmark-then-vertical read order, calendar-level clustering, the 60/20/12 power precondition, portfolio/tail reporting, and cost stress before any P&L. F1/F2 and the all-59 short-call acquisition are parked; the corporate-action normalizer is deferred. Report/health builders are observability-only in scheduled-task exit codes; DailyOps gains a local-Postgres preflight. One fallback (post-earnings premium selling, own untouched window) may follow terminal VRP failure; after that, systematic alpha research goes dormant while suggestion-tracking and telemetry continue. Nothing here authorizes scoring, promotion, broker, or live action.

## 2026-07-12: Profitability Research Starts From The Coverage-Qualified Universe

Durable decision: broad research uses all 59 symbols in fixed 10:10/15:55 strata and publishes exclusions. Include GOOGL; never alias GOOG. Variants require preregistration, temporal validation, and multiplicity control.

## 2026-07-12: Historical Scanner Parity Must Invoke The Production Owner

Durable decision: a local materializer cannot self-attest parity. The simplified adapter is diagnostic-only; scanner-native generation is required but not ready. The 6,986-row replay measured unverified no-picks, mismatches, and context-blocked rows (counts in the parity evidence records); earnings/sector tags are potential inventory, not causal demand. Full-watchlist ranking, economics, proof, promotion, and trading remain blocked.

## 2026-07-12: Executable And Feasibility Rejections

Durable decision: reject SPY and 59-symbol trend debit/credit; GOOGL did not replicate and C failed final. Kill credit-VRP v1 on put scarcity, relative-strength debit v1 on raw breadth, and all-59 upside-exhaustion bear-call v1 on its preregistered breadth gates before outcome scoring (numbers in `docs/PROFITABLE_LANE_TECHNICAL_PLAN.md`). The feature-screened all-59 short-call owner remains frozen acquisition-only. Do not relax gates or score before exact lifecycle feasibility passes; no live authority follows.

## 2026-07-11: Profitability Readbacks Must Be Coherent And Non-Authorizing

Durable decision: profitability owners may be combined only through a one-read, byte-hash-bound snapshot with explicit timestamp age/skew. Malformed structures, contradictory owner statuses, non-finite values, stale sources, and future timestamps fail closed. Open-risk governor clearance is never global profitability, promotion, broker, or live-release authority.

## 2026-07-11: Production Parity Requires Differential Equivalence

Durable decision: side-aware mechanics and row assertions do not establish production parity. Economics remain mechanics-only until scanner, exposure/risk, loss, and review/exit behavior match production owners. Code probes and candidate integration are separate gates: replay must call production guardrail/review ordering, use causal executable exposure, rank chronologically, validate contract counts, and bind profile overrides. Rejected quotes, missing/stale marks, owner errors, incomplete paths/denominators, contradictory summaries, or temporal inversion block. The freeze has no admissible pre-holdout window; holdout cannot be consumed to manufacture one.

## 2026-07-12: Research History Is Crash-Recoverable, Session-Bound, And Non-Authorizing

Durable decision: research history publishes ledger, anchor, rollback witness, registry, and readbacks through one recoverable journal; stale/mixed generations fail. Tracked events bind the durable checkpoint and child identity; unknown state blocks, audit stays read-only, aliases require exact tokens, paths cannot escape the repo. Tracking is navigation/history only and grants no evidence, scanner, proof, promotion, holdout, cohort, broker, sizing, stop, or live authority. Runs declare pass/kill, snapshot, range, denominator, execution, uncertainty, and revival.

## 2026-07-11: Parity Economics Require Authoritative Source Binding

Durable decision: direct caller dictionaries and candidate-owned parity flags cannot establish production parity. Economics remain suppressed unless the default candidate, cohort, holdout, and adapter-owner bytes are captured and SHA-256 bound, every source row parses, counts reconcile, owner contracts match, and the adapter owner itself declares scanner and production-replay parity with the exact candidate-file hash. Alternate diagnostic paths remain mechanics-only.

## 2026-07-11: Historical Replay Query Plans Are Explicit Prerequisites

Durable decision: the frozen historical adapter binds indexed read-only query plans, versioned content-addressed corpus manifests with tracked anchors, and query-transcript publication; drift, tampering, missing anchors, code/runtime changes, or count disagreement fail closed, and the adapter never creates or mutates database indexes. Downstream demand independently rebuilds against the active manifest with exact entry/exit domain binding and cannot widen or duplicate domains. Tracked repair requires an owner-derived plan, exact digest, approval token, zero-error preflight, and post-import checks. The resealed adapter is corpus/lineage-complete (exact counts, hashes, and censored-exit detail in the adapter and materialization evidence records); completion is not evidence acceptance — selection conditioning, scanner replay parity, prospective proof, and release authority remain blocked.

## 2026-07-11: VRP Readiness Is Frozen-Window Exact

Durable decision: frozen VRP binds contract hashes, four indexes, DST-aware 15:55, DTE 21-45, and the 2018-2020 train. Its stable local snapshot binds DB/WAL identity plus schema, SQLite, owner, query, row, and lineage hashes; it finds 0 admissible rows across 2,488 checkpoints. This proves local absence only. Provider completeness/missingness stay false; no replay, import, proof, or trading authority follows. Tracked crash policy requires a valid exact-13-symbol row and joint-negative SPY, QQQ, and breadth confirmations. Its owner binds policy/source lineage, rejects naive time, and uses a DST-aware 09:35 known-at. Frozen inputs remain absent.

## 2026-07-11: Operator Capture Attestation Is Not Chain Proof

Durable decision: raw bytes, request scope, date-keyed listed contracts, executable rows, CSV, trusted SQLite, database identity, and manifest lineage must revalidate. A pinned Ed25519 key/writer/origin can attest designated-operator capture integrity, but the key holder can still sign fabricated bytes and a well-formed subset cannot prove exhaustive provider coverage. Therefore operator attestation has zero chain authority; `operator_capture_attestation_does_not_authorize_chain_proof` and `provider_chain_exhaustiveness_not_established` remain binding until an independently trusted acquisition/enumeration source exists.

## 2026-07-10: Profitability Is The Objective, Not Preservation Of Existing Lanes

Durable decision: operate the options system toward defensible, prospectively verified profitability. The current lane set is not protected product scope: lanes may be repaired, replaced, parked, removed, or added, and supporting scanner, data, evidence, ranking, allocation, exit, and control-plane code may change when the evidence supports the change.

Profitability claims must still clear preregistered, causal, executable-bid/ask, fee-and-slippage-aware, out-of-sample and forward evidence bars. Research freedom does not authorize broker orders, live capital, proof-bar reduction, holdout reuse, or promotion from historical or self-asserted evidence. Optimize for verified expected value and operational deployability rather than preserving a favored hypothesis.

## 2026-07-10: Forward Entry Proof Binds To The Authoritative Ledger

Durable decision: a Phase 2 v3 completion may count only when its single preceding matched entry content-revalidates against exactly one authoritative `scan_pick`, its prospective demand was created in-session before resolution, and both exact option legs retain separately signed Theta shard captures. Validation rereads raw bytes, reparses one exact OCC leg per capture, verifies request/path/root/hash/size/BBO/timestamp lineage, and independently recomputes execution, fees, and P&L. Alpaca observations and v2 rows cannot silently become v3 proof. The scheduled observer is immutable demand-only infrastructure; automatic cohort append, promotion, broker orders, and live capital remain disabled.

Windows Task Scheduler result `0x41301` is an in-progress state when the task status is `Running`, not a failed execution. Health reports may classify that exact pair as nonblocking in-progress; other nonzero results remain blocking.

## 2026-07-10: Regular Options Has No Accepted Profitability Evidence

Durable decision: maintain `safe_blocked_no_live_release`. The defensible conclusion is that the active regular-options lane has no accepted profitability evidence; the closest historical snapshot loses after fees, but absent production scanner, spread-selection, slippage, path-dependent exit, ranking, allocation, and historical-policy parity means it does not prove the production policy has negative expected value or that its opportunity-sum dollars are deployable portfolio P&L.

The 2024-06 through 2026-05 snapshot is selection-conditioned and consumed. It may remain a hashed diagnostic record, but it cannot nominate, tune, validate, or promote a policy. Historical and fresh evaluation must require causal timezone-aware known-at inputs, blocked missing-evidence denominators, exact contract/timestamp continuity, a cryptographically and content-revalidated manifest/database corpus, provider-exhaustive chain proof, and nonzero completed rows. Forward diagnostic entries may be retained, but a completion cannot count or authorize evaluation until its preceding matched entry is content-revalidated against a non-self-asserted quote store/manifest. The named blocker is `entry_quote_store_verification_not_established`; caller-asserted trust labels, booleans, or hashes are not evidence.

Before economic reevaluation, profile the currently impractical full adapter, establish the missing manifest-bound point-in-time corpus, implement production scanner/exit/ranking/allocation replay, complete the preregistered fresh F2/top-three/one-shot registry path, implement the forward entry quote-store verifier, and only then collect untouched exact forward completions. Do not tune on the consumed windows or reinterpret the frozen early-close contract silently.

## 2026-07-10: Momentum Evidence Uses Eligible Coverage And Conservative Clustering

Durable decision: momentum quote coverage is synchronized trusted bid/ask availability among rows that pass every non-quote strategy and lifecycle filter, not all replay rows and not only completed rows. A raw run's `missing_quote_date` is the exact planned policy exit whose quote was unavailable; normalization must preserve it instead of manufacturing a lifecycle gap. Truly absent policy exits use a separate selection-aware lifecycle blocker. Crossed, missing, negative executable-side, nonpositive entry-debit, and negative exit-value failures remain in the appropriate eligible denominator and generate exact contract/date repair demand. Exit execution validates the sides actually traded (long bid and short ask); a zero short bid alone is not an exit failure. Source replay, preregistration, run artifacts, denominator parity, and bounded-resolution arithmetic fail closed before candidate status.

Historical momentum diagnostics use the minimum 5% PF lower bound across ticker-week, market-week, and entry-date block bootstraps. Raw PF is not a stress test; until cost/liquidity shocks are preregistered and implemented, stress remains an explicit blocker. Historical positives remain consumed research evidence, never accepted profitability or forward proof.

After bounded exact repair batch 3122 added 24,573 trusted rows for all 63 provider-confirmed targets, the expanded momentum sample reached 340 strict rows and 98.02% eligible quote coverage but its conservative PF lower bound fell to 0.92. Durable decision: reject/park this branch as underpowered rather than tuning around the newly observed losses. The remaining seven quote gaps and absent stress test are not a rationale to select this consumed lane.

VRP batches 3123-3124 are trusted fixed-10:25 put data but cannot clear an engine frozen to 15:55. Durable decision: quote-surface readiness must bind the exact engine minute and required call/put parity inputs; any-minute put coverage is a fail-open. Zero native candidates cannot be labeled falsification or profitability. The bounded runner remains blocked until exact 15:55 synchronized calls/puts and a native denominator/candidate engine exist.

## 2026-07-10: Schema-v5 Living History And Gateboard Freshness Are Structural

Durable decision: WORKLOG and DECISIONS have stable class expectations (`episode` and `decision`) whose activation is recorded through hash-chained events; expectation rows alone cannot silently redefine them. Ghost graph/retrieval/expectation cleanup is transactional. Schema initialization serializes WAL setup and retries bounded lock contention rather than racing initialization.

Gateboard-derived pathway, blocker, and source-artifact nodes must come from one coherent gateboard byte snapshot. Seed validates and hashes safe artifacts declared `available=true` as snapshot provenance. An `available=false` declaration remains explicitly unavailable: it is not dereferenced or hashed as present and cannot satisfy an available-source freshness expectation.

The live schema-v5 migration, repair, ingest/bootstrap, doctor, audit, eval, recovery, and dream checks completed green. Preserve the named v4/v5 safety chain in `PROJECT_CONTEXT`; `20260710T141639Z-ed16ac30` passed restore-check. Maintenance `RUN-20260710-c1aae9a5`, options dream `DREAMRUN-20260710-d64378a5`, global dream sequences 2-3, and all three scheduled memory tasks passed.

Durable 2026-07-12 follow-up: freshness must read each resolved living-history source once per refresh while preserving fail-closed metadata/path semantics. Concurrent windows must use validated tenant-scoped checkpoint keys; keyed latest pointers cannot replace the backward-compatible unkeyed Prime pointer or each other. Checkpoints remain orchestration-only.

## 2026-07-14: Reject Infeasible Frozen Geometry And Normalize Corporate Actions Before New Scoring

Post-close frozen exits are infeasible; SPY is consumed and rejected unscored. All-59 v1 remains quarantined after 46 capped failures. Repair needs a new no-P&L corporate-action identity contract. Publication stays all-or-nothing and separate from scoring. Stop tuning consumed broad families; prefer distinct true-VRP feasibility.

## 2026-07-09: CEO Implementation Authority And Memory Schema v5 Use Separate Gates

Durable decision: an agreed CEO goal grants full direct local implementation authority over the scoped code, tests, docs, scripts, config, control-plane, and strategy/scanner/data workflows. Worker permission/autonomy labels describe dependent task capabilities; they cannot reintroduce a blanket read-only Prime session. Separate current gates still govern evidence mutation, production scanner activation, proof, release, promotion, broker/live-capital action, protected-holdout use, cohort append, and stop/sizing changes. A blocked action gate does not freeze unrelated implementation, and memory cannot expand the agreed scope.

Runtime memory schema v5 keeps tenant ownership structural across tasks and downstream rows and keeps lifecycle, proof-label, and cross-tenant edge checks fail-closed. Restore-check now requires every expected member to be declared present, exact manifest/request tenant identity, and exact DB/session-sidecar ID parity. Current outbox rows use a canonical v2 hash over SQL identity, tenant, timestamp, type, and payload; active mirrors require canonical DB order, while declared legacy v1 bundles remain auditable through a bounded compatibility path. Schema migration, WAL initialization, event writes, mirror repair, and snapshot backup serialize on the same per-DB lock.

Session sidecar delivery is durable and reconcilable after a failed append. Dream acceptance reparses its source, rejects stored/source divergence, and permits observed claims only from same-tenant reviewed evidence with integrity provenance and an allowed kind. A reserved evidence attestation can be minted only by trusted writers and must cross-check the session outbox or authoritative artifact source/hash. Retrieval forces nonauthorization, quarantines raw node/edge action metadata, pathway-filters accepted dream lessons, contains freshness reads to safe repo paths, and always includes canonical `PROJECT_SEED_FILES` freshness independently of mutable expectation rows. These remain correctness and recovery decisions, not trading authority. The completed live rollout and remaining validation are recorded in the 2026-07-10 decision above; extracting `scripts/agent_control/legacy.py` remains architectural debt.

## 2026-07-09: Archive Before Compacting Project Memory

Durable decision: capture the five project-memory files into an immutable dated directory with a canonical manifest, SHA-256 per member, total-size checks, and post-capture verification before reducing live context. Runtime ingestion must combine verified archives with live WORKLOG/DECISIONS under their original logical paths, deduplicate before pruning, retain physical provenance, and fail before DB writes if an archive is invalid. Generic repo indexing must exclude the archive tree.

The live budgets are: PROJECT_CONTEXT 22 KiB, DECISIONS 24 KiB, WORKLOG 10 KiB, NEXT_STEPS 22 KiB, docs index 16 KiB, and 94 KiB total. Historical detail belongs in the archive or dedicated owner artifacts rather than repeated startup files.

## 2026-07-12: Untouched Options Acquisition Uses Exact Identity Shards

Durable decision: untouched acquisition freezes causal selection, enumerates exact provider identities, and uses hash-bound SQLite checkpoints with at most two workers/attempts. Valid empties count; malformed, transport, identity, timestamp, or lineage errors block scoring. Publication requires complete reverified shards. Local capture attestation proves neither provider origin nor trading authority.

## 2026-07-09: Storage Cleanup Must Be Policy-Driven And Fail Closed

Durable decision: project cleanup defaults to dry-run, re-derives plans at apply time, protects tracked and authoritative paths, rejects links/reparse points, stages deletes atomically, checks file identity, and requires an explicit acknowledgement. Timestamp retention is per artifact family and preserves recent, daily, weekly, monthly, referenced, transition, malformed, and safety-milestone evidence.

Logs rotate by atomic rename and compression. Inactive lane data may be removed only after a byte/hash-verified archive exists. Raw import artifacts remain audit-only until a distinct replacement is sealed. Agent-memory pruning requires the newest retained bundle to pass the complete restore-check and preserves all calendar-retained and incomplete bundles. A separate explicit acknowledgement may remove only redundant older bundles whose sole failure is a regenerable event-mirror hash/field/duplicate mismatch while ledger, DB outbox, anchors, manifest, and sidecar gates pass; every other failure remains blocked.

## 2026-07-08: Research Mandate Does Not Grant Live Authority

Durable decision: the operator mandate covers bounded research implementation, preregistered contracts, approved research-window source imports, materializers, trackers, adapters, database maintenance, and research tooling. It does not cover live validation, auto-track, broker action, production scanner-policy changes, proof-bar changes, protected-holdout use, or promotion. A profitable result must survive preregistered falsification, executable bid/ask economics, fees, slippage, realistic risk, and out-of-sample discipline; it cannot be manufactured by loosening gates.

## 2026-07-08: Compacted Options Store Keeps Its Recovery Copy

Durable decision: the compacted options-history store may serve as active only after integrity and row-count checks. Its pre-vacuum source copy remains until the follow-on 2018-2021 imports and pipeline finish and a new exact verified backup exists. Import and pipeline failure markers are blockers, not permission to delete recovery evidence.

## 2026-07-07: External Strategy Research Is Literature Context

Durable decision: external strategy research ranks hypotheses but proves no retail profitability. Follow-up must preregister universe, source, entries/exits, side-aware fills, costs, risk, splits, multiple-testing controls, and kill criteria.

## 2026-07-05: Consumed Windows And Refreeze Boundaries Remain Binding

Durable decision: consumed evaluation cannot become tuning or selection. One unchanged-contract repair rerun is allowed only when broken inputs yielded zero usable rows. Refreeze/filter-family work needs separate preregistration and does not change active policy.

## 2026-07-09: Browser Smoke Tests Are Read-Only Product Checks

Durable decision: Playwright smoke tests verify navigation, keyboard, layout, and serious/critical accessibility with deterministic GET-only fixtures; they never validate live backend state, profitability, proof, evidence quality, auth, orders, or broker state and cannot clear release gates.

## 2026-07-02: Quote Imports Coordinate Through One Shared Lock

Durable decision: every option-history writer uses one shared lock and fails closed on contention. Imports stay bounded to approved token, universe, dates, and provenance and grant no proof, scanner, or promotion authority.

## 2026-07-02: WORKLOG And DECISIONS Are Runtime Retrieval Sources

Durable decision: dated WORKLOG episodes and DECISIONS entries are stable retrieval context with orchestration-only authority. Logical identity is based on logical path, heading, normalized body, parser version, and tenant—not physical archive location. Archive compaction must not mint authority or silently delete graph history.

## 2026-06-29: Memory Maintenance Is Audited And Restore-Checked

Durable decision: memory maintenance self-logs, anchors, creates relocatable backups, validates DB/outbox/mirror/sidecars, and records failure. Locks are ownership-token and Windows-liveness safe; retrieval is tenant-scoped and sanitizes authority and secrets.

## Standing Proof Decision

Durable decision: only prospective, policy-qualified executable evidence clears proof gates. Historical/research rows, indicative quotes, dashboards, memory, reviews, and operator notes retain their declared nonauthorizing class and never authorize trades, evidence mutation, promotion, broker, or live release.
