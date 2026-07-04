# Audit Remediation Plan — 2026-07-01

Manually maintained working plan. Derived from the 2026-07-01 external audit of the regular-options main lane, the 20+4 month historical simulated-forward audit chain, and the agent-control memory graph. Each phase is a separate reviewable checkpoint: implement one phase, stop, request code review, then continue.

Three independent tracks:
- **Track A — Forward-sim/statistics (Phases 0–7)**: complete as of 2026-07-02 (Phase 0 ThetaData entitlement resolved 2026-07-02: Options STANDARD confirmed, probe healthy).
- **Track B — Memory graph (Phases 8–11)**: Phases 8–10 complete as of 2026-07-02 (episodes 34→816, decisions 4→201, edges 209→2,770, freshness flags live). Phase 11 optional, not started.
- **Track C — Forward-experiment completion (Phases 12–15)**: Phases 12–14 complete as of 2026-07-02 (exit-completion path + bar evaluator live at 0/30; parity diff built but data-blocked until the materializer advances past 2026-05-29; parked-branch ledger + archive done). Phase 15 not started — 15.1 contract must be committed before the 2022–2024 import. The scoped 59-symbol recent-window import is running as of 2026-07-02.

## Context For A Fresh Agent (read this first)

Repo: this repository (`options-chatbot`). Python scripts run with `uv run --locked python ...`. Tests live in `tests/` and run with `uv run --locked python -m unittest tests.<module>`. Generated research artifacts follow the pattern: script writes `data/.../latest.json` + timestamped copies + a generated doc under `docs/`. Read `AGENTS.md` and `docs/index.md` before editing.

The audited chain (all read-only research, all currently green on their own tests):

1. `scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py` — materializes deterministic point-in-time candidates for the frozen 13-symbol surface; side-aware entry (`long_ask - short_bid`) at 10:10–10:25 ET, side-aware exit (`long_bid - short_ask`) at ≥15:55 ET on the 75%-of-DTE day, `pnl_pct` percent-of-debit.
2. `scripts/build_regular_options_historical_simulated_forward_audit.py` — splits selected exact rows into 20 train + 4 audit months (`_split_months`), gates on i.i.d. bootstrap PF lower bound.
3. `scripts/build_regular_options_historical_profitability_filter_iteration.py` — generates 162 candidate filters from train rows, but the acceptance gate ALSO requires audit-window success and ranks accepted filters by audit PF LB.
4. `scripts/build_regular_options_historical_filtered_simulated_forward_audit.py` — recomputes metrics for `accepted_filters[0]` from the latest iteration artifact.
5. `scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py` — matches prospective scan-pick rows (`data/scan_picks.jsonl` area) against the filter conditions read from the latest filtered-audit artifact.
6. `scripts/run_daily_ops.py` (`npm run daily-ops`) re-runs 2–5 every day.

Audit findings this plan remediates:

- F1 (critical): the 4 audit months (2026-02..05) were consumed by selection — 1 of 162 filters survived a gate that requires audit-window success; reported audit PF 2.47 / PF-LB 1.54 is upward-biased. Train-best filters scored audit LB ~0.0–0.6.
- F2 (critical): winner is fragile (top-9 neighbor fails train; train edge is 10 positive / 9 negative months; IWM lost in train but led the audit).
- F3 (major): 65 audit rows ≈ 21 ticker-weeks of overlapping correlated call spreads; i.i.d. bootstrap overstates confidence; cross-lane same-ticker-same-day duplicate rows are not deduped in filter metrics.
- F4 (major): audit-window success is regime-concentrated (48/65 rows in the Apr–May 2026 rally; March rows near −100%; no stop policy).
- F5 (defect): the "frozen" filter is not pinned — daily-ops re-derives it; a month rollover slides `_split_months`, re-selection can silently swap the filter under the running paper-shadow tracker.
- F6 (major, operational): forward evidence collection is starved (0/30 strict rows, tracker 0 evaluated rows, ThetaData entitlement 403) and the production scanner is not parity with the materializer (different entry times/gates).
- F7 (minor): percent-only PF gates, no per-contract fees, optimistic `max(0, ...)` exit clamp undocumented.
- F8 (minor): `docs/current-state.md` stale (2026-05-31); stray `tmp8zf11ul3/` in repo root; uncommitted modified artifacts under `data/forward-tracking/`.

## Non-Negotiable Boundaries (apply to every phase)

- Do NOT change scanner policy, stops, sizing, proof bars, lane promotion, live validation, auto-track, or broker behavior.
- Do NOT import quotes, mutate `options_history.db` / `chat_history.db` / Postgres, or consume the protected forward holdout.
- Keep `accepted_profitability=false` and `historical_rows_are_forward_proof=false` in every touched artifact.
- If a metrics change (fees, dedupe, block bootstrap) causes the currently accepted filter to FAIL its gates, that is an acceptable and expected outcome. Do not re-tune thresholds, add filters, or search again to make it pass. Report the new numbers honestly.
- Every phase: update/extend the matching test module in `tests/`, run it, then run `npm run verify:docs` if any doc under `docs/` changed, and update `docs/WORKLOG.md` with a dated entry.

---

## Phase 0 — Operator Actions (human, not agent; can run in parallel)

These are Kale's tasks; agents cannot do them but should not be blocked by them.

- [ ] Fix the ThetaData options entitlement: the 59-symbol OPRA import resume reports `blocked_thetadata_options_entitlement` (HTTP 403 while the terminal banner shows `Options: FREE`). Log into the ThetaData account, confirm the options data subscription tier, re-enter credentials in the local ThetaTerminal, then verify with:
  `npm run options:source-repair:59-symbol-thetadata-opra-import-resume`
- [ ] Decide the forward evidence bar (Phase 6 pre-registers it; default proposal: 30 completed forward paper-shadow rows with block-bootstrap PF-LB > 1.0 and positive net USD).

---

## Phase 1 — Pin The Frozen Filter (F5) — URGENT, do first

The month rollover (2026-06 data landing now) can silently swap the filter under the tracker. This phase makes the policy an explicit, hash-verified contract.

### 1.1 New freeze script

Create `scripts/freeze_regular_options_filtered_policy.py`:

- Reads the current filtered-audit artifact (`data/profitability-lab/regular-options-historical-filtered-simulated-forward-audit/latest.json`).
- Requires an explicit operator token flag (follow the existing tokened-importer convention, e.g. `--freeze-token freeze_filtered_policy_v1`); refuses to run without it.
- Writes `data/contracts/regular-options-frozen-filtered-policy-v1.json` containing:
  - `policy_id` (e.g. `historical_filtered_candidate_policy_v1`), `frozen_at_utc`
  - the exact `filter_id`, `description`, `conditions` array (copied verbatim)
  - `conditions_sha256` = SHA-256 of the canonical JSON (`json.dumps(conditions, sort_keys=True, separators=(",", ":"))`)
  - provenance: source artifact path + its SHA-256, iteration artifact path + SHA-256, train/audit months at freeze time
  - `tracking_start_at_utc` = `2026-06-30T05:03:45Z` (the tracker's existing stable start)
  - the usual boundary flags (`accepted_profitability=false`, etc.)
- Refuses to overwrite an existing contract unless `--refreeze-token` is supplied with a new version suffix (refreeze creates `-v2`, never mutates v1).

### 1.2 Tracker consumes the contract, fail-closed

Edit `scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py`:

- Add `--policy-contract` (default `data/contracts/regular-options-frozen-filtered-policy-v1.json`).
- In `build_report`: load the contract; if missing → blocker `frozen_filtered_policy_contract_missing`; if present, use the contract's `conditions` as the ONLY matching source (stop reading conditions from the filtered-audit artifact for matching).
- Verify `conditions_sha256` recomputes correctly; on mismatch → blocker `frozen_filtered_policy_hash_mismatch`, status blocked, match nothing.
- Compare against the live filtered-audit artifact's `filter_source.conditions`: if they now differ, DO NOT block, but emit `policy_drift_status = "latest_filtered_audit_diverged_from_frozen_contract"` in the report so drift is visible.
- `tracking_start_at_utc` comes from the contract, not from previous artifacts (keep previous-artifact fallback only when the contract lacks it).

### 1.3 Tests + freeze execution

- Extend `tests/test_regular_options_filtered_forward_paper_shadow_tracker.py`: contract missing → blocked; hash mismatch → blocked; drift → active with drift status; happy path matches with contract conditions.
- Add `tests/test_freeze_regular_options_filtered_policy.py`: no token → refuses; writes expected schema; refuses overwrite.
- Run the freeze once for real (with token), then rerun the tracker and confirm `status=filtered_forward_paper_shadow_tracking_active` with the contract as source.
- Add npm scripts: `options:freeze:filtered-policy`, and update the tracker's npm script if flags changed.

### Checkpoint 1 review criteria

- Contract file exists, hash verifies, tracker fails closed on tampering (demonstrate by test, not by editing the real contract).
- daily-ops rerun cannot change what the tracker matches. Prove it: temporarily point the tracker at a doctored filtered-audit fixture in a test and show matching is unchanged.
- No scanner/proof/promotion surfaces touched. `docs/WORKLOG.md` updated.

---

## Phase 2 — Stop Re-Selection On Consumed Audit Windows (F1 structural part)

Prevent future silent leakage when `_split_months` slides.

### 2.1 Window-consumption registry

- Create `data/contracts/regular-options-audit-window-consumption-registry.json` (manually seeded by this phase) recording: window months `2026-02..2026-05`, consumed by `regular_options_historical_profitability_filter_iteration` on the selection date, candidate count 162, accepted filter id.
- Edit `scripts/build_regular_options_historical_profitability_filter_iteration.py`:
  - Load the registry. If the computed audit months overlap ANY consumed window, the run may still compute diagnostics, but: `status = "blocked_audit_window_already_consumed_for_selection"`, `accepted_filters = []`, and a top-level `selection_permitted = false`.
  - New audit windows (fully disjoint months) may select; on any run where `accepted_filter_count > 0` and selection was permitted, append that window to the registry (guarded by `--record-consumption` flag so tests don't mutate it; daily-ops passes the flag).
- Edit `scripts/build_regular_options_historical_filtered_simulated_forward_audit.py`: when the iteration artifact reports `selection_permitted=false`, fall back to recomputing metrics for the FROZEN contract filter (Phase 1 contract) instead of `accepted_filters[0]`, and label `filter_source_mode="frozen_contract"`. This keeps the daily readback meaningful without re-selection.
- Edit `scripts/run_daily_ops.py` only as needed to pass flags; do not remove steps.

### 2.2 Tests

- Iteration: overlapping window → blocked status, empty accepted list; disjoint window fixture → selection permitted.
- Filtered audit: iteration blocked → uses frozen contract, still recomputes metrics deterministically.

### Checkpoint 2 review criteria

- Running the iteration today (audit months 2026-02..05 or any slide that overlaps them) produces `selection_permitted=false` and cannot mint a new accepted filter.
- daily-ops completes 22/22 steps with the new statuses (run `npm run daily-ops` and attach the summary).
- Registry append is token/flag-guarded and covered by a test.

---

## Phase 3 — Statistics Hardening: Block Bootstrap + Dedupe (F3)

### 3.1 Cluster-aware bootstrap

Edit `scripts/evaluate_regular_options_autoresearch.py`:

- Add `block_bootstrap_confidence_for_values(entries, *, branch_id, draws)` where `entries` is a list of `(cluster_key, value)`. Resample CLUSTERS with replacement (same number of clusters per draw), concatenate their values, compute PF/avg per draw, return the same shape as `bootstrap_confidence_for_values` plus `cluster_count`, `method="cluster_block_bootstrap"`. Keep the existing function untouched (other callers depend on it).
- Cluster key policy for this chain: `f"{ticker}:{iso_year}-W{iso_week:02d}"` from `entry_date`. Document why in the docstring (overlapping multi-week holds; consecutive-day re-entries).

### 3.2 Dedupe in the filter chain

In `build_regular_options_historical_profitability_filter_iteration.py` and the filtered audit:

- After `_accepted_rows`, apply strict dedupe on `(entry_date, ticker, direction)` keeping the first row by `(lane_id, long_contract_symbol)` sort order (deterministic). Emit `deduped_row_count` and `duplicate_rows_removed` in the artifact. (Expected: ~12 duplicates removed from the 306 filtered rows; the raw 2851-row base will also shrink slightly.)

### 3.3 Apply to gates

- In `_metrics` for both scripts, compute BOTH the existing i.i.d. bootstrap (keep for comparability, rename key to `bootstrap_iid`) and the cluster bootstrap (`bootstrap_cluster`). All PASS/FAIL gates (`MIN_PF_LB` checks) switch to the CLUSTER lower bound.
- Update `scripts/build_regular_options_historical_simulated_forward_audit.py` the same way for its audit-months gate.
- Update the generated markdown tables to show both LBs.

### 3.4 Tests

- Unit test the cluster bootstrap: single cluster → degenerate (LB ≈ point); many identical independent clusters → close to i.i.d.; synthetic correlated clusters → cluster LB < i.i.d. LB.
- Extend the three chain test modules for the new artifact keys and dedupe counts.

### Checkpoint 3 review criteria

- Recomputed real artifacts attached to the review: expect the winner's audit cluster-LB to drop materially below 1.54 (predicted effective N ≈ 21 clusters). If it now fails gates, statuses must flip to blocked — do not soften gates.
- No change to `bootstrap_confidence_for_values` behavior for existing callers (run `npm run verify:python:research` or at least the modules importing it).

---

## Phase 4 — Economics Hardening: Net USD + Fees + Exit-Clamp Labeling (F7)

### 4.1 Adapter emits USD economics

Edit `scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py` (`_attach_exit_pnl` and the entry-row builder):

- Add per-row: `contract_multiplier=100`, `fee_per_contract_leg_usd` (default `0.65`, override via `--fee-per-contract-leg`), `total_fees_usd = 4 * fee` (2 legs open + 2 legs close; expiry-settled rows: 2 legs open only — but this adapter always closes at the 75%-DTE exit, so 4), `gross_pnl_usd = (exit_value - entry_debit) * 100`, `net_pnl_usd = gross_pnl_usd - total_fees_usd`.
- Add `exit_value_floored_at_zero: bool` set when `long_bid - short_ask < 0` was clamped; keep the clamp but make it visible. Emit a count of floored rows in the run summary.
- Do NOT change `pnl_pct` semantics (downstream compatibility); add `net_pnl_pct_after_fees` as a separate field.
- Note: regenerating `selected_candidates.jsonl` requires the adapter chain rerun (`npm run daily-ops` covers it). Rows are derived from the local trusted store; this is not a quote import.

### 4.2 Gates use USD alongside percent

- In the filter iteration + filtered audit + broad audit `_metrics`: add `net_pnl_usd` sums, USD profit factor, and cluster-bootstrap LB over per-cluster USD values. Acceptance gates now require BOTH: percent cluster PF-LB > 1 AND USD cluster PF-LB > 1 AND total `net_pnl_usd > 0`.

### 4.3 Tests

- Fixture rows with known bid/ask → assert exact fee math, USD PF, floored-exit flag.

### Checkpoint 4 review criteria

- One regenerated real run attached: USD metrics present on every exact row; floored-row count reported; gate statuses recomputed honestly.
- `net_pnl_pct` unchanged for existing rows (spot-check 3 rows against prior artifact).

---

## Phase 5 — Reporting Honesty: Selection-Bias Labeling (F1/F2/F4 presentation)

No math changes; make the artifacts tell the truth about what the numbers mean.

- Filter iteration artifact + markdown: add a `selection_bias_disclosure` block stating: candidate count searched (162), acceptance gate includes audit-window success, ranking is audit-first, and therefore accepted-filter audit metrics are upward-biased maxima, not unbiased out-of-sample estimates. Include the empirical inversion note (train-best filters failed audit).
- Filtered audit artifact + markdown: rename the headline confidence for the audit window from `confident_positive` to `selection_conditioned_positive` whenever the filter came from an audit-gated selection (i.e., always for v1), and surface regime concentration: rows per audit month, share of rows in best 2 months, direction mix. Add blocker-style WARNING (non-blocking) `audit_rows_regime_concentrated` when >60% of audit rows fall in 2 of 4 months.
- Update `docs/current-state.md` (stale at 2026-05-31): refresh the validation snapshot section to reflect the filtered-audit chain, the frozen contract (Phase 1), the consumption registry (Phase 2), and the corrected statistical framing. Follow the freshness checklist in `docs/index.md` (`npm run verify:docs` must pass).
- Update `docs/regular-options-historical-profitability-filter-iteration.md` and `docs/regular-options-historical-filtered-simulated-forward-audit.md` via their generators (never hand-edit generated docs).

### Checkpoint 5 review criteria

- Generated docs regenerate cleanly from scripts; `npm run verify:docs` passes; `docs/current-state.md` date bumped with evidence sources cited in `docs/WORKLOG.md`.
- No numeric behavior changed in this phase (diff artifacts: only new keys/labels).

---

## Phase 6 — Pre-Registered Forward Evidence Bar + Parity Surfacing (F6)

### 6.1 Forward evidence bar contract

- Create `data/contracts/regular-options-filtered-forward-evidence-bar-v1.json` (tokened generator script, same pattern as Phase 1): minimum `30` completed forward paper-shadow rows matched by the frozen v1 policy, cluster-bootstrap PF-LB > 1.0 on percent AND USD, total net USD > 0, at least `8` distinct ticker-week clusters, at least `3` distinct calendar months with rows, zero rows sourced from fixtures. Evaluation may not occur before the row count is met.
- Tracker (`build_regular_options_filtered_forward_paper_shadow_tracker.py`): load the bar contract; report `forward_evidence_bar` progress (rows completed / required, clusters, months) every run. The tracker still cannot approve anything; it only reports progress against the pre-registered bar.

### 6.2 Parity gap surfacing

- Tracker report: add a `parity_disclosure` block: historical audit rows entered 10:10–10:25 ET via the deterministic materializer; forward rows come from production scan sessions (11:00/11:30 local scheduled tasks) with additional scanner gates (momentum/tech_score/liquidity); therefore forward results are a NEW distribution, not a continuation of the historical audit sample. Include the scheduled-session times read from the scan-task health artifact if available rather than hardcoding.
- Throughput expectation: emit `expected_match_rate_note` computed from history — filtered materializer produced 306 rows / 24 months (~13/month upper bound before scanner gates) — so months of zero matches are expected, not a bug.

### 6.3 Tests

- Bar contract schema test; tracker progress-block test with fixture rows (complete vs incomplete bar).

### Checkpoint 6 review criteria

- Bar contract exists, is version-pinned, and the tracker renders progress without any approval authority.
- Confirm with a fixture that reaching 30 rows does NOT flip any acceptance flag anywhere (evaluation is a separate future human/operator step).

---

## Phase 7 — Hygiene + Final Verification (F8)

- Delete stray `tmp8zf11ul3/` from the repo root after confirming it contains nothing referenced (check with a repo-wide grep for the dirname first).
- Review uncommitted modifications under `data/forward-tracking/` (`git status`): commit legitimate artifact refreshes with a descriptive message, or discard if they are stale partial runs — decide per file by reading the diff, do not blanket-discard.
- Add the new contracts and scripts to `docs/index.md` under the appropriate sections (frozen filtered policy contract, consumption registry, evidence bar contract, freeze scripts).
- Full verification sweep, attach outputs to the review:
  - `uv run --locked python -m unittest tests.test_regular_options_historical_profitability_filter_iteration tests.test_regular_options_historical_filtered_simulated_forward_audit tests.test_regular_options_filtered_forward_paper_shadow_tracker tests.test_regular_options_historical_simulated_forward_audit tests.test_regular_options_historical_frozen_scanner_replay_adapter`
  - `npm run verify:python:research`
  - `npm run verify:docs`
  - `npm run daily-ops` (expect all steps green with the new blocked/labeled statuses where applicable)
- Final `docs/WORKLOG.md` entry summarizing all phases with dates and artifact evidence paths.

### Checkpoint 7 review criteria

- All commands above green (or failures explained honestly with output attached).
- `git status` clean except intentional commits.

---

---

# Memory Graph Track (Phases 8–11)

Independent of Phases 1–7; can run in a separate context window and in any order relative to them (but 8 before 9 before 10 within this track). Source of findings: the 2026-07-01 memory-graph audit.

## Context For A Fresh Agent (memory track)

- The system is `scripts/agent_control.py` (10,124 lines, single file), state under ignored `data/agent-control/` (`agent_control.db` ~45 MB, `events.jsonl`, `backups/`, `anchors.jsonl`). Docs: `docs/agent-control-plane.md`, `docs/agent-memory-graph.md`. Commands: the `memory:*` scripts in `package.json`. Existing tests: `tests/test_agent_control.py` (90 tests), `tests/test_agent_memory_graph.py`.
- Key schema: `graph_nodes(kind, tenant_id, sub_tenant_id, title, body, metadata_json, ...)`, `graph_edges(relation, ...)`, `retrieval_documents(doc_id, source_node_id, source_type, source_quality, authority_scope, ..., content_sha256, freshness_status)` + FTS5 table `retrieval_documents_fts` queried with `bm25()` (around `scripts/agent_control.py:3751`). CLI surface built by `add_parser` calls around lines 8820–9290 (`graph query`, `context pack`, `bootstrap`, `memory ...`).
- Measured state (2026-07-01): 1,487 nodes — 1,252 `knowledge` (repo-file excerpts), 127 `entity`, 34 `episode`, 29 `evidence_artifact`, 28 `blocker`, **8 `memory`**, 4 `decision`. 1,430 retrieval docs — **1,239 are `repo_file_index`**. Only 209 edges. Empty tables: `messages`, `feature_snapshots`, `drift_reports`, `dataset_versions`, `provenance_edges`; `blockers` table has 0 rows while 28 blocker NODES exist. All retrieval docs are `freshness_status='current'` regardless of source drift. One cross-project node ("Fashion shopping bot planning loop") sits in the store.
- Audit verdict: infrastructure excellent (backups/restore-check, hash-chain ledger, doctor all pass); content thin; retrieval signal drowned by the repo-file mirror; graph edges near-absent; freshness unwired.

## Memory-Track Boundaries (every phase)

- Memory remains `authority_scope=orchestration_only`. Nothing in this track may authorize trading actions, evidence mutation, scanner/policy changes, or promotion — preserve every existing policy guard and the policy text checks in `_validate_memory_policy_text`.
- Do not break `memory:doctor`, `memory:backup`, `memory:anchor-ledger`, or the run-ledger hash chain. Run `npm run memory:doctor` at the end of every phase; it must stay `pass`.
- Schema changes go through the existing `schema_migrations` mechanism (`init_schema`), never ad-hoc `ALTER` at query time.
- Take a fresh backup (`npm run memory:backup`) BEFORE any phase that touches the DB schema or deletes rows.

---

## Phase 8 — Retrieval Ranking Tiers + Golden-Query Eval

Biggest win: stop the repo-file mirror from drowning real memories in BM25 results.

### 8.1 Source-type tiering in query paths

- Locate every FTS query site (the `bm25(retrieval_documents_fts)` select near line 3751 and any siblings) and the consumers: `graph query`, `context pack`, `bootstrap`.
- Add a tier policy (single constant, one place):
  - Tier 1: `memory`, `decision`, `episode`, `blocker`-derived docs, `living_doc`, `control_plane_doc`, `startup_doc`, `static_memory_graph_node`, `gateboard_*`.
  - Tier 2: `profit_learning_sync`, `dream_run`.
  - Tier 3: `repo_file_index`.
- Default behavior for `context pack` and `bootstrap`: EXCLUDE tier 3 entirely. For `graph query`: include tier 3 only with `--include-repo-index`, and even then rank all tier-1/2 hits above tier-3 hits regardless of BM25 score (two-pass query or `ORDER BY tier, rank`).
- Emit `retrieval_tier` on each returned doc so context manifests show why something ranked.

### 8.2 Golden-query retrieval eval

- Add a fixture file `data/contracts/memory-golden-queries.json` (checked in, small): ~10 queries with expected doc predicates, e.g. `{"query": "what blocks strict forward 30", "expect_source_types": ["gateboard_blocker", "living_doc"], "expect_title_contains_any": ["strict-forward", "strict forward"]}`. Include one query that must NOT return any `repo_file_index` doc by default.
- Wire into the existing `memory agent-eval` command: each golden query runs through the real query path; failure lists which expectation missed. `npm run memory:agent-eval` must include these results in its pass/fail.
- Unit tests in `tests/test_agent_memory_graph.py`: tier ordering, tier-3 exclusion by default, golden-query harness with an in-memory fixture DB.

### Checkpoint 8 review criteria

- `npm run memory:context` output contains zero `repo_file_index` docs; a `graph query` for a code filename still finds it with `--include-repo-index`.
- Golden-query eval green and running inside `memory:agent-eval`; `memory:doctor` still `pass`.
- Diff limited to query/eval paths; no schema change.

---

## Phase 9 — Auto-Distill WORKLOG/DECISIONS Into Episodes/Decisions + Edges

Closes the capture gap: the repo's real memory (`docs/WORKLOG.md`, `docs/DECISIONS.md`) is never ingested.

### 9.1 Ingestion step

- New maintenance sub-step (inside `memory maintenance`, plus standalone command `memory ingest-living-history`): parse `docs/WORKLOG.md` dated entries into `episode` nodes and `docs/DECISIONS.md` entries into `decision` nodes.
  - Idempotency: node id derived from a stable hash of (file, entry heading/date, normalized text); re-runs update in place, never duplicate. Store `content_sha256`; skip unchanged.
  - Each ingested node gets `metadata.source_type="living_history_ingest"`, `authority_scope=orchestration_only`, and the standard memory policy metadata (reuse `_with_memory_policy_metadata`).
- Edge auto-creation: scan each entry body for repo-relative paths (`docs/...`, `scripts/...`, `data/...`) that exist on disk; create `references` edges from the episode/decision node to the corresponding repo-file/artifact node (create a lightweight target node if absent). Cap edges per entry (e.g. 12) to avoid noise.
- Ingested docs join the retrieval index as tier 1.

### 9.2 Tests + backfill

- Tests: parser handles the real current WORKLOG/DECISIONS formats (use trimmed fixture copies); idempotent re-run; edge extraction; policy metadata present; malformed entries skipped with a counted warning, not a crash.
- Run the real backfill once; report node/edge counts in the review (expect episodes to jump from ~34 to 100+, edges from 209 to several hundred).

### Checkpoint 9 review criteria

- Golden query from Phase 8 for a recent WORKLOG topic (e.g. "filtered forward paper shadow tracker") returns an ingested episode in the top results.
- Re-running ingestion twice produces zero new rows the second time (prove with counts).
- `memory:doctor` pass; backup taken before backfill.

---

## Phase 10 — Freshness Wiring, Tenancy Enforcement, Schema Pruning

### 10.1 Freshness

- In `memory maintenance`: for every retrieval doc whose source is a file (repo_file_index, living_doc, ingested history), re-hash the source; on mismatch set `freshness_status='stale'` (and `'missing'` if the file is gone). Query paths from Phase 8 demote stale docs below current ones within the same tier and label them.
- `memory:doctor` gains a non-fatal check reporting stale/missing counts.

### 10.2 Tenancy on write

- All node/doc writes must set an explicit `tenant_id`; default tenant is this repo/project. Add a write-time guard rejecting ingest of content flagged for another tenant. Re-home or archive the existing "Fashion shopping bot planning loop" node (move to its correct tenant or mark `archived`, do not silently delete — record the action in the run ledger).

### 10.3 Schema pruning

- For each empty table (`messages`, `feature_snapshots`, `drift_reports`, `dataset_versions`, `provenance_edges`): either (a) drop via a schema migration, or (b) keep with a one-line "reserved" comment in `init_schema` — decide per table by grepping for any code path that writes it; drop only truly dead ones.
- Resolve the blockers duplication: the `blockers` TABLE (0 rows) vs 28 `blocker` nodes. Pick the node representation as canonical, migrate/drop the table, and update any readers.
- Backup + restore-check before and after the migration; `schema_migrations` row added.

### Checkpoint 10 review criteria

- Deliberately touch a fixture source file in a test → doc flips to stale and demotes in ranking.
- Migration is reversible-documented (what was dropped and why, in the phase WORKLOG entry); doctor, backup, anchor-ledger, run-ledger all pass after.

---

## Phase 11 (optional, larger) — Split `agent_control.py` Into A Package

Only start after 8–10 are merged and green.

- Mechanical split into `scripts/agent_control/` package: `__main__.py` (CLI), `schema.py`, `graph.py`, `retrieval.py`, `ledger.py`, `maintenance.py`, `dreams.py`, `formatting.py`. Keep `scripts/agent_control.py` as a thin shim re-exporting the public functions so all npm scripts, scheduled tasks, and tests keep working unchanged.
- No behavior changes permitted in this phase — pure moves. Prove it: full `tests/test_agent_control.py` + `tests/test_agent_memory_graph.py` green before and after, plus `memory:doctor` pass.

### Checkpoint 11 review criteria

- `git diff` shows moves + imports only (reviewer spot-checks 3 functions byte-identical).
- All `memory:*` npm scripts run unchanged; scheduled maintenance task still points at a valid entrypoint.

---

---

# Track C — Forward-Experiment Completion (Phases 12–15)

Added 2026-07-02 after verifying Track A. Independent of Track B (no shared files). Order: 12 first; 13 and 14 in any order; 15 gated on the Phase 0 ThetaData entitlement fix.

## Context For A Fresh Agent (Track C)

Post-Track-A verified state (2026-07-02):

- The frozen filter (`data/contracts/regular-options-frozen-filtered-policy-v1.json`, `historical_filtered_candidate_policy_v1`: top-8 tickers NEM/JNJ/GOOGL/AAPL/IWM/CVX/SPY/QQQ + `signal_evidence.prior_20_trading_day_return_pct >= 10.990605`) is a pinned hypothesis. Corrected historical metrics: train 237 rows, percent cluster PF-LB `0.93`, USD cluster PF-LB `0.80` (fails gates — the filtered audit correctly reports `blocked_historical_filtered_simulated_forward_audit`); audit window 57 rows, cluster LBs `1.15` / `1.89` (positive but selection-conditioned and registry-sealed).
- The pre-registered forward bar is `data/contracts/regular-options-filtered-forward-evidence-bar-v1.json`: ≥30 completed forward paper-shadow rows, ≥8 ticker-week clusters, ≥3 calendar months, percent AND USD cluster PF-LB > 1.0, net USD > 0, 0 fixture rows, 10k draws.
- The tracker (`scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py`) matches prospective scan-pick rows against the frozen contract and reports bar progress. **Verified gap: matched rows are created with `realized_pnl_status="open_no_exit_yet"` and NOTHING in the repo ever completes them.** `_is_completed_forward_row` (~line 284) counts completions that no code path can produce. The Phase 2 exit stager (`scripts/build_regular_options_strict_forward_30_exit_completion_stager.py`) serves a different cohort log and does not complete tracker rows.
- Historical exit conventions (must match for comparability): exit date = first market day on/after `entry_date + round(0.75 * DTE)`, capped at expiry; exit value = `max(0, long_bid - short_ask)` from trusted quotes at/after 15:50–15:55 ET; fees `4 * fee_per_contract_leg_usd` (default `0.65`); `net_pnl_usd = (exit_value - entry_debit) * 100 - total_fees_usd`. See `_attach_exit_pnl` in `scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py`.
- ThetaData OPRA import is blocked on entitlement (`blocked_thetadata_options_entitlement`, HTTP 403). Until fixed, trusted historical exit quotes cannot be imported; Phase 12 must therefore design exit capture to fail closed on untrusted sources and support both source paths.
- Do NOT run any further filter research/selection on the existing 24-month dataset. The consumption registry (`data/contracts/regular-options-audit-window-consumption-registry.json`) blocks 2026-02..05; the train window is equally off-limits for new selection. New information comes only from new months (Phase 15), completed forward rows (Phase 12 + time), or nothing.

Track A's Non-Negotiable Boundaries apply to every Track C phase.

---

## Phase 12 — Exit Completion Path + Evidence-Bar Evaluator (do first)

Without this, the 30-row bar can never be met and the forward experiment is decorative.

### 12.1 Durable matched-row log

- The tracker currently recomputes matched rows from `scan_picks` on every run; nothing persists per-row lifecycle. Add an append-only log `data/forward-tracking/regular-options-filtered-forward-paper-shadow/matched_rows.jsonl`: when the tracker matches a row not already in the log (key: `candidate_id` = stable hash of scan_run_id + ticker + scan_date + contract identity), append it with full entry provenance. Never rewrite or delete existing lines; tracker artifacts merge log + fresh matches.
- Fail closed at append time if the scan pick lacks: exact long/short contract symbols, executable entry quote source + timestamp, entry debit basis (`long_ask - short_bid`), expiry/DTE. Rows missing these are reported as `matched_but_unappendable_missing_entry_provenance` — visible, not silently dropped. (Verify what current scan-pick rows actually carry before coding; `scripts/log_scan_picks.py` persists entry quote source/timestamps and `signal_ret20` since the June fix.)

### 12.2 Exit evidence capture

- New script `scripts/capture_regular_options_filtered_forward_exit_evidence.py` (+ npm script). For each open matched row whose policy exit date (75%-of-DTE rule above) is on/before the latest completed market day: attempt to resolve trusted exit quotes for both legs.
  - Source A (preferred once entitlement is fixed): trusted ThetaData intraday rows in `data/options-validation/options_history.db` at/after 15:50 ET on the exit date — read-only against the store; any *import* still goes through the existing guarded import machinery, never this script.
  - Source B: a live same-day capture path that snapshots both legs' NBBO at 15:50–16:00 ET on the exit date and writes them to `exit_evidence.jsonl` with source label + retrieval timestamp. This requires the capture to run ON the exit day (scheduled task acceptable, same pattern as the existing 11:00/11:30 tasks); a missed window is recorded as `exit_window_missed_awaiting_trusted_backfill`, never synthesized.
  - Untrusted/midpoint/indicative sources are rejected (`untrusted_exit_quote_source`), mirroring the Phase 2 stager's validation.
- Completion writer: when trusted exit quotes validate, append a completion record (same `candidate_id`, `realized_pnl_status="completed_exact_exit"`, exit quotes, `exit_value`, fees, `net_pnl_usd`, `net_pnl_pct`) to the matched-row log. Append-only; entry rows are never mutated.

### 12.3 Bar evaluator

- New read-only script `scripts/build_regular_options_filtered_forward_evidence_bar_evaluation.py` (+ npm script + generated doc `docs/regular-options-filtered-forward-evidence-bar-evaluation.md`): loads the bar contract, the matched-row log, and the frozen policy contract (hash-verify); computes completed-row count, ticker-week clusters, calendar months, percent AND USD cluster bootstrap PF-LB (reuse the Phase 3 cluster bootstrap); refuses to emit any metric verdict before `min_completed_forward_paper_shadow_rows` is reached (`evaluation_not_permitted_yet`); carries `approval_authority=false` and all standard prohibited-action flags. Meeting the bar produces status `bar_met_pending_operator_review` — never an automatic promotion or scanner change.
- Wire into `daily-ops` after the tracker step. Update the tracker to read completion state from the log so `completed_candidate_count` becomes real.

### 12.4 Tests

- Matched-row append idempotency; missing-provenance fail-closed; exit-date policy math vs the adapter's convention (share a fixture); untrusted-source rejection; completion append; bar evaluator gate (29 rows → not permitted; 30 fixture rows → computes; fixture rows counted → `max_fixture_rows` violation).

### Checkpoint 12 review criteria

- End-to-end fixture walk: matched entry → exit capture → completion → bar progress increments, all through the real scripts.
- No path in the diff can create tracked positions, submit orders, import quotes outside guarded machinery, or mutate `options_history.db`.
- `npm run daily-ops` green with the new steps; scheduled-task registration (if added for source B) follows the existing `.bat` + scheduler-health pattern.

---

## Phase 13 — Scanner-vs-Materializer Parity Diff (read-only)

Explains why forward throughput starves; evidence for the 2026-07-28 refreeze decision. Changes NOTHING about scan behavior.

- New read-only script `scripts/build_regular_options_scanner_materializer_parity_diff.py` (+ npm script + generated doc). For each market day in a bounded recent window (default: since the 2026-06-14 freeze):
  - Column 1: what the deterministic materializer chain selected or no-picked for the frozen lanes/symbols that day (from the frozen entrypoint/daily-decision artifacts).
  - Column 2: what the scheduled scan sessions emitted (from the forward ledger / `scan_picks.jsonl`), including per-symbol drop reasons where persisted (post-June rows).
  - Classify each divergence: `scanner_gate_drop:<reason>`, `no_scheduled_session`, `entry_time_basis_differs` (materializer 10:10–10:25 ET vs scheduled sessions), `materializer_no_pick_scanner_pick`, `insufficient_drop_reason_data` (pre-fix rows).
  - Summarize: of the days the frozen FILTER would have matched a materializer candidate, how many scheduled sessions produced a matching pick, and which single scanner gate is the largest killer.
- Boundary text in artifact + doc: diagnostic only; scan config changes remain forbidden until the frozen-cohort evaluation date, and then only by explicit operator refreeze.
- Tests: fixture days for each divergence class; no-write verification.

### Checkpoint 13 review criteria

- Real-run artifact attached with the divergence table; no mutation anywhere (script has no write path outside its own generated artifacts).
- The summary names the top starvation gate with day counts, or honestly reports `insufficient_drop_reason_data` dominance.

---

## Phase 14 — Parked-Branch Artifact/Doc Consolidation

Reduces daily-ops runtime, agent context cost, and memory-graph index noise. Archival only — no deletion of data artifacts.

- Build the inventory first (read-only pass): every generated doc + script + daily-ops step belonging to explicitly parked/falsified/exhausted branches (candidates from `docs/index.md`: opening-range reversal replay, quote-derived synthetic-forward surface, local quote-structure capability matrix/atlas, exhausted-source archives, superseded repair packets, and similar "do not rerun unless data changes" branches). Present the list in the artifact BEFORE moving anything.
- For each confirmed-parked branch: move its generated doc to `docs/archive/` (preserving content), remove its `docs/index.md` "Start Here" entry, and remove its step from `scripts/run_daily_ops.py` if present. Keep the script itself (it may be revived by a data repair) — just stop running/indexing it by default.
- Create ONE consolidated `docs/regular-options-parked-branch-ledger.md` (generated) listing every parked branch, its blocker, its revival condition, and its archived doc path — so the do-not-rerun warnings survive consolidation in a single place instead of forty.
- Guards: `npm run verify:docs` must pass after every batch; `daily-ops` must still complete all remaining steps; do not archive anything whose status is `ready`, `collecting`, `active`, or that Track C Phases 12/13/15 consume.
- Tests: ledger generator; a docs-hygiene check that archived docs are not referenced from the live index.

### Checkpoint 14 review criteria

- Before/after counts: index entries, daily-ops steps, daily-ops wall-clock. All verification suites green.
- Spot-check: two archived branches still fully reconstructable (script present, archived doc readable, ledger entry has revival condition).

---

## Phase 15 — Out-Of-Sample History Extension (gated on Phase 0 entitlement fix)

The fastest honest verdict on the frozen filter: evaluate it on months that never touched any selection. Do NOT start until `npm run options:source-repair:59-symbol-thetadata-opra-import-resume` reports the entitlement blocker cleared.

### 15.1 Pre-register the evaluation before touching data

- Write `data/contracts/regular-options-out-of-sample-extension-v1.json` FIRST (tokened generator, same pattern as the other contracts): target window `2022-01` through `2024-05` (or the deepest window the provider actually serves — record what was requested vs received), the 13-symbol proof set, the frozen policy id + conditions hash, and the exact gates: percent cluster PF-LB > 1.0 AND USD cluster PF-LB > 1.0 AND net USD > 0 on the new window, cluster = ticker-ISO-week, 10k draws, fees per the adapter. State explicitly: evaluation-only; any filter modification, threshold change, or new filter family on this window is prohibited; the window enters the consumption registry as `consumed_for_evaluation` immediately upon evaluation.
- Note honestly in the contract: with train cluster-LB at 0.93, the pre-registered expectation is uncertain; a failing result parks the filter (tracker may continue but the hypothesis is downgraded), a passing result upgrades it to "historically consistent, still awaiting forward bar". Neither outcome authorizes trading.

### 15.2 Scoped import + backward extension

- Import via the EXISTING guarded ThetaData import machinery only (scoped to the 13 symbols + target window; protected-holdout overlap must stay 0). Underlying daily OHLCV for the same window through the existing staged-CSV underlying-daily import path (`data/import-staging/underlying_daily/`, tokened importer) — the current source covers only 24 months and the signal needs prior-20-day returns and 50-day SMA, so stage daily bars back to `2021-10` at least.
- Rerun the materializer chain for the extended calendar (adapter → daily decisions → entrypoint → source surface → engine). The chain must mark the new months `candidate_generation_basis` identically and keep `scanner_parity=false`.

### 15.3 Evaluation

- New read-only script `scripts/build_regular_options_out_of_sample_frozen_filter_evaluation.py` (+ npm script + generated doc): applies the frozen contract filter (hash-verified) to ONLY the new months' exact rows, computes the pre-registered gates, appends the window to the consumption registry with `consumed_for_evaluation`, and reports pass/park with per-month and per-ticker breakdowns plus regime notes (the new window includes the 2022 bear market — exactly the regime the filter has never seen).
- Tests: hash-verify gate, month scoping (must not include any 2024-06+ rows), registry append, fail-closed on missing import coverage (partial months are excluded and reported, never padded).

### Checkpoint 15 review criteria

- Contract existed (committed) BEFORE the import ran — reviewer checks timestamps.
- Import provenance: rows in window/symbols only, holdout overlap 0, import logs attached.
- One evaluation run, one registry append, verdict reported verbatim whichever way it lands. Any attempt to iterate filters on this window is a review-rejection.

---

## Phase 16 — Recurring Fresh-Window Trusted Quote Import (added 2026-07-02)

Root cause found after the 59-symbol gap-fill import: that import filled the HISTORICAL gap manifest (shared dates 260 → 510, ending 2026-06-04; store max intraday date 2026-06-08), but nothing imports NEW trading days going forward. Consequences: the parity diff's post-freeze window (2026-06-14 onward) has no trusted quotes and stays `materializer_window_has_no_rows`; Phase 12's exit-evidence source A (trusted store lookup) can never serve exits for current forward rows; the materializer cannot advance into the current month.

### 16.1 Recurring import

- New tokened script `scripts/import_regular_options_fresh_window_thetadata_opra.py` (+ npm script): imports trusted ThetaData intraday OPRA/NBBO for a bounded recent window (default: from the store's max intraday date + 1 through the latest completed market day), scoped to the frozen-cohort symbols (both lanes' unions) plus the 13-symbol proof set. Reuses the existing import-batch machinery, source label, and trust marking — no new storage paths. Approval token required (`APPROVE_FRESH_WINDOW_THETADATA_OPRA_IMPORT`); protected-holdout overlap must be 0 and measured; outside-universe rows must be 0 and measured.
- Register a Windows scheduled task (existing `.bat` + scheduler-health pattern) running weekday evenings after close (e.g. 17:30 local), plus a scheduler-health readback extension that fails closed if the task is missing/mispointed, mirroring `\OptionsStrictForward30Collector` health checks. The batch must not carry scan/auto-track/append flags.
- After each import, refresh the materializer chain + parity diff (append steps or reuse daily-ops).

### 16.2 Tests + checkpoint

- Tests: window computation (store max date + 1 → last completed market day; empty when up to date), token gate, scope enforcement (reject symbols outside the union), holdout/outside-universe measured outputs.
- Checkpoint: one real tokened run attached showing store max date advancing to the latest completed market day; parity diff rerun showing `materializer_rows_in_window > 0` (or an honest remaining blocker if the materializer chain needs a separate refresh); scheduler-health readback green.
- Boundaries: Track A non-negotiables apply; this phase imports quotes ONLY through guarded tokened machinery with measured scope/holdout outputs; it does not change filters, gates, scanner policy, or selection permissions.

---

## Expected End State

- The v1 filter is a hash-pinned, pre-registered hypothesis under prospective paper-shadow tracking with a pre-registered pass bar — not a re-derivable claim.
- The 2026-02..05 audit window can never again mint an accepted filter.
- All PF gates in this chain use cluster (ticker-week) bootstrap lower bounds on both percent and fee-adjusted USD P&L, with duplicates deduped.
- Artifacts and docs state plainly that the historical filtered "pass" was selection-conditioned and regime-concentrated.
- Honest likely outcome: under Phases 3–4 the historical filtered audit flips to blocked. That is correct behavior, not a regression. The forward tracker remains the only path to acceptance.
- Memory track: context packs and queries surface real memories/decisions/episodes first (repo-file mirror demoted or excluded), WORKLOG/DECISIONS history is auto-ingested with provenance edges, freshness reflects source drift, tenancy is enforced, and dead schema is pruned — with doctor/backup/ledger green throughout.
- Track C: matched paper-shadow rows have a real entry→exit→completion lifecycle feeding the pre-registered bar; scanner starvation is quantified per gate for the refreeze decision; parked branches are archived into one ledger; and (post-entitlement) the frozen filter has a pre-registered out-of-sample verdict from 2022–2024 months that never touched selection.
