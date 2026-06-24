Continue the same regular-options profitability loop in this existing Pro Extended session.

Codex completed the selected read-only `quote_surface_opening_range_reversal_vertical_v1` task.

Real implementation:
- Added `scripts/build_regular_options_quote_surface_opening_range_reversal_replay.py`.
- Added `tests/test_regular_options_quote_surface_opening_range_reversal_replay.py`.
- Added npm script `options:research:quote-surface-opening-range-reversal-replay`.
- Generated `docs/regular-options-quote-surface-opening-range-reversal-replay.md`.
- Generated latest JSON/Markdown plus `daily_denominator.jsonl` and `candidate_rows.jsonl` under `data/profitability-lab/regular-options-quote-surface-opening-range-reversal-replay/`.
- Updated `docs/WORKLOG.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, `docs/index.md`, and `docs/PROJECT_CONTEXT.md`.

Real result:
- `status=blocked_quote_surface_opening_range_reversal_replay`.
- `read_only_db_open=true`.
- Base clean stack identity hash count: `157`.
- Window: `2024-06-01` through `2026-05-31` as of `2026-06-04`.
- Universe: `SPY, QQQ, IWM, DIA`.
- Daily denominator rows: `1,976`.
- Denominator status counts: `blocked_missing_underlying_price=1,976`.
- Candidate rows: `0`.
- Full-window exact completed rows: `0`.
- Full-window strict-new rows after opportunity dedupe: `0`.
- Latest-four months: `2026-02, 2026-03, 2026-04, 2026-05`.
- Latest-four strict executable completed rows after opportunity dedupe: `0/30`.
- Blockers: `blocked_missing_quote_surface_underlying_price`, `blocked_latest_four_rows_below_30`.
- Smallest causal blocker: `blocked_missing_quote_surface_underlying_price`.

Interpretation:
- This branch is now parked. Current local OPRA/NBBO option quote rows do not provide the point-in-time `underlying_price` / opening-range snapshot surface required to generate the signal.
- Do not repeat opening-range reversal unless a trusted underlying/opening-bucket source or an explicitly approved research-only source surface changes that blocker.
- Do not repeat PMCC readiness, 13-symbol runner/source-surface/denominator-v2, flow, macro-event, VIX, momentum, VRP/term/skew readiness, dashboard-only branches, or this opening-range reversal branch unless a new source/artifact changes the blocker.

Safety still true:
- `accepted_profitability=false`.
- `historical_rows_are_forward_proof=false`.
- No quote import.
- No evidence DB mutation.
- No scanner/strategy/stops/sizing/proof-bar change.
- No live validation.
- No auto-track.
- No broker/order action.
- No protected holdout consumption.
- No promotion.

Verification passed:
- `uv run --locked python -m py_compile scripts/build_regular_options_quote_surface_opening_range_reversal_replay.py tests/test_regular_options_quote_surface_opening_range_reversal_replay.py`
- `uv run --locked python -m unittest tests.test_regular_options_quote_surface_opening_range_reversal_replay -v`
- `npm run options:research:quote-surface-opening-range-reversal-replay -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,DIA --no-write --json`
- `npm run verify:docs`
- `git diff --check`

User standing directive:
- Assume yes for read-only/research-only implementation, replay, validators, planners, and generated artifacts.
- Only ask for broker/live/order, quote import, evidence mutation, protected holdout consumption, promotion, or other trading-state-changing actions.

Goal remains:
- Find a path to at least `30` profitable strict completed forward-audit/latest-four-month rows.
- Return exactly one JSON-like next Codex task or an earned stop_exception.
- Include selected branch, why it is significant, exact files/artifacts, implementation steps, commands, acceptance criteria, failure criteria, forbidden actions, and stop condition.
- If a branch is blocked on missing data/source surface under current prohibitions, park it and pivot to the next materially different read-only option-structure, quote-surface, data-surface, or causal branch.
