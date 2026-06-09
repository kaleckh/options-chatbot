# Regular Options Exact Candidate Selection Repair

This report is generated from `scripts/build_regular_options_exact_candidate_selection_repair.py`. It is a read-only repair target list for lanes with signal candidates but zero exact chain-native spread candidates.

## Summary

- Status: `exact_candidate_selection_repair_readback`.
- Overall status: `exact_candidate_selection_repair_targets_ready`.
- Target lanes: `1`.
- Target dates: `1`.
- Signal candidates: `4`.
- Exact candidates: `0`.
- Would-track rows: `0`.
- Exact reject reasons: `{"no_chain_native_spread_passed_current_filters": 4}`.
- Top signal tickers: `["COIN", "DIS", "META", "SBUX"]`.
- Next evidence actions: `1`.
- Promotion ready: `False`.
- Blockers: `["chain_native_filter_relaxation_replay_missing", "no_chain_native_spread_passed_current_filters"]`.
- Live policy change: `false`.

## Repair Targets

| Lane | Scan Date | Signals | Exact | Would Track | Tickers | Exact Reject Reasons | Next Action |
|---|---|---:|---:|---:|---|---|---|
| regular_bearish_put_primary | 2026-05-22 | 4 | 0 | 0 | ["META", "COIN", "SBUX", "DIS"] | {"no_chain_native_spread_passed_current_filters": 4} | `build_chain_native_filter_relaxation_replay` |

## Next Evidence Queue

| Priority | Action | Count | Reason |
|---:|---|---:|---|
| 4 | `build_chain_native_filter_relaxation_replay` | 1 | no_chain_native_spread_passed_current_filters:1 |

## Boundary

This exact-candidate selection repair is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, lower exact OPRA/NBBO proof bars, or synthesize P&L for signal-only rows.

