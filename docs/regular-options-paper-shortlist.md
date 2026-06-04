# Regular Options Paper Shortlist

This report is generated from `scripts/build_regular_options_paper_shortlist.py`. It is a paper-review release gate for fresh executable Tier A lane matches, not a scanner promotion or broker-action surface.

## Summary

- Status: `paper_shortlist_readback`.
- Release gate: `no_paper_shortlist_candidates`.
- Eligible paper-review candidates: `0`.
- Invariant violations: `0`.
- Source queue rows: `97`.
- Capture bridge statuses: `{"not_tier_a": 82, "requires_fresh_executable_tier_a_match": 15}`.
- Fresh bridge statuses: `{"not_bridge_eligible": 15}`.
- Fresh bridge blockers: `{"guardrail_not_clear": 9, "lane_signature_not_matched": 8, "no_tier_a_lane_match": 15}`.
- Live policy change: `False`.

## Proof Policy

- Eligible rows require a fresh executable quote-window scanner row, clear guardrails, a lane-signature match, matched Tier A clean exact evidence, no bridge blockers, and `live_policy_change=false`.
- Tier B, Tier C, blocked, quarantine, symbol-only, stale, midpoint, EOD, fallback, and manual evidence remain non-promotable.
- This report does not change scanner, broker, stop, auth, DB, or proof behavior.

## Eligible Paper-Review Candidates

| Symbol | Playbook | Direction | Expiry | Matched Tier A lanes | Debit % | Quality | Execution label |
|---|---|---|---|---|---:|---:|---|

## Non-Eligible Fresh Matches

| Symbol | Playbook | Decision | Match | Executable | Bridge | Blockers |
|---|---|---|---|---|---|---|
| QQQ | range_breakout_observation | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| QQQ | swing | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| QQQ | volatility_expansion_observation | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| SPY | range_breakout_observation | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| SPY | swing | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| SPY | volatility_expansion_observation | clear | lane_signature | True | not_bridge_eligible | no_tier_a_lane_match |
| SPY | tracked_winner_primary | blocked | lane_signature | True | not_bridge_eligible | guardrail_not_clear, no_tier_a_lane_match |
| QQQ | bullish_momentum | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| QQQ | quality90_debit55_canary | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| QQQ | speculative | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SPY | bullish_momentum | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SPY | quality90_debit55_canary | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SPY | short_term | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SPY | speculative | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SPY | tracked_winner_observation | blocked | symbol_only | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
