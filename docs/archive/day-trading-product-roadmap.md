# Day Trading Product Roadmap

Last updated: 2026-04-03

## Status Note

This is a dated roadmap, not the current browser implementation contract.

Some route and UI references in this file are not present in the current worktree. Use `docs/day-trading-current-state.md` for the current lane status before treating any item below as active.

## Goal

Turn the crypto day-trading lane from a read-heavy research console into a tight operator workflow:

1. scan
2. permission
3. execution logging
4. review
5. research iteration

The operating principle stays the same:
- truth capture matters more than trade frequency
- the user stays in control of execution
- the lane should make process breakdowns obvious

## Current Status

Completed:
- crypto-first lane selection in the UI
- profitability pilot dashboard
- in-app preflight console
- in-app ticket desk
- artifact drift warning for stale saved strategy/watchlist bundles

In progress now:
- in-app journal logging against approved same-day BTC tickets

## Roadmap

### Phase 1: Workflow Completion

Objective:
- finish the operator loop inside the app

Scope:
- add `POST /api/day-trading/journal`
- add a `Journal Trade` panel in `DayTradingLab`
- seed journal inputs from approved tickets
- refresh snapshot and watchlist after journal submission

Primary files:
- `src/app/api/day-trading/journal/route.ts`
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/index.js`
- `tests/day-trading/crypto-engine.test.js`

Why first:
- this closes the highest-value missing loop
- it improves pilot truth immediately
- the backend logic already exists and is stable

Acceptance:
- a user can request a ticket, log the trade in-app, and see ticket usage plus pilot metrics update without touching CLI scripts

### Phase 2: Live Operator Console

Objective:
- make the lane feel alive during session hours

Scope:
- add watchlist polling during active session windows
- show session countdowns and last-refresh age
- expose bar freshness more prominently
- surface preflight and journal success/failure as lane-local status, not only inline form output

Primary files:
- `src/components/strategy/DayTradingLab.tsx`
- `src/app/api/day-trading/watchlist/route.ts`

Why second:
- better intraday ergonomics
- faster decision feedback
- low coupling to strategy logic

Acceptance:
- the lane updates itself during live windows and makes stale/closed-session state obvious

### Phase 3: Pilot-Aware Ranking

Objective:
- rank setups by what is actually tradable and promotable now

Scope:
- replace generic legacy-style ranking weight with pilot-specific factors:
  - ticket availability
  - current regime fit
  - execution cost quality
  - freshness
  - adherence evidence
  - disqualification pressure
- separate `research leader` from `live-ready now`

Primary files:
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/engine.js` only if shared helpers need to move
- `src/components/strategy/DayTradingLab.tsx`
- `tests/day-trading/crypto-engine.test.js`

Why third:
- ranking should use real execution truth, not just replay score
- that truth gets stronger once journal logging is live

Acceptance:
- the top of the watchlist reflects live process fitness, not only historical replay performance

### Phase 4: Session-Native Review

Objective:
- make post-trade review and session review part of the product, not an external habit

Scope:
- add grouped review views:
  - today
  - this week
  - by regime
  - by mistake tag
- show journal-linked disqualification causes and rule-adherence drift
- add operator summaries like:
  - late entries
  - taker creep
  - repeat blockers

Primary files:
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/types.ts`

Why fourth:
- by this point the lane has enough in-app truth to review meaningfully

Acceptance:
- the user can review today’s process failures without opening raw JSON artifacts

### Phase 5: Research Controls In-App

Objective:
- bring the strongest research controls out of scripts and into the lab

Scope:
- add experiment runner controls for:
  - bars
  - window modes
  - strict mode
  - control-first batch settings
- surface experiment report summaries and family-level outcomes in the UI

Primary files:
- `src/components/strategy/DayTradingLab.tsx`
- `src/app/api/day-trading/route.ts`
- `src/lib/day-trading/crypto-engine.js`

Why fifth:
- this expands the research surface without distracting from the live workflow

Acceptance:
- the app can run and explain controlled crypto experiments without dropping to CLI

## Build Order

1. Finish in-app journal logging
2. Add polling and session timing
3. Rework ranking around pilot truth
4. Add review-native summaries
5. Expose experiment controls

## Risks

- `DayTradingLab.tsx` is becoming a large component and may need decomposition once phases 2 and 4 land
- strategy/watchlist artifact drift needs eventual migration work, not just warning copy
- the crypto lane still shares some generic legacy ranking and paper-trade plumbing that should be isolated more cleanly over time

## Decision Rule

If a candidate improvement makes the lane feel more “alive” but does not improve truth capture, it should come after workflow completion and journal-backed review.
