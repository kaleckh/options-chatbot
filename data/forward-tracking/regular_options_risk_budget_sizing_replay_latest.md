# Regular Options Risk-Budget Sizing Replay

This report is generated from `scripts/build_regular_options_risk_budget_sizing_replay.py`. It is read-only sizing evidence over priced research/backfill rows and does not change live size tiers, scanner policy, broker behavior, DB state, proof bars, or lane promotion.

## Summary

- Status: `risk_budget_sizing_replay_readback`.
- Overall status: `sizing_replay_built_collect_fresh_exact_evidence`.
- Source rows: `206`.
- Baseline net P&L: `-18755.0`.
- Best research scenario: `paper_shadow_only` / net `971.3` / PF `1.83`.
- Positive research scenarios: `2`.
- Open-risk status / live entry allowed: `open_risk_governor_pass` / `True`.
- Promotion ready: `False`.
- Blockers: `["fresh_exact_realized_sizing_evidence_required", "historical_research_backfill_rows_are_not_production_sizing_proof", "sizing_change_requires_separate_promotion_gate"]`.
- Live policy change: `false`.

## Scenario Replay

| Scenario | Included | Risk Units | Net USD | PF | Avg % | Median % | Win Rate | Worst Month | Blockers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline_one_contract_all_untracked | 206 | 206.0 | -18755.0 | 0.32 | -16.54 | -12.64 | 34.95 | -13578.6 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, profit_factor_below_sizing_gate |
| quarantine_zero_weight | 72 | 72.0 | -1387.15 | 0.75 | -3.84 | -4.5 | 44.44 | -3184.15 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, profit_factor_below_sizing_gate |
| paper_shadow_only | 24 | 24.0 | 971.3 | 1.83 | 6.74 | 2.15 | 50.0 | -55.25 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof |
| tiered_shadow_full_retest_quarter | 72 | 36.0 | 381.69 | 1.17 | 1.45 | -4.5 | 44.44 | -837.47 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, profit_factor_below_sizing_gate |
| current_governor_zero_new_risk | 206 | 206.0 | -18755.0 | 0.32 | -16.54 | -12.64 | 34.95 | -13578.6 | fresh_exact_realized_sizing_evidence_required, historical_research_backfill_rows_are_not_production_sizing_proof, net_pnl_not_positive, profit_factor_below_sizing_gate |

## Lane Budget Table

| Lane | Disposition | Archive | Rows | Net USD | PF | Avg % | Paper Weight | Tiered Weight |
|---|---|---|---:|---:|---:|---:|---:|---:|
| swing | `quarantine` | `archived_quarantine_lane` | 49 | -6331.95 | 0.2 | -20.24 | 0.0 | 0.0 |
| bullish_momentum | `quarantine` | `archived_quarantine_lane` | 16 | -3819.3 | 0.04 | -48.45 | 0.0 | 0.0 |
| bullish_pullback_observation | `quarantine` | `archived_quarantine_lane` | 15 | -3698.45 | 0.24 | -22.81 | 0.0 | 0.0 |
| short_term | `quarantine` | `archived_quarantine_lane` | 54 | -3518.15 | 0.33 | -18.93 | 0.0 | 0.0 |
| tracked_winner_observation | `retest` | `` | 20 | -972.65 | 0.5 | -8.43 | 0.0 | 0.25 |
| tracked_winner_primary | `retest` | `` | 20 | -972.65 | 0.5 | -8.43 | 0.0 | 0.25 |
| speculative | `retest` | `` | 8 | -413.15 | 0.1 | -12.62 | 0.0 | 0.25 |
| volatility_expansion_observation | `paper_shadow` | `` | 24 | 971.3 | 1.83 | 6.74 | 1.0 | 1.0 |

## Boundary

This sizing replay is read-only. It does not change size tiers, create trades, submit broker orders, mutate DB state, change scanner policy, lower exact OPRA/NBBO proof bars, or promote research/backfill sizing rows to production proof.

