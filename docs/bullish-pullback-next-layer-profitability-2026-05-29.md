# Bullish Pullback Next-Layer Profitability Iteration - 2026-05-29

## Conclusion

ThetaData v3 was brought up on `127.0.0.1:25503`, missing exact-contract imports were run, affected replays were rerun, and missing contracts were reclassified after the new rows landed.

The `200+` exact trusted trades/year target is still not reachable honestly from the current one-year exact ThetaData intraday OPRA/NBBO evidence. The highest-count tested branch reaches `165` exact trades, but fails the PF, coverage, stress, and rolling-OOS gates. The strongest reliable count branch remains `sleeve_pf59_coverage_a_refill_v1` at `130` exact trades, PF `2.04`, `97.7%` coverage, and 5%/side stress PF `1.53`.

This remains paper-shadow research only. No variant here is live-capital approval.

## Scoreboard

| Variant | Exact | PF | Avg PnL | Coverage | Unpriced | 5%/side stress PF | Rolling | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `sleeve_winner_cluster_exit_balanced_quoted_v1` | 130 | 2.53 | +33.20% | 97.7% | 3 | 1.91 | passed, PF 2.77 | Best 130-trade PF reference; blocked |
| `sleeve_pf59_coverage_a_refill_v1` | 130 | 2.04 | +24.54% | 97.7% | 3 | 1.53 | passed, PF 2.35 | Best count/coverage branch |
| `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1` | 129 | 2.20 | +28.97% | 100.0% | 0 | 1.67 | passed, PF 2.51 | Best fully priced clean branch |
| `sleeve_next_move_bucket_refill_v1` | 135 | 2.03 | +23.13% | 91.2% | 13 | 1.49 | passed | Not promoted; coverage/stress miss |
| `sleeve_pf59_s_ab_timecluster_v1` | 146 | 2.23 | +26.97% | 89.6% | 17 | 1.66 | watch | Not promoted; coverage/OOS miss |
| `sleeve_pf59_s_a_energy_defensive_v1` | 139 | 2.50 | +30.13% | 91.4% | 13 | 1.85 | watch | Not promoted; coverage/OOS miss |
| `sleeve_pf59_s_themeA_no_ticker_bans_v1` | 165 | 1.49 | +14.00% | 90.7% | 17 | 1.12 | watch | Rejected; PF/stress/OOS miss |
| `sleeve_pf59_coverage_clean_v1` | 146 | 1.66 | +16.75% | 89.6% | 17 | 1.23 | watch | Rejected; PF/stress/OOS miss |

## ThetaData Imports

Trusted-only import/backfill actions completed in this pass:

- `sleeve_pf59_coverage_a_refill_v1`: exact-contract imports `thetadata_exact_missing_intraday_20260529T042128Z.json` and `20260529T042332Z.json` requested the WMT/JNJ misses over one-minute and full-session windows. ThetaData returned `0` normalized rows. Replay rerun: `data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json`.
- `sleeve_next_move_bucket_refill_v1`: exact import `thetadata_exact_missing_intraday_20260529T042508Z.json` normalized `3,682` rows and imported `3,676` trusted rows. A second exact-fill cycle `20260529T042707Z.json` found `700` duplicate rows and imported `0`. Replay rerun: `data/options-validation/runs/20260528_224733_sleeve_next_move_bucket_refill_v1_intraday.json`.
- Move-bucket unresolved windows then received broader trusted ThetaData OPRA/NBBO imports: UNH `2025-11-19..2025-11-24` (`633,621` rows), CAT/PM/WMT/JNJ `2026-03-19..2026-03-31` (`4,823,902` rows), and PM `2026-04-08..2026-04-13` (`284,043` rows).
- Expanded high-count variants: exact import `thetadata_exact_missing_intraday_20260529T050747Z.json` normalized `7,262` rows and imported `6,743` trusted rows across AA/ABBV/ARM/FCX/GOOGL/JNJ/MCD/PFE/PG/SLB/T/UNH/WELL/WMT. The required second cycle `20260529T051508Z.json` found `2,824` duplicate rows and imported `0`. Replays were rerun afterward.

Post-import readiness is `ready_for_exact_replay`: `12,981,701` trusted intraday ThetaData OPRA/NBBO rows, all `59` required underlyings present, `252` shared quote dates from `2025-05-22` through `2026-05-22`, and latest trusted batches `1787` through `1793`.

## Remaining Gaps

The remaining misses are not unattempted local backfills. Classifier results after the import cycles show `0` exact executable rows for the missing OCC contracts while same-expiry trusted chain rows exist:

- `sleeve_pf59_coverage_a_refill_v1`: `3` provider no-match legs (`WMT` 2, `JNJ` 1).
- `sleeve_next_move_bucket_refill_v1`: `15` provider no-match legs (`CAT` 5, `PM` 5, `WMT` 3, `UNH` 1, `JNJ` 1).
- `sleeve_pf59_s_ab_timecluster_v1`: `18` provider no-match legs.
- `sleeve_pf59_s_a_energy_defensive_v1`: `16` provider no-match legs.
- `sleeve_pf59_s_themeA_no_ticker_bans_v1`: `19` provider no-match legs.
- `sleeve_pf59_coverage_clean_v1`: `18` provider no-match legs.

Alpaca was not used as proof because this lane's hard proof rule is trusted ThetaData intraday OPRA/NBBO exact-contract evidence only. Existing repo probes also treat Alpaca historical bars/trades as research-only because they do not provide historical executable bid/ask replay rows.

## Lane Decisions

- Keep current lane: `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`.
- Keep separate frozen hypotheses: ETF/index (`QQQ`, `DIA`, `XLK`), high-beta (`NVDA`, `AMZN`, `TSLA`), defensive/refill (`WMT`, `PM`), REIT/rate-sensitive (`PLD`), industrial (`CAT`).
- Remove from current queue: `JPM`, `BAC`, `C`, `ABBV`, `SLB`, `RTX`, `FCX`, `COIN`, `PLTR`.
- Keep remaining symbols research/data-needed until exact evidence improves.

## Stop Rationale

Further loops on the tested branches are unlikely to improve both profitability and trade count. The extra trades come from weak broad C/Blocked evidence, unresolved exact-contract no-matches, or branches that fail PF/stress/OOS gates. Extending history can be useful for validation, but it does not honestly turn the current one-year `130`-trade annual cadence into `200+` annual exact trades without a new causal signal.

Detailed machine-readable summary: `data/profitability-lab/bullish-pullback-observation/next-layer-summary-2026-05-29.json`.
