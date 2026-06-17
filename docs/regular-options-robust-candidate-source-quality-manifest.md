# Regular Options Robust Candidate Source-Quality Manifest

This report is generated from `scripts/build_regular_options_robust_candidate_source_quality_manifest.py`. It classifies the current high-priority `candidate_source_quality_repair` blockers from the regular-options historical walk-forward workflow. It is read-only and does not import quotes, mutate evidence stores, edit source-quality policy, change scanner or proof rules, consume protected holdout, or claim production proof.

## Summary

- Status: `blocked_non_promotable_observe_only`.
- High-priority rows: `3` (`combined_portfolio, lane:bullish_pullback_core, lane:lane_a_chain_native_ret20_4_stop200_time75`).
- Walk-forward status: `historical_walkforward_ran_candidates_blocked`.
- Robust-search status: `historical_candidates_blocked`; ready candidates `0` / `3`.
- Accepted exact trades: `231`.
- Source-quality gate: `source_quality_gate_blocked`; scope-policy exclusions `3`.
- Combined final holdout: `N=28`, PF-LB `0.61`, selection-adjusted bar `1.18`.
- Protected holdout starts `2026-06-05`; overlap `False`.
- Proof/gate status: `blocked_non_promotable_observe_only`; promotion allowed `False`.

## Row Classifications

| Row | Priority | Classes | Key Metrics | Permission Summary |
|---|---|---|---|---|
| `combined_portfolio` | `high` | `importable_missing_quote_candidate`, `importable_missing_quote_candidate`, `no_chain_native_spread_selection_gap`, `observed_zero_bid_tradability_kill_candidate`, `observed_zero_bid_tradability_kill_candidate`, `paper_shadow_evidence_gap`, `pure_statistical_sample_blocker`, `source_quality_pending` | total N 231; holdout N 28; holdout PF 1.2725; PF-LB 0.61 | not_actionable_without_forward_evidence, read_only_research_ok, requires_explicit_approval_before_evidence_store_mutation, requires_policy_change_approval |
| `lane:bullish_pullback_core` | `high` | `importable_missing_quote_candidate`, `observed_zero_bid_tradability_kill_candidate`, `paper_shadow_evidence_gap`, `pure_statistical_sample_blocker`, `source_quality_pending` | total N 127; holdout N 18; holdout PF 0.8074; PF-LB 0.32 | not_actionable_without_forward_evidence, read_only_research_ok, requires_explicit_approval_before_evidence_store_mutation, requires_policy_change_approval |
| `lane:lane_a_chain_native_ret20_4_stop200_time75` | `high` | `importable_missing_quote_candidate`, `no_chain_native_spread_selection_gap`, `observed_zero_bid_tradability_kill_candidate`, `paper_shadow_evidence_gap`, `pure_statistical_sample_blocker`, `source_quality_pending` | total N 104; holdout N 14; holdout PF 1.2143; PF-LB 0.28 | not_actionable_without_forward_evidence, read_only_research_ok, requires_explicit_approval_before_evidence_store_mutation, requires_policy_change_approval |

## Target-Level Readback

- Bullish-pullback unpriced targets: `3` total, `3` missing-quote rows, reasons `{'missing_exit_quote_for_leg': 3}`, tickers `{'JNJ': 1, 'WMT': 2}`.
- Lane A unpriced targets: `137` total, `127` missing-quote rows, `10` no-chain-native-spread rows, coverage `53.1`%.
- Lane A zero-bid: conservative combined PF `0.85`, zero-bid exit rate `41.99`%, combined unpriced `11`, side-aware PF `0.11`.
- CVX zero-bid/tradability: active source-quality scope policy excludes matching CVX bullish-pullback rows; changing that rule requires policy approval.

## Action Permissions

- `read_only_research_ok`: May inspect, classify, group, and recommend bounded follow-up without writing evidence stores or changing policy.
- `requires_explicit_approval_before_evidence_store_mutation`: Any quote import, replay write that mutates evidence stores, or repair write needs explicit Prime CEO/operator approval.
- `requires_policy_change_approval`: Any candidate kill/exclusion, source-quality policy change, contract-selection change, proof-bar change, or scanner-policy edit needs explicit approval.
- `not_actionable_without_forward_evidence`: Historical rows cannot clear this gate; wait for pre-approved pre-holdout repair or fresh post-freeze forward evidence.

## Next Worker Recommendations

- Build a read-only exact target plan for the bullish-pullback 3 and Lane A missing-exit quote groups. Permission: `read_only_research_ok`; before write: `requires_explicit_approval_before_evidence_store_mutation`.
- Separate Lane A no-chain-native-spread rows from missing-quote rows and decide whether they are policy-change candidates or dead diagnostics. Permission: `read_only_research_ok`; before write: `requires_policy_change_approval`.
- Prepare a read-only zero-bid kill/exclusion proposal for Lane A if Prime CEO wants one; leave the active CVX scope policy unchanged. Permission: `read_only_research_ok`; before write: `requires_policy_change_approval`.
- Treat paper-shadow evidence and sample-size/PF-LB blockers as not actionable from historical rows alone. Permission: `not_actionable_without_forward_evidence`; before write: `fresh post-freeze forward exact evidence or separately approved pre-holdout repair`.

## Prohibited Commands

- no quote imports or evidence-store mutation without explicit approval
- no --apply
- no DB migrations, backups, deletes, broker, paper, or live-trading commands
- no scanner commands
- no promotion commands
- do not run --run-all-planned
- do not consume protected forward holdout
- do not edit source-quality policy from this manifest

## Boundary

Current status remains blocked, non-promotable, and observe-only. This manifest is a source-quality triage surface for Prime CEO task selection, not a quote import plan, source-quality policy change, scanner change, proof-bar change, broker instruction, or production proof claim.
