# Active Options Operating Scorecard

- Status: `visible_product_profitability_progress_but_proof_still_blocked`
- Product profitability progress visible: `True`
- Proof-grade profitability progress visible: `False`

## Trading Desk Guardrails

- Baseline avg/median/negative-rate: `5.21%` / `-1.58%` / `50.4%`
- Promoted kept avg/median/negative-rate: `53.08%` / `46.4%` / `25.0%`
- Deltas: `{'avg_pnl_pct': 47.87, 'median_pnl_pct': 47.98, 'negative_rate_priced_pct': -25.4}`

## Frozen Proof Judge

- Best variant: `lane_a_goal_stop200_time75_symbol_health90_backfill`
- Score/status: `0.0` / `scout_or_blocked`
- Clean/scout count: `0.0` / `191.0`
- Lane A conservative PF / zero-bid rate: `0.92` / `43.24%`
- Blockers: `['clean_trade_count_below_200', 'effective_unresolved_candidates_remain', 'rolling_oos_not_passed:lane_a_chain_native_ret20_4_stop200_time75', 'zero_bid_exit_rate_above_2pct', 'lane_a_conservative_pf_below_1_30']`

## Live Scan Starvation

- Status: `upstream_zero_candidate_scan_pressure`
- Playbooks completed/requested: `13` / `13`
- Candidate/returned totals: `0` / `0`
- Guardrail starvation playbooks: `[]`
- Zero-candidate playbooks: `13`
- Leading drops: `[{'count': 115, 'value': 'direction_filter'}, {'count': 96, 'value': 'option_liquidity'}, {'count': 72, 'value': 'momentum'}, {'count': 60, 'value': 'history_or_liquidity'}, {'count': 33, 'value': 'tech_score'}, {'count': 2, 'value': 'direction_score'}, {'count': 0, 'value': 'min_history'}, {'count': 0, 'value': 'signal_index'}]`

## Open Position Risk

- Open regular rows: `48`
- Evidence counts: `{'fresh_executable_review': 47, 'fresh_unpriced_review': 1}`
- Action counts: `{'hold_or_positive': 32, 'negative_mark_hold_or_unknown': 15, 'stored_non_executable_sell': 1}`
- Actionable open IDs: `[104]`
- Executable close-ready rows: `0`
- Review-required non-executable rows: `1`

## Suggested Trade Close Risk

- Open suggested rows: `1`
- Evidence counts: `{'missing_review': 1}`
- Action counts: `{'no_stored_review': 1}`
- Close-risk suggested IDs: `[]`
- Stale/missing review IDs: `[138]`
- Executable close-ready suggested rows: `0`
- Review-required suggested rows: `1`

## Trading Desk API Performance

- Status: `ok`
- Endpoints ok/errors: `11` / `0`
- Frontend max elapsed / total payload bytes: `230.6 ms` / `321783`
- Backend max duration header: `49.1 ms`
- Slowest frontend route: `{'label': 'next_suggested_trades_open', 'target': 'next_route', 'path': '/api/suggested-trades?status=open&compact=1', 'status_code': 200, 'elapsed_ms': 230.6, 'backend_duration_ms': 2.0, 'payload_bytes': 1368, 'row_count': 1, 'page': None}`
- Largest payload route: `{'label': 'backend_tracked_positions_closed_page_100', 'target': 'python_backend', 'path': '/api/positions?status=closed&limit=100&offset=0&compact=1', 'status_code': 200, 'elapsed_ms': 57.9, 'backend_duration_ms': 34.6, 'payload_bytes': 171667, 'row_count': 100, 'page': {'limit': 100, 'offset': 0, 'returned': 100}}`
- Cache stats: `{'memory_cache_entries': 0, 'memory_cache_families': {}, 'request_scope_active': False, 'request_scope_entries': 0, 'schema_initialized': False, 'status': 'ok', 'totals': {}}`

## AI Commodity OPRA Proof Lane

- Status: `recording_progress_waiting_for_exact_history_depth`
- Provider/source: `alpaca:sip:opra` / `alpaca_opra_daily_snapshot`
- Exact shared quote dates: `3` / `100` (remaining `97`)
- Verification/replay: `not_verified` / trades `None` / PF `None`
- Live/proof candidates: `0` / `0`
- Capture status: `no_rows_captured` target `2026-05-26` complete `False` missing symbols `24`
- Guarded command: status `waiting_until_next_guarded_event` safe-now `False` next `python scripts/run_ai_commodity_opra_progress.py --skip-capture` not-before `2026-06-01T08:10:00-06:00`
- Safe to tune filters: `False`
- Top scan drops: `[{'drop_key': 'option_liquidity', 'count': 13, 'example_symbols': ['AA', 'BHP', 'COPX', 'FCX'], 'next_diagnostic_action': 'after_fresh_quotes_recheck_quote_age_then_structural_spread_distance'}, {'drop_key': 'momentum', 'count': 8, 'example_symbols': ['ALB', 'CARR', 'CCJ', 'CEG'], 'next_diagnostic_action': 'review_commodity_momentum_distance_after_exact_replay_unlock'}, {'drop_key': 'tech_score', 'count': 2, 'example_symbols': ['PWR', 'VRT'], 'next_diagnostic_action': 'review_commodity_tech_threshold_distance_after_exact_replay_unlock'}]`
- Blockers: `["capture_target_incomplete:['FCX', 'SLV', 'VRT', 'VST', 'ETN', 'GEV', 'PWR', 'CCJ', 'CEG', 'SCCO', 'COPX', 'URA', 'ALB', 'SQM', 'MP', 'RIO', 'BHP', 'TECK', 'AA', 'XME', 'NRG', 'NVT', 'CARR', 'TT']", 'shared_quote_dates:3/100', 'readiness:thin_required_history', 'replay_error:Imported historical validation has insufficient imported replay quote dates before replay under the requested trust scope. Selected dates: 3.', 'live_scan_candidates:0']`
- Failed goal requirements: `['full_scan_universe_is_exact_proof_scope', 'has_required_exact_alpaca_opra_history_depth', 'exact_replay_is_profitable', 'live_scan_has_verifiable_candidate']`

## Closed-Trade Follow-Up

- Negative trade rows audited: `213`
- Legacy missed-close targets: `3`
- Legacy missed-close recommendation: `no_broad_exit_policy_change; preserve as historical stale-policy diagnostic`
- Legacy current action required: `0`
- Broad exit promote candidates: `0`
- Legacy target positive replay rows: `27`

## Next Actions

- Do not close open rows from display-only marks; rerun explicit review during a fresh executable quote window for non-executable SELL or below-stop mark rows.
- Refresh stale or missing suggested-trade reviews before relying on suggested-trade P&L or close state.
- Treat legacy rows 26/39/44 as historical stale-policy diagnostics, not a broad current exit-policy change.
- Do not loosen promoted Trading Desk entry guardrails for the current no-pick state; investigate upstream scan/data/liquidity drops.
- Do not tune Lane A entry/memory again; test a non-overlapping sleeve or materially different exit/liquidity rule.
- Do not promote a broad exit-policy replay; current candidates improve some rows but fail broader negative-rate/winner-loss checks.
- Keep AI commodity production filters locked; wait for the guarded OPRA event before running `python scripts/run_ai_commodity_opra_progress.py --skip-capture`.
- Repair the AI commodity exact OPRA capture failure before strategy tuning; the latest target capture did not advance shared quote dates.
