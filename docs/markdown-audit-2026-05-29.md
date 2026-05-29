# Markdown Audit - 2026-05-29

## Scope

Audited the living Markdown docs and generated route map against the current repo state. Historical records under `docs/archive/`, `docs/autoresearch/`, generated progress files, and `research_runs/` remain useful context, but they are not treated as the source of truth when they disagree with code or living docs.

## Findings

- `npm run verify:docs` passed; `docs/route-parity.md` is current with the Next/FastAPI route tree.
- Living docs had one broken internal Markdown link in `docs/autoresearch/automation-handoff.md`; it now points to `../profit-loop/contract.md`.
- `docs/current-state.md`, `docs/NEXT_STEPS.md`, `docs/PROJECT_CONTEXT.md`, `docs/lane-lab-lanes.md`, and `docs/paid-options-data-import-checklist.md` were stale on AI commodity progress. They now reference the latest generated readback from `2026-05-27T14:17:01Z`, the `3` / `100` shared-date state, and the guarded capture command for target date `2026-05-26`.
- The regular options living docs now include the current bullish-pullback exact ThetaData state: high-confidence S/A/B has `108` exact trades at PF `4.86`; count-expanded evidence has `130` exact trades at PF `2.04`; the per-ticker audit remains the current keep/move/research/remove source.
- `README.md` and `docs/index.md` now point readers to the current bullish-pullback ticker audit.

## Verification

Commands run:

```powershell
npm run verify:docs
python -m pytest tests\test_bullish_pullback_ticker_audit.py tests\test_bullish_pullback_confidence_tiers.py tests\test_wfo_sleeve_selection.py tests\test_imported_intraday_robustness.py -q
```

The broader Markdown link audit intentionally excludes `node_modules`, `research_runs`, and `docs/archive`; living-doc links have no missing internal Markdown targets after the automation-handoff fix.
