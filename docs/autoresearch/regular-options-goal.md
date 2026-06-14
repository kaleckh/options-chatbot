# Regular Options Clean-Proof Goal v2

Use this prompt when running a strategy `/goal` loop after the evaluator-gradient repair has landed.

## Single Objective

Increase the strict-deduped clean exact-trade stack from the 157-trade core baseline toward 200 without counting Lane A, measured only by the frozen evaluator:

```powershell
python scripts/evaluate_regular_options_autoresearch.py --refresh-multilane --experiment-id <slug> --hypothesis "<one hypothesis>" --append-ledger --score-line
```

Primary metrics, reported before and after every loop from the evaluator score line:

- M1: strict-deduped clean exact trade count, deduped by date, ticker, and direction.
- M2: portfolio PF on conservative side-aware pricing, not priced-only PF.
- M3: 5%/side slippage-stress PF.
- M4: diagnostic bootstrap PF 5% lower bound and `stat_conf`, used to separate possible edge from selection luck without changing the frozen `score`.

A loop succeeds only if M1 increases by at least 10 strict-new clean trades while M2 stays at least 1.50 and M3 stays at least 1.25 on the combined stack, all on trusted intraday OPRA/NBBO exact-contract evidence with executable side-aware exit pricing. Never count midpoint, last-trade, daily/EOD, stale-snapshot, or unresolved rows.

Bootstrap readbacks are trade-level resamples over net P&L%, seeded and deterministic. They are diagnostic only: `underpowered` means the point PF looks positive but the 5% lower bound falls below 1.0, `confident_positive` means the lower bound is above 1.0, and `negative_or_flat` means the branch has not established a positive PF lower bound. No-loss PF remains undefined rather than promoted through a sentinel.

Search-effort readbacks are also diagnostic only. The evaluator counts distinct variants already evaluated per `strategy_family` from the autoresearch ledger and reports `variants_searched` plus `selection_adjusted_bar`. Formula: `selection_adjusted_bar = 1.0 + 0.05 * log2(max(variants_searched, 1))`, rounded to two decimals. This is an advisory PF-LB discussion bar, not a frozen `score` or `progress_score` gate.

## Hard Constraints

1. Lane A variants, entry-memory variants, symbol-health variants, and backfill-count variants are banned.
2. Coverage improvements do not count as progress. Quote coverage and unresolved-count are eligibility preconditions only.
3. A variant needs at least 30 exact out-of-sample trades in rolling test windows before its PF may be compared to baseline. Below that, record `insufficient_sample` and stop tuning it.
4. Allowed search space this cycle: extending replay lookback to 2 or 3 years for existing clean core sleeves with chronological train/validation/final-OOS splits; genuinely non-overlapping symbol sets from the ticker-audit research/data-needed bucket after trusted ThetaData intraday import; or one materially different exit/liquidity rule with a preregistered causal hypothesis.
5. Preregister every variant in the ledger before looking at its results. Use one hypothesis per loop.

## Stop Rules

If two consecutive loops fail to add at least 10 strict-new clean trades, stop and write a data-bottleneck report: which symbols/dates lack trusted intraday coverage, the import cost to fix it, and whether 200/year is achievable from this universe at all.
