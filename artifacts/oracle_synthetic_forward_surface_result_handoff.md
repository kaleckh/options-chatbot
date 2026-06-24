We are continuing the same regular-options profitability goal loop in the existing ChatGPT session. Do not stop casually. The operator has approved research-only implementation/replay/artifact slices when you would otherwise ask, but still forbids broker orders, live validation, auto-track, production scanner/strategy/stop/sizing/proof-bar changes, quote import, evidence-store mutation, protected-holdout consumption, and promotion unless separately explicit.

Goal / acceptance target:
- Reach at least 30 profitable strict completed rows in the latest approximately four-month / forward-style audit window, or earn a concrete stop_exception only after you have exhausted significant proof-safe upgrades.
- Current accepted profitability remains false. Forward/latest-four strict proof remains 0/30.

Codex completed your selected task:
- Implemented `quote_derived_synthetic_forward_opening_bucket_surface_v1`.
- Added `scripts/build_regular_options_quote_derived_synthetic_forward_surface.py`.
- Added `tests/test_regular_options_quote_derived_synthetic_forward_surface.py`.
- Added package script `options:research:quote-derived-synthetic-forward-surface`.
- Generated:
  - `docs/regular-options-quote-derived-synthetic-forward-surface.md`
  - `data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/latest.json`
  - `data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/latest.md`
  - `data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/daily_symbol_surface.jsonl`
- Updated memory docs: `docs/WORKLOG.md`, `docs/DECISIONS.md`, `docs/NEXT_STEPS.md`, `docs/index.md`, `docs/PROJECT_CONTEXT.md`.

Real result:
- `status`: `blocked_quote_derived_synthetic_forward_surface`
- `surface_id`: `quote_derived_synthetic_forward_opening_bucket_surface_v1`
- `read_only_db_open`: true
- window: `2024-06-01` through `2026-05-31`, as of `2026-06-04`
- universe: `SPY`, `QQQ`, `IWM`, `DIA`
- buckets: `09:35`, `10:35`, `10:40`, `15:50`
- `daily_symbol_surface_rows`: 1,976
- `requested_symbol_date_bucket_count`: 7,904
- `ready_symbol_date_bucket_count`: 0
- `requested_symbol_date_bucket_coverage_pct`: 0.0
- `train_months_covered`: 0
- `latest_four_months_covered`: 0
- `bucket_status_counts`: `blocked_missing_call_put_pairs=7904`
- `surface_status_counts`: `blocked_missing_call_put_pairs=1976`
- blockers:
  - `blocked_missing_call_put_pair_surface`
  - `blocked_insufficient_synthetic_forward_coverage`
- `smallest_next_blocker_clearing_slice`: `blocked_missing_call_put_pair_surface`
- `next_replay_command`: null
- `accepted_profitability`: false
- `historical_rows_are_forward_proof`: false
- `quotes_imported`: false
- `evidence_stores_mutated`: false
- `protected_holdout_consumed`: false
- `live_validation_enabled`: false
- `auto_track_enabled`: false
- `broker_order_allowed`: false
- `promotion_ready`: false

Verification run:
- `uv run --locked python -m py_compile scripts/build_regular_options_quote_derived_synthetic_forward_surface.py tests/test_regular_options_quote_derived_synthetic_forward_surface.py`: passed
- `uv run --locked python -m unittest tests.test_regular_options_quote_derived_synthetic_forward_surface -v`: passed, 6 tests
- `npm run options:research:quote-derived-synthetic-forward-surface -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,DIA --buckets 09:35,10:35,10:40,15:50 --no-write --json`: passed with blocked result above
- `npm run verify:docs`: passed
- `git diff --check`: passed with CRLF normalization warnings only

Important implementation note:
- The first real command timed out before optimization. Codex added a read-only bucket-availability precheck so absent requested bucket rows become explicit `blocked_missing_call_put_pairs` without thousands of unnecessary joins. This did not change proof bars or evidence; it only made the audit tractable.

Your task:
Return one JSON object only.

Required fields:
- `verdict`: `continue` or `stop_exception`
- `significant_upgrade_available`: boolean
- `selected_branch_id`: string or null
- `burden_of_proof_check`: object including current forward/latest-four strict row count and why stop is or is not earned
- `assumption_challenges`: array of concrete assumptions we may be getting wrong
- `branches_to_stop`: array of branch names to stop repeating
- `candidate_branches`: array with expected value, uncertainty, and why selected/not selected
- `next_codex_task`: object with objective, exact scope, implementation steps, allowed files/artifacts, expected artifacts, commands to run, acceptance criteria, failure criteria, forbidden actions, and stop condition after task
- `operator_questions`: array, but assume the operator says yes to research-only implementation/replay/artifact approvals and no to live/broker/mutation/import/holdout/promotion unless separately explicit

Do not recommend dashboard polish, generic advice, or repeating a blocked branch unless it directly clears the proof blocker. Prefer the highest-value proof-safe next slice that can move us toward at least 30 profitable strict latest-four/forward-style completed rows.
