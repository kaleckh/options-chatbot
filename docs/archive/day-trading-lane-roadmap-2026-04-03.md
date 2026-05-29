# Day Trading Lane Product Roadmap

Last updated: 2026-04-03

## Status Note

This roadmap is historical planning context.

It references day-trading routes and UI files that are not present in the current worktree. Use `docs/day-trading-current-state.md` for the current status of the lane, and treat the implementation references below as archived intent rather than a live route map.

## Already Shipped

- In-app preflight console
- Ticket desk in the crypto lane
- Snapshot ticket summary and artifact-drift warning

Main files already carrying this surface:
- `src/components/strategy/DayTradingLab.tsx`
- `src/app/api/day-trading/preflight/route.ts`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/types.ts`

## Phase 1: Complete The In-App Supervised Workflow

Priority: highest impact, lowest coordination cost

Goal:
- keep the user inside the lane from approval to logged review

Deliverables:
- add in-app journal submission for the BTC pilot
- prefill journal fields from approved tickets where possible
- show recent logged trades and pilot eligibility state in the UI
- refresh ticket/journal state after submit so the lane shows `approved -> used`

Likely files:
- `src/app/api/day-trading/journal/route.ts`
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/index.js`
- `src/lib/types.ts`
- `tests/day-trading/crypto-engine.test.js`

Notes:
- this is the missing half of the workflow that still lives in `npm run daytrading:journal:add`
- the UI should stay explicit and supervised; no autonomous execution logic belongs here

## Phase 2: Make The Watchlist Operational

Priority: high impact, moderate cost

Goal:
- make the watchlist behave like a live intraday console instead of a manual refresh table

Deliverables:
- polling during the active Denver session
- countdown to session open/close
- stronger stale-data emphasis and last-trusted-bar age
- explicit notify state changes when tickets are exhausted or regime blockers activate

Likely files:
- `src/components/strategy/DayTradingLab.tsx`
- `src/app/api/day-trading/watchlist/route.ts`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/types.ts`

Notes:
- keep polling scoped to the active lane and avoid background loops outside the page

## Phase 3: Replace Generic Ranking With Pilot-Aware Ranking

Priority: high impact, moderate-to-high cost

Goal:
- rank what is actually tradable under the BTC pilot, not what merely scores well in a generic replay table

Deliverables:
- weight regime fit, freshness, cost-to-target, daily-cap state, and execution viability
- expose ranking reasons in the watchlist payload
- distinguish `research leader` from `live candidate`

Likely files:
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/engine.js`
- `src/lib/types.ts`
- `tests/day-trading/crypto-engine.test.js`

Notes:
- keep legacy equities behavior intact unless intentionally migrated

## Phase 4: Surface Experiment Controls In The Lab

Priority: medium impact, medium cost

Goal:
- let the UI drive the research controls that already exist in code

Deliverables:
- add an experiments API surface for the crypto lane
- expose window modes, control-first settings, and family-level results in the UI
- compare latest experiment output against the current live operating plan

Likely files:
- `src/app/api/day-trading/experiments/route.ts`
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/day-trading/index.js`
- `src/lib/types.ts`

Notes:
- keep default experiments narrow and honest; do not re-open broad sweeps by accident

## Phase 5: Clean Up Artifact And Schema Drift

Priority: medium impact, low-to-medium cost

Goal:
- stop mixing old multi-window artifacts with the new BTC-first fixed-session pilot

Deliverables:
- add explicit artifact versioning for crypto strategy/watchlist outputs
- provide a migration or regeneration path for old watchlist/strategy files
- show artifact timestamps and compatibility state in the lane

Likely files:
- `src/lib/day-trading/crypto-engine.js`
- `scripts/run_day_trading_watchlist.js`
- `scripts/run_day_trading_pilot.js`
- `docs/day-trading-current-state.md`
- `tests/day-trading/crypto-engine.test.js`

Notes:
- the warning banner is already in place; this phase removes the root cause

## Phase 6: Add Review And Behavior Coaching

Priority: medium impact, higher product complexity

Goal:
- convert the lane from a toolset into a disciplined review loop

Deliverables:
- behavior summaries from journal entries
- mistake clustering by regime, timing, and execution quality
- adaptive post-trade prompts based on actual trade path

Likely files:
- `src/components/strategy/DayTradingLab.tsx`
- `src/lib/day-trading/crypto-engine.js`
- `src/lib/types.ts`
- `tests/day-trading/crypto-engine.test.js`

Notes:
- only build this after Phase 1 and Phase 2 are in place; otherwise the feedback loop is too thin

## Recommended Execution Order

1. Ship in-app journal logging and recent journal state.
2. Add live watchlist polling and session countdowns.
3. Rework watchlist ranking for pilot-fit instead of generic score.
4. Expose experiment controls once the live workflow is complete.
5. Remove stale artifact drift with versioning and migration.
6. Layer in review coaching after the lane has reliable operational data.
