# Next Steps

Last updated: 2026-05-29

## Bullish Pullback Observation Lane

Current full active-universe exact-contract status:
- active universe: `59` symbols from `data/options-lanes/universes/bullish_pullback_observation.json`
- `CMCSA` excluded from the active universe
- trusted ThetaData intraday OPRA/NBBO coverage: all active symbols, `252` shared dates from `2025-05-22` through `2026-05-22`
- preserved baseline artifact: `data/options-validation/runs/20260527_211058_bullish_pullback_observation_intraday.json`
- current high-PF cluster artifact: `data/options-validation/runs/20260528_013544_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1_intraday.json`
- current high-PF cluster robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1.json`
- current high-coverage cluster artifact: `data/options-validation/runs/20260528_014057_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1_intraday.json`
- current high-coverage cluster robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1.json`
- current clean quoted subset artifact: `data/options-validation/runs/20260528_014353_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1_intraday.json`
- current count-expanded all-59 refill artifact: `data/options-validation/runs/20260528_085047_sleeve_pf59_coverage_a_refill_v1_intraday.json`
- current count-expanded all-59 refill robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_pf59_coverage_a_refill_v1.json`
- current confidence-tier report: `data/profitability-lab/bullish-pullback-observation/confidence/latest.json`
- current per-ticker keep/move/remove audit: `docs/bullish-pullback-ticker-audit-2026-05-29.md` and `data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json`
- previous strict quoted-exit lead artifact: `data/options-validation/runs/20260528_005918_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_v1_intraday.json`
- current fully priced mixed/settlement artifact: `data/options-validation/runs/20260528_010301_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly75_v1_intraday.json`
- sleeve sweep artifacts: cluster/all-59 rounds under `data/profitability-lab/bullish-pullback-observation/sleeves/`, including `sleeve_round_20260528T025450Z.json`

1. Use `sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1` as the high-PF profitability-first paper/live-shadow branch: `120` candidates, `113` exact quoted trades, `7` unresolved candidates, `94.2%` quote coverage, PF `4.34`, avg `+49.78%`, median `+54.20%`, win rate `72.6%`, and all priced exits are bid/ask `time_exit` fills. It excludes `CAT`, `PM`, `PLD`, and `XLK`, uses 60% DTE exits for energy/GOOGL/JNJ/LLY, 55% for NEM/IWM, and 50% for AAPL/UNH.

2. Use `sleeve_pf59_coverage_a_refill_v1` as the count-expanded all-59 paper-shadow candidate when the goal is enough trades rather than max PF: `133` candidates, `130` exact quoted trades, `3` unresolved WMT/JNJ provider no-match candidates, `97.7%` quote coverage, PF `2.04`, avg `+24.56%`, rolling test `34` exact trades at PF `2.35`, and 5%/side stress PF `1.53`. Its robustness status is still `blocked` only because the `3` full-sample unpriced candidates remain unresolved.

3. Use `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1` when coverage/count cleanliness matters more than raw PF and before adding the lower-PF refill block: `116` candidates, `115` exact quoted trades, `1` unresolved JNJ provider no-match, `99.1%` quote coverage, PF `2.57`, avg `+34.29%`, and rolling test `36` exact trades at PF `2.59` with `0` unpriced test candidates. It stays positive under 5%/side stress at PF `1.95`, top-5 winner removal at PF `2.08`, worst-ticker removal at PF `2.08`, and worst-month removal at PF `2.06`.

4. Keep `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1` as the clean quoted proof subset: `95` candidates, `95` exact quoted trades, `0` unresolved, `100.0%` quote coverage, PF `3.36`, avg `+44.07%`, 5%/side stress PF `2.56`, top-5 winner removal PF `2.66`, worst-ticker removal PF `2.71`, and worst-month removal PF `2.61`. It is below the `100`-trade target and lacks a full rolling window, so treat it as a clean component sleeve rather than the main paper family.

5. Use the confidence-tier report and per-ticker audit as the picking queue rather than forcing a pick for every tracked stock. Current S/A/B has `108` exact quoted trades across `10` keep symbols at PF `4.86` and avg `+53.22%`: `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, and `NEM`.

6. Route positive or strategic but non-promoted symbols to separate frozen hypotheses before allowing picks: ETF/index (`QQQ`, `DIA`, `XLK`), high-beta (`NVDA`, `AMZN`, `TSLA`), defensive/refill (`WMT`, `PM`), industrial scout (`CAT`), and REIT/rate-sensitive (`PLD`). Remove `JPM`, `BAC`, `C`, `ABBV`, `SLB`, `RTX`, `FCX`, `COIN`, and `PLTR` from the current bullish-pullback tradable queue.

7. Do not call the 100+ quoted cluster or expanded refill sleeves strict proof-complete yet. Bounded exact-fill/classification for the cluster branches wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260528T074150Z.json`, and the count-expanded branch wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260528T145332Z.json`; the latest count-expanded import attempt imported `0` rows because ThetaTerminal was unavailable, leaving the WMT/JNJ provider no-match gaps open.

8. Do not keep tuning broad all-59 refill variants as the primary path. The tested broader refills added exact trades but failed the reliability tradeoff: A/B theme refills had weak PF, coverage fell into the high-80% range, and the broad C/Blocked pool is not tradable. The path to the desired `200+` annual exact-trade cadence is additional frozen lanes, not weaker current-lane picks.

9. Next concrete implementation target: add an assignment/expiration-safe live-shadow harness for the quoted cluster and `sleeve_pf59_coverage_a_refill_v1` branches, then build the separate ETF/index and high-beta scout lanes. Also add trailing partial-window robustness reporting and leg-level bid/ask execution audit/stress before sizing beyond paper.

10. Keep the broad baseline as the control. The current baseline remains weak (`21` exact trades, PF `0.83`), so sleeve profitability is coming from allocation/selection/execution changes rather than a silent baseline behavior change.

## AI Commodity / Commodity-Infrastructure Lane

Current readback source: `data/ai-commodity-infra/progress/latest.md`, generated `2026-05-27T14:17:01Z`.

Current state:
- proof source: `alpaca:sip:opra` / `alpaca_opra_daily_snapshot`
- exact shared quote dates: `3` / `100`, from `2026-05-20` through `2026-05-22`
- scan/proof universe: `24` aligned symbols
- latest live scan candidates: `0`
- next guarded capture target: `2026-05-26`, due now if Alpaca credentials and market-data access are available
- full replay unlock projection: `2026-10-12` if one shared OPRA date is captured per market day

1. Run the guarded post-close capture selected by the latest runbook:

```powershell
python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-26
```

Expected success state: shared quote dates advance from `3` to `4`, `capture.target_capture_complete` becomes true, and the full scan/proof universe remains aligned.

2. Immediately after the capture command, run the readback:

```powershell
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
```

3. If the readback does not advance to `4` shared dates, repair the capture failure before replay or filter work. The latest blocker lists the full 24-symbol capture target for `2026-05-26`.

4. If the local store changed and the readback says derived evidence is stale, refresh deterministic readiness without recapturing or rescanning:

```powershell
python scripts/run_ai_commodity_opra_progress.py --skip-capture --skip-scan
```

5. Continue daily guarded captures until the shared-date gate reaches `100` and exact replay unlocks. Run full replay only when the generated runbook says the exact replay unlock contract is ready:

```powershell
python scripts/run_ai_commodity_opra_progress.py
```

6. Keep production filters locked until exact OPRA replay has enough shared bid/ask history, a completed replay with trades, positive profitability metrics, and a live candidate inside the exact proof universe.

7. If a licensed ThetaData Standard/Pro terminal is available on port `25503`, use `scripts/import_thetadata_options_nbbo.py` to import at least 100 shared market days for the full 24-symbol AI commodity universe, then run `scripts/audit_paid_data_readiness.py` against that source label before using it in replay.

8. Treat OnclickMedia EOD chains and Alpaca historical option bars/trades as research support only. They are not final proof-grade bid/ask replay sources for this lane.
