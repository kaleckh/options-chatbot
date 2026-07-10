# Regular Options Main Lane — Independent Review Evidence Packet

Date: 2026-07-09 (America/Denver)

Purpose: compact, source-backed context for an independent second-model review of the regular-options main lane. This packet is diagnostic. It does not authorize trading, broker actions, live validation, promotion, proof-bar changes, or strategy tuning on consumed windows.

## Recovered audit and scope

- Interrupted Codex session: `019f49d5-39a1-7ad0-b3fb-4c93df75bb68` in `C:/Users/kalec/.codex/sessions/2026/07/09/rollout-2026-07-09T20-22-18-019f49d5-39a1-7ad0-b3fb-4c93df75bb68.jsonl`.
- The JSONL ends after a successful command with no final answer, completion marker, exception, or explicit cancellation. The audit was not completed.
- Current audit boundary: local code, derived research artifacts, temp databases, and read-only inspection of the real quote store. No provider import, real DB mutation, protected-holdout use, live-capital action, or broker action.

## Economic observations

The closest historical proxy is not a production scanner replay. It is a deterministic point-in-time materializer over the current 13-symbol frozen cohort, backfilled across 2024-06 through 2026-05.

| Surface | Rows | After-fee average | After-fee PF | Net USD | Decision |
|---|---:|---:|---:|---:|---|
| Broad combined proxy | 2,671 | -5.61% | 0.8564 | -$127,401.60 | Negative |
| Broad train (20 months) | 2,346 | -6.53% | 0.8338 | -$150,135.60 | Negative |
| Broad latest four months | 325 | +1.05% | 1.0281 | +$22,734.00 | Not robust; ticker-week cluster PF 5% LB 0.70 |
| Frozen filtered train | 232 | +10.90% | 1.3864 | +$3,823.80 | Blocked; cluster PF 5% LB 0.89, USD LB 0.73 |
| Frozen filtered latest four months | 57 | +30.21% | 2.4606 | +$14,599.80 | Selection-conditioned and regime-concentrated |

Corrections versus the prior generated reports:

- Prior `avg_pnl_pct` and percent PF used gross returns while labeling the field `net_pnl_pct`; USD fields included commissions. Repaired readers prefer `net_pnl_pct_after_fees`, preserve gross fields separately, and keep legacy compatibility.
- Exact enumeration of all 4^4 month-block resamples gives the broad four-month proxy PF 5% quantile 0.4257 and average-return 5% quantile -28.56%. For the filtered proxy, PF 5% quantile is 0.5503, USD PF 5% quantile 0.7988, and average-return 5% quantile -19.77%.
- The filtered March 2026 cohort has six rows averaging about -100.73% after fees; April supplies most of the apparent gain. All 57 audit rows are calls, and 70.18% occur in the two most populated months.
- The filter search evaluated 162 variants. The audit window was already used for selection, so its positive result is not an unbiased out-of-sample estimate.
- The 13-symbol universe was frozen on 2026-06-14 from a profitability-repair keep list and then backfilled over earlier history. It is a current-definition/post-selection replay, not historical policy snapshots.

## Production-parity observations

- The production `no_write` scanner path returns zero candidates before candidate generation (`no_write_scan_blocks_provider_fetches`). Signatures and historical quote-provider support exist, but an end-to-end production scanner replay does not.
- The repaired chain carries research rows with `research_materializer_safe=true` while keeping `proof_safe=false`, `production_scanner_replay=false`, and nomination/proof blockers.
- Materializer signal differences are material: 568 of 2,399 bullish rows fail the production `ret20 > 2%` gate, including 231 with negative ret20; the production pullback also requires `-4% < ret5 < 0.25%`. Volatility gates and ranking differ as well.
- Nine materialized spreads were below the active $0.30 minimum debit; 393 index spreads exceeded the active 4% width ceiling.
- The historical proxy uses a fixed 75%-of-DTE exit, no active 5%-per-side entry/exit slippage, and no active spread stop/profit/early-exit path. Active equity spread settings are stop 40%, profit 80%, time 55%; index settings are stop 35%, profit 75%, time 55%.
- Repaired artifacts emit structured production-parity mismatches and selection-conditioning blockers. Historical rows remain diagnostic and cannot nominate the active policy.

## Quote, exit, and allocation integrity

- Entry and exit legs now require exact shared full-precision UTC timestamps that map to the same Eastern date/minute; exit pairs require exactly 15:55 ET. Mismatched, fractional-second-different, late, or wrong-date rows are not exact-priced.
- Policy exit dates now use the authoritative US equity calendar. Only targets after the as-of date are right-censored. Missing calendar coverage, missing quotes, non-executable quotes, and missing synchronized pairs are distinct blockers.
- There are 169 same-date/ticker/direction cross-lane collision groups. The old lexicographic rule always retained bullish pullback. Favorable collision choice still leaves the broad sample losing, but no combined portfolio is unbiased without a predeclared allocation policy.
- Robust-search and historical/filtered audits now use the canonical opportunity identity and block combined nomination while reporting collision sensitivity.

## Portfolio realism

- The 2,671 historical opportunities occur on 476 entry dates: mean 5.61/day, median 5, p90 9, max 12; 364 days have more than three entries.
- Up to 188 spreads are simultaneously open. Peak one-contract open debit is about $84,709. Realized opportunity-sum drawdown is $204,617.20 from 2024-07-17 to 2026-04-23.
- The frozen production policy permits one new position/day and two concurrent positions. No production ranking/allocation replay exists, so the -$127,401.60 is an opportunity sum, not deployable portfolio P&L.
- LLY and UNH account for roughly $122k of losses. Excluding them now would be post-hoc tuning, not proof.

## Forward evidence

- Latest strict-forward packet: 0/30 completed exact rows.
- Paper shortlist: 0 eligible candidates.
- Fifty-three scheduled Phase-2 sessions returned zero picks; current evidence is candidate-starved.
- The old tracker trusted completion status/P&L without leg lineage. Repairs now require a preceding trusted matched-entry lifecycle, exact matching contract IDs, trusted intraday entry and exit sources, synchronized leg timestamps, executable side prices, and recomputed fee-adjusted percent/USD P&L.
- Duplicate completion events count once and fail uniqueness; a later trusted recapture supersedes a legacy invalid claim for current criteria while historical rejection diagnostics remain.

## Fresh 2018–2021 evidence lane

- Existing real coverage: 24/96 monthly pass chunks logged, all entry-side 2018-01 through 2019-12; no exit chunks. The January 2020 `4294967295` code was unsigned `-1` after a prior agent forcibly killed the child process, not a natural provider return.
- The first 24 chunks contain 96 missing real symbol/date pairs; 89 are LLY after 2019-08-23. The staged Alpaca minute artifact also has 20 real symbol/date gaps.
- The frozen contract asks for 15:55 ET option quotes on nine early-close sessions. The repaired driver blocks the contract before lock, manifest, provider, or DB mutation and lists the dates. It does not reinterpret the frozen time.
- The resumable manifest now binds exact contract semantics/hash, plan/chunks, resolved DB and full operational schema/index identity, provider request lineage, parsed CSV content/hash, import batch accounting, and exact trusted DB quote rows. All-duplicate and mixed partial retries remain valid.
- Provider timestamps, rights, OCC symbols, DTE/minute/date bounds, and counts fail closed without fabrication/coercion. Locks use owner tokens and preserve foreign replacements.
- Pipeline upstream artifacts are exactly family-train 2018-01-01 through/as-of 2020-06-30. Train diagnostics can use research-materializer readiness while production proof remains blocked.
- The implementation still intentionally lacks F2 execution, top-3 selection, formal one-shot family validation, and consumption-registry append. It reports `validation_pending`, exits blocked/nonzero, and never emits `PIPELINE_COMPLETE`.
- No provider/network/real DB run was resumed. The 105.09-GiB backup remains retained.

## VRP research harness

- Public and CLI entrypoints enforce the exact frozen train window, canonical geometry, fixed VIX thresholds, 10,000 draws, authoritative market-date equality, and exact VIX/crash date identity before DB access.
- Quotes require trusted deterministic dedupe and exact DST-aware requested-time synchronization; entry credit and exit debit must be within vertical-spread bounds.
- Missing daily exits, expiry/assignment, split-end open positions, missing quote surfaces, and missing/invalid regime inputs remain in the denominator and suppress evaluation-wide metrics.
- Metrics are after-fee and include max drawdown, worst month, skew, and excess kurtosis.
- Real scoring remains intentionally blocked because the default regime artifact lacks an explicit point-in-time crash flag/known-at contract and no formal family-validation runner exists.

## Verification evidence

- Accepted core/proof review: 94/94 final core tests plus direct adversarial probes; independent local rerun 88/88 on the main nine modules.
- Forward-lineage reviewer: ACCEPT after wrong-contract, standalone forged-P&L, daily-snapshot, duplicate-event, recapture, timestamp, and DB-pair counterexamples were closed.
- VRP reviewer: ACCEPT; 12 VRP + 6 calendar tests plus Ruff/format/compile.
- Fresh-window reviewer: PASS; independent 117 tests + 23 subtests, 50 focused + 11 subtests, and seven temp-store adversarial probes. Ruff/compile/diff checks pass.
- No live/provider/broker/holdout action was used for these verifications.

## Questions for the independent reviewer

1. Is the conclusion justified: the active production lane has no defensible profitability evidence; its closest historical proxy loses, but the proxy cannot prove production economics because scanner/exit/allocation parity is absent?
2. Do any attached repaired source paths still fail open in a way that could create false profitability, false exact lineage, false contract completion, or validation leakage?
3. Is any proposed next step logically prior to a versioned early-close contract amendment, complete fresh import, preregistered train/top-3/one-shot validation path, production allocation replay, and untouched forward evidence?
