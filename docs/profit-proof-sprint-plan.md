# Profit Proof Sprint Plan

Last updated: 2026-04-06

## Purpose

This document is the implementation handoff for turning the options lane from:

- interesting replay
- thin forward recording
- manually reviewed tracked positions

into:

- canonical live scanner evidence
- explicit taken-position linkage
- reliable review and close evidence
- a frozen SPY/QQQ canary that can support or reject a real profitability claim

This is written so future context windows do not need to repeat the code-reading and funnel diagnosis that led to this plan.

## Read This First

Before making changes, read these files:

- `C:\Users\kalec\options-chatbot\forward_options_ledger.py`
- `C:\Users\kalec\options-chatbot\profit_loop_automation.py`
- `C:\Users\kalec\options-chatbot\options_chatbot.py`
- `C:\Users\kalec\options-chatbot\supervised_scan.py`
- `C:\Users\kalec\options-chatbot\python-backend\main.py`
- `C:\Users\kalec\options-chatbot\python-backend\positions_service.py`
- `C:\Users\kalec\options-chatbot\python-backend\positions_repository.py`
- `C:\Users\kalec\options-chatbot\tests\test_forward_options_ledger.py`
- `C:\Users\kalec\options-chatbot\tests\test_tracked_positions_api.py`
- `C:\Users\kalec\options-chatbot\tests\test_positions_review_engine.py`
- `C:\Users\kalec\options-chatbot\docs\current-state.md`
- `C:\Users\kalec\options-chatbot\docs\autoresearch\truth-first-champions.json`

## Executive Summary

The repo already has most of the pieces for a supervised live-trading evidence loop:

- scan picks can be recorded
- tracked positions can be created
- open positions can be reviewed
- positions can be manually closed
- forward holdout and profitability gates already exist

But the system still does not accumulate strong evidence because of four structural issues:

1. Canonical scan-to-position linkage is weak.
2. Position open is not recorded as first-class forward evidence.
3. Zero-candidate days are not fully diagnosable from stored evidence.
4. Profitability thresholds in code are loop-health thresholds, not claim-ready thresholds.

This sprint plan fixes those problems in order.

## Ground Truth Findings

### 1. Scanner evidence exists, but taken-position linkage is heuristic

The scanner records forward evidence from the API path.

Relevant code:

- `python-backend/main.py` in `_record_forward_truth_for_scan`
- `forward_options_ledger.py` in `record_forward_snapshot`

Problem:

- once a tracked position is opened, the ledger mostly infers whether a scan pick was "taken" by matching on contract symbol, ticker, expiry, direction, strike, and cohort
- that is better than nothing, but it is not a canonical join

Relevant code:

- `forward_options_ledger.py` in `_tracked_position_matches_pick`
- `forward_options_ledger.py` in `_pick_outcome_state`

Implication:

- repeated SPY/QQQ ideas can become ambiguous
- the proof lane should not rely on inference when the UI already knows exactly which pick the user clicked

### 2. Position open is not its own proof event

The system records:

- scan sessions and scan picks
- tracked-position review events
- tracked-position close events

But it does not record a dedicated "position opened" forward event at the moment the user takes the trade.

Relevant code:

- `python-backend/main.py` in `create_position_endpoint`
- `python-backend/main.py` in `_record_forward_truth_for_position_events`
- `forward_options_ledger.py` in `record_forward_snapshot`

Implication:

- the funnel has a weak middle
- we can say a pick existed, and later we can say a position was reviewed or closed
- but we are not currently writing the exact moment and linkage of "user took this exact scan pick"

### 3. Zero-candidate diagnosis is incomplete after persistence

The raw scanner computes detailed drop counts:

- min history
- history/liquidity
- signal index
- momentum
- tech score
- direction score
- earnings
- option liquidity
- IV crush penalty
- EV floor
- guardrails
- exceptions

Relevant code:

- `options_chatbot.py` in `SCAN_FUNNEL_DROP_KEYS`
- `options_chatbot.py` in `_empty_scan_drop_counts`
- `options_chatbot.py` in `_bump_scan_drop`
- `options_chatbot.py` in `scan_daily_top_trades`

The supervised scanner includes `drop_counts` in the scan funnel.

Relevant code:

- `supervised_scan.py` in `_build_scan_funnel`

But the forward ledger currently normalizes scan funnels without preserving `drop_counts`.

Relevant code:

- `forward_options_ledger.py` in `_normalized_scan_funnel`

The holdout automation then classifies starvation using the normalized funnel.

Relevant code:

- `profit_loop_automation.py` in `_scan_funnel_stage`
- `profit_loop_automation.py` in `_candidate_flow_breakdown`

Implication:

- after persistence, we know whether starvation happened before policy, at policy, at guardrails, or at final trim
- but we do not reliably retain which raw scanner gate actually killed candidate flow

### 4. The live proof lane is stricter in spirit than in write-path enforcement

The scanner already records the metadata needed for exact-contract proof:

- `contract_symbol`
- `expiry`
- `strike`
- `quote_time_et`
- `quote_basis`
- `underlying_price_at_selection`
- `selection_source`
- `promotion_class`
- `entry_execution_price`
- `entry_execution_basis`
- `entry_fee_total_usd`

Relevant code:

- `options_chatbot.py` in `scan_daily_top_trades`
- `python-backend/main.py` in `_normalize_scan_pick`
- `forward_options_ledger.py` in `_event_fields_from_pick`

Tracked-position review is also correctly biased toward exact-contract identity and explicitly avoids nearest-strike substitution.

Relevant code:

- `positions_service.py` in `_fetch_option_quote`

But `build_position_payload()` only requires:

- ticker
- direction/type
- strike
- expiry

Relevant code:

- `positions_service.py` in `build_position_payload`

Implication:

- proof-lane positions can still be opened without full exact-contract metadata
- review may later become unpriced
- this slows or weakens realized evidence

### 5. The current profitability gate is too weak for a real claim

Current defaults:

- minimum eligible forward events: `10`
- minimum eligible events per symbol: `3`
- minimum closed tracked positions: `1`
- minimum realized profit factor: `1.0`
- minimum realized average net pnl pct: `0.0`

Relevant code:

- `options_profit_gate.py`

Implication:

- these are reasonable loop-health gates
- they are not strong enough to support a profitability claim

### 6. Canonical repo state currently does not match historical narrative

In this checkout:

- authoritative forward ledger is empty
- archive forward ledger is empty
- profitability gate sees zero canonical forward evidence
- profitability gate sees zero closed tracked positions

But `docs/current-state.md` still describes prior holdout sessions and imported-daily artifacts as if they are present in canonical repo state.

Implication:

- canonical evidence health must be made explicit
- temporary workspace artifacts must not be treated as production evidence

## Non-Negotiable Rules For This Plan

- Do not loosen rules to manufacture evidence.
- Do not convert hypothetical suggested trades into real-position proof.
- Do not let nearest-strike substitution enter the tracked-position proof lane.
- Do not change the frozen SPY/QQQ canary mid-run.
- Do not make promotion or profitability claims from replay-only wins.
- Do not silently backfill missing joins when the UI already knows the exact source pick.

## Target State

At the end of this plan, the repo should support this exact funnel:

1. scanner emits exact live picks
2. every picked row has durable identity
3. user takes one exact pick
4. tracked position stores exact scan provenance
5. position open is recorded in the forward ledger
6. review writes canonical review evidence
7. close writes canonical realized evidence
8. summaries and gates can answer:
   - how many forward opportunities matured
   - how many were taken
   - how many were reviewed
   - how many were closed
   - whether results are good enough for a profitability claim

## Sprint Structure

This plan assumes 4 implementation sprints plus a 90-day canary run.

- Sprint 1: Canonical linkage and event plumbing
- Sprint 2: Scanner starvation observability
- Sprint 3: Strict proof-lane tracked positions
- Sprint 4: Profit-claim thresholds, dashboards, and canary operations

## Sprint 1: Canonical Linkage And Event Plumbing

### Goal

Remove heuristic ambiguity from the live funnel.

### Primary Deliverables

- tracked positions store explicit scan provenance
- forward ledger records `position_opened`
- scan pick to tracked position join uses explicit ids first
- end-to-end tests prove the canonical path

### Files To Modify

- `C:\Users\kalec\options-chatbot\python-backend\positions_repository.py`
- `C:\Users\kalec\options-chatbot\python-backend\positions_service.py`
- `C:\Users\kalec\options-chatbot\python-backend\main.py`
- `C:\Users\kalec\options-chatbot\forward_options_ledger.py`
- `C:\Users\kalec\options-chatbot\tests\test_tracked_positions_api.py`
- `C:\Users\kalec\options-chatbot\tests\test_forward_options_ledger.py`

### Schema Changes

Add to `tracked_positions`:

- `source_scan_session_id BIGINT`
- `source_scan_event_key TEXT`
- `source_scan_run_id TEXT`
- `source_scan_recorded_at_utc TIMESTAMPTZ`

Optional but useful:

- `proof_eligible BOOLEAN NOT NULL DEFAULT FALSE`
- `proof_ineligibility_reason TEXT`

Keep the existing `source_pick_snapshot JSONB`; do not replace it.

### API Contract Changes

When `/api/positions` is called, the backend should accept and preserve from the chosen scan pick:

- `source_scan_session_id`
- `source_scan_event_key`
- `source_scan_run_id`
- `source_scan_recorded_at_utc`

If the UI does not currently send these, add them to the scan response first, then pass them back on create.

### Ledger Changes

Add a new forward event type:

- `position_opened`

Each `position_opened` event must include:

- `position_id`
- `ticker`
- `contract_symbol`
- `expiry`
- `strike`
- `option_type`
- `entry_execution_price`
- `entry_execution_basis`
- `entry_fee_total_usd`
- `contracts`
- `filled_at`
- explicit source scan provenance
- `cohort_id`
- `cohort_role`
- `selection_source`
- `promotion_class`

### Matching Logic Changes

Current:

- `_tracked_position_matches_pick()` tries contract/ticker/expiry/strike matching

New behavior:

1. if both scan pick and position have `source_scan_session_id` and `source_scan_event_key`, use those
2. else if contract symbols match exactly, use that
3. else fall back to the current heuristic

### Tasks

1. Extend tracked-position schema.
2. Update `build_position_payload()` to copy explicit scan provenance into payload and `source_pick_snapshot`.
3. Update `create_position_endpoint()` to record a `position_opened` forward event immediately after create.
4. Extend forward ledger schema if needed for `position_id` and `contracts` on position events.
5. Update `record_forward_snapshot()` to write `position_opened`.
6. Update `_pick_outcome_state()` and related linkage helpers to prefer explicit ids.

### Acceptance Criteria

- every newly opened tracked position has explicit source scan provenance
- every newly opened tracked position generates a `position_opened` ledger event
- a taken scan pick is attributable to one specific position open event
- no new proof logic depends primarily on fuzzy matching

### Tests Required

Add or update tests to prove:

- create position stores explicit provenance
- forward ledger writes `position_opened`
- review and close events share the same `position_id`
- legacy rows without provenance still function through fallback matching

## Sprint 2: Scanner Starvation Observability

### Goal

Make raw candidate scarcity diagnosable from persisted evidence.

### Primary Deliverables

- scan funnel persistence includes `drop_counts`
- per-symbol gate diagnostics for SPY and QQQ are stored
- holdout summary can explain zero-candidate days
- "empty market" is stricter than "we saw zero raw candidates"

### Files To Modify

- `C:\Users\kalec\options-chatbot\options_chatbot.py`
- `C:\Users\kalec\options-chatbot\supervised_scan.py`
- `C:\Users\kalec\options-chatbot\forward_options_ledger.py`
- `C:\Users\kalec\options-chatbot\profit_loop_automation.py`
- `C:\Users\kalec\options-chatbot\tests\test_forward_options_ledger.py`

### Required Persistence Additions

Preserve in session notes:

- `scan_funnel.drop_counts`
- per-symbol raw diagnostics for SPY and QQQ:
  - history/liquidity eligible
  - signal direction candidate
  - tech gate result
  - direction gate result
  - earnings block
  - option liquidity result
  - EV floor result
  - exact contract availability
  - final candidate produced or not

### Holdout Classification Changes

Current classification in `_candidate_flow_breakdown()`:

- `environment_or_data_failure`
- `filtered_by_history_or_liquidity`
- `no_candidates_from_scan`
- `filtered_by_policy`
- `filtered_by_guardrails`

New behavior:

- keep the current classes
- add `scanner_starvation_unresolved`
- only label `no_candidates_from_scan` when stored symbol diagnostics support genuine raw-zero conditions
- if raw-zero happens but diagnostics are absent or incomplete, classify as unresolved starvation instead of "empty market"

### Tasks

1. Preserve `drop_counts` in forward-ledger scan funnel normalization.
2. Add optional symbol diagnostics payload to `build_forward_scan_snapshot()`.
3. Teach `scan_daily_top_trades()` to expose symbol-level gate results.
4. Extend holdout summary and truth holdout artifact to include these diagnostics.
5. Update docs to define "empty market" using persisted symbol diagnostics.

### Acceptance Criteria

- any zero-candidate day can be explained from ledger data
- the repo can distinguish:
  - no raw setups
  - policy filtered all
  - guardrails filtered all
  - final trimming to zero
  - unresolved starvation
- holdout artifacts no longer overclaim "empty market" without sufficient diagnostics

### Tests Required

Add tests for:

- `drop_counts` persistence through forward sessions
- zero-candidate session with `tech_score` starvation
- zero-candidate session with `option_liquidity` starvation
- classification downgrade to unresolved when diagnostics are missing

## Sprint 3: Strict Proof-Lane Tracked Positions

### Goal

Make tracked positions in the proof lane fail closed unless they are exact-contract, executable, and reviewable.

### Primary Deliverables

- proof-lane create validation
- richer review pricing states
- manual close flow prefills executable exit data
- proof-lane positions are clearly separated from permissive hypothetical capture

### Files To Modify

- `C:\Users\kalec\options-chatbot\python-backend\positions_service.py`
- `C:\Users\kalec\options-chatbot\python-backend\main.py`
- `C:\Users\kalec\options-chatbot\python-backend\positions_repository.py`
- `C:\Users\kalec\options-chatbot\tests\test_positions_review_engine.py`
- `C:\Users\kalec\options-chatbot\tests\test_tracked_positions_api.py`

### Proof-Lane Create Requirements

For proof-lane tracked positions, require:

- `ticker`
- `direction`
- `expiry`
- `strike`
- `contract_symbol`
- `quote_time_et`
- `bid`
- `ask`
- `entry_execution_price`
- `entry_execution_basis`
- `selection_source = live_chain_exact_contract`
- `promotion_class = promotable_exact_contract`

If any of these are missing:

- block proof-lane position creation
- include a human-readable reason

Do not apply this strictness to suggested trades.

### Review State Upgrade

Current review behavior returns warnings and pricing source.

Add a stronger review state field such as:

- `priced_exact`
- `priced_display_only_last`
- `unpriced_exact_contract_missing`
- `unpriced_exact_contract_not_in_chain`
- `unpriced_expiry_not_available`
- `unpriced_chain_fetch_failed`

Persist the state in `latest_review.metrics_snapshot` and/or a dedicated field.

### Close Flow Upgrade

If latest review already has:

- `exit_execution_price`
- `exit_execution_basis`
- executable quote

then the close endpoint or UI should be able to prefill those values for confirmation.

This does not automate the close.

It removes unnecessary manual copy work.

### Tasks

1. Add proof-lane validation in `build_position_payload()`.
2. Add proof-lane create tests for missing contract symbol and missing executable entry quote.
3. Extend review result payload with explicit pricing state.
4. Persist the pricing state through repository review writes.
5. Extend close-path tests to verify prefilling behavior or persisted executable exit context.

### Acceptance Criteria

- no proof-lane position is created without exact-contract identity
- reviews clearly distinguish executable, display-only, and unpriced states
- close loop preserves executable exit context

### Tests Required

Add tests for:

- missing `contract_symbol`
- missing `entry_execution_price`
- non-exact selection source
- review when exact contract is absent from chain
- review when only last trade is available
- close after executable review

## Sprint 4: Profit Claim Readiness And Operating System

### Goal

Separate loop-health readiness from claim-readiness, then run a frozen SPY/QQQ canary on top of the repaired evidence loop.

### Primary Deliverables

- two-tier proof gates
- canonical dashboard or summary artifact
- frozen canary procedure
- daily operating checklist

### Files To Modify

- `C:\Users\kalec\options-chatbot\options_profit_gate.py`
- `C:\Users\kalec\options-chatbot\profit_loop_automation.py`
- `C:\Users\kalec\options-chatbot\python-backend\main.py`
- `C:\Users\kalec\options-chatbot\docs\current-state.md`
- `C:\Users\kalec\options-chatbot\docs\autoresearch\truth-first-champions.json`

### Gate Split

Keep the current low thresholds as a loop-health gate only.

Add a second gate for profitability claims.

#### Loop-Health Thresholds

- `10` matured eligible forward events total
- `3` matured eligible forward events per symbol
- `3` closed tracked positions total
- exact-contract capture above a minimum floor

#### Claim-Readiness Thresholds

- `40` matured eligible forward events total
- `15` matured eligible forward events per symbol
- `20` closed exact-contract tracked positions total
- `8` closed exact-contract tracked positions per symbol
- net profit factor `>= 1.20`
- average net pnl after fees `> 0`
- exact-contract capture `>= 95%`

### Canonical Dashboard / Summary Requirements

Expose one canonical summary source that reports:

- forward event counts
- pending-truth event counts
- exact-contract capture counts
- taken-pick count
- opened-position count
- review count
- closed-position count
- per-symbol stats
- realized gross and net pnl
- loop-health verdict
- claim-readiness verdict

Do not rely on temporary run workspaces for this summary.

### Frozen Canary Workflow

Keep it fixed:

- symbols: `SPY`, `QQQ`
- control cohort: `baseline_broad_control`
- challenger cohort: `broad_ev7_momentum070_exit_time33`
- fixed windows: `10:00 ET`, `13:30 ET`
- at most one new position per symbol per day
- review once daily at a fixed time

Daily rules:

1. record control policy-gated run
2. record raw audit run
3. record challenger shadow run
4. if proof-eligible pick exists, user may take it
5. record `position_opened`
6. review all open canary positions
7. manually close only on user confirmation

### Tasks

1. Add a second claim-readiness evaluator to `options_profit_gate.py`.
2. Add one canonical summary endpoint or JSON artifact in `python-backend/main.py`.
3. Update `profit_loop_automation.py` to use the repaired holdout diagnostics and gate split.
4. Update docs with exact canary instructions and thresholds.

### Acceptance Criteria

- the repo can say whether the loop is healthy even when profitability is still unproven
- the repo can separately say whether profitability is claim-ready
- every claim-ready metric comes from canonical stored evidence

### Tests Required

Add tests for:

- loop healthy but not claim ready
- claim ready only when thresholds are all met
- insufficient exact-contract capture blocks claim readiness

## Cross-Sprint Data Model Checklist

These fields should exist and be treated as first-class proof metadata.

### Scan-Time Metadata

- `source_scan_session_id`
- `source_scan_event_key`
- `source_scan_run_id`
- `source_scan_recorded_at_utc`
- `ticker`
- `direction`
- `option_type`
- `expiry`
- `strike`
- `contract_symbol`
- `quote_time_et`
- `quote_basis`
- `bid`
- `ask`
- `mid`
- `entry_execution_price`
- `entry_execution_basis`
- `entry_fee_total_usd`
- `underlying_price_at_selection`
- `selection_source`
- `promotion_class`
- `quote_freshness_status`
- `cohort_id`
- `cohort_role`
- `candidate_rank`

### Position-Time Metadata

- `position_id`
- all source scan provenance fields
- `contracts`
- `filled_at`
- actual `fill_price`
- actual `entry_execution_price`
- actual `entry_execution_basis`
- `entry_fee_total_usd`
- `proof_eligible`
- `proof_ineligibility_reason`

### Review-Time Metadata

- `reviewed_at`
- `pricing_source`
- `pricing_state`
- `current_option_price`
- `exit_execution_price`
- `exit_execution_basis`
- `gross_pnl_pct`
- `net_pnl_pct`
- `gross_pnl_usd`
- `net_pnl_usd`
- `fee_total_usd`
- `recommendation`
- `reason`
- `warnings`

### Close-Time Metadata

- `closed_at`
- `exit_option_price`
- `exit_execution_price`
- `exit_execution_basis`
- `exit_reason`
- realized gross/net pnl

## Daily Operating Checklist After Implementation

Once Sprints 1-4 land, the daily routine should be:

1. verify canonical truth bundle is present
2. run fixed SPY/QQQ control scan
3. run fixed raw audit scan
4. run fixed challenger shadow scan
5. if a proof-eligible pick appears, user may take it
6. ensure `position_opened` was written
7. review all open canary positions at the fixed review time
8. if user closes, ensure close event was written
9. inspect canonical summary, not temp artifacts

## Definition Of Done By Phase

### Sprint 1 Done

- explicit scan provenance stored on tracked positions
- `position_opened` ledger events exist
- taken linkage prefers explicit provenance
- end-to-end tests pass

### Sprint 2 Done

- `drop_counts` preserved
- per-symbol diagnostics stored
- zero-candidate days diagnostically explainable
- holdout classifier no longer overclaims empty-market state

### Sprint 3 Done

- proof-lane create path is strict
- exact-contract-only tracked positions are enforced for proof
- review states are explicit and persisted
- close flow preserves executable exit context

### Sprint 4 Done

- loop-health and claim-readiness are distinct
- canonical summary exists
- frozen canary instructions are codified
- docs match canonical repo state

## 30 / 60 / 90-Day Evidence Targets

### 30 Days

- canonical ledgers populated
- at least `10` matured eligible forward events
- at least `3` closed tracked positions
- exact-contract capture floor consistently high
- no profitability claim

### 60 Days

- at least `25` matured eligible forward events
- at least `10` closed tracked positions
- at least one month without evidence-plumbing failures
- no profitability claim yet unless claim gate is truly met

### 90 Days

- at least `40` matured eligible forward events
- at least `20` closed exact-contract tracked positions
- per-symbol minimums met
- claim-readiness judged from canonical evidence only

## Immediate Next PR Recommendation

The highest-leverage first PR is Sprint 1:

- tracked-position schema provenance
- `position_opened` event
- explicit scan-to-position join
- tests

That PR creates the backbone required for every later claim.

## Notes For Future Context Windows

- Do not start by optimizing the strategy.
- Start by repairing evidence plumbing.
- Do not trust `docs/current-state.md` unless it matches canonical artifacts in the repo.
- Do not use temporary workspace artifacts as production truth.
- The right question is not "is the strategy profitable?"
- The right first question is "can the repo prove what happened, from scan to close, without inference?"
