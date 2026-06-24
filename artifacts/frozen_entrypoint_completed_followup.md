We already implemented the task GPT-5.5 Pro just selected:

`candidate_generation_repair:frozen_13_symbol_reusable_candidate_generation_entrypoint_v1`

Completed implementation:
- Added `scripts/regular_options_frozen_candidate_generation_entrypoint.py`.
- Added `tests/test_regular_options_13_symbol_frozen_candidate_generation_entrypoint.py`.
- Added package script `options:research:13-symbol-frozen-candidate-generation-entrypoint`.
- Wired `scripts/build_regular_options_13_symbol_frozen_candidate_generation_engine.py` to consume the entrypoint artifact.
- Wired `scripts/build_regular_options_13_symbol_frozen_candidate_generation_source_surface.py` to default to the entrypoint artifact.
- Wired `scripts/build_regular_options_historical_simulated_forward_audit.py` to default to the frozen source surface instead of the old broad selected-trade source.
- Wired `scripts/build_options_oracle_profit_loop_packet.py` to include the completed entrypoint state.

Verification passed:
- `uv run --locked python -m py_compile scripts/regular_options_frozen_candidate_generation_entrypoint.py scripts/build_regular_options_13_symbol_frozen_candidate_generation_engine.py scripts/build_regular_options_13_symbol_frozen_candidate_generation_source_surface.py scripts/build_regular_options_historical_simulated_forward_audit.py scripts/build_options_oracle_profit_loop_packet.py tests/test_regular_options_13_symbol_frozen_candidate_generation_entrypoint.py tests/test_regular_options_13_symbol_frozen_candidate_generation_engine.py tests/test_regular_options_13_symbol_frozen_candidate_generation_source_surface.py tests/test_regular_options_historical_simulated_forward_audit.py tests/test_options_oracle_profit_loop_packet.py`
- `uv run --locked python -m unittest tests.test_regular_options_13_symbol_frozen_candidate_generation_entrypoint tests.test_regular_options_13_symbol_frozen_candidate_generation_engine tests.test_regular_options_13_symbol_frozen_candidate_generation_source_surface tests.test_regular_options_historical_simulated_forward_audit tests.test_options_oracle_profit_loop_packet -v`
- `npm run options:research:13-symbol-frozen-candidate-generation-entrypoint -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json`
- `npm run options:research:13-symbol-frozen-candidate-generation-source-surface -- --no-write --json`
- `npm run options:research:13-symbol-frozen-candidate-generation-engine -- --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json`
- `npm run options:audit:historical-simulated-forward -- --json`
- `npm run options:oracle-loop:packet -- --json`
- `npm run verify:docs`
- `git diff --check` passed with CRLF warnings only.

Current completed-task result:
- Entrypoint status: `blocked_frozen_13_symbol_candidate_generation_entrypoint`.
- Entrypoint daily rows: `6,916`.
- Entrypoint selected candidates: `0`.
- Entrypoint covered months: `0/24`.
- Entrypoint blockers: `candidate_generation_months_0_below_requested_24`, `missing_daily_candidate_generation_diagnostics`, `source_artifact_universe_not_13_symbol`.
- Source-surface status: `blocked_13_symbol_frozen_candidate_generation_source_surface`.
- Engine status: `blocked_frozen_13_symbol_candidate_generation_engine`.
- Engine decision: `blocked_frozen_candidate_generation_entrypoint_incomplete`.
- Historical simulated-forward audit status: `blocked_historical_simulated_forward_audit`.
- Historical audit rows: `0` selected rows, `0` train months, `0` audit months, `0/30` exact audit trades.

Do not select the frozen 13-symbol entrypoint task again unless source state changes. It is implemented and verified. The branch is now parked on the result: no real daily candidate-generation diagnostics exist in the current source chain.

Return the next different Codex task toward the same target: at least 30 profitable strict completed forward-audit trades in the latest approximately 4-month/post-freeze audit window. Keep the profitability-first blocker-ranking prompt rules. Select exactly one next task, or return a fully earned stop_exception. Do not acknowledge only.
