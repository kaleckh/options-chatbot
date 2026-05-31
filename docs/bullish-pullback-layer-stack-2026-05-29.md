# Bullish Pullback Layer Stack - 2026-05-29

This report freezes the next few bullish-pullback profitability layers from trusted ThetaData intraday OPRA/NBBO exact-contract evidence. It is paper-shadow research only, not live-capital approval.

## Result

The next honest layer stack is the high-confidence core, the frozen quoted cluster layers, the 129-trade clean exact branch, the 130-trade count-expanded branch, the 130-trade high-PF reference, and an S-only timecluster component watch. The `200+` exact annual-trade target is still not reached; no tested add-on contributes the needed `20-30` reliable extra exact trades without degrading coverage, stress, OOS, or PF.

## Ordered Layers

| Layer | Decision | Exact | PF | Avg PnL | Coverage | Unpriced | Stress PF | Rolling | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| layer_0_confidence_core_s_a_b | use_as_current_core_queue | 108 | 4.86 | 53.22 |  |  |  |  | high_confidence_core_below_count_target |
| layer_1_high_pf_cluster | freeze_as_high_pf_paper_shadow_layer | 113 | 4.34 | 49.78 | 94.20 | 7 | 3.23 | passed | component_or_watch_layer |
| layer_2_high_coverage_cluster | freeze_as_high_coverage_quoted_layer | 115 | 2.57 | 34.29 | 99.10 | 1 | 1.95 | passed | paper_shadow_layer_strict_blocked |
| layer_3_clean_cluster_component | keep_as_clean_component_layer | 95 | 3.36 | 44.07 | 100.00 | 0 | 2.56 | watch | component_or_watch_layer |
| layer_4_clean_exact | promote_as_clean_paper_shadow_layer | 129 | 2.20 | 28.97 | 100.00 | 0 | 1.67 | passed | clean_paper_shadow_layer |
| layer_5_count_expanded | use_as_count_expanded_paper_shadow_reference | 130 | 2.04 | 24.54 | 97.70 | 3 | 1.53 | passed | paper_shadow_layer_strict_blocked |
| layer_6_high_pf_130_reference | use_as_high_pf_130_trade_reference | 130 | 2.53 | 33.20 | 97.70 | 3 | 1.91 | passed | paper_shadow_layer_strict_blocked |
| layer_7_s_timecluster_component | component_watch_not_count_expansion | 95 | 3.71 | 45.53 | 100.00 | 0 | 1.66 | watch | component_or_watch_layer |

## Rejected Expansion

| Branch | Exact | PF | Coverage | Stress PF | Rolling | Decision |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| sleeve_next_move_bucket_refill_v1 | 135 | 2.03 | 91.20 | 1.49 | passed | do_not_promote_full_branch |
| sleeve_pf59_s_ab_timecluster_v1 | 146 | 2.23 | 89.60 | 1.66 | watch | do_not_promote_full_branch |
| sleeve_pf59_s_a_energy_defensive_v1 | 139 | 2.50 | 91.40 | 1.85 | watch | do_not_promote_full_branch |
| sleeve_pf59_s_themeA_no_ticker_bans_v1 | 165 | 1.49 | 90.70 | 1.12 | watch | do_not_promote_full_branch |
| sleeve_pf59_coverage_clean_v1 | 146 | 1.66 | 89.60 | 1.23 | watch | do_not_promote_full_branch |

## Rejected Incremental Components

| Component | Exact | PF | Avg PnL | Reason |
| --- | ---: | ---: | ---: | --- |
| coverage_a_refill | 26 | 1.11 | 2.72 | Refill block is weak as a standalone add-on: PF 1.11 and avg +2.72%, so it should not drive the next layer. |
| a_theme_energy_defensive | 48 | 0.94 | -1.71 | Energy/defensive A refill is not independently profitable after import: PF 0.94 and avg -1.71%. |
| b_pf1_refill | 25 | 0.51 | -18.34 | B refill adds exact count but loses money: PF 0.51 and avg -18.34%. |

## Surgical Scout Test

| Scout | Exact | PF | Coverage | Unpriced | Stress PF | Rolling | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| sleeve_next_defensive_refill_v1 | 130 | 2.15 | 94.20 | 8 | 1.60 | passed | do_not_promote_after_exact_fill |

The defensive refill scout remains blocked after exact-fill: classification counts `{'provider_no_match_exact_contract_with_same_expiry_chain': 10}`, by ticker `{'UNH': 1, 'PM': 5, 'WMT': 3, 'JNJ': 1}`, and exact executable rows found `0`. Its WMT/PM refill tier has only `22` exact trades at PF `1.36` and avg `+7.66%`, so it is not the next layer.

## Data Read

- ThetaData was already brought up and used in the prior import/rerun loop for this evidence set.
- A post-layer defensive refill exact-fill attempt wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json`; ThetaData returned `497` normalized rows but `0` new trusted rows because all were duplicates.
- The remaining unresolved rows are provider no-match exact OCC contracts after direct import attempts, not skipped local data work.
- Do not re-open broad refill tuning unless a new exact trusted data source or a new frozen causal rule changes the setup.

## Keep / Move / Remove

- Keep current lane: `IWM, AAPL, GOOGL, UNH, LLY, JNJ, XOM, CVX, COP, NEM`.
- Move to separate lanes: `QQQ, DIA, XLK, NVDA, AMZN, TSLA, WMT, PM, CAT, PLD`.
- Remove from current queue: `JPM, BAC, C, ABBV, SLB, RTX, FCX, COIN, PLTR`.
- Remaining symbols stay research/data-needed unless exact evidence improves.

## Verification

- `python scripts/build_bullish_pullback_layer_stack.py`: passed; regenerated layer-stack latest.json and markdown report.
- `python -m pytest tests/test_bullish_pullback_layer_stack.py tests/test_bullish_pullback_confidence_tiers.py tests/test_bullish_pullback_ticker_audit.py -q`: 16 passed.
- `python -m py_compile scripts/build_bullish_pullback_layer_stack.py`: passed.
- `python scripts/run_bullish_pullback_sleeves.py --only sleeve_next_defensive_refill_v1 --json`: post-import rerun: 138 candidates, 130 exact, 8 unpriced, 94.2% coverage, PF 2.15.
- `python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260529_180007_sleeve_next_defensive_refill_v1_intraday.json --start-time 09:30:00 --end-time 16:00:00 --interval 1m --lookahead-calendar-days 5 --timeout 180 --json`: ThetaData returned 497 normalized rows; imported 0 new trusted rows because all were duplicates in batch 1794.
- `python scripts/classify_missing_replay_contracts.py data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json --json`: 10 missing legs; all provider_no_match_exact_contract_with_same_expiry_chain; exact executable rows found 0.
- `python scripts/imported_intraday_robustness.py --run data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json --train-days 50 --test-days 20 --json`: blocked by unpriced candidates; rolling test passed at PF 3.12; 5%/side stress PF 1.60.

## Next Actions

- Wire the ordered layer stack into paper-shadow reporting/harness selection before adding more ticker hypotheses.
- Build assignment/expiration-safe live-shadow handling for the clean and count-expanded layers.
- Add trailing partial-window robustness and leg-level bid/ask audit before any sizing beyond paper.
- Run only one surgical split/provider-risk diagnostic for the energy/defensive branch if needed; do not reopen broad refill tuning.
- Resume scout lanes only with a new causal rule or new exact trusted data, not by broad all-59 refill loosening.
