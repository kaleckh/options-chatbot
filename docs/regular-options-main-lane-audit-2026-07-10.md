# Regular Options Main Lane Audit — Final

Date: 2026-07-10 (America/Denver)

## Executive Verdict

The main regular-options lane is **not ready for profitability acceptance, promotion, live validation, auto-track, broker-paper execution, or live capital**. The current `safe_blocked_no_live_release` posture is correct.

The strongest defensible economic statement is:

> The active production lane has no defensible profitability evidence. Its closest historical proxy loses, but that proxy cannot prove production economics because scanner, exit, ranking, and allocation parity are absent.

The audit does **not** establish that the active production policy has negative expected value. It establishes that no current evidence path supports a positive expected-value claim and that the closest available proxy is negative, selection-conditioned, operationally unrealistic, and now stale under the repaired-or-explicitly-blocked lineage contract.

| Area | Final verdict | Meaning |
| --- | --- | --- |
| Existing historical economics | Negative diagnostic snapshot | After-fee opportunity-sum economics lose, but are not production portfolio P&L. |
| Historical proof readiness | Rejected / fail-closed | The repaired adapter now blocks where point-in-time, quote-corpus, and production-parity evidence is missing. |
| Strict forward evidence | Rejected / hard-blocked and incomplete | `0/30` completed exact rows; exact entry quote-store verification is not established; no eligible paper shortlist. |
| Fresh 2018–2021 pipeline | Rejected / diagnostic only | Manifest and fail-closed controls are repaired, but provider-exhaustive chain proof and the formal validation path do not exist. |
| VRP research harness | Rejected for evaluation today | Exact lineage controls are repaired; the real manifest remains absent/incomplete and chain completeness is not established. |
| Trading/release action | Prohibited | No broker, live, promotion, proof-bar, holdout, or scanner-policy action is justified. |

## Recovered Session And Audit Boundary

The interrupted Codex session was recovered at:

`C:/Users/kalec/.codex/sessions/2026/07/09/rollout-2026-07-09T20-22-18-019f49d5-39a1-7ad0-b3fb-4c93df75bb68.jsonl`

Session ID: `019f49d5-39a1-7ad0-b3fb-4c93df75bb68`.

The JSONL ends after a successful command. It contains no final answer, completion marker, exception, or explicit cancellation, so the exact UI/process reason for the prior closure cannot be established from the durable record.

This resumed audit used local source, generated research artifacts, temporary stores, and read-only inspection of the real options store. It did not resume the provider import, mutate the real quote database, consume protected holdout, append a cohort, change production scanner policy, lower proof bars, promote a lane, or perform broker/live-capital action.

## Existing Historical Snapshot

The closest historical proxy is the deterministic point-in-time materializer over the current 13-symbol cohort, backfilled across 2024-06 through 2026-05. It is not an end-to-end production scanner replay.

The independently recomputed snapshot source was:

- `selected_candidates.jsonl` SHA-256: `2f7279906521511445edb26752804a7c31dd47723e8ae5c10dec18a199d66e72`
- `latest.json` SHA-256: `9e4167e9870b0af8eccced928314d123cc95e74aa2f57a5378b696a591f80b0a`
- `latest.json` last modified: `2026-07-07T21:38:00.6367874Z`

After canonical same-date/ticker/direction dedupe, 2,840 raw exact rows become 2,671 opportunities; 169 cross-lane collisions are removed.

| Snapshot | Rows | Average after-fee return | After-fee percent PF | Net USD | USD PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broad combined | 2,671 | -5.61% | 0.8564 | -$127,401.60 | 0.7361 |
| Broad train, first 20 months | 2,346 | -6.53% | 0.8338 | -$150,135.60 | 0.6603 |
| Broad latest four months | 325 | +1.05% | 1.0281 | +$22,734.00 | 1.5574 |
| Frozen filtered train | 232 | +10.90% | 1.3864 | +$3,823.80 | 1.2218 |
| Frozen filtered latest four months | 57 | +30.21% | 2.4606 | +$14,599.80 | 4.2739 |

The prior generated percentage fields used gross returns while being labeled as net. The audit repaired downstream readers to prefer `net_pnl_pct_after_fees`, retained explicit gross fields, and preserved legacy compatibility. The USD fields were already fee-adjusted.

The positive recent and filtered observations do not clear robustness or independence:

- The broad latest-four-month ticker-week cluster PF 5% lower bound is 0.70.
- Exact enumeration of the four observed months with replacement gives broad PF 5% quantile 0.4257 and average-return 5% quantile -28.56%.
- The filtered equivalent gives percent PF 5% quantile 0.5503, USD PF 5% quantile 0.7988, and average-return 5% quantile -19.77%.
- The filter search evaluated 162 variants and used the reported audit window during selection. The result is not unbiased out-of-sample evidence.
- All 57 filtered audit rows are calls. The two most populated months contain 70.18% of rows.
- March 2026 contains six rows averaging -100.73% after fees; April supplies most of the apparent gain.
- Fifteen of the 24 broad months are negative.
- The 13-symbol universe was frozen on 2026-06-14 from a profitability-repair keep list, then backfilled over earlier history. It is a current-definition/post-selection replay, not historical policy snapshots.

Loss concentration is material but cannot be repaired post hoc: LLY contributes -$86,283.40, UNH -$35,965.00, XOM -$13,618.00, and COP -$11,618.20. Removing them after observing outcomes would be tuning, not proof.

## Portfolio And Production-Parity Limits

The historical dollar total is an opportunity sum, not a deployable portfolio result:

- 476 entry dates, mean 5.61 opportunities/day, median 5, p90 9, maximum 12.
- 364 dates have more than three entries.
- Maximum simultaneous open spreads: 188.
- Peak one-contract open debit: approximately $84,709.
- Realized opportunity-sum drawdown: $204,617.20 from 2024-07-17 through 2026-04-23.
- Frozen production limits are one new position/day and two concurrent positions.

No production ranking/allocation replay exists.

Other material parity gaps remain:

- Production `no_write` scanning short-circuits before candidate generation with `no_write_scan_blocks_provider_fetches`; signatures and historical provider support do not constitute an end-to-end replay.
- The materializer signal and ranking rules differ from production. In the existing snapshot, 568 of 2,399 bullish rows fail production `ret20 > 2%`, including 231 with negative ret20.
- Nine materialized spreads fall below the active $0.30 minimum debit; 393 index spreads exceed the active 4% width ceiling.
- The proxy uses a fixed 75%-of-DTE exit and omits active 5%-per-side entry/exit slippage and path-dependent stop/profit/early exits.
- Active equity spread settings are stop 40%, profit 80%, time 55%; index settings are stop 35%, profit 75%, time 55%.
- Cross-lane collision resolution lacks a predeclared production allocation rule.

The repaired one-date, full-frozen-universe no-write smoke completed in 2.6 seconds without writes and returned `blocked_historical_frozen_scanner_replay_adapter`. The inspected SPY row had `proof_safe=false`, `research_materializer_safe=false`, and explicit missing point-in-time entry/chain/scanner inputs. Report-level blockers included `manifest_bound_quote_corpus_not_established`, `production_policy_parity_not_established`, and `end_to_end_no_write_scanner_replay_unavailable`.

## Source-Level Fail-Open Defects And Repairs

An independent GPT-5.5 Pro Oracle review accepted the narrow economic conclusion but rejected proof readiness. Every reported HIST, FWD, and FRESH defect was reproduced locally. The resulting defects were repaired or converted into explicit fail-closed blockers. VRP defects were reproduced locally; the first VRP lineage repair was independently rejected and then strengthened.

### Historical adapter

- `HIST-1`: feature `known_at` is now strict timezone-aware UTC, must be no later than the actual decision, and duplicate symbol/date feature lineage blocks instead of overwriting.
- `HIST-2`: missing trusted quotes, missing requested-window quotes, and missing synchronized pairs are blocked denominator states, not accepted `explicit_no_pick` rows.
- `HIST-3`: earnings gating uses the actual candidate decision timestamp, so a same-day event known before the scan cannot be ignored by a midnight comparison.
- `HIST-4`: selection uses the earliest synchronized causal surface. A separate exact-10:10 mode exists for the frozen fresh contract; the diagnostic 10:10–10:25 mode remains explicitly non-manifest-bound and proof-blocked.

The old readiness fixture was intentionally downgraded because nine symbols lacked per-row quote evidence. Code was not weakened to preserve the old assertion.

### Forward tracker and capture

- `FWD-1/2`: generic timestamps are no longer copied into both legs. Entry and exit legs require explicit, timezone-aware, full-precision equality at the required event time; naive and seconds-mismatched rows reject. Exact entry quote-store/manifest verification is still absent, so diagnostic matched entries and raw completion claims may remain visible, but proof-valid completion counting, profitability metrics, and evaluation are hard-blocked by `entry_quote_store_verification_not_established`. Caller-supplied booleans, hashes, and trusted-source labels cannot bypass that blocker.
- `FWD-3`: completion requires the authoritative policy exit date, a valid market day, exit after entry, and exit no later than expiry.
- `FWD-4`: candidate ID reuse cannot change ticker, direction, lane, expiry, DTE, policy, contracts, or spread geometry.
- `FWD-5`: OCC symbols, root/right/expiry/strike geometry, executable quotes, and debit/exit-value bounds are validated.
- `FWD-6`: scan-task health, artifact hash, point-in-time signal lineage, and normalized tracking-start UTC ordering are gating inputs rather than disclosures.

### Fresh 2018–2021 import/evaluation pipeline

- `FRESH-1`: CSV/database validation is exact in both directions per chunk. A full manifest-corpus row-set hash/equality check rejects any extra trusted executable row in the plan window, including adjacent-minute 10:11 rows. Duplicate-only and mixed retries remain content-valid.
- `FRESH-2`: unproved provider chain completeness is `diagnostic_only_incomplete_quote_surface`. Metrics and events are explicitly diagnostic, and selection/evaluation/acceptance flags remain false. The pipeline stops before downstream selection/validation.
- `FRESH-3`: missing close-time metadata is a named preflight blocker. A post-repair independent review found and fixed one remaining ordering bug: the driver now returns `database_identity.status=not_checked_preflight_blocked` before database identity, coverage, manifest, lock, HTTP session, or provider activity. The permanent tripwire makes `_database_identity` raise if called.

Manifest schema is version 3. The chain standard is `regular_options_provider_chain_completeness_v1`.

### VRP research harness

- `VRP-1`: exact 15:55 synchronization requires full aware timestamps equal to `15:55:00`; seconds/fractional mismatches reject.
- `VRP-2`: exit quotes must use the exact entry contract symbols and matching strike geometry.
- `VRP-3`: public evaluation no longer accepts caller-supplied normalized trust/hash fields. It loads and hashes the import manifest, checks the versioned chain standard, rebuilds the fresh plan, revalidates the complete manifest against the selected database, recomputes full corpus equality, derives batch IDs only from that revalidated manifest, and validates batch accounting before quote queries. Fabricated normalized and structurally self-asserted manifests produce no IDs/readiness.
- `VRP-4`: quote dedupe partitions by contract symbol; ambiguous same-strike series block rather than silently overwrite.
- `VRP-5`: zero completed trades produces `zero_completed_trades`, suppresses metrics, and cannot be evaluation-ready.

The current real path remains blocked because the fresh manifest/chain is absent or incomplete. The repair makes the success path evidence-bound; it does not manufacture that missing evidence.

## Current Forward And Fresh Evidence

Current readbacks remain empty or blocked:

- Strict-forward review packet: 0 rows collected, 30 remaining; status `candidate_review_waiting_for_scheduler_health`.
- Filtered forward evidence bar: 0 completed rows, 0 calendar months, 0 ticker-week clusters. A post-repair no-write readback returned proof blocker and bar status `entry_quote_store_verification_not_established`; evaluation remained false and no report or evidence-store write occurred. Current scan-task-health blockers also keep the tracker-level status blocked.
- Paper shortlist: 0 eligible candidates; release gate `no_paper_shortlist_candidates`.
- Fifty-three scheduled Phase-2 sessions produced zero picks.

The existing real fresh import is incomplete:

- 24/96 pass chunks recorded, all entry-side 2018–2019; no exit chunks.
- 3,962,313 rows across 24 recorded batches.
- 96 real symbol/date gaps in those chunks; 89 are LLY after 2019-08-23.
- The staged underlying-minute artifact has 20 real symbol/date gaps.
- The frozen contract requests 15:55 quotes on nine known early-close sessions; it is blocked rather than silently reinterpreted.
- F2 execution, frozen top-three selection, formal one-shot family validation, and atomic consumption-registry append are not implemented.

The 39.71-GiB active options database and 105.09-GiB pre-vacuum backup were not mutated. The backup remains required. Free C: space at final inspection was approximately 155.17 GiB.

## Verification

Final verification after the FWD-1 residual repair:

- Root integrated matrix: `168/168` across 13 historical adapter/generation/audit, forward tracker/Phase 1–2, fresh recovery/importer, VRP, and market-calendar modules.
- Post-repair forward tracker/Phase 1–2 matrix: `35/35`, including a fabricated allowlisted entry with self-asserted verification booleans and hashes that remains ineligible for completion/evaluation. Positive-path tests inject temporary ready scan-health artifacts; the same matrix passed while the mutable workspace artifact was `scan_task_runtime_blocked`, so scheduler refreshes no longer determine the result.
- Fresh owner matrix: `128 passed + 28 subtests`; focused `55 + 13`; high-risk probes `7 + 2`.
- Final FRESH/VRP post-ordering-fix set: `61 passed + 20 subtests`.
- VRP: `14/14`; fabricated manifest/binding probes fail closed.
- Earlier full-scope Ruff lint passed all 29 selected audit source/test files. After the residual repair, Ruff lint, Ruff format check, `py_compile`, and scoped `git diff --check` all passed on the three touched forward files; only expected LF-to-CRLF working-copy warnings were emitted.
- Final one-date historical no-write smoke: passed, blocked as designed, no artifact write.
- Final forward tracker no-write readback: 0 completed, evaluation false, exact entry quote-store proof blocker present, report write false, evidence-store mutation false.

No provider, network, real quote-database, broker, live, promotion, or protected-holdout action was used.

## Aborted Stale Regeneration

The pre-final full historical regeneration started at 2026-07-09 22:38:57 America/Denver. After approximately 9 hours 28 minutes it remained CPU-active, had consumed about 21,152 CPU seconds, and had not changed the `latest.json` artifact. During that run, the source contract changed materially through accepted HIST/FWD repairs, so any eventual output would have been stale and could have overwritten `latest` with pre-fix semantics.

The exact read-only process tree was terminated at 2026-07-10 08:07 America/Denver. The existing artifact timestamp and hash remained unchanged. This is an operational audit finding: the full adapter path requires profiling/query batching or indexing before a repaired full-corpus regeneration is attempted.

## Required Order Before Economic Reevaluation

1. Profile and repair the full historical adapter's runtime before another full regeneration.
2. Establish versioned, manifest-bound point-in-time entry/exit quote corpus and per-row earnings/feature lineage for the requested historical population.
3. Implement an end-to-end production scanner replay with production signals, spread selection, slippage, path-dependent exits, ranking, one-new/two-open allocation, and historical policy snapshots.
4. Complete the fresh provider import under an amended/versioned early-close-compatible contract and prove provider-exhaustive chain completeness.
5. Implement and preregister F2 time alignment, frozen top-three selection, one-shot validation, and consumption-registry append.
6. Implement a non-self-asserted verifier that content-revalidates each preceding matched entry against an exact, versioned quote store/manifest; keep `entry_quote_store_verification_not_established` in force until it passes.
7. Only then accumulate 30 untouched exact forward completions under the lifecycle, policy, scan-health, signal-lineage, contract, and quote-store contract.
8. Recompute economics only from the repaired population. Do not tune on the consumed 2024–2026 windows or reinterpret the old -$127,401.60 as production portfolio P&L.

Until those dependencies clear, maintain `safe_blocked_no_live_release`.
