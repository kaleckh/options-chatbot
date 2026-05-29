# Options Trading Sprints

Archive note: this is a historical sprint record. It predates the current scope decision in `../DECISIONS.md`; treat references to active crypto or day-trading work as archived context unless the user explicitly reopens that lane.

Goal: simple, supervised options maintenance and controlled trade evaluation.

Last updated: 2026-04-03

This document is options-only.

For the then-active crypto research lane, this record pointed to:
- `docs/day-trading-current-state.md`

The product loop stays intentionally narrow:
1. Scan for live options trades.
2. Surface only the ideas we trust most right now.
3. Let the user choose which trade they actually took.
4. Track the position and return HOLD or SELL.
5. Compare real tracked outcomes against replay expectations.

At the time, the crypto profitability pilot lived separately in the day-trading docs and scripts. This file stayed focused on the options maintenance lane.

## Sprint 1: Replay-Backed Trade Policy

Status: completed.

Purpose:
- Turn the scanner into a deployment gate instead of a generic idea list.
- Label live picks as Approved, Watch, or Blocked from replay evidence.
- Bias the supervised workflow toward the cohorts that actually held up in backtests.

Scope:
- Build a replay-backed live trade policy from the experiment matrix.
- Apply the policy to live scan picks.
- Show the hard gate, preferred context, and decision counts in the scanner.
- Carry the policy decision and rationale into the take-trade flow.

Delivered:
- live trade policy from the latest saved replay
- scanner default mode: replay-backed focus
- policy decisions: `approved`, `watch`, `blocked`
- replay-derived hard filters and preferred context carried into the scanner
- watch-only fallback when the latest saved policy is not ready to promote

Success bar:
- The scanner defaults to replay-backed focus mode.
- Approved and Watch picks are clearly separated from blocked ideas.
- The user can still switch back to the broader all-qualifying scanner when needed.

## Sprint 2: Horizon Playbooks + Portfolio Guardrails

Status: completed in practical product form.

Purpose:
- Support short-term and swing-style options decisions without turning the product into a complex optimizer.
- Reduce overtrading and correlated exposure.

Scope:
- Add playbooks for short-term and swing options holds.
- Cap new positions per day and repeated exposure by ticker, sector, and regime.
- Add a suggested size tier next to approved scan picks.
- Replay-validate exits for only the approved entry slices.

Delivered:
- playbooks: `short_term` and `swing`
- portfolio guardrails against actual open tracked positions
- size tiers: `starter`, `half`, `full`, `blocked`
- blocked-idea inspection toggle in the scanner
- playbook exit-audit report for approved/watch/blocked cohorts

Note:
- the exit-audit report is now available
- a deeper baseline-comparison harness against alternate exit models is still optional future work, not a blocker for current supervised testing

Success bar:
- The user can choose a simple trading horizon.
- The product avoids surfacing multiple versions of the same bet.
- Exit behavior is measured against hold-to-target and time-exit baselines.

## Sprint 3: Options Truth-First

Status: completed.

Purpose:
- Make the options system truthful before adding more promotion logic.
- Tighten tracked-position integrity so live outcomes are worth trusting.
- Make the main supervised workflow visually obvious.

Scope:
- Align docs and UI copy to the latest saved truth bundle.
- Carry source metadata more clearly through truth outputs.
- Persist exact contract identity when available.
- Remove silent nearest-strike substitution for tracked positions.
- Harden review and close validation.
- Demote legacy analytics behind scanner and tracked positions.

Delivered:
- current docs now reflect the latest saved replay, metric-truth report, live policy, and exit audit
- live policy and exit audit now expose clearer source metadata
- tracked positions persist `contract_symbol` when the scanner provides it
- review logic now requires the exact contract or exact stored strike
- invalid close/review inputs now fail clearly
- scanner and tracked positions now lead the options UI, with suggested trades explicitly labeled hypothetical

Success bar:
- Product messaging no longer overstates readiness.
- Real tracked positions are reviewed against the exact contract when possible.
- Missing exact pricing returns warnings instead of synthetic substitutes.
- The next context window can read the docs and get the same answer the current code would give.

## Sprint 4: Live Cohort Scorecard

Status: next, but intentionally deferred.

Purpose:
- Close the loop between research and supervised deployment.
- Promote or pause trade cohorts based on actual tracked outcomes.

Scope:
- Tag every tracked trade with its entry cohort.
- Compare live realized P&L against replay expectations.
- Add weekly cohort promotion, pause, and probation states.
- Keep single-name winners as watchlist context unless they keep proving themselves.

Success bar:
- The policy can evolve from actual supervised usage instead of static backtests.
- Weak cohorts can be paused without changing the whole system.
- New tickers and slices enter through probation instead of immediately going live.

Note:
- this remains an options maintenance roadmap, not the primary systematic research lane
- the primary active research lane is the crypto spot profitability pilot
