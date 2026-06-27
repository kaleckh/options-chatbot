# Regular Options Paper Shortlist

This report is generated from `scripts/build_regular_options_paper_shortlist.py`. It is a paper-review release gate for fresh executable Tier A lane matches, not a scanner promotion or broker-action surface.

## Summary

- Status: `paper_shortlist_readback`.
- Release gate: `no_paper_shortlist_candidates`.
- Eligible paper-review candidates: `0`.
- Invariant violations: `0`.
- Source queue rows: `97`.
- Capture bridge statuses: `{"not_tier_a": 82, "requires_fresh_executable_tier_a_match": 15}`.
- Fresh bridge statuses: `{"not_bridge_eligible": 2}`.
- Fresh bridge blockers: `{"guardrail_not_clear": 2, "lane_signature_not_matched": 2, "no_tier_a_lane_match": 2}`.
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
| RIO | ai_commodity_infra_observation | blocked | no_symbol_sleeve | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
| SLV | ai_commodity_infra_observation | blocked | no_symbol_sleeve | True | not_bridge_eligible | guardrail_not_clear, lane_signature_not_matched, no_tier_a_lane_match |
