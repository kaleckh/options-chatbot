# Active Options Multi-Lane Performance Goal

> Retired for profitability strategy loops as of 2026-06-09. This broad operating prompt is still useful for product/runtime maintenance, but it is no longer the standing regular-options profitability objective because it can succeed without improving executable P&L. Use `docs/autoresearch/regular-options-goal.md` for clean-proof strategy work and `docs/autoresearch/fresh-executable-evidence-goal.md` for forward realized-P&L evidence collection.

Use this prompt when running an end-to-end `/goal` loop to drastically improve performance across the active options system. This is a multi-lane operating goal, not a Lane A-only strategy loop.

## Objective

Improve the active options product across every measured performance surface:

- Trading Desk runtime performance: route latency, payload size, browser responsiveness, mobile usability, and default-load work.
- Trading Desk decision performance: realized closed P&L, negative-rate reduction, open-position risk, and suggested-trade close risk.
- Live scan performance: current-candidate generation, upstream zero-candidate drops, option-liquidity drops, and guardrail starvation.
- Regular stock-options proof performance: clean promotable evidence under the frozen evaluator, not raw trade count.
- Bullish Pullback operating performance: paper/live-shadow harness quality, layer-stack wiring, and exact-contract execution safety.
- AI commodity proof-lane performance: exact Alpaca SIP/OPRA history depth, capture reliability, proof-universe alignment, and guarded replay readiness.
- Engineering performance: smaller hot modules, fewer duplicate data paths, no hidden state mutations, and faster verification loops.

A loop succeeds only when it produces a measured improvement, removes a blocker with evidence, or retires a branch strongly enough that future loops will not waste time repeating it.

## Scope

Active scope:

- Regular supervised options browser product: live scan, replay diagnostics, suggested trades, tracked-position review, and Trading Desk UX.
- Regular stock-options research/proof lanes that feed the active product.
- AI commodity / commodity-infrastructure options proof lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`.

Out of scope unless explicitly reopened by the operator:

- crypto options
- Polymarket
- day-trading

Shared infrastructure may touch adjacent files only when required for the active regular options product or AI commodity proof lane.

## Goal Health Check

This goal is doing what the operator wants only if each turn keeps the full lane map visible while making progress on one measurable slice. Before editing, write a short lane-status snapshot covering:

- regular product safety and Trading Desk runtime
- live scan starvation
- regular clean-proof / autoresearch
- Bullish Pullback operating harness
- AI commodity OPRA proof lane
- engineering maintainability / verification cost

Use this compact shape so the lane map is visible in every resumed or fresh run:

| Lane | Current evidence | Status | Next implication |
| --- | --- | --- | --- |
| Regular product safety / runtime | artifact, route probe, or scorecard field | improved this turn / active slice / blocked / not touched | what this means now |
| Live scan starvation | artifact or command output | status | what this means now |
| Regular clean-proof / autoresearch | artifact or score line | status | what this means now |
| Bullish Pullback operating harness | artifact or living-doc blocker | status | what this means now |
| AI commodity OPRA proof | readback guard or scorecard field | time-gated / blocked / active slice | exact allowed or not-before action |
| Engineering maintainability / verification cost | file/module/test evidence | status | what this means now |

For each lane, record one of: improved this turn, active slice, time-gated, blocked by named artifact, or not touched with reason. If the work only touches one lane, explicitly say why that lane is the highest-priority slice and which artifacts prove the other lanes were not ignored.

Do not treat the goal as healthy merely because useful work happened. It is healthy only when the next action is chosen from current evidence, lane blockers are not stale, and completed work writes back to the scorecard, living docs, or a generated report that future loops will read.

Named priorities from older goal text or previous turns are starting hypotheses, not permanent orders. Re-check rows, artifacts, ports, generated reports, and guard states before acting on a named item such as a position ID, suggested trade ID, stale route metric, specific sleeve, or time-gated OPRA command. If the latest evidence no longer supports that item as the highest-value slice, record why and choose the current blocker instead.

On continuation after compaction, interruption, or a new user message, first re-read the newest user request and current artifacts. Continue the previous in-progress slice only if it is still the highest-priority actionable slice under the fresh lane table; otherwise switch and explain the evidence that changed the priority.

## Start Every Run

Before editing code, read the repo startup docs and establish a baseline:

```powershell
python scripts/build_regular_profitability_operating_scorecard.py --json
python scripts/evaluate_regular_options_autoresearch.py --no-write --score-line
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
```

Use the latest artifacts as the scoreboard:

- `docs/regular-options-operating-scorecard.md`
- `data/profitability-lab/regular-options-operating-scorecard/latest.json`
- `data/forward-tracking/trading_desk_api_performance_latest.json`
- `data/forward-tracking/regular_guardrail_starvation_latest.json`
- `data/forward-tracking/regular_open_position_risk_latest.json`
- `data/forward-tracking/suggested_trade_close_risk_latest.json`
- `data/profitability-lab/regular-options-autoresearch/ledger.jsonl`
- `data/ai-commodity-infra/progress/latest.json`

Do not rely on stale prose when the scorecard or generated artifacts disagree with it.

For short status or follow-up turns, it is acceptable to read the latest artifacts instead of rerunning every baseline command, but do not make a fresh performance or proof claim from an artifact that the current change could have invalidated. Time-gated commands must follow the generated readback and exact not-before time.

## Per-Turn Operating Loop

At the start of each turn, choose one measurable slice instead of trying to advance every lane at once.

1. Reconfirm the current guard state and lane map.

   Check whether any time-gated lane is safe to run now, especially AI commodity OPRA readbacks. If a guarded command is not safe, record the exact not-before time and move to the next measurable regular-options blocker. Update the lane-status snapshot so a single-lane slice cannot masquerade as a full-system audit.

2. Pick the highest-priority actionable slice.

   Prefer P0 truth or safety issues first, then the largest measured runtime or payload bottleneck, then proof-lane blockers that can be reduced without weakening evidence standards. Name the lane or lanes touched before editing, cite the artifact path or command output that made this slice highest priority, and cite the reason any apparently urgent lane is waiting.

3. Define the expected proof of improvement.

   Before changing code, identify the metric, artifact, route, test, or report that will prove the slice improved. Examples: open-risk counts, stale suggested-review counts, route payload bytes, backend duration header, starvation status, quote coverage, unresolved-candidate count, zero-bid rate, frozen evaluator score line, or AI commodity shared OPRA dates.

4. Make the smallest complete change.

   Keep edits narrow enough that the verification evidence still maps directly to the chosen slice. Do not combine unrelated profitability tuning, UI polish, and architecture cleanup unless they are part of the same measured bottleneck.

5. Verify and write back.

   Run the smallest relevant test or audit, compare before/after numbers, update `docs/WORKLOG.md`, and update living docs when their owned facts changed. If a generated dashboard/report owns the metric, regenerate it.

## Ordered Work Plan

Work in this order unless a fresh scorecard shows a more urgent P0 safety issue.

1. Baseline and instrumentation

   Confirm the scorecard, route-performance artifact, open-risk artifact, suggested-risk artifact, starvation audit, frozen evaluator, and AI commodity readback all run or fail with an actionable error. Fix missing measurement before optimizing.

2. Truth, safety, and mutation boundaries

   Remove any mismatch between UI badges, API status, tracked-position storage, proof-summary storage, and options-profit status. Passive UI reads must stay read-only. State-changing endpoints such as position review or close flows require explicit user action and executable quote evidence.

3. Trading Desk runtime and browser performance

   Attack the largest measured payloads and slowest routes first. Current known hot spots include the closed tracked-position window payload, default `PredictionsView.tsx` data/mutation surface, Trading Desk component weight, and browser QA on desktop/mobile after backend restart. Keep behavior stable while reducing default work.
   When browser QA is the active slice, exercise desktop and mobile, archive-gated tabs, and any expanded drawer/detail states that own the acceptance signal; a collapsed header alone is not proof for drawer-owned badges or metrics.

4. Open position and suggested-trade risk

   Resolve operator-facing safety follow-ups before strategy tuning. Re-review open rows only through explicit executable quote paths, especially non-executable display-only `SELL` states. Refresh stale or missing suggested-trade reviews before using suggested-trade P&L or close state.

5. Live scan starvation across all regular playbooks

   Use the all-regular starvation audit before loosening guardrails:

   ```powershell
   python scripts/audit_regular_guardrail_starvation.py --top-limit 8
   ```

   If the audit says upstream zero-candidate pressure, investigate direction filters, option liquidity, momentum, history/liquidity, and tech-score drops first. Do not weaken promoted entry guardrails merely because the current scan returned zero picks.

6. Trading Desk profitability repair

   Keep promoted guardrails that improved realized Trading Desk metrics unless a replay proves they are harming more winners than losers. Any new entry or exit rule must be replayed against both avoided losers and lost winners using trusted executable evidence. Do not promote broad exit-policy changes from stale legacy rows alone.

7. Regular multi-lane clean proof

   Do not collapse the proof loop to Lane A. Lane A is one diagnosed blocker: priced-only economics fail conservative side-aware zero-bid replay. The next clean-proof attempt should target genuinely non-overlapping regular stock-options sleeves or a materially different exit/liquidity rule that can add at least `43` strict-new clean trades over the `157` clean baseline.

   Use these gates before claims:

   ```powershell
   python scripts/run_regular_options_multilane_portfolio.py
   python scripts/evaluate_regular_options_autoresearch.py --no-write --score-line
   python scripts/run_regular_options_all_planned_sleeves.py
   ```

   Count feasibility is not clean promotion. Raw `200+` rows, midpoint fills, daily/EOD evidence, stale snapshots, and research/backfill paper rows do not satisfy production proof.

8. Bullish Pullback operating layer

   Treat Bullish Pullback as one lane family inside the regular product. Wire the layer stack into paper-shadow reporting and harness selection before expanding risk. Add assignment/expiration-safe live-shadow handling, leg-level bid/ask execution audits, partial-window robustness, and explicit paper/live-shadow separation before sizing claims.

9. AI commodity OPRA proof lane

   Follow the generated guarded command, not memory. First run:

   ```powershell
   python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
   ```

   If and only if the readback says the guarded command is safe, run the exact allowed command and then read back again. Repair the failed full-universe `2026-05-26` capture before replay or filter tuning. Keep production filters locked until exact Alpaca SIP/OPRA bid/ask history reaches the required depth, exact replay runs, and live/proof candidates exist inside the proof universe.

10. Architecture and maintainability performance

   Reduce hot monoliths only when the extraction lowers runtime cost, risk, or verification burden. Current high-value targets are `PredictionsView.tsx`, `python-backend/main.py`, `options_chatbot.py`, `wfo_optimizer.py`, and `scripts/run_ai_commodity_opra_progress.py`. Each split must preserve route contracts and evidence semantics.

## Lane Rules

- Treat every regular playbook as its own lane unless an artifact explicitly says it is a single-lane audit.
- Use `scripts/audit_zero_pick_days_all_lanes.py` for all-lanes zero-pick claims.
- Use `scripts/run_regular_options_multilane_portfolio.py` before trade-count claims.
- Use the frozen evaluator before clean-promotion claims.
- Use the operating scorecard before answering whether performance improved.
- Do not tune failed simple shapes again unless a new causal rule changes the failure mode.
- Keep a cross-lane blocker ledger current. If a turn does not directly improve a lane, it should either explain why that lane is time-gated or convert its blocker into a concrete next action.
- Do not call a turn "multi-lane" unless it either changes multiple lanes or reports the current blocker/artifact state for every active lane before choosing the one lane to change.

## Evidence Rules

Proof claims require trusted intraday OPRA/NBBO exact-contract evidence. Do not promote:

- midpoint-only fills
- last-trade evidence
- stale snapshots
- daily/EOD rows
- lifecycle-only closes
- unresolved candidates
- bar-only AI commodity research
- research/backfill paper rows as live-production proof

For tracked positions, distinguish executable exit P&L from paper or display-only mark P&L.

## Acceptance Criteria

Each completed loop must include:

- baseline scorecard and post-change scorecard, or a clear reason the scorecard could not run
- files changed and why they address the measured bottleneck
- artifacts generated or updated
- verification commands and results
- a concise statement of which metric improved, which blocker was removed, or which branch was retired
- docs updates in `docs/WORKLOG.md` and any living doc whose owned facts changed
- an updated operating dashboard/report when proof gates, live-product metrics, quote coverage, zero-bid rate, unresolved candidates, open risk, latency, cache stats, or starvation state changed

Do not call the goal complete while any P0 truth, mutation, proof-source, or user-visible risk issue remains unresolved.

Before marking the goal complete, build a completion ledger from the original objective and current living docs. For each explicit requirement, record the authoritative evidence that proves it, such as a current artifact, command output, test, route probe, rendered UI check, or generated report. Treat missing, stale, indirect, or partial evidence as incomplete work.

## Stop Rules

Stop and change approach when:

- two consecutive experiments improve raw count but fail the frozen proof gates for the same reason
- a branch improves one metric by weakening evidence quality
- a route optimization hides required provenance, quote, or review state
- a scan change produces picks by bypassing promoted guardrails instead of fixing upstream drops
- an AI commodity change tries to tune filters before exact OPRA replay unlocks

When a branch fails, preserve the artifact and write the reason plainly so the next loop does not re-run the same dead end.
