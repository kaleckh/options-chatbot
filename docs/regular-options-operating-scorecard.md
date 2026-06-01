# Regular Options Operating Scorecard

- Status: `visible_product_profitability_progress_but_proof_still_blocked`
- Product profitability progress visible: `True`
- Proof-grade profitability progress visible: `False`

## Trading Desk Guardrails

- Baseline avg/median/negative-rate: `5.21%` / `-1.58%` / `50.4%`
- Promoted kept avg/median/negative-rate: `53.08%` / `46.4%` / `25.0%`
- Deltas: `{'avg_pnl_pct': 47.87, 'median_pnl_pct': 47.98, 'negative_rate_priced_pct': -25.4}`

## Frozen Proof Judge

- Best variant: `lane_a_goal_stop200_time75_symbol_health90_backfill`
- Score/status: `0.0` / `scout_or_blocked`
- Clean/scout count: `0.0` / `191.0`
- Lane A conservative PF / zero-bid rate: `0.92` / `43.24%`
- Blockers: `['clean_trade_count_below_200', 'effective_unresolved_candidates_remain', 'rolling_oos_not_passed:lane_a_chain_native_ret20_4_stop200_time75', 'zero_bid_exit_rate_above_2pct', 'lane_a_conservative_pf_below_1_30']`

## Closed-Trade Follow-Up

- Negative trade rows audited: `213`
- Legacy missed-close targets: `3`
- Legacy missed-close recommendation: `no_broad_exit_policy_change; preserve as historical stale-policy diagnostic`
- Legacy current action required: `0`
- Broad exit promote candidates: `0`
- Legacy target positive replay rows: `27`

## Next Actions

- Treat legacy rows 26/39/44 as historical stale-policy diagnostics, not a broad current exit-policy change.
- Keep promoted Trading Desk entry guardrails active and monitor starvation before loosening.
- Do not tune Lane A entry/memory again; test a non-overlapping sleeve or materially different exit/liquidity rule.
- Do not promote a broad exit-policy replay; current candidates improve some rows but fail broader negative-rate/winner-loss checks.
