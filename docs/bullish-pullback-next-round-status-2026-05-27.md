# Bullish Pullback Next-Round Status - 2026-05-27

## Verdict

Terminal state for this iteration: CONTINUE, not SUCCESS.

The lane remains exact-contract profitable in full sample, but no candidate passed the strict promotion gates. The repeated blockers are:

- unpriced exact-contract candidates remain
- strict rolling OOS does not pass
- Jan-Feb 2026 weakness persists across the best count-growth variants
- replay/live parity is still not durable enough for paper/live-shadow

Broad ticker/date data is not the bottleneck anymore. The current bottleneck is executable contract selection plus recent OOS weakness.

## Data Coverage

Subagent coverage audit found:

- active post-CMCSA universe: 59 symbols
- CMCSA: excluded
- trusted ThetaData source: `thetadata_opra_nbbo_1m`
- broad trusted intraday coverage: 59/59 symbols complete for the audited window
- active-window trusted rows: 7,189,107

Remaining unpriced candidates are mostly exact contract/leg no-match or executable-selection issues, not missing broad underlying/ticker coverage.

## Code Changes

- Added live-safe numeric replay playbook filters in `wfo_optimizer.py`:
  - `min_spy_ret5`, `max_spy_ret5`
  - `min_hv30`, `max_hv30`
  - `min_tech_score`, `max_tech_score`
  - `min_direction_score`, `max_direction_score`
- Added bounded next-round variants in `scripts/run_bullish_pullback_next_round.py`:
  - SPY-regime variants
  - shallower-pullback variants
  - `debit50_direction65_ret5min3_target120`
  - `debit50_direction65_ret5min3_dte29_45`
- Fixed `scripts/imported_intraday_robustness.py` so rolling OOS windows include unpriced candidates instead of silently ignoring them.
- Added `tests/test_imported_intraday_robustness.py`.

Additional 2026-05-27 continuation:

- Added past-only exact-contract quote-continuity metrics in `historical_options_store.py`.
- Added replay-only chain-native prior-quote continuity gates in `wfo_optimizer.py`.
  - `chain_native_min_prior_quote_days`
  - `chain_native_prior_quote_lookback_days`
  - `chain_native_max_entry_leg_bid_ask_pct`
  - `chain_native_min_entry_short_bid`
- Added continuity variants in `scripts/run_bullish_pullback_next_round.py`.
- Added `tests/test_chain_native_continuity.py`.
- Extended `scripts/iterate_thetadata_exact_fill_replays.py` so bounded exact-fill loops can pass `--start-time`, `--end-time`, and `--interval` into the targeted ThetaData importer.

## Best Current Evidence

| Candidate | Exact Trades | PF | Avg PnL | Coverage | 5%/side Slippage PF | Strict Rolling OOS |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `debit45_ret5min3` | 103 | 2.42 | 24.04% | 52.3% | 1.68 | 0/2 passed |
| `debit50_direction65_ret5min3` | 117 | 1.93 | 18.04% | 56.0% | 1.34 | 0/3 passed |
| `debit50_direction65_ret5min3_dte29_45` | 115 | 1.94 | 18.39% | 55.0% | 1.36 | 0/3 passed |
| `debit50_direction65_ret5min3_target120` | 116 | 1.80 | 15.54% | 55.5% | 1.24 | 0/3 passed |
| `ret20_3_debit50_direction70_ret5min3_spymin1` | 102 | 2.03 | 19.13% | 60.7% | 1.41 | 0/1 passed |
| `ret20_25_debit50_direction70_ret5min2_spymin05` | 90 | 2.50 | 25.35% | 60.4% | 1.76 | below 100 exact trades |

### Continuity-Gate Round

The continuity gate is live-safe because it only reads valid bid/ask quote dates strictly before the entry date. It is still replay-only research and should not be promoted into live scan logic until the lane passes strict OOS and unpriced-candidate gates.

| Candidate | Exact Trades | PF | Avg PnL | Coverage | 5%/side Slippage PF | Strict Rolling OOS |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `debit50_direction65_ret5min3_dte29_45_cont2` | 114 | 1.85 | 17.06% | 54.3% | 1.29 | 0/3 passed |
| `debit50_direction65_ret5min3_dte29_45_cont3` | 117 | 1.72 | 15.01% | 55.5% | 1.20 | 0/3 passed |
| `ret20_3_debit50_direction70_ret5min3_spymin1_cont2` | 103 | 2.02 | 18.88% | 61.3% | 1.40 | 0/1 passed |

Best continuity branch by coverage and stressed PF was `ret20_3_debit50_direction70_ret5min3_spymin1_cont2`, but it still failed the only strict OOS window:

- `2025-12-17..2026-02-02`: 25 exact trades, PF 0.84, avg -4.92%, 9 unpriced candidates

The DTE29_45 continuity variants did not solve the weak Jan-Feb window:

- `cont2` `2026-01-02..2026-02-11`: 22 exact trades, PF 0.50, avg -16.54%, 12 unpriced candidates
- `cont3` `2026-01-02..2026-02-11`: 23 exact trades, PF 0.47, avg -17.83%, 12 unpriced candidates

### Exact-Fill Sensitivity Round

Theta Terminal was available locally at `127.0.0.1:25503`, so the current best continuity branch was run through bounded full-session exact-fill cycles.

Important interpretation: full-session fills are a sensitivity/probe policy. They are stronger for proving whether ThetaData has an exact OCC/date quote somewhere in the session, but they are not the same as the original 15:55 proof lane. Promotion still needs one frozen and consistently applied fill policy.

Full-session exact-fill cycles against `ret20_3_debit50_direction70_ret5min3_spymin1_cont2`:

| Cycle | Input Run | Unique Items | Imported Rows | Result |
| --- | --- | ---: | ---: | --- |
| 1 | `20260526_212733...spymin1_cont2` | 54 | 4,677 | coverage improved |
| 2 | `20260526_213314...spymin1_cont2` | 50 | 4,080 | no metric improvement |
| 3 | `20260526_213522...spymin1_cont2` | 47 | 2,518 | no metric improvement |

Best post-refill run:

| Candidate | Exact Trades | PF | Avg PnL | Coverage | 5%/side Slippage PF | Strict Rolling OOS |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `ret20_3_debit50_direction70_ret5min3_spymin1_cont2_refill` | 109 | 1.66 | 14.05% | 65.3% | 1.16 | 0/1 passed |

The refill increased exact trades from 103 to 109 and coverage from 61.3% to 65.3%, but it reduced aggregate PF from 2.02 to 1.66 because newly filled trades included losers. The strict OOS window remained negative:

- `2025-12-17..2026-02-02`: 26 exact trades, PF 0.88, avg -3.56%, 7 unpriced candidates

Remaining unpriced after refill:

- 58 total
- 49 `missing_exit_quote_for_leg`
- 9 `no_chain_native_spread`

Local DB classification of remaining missing exit legs:

- 48 unique missing exact contract/date items
- 0 had exact valid rows in the DB after refill
- 48/48 had same-expiry valid neighbor-chain rows on the missing date
- 0 were whole-chain/date absences

That strongly points to exact-strike sparse/no-match contract selection, not broad data absence.

The best OOS-near-miss remains `debit50_direction65_ret5min3`, but its strict Jan-Feb test window is still negative:

- `2026-01-02..2026-02-11`: 23 exact trades, PF 0.44, avg -19.81%, 10 unpriced candidates

The DTE29_45 neighbor improves that window but does not pass:

- `2026-01-02..2026-02-11`: 22 exact trades, PF 0.50, avg -16.54%, 11 unpriced candidates

## Subagent Debate Synthesis

Data: broad ThetaData coverage is complete for all active symbols. Stop broad-filling; only run exact-fill loops for a final candidate.

Growth: `debit50_direction65_ret5min3` is the best count/OOS near-miss. DTE29_45 is a small improvement; target120 is worse.

Risk: do not promote. OOS fails, unpriced candidates remain, GOOGL/top winners still matter, and the promotable subset is weak.

Implementation: variants are still research-script injected. Live scan thresholds and spread selection are not yet aligned with replay.

Continuation subagent synthesis:

- Data audit confirmed the DB can efficiently check prior quote continuity by exact contract using `contract_symbol`, `snapshot_kind`, and `quote_date_et`; volume/open-interest are not reliable in the current intraday rows.
- Skeptic audit warned that remaining unpriced candidates are not promotion-safe until targeted exact OCC/date refetch is exhausted or the failures are conservatively classified.
- Growth audit ranked the next best test targets as `ret20_25...ret5min2_spymin05`, `debit50_direction65_ret5min3_dte29_45`, and `ret20_3...spymin1`.
- Implementation audit recommended keeping continuity gates replay-only until live/replay parity is deliberately implemented.
- Exact-fill debate concluded that full-session import is useful for diagnosis, but a single consistent execution-time policy must be frozen before promotion.

## Next Bottleneck

Next useful work should focus on live-safe executable-contract selection:

1. Add entry-time contract continuity/liquidity gates that avoid sparse short legs.
2. Prefer spreads whose long and short legs have reliable recent trusted quote continuity before entry.
3. Keep the SPY-regime and DTE filters available, but do not promote them until OOS passes.
4. Move the best candidate config out of the research script and into a replay/live-shared config only after a frozen candidate passes strict OOS.

After the continuity-gate round, the next bottleneck is stricter than simple prior quote continuity:

1. The Jan-Feb 2026 OOS loss regime is still real and survived the continuity gate.
2. Remaining unpriced candidates need targeted exact OCC/date probing, ideally full-session or multiple execution-relevant timestamps, before they can be called true liquidity rejects.
3. If another iteration is run, test a small fixed set only:
   - `ret20_25_stop120_time60_debit50_direction70_ret5min2_spymin05`
   - `debit50_direction65_ret5min3_dte29_45`
   - `ret20_3_stop120_time60_debit50_direction70_ret5min3_spymin1`
   - `debit45_direction70_ret5min3` as the profit control

After the full-session exact-fill round, the bottleneck is now:

1. Exact-strike sparsity/no-match for selected short legs.
2. A real weak OOS window in late 2025 / early 2026 that remains negative even after refills.
3. The need to choose one consistent exit quote policy before comparing candidates.

Recommended next bounded variants from subagent debate:

1. `ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05`
2. `ret20_25_stop120_time60_debit50_direction70_ret5min2_spymin05_npicks6`
3. `ret20_3_stop120_time60_debit50_direction70_ret5min2_spymin1`

Do not promote the current branch. It is positive in aggregate, but failed OOS and remains below the desired proof-grade coverage.

### Shallower-Pullback Refill + Liquidity-Gate Round

The strongest branch after targeted exact-fill is now:

`lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05_shortbid05`

| Candidate | Exact Trades | PF | Avg PnL | Coverage | 5%/side Slippage PF | Strict Rolling OOS |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `ret20_25_direction65_ret5min2_spymin05_refill4` | 110 | 1.63 | 14.25% | 67.5% | 1.16 | 0/1 passed |
| `ret20_25_direction65_ret5min2_spymin05_shortbid05` | 110 | 1.65 | 14.75% | 67.5% | 1.18 | 0/1 passed |
| `ret20_25_direction65_ret5min2_spymin05_shortbid05_refill4` | 111 | 1.59 | 13.78% | 68.1% | 1.14 | 0/1 passed |
| `ret20_25_direction65_ret5min2_spymin05_cont2` | 100 | 1.49 | 11.12% | 68.0% | not rerun | not rerun |
| `ret20_25_direction65_ret5min2_spymin05_shortbid10` | 109 | 1.62 | 14.33% | 66.9% | not rerun | not rerun |
| `ret20_25_direction65_ret5min2_spymin05_cont2_shortbid05` | 100 | 1.51 | 11.67% | 68.0% | not rerun | not rerun |

The short-bid nickel gate is the best simple contract-selection tweak so far. It improves aggregate PF and stressed PF without losing exact trade count. Additional exact-fill passes raised coverage slightly but did not improve the edge, so the best risk/reward snapshot remains the pre-extra-refill `shortbid05` run while the latest fully rerun state is `shortbid05_refill4`.

The strict OOS priced slice is now positive for the best branch:

- `2025-12-11..2026-01-29`: 27 exact trades, PF 2.24, avg 27.63%

The latest rerun after additional targeted fills has:

- `2025-12-11..2026-01-29`: 28 exact trades, PF 1.94, avg 23.30%

It still fails promotion because that same OOS window has 5 unpriced candidates, all missing short-leg exit quotes:

- DIS `DIS260123C00122000` on 2026-01-06
- TSLA `TSLA260130C00545000` on 2026-01-29
- C `C260206C00127000` on 2026-02-02
- V `V260206C00380000` on 2026-01-23
- SBUX `SBUX260227C00106000` on 2026-01-30

The repeated TSLA fill path proved some missing rows can be recovered, but it began walking the TSLA exit forward one day at a time without improving metrics. The remaining non-TSLA OOS misses have repeatedly returned no matched rows in full-session ThetaData exact-fill attempts.

Remaining exact-miss classification after the refill/shortbid round:

- 53 total unpriced candidates
- 45 `missing_exit_quote_for_leg`
- 8 `no_chain_native_spread`
- 42 unique missing exact contract/date items in the missing-exit set
- 41/42 are short legs
- 0/42 have exact valid rows after full-session refills
- 42/42 have same-expiry neighbor-chain rows

Interpretation: the current blocker is not broad data coverage. It is selected short-leg exact-strike sparsity/no-match plus a still-thin stressed edge.

Subagent skeptical review agreed this branch is promising but not promotable:

- 110 exact trades is useful.
- Aggregate and OOS priced metrics are positive.
- 5%/side slippage remains positive but thin.
- Promotion still requires resolving or conservatively classifying the 6 OOS unpriced short-leg exits, then rerunning robustness with one frozen execution policy.

Update after later exact-fill passes: the OOS unpriced count is now 5, but the conclusion is unchanged. This is CONTINUE, not SUCCESS.

### Data Store Audit

The options quote store is more centralized than expected:

- central quote DB: `data/options-validation/options_history.db`
- quote rows: 26,146,760
- trusted ThetaData intraday OPRA/NBBO rows: 7,276,952
- source/trust metadata: `import_batches`
- raw CSV/parquet files under `data/options-validation/*` are import artifacts, not the query source of truth
- run JSON artifacts live under `data/options-validation/runs`
- profitability/robustness reports live under `data/profitability-lab`

Added a reusable audit script:

```powershell
python .\scripts\audit_options_data_store.py --json
```

Applied DB/index cleanup for source/trust scoped audits:

- `idx_option_quotes_source_batch_snapshot_date`
- `idx_import_batches_source_trust_kind`

Forward tracking is still the least tidy area. Treat `data/options-validation/forward_tracking_authoritative.db` as the forward-tracking source of truth and JSONL files under `data/forward-tracking` as logs unless a later audit proves otherwise.

## Verification

Command run:

```powershell
python -m pytest .\tests\test_imported_intraday_robustness.py .\tests\test_imported_daily_walk_forward.py .\tests\test_strategy_audit.py .\tests\test_lane_universe_manifest.py -q
```

Result: 111 passed.

Continuation verification:

```powershell
python -m pytest .\tests\test_chain_native_continuity.py .\tests\test_imported_intraday_robustness.py .\tests\test_imported_daily_walk_forward.py .\tests\test_strategy_audit.py .\tests\test_lane_universe_manifest.py -q
```

Result: 113 passed.

Re-run after exact-fill continuation:

```powershell
python -m pytest .\tests\test_chain_native_continuity.py .\tests\test_imported_intraday_robustness.py .\tests\test_imported_daily_walk_forward.py .\tests\test_strategy_audit.py .\tests\test_lane_universe_manifest.py -q
```

Result: 113 passed.
