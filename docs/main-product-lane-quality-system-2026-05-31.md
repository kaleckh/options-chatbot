# Main Product Lane Quality System - 2026-05-31

## Scope

This report turns the all-lanes negative-trade audit into a repair backlog for the Trading Desk regular supervised options product lane. It uses the existing tracked-position audit artifacts only; it does not treat crypto, Polymarket, day-trading, or AI commodity lanes as in scope.

Primary inputs:

- `docs/main-product-lane-negative-trade-audit-2026-05-31.md`
- `data/forward-tracking/main_product_lane_negative_trade_audit_20260531.json`
- `data/forward-tracking/main_product_lane_negative_trade_audit_20260531.csv`
- `data/forward-tracking/main_product_lane_repair_metrics_20260531.json`
- `data/tracked_positions.pre-historical_suggested_close_realized_pnl_repair_v1-20260531-132506.json`

Evidence rules are unchanged: trusted intraday OPRA/NBBO exact-contract bid/ask evidence is the proof standard, research/backfill rows are not live-production proof, and missed-exit claims require executable timestamped review evidence.

## System Read

| Class | Rows | Negative | Read |
|---|---:|---:|---|
| Live exact tracked | 5 | 0 | No negative live exact tracked rows found; sample is too small for promotion claims |
| All-lanes zero-pick research backfill | 425 | 182 | Main learning set, not production proof |
| Main-lane zero-pick research backfill | 60 | 26 | Bullish Pullback learning set, not production proof |
| Legacy or unknown tracked | 46 | 5 | Quarantine before using in promotion metrics |
| Total | 536 | 213 | `62` rows are unknown/unpriced and must not be forced into wins/losses |

The first product rule is therefore provenance, not stop tightening: production metrics must exclude research backfill rows and quarantine legacy/unclassified rows unless a report explicitly says it is measuring research/paper learning.

## Implementation Status

The Trading Desk tracked-position surface now applies this rule in the operator summary layer:

- Open and closed summary cards separate production-proof rows from research/paper rows instead of blending them into a single win-rate or average-P&L read.
- The tracked-position table keeps row-level evidence labels visible.
- A compact evidence-mix strip shows `Live exact`, `Manual exact`, `Historical paper`, `Research backfill`, `Lifecycle-only`, `Proof ineligible`, and `Legacy/unclassified` counts for the visible rows.
- A lane-quality panel summarizes the repair lanes across `short_term`, `swing`, `bullish_momentum`, and Bullish Pullback.
- A read-only guardrail panel measures candidate filters against visible repair-lane rows, reporting avoided negative rows, lost positive/flat rows, and unknown rows without changing trade selection.
- The scanner now enforces the replay-backed entry repair rules for `short_term`, `swing`, `bullish_momentum`, and Bullish Pullback: debit over `45%` of width, fill degradation at or above `20%`, worst-leg bid/ask spread at or above `20%`, lane-specific ticker quarantines, Bullish Pullback keep-bucket enforcement, and Bullish Pullback `ret5 >= -2`.
- Momentum-chase blocking was not adopted because the all-row replay showed it would remove too many winners.

Implementation files:

- `src/components/predictions/PredictionsView.tsx`
- `src/lib/types.ts`
- `supervised_scan.py`
- `scripts/analyze_trading_desk_profitability_guardrails.py`
- `docs/trading-desk-profitability-guardrails-2026-05-31.md`

## Lane State

| Playbook | Rows | Negative | Unknown | Priced Neg Rate | State |
|---|---:|---:|---:|---:|---|
| `short_term` | 159 | 84 | 13 | 57.5% | P1 repair lane; pause promotion, inspect ticker/debit/exit survivability |
| `swing` | 157 | 60 | 24 | 45.1% | P1 repair lane; biggest unknown/unpriced cleanup target |
| `bullish_momentum` | 51 | 23 | 1 | 46.0% | P1 repair lane; fewer rows but severe losses |
| `bullish_pullback_observation` | 62 | 26 | 8 | 48.1% | P1 repairable by existing ticker-bucket policy first |
| `tracked_winner_observation` | 35 | 7 | 9 | 26.9% | P2 evidence cleanup; do not judge until unknowns shrink |
| `volatility_expansion_observation` | 13 | 5 | 4 | 55.6% | P2 small-sample repair; likely hold until more evidence |
| `tracked_winner_primary` | 12 | 3 | 2 | 30.0% | P2 small sample; open-negative review target |
| `legacy_unlabeled` | 46 | 5 | 0 | 10.9% | P0 provenance cleanup, not a lane-quality signal |
| `range_breakout_observation` | 1 | 0 | 1 | n/a | No conclusion |

## Failure Taxonomy

| Failure Mode | Evidence | Repair Direction |
|---|---|---|
| Provenance confusion | `208` of `213` negatives are research/backfill | Separate production metrics, research learning metrics, and legacy rows everywhere |
| Backfilled lane weakness | `short_term`, `swing`, and `bullish_momentum` contribute `167` negatives | Pause promotion reads and run lane-specific repair probes |
| Bullish Pullback bucket drift | Most Bullish Pullback negatives are outside the current keep bucket | Enforce keep/move/remove buckets before new current-lane tracking |
| High debit/width exposure | A debit-over-45%-width probe blocks `46` negatives, `26` positive/flat, and `5` unknown rows | Replay as a candidate cap; do not adopt solely from backfill filtering |
| Ticker concentration | SLB probe blocks `16` negatives and `1` positive/flat; NVDA blocks `13` negatives and `6` positive/flat | Test lane-specific ticker quarantines, especially SLB and NVDA |
| Unknown/unpriced exits | `62` total unknown rows, led by `swing` `24`, `short_term` `13`, `tracked_winner_observation` `9`, Bullish Pullback `8` | Import exact exit evidence or keep rows visibly unpriced |
| Missing review timeline | `186` of `213` negative rows have no intra-life `position_reviews` | Do not claim missed exits; add deterministic historical review snapshots only if needed |
| Legacy classification debt | `46` legacy rows are not cleanly production/research classified | Quarantine from proof metrics until source/proof class is reconstructed |

## Ticker And Entry Signals

Negative-only concentration analysis joined `208` of `213` negative rows back to scan/fill logs. The five unmatched rows are legacy/unclassified.

Top ticker/playbook negative clusters:

| Playbook | Ticker | Negatives | Avg P&L |
|---|---:|---:|---:|
| `short_term` | XLK | 14 | `-54.8%` |
| `short_term` | IWM | 12 | `-53.7%` |
| `short_term` | SPY | 8 | `-38.0%` |
| `short_term` | DIA | 8 | `-47.1%` |
| `swing` | IWM | 8 | `-59.1%` |
| `swing` | XLK | 8 | `-65.5%` |
| `short_term` | SLB | 7 | `-48.1%` |
| `swing` | SLB | 7 | `-64.9%` |
| `bullish_momentum` | NVDA | 6 | `-81.8%` |
| `tracked_winner_observation` | GOOGL | 5 | `-67.4%` |

Candidate filters to replay against all rows, not just negatives:

- Research-tag or block `fill_degradation_vs_mid_pct >= 20`; the negative slice had `79` such rows averaging `-63.7%`.
- Research-tag or block worst-leg bid/ask spread `>= 20%`; the negative slice had `73` such rows averaging `-64.8%`.
- Treat the intersection of both conditions as high risk; the negative slice had `60` rows averaging `-65.3%`.
- Require extra proof for momentum-chasing rows where `ret5 >= 5`, especially when paired with `direction_score >= 85` or `quality_score >= 75`.

These are candidate repair hypotheses, not adopted product rules, because the analysis was negative-only. The next pass must measure lost winners and unknown-row effects before hard blocking.

## Exit Evidence

The audit found little support for broad "we failed to close winners" claims:

| Exit Evidence Slice | Count |
|---|---:|
| Negative rows | 213 |
| Negative rows with any `position_reviews` | 27 |
| Negative rows with no review history | 186 |
| Negative rows with executable `SELL` reviews | 10 |
| Negative rows with an earlier positive executable `SELL` review | 3 |
| Closed lifecycle-only/unpriced rows across the tracked ledger | 61 |

The three clear earlier-positive executable sell cases are legacy/unclassified rows, not all-lanes research backfills and not live exact rows:

| ID | Ticker | Final P&L | Best Executable Review |
|---:|---|---:|---:|
| `26` | JPM | `-44.78%` | `+45.38%` |
| `39` | DIA | `-42.98%` | `+3.05%` |
| `44` | JPM | `-80.10%` | `+12.53%` |

Those rows deserve a separate legacy auto-close audit. For the broad all-lanes research negatives, the stored executable sells were already negative stop exits, not missed positive closes.

Before calling any row a missed exit, require exact stored contract/spread legs, a timestamped review or replay checkpoint, trusted exact bid/ask exit evidence, `price_trigger_ok=true`, non-null `exit_execution_price`, and executable basis such as `bid` or `spread_bid_ask`.

## Guardrail Probes

The first negative-only probes came from `main_product_lane_repair_metrics_20260531.json`. The all-row replay in `docs/trading-desk-profitability-guardrails-2026-05-31.md` then measured lost winners and promoted only the passing entry rules.

| Probe | Blocked Rows | Blocked Neg | Blocked Pos/Flat | Blocked Unknown | Read |
|---|---:|---:|---:|---:|---|
| Exclude research backfills from production metrics | 485 | 208 | 215 | 62 | Adopt as reporting/proof gate |
| Pause `short_term` research backfill | 159 | 84 | 62 | 13 | Highest severity; repair first |
| Pause `swing` research backfill | 157 | 60 | 73 | 24 | Repair first, but watch opportunity cost |
| Pause `bullish_momentum` research backfill | 51 | 23 | 27 | 1 | Severe losses; repair first |
| Debit over 45% width | 77 | 46 | 26 | 5 | Strong candidate; needs replay tradeoff test |
| Ret5 below `-2` | 6 | 6 | 0 | 0 | Narrow but clean Bullish Pullback warning |
| SLB backfill quarantine | 20 | 16 | 1 | 3 | Strong ticker quarantine candidate |
| NVDA backfill quarantine | 23 | 13 | 6 | 4 | Candidate for momentum/high-beta-specific guard |
| DIA backfill quarantine | 45 | 19 | 14 | 12 | Mixed; likely lane-specific, not global |
| XLK, QQQ, SPY backfill quarantine | 163 combined rows | 52 | 94 | 17 | Do not global-ban; too many positive/flat rows blocked |

Promoted scanner guardrails now in force:

| Guardrail | Scope | Replay Read |
|---|---|---|
| Debit over `45%` of width | `short_term`, `swing`, `bullish_momentum`, Bullish Pullback | Kept rows improved to `12.3%` average P&L for the single probe |
| Fill degradation `>= 20%` versus midpoint | Same repair lanes | Kept rows improved to `19.31%` average P&L |
| Worst-leg bid/ask spread `>= 20%` | Same repair lanes | Kept rows improved to `16.78%` average P&L |
| Lane-specific ticker quarantine | `short_term`, `swing`, `bullish_momentum` | Kept rows improved to `19.03%` average P&L |
| Bullish Pullback keep bucket | Bullish Pullback | Enforces the current ticker audit keep set |
| Bullish Pullback `ret5 < -2` block | Bullish Pullback | Blocked `6` rows, all negative |

Combined replay effect for promoted guardrails: baseline `429` rows had `193` negatives among `383` priced rows, `5.21%` average P&L, and `-1.58%` median P&L. The promoted kept subset is `130` rows with `29` negatives among `116` priced rows, `53.08%` average P&L, and `46.4%` median P&L. The blocked set remains audit-visible rather than rewritten out of history.

## Repair Backlog

### P0 - Metric And Provenance Safety

1. Production-proof summaries must exclude `all_lanes_zero_pick_research_backfill` and `main_zero_pick_research_backfill` unless the report explicitly says it is a research/backfill audit.
2. Legacy/unclassified rows should be visible but quarantined from lane promotion metrics.
3. Trading Desk evidence labels should continue to show `Live exact`, `Research backfill`, `Historical paper`, `Lifecycle-only`, and `Legacy/unclassified`.
4. Summary cards such as Closed Trades, Win Rate, and Avg P&L should either filter by provenance or show grouped provenance stats so research losses cannot look like live scanner losses.

### P1 - High-Leverage Lane Repair

1. `short_term`: investigate XLK, IWM, SPY, DIA, QQQ, and SLB concentration; test debit/width cap, liquidity/quote freshness, and zero-bid survivability before allowing promotion language.
2. `swing`: prioritize unknown/unpriced cleanup, then test the same debit/width and ticker concentration probes; do not adopt broad index/ETF bans because they block many positive rows.
3. `bullish_momentum`: inspect NVDA, TSLA, COIN, NFLX, WMT, and SLB; test high-beta/event guardrails and contract survivability.
4. `bullish_pullback_observation`: enforce current keep/move/remove buckets and test the `ret5 < -2` warning as a small but clean backfill-derived guard.

### P1 - Exit Replay And Legacy Close Audit

1. Add historical review-snapshot replay for backfills before making missed-exit claims.
2. Replay profit-harvest, trailing-giveback, and lane-specific time exits using executable bid/ask only.
3. Compare `50%` versus `90%` stop behavior as a replay experiment, not as an assumed fix.
4. Run a legacy auto-close audit for rows `26`, `39`, and `44`.
5. Dry-run current-policy reviews for open negatives before any state-changing review endpoint is called.

### P2 - Evidence Cleanup Before Judgment

1. `tracked_winner_observation`: resolve or label the `9` unknown rows before treating the lane as weak; GOOGL concentration needs separate review.
2. `volatility_expansion_observation`: small sample with high unknown rate; keep as scout until exact exits improve.
3. `tracked_winner_primary`: review open negatives with executable bid/ask evidence only.
4. `range_breakout_observation`: no conclusion; one unknown row is not a lane signal.

## Next Goal Prompt

```text
Implement the all-lanes negative-trade repair backlog for the Trading Desk regular supervised product lane.

Use docs/main-product-lane-quality-system-2026-05-31.md, docs/main-product-lane-negative-trade-audit-2026-05-31.md, and the negative ledger as the starting evidence. First make product metrics provenance-safe, then replay lane/ticker/contract-quality guardrails against both positive and negative rows before making any hard blocks.

Do not touch crypto, Polymarket, day-trading, or AI commodity lanes.

Priorities:
P0: Make production-proof metrics exclude research/backfill, lifecycle-only, unresolved, and legacy/unclassified rows unless explicitly grouped as research evidence.
P1: Build all-row guardrail reports for short_term, swing, bullish_momentum, and Bullish Pullback bucket enforcement.
P1: Test lane/ticker gates, fill degradation, worst-leg spread, high-debit, and ret5 momentum-chase filters against both avoided losers and lost winners.
P1: Replay profit harvest, trailing giveback, and time-exit variants using trusted exact bid/ask only; audit legacy rows 26, 39, and 44 separately for missed auto-closes.
P3: Add historical review snapshots and policy/quote-quality instrumentation for future backfills.
```

## Verification Plan

Smallest useful checks for the next implementation pass:

```powershell
npm run verify:docs
python scripts/audit_zero_pick_days_all_lanes.py --no-write-report
python scripts/repair_historical_backfill_realized_pnl.py --as-of-date 2026-05-31
python scripts/evaluate_regular_options_autoresearch.py --no-write --score-line
```

Use replay or frozen-evaluator checks before adopting any entry/exit guardrail. A filter is only a repair candidate if it reduces bad research rows without silently hiding profitable rows or weakening exact bid/ask evidence standards.
