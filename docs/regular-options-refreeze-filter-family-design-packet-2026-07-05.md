# Regular Options Refreeze / Filter-Family Design Packet (2026-07-05)

- Status: `design_only_hypothesis_family_packet`
- Authority: NONE. `research_only_not_forward_proof`.
- Contract: `data/contracts/regular-options-refreeze-filter-family-research-contract-v1.json`
- Activation record: `docs/DECISIONS.md` 2026-07-05 operator activation entry
- Frozen policy preserved: `train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906` (conditions hash `3b10d0306800e1a203480b80e4fafda03d5e1b6443d8d294cbf8ff7f20324967`)
- Forward evidence bar preserved: `regular_options_filtered_forward_evidence_bar_v1` (30 completed rows, unchanged)

This packet defines falsifiable hypothesis families only. No family is evaluated here. No window is consumed here. Evaluation requires a separate pre-registered family-definition JSON, a window split that excludes the consumed `2026-02`..`2026-05` audit window, the consumed `2022-01`..`2024-05` out-of-sample window, and protected holdout, and a separate operator approval packet before any refreeze.

## Evidence Inputs (read-only, hashes recorded in contract)

- Phase 2 drop decomposition (target 2026-07-02): `2,398` scheduled drops over `77` sessions, `0` returned picks. `momentum=1,710` (71.3%), `option_liquidity=384` (16.0%), `history_or_liquidity=304` (12.7%). By playbook: `bullish_pullback_observation` 38 sessions / 2,242 drops / 0 picks; `volatility_expansion_observation` 39 sessions / 156 drops / 0 picks.
- Materializer stationarity: post-freeze `182` accepted rows, `0` frozen-filter matches; zero-run within historical variation (10.8% of 13-day windows; 2024-10 was a full zero month); minimum historical distance below the frozen threshold `0.0236` percentage points; scheduled-session time overlap with the materializer entry window only `14/341` distinct times.
- Parity diff: one SPY `2026-06-16` scheduled-session vs materializer-entry-window divergence row.

## Family F1: Production Momentum-Gate Alignment (`production_gate_drop_key_family_hypotheses`)

Hypothesis: the production scanner's momentum gate is stricter than, or measures a different quantity than, the frozen filter's `prior_20_trading_day_return_pct >= 10.9906` signal, so symbol-days the frozen filter would match are dropped upstream and never reach the filter. The 71.3% momentum drop share with 0 returned picks across 77 sessions is consistent with an upstream gate that starves the lane in the current regime.

Falsifiable family (design only): `F1(p)` = production momentum gate parameterized by percentile-or-threshold `p`, aligned against the frozen filter's measured signal on the same symbol-day. Family members differ only in `p` and in the measurement window used by the gate. Null to refute: relaxing the production gate toward the frozen filter's own threshold does not increase filter-matched candidate throughput in a fresh, never-consumed window.

Required before any evaluation: preregistered family-definition JSON naming `p` grid; fresh-window-only split (candidate windows: pre-2022 history under a new contract, or future post-freeze forward data not used by the current bar); no consumed-window or holdout contact; production scanner policy unchanged during research.

## Family F2: Session-Time / Entry-Window Alignment (`scanner_materializer_timing_alignment_hypothesis`)

Hypothesis: scheduled scan sessions run at times that overlap the materializer entry window on only `14/341` distinct session times, so the production lane and the frozen evidence lane observe different intraday states; the SPY 2026-06-16 divergence is one observed instance.

Falsifiable family (design only): `F2(w)` = candidate emission conditioned on session time within window `w` of the materializer entry minute (ET 10:10). Null to refute: aligning session time to the entry window does not change the frozen-filter match rate on fresh windows.

Required before any evaluation: same preregistration and window-exclusion requirements as F1; timing analysis may use existing diagnostic artifacts descriptively but may not score filter variants on consumed windows.

## Family F3: Threshold-Distance Sensitivity (deferred)

The stationarity report shows historical near-misses approaching within `0.0236` points of the frozen threshold. A threshold-relaxation family `F3(t)` is definable but is explicitly deferred: any `t` chosen while the forward bar is active and the consumed windows are the only labeled data would be selection on consumed evidence. F3 may only be defined after a new never-consumed window exists under its own contract.

## Addendum 2026-07-06: Preregistered Family Grid And Term-Level Drop Diagnostic

Machine-readable family definitions now exist in `data/contracts/regular-options-filter-family-preregistration-draft-v1.json` (F1a ret20-threshold grid, F1b ret5-band grid, F1c trend-anchor grid, F2 emission-window grid), grounded in the actual production gate read from `options_chatbot.py` (pullback gate: `price > sma50 AND ret20 > 2.0 AND -4.0 < ret5 < 0.25`).

Descriptive term-level failure tally over `8,045` unique post-freeze (2026-06-14+) pullback momentum drops from the scheduled-scan ledger (counts only; no profitability scoring; no window consumption):

- `ret20 > 2.0` fails on `5,683` drops (70.6%); post-freeze ret20 median is `-5.19` (p25 `-12.03`, p75 `3.10`) — the market regime is broadly below the uptrend-momentum requirement.
- ret5 band `(-4.0, 0.25)` fails on `5,647` (70.2%); `2,353` drops (29.2%) fail ONLY the ret5 band — the largest near-miss slice, making F1b the highest-leverage family.
- `price > sma50` fails on `4,748` (59.0%); `2,571` drops (32.0%) fail all three terms.

Interpretation boundary: these are admission statistics, not edge statistics. Widening any term admits more candidates but says nothing about profitability; only the future fresh-window one-shot family evaluation (2018-01..2021-12 candidate window, separate contract, split before import) can rank families on economics.

## Prohibited Here

No scanner-policy change, no filter/threshold change, no proof-bar change, no cohort append, no quote import, no evidence mutation, no protected-holdout use, no live validation, no auto-track, no broker orders, no promotion, no treating historical or diagnostic rows as forward proof.
