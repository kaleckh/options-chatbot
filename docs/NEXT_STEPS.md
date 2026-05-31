# Next Steps

Last updated: 2026-05-31

## Documentation Hygiene

Current read:
- global agent behavior rules live in `C:\Users\kalec\AGENTS.md` and `C:\Users\kalec\CLAUDE.md`
- repo-specific agent startup and evidence rules live in `AGENTS.md`
- latest Markdown placement audit: `docs/markdown-audit-2026-05-31.md`

1. When adding new Markdown, update `docs/index.md` only for living docs or reports that change the current decision surface. Keep generated research reports beside their source artifacts under `data/` or `research_runs/`.

## Frontend Makeover Follow-Up

Current read:
- the main UI now uses `Trading Desk` / `Strategy Lab` naming
- `Trading Desk` prioritizes open/closed tracked positions and scanner picks, while paper ideas and legacy prediction analytics are de-emphasized
- scanner evidence, proof state, and guardrails are collapsed rather than removed
- `FinTable` now renders mobile cards below tablet width, while desktop tables retain horizontal density
- the in-app browser automation backend was unavailable during the makeover, so verification used lint, typecheck, production build, and a local HTTP 200 load check

1. Do a visual browser QA pass on desktop and mobile with the app plus backend running together (`npm run dev`) before treating the makeover as final polish.

2. Continue reducing the large `src/components/predictions/PredictionsView.tsx` surface by extracting hooks, formatting helpers, scanner view, tracked positions view, and paper ideas view before attempting deeper row expansion or drawer work.

3. Add a focused responsive pass for trade row details: keep ticker, side, live P&L, status, and action first, then move target/stop/quote/expiry/provenance into row details instead of making every table expose every column.

## Tracked Position Profit Controls

Current read:
- the UI-backed tracked-position store contains historical paper rows with raw `stop_loss_pct=90`
- live review intentionally honors `90%` configured stops for profit-first paper/live-shadow behavior
- configured stops wider than `90%` are capped to `90%`, while retaining both `configured_stop_loss_pct` and `effective_stop_loss_pct` in review metrics
- verified executable zero exits can now auto-close paper positions at `0.0` instead of leaving total-loss options open
- display-only last-price marks still suppress stop/target triggers and do not auto-close positions
- passive positions/suggestions polling in the UI is now read-only; explicit refresh/review actions are required before the UI POSTs review requests
- `POST /api/positions/review` is still state-changing: it saves reviews and can auto-close executable `SELL` recommendations

1. Audit the currently open historical paper positions before running the state-changing review endpoint, then decide whether to let executable `SELL` recommendations auto-close or close selected rows manually.

2. Keep investigating the app truth-health mismatch seen during the local server check: `/api/options-profit/status` reported `TRACKED DB DOWN` while `/api/positions` and `/api/proof-summary` still returned tracked-position data.

## Regular Options Multi-Lane Portfolio

Current artifact:
- runner: `scripts/run_regular_options_multilane_portfolio.py`
- latest JSON: `data/profitability-lab/regular-options-multilane/latest.json`
- latest Markdown: `data/profitability-lab/regular-options-multilane/latest.md`
- report: `docs/regular-options-multilane-2026-05-30.md`
- frozen autoresearch evaluator: `scripts/evaluate_regular_options_autoresearch.py`
- autoresearch goal prompt: `docs/autoresearch/regular-options-goal.md`
- autoresearch latest JSON: `data/profitability-lab/regular-options-autoresearch/latest.json`
- autoresearch latest Markdown: `data/profitability-lab/regular-options-autoresearch/latest.md`
- autoresearch ledger: `data/profitability-lab/regular-options-autoresearch/ledger.jsonl`
- autoresearch goal experiment harness: `scripts/run_regular_options_goal_experiment.py`
- autoresearch goal experiment latest JSON: `data/profitability-lab/regular-options-autoresearch/experiments/latest.json`
- all-planned sleeves runner: `scripts/run_regular_options_all_planned_sleeves.py`
- all-planned latest JSON: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/latest.json`
- all-planned latest batch: `data/profitability-lab/regular-options-autoresearch/all-planned-sleeves/20260531T053337Z_merged_all_planned_plus_repairs/summary.json`

Current read:
- operator read: `200 good trades` is misframed. The multi-lane count gate is passed, but the frozen clean-promotion gate is still blocked.
- combined proof-grade regular stock-options portfolio: `234` trusted intraday exact trades after strict entry-date + ticker + direction dedupe
- PF: `2.16`
- avg PnL: `+26.76%`
- gap to `200`: `0`
- quality gate: `quality_pending`
- count gate: `passed`
- coverage gate: `blocked`
- robustness gate: `blocked`
- paper-shadow gate: `pending`
- counted proof source: trusted intraday OPRA/NBBO exact rows only
- daily/EOD artifacts remain research-only and are not counted toward the proof target
- the `234` stack comes from `sleeve_pf59_coverage_a_refill_v1` plus the latest `lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1`
- latest Lane A read: `155` exact trades, `137` unpriced candidates, `53.1%` quote coverage, PF `3.59`, avg `+42.34%`, 5%/side stress PF `2.65`
- latest Lane A classifier read: `111` missing exact leg/date items still classify as provider no-match exact contracts in the trusted local store, but a raw ThetaData probe found all `111` exact short-leg rows at `15:55` with `bid=0` and `ask>0`; the current importer/classifier drops them because it requires `bid > 0`
- side-aware Lane A zero-bid replay: `data/profitability-lab/side-aware-zero-bid/latest_lane_a_side_aware_zero_bid.json` priced `126` of `127` missing-exit candidates in conservative long-bid/short-ask mode; `118` priced rows used at least one zero-bid exit quote, the side-aware rows alone were PF `0.11` and avg `-66.59%`, and combined Lane A falls to `281` priced trades at PF `0.85`, avg `-6.51%`, and `96.2%` coverage. Midpoint zero-bid mode is also weak at combined PF `1.11`, avg `+3.79%`.
- contrarian count scan: existing trusted intraday artifacts can reach a raw `300+` exact-priced scenario only by adding low-coverage research artifacts, especially older `tracked_winner_chain_native_qqq_time80_research` artifacts; a current trusted-intraday rerun now makes that scout explicit at `102` strict-new exact trades over the current stack, PF `1.36`, `51.8%` coverage, and `95` unpriced candidates, so it is not production-clean evidence
- latest tracked-winner classifier read: `77` missing exact leg/date items classify as provider no-match exact contracts with same-expiry chain rows present
- clean/high-coverage existing artifacts do not solve the `300` target: clean coverage>=97.5 and unpriced=0 artifacts union to only `134` strict keys, and the clean bullish-pullback reference adds only `17` strict-new rows over the current stack
- frozen autoresearch baseline, from the ledger rather than current `latest.json`: `score: 0.00`, `research_score: 177.74`, status `scout_or_blocked`, clean count `0`, scout count `234`, PF `2.16`, avg `+26.76%`, effective side-aware coverage `96.71%`, unresolved `14`, stress PF `1.53`, zero-bid exit rate `41.99%`, Lane A conservative PF `0.85`
- current autoresearch `latest.json`: latest Lane A repair experiment, not the baseline. It reports `score: 0.00`, clean count `0`, scout count `130`, and `lane_a_is_counted=false` because the repaired Lane A variant had only `81` exact trades.
- first Lane A goal-loop result: simple entry survivability filters were not enough. The best entry-filter variant, `lane_a_goal_stop200_time75_shortprior3_shortbid10_backfill`, improved effective coverage to `99.09%` and unresolved candidates to `3`, but left Lane A conservative PF at `0.88` and zero-bid exit rate above `42%`.
- second Lane A goal-loop result: the bad-zero-ticker/debit repair proved the economics can be improved but not at enough count. `lane_a_goal_bad_zero_ticker_exclusion_debit45_npicks8` reached `research_score: 236.19` and Lane A conservative PF `1.30`, but only `81` exact Lane A trades, so Lane A was not counted and the stack fell back to the `130`-trade core.
- replacement-sleeve check: core plus the clean exact reference reaches only `157` strict-deduped trades; core plus clean reference plus all high-PF/coverage cluster artifacts reaches only `158` because of overlap. Current trusted-intraday tracked-winner replacements failed profitability (`tracked_winner_chain_native_qqq_time65_research` reran at `109` exact trades but PF `1.04`).
- all-planned sleeve audit: `30` currently implemented planned regular stock-options variants have now run end-to-end with `0` run failures. The audit still does not show a clean gap-closer. The best new candidate is `tracked_winner_chain_native_googl_nvda_time65_all_sleeves` (`49` strict-new exact, PF `1.98`, avg `+18.27%`, stress PF `1.39`), which could close the `43`-trade clean gap only if its `68.1%` quote coverage and `23` unpriced candidates are repaired. The broader no-SPY tracked-winner repair adds `67` strict-new rows at PF `1.85`, but has only `62.0%` coverage and stress PF `1.24`. Cheap-debit continuity adds `98` strict-new rows but misses quality at PF `1.43`, `50.8%` coverage, and stress PF `0.97`. Fast volatility expansion, current relative-strength pullback, high-beta momentum, and range-breakout shapes remain rejected.
- planned-but-not-tested ledger: `29` lane-lab specs remain explicitly blocked or not yet testable rather than skipped. Statuses are `12` pending forward/paper logs, `9` blocked by instrumentation, `5` blocked by missing data, `1` partial fill-discipline paper result, `1` scored high-debit control, and `1` now ready for paper backtest. `IWM` was a stale blocker; the all-planned runner now derives readiness from the current trusted ThetaData store and marks `iwm_small_cap_risk` as `ready_for_paper_backtest`.

1. Use the multi-lane runner before arguing trade count. It separates portfolio-candidate lanes, intraday scouts, daily/EOD research, and blocked lane specs.

2. Use the frozen autoresearch evaluator before running `/goal` loops or accepting strategy changes. The evaluator's hard `promotable_clean` gates are: `>=200` clean trades, PF `>=1.50`, avg PnL `>0`, effective coverage `>=97.5%`, unresolved candidates `0`, 5%/side stress PF `>=1.25`, rolling/OOS pass, side-aware conservative Lane A replay if Lane A is counted, Lane A conservative PF `>=1.30`, and zero-bid exit rate `<=2%`. Paper-shadow pass is still required for production readiness.

3. Keep the explicit tracked-winner intraday scout in the multi-lane runner before saying the existing artifact set cannot reach `300`. It has enough strict-new rows to matter for raw count, but the current rerun fails PF and coverage gates, so it should stay behind the quality gate unless a redesigned causal/contract-selection version clears them.

4. Stop treating simple Lane A filter tuning as the primary path to `200` clean trades. Entry short-bid, prior-quote, liquidity-score, tradability, early-exit, debit/width, and broad bad-zero-ticker probes either leave Lane A conservative PF below gate or reduce the lane below the `100` exact-trade portfolio-candidate threshold. The next `/goal` implementation target should repair tracked-winner GOOGL/NVDA contract survivability first, then convert blocked lane-lab specs into runnable end-to-end tests with the same frozen evaluator.

5. Do not promote the newly tested bearish put, range-breakout, or volatility-expansion probes. Put-chain data was imported and exact exits were filled where possible; the bearish time-exit lane priced `73` exact trades at PF `0.21`, and range/volatility probes remained negative or below breakeven.

6. It is now fair to say every currently implemented planned sleeve in the all-planned runner has been tested end-to-end. It is not fair to say every planned lane-lab spec is fully tested: `29` specs still need data imports, paper logs, or structure/instrumentation support before they can produce replay metrics. Keep those specs visible and burn them down systematically rather than ranking them away.

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
- current count-expanded all-59 refill artifact: `data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json`
- current count-expanded all-59 refill robustness artifact: `data/profitability-lab/imported-intraday-robustness/latest_sleeve_pf59_coverage_a_refill_v1.json`
- current frozen layer-stack artifact: `data/profitability-lab/bullish-pullback-observation/layer-stack/latest.json`
- current frozen layer-stack report: `docs/bullish-pullback-layer-stack-2026-05-29.md`
- latest next-layer report: `docs/bullish-pullback-next-layer-profitability-2026-05-29.md`
- latest next-layer sleeve round: `data/profitability-lab/bullish-pullback-observation/sleeves/sleeve_round_20260529T052213Z.json`
- latest next-layer scoreboard: `data/profitability-lab/bullish-pullback-observation/next-layer-summary-2026-05-29.json`
- latest next-layer import artifacts: `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T050747Z.json` and `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T051508Z.json`
- current confidence-tier report: `data/profitability-lab/bullish-pullback-observation/confidence/latest.json`
- current per-ticker keep/move/remove audit: `docs/bullish-pullback-ticker-audit-2026-05-29.md` and `data/profitability-lab/bullish-pullback-observation/ticker-audit/latest.json`
- previous strict quoted-exit lead artifact: `data/options-validation/runs/20260528_005918_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_v1_intraday.json`
- current fully priced mixed/settlement artifact: `data/options-validation/runs/20260528_010301_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly75_v1_intraday.json`
- sleeve sweep artifacts: cluster/all-59 rounds under `data/profitability-lab/bullish-pullback-observation/sleeves/`, including `sleeve_round_20260528T025450Z.json`
- best clean 100% exact branch: `data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json`
- best 130-trade PF branch: `data/options-validation/runs/20260528_013904_sleeve_winner_cluster_exit_balanced_quoted_v1_intraday.json`
- latest defensive refill scout rerun: `data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json`
- latest defensive refill exact-fill attempt: `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json`
- zero-pick current-algorithm audit script: `scripts/audit_zero_pick_days_current_main_lane.py`
- zero-pick current-algorithm audit report: `data/forward-tracking/main_lane_zero_pick_current_algo_audit_latest.json`
- zero-pick paper-position migration script: `scripts/migrate_main_lane_backfills_to_positions.py`
- zero-pick paper-position migration report: `data/forward-tracking/main_lane_zero_pick_position_migration_latest.json`
- zero-pick audit tracking status: `60` exact historical main-lane picks appended as `research_backfill` / `backfilled_historical_track` and explicitly migrated into UI-backed Postgres paper tracked positions; final audit-position state is `27` open and `33` closed by historical time-exit. These are historical paper positions, not live-production proof.

1. Use `sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1` as the high-PF profitability-first paper/live-shadow branch: `120` candidates, `113` exact quoted trades, `7` unresolved candidates, `94.2%` quote coverage, PF `4.34`, avg `+49.78%`, median `+54.20%`, win rate `72.6%`, and all priced exits are bid/ask `time_exit` fills. It excludes `CAT`, `PM`, `PLD`, and `XLK`, uses 60% DTE exits for energy/GOOGL/JNJ/LLY, 55% for NEM/IWM, and 50% for AAPL/UNH.

2. Use `sleeve_pf59_coverage_a_refill_v1` as the count-expanded all-59 paper-shadow candidate when the goal is enough trades rather than max PF: latest rerun `data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json` has `133` candidates, `130` exact quoted trades, `3` unresolved WMT/JNJ provider no-match candidates, `97.7%` quote coverage, PF `2.04`, avg `+24.54%`, rolling test `34` exact trades at PF `2.35`, and 5%/side stress PF `1.53`. Its robustness status is still `blocked` only because the `3` full-sample unpriced candidates remain unresolved.

Latest 2026-05-29 next-layer stop state:
- Do not promote `sleeve_next_move_bucket_refill_v1`: after successful ThetaData imports it is the highest new move-bucket count scout at `135` exact trades and PF `2.03`, but quote coverage is only `91.2%`, `13` candidates remain unpriced, and 5%/side stress PF is `1.49`.
- Do not promote `sleeve_next_defensive_refill_v1`: after a post-layer exact-fill attempt and rerun it remains `130` exact trades at PF `2.15`, but coverage is only `94.2%`, `8` candidates remain unpriced, and the incremental WMT/PM refill tier is only `22` exact trades at PF `1.36` and avg `+7.66%`.
- Do not continue high-beta bullish-pullback or momentum variants without a new causal hypothesis: `sleeve_next_high_beta_survival_v1` was `16` exact trades at PF `0.11`, and `sleeve_next_high_beta_momentum_fast_v1` was `44` exact trades at PF `0.20`.
- Treat ETF/index, PM, PLD, and CAT as small scout lanes only. Their isolated exact samples are too thin to close the `70` to `92` annual-trade gap.
- ThetaTerminal v3 is available and the missing-contract import loop was rerun. Further count-expansion work should start from the new exact import artifacts, rerun replay/classifier/robustness after any additional import, and treat remaining provider no-match exact contracts as non-proof unless ThetaData returns executable bid/ask rows for the exact OCC contract.

3. Use `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1` when coverage/count cleanliness matters more than raw PF and before adding the lower-PF refill block: `116` candidates, `115` exact quoted trades, `1` unresolved JNJ provider no-match, `99.1%` quote coverage, PF `2.57`, avg `+34.29%`, and rolling test `36` exact trades at PF `2.59` with `0` unpriced test candidates. It stays positive under 5%/side stress at PF `1.95`, top-5 winner removal at PF `2.08`, worst-ticker removal at PF `2.08`, and worst-month removal at PF `2.06`.

4. Keep `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1` as the clean quoted proof subset: `95` candidates, `95` exact quoted trades, `0` unresolved, `100.0%` quote coverage, PF `3.36`, avg `+44.07%`, 5%/side stress PF `2.56`, top-5 winner removal PF `2.66`, worst-ticker removal PF `2.71`, and worst-month removal PF `2.61`. It is below the `100`-trade target and lacks a full rolling window, so treat it as a clean component sleeve rather than the main paper family.

5. Use the confidence-tier report and per-ticker audit as the picking queue rather than forcing a pick for every tracked stock. Current S/A/B has `108` exact quoted trades across `10` keep symbols at PF `4.86` and avg `+53.22%`: `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, and `NEM`.

6. Route positive or strategic but non-promoted symbols to separate frozen hypotheses before allowing picks: ETF/index (`QQQ`, `DIA`, `XLK`), high-beta (`NVDA`, `AMZN`, `TSLA`), defensive/refill (`WMT`, `PM`), industrial scout (`CAT`), and REIT/rate-sensitive (`PLD`). Remove `JPM`, `BAC`, `C`, `ABBV`, `SLB`, `RTX`, `FCX`, `COIN`, and `PLTR` from the current bullish-pullback tradable queue.

7. Do not call the 100+ quoted cluster or expanded refill sleeves strict proof-complete yet. Bounded exact-fill/classification for the cluster branches wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260528T074150Z.json`; the refreshed count-expanded imports wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T042128Z.json` and `20260529T042332Z.json` and returned `0` exact rows for the WMT/JNJ misses. The WMT/JNJ gaps remain provider no-match exact-contract gaps with same-expiry chain rows present.

8. Do not keep tuning broad all-59 refill variants or the 2026-05-29 move-bucket scouts as the primary path. The tested broader refills added exact trades but failed the reliability tradeoff: the highest-count branch reached `165` exact trades but PF fell to `1.49`, coverage remained near `90%`, broad C/Blocked evidence is not tradable, and the best move-bucket scout added only `5` exact trades while missing the coverage/stress gates. The desired `200+` annual exact-trade cadence is blocked by lack of a repeatable exact pattern, not by an unattempted local ThetaData import.

9. Next concrete implementation target: wire `data/profitability-lab/bullish-pullback-observation/layer-stack/latest.json` into paper-shadow reporting/harness selection, then add an assignment/expiration-safe live-shadow harness for the quoted cluster and `sleeve_pf59_coverage_a_refill_v1` branches. Add trailing partial-window robustness and leg-level bid/ask execution audit/stress before sizing beyond paper. Separate scout lanes should resume only after a new data import or causal hypothesis, not by rerunning the exhausted 2026-05-29 variants.

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
