# Goal-Prompt Rotation - Post-Sprint Operating Loop

Prerequisite: Sprint 1-2 of `docs/sprint-plan-2026-06-09.md` complete: working
flywheel-or-archived, evaluator gradient, and truthful metrics. Until then, only Prompts 2 and 3
from the sprint plan are worth running.

## Why A Rotation Instead Of One Big Prompt

The audit showed what happens with a single standing "improve profitability" prompt: it sprawls to
seven surfaces, succeeds without touching P&L, optimizes whatever proxy is easiest, and goes stale
against the decision log. The fix is several narrow prompts, each owning one metric, run on a
schedule, with the realized-evidence cohort flowing between them as the shared currency.

```text
        +----------------------------------------------------+
        |  HEARTBEAT (always on): Fresh Executable Evidence  |
        |  output: realized cohort (n, PF, avg P&L, by lane) |
        +----------------------+-----------------------------+
                               |
                               | cohort numbers pasted verbatim into
   +---------------+-----------+------------+--------------------+
   v               v                        v                    v
WEEKLY          MONTHLY                 MONTHLY            EVERY 3 LOOPS
Strategy        Lane Lifecycle &        Execution           Meta Loop Audit
Hypothesis      Portfolio Review        Quality Truth       (direction check)
(1 hypothesis,  (promote/demote/        (modeled vs         (is the loop itself
 1 lane)         retire lanes)           realized friction)   gaming or stale?)
```

## Invariants For Every Prompt In The Rotation

Copy these into each prompt. Never relax them.

- Evidence: trusted intraday OPRA/NBBO exact-contract, side-aware executable pricing. Never
  midpoint, last-trade, daily/EOD, stale-snapshot, or unresolved rows. Executable exit P&L, never
  paper marks.
- One objective, one owned metric, stated baseline to target.
- Sample floor: no PF comparison under 30 trades; no keep/kill call under 20. Below floor, the only
  valid verdict is `insufficient_sample`.
- Pre-register the hypothesis before looking at results. One hypothesis per loop.
- Stop rule in every prompt. "The bar is unreachable, here's why and what it costs to fix" is a
  successful outcome.
- Never run two strategy loops against the same lane in parallel.
- Realized-cohort numbers feed forward verbatim: no summarizing, no rounding into prose.

## R0 - Heartbeat: Fresh Executable Evidence (Always On)

This is Prompt 2 from the sprint plan, promoted to a standing daily routine. Its output, the
realized cohort ledger (`n`, executable PF, avg P&L, per lane, per month), is the baseline input
every other prompt cites. If the heartbeat stops because the feed is down, the governor is blocked,
or there are zero fill attempts, every other loop in the rotation pauses. Replay work done while the
heartbeat is down is rearranging old research.

Standing addition once more than 20 rows exist:

```markdown
## Cohort Report (Append To Every Heartbeat Readback)

- rows total / this week, by lane
- executable PF and avg P&L per lane (USD-based), flagged `collecting (n=X)` under 20 rows
- modeled-at-entry P&L vs realized P&L per row (feeds R3)
- blockers that prevented fill attempts this week, ranked by count
```

## R1 - Weekly: Strategy Hypothesis Loop

Prompt 1 from the sprint plan is the template. Per cycle, fill in three slots and change nothing
else:

```markdown
# Strategy Hypothesis Loop - {date}

## Baseline (from heartbeat cohort + evaluator, verbatim)

{paste: lane, n, conservative PF, stress PF, clean count, last cycle's verdict}

## This Cycle's Single Hypothesis (Pre-Registered)

LANE: {one lane - must have >=30 exact OOS trades available, else pick a different lane}
HYPOTHESIS: {one sentence, causal: "X improves executable P&L because Y"}
CHANGE: {the one parameter/rule/universe change that tests it}

## Success / Failure (Decide Before Running)

- SUCCESS: {owned metric} moves from {baseline} to >= {target} on >=30 OOS trades,
  conservative side-aware pricing, with stress PF >= {floor}.
- FAILURE: anything else. Record the verdict and the realized numbers in the ledger either way.

## Constraints

{the standing invariants + Prompt 1's anti-gaming list: no Lane A, coverage doesn't count,
 chronological splits, no post-OOS parameter changes}

## Stop Rule

Two consecutive failed cycles on the same lane => stop tuning that lane; hand the lane to R2
with verdict `tuning_exhausted` and pick a different lane or hypothesis class next cycle.
```

Scheduling rule: the lane with the most fresh realized evidence gets the slot. Right now that queue
is `volatility_expansion` first, to grow the sample to 30+ before any tuning, then whatever R2
promotes.

## R2 - Monthly: Lane Lifecycle & Portfolio Review

This owns the portfolio-level decision the repo previously did not make explicitly: which lanes
deserve evidence budget at all. It runs against the monthly command center:
`scripts/build_monthly_all_lanes_profitability_audit.py`.

```markdown
# Lane Lifecycle Review - {month}

## Objective

Assign every lane exactly one disposition for next month, from realized + exact-replay evidence:

grow
: Positive executable PF on >=20 realized or >=30 exact replay trades. Gets heartbeat priority and
  the R1 slot.

collect
: Positive signal but under sample floor. Gets paper-evidence budget only, no tuning.

probation
: Negative but with a pre-registered regime/condition hypothesis that explains it. One month to
  show sign improvement, else retire.

retire
: Negative with `tuning_exhausted` or two failed probations. Archive with a dated `DECISIONS.md`
  entry. Retired lanes stop appearing in goal prompts entirely.

## Rules

- Dispositions use USD-based executable PF only. Replay PF may argue for `collect`, never `grow`.
- A lane may not stay in `probation` or `collect` more than 2 consecutive reviews: up or out.
- New-lane slots: at most {1} `collect` lane may be added per month, and only via R4.
- The review's output table (lane, n, PF, avg, disposition, reason) goes in DECISIONS.md verbatim.

## Stop Rule

If after this review fewer than 2 lanes are `grow`/`collect`, the deliverable is not more lanes.
It is a strategy-class question for the operator: which structurally different trade families
(R4 candidates) are worth incubating, with what data cost.
```

## R3 - Monthly: Execution Quality Truth

This closes the loop that the WFO-friction fix opens: is the friction model still honest?

```markdown
# Execution Quality Truth - {month}

## Objective

Reconcile modeled vs realized friction on the month's realized cohort. Owned metric:
mean |modeled P&L - realized P&L| per trade, and its sign bias.

## Loop

1. For every realized row: modeled-at-entry expected P&L vs executable realized P&L. Decompose the
   gap into spread cost, slippage vs quote, fees, and timing.
2. If mean absolute gap > {2%} of premium or sign bias > {1%}: update the friction parameters in
   `_simulate_window` to match observed reality, re-run the affected sleeve's WFO, and report which
   currently selected parameters survive.
3. Flag any lane whose realized PF is more than {0.3} below its replay PF on >=20 rows as
   `replay_optimistic`; that lane's replay evidence is downgraded in R2 until explained.

## Constraint

The friction model may only be made more pessimistic by this loop without operator sign-off.
Loosening it requires a written case from >=50 realized rows.
```

## R4 - As Needed: New-Lane Incubation (Max 1 Active)

This is how volatility-expansion-style candidates enter without flooding the portfolio:

```markdown
# New Lane Incubation - {name}

## Pre-Registration (Before Any Backtest)

- Trade family + one-sentence economic rationale (why does the counterparty lose?)
- Universe, data requirement, and import cost
- Kill criteria, decided now: exact-replay PF < {1.2} on first {50} trades => archive, no retuning

## Gates (In Order; No Skipping)

diagnostic
: Exact-contract replay on trusted intraday history, >=50 trades, conservative pricing.

paper
: Heartbeat shortlist inclusion, >=20 realized paper rows.

collect
: Enters R2 as `collect`; subject to its up-or-out rule thereafter.

## Constraint

One incubation lane at a time. A new one starts only when the current one promotes or archives.
```

## R5 - Every 3 R1 Loops: Meta Loop Audit (Direction Check)

This generalizes sprint Prompt 3 into a recurring health check. The audit that caught the dead
flywheel, the 0.00-score tie, and the coverage hack should not be a one-off.

```markdown
# Meta Loop Audit - Every 3rd Strategy Cycle

Operator session. Loop-code edits allowed.

## Questions (Answer Each With Evidence, File:Line)

1. GAMING: rank the last 3 cycles' variants by progress_score and by raw executable P&L
   separately. Did any variant climb the score without moving P&L? If yes: name the term being
   gamed, patch the score, add the regression test.
2. STALENESS: do any standing prompts, harness defaults, or hardcoded goal strings contradict the
   newest DECISIONS.md entries? This is how Lane A kept being tuned after retirement.
3. DEAD MACHINERY: list every gate/loop/lane whose last state-change is >20 business days old.
   Each gets: repair, archive, or an explicit dated waiver. Silently-blocked is not allowed.
4. DIRECTION: of the last 3 cycles' outputs, how many produced fresh executable evidence vs
   rearranged historical replays? If 0 of 3 produced fresh evidence: pause R1, route all effort to
   the heartbeat's top blocker, and say so in WORKLOG.

## Output

A dated entry in DECISIONS.md: what was gamed/stale/dead, what changed, and the one number that
must move by the next meta audit.
```

## First 6 Weeks After The Sprints

| Week | Running |
|---|---|
| 1 | R0 daily. R1 slot -> grow volatility_expansion sample (collect-only, no tuning: it is at n=24, floor is 30). R3 baseline pass on whatever realized rows exist. |
| 2 | R0. R1 -> first real hypothesis on whichever lane crossed 30 realized/OOS trades. |
| 3 | R0. R1 cycle 2. R5 meta audit #1 after 3 R1 slots including week 1. |
| 4 | R0. R1 cycle 3. R2 lifecycle review #1: first real promote/retire pass; expect several `retire` verdicts given the PF 0.34 baseline. R3 #1 with a month of cohort data. |
| 5 | R0. R1 on R2's `grow` pick. R4 opens its single incubation slot if R2 left fewer than 2 viable lanes. |
| 6 | R0. R1. R5 meta audit #2. If both audits show no fresh-evidence progress, the handoff branch's own rule applies: stop lane tuning, fix the machinery. |

## What This Rotation Deliberately Does Not Do

- No "improve every metric" prompt exists anywhere in it. Each prompt owns one number.
- No prompt may cite coverage, trade count, latency, payload size, or UX as progress.
- No live-trading authorization is implied anywhere. Promotion past `collect` is an operator
  decision with R2's table as input.
