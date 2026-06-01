# Regular Options Autoresearch Goal

Use this prompt when running a Karpathy-style `/goal` loop for the regular stock-options lane.

## Objective

Improve proof-grade closed profitability across the active regular supervised options product. This has two measured surfaces:

- product closed-profitability progress in the Trading Desk, using executable/truth-grade closed rows and read-only replay audits
- historical proof-grade progress under the frozen regular-options autoresearch evaluator, using trusted intraday OPRA/NBBO exact-contract evidence only

The goal is not to produce more rows, more experiments, or a raw `300`-trade count. Every loop must show a measured delta in the operating scorecard, or it must retire the failed branch and name the next higher-leverage branch.

## Operating Scorecard

Run the operating scorecard before and after each meaningful loop:

```powershell
python scripts/build_regular_profitability_operating_scorecard.py --json
```

The scorecard writes:

- `data/profitability-lab/regular-options-operating-scorecard/latest.json`
- `docs/regular-options-operating-scorecard.md`

Interpret the status literally:

- `proof_grade_profitability_ready`: the frozen proof judge has real clean-profitability progress.
- `visible_product_profitability_progress_but_proof_still_blocked`: Trading Desk profitability improved, but the exact-contract proof stack is still blocked.
- `no_material_profitability_progress_visible`: stop the branch and pick a sharper hypothesis.

The operator-facing answer to "are we seeing results?" comes from this scorecard, not from vibes, trade count, or isolated PF on a rejected scout.

## Frozen Judge

Run the judge before and after every historical proof experiment:

```powershell
python scripts/evaluate_regular_options_autoresearch.py --refresh-multilane --experiment-id <slug> --hypothesis "<one hypothesis>" --append-ledger --score-line
```

The judge writes:

- `data/profitability-lab/regular-options-autoresearch/latest.json`
- `data/profitability-lab/regular-options-autoresearch/latest.md`
- `data/profitability-lab/regular-options-autoresearch/ledger.jsonl`

During a `/goal` run, do not edit `scripts/evaluate_regular_options_autoresearch.py`, this goal file, or the ledger schema. Strategy experiments may edit strategy/replay code and generate artifacts, but the evaluator stays fixed until a human explicitly changes it outside the run.

## Promotion Gates

Historical `promotable_clean` requires:

- trusted intraday OPRA/NBBO exact evidence only
- strict portfolio dedupe by entry date, ticker, and direction
- clean count `>=200`
- PF `>=1.50`
- avg PnL `>0`
- effective quote coverage `>=97.5%`
- unresolved candidates `0`
- 5%/side stress PF `>=1.25`
- rolling/OOS status `passed`
- counted Lane A must have side-aware conservative zero-bid replay
- Lane A conservative PF `>=1.30`
- zero-bid exit rate `<=2%`

Production readiness additionally requires paper-shadow status `passed`.

## Loop Rules

1. Run the operating scorecard and identify the weakest measured surface.
2. Pick exactly one hypothesis with a measurable expected delta.
3. For Trading Desk closed-profitability work, use executable/truth-grade closed rows, read-only replay/audit first, and never synthesize exits from midpoint, last trade, stale, daily/EOD, or lifecycle-only rows.
4. For historical proof work, change only the strategy/replay surface needed for the hypothesis, then regenerate the relevant replay and multi-lane artifacts.
5. Run focused tests plus the scorecard. Run the frozen judge when the hypothesis touches the historical proof stack.
6. Keep the change only if it improves `status` to `promotable_clean`, materially improves the Trading Desk closed-profitability surface without weakening proof rules, or retires a branch with evidence that prevents wasted future loops.
7. If the experiment fails, revert only disposable experiment edits. Keep audit artifacts and docs that prevent repeating the same failed branch.

## Current High-Leverage Hypotheses

1. Audit legacy rows `26`, `39`, and `44` to explain why stored executable time-exit-style SELL evidence did not realize before final negative closure. Fix only if the cause applies to current state-changing review behavior, not merely historical migration.
2. Keep promoted Trading Desk entry guardrails active and monitor scan starvation before loosening them.
3. Stop tuning Lane A entry, memory, or broad bad-zero-ticker variants unless a genuinely new causal exit/liquidity rule changes the zero-bid economics.
4. Pursue non-overlapping regular stock-options sleeves or materially different exit/liquidity rules that can add at least `43` strict-new clean trades over the `157` clean baseline.
5. Reject any branch that only improves midpoint, stale, daily/EOD, or research/backfill paper evidence.
