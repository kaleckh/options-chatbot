# Regular Options Autoresearch Goal

Use this prompt when running a Karpathy-style `/goal` loop for the regular stock-options lane.

## Objective

Repair the regular stock-options stack so it increases promotable clean trade count under a frozen conservative evaluator. The first target is Lane A zero-bid survivability, not a raw `300`-trade count.

## Frozen Judge

Run the judge before and after every experiment:

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

1. Run the judge and record the baseline ledger row.
2. Pick exactly one hypothesis.
3. Change only the strategy/replay surface needed for that hypothesis.
4. Regenerate the relevant replay and multi-lane artifacts.
5. Run focused tests plus the judge.
6. Keep the change only if it improves `status` to `promotable_clean` or materially reduces blockers without weakening the frozen gates.
7. If the experiment fails, revert only the experiment edits. Do not delete the ledger row.

## First Hypotheses

1. Add causal pre-entry bid/ask continuity filters for both legs, especially short-leg survivability.
2. Test more liquid strike or width alternatives at entry using only pre-entry information.
3. Identify Lane A ticker, DTE, moneyness, and spread-width subsets that survive conservative side-aware replay.
4. Compare conservative side-aware exits against midpoint-only behavior. If the lane only works at midpoint, reject it.
5. After Lane A is clean, pursue separate non-overlapping lanes toward `300`.
