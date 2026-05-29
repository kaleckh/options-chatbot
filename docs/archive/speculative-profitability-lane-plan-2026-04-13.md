# Speculative Profitability Lane Plan

Last updated: 2026-04-13

## Purpose

This document defines the recommended path for adding a separate speculative options lane and deciding whether the profitability loop should expand beyond the current `SPY` / `QQQ` scope.

The answer from the codebase is:

- yes, add a separate speculative lane
- no, do not expand the profitability claim loop to all tracked tickers yet
- if expansion happens later, expand the evidence layer first and keep claims segmented by cohort and symbol

## Executive Decision

### 1. Add a separate speculative lane

The speculative lane should be implemented as:

- a separate scanner playbook
- a separate cohort family in the profitability system
- a separate measurement verdict from the main broad-control lane
- watch-only / observation-only until it earns exact-contract proof

It should not be implemented by loosening the existing `short_term` or `swing` lanes.

### 2. Do not expand the profitability loop to all tracked tickers right now

The scanner can evaluate a broader watchlist, but the profitability loop is intentionally narrower because the trusted truth and exact-contract evidence are narrower.

The current codebase still hard-limits the profit loop to `SPY` and `QQQ`:

- [options_profit_state.py](C:\Users\kalec\options-chatbot\options_profit_state.py:16)
- [python-backend/main.py](C:\Users\kalec\options-chatbot\python-backend\main.py:117)

The current frozen validation manifest also limits the active validation scope to `SPY` and `QQQ`:

- [docs/autoresearch/truth-first-champions.json](C:\Users\kalec\options-chatbot\docs\autoresearch\truth-first-champions.json:1)

### 3. If expansion happens later, expand evidence, not claims

The long-term move is not “blend all tracked tickers into one profitability verdict.”

The right long-term move is:

- support broader evidence capture per symbol
- support cohort-specific measurement and claim readiness
- keep profitability verdicts segmented by lane/cohort/symbol family

This avoids mixing validated index behavior with unvalidated single-name or speculative behavior.

## Why This Is The Right Call

### The scan universe is broader than the profit loop

Update 2026-05-21: this warning no longer applies to the `ai_commodity_infra_observation` Alpaca OPRA proof loop. That lane now keeps live scan, capture, replay, and proof readiness aligned to the full scan-eligible AI commodity universe. The broader warning still applies to unrelated speculative/watchlist expansion unless those lanes first expand their exact evidence layer.

The live options scan uses a larger watchlist:

- [options_chatbot.py](C:\Users\kalec\options-chatbot\options_chatbot.py:93)

That watchlist includes:

- `SPY`, `QQQ`
- `IWM`, `DIA`, `XLK`
- `AAPL`, `NVDA`, `MSFT`, `AMZN`, `GOOGL`, `META`, `AMD`, `NFLX`, `JPM`, `TSLA`

There is also an expansion watchlist and a high-beta list:

- [options_chatbot.py](C:\Users\kalec\options-chatbot\options_chatbot.py:103)
- [options_chatbot.py](C:\Users\kalec\options-chatbot\options_chatbot.py:119)

So the product already tracks more names than the profit loop currently judges.

### The profitability loop is deliberately narrow

The state layer only allows `SPY` and `QQQ`:

- [options_profit_state.py](C:\Users\kalec\options-chatbot\options_profit_state.py:16)

The backend read-only defaults also assume only `SPY` and `QQQ`:

- [python-backend/main.py](C:\Users\kalec\options-chatbot\python-backend\main.py:140)

The current candidate files under `data/options-profit/candidates/` are only `SPY` / `QQQ` variants.

### Exact-contract proof is still the bottleneck

The latest imported-daily artifact can show research promise, but the authoritative exact-contract gate still fails:

- [data/options-validation/runs/latest_daily.json](C:\Users\kalec\options-chatbot\data\options-validation\runs\latest_daily.json:1)
- [wfo_optimizer.py](C:\Users\kalec\options-chatbot\wfo_optimizer.py:4641)

The authoritative gate requires:

- at least `25` exact-contract trades
- `profit_factor >= 1.05`
- `avg_pnl_pct > 0`
- `directional_accuracy_pct >= 50`

The current artifact still reports `0` exact-contract trades for the authoritative subset.

### The live measurement gate is not healthy enough to justify broadening

The options profit gate currently requires loop health evidence before it should be trusted:

- [options_profit_gate.py](C:\Users\kalec\options-chatbot\options_profit_gate.py:609)

Current default loop-health bars:

- `10` eligible forward events
- `3` eligible events per symbol
- `1` closed tracked position
- realized `PF >= 1.0`
- realized average net P&L `> 0`

Current claim-readiness bars are higher:

- `40` eligible forward events
- `PF >= 1.20`

The current saved status is blocked by stale truth freshness:

- [data/options-profit/status.json](C:\Users\kalec\options-chatbot\data\options-profit\status.json:1)

That means broadening the loop now would expand the surface area of untrusted evidence, not improve trust.

## Recommended Architecture

## A. Scanner / UI lane

Add a new speculative playbook in:

- [supervised_scan.py](C:\Users\kalec\options-chatbot\supervised_scan.py:38)

Recommended playbook behavior:

- `id = "speculative"`
- visible as a separate tab/button next to `short_term` and `swing`
- stricter portfolio caps than the current playbooks
- default size always `starter`
- never auto-presented as a promoted lane
- explicit copy that this is a high-convexity, low-probability lane

Recommended scan-pick metadata:

- `risk_tier`
- `upside_tier`
- `speculative_flag`
- `speculative_reason`
- `convexity_class`

Those fields should travel on `ScanPick` and be preserved through:

- [python-backend/main.py](C:\Users\kalec\options-chatbot\python-backend\main.py:326)
- [src/lib/types.ts](C:\Users\kalec\options-chatbot\src\lib\types.ts:39)
- [src/components/predictions/PredictionsView.tsx](C:\Users\kalec\options-chatbot\src\components\predictions\PredictionsView.tsx:1478)

Suggested trades and tracked positions already persist the full pick snapshot, so this metadata can be retained without a storage redesign:

- [python-backend/positions_service.py](C:\Users\kalec\options-chatbot\python-backend\positions_service.py:160)
- [python-backend/suggested_trades_repository.py](C:\Users\kalec\options-chatbot\python-backend\suggested_trades_repository.py:93)

## B. Profitability lane

The speculative lane should be tracked as a separate cohort family, not just a scanner label.

The first implementation should stay inside the current trusted index scope:

- `SPY`
- `QQQ`

Add speculative cohorts to:

- [docs/autoresearch/truth-first-champions.json](C:\Users\kalec\options-chatbot\docs\autoresearch\truth-first-champions.json:1)

Recommended cohort shape:

- `role = "speculative_challenger"`
- separate `cohort_id`
- explicit overrides for speculative entry rules
- separate lane from `baseline_broad_control`

This allows the existing candidate bootstrap flow to work without redefining the whole system:

- [options_profit_state.py](C:\Users\kalec\options-chatbot\options_profit_state.py:148)

The key rule:

- speculative cohorts must be measured separately
- speculative cohorts must not share the same single summary verdict as the control lane

## C. Shared-state / automation lane

Today the shared state stores one top-level `latest_profit_validation` snapshot:

- [profit_loop_shared_state.py](C:\Users\kalec\options-chatbot\profit_loop_shared_state.py:235)

The automation also computes one profitability verdict per run:

- [profit_loop_automation.py](C:\Users\kalec\options-chatbot\profit_loop_automation.py:1942)

That is fine for one narrow lane, but it is the wrong shape for adding a speculative cohort with its own proof status.

Recommended state change:

- keep `latest_profit_validation` as the current control-lane summary
- add `latest_profit_validation_by_lane`
- key it by lane/cohort family, for example:
  - `control_index_call`
  - `speculative_index_call`

This avoids accidental blending of:

- control
- speculative
- future expanded symbols

## D. Forward evidence lane

The forward ledger is already the strongest part of the design for this work.

It already carries:

- `cohort_id`
- `cohort_role`
- `contract_symbol`
- exact-contract coverage metadata

Relevant file:

- [forward_options_ledger.py](C:\Users\kalec\options-chatbot\forward_options_ledger.py:1351)

So the speculative lane should reuse the existing ledger plumbing and rely on cohort-aware filtering, not invent a second evidence system.

## What Should Not Happen

Do not do any of these in the first speculative rollout:

- do not drop the core `5 DTE` minimum for the main scan lane
- do not mix speculative and control evidence into one profitability verdict
- do not widen `ALLOWED_OPTIONS_PROFIT_SYMBOLS` to the entire watchlist yet
- do not claim profitability from research-only nearest-listed or bootstrap results
- do not let speculative wins change the default lane before exact-contract proof exists

## Ticker Scope Decision

## Decision: do not expand the profitability loop to all tracked tickers now

This is the correct long-term profitability move because:

- trusted imported truth is still narrow
- authoritative exact-contract proof is still thin
- the current loop is already blocked by truth freshness
- expanding now would create more noise than trustworthy evidence

## What to do instead

### Near term

Keep the profitability loop scoped to `SPY` / `QQQ`, but allow two cohort families inside that scope:

- control
- speculative

This gives the system a clean A/B proof structure without inflating the symbol universe.

### Medium term

Only expand beyond `SPY` / `QQQ` after all of these are true for a new symbol family:

- trusted imported-daily truth exists for those symbols
- exact-contract capture is reliable
- the measurement gate is healthy
- the new symbols can be judged separately from the existing control lane

### Long term

If the loop expands, expand it in two layers:

1. `Evidence layer`
   Collect forward and exact-contract evidence for more symbols.

2. `Claim layer`
   Keep verdicts segmented by cohort family and symbol group.

That means:

- one lane can be healthy while another remains unproven
- one symbol family can be claim-ready while another stays watch-only

## Implementation Phases

## Phase 1: Speculative lane inside current proof scope

Goal:

- add a speculative scanner playbook
- add speculative metadata to picks
- add speculative cohorts for `SPY` / `QQQ`
- keep the lane watch-only

Files most likely to change:

- [supervised_scan.py](C:\Users\kalec\options-chatbot\supervised_scan.py:38)
- [options_chatbot.py](C:\Users\kalec\options-chatbot\options_chatbot.py:3888)
- [python-backend/main.py](C:\Users\kalec\options-chatbot\python-backend\main.py:326)
- [src/lib/types.ts](C:\Users\kalec\options-chatbot\src\lib\types.ts:39)
- [src/components/predictions/PredictionsView.tsx](C:\Users\kalec\options-chatbot\src\components\predictions\PredictionsView.tsx:1478)
- [docs/autoresearch/truth-first-champions.json](C:\Users\kalec\options-chatbot\docs\autoresearch\truth-first-champions.json:1)

## Phase 2: Separate profitability verdicts by lane

Goal:

- keep the control lane verdict intact
- add speculative-lane measurement snapshots
- avoid blended profitability claims

Files most likely to change:

- [profit_loop_shared_state.py](C:\Users\kalec\options-chatbot\profit_loop_shared_state.py:235)
- [profit_loop_automation.py](C:\Users\kalec\options-chatbot\profit_loop_automation.py:1942)
- [options_profit_state.py](C:\Users\kalec\options-chatbot\options_profit_state.py:16)

## Phase 3: Expand evidence scope only when truth is ready

Goal:

- broaden symbol coverage without broadening claims prematurely

Prerequisites:

- trusted imports for the new symbols
- exact-contract readiness for those symbols
- enough eligible forward evidence per symbol
- enough closed exact-contract tracked positions

Only after those prerequisites should `ALLOWED_OPTIONS_PROFIT_SYMBOLS` be widened.

## Success Criteria

The speculative-lane rollout is successful when:

- the scanner can show speculative ideas separately from normal playbooks
- speculative picks retain their cohort metadata through save/review/close flows
- speculative lane evidence is written into the forward ledger under its own cohort IDs
- the automation can report a speculative-lane profitability verdict without affecting the control lane verdict
- no code path can accidentally use speculative research wins to promote the main control lane

## Final Recommendation

Build the speculative lane now, but keep it narrow:

- separate playbook
- separate cohorts
- separate profitability measurement
- same trusted `SPY` / `QQQ` scope at first

Do not expand the profitability loop to all tracked tickers yet.

When expansion becomes justified, expand the evidence layer first and keep claims split by cohort and symbol family.
