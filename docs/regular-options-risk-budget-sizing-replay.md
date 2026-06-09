# Regular Options Risk-Budget Sizing Replay

This report is generated from `scripts/build_regular_options_risk_budget_sizing_replay.py`. It is read-only sizing evidence over priced research/backfill rows and does not change live size tiers, scanner policy, broker behavior, DB state, proof bars, or lane promotion.

## Summary

- Status: `risk_budget_sizing_replay_readback`.
- Overall status: `sizing_replay_built_open_risk_blocked`.
- Source rows: `206`.
- Baseline net P&L: `-16314.0`.
- Best research scenario: `paper_shadow_only` / net `972.3` / PF `1.84`.
- Positive research scenarios: `2`.
- Open-risk status / live entry allowed: `open_risk_governor_blocked` / `False`.
- Promotion ready: `False`.
- Blockers: `["fresh_exact_realized_sizing_evidence_required", "historical_research_backfill_rows_are_not_production_sizing_proof", "open_risk_governor_blocks_sizing", "sizing_change_requires_separate_promotion_gate"]`.
- Live policy change: `false`.

## Scenario Replay

| Scenario | Included | Risk Units | Net USD | PF | Avg % | Median % | Win Rate | Worst Month | Blockers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline_one_contract_all_untracked | 206 | 206.0 | -16314.0 | 0.34 | -15.28 | -11.5 | 33.98 | -11786.6 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, open_risk_governor_blocks_sizing, profit_factor_below_sizing_gate |
| quarantine_zero_weight | 72 | 72.0 | -1496.15 | 0.73 | -4.26 | -7.6 | 41.67 | -3183.15 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, open_risk_governor_blocks_sizing, profit_factor_below_sizing_gate |
| paper_shadow_only | 24 | 24.0 | 972.3 | 1.84 | 6.75 | 2.15 | 50.0 | -54.25 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, open_risk_governor_blocks_sizing |
| tiered_shadow_full_retest_quarter | 72 | 36.0 | 355.19 | 1.16 | 1.24 | -7.6 | 41.67 | -836.47 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, open_risk_governor_blocks_sizing, profit_factor_below_sizing_gate |
| current_governor_zero_new_risk | 0 | 0.0 | 0.0 |  |  |  |  |  | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, open_risk_governor_blocks_sizing, profit_factor_below_sizing_gate, zero_new_risk_budget_due_to_governor |

## Lane Budget Table

| Lane | Disposition | Archive | Rows | Net USD | PF | Avg % | Paper Weight | Tiered Weight |
|---|---|---|---:|---:|---:|---:|---:|---:|
| bullish_momentum | `quarantine` | `archived_quarantine_lane` | 16 | -3819.3 | 0.04 | -48.45 | 0.0 | 0.0 |
| swing | `quarantine` | `archived_quarantine_lane` | 49 | -3781.95 | 0.28 | -14.31 | 0.0 | 0.0 |
| bullish_pullback_observation | `quarantine` | `archived_quarantine_lane` | 15 | -3698.45 | 0.24 | -22.81 | 0.0 | 0.0 |
| short_term | `quarantine` | `archived_quarantine_lane` | 54 | -3518.15 | 0.33 | -18.93 | 0.0 | 0.0 |
| tracked_winner_observation | `retest` | `` | 20 | -1027.65 | 0.48 | -9.19 | 0.0 | 0.25 |
| tracked_winner_primary | `retest` | `` | 20 | -1027.65 | 0.48 | -9.19 | 0.0 | 0.25 |
| speculative | `retest` | `` | 8 | -413.15 | 0.1 | -12.62 | 0.0 | 0.25 |
| volatility_expansion_observation | `paper_shadow` | `` | 24 | 972.3 | 1.84 | 6.75 | 1.0 | 1.0 |

## Boundary

This sizing replay is read-only. It does not change size tiers, create trades, submit broker orders, mutate DB state, change scanner policy, lower exact OPRA/NBBO proof bars, or promote research/backfill sizing rows to production proof.

