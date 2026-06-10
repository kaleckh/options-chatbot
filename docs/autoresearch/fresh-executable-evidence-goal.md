# Fresh Executable Evidence Goal

Use this prompt for the forward-evidence collection loop after Sprint 1 evaluator and flywheel repairs.

## Single Objective

Convert the paper-gate pipeline from `0` fresh exact realized-P&L rows into a measured forward sample. Target: at least 20 fresh paper rows with executable realized exit P&L inside the goal window.

Success metric: `exact_realized_pnl_count` and `promotion_discussion_ready_count` from:

```powershell
python scripts/build_regular_options_fresh_evidence_loop.py --json
```

Nothing else counts: not replay PF, not Tier A historical evidence, not coverage.

## Evidence Standard

Every realized row must have trusted intraday OPRA/NBBO exact-contract entry and exit quotes, with P&L computed at executable side-aware prices. Long exits sell at bid; short exits buy at ask. Never count paper marks, midpoint marks, stale snapshots, last trades, or daily/EOD rows.

Every readback must distinguish executable exit P&L from display-only mark P&L.

## Loop

1. Run `scripts/build_regular_options_paper_shortlist.py` and `scripts/validate_pending_scan_candidates.py` daily during quote windows. Record why each pending candidate did or did not produce a fill attempt in `fill_attempts.jsonl`.
2. For each blocker class keeping `eligible_count=0`, pick the largest-count blocker, fix only the pipeline defect that causes it, and rerun. Do not loosen guardrails, proof bars, or the Tier A bridge definition to manufacture eligibility.
3. After every 10 realized rows, compute realized executable PF and average P&L of the cohort and append it to the ledger. Copy those realized cohort numbers verbatim into the next strategy goal baseline.

## Sample-Size Honesty

Do not draw profitability conclusions from fewer than 20 realized rows. Report cohort P&L as `collecting (n=X)` until then. A 20-row cohort supports only a coarse go/no-go on sign, not PF precision.

## Stop Rule

If after 10 trading sessions zero candidates reach a fill attempt, the deliverable is a defect report naming the exact gate, file, and readback field blocking the funnel, with a proposed fix for operator review.
