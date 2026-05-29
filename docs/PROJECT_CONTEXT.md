# Project Context

This repository is a mixed Next.js and FastAPI options research system. The active product lane is supervised options scanning, replay diagnostics, suggested trades, and tracked-position review.

The current AI commodity / commodity-infrastructure lane is a proof-first options lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`. Its preferred final proof path is Alpaca SIP/OPRA bid/ask snapshot replay using `alpaca_opra_daily_snapshot` rows in `data/options-validation/options_history.db`.

The lane must not claim profitability from underlying bars, option OHLC bars, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, or in-sample-only sweeps. Final promotion requires point-in-time bid/ask or NBBO replay with realistic costs and validation splits.

For the regular `bullish_pullback_observation` lane, historical proof currently uses trusted ThetaData intraday OPRA/NBBO rows only. Imported replay lookup helpers support a `trusted_only` mode, and the research runner supports entry-time execution-aware ranked backfill, tier-aware sleeve selection, allocation caps, selected-contract execution memory, fixed-time spread exit monitoring, calendar-basis spread time exits, and by-sleeve diagnostics. The current profitability-first paper/live-shadow family is the no-CAT/no-PM hard-prior fixed-exit sleeve family. The strongest 100+ exact-trade branches are ticker-cluster fixed-exit variants: `sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1` is the high-PF branch with unresolved provider no-matches, and `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1` is the higher-coverage quoted branch with one unresolved provider no-match. `sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1` is the clean quoted proof subset with `95` exact trades and no unresolved candidates, but it is below the `100`-trade target. The count-expanded all-59 paper-shadow branch is `sleeve_pf59_coverage_a_refill_v1` with `130` exact quoted trades at PF `2.04` and `97.7%` quote coverage, but it remains strict-proof blocked by `3` unresolved WMT/JNJ provider no-match candidates. Confidence-tier reporting lives under `data/profitability-lab/bullish-pullback-observation/confidence/` and should be used to separate tradable S/A/B evidence from scout-only broad-symbol evidence. The per-ticker audit under `data/profitability-lab/bullish-pullback-observation/ticker-audit/` is the current source for keep/move/research/remove decisions across the full `59`-symbol universe.

Latest local AI commodity readback:

- generated: `2026-05-27T14:17:01Z`
- exact shared quote dates: `3` / `100`
- proof source: `alpaca_opra_daily_snapshot`
- scan/proof universe: `24` aligned symbols
- live scan candidates: `0`
- next guarded capture target: `2026-05-26`, due now when Alpaca credentials and market-data access are available
- next guarded command: `python scripts/run_ai_commodity_opra_progress.py --force-capture --target-date 2026-05-26`
- full replay unlock projection at one capture per market day: `2026-10-12`

Alpaca account probing shows historical option bars and trades are available, but historical option quotes returned `404`, so they do not currently accelerate the exact bid/ask proof path. OnclickMedia EOD bid/ask data is research-grade only, not OPRA-certified final proof.

## Active Lane Scope

Until this document is updated or the user explicitly reopens a lane, project work should stay focused on:

- Regular supervised options lane: live scan, replay diagnostics, forward evidence, suggested trades, and tracked-position review.
- AI commodity / commodity-infrastructure options lane: proof-first OPRA/SIP/NBBO validation and related automation.

The following lanes are out of scope for active work:

- Crypto options lane under `crypto_options/*`.
- Polymarket lane under `src/lib/polymarket/*` and related scripts.
- Day-trading lane under `src/lib/day-trading/*`, day-trading tests, and legacy day-trading docs. This lane is paused, not deleted.

Do not spend implementation, performance, research, documentation, or automation effort on out-of-scope lanes unless the user explicitly asks to archive, remove, repair, or reopen one of them. Shared infrastructure changes may touch adjacent files only when required for the regular options lane or the AI commodity lane.

Relevant commands:

```bash
npm run build
npm run verify
uv run --locked python -m unittest discover -s tests -p "test_*.py" -v
python scripts/run_ai_commodity_opra_progress.py --next-execution --from-latest
python scripts/audit_paid_data_readiness.py --json
npm run accuracy:report
npm run verify:accuracy:no-write
```

## Agent Worktree Hygiene

Agents should read `docs/agent-worktree-hygiene.md` before broad edits, recurring automation work, or any audit expected to touch multiple files. Big verified changes should be pushed to a `codex/` branch or PR when publishing is allowed, instead of being left only as a large dirty worktree. Required untracked files must be reported and included before release.
