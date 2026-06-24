🧿 oracle 0.15.0 — We QA the AI so you can ship the code.
[SYSTEM]
You are Oracle, a focused one-shot problem solver. Emphasize direct answers and cite referenced files as path:line or path:line-line when line numbers are available.

[USER]
Continue the same regular-options profitability loop in this existing session. User directive: assume yes for read-only/research-only implementation, replay, validators, planners, and generated artifacts; only ask for broker/live/import/mutation/holdout/promotion actions. Goal remains at least 30 profitable strict completed forward-audit/latest-four-month rows. Codex completed pmcc_diagonal_replay_readiness_audit_v1: blocked_pmcc_diagonal_replay_readiness with blockers missing_point_in_time_trend_or_regime_inputs, point_in_time_vix_bucket_blocked, missing_trusted_pmcc_diagonal_quote_surface; DB inventory found 1,992,676 trusted SPY/QQQ call quote rows but 0 long-DTE call rows. Do not repeat parked completed branches unless a new source/artifact changes their blocker. Return one JSON-like next Codex task or earned stop with files, commands, acceptance/failure criteria, forbidden actions, and stop condition.

### File: data/forward-tracking/options_oracle_profit_loop_packet_latest.json
Lines: 1-834
````json
  1 | {
  2 |   "artifacts": {
  3 |     "json": "data/forward-tracking/options_oracle_profit_loop_packet_latest.json",
  4 |     "markdown": "docs/research-decisions/options_oracle_profit_loop_packet_latest.md"
  5 |   },
  6 |   "auto_track_allowed": false,
  7 |   "broker_order_allowed": false,
  8 |   "continuation_branches": [
  9 |     {
 10 |       "branch_id": "fresh_forward_paper_shadow_collection",
 11 |       "requires_operator_approval": true,
 12 |       "why": "Only fresh post-freeze executable rows can become proof-qualified profitability."
 13 |     },
 14 |     {
 15 |       "branch_id": "scoped_source_repair_or_replay",
 16 |       "requires_operator_approval": true,
 17 |       "why": "May require quote import, evidence repair, or source-surface mutation; must be explicitly scoped."
 18 |     },
 19 |     {
 20 |       "branch_id": "new_causal_playbook_generation",
 21 |       "requires_operator_approval": false,
 22 |       "why": "Read-only preregistration/falsification can continue without live or evidence mutation."
 23 |     },
 24 |     {
 25 |       "branch_id": "new_historical_data_surface_or_longer_lookback",
 26 |       "requires_operator_approval": true,
 27 |       "why": "Changes the data surface and can invalidate prior branch-scoped stop verdicts."
 28 |     },
 29 |     {
 30 |       "branch_id": "dashboard_or_operator_visibility",
 31 |       "requires_operator_approval": false,
 32 |       "why": "Useful only if it changes execution decisions; not significant by itself unless tied to a proof blocker."
 33 |     }
 34 |   ],
 35 |   "current_evidence_summary": {
 36 |     "base_clean_stack_identity_ledger_blockers": [],
 37 |     "base_clean_stack_identity_ledger_duplicate_count": 0,
 38 |     "base_clean_stack_identity_ledger_expected_rows": 157,
 39 |     "base_clean_stack_identity_ledger_future_dependency_rows": 0,
 40 |     "base_clean_stack_identity_ledger_holdout_overlap_count": 0,
 41 |     "base_clean_stack_identity_ledger_missing_identity_rows": 0,
 42 |     "base_clean_stack_identity_ledger_row_count": 157,
 43 |     "base_clean_stack_identity_ledger_status": "base_clean_stack_identity_ledger_ready",
 44 |     "base_clean_stack_identity_ledger_unique_count": 157,
 45 |     "candidate_generation_13_symbol_candidate_months": 0,
 46 |     "candidate_generation_13_symbol_frozen_source_surface_blockers": [
 47 |       "candidate_generation_months_0_below_requested_24",
 48 |       "missing_daily_candidate_generation_diagnostics",
 49 |       "missing_frozen_13_symbol_candidate_generation_engine",
 50 |       "outside_universe_source_rows_present",
 51 |       "source_artifact_universe_not_13_symbol"
 52 |     ],
 53 |     "candidate_generation_13_symbol_frozen_source_surface_months_covered": 0,
 54 |     "candidate_generation_13_symbol_frozen_source_surface_selected_rows": 0,
 55 |     "candidate_generation_13_symbol_frozen_source_surface_status": "blocked_13_symbol_frozen_candidate_generation_source_surface",
 56 |     "candidate_generation_13_symbol_frozen_source_surface_zero_pick_months": 0,
 57 |     "candidate_generation_13_symbol_non_13_rows": 0,
 58 |     "candidate_generation_13_symbol_quote_months": 24,
 59 |     "candidate_generation_13_symbol_runner_status": "read_only_no_write_runner_available",
 60 |     "candidate_generation_13_symbol_surface_audit_blockers": [
 61 |       "candidate_generation_months_0_below_requested_24",
 62 |       "existing_candidate_generation_surface_not_frozen_13_symbol",
 63 |       "missing_candidate_generation_diagnostics",
 64 |       "not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof",
 65 |       "quote_depth_only_months_cannot_count",
 66 |       "source_artifact_universe_not_13_symbol"
 67 |     ],
 68 |     "candidate_generation_13_symbol_surface_audit_status": "blocked_13_symbol_candidate_generation_surface_audit",
 69 |     "causal_branches_to_stop": [
 70 |       "raw overlapping count aggregation",
 71 |       "tracked-winner count retuning without new causal evidence",
 72 |       "clean index/IWM refill as the primary gap closer",
 73 |       "existing current-regime momentum-compatible artifact aggregation"
 74 |     ],
 75 |     "causal_continue_loop": true,
 76 |     "causal_falsification_status": "existing_surface_falsified_new_causal_branch_still_possible",
 77 |     "causal_significant_upgrade_available": true,
 78 |     "denominator_mapping_status": "ready",
 79 |     "dispersion_proxy_hybrid_replay_readiness_blockers": [
 80 |       "missing_dispersion_or_concentration_proxy_inputs",
 81 |       "point_in_time_vix_bucket_blocked",
 82 |       "missing_pair_construction_engine",
 83 |       "missing_side_aware_all_leg_pair_pricing",
 84 |       "missing_pair_max_loss_or_collateral_convention",
 85 |       "missing_full_denominator_mapping",
 86 |       "missing_strict_new_dedupe"
 87 |     ],
 88 |     "dispersion_proxy_hybrid_replay_readiness_smallest_next_blocker": "missing_dispersion_or_concentration_proxy_inputs",
 89 |     "dispersion_proxy_hybrid_replay_readiness_status": "blocked_dispersion_proxy_hybrid_replay_readiness",
 90 |     "flow_extreme_denominator_dedupe_bridge_blockers": [],
 91 |     "flow_extreme_denominator_dedupe_bridge_status": "flow_extreme_denominator_dedupe_bridge_ready",
 92 |     "flow_extreme_full_denominator_mapping_status": "ready",
 93 |     "flow_extreme_ratio_backspread_replay_readiness_blockers": [
 94 |       "missing_point_in_time_flow_extreme_input",
 95 |       "missing_point_in_time_vix_bucket"
 96 |     ],
 97 |     "flow_extreme_ratio_backspread_replay_readiness_generated_at_utc": "2026-06-23T21:28:47Z",
 98 |     "flow_extreme_ratio_backspread_replay_readiness_raw_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
 99 |     "flow_extreme_ratio_backspread_replay_readiness_reason_codes": [],
100 |     "flow_extreme_ratio_backspread_replay_readiness_smallest_next_blocker": "missing_point_in_time_flow_extreme_input",
101 |     "flow_extreme_ratio_backspread_replay_readiness_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
102 |     "flow_extreme_strict_new_dedupe_status": "ready",
103 |     "flow_extreme_volume_oi_blockers": [
104 |       "missing_trusted_volume_open_interest_source_rows",
105 |       "trusted_rows_have_null_volume_open_interest",
106 |       "insufficient_month_coverage",
107 |       "insufficient_date_coverage"
108 |     ],
109 |     "flow_extreme_volume_oi_coverage": {
110 |       "covered_date_count": 0,
111 |       "covered_month_count": 0,
112 |       "covered_months": [],
113 |       "date_coverage_pct": 0.0,
114 |       "minimum_covered_months": 20,
115 |       "minimum_date_coverage_pct": 90.0,
116 |       "missing_months": [
117 |         "2024-06",
118 |         "2024-07",
119 |         "2024-08",
120 |         "2024-09",
121 |         "2024-10",
122 |         "2024-11",
123 |         "2024-12",
124 |         "2025-01",
125 |         "2025-02",
126 |         "2025-03",
127 |         "2025-04",
128 |         "2025-05",
129 |         "2025-06",
130 |         "2025-07",
131 |         "2025-08",
132 |         "2025-09",
133 |         "2025-10",
134 |         "2025-11",
135 |         "2025-12",
136 |         "2026-01",
137 |         "2026-02",
138 |         "2026-03",
139 |         "2026-04",
140 |         "2026-05"
141 |       ],
142 |       "requested_date_count": 494,
143 |       "requested_month_count": 24,
144 |       "requested_months": [
145 |         "2024-06",
146 |         "2024-07",
147 |         "2024-08",
148 |         "2024-09",
149 |         "2024-10",
150 |         "2024-11",
151 |         "2024-12",
152 |         "2025-01",
153 |         "2025-02",
154 |         "2025-03",
155 |         "2025-04",
156 |         "2025-05",
157 |         "2025-06",
158 |         "2025-07",
159 |         "2025-08",
160 |         "2025-09",
161 |         "2025-10",
162 |         "2025-11",
163 |         "2025-12",
164 |         "2026-01",
165 |         "2026-02",
166 |         "2026-03",
167 |         "2026-04",
168 |         "2026-05"
169 |       ]
170 |     },
171 |     "flow_extreme_volume_oi_source_row_count": 0,
172 |     "flow_extreme_volume_oi_source_rows_status": "blocked_flow_extreme_volume_oi_source_rows",
173 |     "flow_extreme_volume_oi_usable_aggregate_row_count": 0,
174 |     "flow_readiness_full_denominator_blocker_cleared": true,
175 |     "flow_readiness_pricing_blocker_cleared": true,
176 |     "flow_readiness_strict_new_dedupe_blocker_cleared": true,
177 |     "frontier": {
178 |       "base_clean_stack_exact_rows": 157,
179 |       "candidate_count": 44,
180 |       "countable_throughput_candidate_found": false,
181 |       "current_historical_surface_exhausted_under_current_prohibitions": true,
182 |       "decision_counts": {
183 |         "blocked_below_strict_new_count": 33,
184 |         "blocked_execution_quality": 2,
185 |         "rejected_negative_or_flat_edge": 9
186 |       },
187 |       "raw_count_candidate_count": 11,
188 |       "status": "current_historical_surface_exhausted_under_current_prohibitions",
189 |       "strict_new_gap_required": 43,
190 |       "target_exact_rows": 200
191 |     },
192 |     "goal_loop_forward_accounting": {
193 |       "auto_track_allowed": false,
194 |       "broker_order_allowed": false,
195 |       "cohort_append_performed": false,
196 |       "cohort_log_exists": false,
197 |       "cohort_log_malformed_row_count": 0,
198 |       "cohort_log_path": "data/forward-tracking/phase2_regular_options_forward_paper_shadow_cohort.jsonl",
199 |       "cohort_log_row_count": 0,
200 |       "cohort_log_status": "missing",
201 |       "excluded_or_rejected_row_flags": 0,
202 |       "live_entry_allowed": false,
203 |       "minimum_required": 30,
204 |       "post_freeze_strict_exact_completed_rows": 0,
205 |       "promotion_ready": false,
206 |       "state": "log_missing_blocker",
207 |       "strict_reject_counts": {
208 |         "blocked_by_required_contracts": 0,
209 |         "duplicate_completed_selection_id": 0,
210 |         "duplicate_row_id": 0,
211 |         "exact_completed_missing_entry_quote_provenance": 0,
212 |         "exact_completed_missing_exit_quote_provenance": 0,
213 |         "exact_completed_missing_policy_exit_condition": 0,
214 |         "fixture_source_not_proof_eligible": 0,
215 |         "lookahead_claimed_as_exact": 0,
216 |         "market_window_not_open": 0,
217 |         "missing_net_pnl_usd": 0,
218 |         "missing_real_source_provenance": 0,
219 |         "missing_required_schema_fields": 0,
220 |         "missing_source_provenance_fields": 0,
221 |         "non_executable_mark_claimed_as_exact": 0,
222 |         "non_frozen_lane": 0,
223 |         "non_preregistered_symbol": 0,
224 |         "pre_freeze_not_acceptance_eligible": 0,
225 |         "scanner_hash_drift": 0,
226 |         "unknown_denominator_status": 0
227 |       },
228 |       "strict_rows_remaining_to_minimum": 30,
229 |       "strict_usd_pf_lower_bound_5pct": null,
230 |       "total_natural_selections": 0
231 |     },
232 |     "goal_loop_next_safe_action": "continue_paper_shadow_only",
233 |     "goal_loop_state": "underpowered_forward_evidence",
234 |     "macro_event_calendar_blockers": [
235 |       "macro_event_calendar_source_missing",
236 |       "missing_required_macro_event_categories"
237 |     ],
238 |     "macro_event_calendar_event_count": 0,
239 |     "macro_event_calendar_status": "blocked_macro_event_calendar_source_missing",
240 |     "macro_event_long_strangle_replay_readiness_blockers": [
241 |       "macro_event_calendar_source_missing",
242 |       "point_in_time_vix_source_missing",
243 |       "missing_vix_bucket_threshold_policy",
244 |       "vix_bucket_date_coverage_incomplete"
245 |     ],
246 |     "macro_event_long_strangle_replay_readiness_status": "blocked_macro_event_long_strangle_replay_readiness",
247 |     "momentum_continuation_bounded_replay_blockers": [
248 |       "bootstrap_pf_lower_bound_not_above_1_after_resolution",
249 |       "duplicate_within_research_harness",
250 |       "entry_missing_leg_quote",
251 |       "exit_missing_leg_quote",
252 |       "exit_value_negative",
253 |       "exit_zero_or_nonpositive_bid_ask",
254 |       "missing_net_usd_pnl",
255 |       "missing_point_in_time_breadth_confirmation",
256 |       "missing_point_in_time_qqq_momentum_confirmation",
257 |       "missing_point_in_time_spy_momentum_confirmation",
258 |       "missing_point_in_time_vix_bucket",
259 |       "net_usd_not_positive_after_resolution",
260 |       "rejected_not_call_debit_spread",
261 |       "rejected_outside_preregistered_universe",
262 |       "strict_rows_below_30_after_resolution"
263 |     ],
264 |     "momentum_continuation_bounded_replay_exact_rows": 0,
265 |     "momentum_continuation_bounded_replay_side_aware_rows": 783,
266 |     "momentum_continuation_bounded_replay_status": "blocked_momentum_continuation_bounded_replay",
267 |     "momentum_continuation_proof_resolution_after_rows": 0,
268 |     "momentum_continuation_proof_resolution_blockers": [
269 |       "bootstrap_pf_lower_bound_not_above_1_after_resolution",
270 |       "duplicate_within_research_harness",
271 |       "entry_missing_leg_quote",
272 |       "exit_missing_leg_quote",
273 |       "exit_value_negative",
274 |       "exit_zero_or_nonpositive_bid_ask",
275 |       "missing_net_usd_pnl",
276 |       "missing_point_in_time_breadth_confirmation",
277 |       "missing_point_in_time_qqq_momentum_confirmation",
278 |       "missing_point_in_time_spy_momentum_confirmation",
279 |       "missing_point_in_time_vix_bucket",
280 |       "net_usd_not_positive_after_resolution",
281 |       "rejected_not_call_debit_spread",
282 |       "rejected_outside_preregistered_universe",
283 |       "strict_rows_below_30_after_resolution"
284 |     ],
285 |     "momentum_continuation_proof_resolution_side_aware_rows": 783,
286 |     "momentum_continuation_proof_resolution_status": "momentum_continuation_blocked_missing_local_proof_inputs",
287 |     "momentum_continuation_replay_concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
288 |     "momentum_continuation_replay_denominator_rows": 1291,
289 |     "momentum_continuation_replay_diagnostic_metrics": {
290 |       "avg_pnl_usd": -65.68,
291 |       "gross_loss_usd": 239470.75,
292 |       "gross_win_usd": 180623.09,
293 |       "loss_count": 427,
294 |       "net_pnl_usd": -58847.66,
295 |       "priced_row_count": 896,
296 |       "profit_factor": 0.7543,
297 |       "row_count": 896,
298 |       "win_count": 469,
299 |       "win_rate_pct": 52.34
300 |     },
301 |     "momentum_continuation_replay_proof_rows": 0,
302 |     "momentum_continuation_replay_status": "implemented_research_replay_no_proof_qualified_rows",
303 |     "momentum_edge_status": "raw_count_available_but_not_countable_profitable_edge",
304 |     "multi_leg_side_aware_pricing_capability_status": "multi_leg_side_aware_pricing_capability_available",
305 |     "pmcc_diagonal_replay_readiness_blockers": [
306 |       "missing_point_in_time_trend_or_regime_inputs",
307 |       "point_in_time_vix_bucket_blocked",
308 |       "missing_trusted_pmcc_diagonal_quote_surface"
309 |     ],
310 |     "pmcc_diagonal_replay_readiness_generated_at_utc": "2026-06-23T21:50:44Z",
311 |     "pmcc_diagonal_replay_readiness_raw_status": "blocked_pmcc_diagonal_replay_readiness",
312 |     "pmcc_diagonal_replay_readiness_reason_codes": [],
313 |     "pmcc_diagonal_replay_readiness_smallest_next_blocker": "missing_point_in_time_trend_or_regime_inputs",
314 |     "pmcc_diagonal_replay_readiness_status": "blocked_pmcc_diagonal_replay_readiness",
315 |     "point_in_time_dispersion_concentration_proxy_blockers": [
316 |       "missing_point_in_time_dispersion_proxy_source",
317 |       "missing_required_return_fields",
318 |       "insufficient_month_coverage",
319 |       "insufficient_date_coverage"
320 |     ],
321 |     "point_in_time_dispersion_concentration_proxy_covered_months": 0,
322 |     "point_in_time_dispersion_concentration_proxy_date_coverage_pct": 0.0,
323 |     "point_in_time_dispersion_concentration_proxy_source_inventory_status": "missing_proxy_source_rows",
324 |     "point_in_time_dispersion_concentration_proxy_status": "blocked_point_in_time_dispersion_concentration_proxy",
325 |     "point_in_time_flow_extreme_input_blockers": [
326 |       "missing_point_in_time_flow_extreme_source",
327 |       "missing_required_flow_fields",
328 |       "insufficient_month_coverage",
329 |       "insufficient_date_coverage"
330 |     ],
331 |     "point_in_time_flow_extreme_input_covered_months": 0,
332 |     "point_in_time_flow_extreme_input_date_coverage_pct": 0.0,
333 |     "point_in_time_flow_extreme_input_proxy_basis": [],
334 |     "point_in_time_flow_extreme_input_source_inventory_status": "missing_flow_source_rows",
335 |     "point_in_time_flow_extreme_input_status": "blocked_point_in_time_flow_extreme_input",
336 |     "point_in_time_vix_bucket_available": false,
337 |     "point_in_time_vix_bucket_blockers": [
338 |       "point_in_time_vix_source_missing",
339 |       "missing_vix_bucket_threshold_policy",
340 |       "vix_bucket_date_coverage_incomplete"
341 |     ],
342 |     "point_in_time_vix_bucket_coverage_pct": 0.0,
343 |     "point_in_time_vix_bucket_source_rows_count": 0,
344 |     "point_in_time_vix_bucket_status": "blocked_point_in_time_vix_source_missing",
345 |     "preregistered_dispersion_proxy_hybrid_concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
346 |     "preregistered_dispersion_proxy_hybrid_status": "preregistered_design_only",
347 |     "preregistered_flow_extreme_ratio_backspread_concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
348 |     "preregistered_flow_extreme_ratio_backspread_status": "preregistered_design_only",
349 |     "preregistered_macro_event_long_strangle_concept_id": "low_mid_vix_macro_event_long_strangle_v1",
350 |     "preregistered_macro_event_long_strangle_status": "preregistered_design_only",
351 |     "preregistered_playbook_concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
352 |     "preregistered_playbook_status": "preregistered_design_only",
353 |     "preregistered_pmcc_diagonal_concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
354 |     "preregistered_pmcc_diagonal_status": "preregistered_design_only",
355 |     "preregistered_post_event_iv_crush_iron_condor_concept_id": "post_event_iv_crush_index_iron_condor_v1",
356 |     "preregistered_post_event_iv_crush_iron_condor_status": "preregistered_design_only",
357 |     "preregistered_skew_broken_wing_concept_id": "low_mid_vix_index_skew_broken_wing_put_fly_v1",
358 |     "preregistered_skew_broken_wing_status": "preregistered_design_only",
359 |     "preregistered_term_structure_calendar_concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
360 |     "preregistered_term_structure_calendar_status": "preregistered_design_only",
361 |     "preregistered_vrp_credit_spread_concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
362 |     "preregistered_vrp_credit_spread_status": "preregistered_design_only",
363 |     "pricing_capability_blockers": [],
364 |     "ratio_backspread_bounded_pricing_status": "available",
365 |     "term_structure_calendar_replay_readiness_blockers": [
366 |       "missing_calendar_diagonal_side_aware_pricing_engine",
367 |       "missing_calendar_diagonal_exit_or_expiry_engine",
368 |       "missing_full_denominator_status_mapping",
369 |       "missing_front_leg_assignment_expiration_classifier",
370 |       "missing_roll_or_expiry_policy",
371 |       "missing_point_in_time_term_structure_inputs",
372 |       "missing_index_calendar_quote_surface",
373 |       "missing_strict_new_dedupe"
374 |     ],
375 |     "term_structure_calendar_replay_readiness_status": "blocked_term_structure_calendar_replay_readiness",
376 |     "vrp_credit_spread_replay_readiness_blockers": [
377 |       "missing_credit_spread_side_aware_pricing_engine",
378 |       "missing_credit_spread_side_aware_exit_pricing_engine",
379 |       "missing_full_denominator_status_mapping",
380 |       "missing_assignment_expiration_classifier",
381 |       "missing_margin_max_loss_convention",
382 |       "missing_point_in_time_vix_bucket",
383 |       "missing_index_credit_spread_quote_surface",
384 |       "missing_protected_holdout_guard"
385 |     ],
386 |     "vrp_credit_spread_replay_readiness_status": "blocked_vrp_credit_spread_replay_readiness"
387 |   },
388 |   "edge_discovery_requirements": {
389 |     "anti_handwave_rules": [
390 |       "Do not say collect more data without naming the exact data, lane, date window, command, and pass/fail threshold.",
391 |       "Do not say try more strategies without naming the exact market hypothesis, structure, universe, and falsification test.",
392 |       "Do not say optimize parameters unless the search budget, frozen validation split, leakage controls, and multiple-hypothesis penalty are explicit.",
393 |       "Do not treat historical dashboard artifacts, repaired historical rows, or point PF alone as proof-qualified profitability."
394 |     ],
395 |     "edge_families_to_evaluate": [
396 |       "volatility risk premium",
397 |       "skew mispricing",
398 |       "term-structure dislocation",
399 |       "earnings or macro event volatility",
400 |       "post-event IV crush",
401 |       "post-event drift",
402 |       "trend or momentum continuation",
403 |       "mean reversion",
404 |       "dispersion-like proxy behavior",
405 |       "liquidity or flow effects"
406 |     ],
407 |     "must_consider_before_stop": [
408 |       "fresh_forward_paper_shadow_collection",
409 |       "scoped_source_repair_or_replay",
410 |       "new_historical_data_surface_or_longer_lookback",
411 |       "new_causal_playbook_generation",
412 |       "new option structures beyond current directional spreads",
413 |       "index/ETF lanes separately from single-name lanes",
414 |       "data requirements that would make the latest-four-month audit proof-valid"
415 |     ],
416 |     "option_structures_to_consider": [
417 |       "vertical spreads",
418 |       "calendars",
419 |       "diagonals",
420 |       "broken-wing butterflies",
421 |       "ratio spreads",
422 |       "backspreads",
423 |       "straddles",
424 |       "strangles",
425 |       "iron condors",
426 |       "iron butterflies",
427 |       "synthetic covered calls or PMCC-style diagonals",
428 |       "debit/credit hybrids"
429 |     ],
430 |     "stop_is_exceptional": true
431 |   },
432 |   "evidence_stores_mutated": false,
433 |   "generated_at_utc": "2026-06-23T21:50:56Z",
434 |   "gpt55_required_output_schema": {
435 |     "anti_handwave_audit": {
436 |       "exact_next_action_present": "boolean",
437 |       "generic_advice_removed": "boolean",
438 |       "measurable_threshold_present": "boolean"
439 |     },
440 |     "assumption_challenges": [
441 |       {
442 |         "assumption": "string",
443 |         "risk": "string",
444 |         "verification": "string"
445 |       }
446 |     ],
447 |     "branches_to_stop": [
448 |       "branch ids or candidate ids to avoid repeating"
449 |     ],
450 |     "burden_of_proof_check": {
451 |       "current_forward_rows": "number",
452 |       "reason": "string",
453 |       "stop_allowed": "boolean",
454 |       "target_profitable_strict_completed_rows": "number"
455 |     },
456 |     "candidate_branches": [
457 |       {
458 |         "branch": "string",
459 |         "expected_value": "string",
460 |         "main_uncertainty": "string",
461 |         "why_not_selected": "string|null"
462 |       }
463 |     ],
464 |     "continue_loop": "boolean",
465 |     "next_codex_task": {
466 |       "acceptance_criteria": [
467 |         "measurable pass/fail criteria"
468 |       ],
469 |       "allowed_files_or_artifacts": [
470 |         "paths or artifact families"
471 |       ],
472 |       "commands_to_run": [
473 |         "exact commands"
474 |       ],
475 |       "exact_scope": "files/modules/artifacts included and excluded",
476 |       "expected_artifacts": [
477 |         "files or readbacks expected after Codex runs"
478 |       ],
479 |       "failure_criteria": [
480 |         "what result rejects or parks this branch"
481 |       ],
482 |       "forbidden_actions": [
483 |         "actions that remain forbidden"
484 |       ],
485 |       "implementation_steps": [
486 |         "ordered steps"
487 |       ],
488 |       "objective": "one concrete implementation or verification task",
489 |       "stop_condition_after_task": "what would make this branch exhausted"
490 |     },
491 |     "operator_questions": [
492 |       {
493 |         "default_if_unanswered": "string",
494 |         "question": "string",
495 |         "why_it_matters": "string"
496 |       }
497 |     ],
498 |     "selected_branch_id": "string|null",
499 |     "significant_upgrade_available": "boolean",
500 |     "verdict": "continue|stop_exception",
501 |     "why_this_is_significant": "short explanation tied to profitability proof"
502 |   },
503 |   "live_entry_allowed": false,
504 |   "loop_goal": {
505 |     "codex_role": "repo implementation, verification, and evidence refresh",
506 |     "gpt55_role": "strategic reviewer and next-slice selector",
507 |     "loop_stop_rule": "Stop only when GPT-5.5 Pro returns verdict=stop_exception after proving no significant upgrade remains across new lanes, new option structures, historical data-depth repair, and forward collection, or when a safety/proof violation is detected.",
508 |     "plain_english": "Make the regular-options work profitable under proof-qualified criteria, targeting at least 30 profitable strict completed rows in the latest approximately four months, or prove there are no significant upgrades left under the current allowed branches.",
509 |     "profit_target": "profitability with executable exact evidence, not raw historical row count or non-executable marks"
510 |   },
511 |   "missing_required_artifacts": [],
512 |   "operator_approval_posture": {
513 |     "fixture_temp_verification_generated_artifacts": "pre_approved_by_user_for_loop_continuation",
514 |     "questions_to_gpt55": "Do not block on read-only/research-only operator questions; state the assumption as approved and choose the next task.",
515 |     "read_only_research_only_work": "pre_approved_by_user_for_loop_continuation",
516 |     "still_requires_separate_explicit_approval": [
517 |       "broker orders or order preparation",
518 |       "live validation",
519 |       "auto-track enablement",
520 |       "production scanner, strategy, stop, sizing, or proof-bar changes",
521 |       "quote import",
522 |       "protected-holdout consumption",
523 |       "promotion",
524 |       "unsafe evidence-store mutation"
525 |     ]
526 |   },
527 |   "profitability_target": {
528 |     "current_forward_rows": 0,
529 |     "current_status": "not forward-audit profitable",
530 |     "minimum_profitable_strict_completed_rows": 30,
531 |     "profitability_metric": "canonical executable exact net P&L after fees/slippage with PF lower-bound discipline",
532 |     "target_window": "latest approximately four months / post-freeze forward-style audit window"
533 |   },
534 |   "promotion_ready": false,
535 |   "prompt": "We are continuing the same regular-options profitability loop in the existing GPT-5.5 Pro ChatGPT session.\n\nYou are GPT-5.5 Pro acting as strategic reviewer and next-slice selector. Codex will implement and verify. The user wants this loop to continue until GPT-5.5 Pro says there are no significant upgrades left.\n\nOperator approval posture:\n{\n  \"fixture_temp_verification_generated_artifacts\": \"pre_approved_by_user_for_loop_continuation\",\n  \"questions_to_gpt55\": \"Do not block on read-only/research-only operator questions; state the assumption as approved and choose the next task.\",\n  \"read_only_research_only_work\": \"pre_approved_by_user_for_loop_continuation\",\n  \"still_requires_separate_explicit_approval\": [\n    \"broker orders or order preparation\",\n    \"live validation\",\n    \"auto-track enablement\",\n    \"production scanner, strategy, stop, sizing, or proof-bar changes\",\n    \"quote import\",\n    \"protected-holdout consumption\",\n    \"promotion\",\n    \"unsafe evidence-store mutation\"\n  ]\n}\n\nPrimary goal:\nMake the regular-options workflow profitable under proof-qualified criteria. The practical target is at least 30 profitable strict completed rows in the latest approximately four months / post-freeze forward-style audit window. Profit means executable exact net P&L after fees/slippage, defensible PF/lower-bound/holdout/forward proof, and no unresolved data-quality defects that could flip the result. Do not accept raw overlapping historical count, midpoint/stale/display/EOD/last/model/manual marks, lookahead-only rows, zero-bid/untradable rows, or historical dashboard/replay rows as live proof.\n\nCurrent proof posture:\n- The system is not forward-audit profitable.\n- Strict post-freeze forward proof is currently 0/30 completed exact rows.\n- The historical current-policy replay panel was removed from the operator dashboard because it could be mistaken for current recommendations or forward-audit performance.\n- The latest-four-month simulated audit is hypothesis-generating only unless its row set, data depth, leakage controls, and PF lower-bound satisfy the strict proof contract.\n\nCurrent frontier result:\n{\n  \"base_clean_stack_exact_rows\": 157,\n  \"candidate_count\": 44,\n  \"countable_throughput_candidate_found\": false,\n  \"current_historical_surface_exhausted_under_current_prohibitions\": true,\n  \"decision_counts\": {\n    \"blocked_below_strict_new_count\": 33,\n    \"blocked_execution_quality\": 2,\n    \"rejected_negative_or_flat_edge\": 9\n  },\n  \"raw_count_candidate_count\": 11,\n  \"status\": \"current_historical_surface_exhausted_under_current_prohibitions\",\n  \"strict_new_gap_required\": 43,\n  \"target_exact_rows\": 200\n}\n\nCurrent momentum-edge result:\n{\n  \"countable_momentum_edge_candidate_count\": 0,\n  \"decision_counts\": {\n    \"blocked_below_trade_count_target\": 5,\n    \"raw_count_target_met_but_not_countable_edge\": 2,\n    \"rejected_negative_or_flat_edge\": 10\n  },\n  \"status\": \"raw_count_available_but_not_countable_profitable_edge\"\n}\n\nCurrent causal-falsification result, if available:\n{\n  \"branches_to_stop\": [\n    \"raw overlapping count aggregation\",\n    \"tracked-winner count retuning without new causal evidence\",\n    \"clean index/IWM refill as the primary gap closer\",\n    \"existing current-regime momentum-compatible artifact aggregation\"\n  ],\n  \"continue_loop\": true,\n  \"hypothesis_status_counts\": {\n    \"falsified_existing_surface\": 4,\n    \"not_falsified_requires_next_oracle_or_operator_selection\": 1\n  },\n  \"significant_upgrade_available\": true,\n  \"status\": \"existing_surface_falsified_new_causal_branch_still_possible\"\n}\n\nCurrent preregistered playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation, replay, quote import, evidence mutation, or forward collection requires a separate explicit decision.\",\n  \"concept_id\": \"breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1\",\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\"\n}\n\nCurrent approved momentum-continuation research replay result, if available:\n{\n  \"accepted_profitability\": false,\n  \"concept_id\": \"breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1\",\n  \"denominator_rows\": 1291,\n  \"denominator_status_counts\": {\n    \"duplicate_within_research_harness\": 461,\n    \"missing_point_in_time_vix_bucket\": 415,\n    \"rejected_not_call_debit_spread\": 237,\n    \"rejected_outside_preregistered_universe\": 178\n  },\n  \"diagnostic_only_metrics\": {\n    \"avg_pnl_usd\": -65.68,\n    \"gross_loss_usd\": 239470.75,\n    \"gross_win_usd\": 180623.09,\n    \"loss_count\": 427,\n    \"net_pnl_usd\": -58847.66,\n    \"priced_row_count\": 896,\n    \"profit_factor\": 0.7543,\n    \"row_count\": 896,\n    \"win_count\": 469,\n    \"win_rate_pct\": 52.34\n  },\n  \"historical_replay_performed\": true,\n  \"lane_implementation_performed\": false,\n  \"proof_metrics\": {\n    \"avg_pnl_usd\": null,\n    \"gross_loss_usd\": 0,\n    \"gross_win_usd\": 0,\n    \"loss_count\": 0,\n    \"net_pnl_usd\": null,\n    \"priced_row_count\": 0,\n    \"profit_factor\": null,\n    \"row_count\": 0,\n    \"win_count\": 0,\n    \"win_rate_pct\": null\n  },\n  \"proof_qualified_rows\": 0,\n  \"research_only_replay_harness_implemented\": true,\n  \"status\": \"implemented_research_replay_no_proof_qualified_rows\",\n  \"top_blockers\": [\n    {\n      \"reason\": \"missing_point_in_time_breadth_confirmation\",\n      \"row_count\": 1291\n    },\n    {\n      \"reason\": \"missing_point_in_time_vix_bucket\",\n      \"row_count\": 1291\n    },\n    {\n      \"reason\": \"missing_side_aware_exit_bid_ask\",\n      \"row_count\": 1291\n    },\n    {\n      \"reason\": \"missing_point_in_time_qqq_momentum_confirmation\",\n      \"row_count\": 1080\n    },\n    {\n      \"reason\": \"spread_diagnostics_marked_diagnostic_only\",\n      \"row_count\": 1064\n    },\n    {\n      \"reason\": \"entry_contains_mid_quote_basis\",\n      \"row_count\": 896\n    },\n    {\n      \"reason\": \"duplicate_within_research_harness\",\n      \"row_count\": 461\n    },\n    {\n      \"reason\": \"missing_net_usd_pnl\",\n      \"row_count\": 395\n    },\n    {\n      \"reason\": \"missing_point_in_time_spy_momentum_confirmation\",\n      \"row_count\": 395\n    },\n    {\n      \"reason\": \"rejected_not_call_debit_spread\",\n      \"row_count\": 290\n    },\n    {\n      \"reason\": \"rejected_outside_preregistered_universe\",\n      \"row_count\": 277\n    },\n    {\n      \"reason\": \"missing_side_aware_entry_bid_ask\",\n      \"row_count\": 227\n    }\n  ]\n}\n\nCurrent momentum-continuation proof-blocker resolution result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"bootstrap_pf_lower_bound_not_above_1_after_resolution\",\n    \"duplicate_within_research_harness\",\n    \"entry_missing_leg_quote\",\n    \"exit_missing_leg_quote\",\n    \"exit_value_negative\",\n    \"exit_zero_or_nonpositive_bid_ask\",\n    \"missing_net_usd_pnl\",\n    \"missing_point_in_time_breadth_confirmation\",\n    \"missing_point_in_time_qqq_momentum_confirmation\",\n    \"missing_point_in_time_spy_momentum_confirmation\",\n    \"missing_point_in_time_vix_bucket\",\n    \"net_usd_not_positive_after_resolution\",\n    \"rejected_not_call_debit_spread\",\n    \"rejected_outside_preregistered_universe\",\n    \"strict_rows_below_30_after_resolution\"\n  ],\n  \"concept_id\": \"breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1\",\n  \"historical_rows_are_forward_proof\": false,\n  \"proof_qualified_rows_after_resolution\": 0,\n  \"proof_qualified_rows_before_resolution\": 0,\n  \"reconstructed_denominator_rows\": 1291,\n  \"resolution_counts\": {\n    \"blocker_counts\": {\n      \"duplicate_within_research_harness\": 461,\n      \"entry_missing_leg_quote\": 227,\n      \"exit_missing_leg_quote\": 413,\n      \"exit_value_negative\": 6,\n      \"exit_zero_or_nonpositive_bid_ask\": 95,\n      \"missing_net_usd_pnl\": 395,\n      \"missing_point_in_time_breadth_confirmation\": 1291,\n      \"missing_point_in_time_qqq_momentum_confirmation\": 1080,\n      \"missing_point_in_time_spy_momentum_confirmation\": 395,\n      \"missing_point_in_time_vix_bucket\": 1291,\n      \"rejected_not_call_debit_spread\": 290,\n      \"rejected_outside_preregistered_universe\": 277\n    },\n    \"full_denominator_fail_closed\": 1291,\n    \"point_in_time_inputs_resolved\": 0,\n    \"proof_qualified_candidate_rows\": 0,\n    \"side_aware_quotes_resolved\": 783\n  },\n  \"side_aware_diagnostic_metrics\": {\n    \"avg_pnl_usd\": 201.07,\n    \"bootstrap_pf_lower_bound_5pct\": null,\n    \"gross_loss_usd\": 121252.6,\n    \"gross_win_usd\": 278693.8,\n    \"loss_count\": 281,\n    \"net_pnl_usd\": 157441.2,\n    \"priced_row_count\": 783,\n    \"profit_factor\": 2.2985,\n    \"row_count\": 783,\n    \"stress_pf\": 2.2985,\n    \"win_count\": 502,\n    \"win_rate_pct\": 64.11\n  },\n  \"source_denominator_rows\": 1291,\n  \"status\": \"momentum_continuation_blocked_missing_local_proof_inputs\",\n  \"strict_research_metrics\": {\n    \"avg_pnl_usd\": null,\n    \"bootstrap_pf_lower_bound_5pct\": null,\n    \"gross_loss_usd\": 0,\n    \"gross_win_usd\": 0,\n    \"loss_count\": 0,\n    \"net_pnl_usd\": null,\n    \"priced_row_count\": 0,\n    \"profit_factor\": null,\n    \"row_count\": 0,\n    \"stress_pf\": null,\n    \"win_count\": 0,\n    \"win_rate_pct\": null\n  }\n}\n\nCurrent momentum-continuation bounded replay gate result, if available:\n{\n  \"accepted_profitability\": false,\n  \"concept_id\": \"breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1\",\n  \"existing_resolution_consumed\": true,\n  \"historical_replay_performed\": false,\n  \"historical_rows_are_forward_proof\": false,\n  \"metrics\": {\n    \"blocker_counts\": {\n      \"duplicate_within_research_harness\": 461,\n      \"entry_missing_leg_quote\": 227,\n      \"exit_missing_leg_quote\": 413,\n      \"exit_value_negative\": 6,\n      \"exit_zero_or_nonpositive_bid_ask\": 95,\n      \"missing_net_usd_pnl\": 395,\n      \"missing_point_in_time_breadth_confirmation\": 1291,\n      \"missing_point_in_time_qqq_momentum_confirmation\": 1080,\n      \"missing_point_in_time_spy_momentum_confirmation\": 395,\n      \"missing_point_in_time_vix_bucket\": 1291,\n      \"rejected_not_call_debit_spread\": 290,\n      \"rejected_outside_preregistered_universe\": 277\n    },\n    \"exact_completed_rows\": 0,\n    \"latest_audit_30_row_bar_met\": false,\n    \"minimum_historical_exact_rows\": 200,\n    \"old_mark_diagnostic_metrics\": {\n      \"avg_pnl_usd\": -65.68,\n      \"gross_loss_usd\": 239470.75,\n      \"gross_win_usd\": 180623.09,\n      \"loss_count\": 427,\n      \"net_pnl_usd\": -58847.66,\n      \"priced_row_count\": 896,\n      \"profit_factor\": 0.7543,\n      \"row_count\": 896,\n      \"win_count\": 469,\n      \"win_rate_pct\": 52.34\n    },\n    \"point_in_time_inputs_resolved\": 0,\n    \"proof_qualified_rows_after_resolution\": 0,\n    \"quote_coverage\": 0.6065,\n    \"replay_gate_blocker_count\": 15,\n    \"side_aware_diagnostic_metrics\": {\n      \"avg_pnl_usd\": 201.07,\n      \"bootstrap_pf_lower_bound_5pct\": null,\n      \"gross_loss_usd\": 121252.6,\n      \"gross_win_usd\": 278693.8,\n      \"loss_count\": 281,\n      \"net_pnl_usd\": 157441.2,\n      \"priced_row_count\": 783,\n      \"profit_factor\": 2.2985,\n      \"row_count\": 783,\n      \"stress_pf\": 2.2985,\n      \"win_count\": 502,\n      \"win_rate_pct\": 64.11\n    },\n    \"side_aware_quotes_resolved\": 783,\n    \"strict_new_exact_completed_rows\": 0,\n    \"strict_research_metrics\": {\n      \"avg_pnl_usd\": null,\n      \"bootstrap_pf_lower_bound_5pct\": null,\n      \"gross_loss_usd\": 0,\n      \"gross_win_usd\": 0,\n      \"loss_count\": 0,\n      \"net_pnl_usd\": null,\n      \"priced_row_count\": 0,\n      \"profit_factor\": null,\n      \"row_count\": 0,\n      \"stress_pf\": null,\n      \"win_count\": 0,\n      \"win_rate_pct\": null\n    },\n    \"total_denominator_rows\": 1291\n  },\n  \"next_oracle_instruction\": \"Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time VIX/breadth input surface or explicit approved data repair changes the blocker. Select the next materially different, falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows.\",\n  \"replay_gate_blockers\": [\n    \"bootstrap_pf_lower_bound_not_above_1_after_resolution\",\n    \"duplicate_within_research_harness\",\n    \"entry_missing_leg_quote\",\n    \"exit_missing_leg_quote\",\n    \"exit_value_negative\",\n    \"exit_zero_or_nonpositive_bid_ask\",\n    \"missing_net_usd_pnl\",\n    \"missing_point_in_time_breadth_confirmation\",\n    \"missing_point_in_time_qqq_momentum_confirmation\",\n    \"missing_point_in_time_spy_momentum_confirmation\",\n    \"missing_point_in_time_vix_bucket\",\n    \"net_usd_not_positive_after_resolution\",\n    \"rejected_not_call_debit_spread\",\n    \"rejected_outside_preregistered_universe\",\n    \"strict_rows_below_30_after_resolution\"\n  ],\n  \"status\": \"blocked_momentum_continuation_bounded_replay\"\n}\n\nCurrent preregistered VRP credit-spread playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.\",\n  \"concept_id\": \"low_mid_vix_index_put_credit_spread_vrp_v1\",\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_put_credit_spreads_only\"\n}\n\nCurrent VRP credit-spread replay readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If blocked, GPT-5.5 Pro should decide whether a named blocker needs operator approval or whether another read-only option-structure branch remains.\",\n  \"blockers\": [\n    \"missing_credit_spread_side_aware_pricing_engine\",\n    \"missing_credit_spread_side_aware_exit_pricing_engine\",\n    \"missing_full_denominator_status_mapping\",\n    \"missing_assignment_expiration_classifier\",\n    \"missing_margin_max_loss_convention\",\n    \"missing_point_in_time_vix_bucket\",\n    \"missing_index_credit_spread_quote_surface\",\n    \"missing_protected_holdout_guard\"\n  ],\n  \"concept_id\": \"low_mid_vix_index_put_credit_spread_vrp_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"blocked_vrp_credit_spread_replay_readiness\"\n}\n\nCurrent preregistered term-structure calendar/diagonal playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.\",\n  \"concept_id\": \"low_mid_vix_index_calendar_term_structure_dislocation_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_calendar_or_diagonal_debit_spreads_only\"\n}\n\nCurrent term-structure calendar/diagonal replay readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If ready, the next step is an exact operator approval question for one research-only implementation/replay harness. If blocked, GPT-5.5 Pro should decide whether a named blocker needs approval or whether another read-only option-structure branch remains.\",\n  \"blockers\": [\n    \"missing_calendar_diagonal_side_aware_pricing_engine\",\n    \"missing_calendar_diagonal_exit_or_expiry_engine\",\n    \"missing_full_denominator_status_mapping\",\n    \"missing_front_leg_assignment_expiration_classifier\",\n    \"missing_roll_or_expiry_policy\",\n    \"missing_point_in_time_term_structure_inputs\",\n    \"missing_index_calendar_quote_surface\",\n    \"missing_strict_new_dedupe\"\n  ],\n  \"concept_id\": \"low_mid_vix_index_calendar_term_structure_dislocation_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"blocked_term_structure_calendar_replay_readiness\"\n}\n\nCurrent preregistered skew broken-wing playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.\",\n  \"concept_id\": \"low_mid_vix_index_skew_broken_wing_put_fly_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_broken_wing_put_butterflies_only\"\n}\n\nCurrent preregistered macro-event long straddle/strangle playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.\",\n  \"concept_id\": \"low_mid_vix_macro_event_long_strangle_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_long_straddles_or_strangles_only\"\n}\n\nCurrent macro-event calendar artifact result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"macro_event_calendar_source_missing\",\n    \"missing_required_macro_event_categories\"\n  ],\n  \"covered_categories\": [],\n  \"event_calendar_implemented\": true,\n  \"event_count\": 0,\n  \"historical_replay_performed\": false,\n  \"missing_categories\": [\n    \"cpi\",\n    \"fomc_minutes\",\n    \"fomc_rate_decision\",\n    \"nonfarm_payrolls\",\n    \"pce\",\n    \"scheduled_fed_chair_testimony\"\n  ],\n  \"source_rows_proof_eligible\": false,\n  \"status\": \"blocked_macro_event_calendar_source_missing\"\n}\n\nCurrent point-in-time VIX bucket artifact result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"point_in_time_vix_source_missing\",\n    \"missing_vix_bucket_threshold_policy\",\n    \"vix_bucket_date_coverage_incomplete\"\n  ],\n  \"bucket_threshold_source\": null,\n  \"coverage_pct\": 0.0,\n  \"covered_date_count\": 0,\n  \"historical_replay_performed\": false,\n  \"late_known_at_count\": 0,\n  \"leakage_reject_count\": 0,\n  \"point_in_time_vix_low_mid_bucket_available\": false,\n  \"requested_date_count\": 505,\n  \"source_rows_count\": 0,\n  \"source_status\": \"missing\",\n  \"status\": \"blocked_point_in_time_vix_source_missing\"\n}\n\nCurrent macro-event long straddle/strangle replay readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this readiness artifact back to GPT-5.5 Pro for continue/stop. A later bounded read-only replay requires a separate Codex task, and still cannot enable live validation, auto-track, broker orders, quote import, evidence mutation, protected-holdout consumption, scanner release, proof-bar changes, or promotion.\",\n  \"blockers\": [\n    \"macro_event_calendar_source_missing\",\n    \"point_in_time_vix_source_missing\",\n    \"missing_vix_bucket_threshold_policy\",\n    \"vix_bucket_date_coverage_incomplete\"\n  ],\n  \"concept_id\": \"low_mid_vix_macro_event_long_strangle_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"smallest_next_blocker_clearing_slice\": {\n    \"blocker\": \"macro_event_calendar_source_missing\",\n    \"smallest_future_codex_slice\": \"Clear exactly this named blocker with a read-only artifact before replay.\"\n  },\n  \"status\": \"blocked_macro_event_long_strangle_replay_readiness\"\n}\n\nCurrent 13-symbol candidate-generation surface audit result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"candidate_generation_months_0_below_requested_24\",\n    \"existing_candidate_generation_surface_not_frozen_13_symbol\",\n    \"missing_candidate_generation_diagnostics\",\n    \"not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof\",\n    \"quote_depth_only_months_cannot_count\",\n    \"source_artifact_universe_not_13_symbol\"\n  ],\n  \"candidate_surface\": {\n    \"frozen_universe_exact_13_symbols\": false,\n    \"non_13_symbol_selected_row_count\": 0,\n    \"outside_allowed_universe\": [\n      \"AA\",\n      \"ABBV\",\n      \"AMD\",\n      \"AMT\",\n      \"AMZN\",\n      \"ARM\",\n      \"BA\",\n      \"BAC\",\n      \"C\",\n      \"CAT\",\n      \"CLF\",\n      \"COIN\",\n      \"COST\",\n      \"DE\",\n      \"DIS\",\n      \"EQR\",\n      \"FCX\",\n      \"GS\",\n      \"JPM\",\n      \"KO\",\n      \"LIN\",\n      \"LMT\",\n      \"MCD\",\n      \"META\",\n      \"MSFT\",\n      \"MSTR\",\n      \"NFLX\",\n      \"NKE\",\n      \"NVDA\",\n      \"OXY\",\n      \"PFE\",\n      \"PG\",\n      \"PLD\",\n      \"PLTR\",\n      \"PM\",\n      \"RTX\",\n      \"SBUX\",\n      \"SLB\",\n      \"SMCI\",\n      \"SPG\",\n      \"T\",\n      \"TSLA\",\n      \"V\",\n      \"WELL\",\n      \"WMT\",\n      \"XLK\"\n    ]\n  },\n  \"cvx_scope\": {\n    \"cvx_scope_enforced\": true,\n    \"excluded_months\": [],\n    \"excluded_trade_count\": 0,\n    \"minimum_executable_quote_pct\": 90.0,\n    \"observed_executable_quote_pct\": 88.66,\n    \"policy_blocker\": null,\n    \"policy_loaded\": true,\n    \"rule_id\": \"cvx_zero_bid_tradability_candidate_scope_v1\",\n    \"rule_status\": \"active\"\n  },\n  \"historical_rows_are_forward_proof\": false,\n  \"quote_vs_candidate_generation\": {\n    \"candidate_generation_months_covered\": [],\n    \"candidate_generation_months_covered_count\": 0,\n    \"distinction\": \"quote-history coverage does not prove pick/no-pick candidate-generation coverage\",\n    \"quote_surface_months_available\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"quote_surface_months_available_count\": 24,\n    \"selected_trade_depth_months_covered\": [\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\"\n    ],\n    \"selected_trade_depth_months_covered_count\": 8\n  },\n  \"runner_support\": {\n    \"candidate_commands\": [\n      \"uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json\"\n    ],\n    \"read_only_no_write_runner_available\": true,\n    \"rejected_commands\": [],\n    \"source_artifact_status\": \"candidate_generation_no_write_runner_ready_with_blockers\",\n    \"status\": \"read_only_no_write_runner_available\",\n    \"support_manifest\": {\n      \"as_of_date\": \"2026-06-04\",\n      \"as_of_gated\": true,\n      \"candidate_commands\": [\n        \"uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json\"\n      ],\n      \"evidence_stores_mutated\": false,\n      \"frozen_universe_exact_13_symbols\": true,\n      \"mutating\": false,\n      \"no_write\": true,\n      \"pre_holdout_as_of\": true,\n      \"production_scanner_changed\": false,\n      \"proof_bars_changed\": false,\n      \"protected_holdout_consumed\": false,\n      \"quotes_imported\": false,\n      \"read_only\": true,\n      \"read_only_no_write_runner_available\": true,\n      \"research_only\": true,\n      \"sizing_changed\": false,\n      \"stops_changed\": false,\n      \"strategy_logic_changed\": false,\n      \"universe_filter\": true\n    },\n    \"validation_reason_codes\": []\n  },\n  \"status\": \"blocked_13_symbol_candidate_generation_surface_audit\"\n}\n\nCurrent 13-symbol frozen candidate-generation source-surface materializer result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"candidate_generation_months_0_below_requested_24\",\n    \"missing_daily_candidate_generation_diagnostics\",\n    \"missing_frozen_13_symbol_candidate_generation_engine\",\n    \"outside_universe_source_rows_present\",\n    \"source_artifact_universe_not_13_symbol\"\n  ],\n  \"calendar_coverage\": {\n    \"calendar_months_covered\": [],\n    \"calendar_months_covered_count\": 0,\n    \"coverage_basis\": \"source_surface_not_frozen_13_symbol_or_missing_month_diagnostics\",\n    \"covered_months\": [],\n    \"status\": \"calendar_coverage_not_proven\",\n    \"unproven_requested_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"zero_selection_months\": [],\n    \"zero_selection_months_explicit\": false\n  },\n  \"historical_rows_are_forward_proof\": false,\n  \"no_write\": true,\n  \"posthoc_filtering_allowed_as_proof\": null,\n  \"read_only\": true,\n  \"selected_trade_summary\": {\n    \"selected_entry_months_with_rows\": [],\n    \"selected_rows_in_window\": 0\n  },\n  \"source_artifact_universe_exact_13_symbols\": null,\n  \"status\": \"blocked_13_symbol_frozen_candidate_generation_source_surface\"\n}\n\nCurrent preregistered post-event IV-crush iron-condor playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion.\",\n  \"concept_id\": \"post_event_iv_crush_index_iron_condor_v1\",\n  \"event_calendar_implemented_in_this_slice\": false,\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_short_iron_condors_or_iron_butterflies_only\"\n}\n\nCurrent preregistered flow-extreme ratio/backspread playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk spreads, and promotion.\",\n  \"concept_id\": \"index_flow_extreme_mean_reversion_ratio_backspread_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_ratio_spreads_or_backspreads_only\",\n  \"undefined_risk_allowed\": false\n}\n\nCurrent flow-extreme volume/open-interest source-row generator result, if available:\n{\n  \"accepted_profitability\": false,\n  \"aggregate_source_summary\": {\n    \"aggregate_row_count\": 1635,\n    \"data_trust\": \"trusted\",\n    \"date_count\": 501,\n    \"snapshot_kind\": \"intraday\",\n    \"source_labels\": [\n      \"thetadata_opra_nbbo_1m\"\n    ],\n    \"usable_aggregate_row_count\": 0\n  },\n  \"blockers\": [\n    \"missing_trusted_volume_open_interest_source_rows\",\n    \"trusted_rows_have_null_volume_open_interest\",\n    \"insufficient_month_coverage\",\n    \"insufficient_date_coverage\"\n  ],\n  \"coverage\": {\n    \"covered_date_count\": 0,\n    \"covered_month_count\": 0,\n    \"covered_months\": [],\n    \"date_coverage_pct\": 0.0,\n    \"minimum_covered_months\": 20,\n    \"minimum_date_coverage_pct\": 90.0,\n    \"missing_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"requested_date_count\": 494,\n    \"requested_month_count\": 24,\n    \"requested_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ]\n  },\n  \"evidence_stores_mutated\": false,\n  \"historical_rows_are_forward_proof\": false,\n  \"quotes_imported\": false,\n  \"source_row_count\": 0,\n  \"status\": \"blocked_flow_extreme_volume_oi_source_rows\",\n  \"threshold_policy\": {\n    \"flow_input_basis\": \"volume_open_interest\",\n    \"future_outcomes_used\": false,\n    \"known_at_rule\": \"prior trusted source date strictly before input_date_et\",\n    \"outcome_tuned\": false,\n    \"plain_bid_ask_used_as_flow\": false,\n    \"quote_depth_fabricated\": false,\n    \"realized_pnl_used\": false,\n    \"selected_winners_used\": false,\n    \"threshold_policy_id\": \"volume_open_interest_prior_day_trailing_distribution_v1\"\n  },\n  \"write_source_rows_allowed\": false\n}\n\nCurrent point-in-time flow-extreme input materializer result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"missing_point_in_time_flow_extreme_source\",\n    \"missing_required_flow_fields\",\n    \"insufficient_month_coverage\",\n    \"insufficient_date_coverage\"\n  ],\n  \"coverage\": {\n    \"covered_date_count\": 0,\n    \"covered_month_count\": 0,\n    \"covered_months\": [],\n    \"date_coverage_pct\": 0.0,\n    \"minimum_covered_months\": 20,\n    \"minimum_date_coverage_pct\": 90.0,\n    \"missing_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"requested_date_count\": 494,\n    \"requested_month_count\": 24,\n    \"requested_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"required_underlyings\": [\n      \"QQQ\",\n      \"SPY\"\n    ]\n  },\n  \"historical_rows_are_forward_proof\": false,\n  \"no_write\": true,\n  \"proxy_basis\": [],\n  \"read_only\": true,\n  \"source_inventory\": {\n    \"feature_store\": {\n      \"available_symbols\": [\n        \"QQQ\",\n        \"SPY\"\n      ],\n      \"error\": null,\n      \"exists\": true,\n      \"generated_at_utc\": \"2026-06-18T06:09:35Z\",\n      \"inventory_status\": \"feature_store_loaded_for_underlyings\",\n      \"missing_symbols\": [],\n      \"path\": \"data/profitability-lab/regular-options-feature-store/latest.json\",\n      \"report_id\": \"regular_options_feature_store\",\n      \"requested_date_count\": 494,\n      \"required\": true,\n      \"status\": \"loaded\",\n      \"status_value\": \"feature_store_built\"\n    },\n    \"options_history_db\": {\n      \"error\": null,\n      \"exists\": true,\n      \"flow_columns\": {\n        \"ask_size\": false,\n        \"bid_size\": false,\n        \"open_interest\": true,\n        \"quote_depth\": false,\n        \"volume\": true\n      },\n      \"path\": \"data/options-validation/options_history.db\",\n      \"status\": \"loaded\",\n      \"tables\": {\n        \"import_batches\": [\n          \"id\",\n          \"source_label\",\n          \"dataset_kind\",\n          \"data_trust\",\n          \"input_path\",\n          \"file_hash\",\n          \"imported_at_utc\",\n          \"total_rows\",\n          \"imported_rows\",\n          \"duplicate_rows\",\n          \"rejected_rows\",\n          \"warnings_json\"\n        ],\n        \"option_quote_snapshots\": [\n          \"id\",\n          \"as_of_utc\",\n          \"quote_date_et\",\n          \"quote_minute_et\",\n          \"snapshot_kind\",\n          \"underlying\",\n          \"contract_symbol\",\n          \"expiry\",\n          \"option_type\",\n          \"strike\",\n          \"bid\",\n          \"ask\",\n          \"last\",\n          \"iv\",\n          \"underlying_price\",\n          \"volume\",\n          \"open_interest\",\n          \"source_batch_id\"\n        ],\n        \"sqlite_sequence\": [\n          \"name\",\n          \"seq\"\n        ]\n      }\n    },\n    \"plain_bid_ask_only_is_not_flow\": true,\n    \"preregistered_playbook\": {\n      \"error\": null,\n      \"exists\": true,\n      \"generated_at_utc\": \"2026-06-23T05:51:48Z\",\n      \"path\": \"data/profitability-lab/regular-options-preregistered-flow-extreme-ratio-backspread-playbook/latest.json\",\n      \"report_id\": \"regular_options_preregistered_flow_extreme_ratio_backspread_playbook\",\n      \"required\": true,\n      \"status\": \"loaded\",\n      \"status_value\": \"preregistered_design_only\"\n    },\n    \"schema_declared_flow_basis\": {\n      \"bid_ask_size_imbalance\": false,\n      \"quote_depth_pressure\": false,\n      \"volume_open_interest\": true\n    },\n    \"source_rows\": {\n      \"error\": null,\n      \"exists\": false,\n      \"path\": \"data/profitability-lab/regular-options-point-in-time-flow-extreme-input/source_rows.jsonl\",\n      \"required\": false,\n      \"row_count\": 0,\n      \"status\": \"missing\"\n    },\n    \"status\": \"missing_flow_source_rows\"\n  },\n  \"status\": \"blocked_point_in_time_flow_extreme_input\"\n}\n\nCurrent multi-leg side-aware pricing capability result, if available:\n{\n  \"accepted_profitability\": false,\n  \"fixture_source_not_proof_eligible\": true,\n  \"historical_rows_are_forward_proof\": false,\n  \"pricing_capability_blockers\": [],\n  \"quote_resolution_counts\": {\n    \"blocker_counts\": {},\n    \"fixture_count\": 1,\n    \"resolved_fixture_count\": 1,\n    \"status_counts\": {\n      \"exact_exit_captured\": 1\n    }\n  },\n  \"source_inventory\": {\n    \"bid_ask_schema_fields\": [\n      \"bid\",\n      \"ask\"\n    ],\n    \"contract_symbol_fields\": [\n      \"underlying\",\n      \"contract_symbol\",\n      \"expiry\",\n      \"option_type\",\n      \"strike\"\n    ],\n    \"error\": null,\n    \"exists\": true,\n    \"path\": \"data/options-validation/options_history.db\",\n    \"quote_timestamp_fields\": [\n      \"as_of_utc\",\n      \"quote_date_et\",\n      \"quote_minute_et\"\n    ],\n    \"read_only_mode\": true,\n    \"status\": \"loaded\",\n    \"tables\": {\n      \"import_batches\": {\n        \"columns\": [\n          \"id\",\n          \"source_label\",\n          \"dataset_kind\",\n          \"data_trust\",\n          \"input_path\",\n          \"file_hash\",\n          \"imported_at_utc\",\n          \"total_rows\",\n          \"imported_rows\",\n          \"duplicate_rows\",\n          \"rejected_rows\",\n          \"warnings_json\"\n        ]\n      },\n      \"option_quote_snapshots\": {\n        \"columns\": [\n          \"id\",\n          \"as_of_utc\",\n          \"quote_date_et\",\n          \"quote_minute_et\",\n          \"snapshot_kind\",\n          \"underlying\",\n          \"contract_symbol\",\n          \"expiry\",\n          \"option_type\",\n          \"strike\",\n          \"bid\",\n          \"ask\",\n          \"last\",\n          \"iv\",\n          \"underlying_price\",\n          \"volume\",\n          \"open_interest\",\n          \"source_batch_id\"\n        ]\n      },\n      \"sqlite_sequence\": {\n        \"columns\": [\n          \"name\",\n          \"seq\"\n        ]\n      }\n    },\n    \"trusted_source_labels\": [\n      \"alpaca_opra_daily_snapshot\",\n      \"thetadata_opra_nbbo_1m\"\n    ]\n  },\n  \"status\": \"multi_leg_side_aware_pricing_capability_available\",\n  \"structure_support\": {\n    \"ratio_backspread_bounded\": {\n      \"blockers\": [],\n      \"denominator_mapping_status\": \"ready\",\n      \"fixture_count\": 1,\n      \"resolved_fixture_count\": 1,\n      \"status\": \"available\",\n      \"undefined_or_naked_ratio_risk_allowed\": false\n    }\n  }\n}\n\nCurrent base clean stack row-level identity ledger result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [],\n  \"duplicate_identity_count\": 0,\n  \"expected_base_clean_stack_exact_rows\": 157,\n  \"future_or_outcome_field_dependency_count\": 0,\n  \"historical_rows_are_forward_proof\": false,\n  \"ledger_row_count\": 157,\n  \"missing_identity_field_row_count\": 0,\n  \"proof_row_count\": 0,\n  \"protected_holdout_overlap_count\": 0,\n  \"status\": \"base_clean_stack_identity_ledger_ready\",\n  \"unique_identity_count\": 157\n}\n\nCurrent flow-extreme denominator/dedupe bridge result, if available:\n{\n  \"accepted_profitability\": false,\n  \"base_identity_hash_count\": 157,\n  \"base_identity_ledger_status\": \"ready\",\n  \"bridge_blockers\": [],\n  \"concept_id\": \"index_flow_extreme_mean_reversion_ratio_backspread_v1\",\n  \"denominator_status_contract\": [\n    \"candidate_not_generated_missing_flow_input\",\n    \"candidate_not_generated_missing_vix_bucket\",\n    \"candidate_rejected_missing_required_flow_fields\",\n    \"candidate_rejected_missing_vix_bucket\",\n    \"candidate_rejected_unbounded_or_undefined_risk\",\n    \"candidate_rejected_missing_leg_quote\",\n    \"candidate_rejected_zero_bid_or_untradable\",\n    \"candidate_rejected_crossed_or_stale_quote\",\n    \"candidate_duplicate_existing_base_stack\",\n    \"candidate_duplicate_within_research_harness\",\n    \"candidate_protected_holdout_overlap\",\n    \"priced_fixture_not_proof_eligible\",\n    \"readiness_candidate_priced_not_replayed\",\n    \"no_pick_explicit\",\n    \"blocked_source_missing\"\n  ],\n  \"fixture_source_not_proof_eligible\": true,\n  \"full_denominator_mapping_status\": \"ready\",\n  \"historical_rows_are_forward_proof\": false,\n  \"identity_fields\": [\n    \"concept_id\",\n    \"structure\",\n    \"underlying\",\n    \"signal_date\",\n    \"planned_entry_timestamp\",\n    \"option_rights\",\n    \"expirations\",\n    \"strikes\",\n    \"leg_sides\",\n    \"leg_ratios\",\n    \"entry_policy\",\n    \"exit_policy\",\n    \"candidate_source_id\"\n  ],\n  \"proof_row_count\": 0,\n  \"status\": \"flow_extreme_denominator_dedupe_bridge_ready\",\n  \"strict_new_dedupe_status\": \"ready\",\n  \"structure\": \"ratio_backspread_bounded\"\n}\n\nCurrent flow-extreme ratio/backspread replay-readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.\",\n  \"blockers\": [\n    \"missing_point_in_time_flow_extreme_input\",\n    \"missing_point_in_time_vix_bucket\"\n  ],\n  \"concept_id\": \"index_flow_extreme_mean_reversion_ratio_backspread_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"packet_ingestion\": {\n    \"expected_concept_id\": \"index_flow_extreme_mean_reversion_ratio_backspread_v1\",\n    \"expected_report_id\": \"regular_options_flow_extreme_ratio_backspread_replay_readiness\",\n    \"expected_structure\": \"defined_risk_ratio_spreads_or_backspreads_only\",\n    \"generated_at_utc\": \"2026-06-23T21:28:47Z\",\n    \"playbook_generated_at_utc\": \"2026-06-23T05:51:48Z\",\n    \"raw_status\": \"blocked_flow_extreme_ratio_backspread_replay_readiness\",\n    \"reason_codes\": [],\n    \"unsafe_flags\": [],\n    \"validated_status\": \"blocked_flow_extreme_ratio_backspread_replay_readiness\"\n  },\n  \"raw_status\": \"blocked_flow_extreme_ratio_backspread_replay_readiness\",\n  \"replay_performed\": false,\n  \"smallest_next_blocker_clearing_slice\": \"missing_point_in_time_flow_extreme_input\",\n  \"status\": \"blocked_flow_extreme_ratio_backspread_replay_readiness\",\n  \"structure\": \"defined_risk_ratio_spreads_or_backspreads_only\",\n  \"undefined_risk_allowed\": false\n}\n\nCurrent preregistered dispersion-proxy hybrid playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk pair structures, and promotion.\",\n  \"concept_id\": \"index_constituent_dispersion_proxy_defined_risk_hybrid_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_index_constituent_debit_credit_hybrid_pairs_only\",\n  \"undefined_or_uncapped_pair_risk_allowed\": false\n}\n\nCurrent point-in-time dispersion/concentration proxy materializer result, if available:\n{\n  \"accepted_profitability\": false,\n  \"blockers\": [\n    \"missing_point_in_time_dispersion_proxy_source\",\n    \"missing_required_return_fields\",\n    \"insufficient_month_coverage\",\n    \"insufficient_date_coverage\"\n  ],\n  \"coverage\": {\n    \"covered_date_count\": 0,\n    \"covered_month_count\": 0,\n    \"covered_months\": [],\n    \"date_coverage_pct\": 0.0,\n    \"minimum_covered_months\": 20,\n    \"minimum_date_coverage_pct\": 90.0,\n    \"missing_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ],\n    \"requested_date_count\": 494,\n    \"requested_month_count\": 24,\n    \"requested_months\": [\n      \"2024-06\",\n      \"2024-07\",\n      \"2024-08\",\n      \"2024-09\",\n      \"2024-10\",\n      \"2024-11\",\n      \"2024-12\",\n      \"2025-01\",\n      \"2025-02\",\n      \"2025-03\",\n      \"2025-04\",\n      \"2025-05\",\n      \"2025-06\",\n      \"2025-07\",\n      \"2025-08\",\n      \"2025-09\",\n      \"2025-10\",\n      \"2025-11\",\n      \"2025-12\",\n      \"2026-01\",\n      \"2026-02\",\n      \"2026-03\",\n      \"2026-04\",\n      \"2026-05\"\n    ]\n  },\n  \"historical_rows_are_forward_proof\": false,\n  \"no_write\": true,\n  \"read_only\": true,\n  \"source_inventory\": {\n    \"feature_store\": {\n      \"available_symbols\": [\n        \"AAPL\",\n        \"COP\",\n        \"CVX\",\n        \"DIA\",\n        \"GOOGL\",\n        \"IWM\",\n        \"JNJ\",\n        \"LLY\",\n        \"NEM\",\n        \"QQQ\",\n        \"SPY\",\n        \"UNH\",\n        \"XOM\"\n      ],\n      \"error\": null,\n      \"exists\": true,\n      \"generated_at_utc\": \"2026-06-18T06:09:35Z\",\n      \"inventory_status\": \"feature_store_missing_underlying_return_fields\",\n      \"missing_symbols\": [],\n      \"path\": \"data/profitability-lab/regular-options-feature-store/latest.json\",\n      \"report_id\": \"regular_options_feature_store\",\n      \"requested_date_count\": 494,\n      \"required\": true,\n      \"return_fields_available\": false,\n      \"status\": \"loaded\",\n      \"status_value\": \"feature_store_built\",\n      \"underlying_price_row_count\": 0\n    },\n    \"source_rows\": {\n      \"error\": null,\n      \"exists\": false,\n      \"path\": \"data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/source_rows.jsonl\",\n      \"required\": false,\n      \"row_count\": 0,\n      \"status\": \"missing\"\n    },\n    \"status\": \"missing_proxy_source_rows\"\n  },\n  \"status\": \"blocked_point_in_time_dispersion_concentration_proxy\"\n}\n\nCurrent dispersion-proxy hybrid replay-readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another research-only structure-readiness branch.\",\n  \"blockers\": [\n    \"missing_dispersion_or_concentration_proxy_inputs\",\n    \"point_in_time_vix_bucket_blocked\",\n    \"missing_pair_construction_engine\",\n    \"missing_side_aware_all_leg_pair_pricing\",\n    \"missing_pair_max_loss_or_collateral_convention\",\n    \"missing_full_denominator_mapping\",\n    \"missing_strict_new_dedupe\"\n  ],\n  \"concept_id\": \"index_constituent_dispersion_proxy_defined_risk_hybrid_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"replay_performed\": false,\n  \"smallest_next_blocker_clearing_slice\": \"missing_dispersion_or_concentration_proxy_inputs\",\n  \"status\": \"blocked_dispersion_proxy_hybrid_replay_readiness\",\n  \"structure\": \"defined_risk_index_constituent_debit_credit_hybrid_pairs_only\"\n}\n\nCurrent preregistered PMCC diagonal playbook result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, or replay requires a separate explicit research-only approval and must still forbid live, broker, quote import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk short calls, and promotion.\",\n  \"concept_id\": \"low_mid_vix_index_pmcc_diagonal_income_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"status\": \"preregistered_design_only\",\n  \"structure\": \"defined_risk_pmcc_style_call_diagonals_only\",\n  \"undefined_or_uncapped_short_call_risk_allowed\": false\n}\n\nCurrent PMCC diagonal replay-readiness result, if available:\n{\n  \"accepted_profitability\": false,\n  \"allowed_next_step\": \"Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.\",\n  \"blockers\": [\n    \"missing_point_in_time_trend_or_regime_inputs\",\n    \"point_in_time_vix_bucket_blocked\",\n    \"missing_trusted_pmcc_diagonal_quote_surface\"\n  ],\n  \"concept_id\": \"low_mid_vix_index_pmcc_diagonal_income_v1\",\n  \"historical_replay_performed\": false,\n  \"lane_implementation_performed\": false,\n  \"packet_ingestion\": {\n    \"expected_concept_id\": \"low_mid_vix_index_pmcc_diagonal_income_v1\",\n    \"expected_report_id\": \"regular_options_pmcc_diagonal_replay_readiness\",\n    \"expected_structure\": \"defined_risk_pmcc_style_call_diagonals_only\",\n    \"generated_at_utc\": \"2026-06-23T21:50:44Z\",\n    \"playbook_generated_at_utc\": \"2026-06-23T06:22:04Z\",\n    \"raw_status\": \"blocked_pmcc_diagonal_replay_readiness\",\n    \"reason_codes\": [],\n    \"unsafe_flags\": [],\n    \"validated_status\": \"blocked_pmcc_diagonal_replay_readiness\"\n  },\n  \"raw_status\": \"blocked_pmcc_diagonal_replay_readiness\",\n  \"replay_performed\": false,\n  \"smallest_next_blocker_clearing_slice\": \"missing_point_in_time_trend_or_regime_inputs\",\n  \"status\": \"blocked_pmcc_diagonal_replay_readiness\",\n  \"structure\": \"defined_risk_pmcc_style_call_diagonals_only\",\n  \"undefined_or_uncapped_short_call_risk_allowed\": false\n}\n\nCurrent goal-loop state:\n{\n  \"forward_evidence_accounting\": {\n    \"auto_track_allowed\": false,\n    \"broker_order_allowed\": false,\n    \"cohort_append_performed\": false,\n    \"cohort_log_exists\": false,\n    \"cohort_log_malformed_row_count\": 0,\n    \"cohort_log_path\": \"data/forward-tracking/phase2_regular_options_forward_paper_shadow_cohort.jsonl\",\n    \"cohort_log_row_count\": 0,\n    \"cohort_log_status\": \"missing\",\n    \"excluded_or_rejected_row_flags\": 0,\n    \"live_entry_allowed\": false,\n    \"minimum_required\": 30,\n    \"post_freeze_strict_exact_completed_rows\": 0,\n    \"promotion_ready\": false,\n    \"state\": \"log_missing_blocker\",\n    \"strict_reject_counts\": {\n      \"blocked_by_required_contracts\": 0,\n      \"duplicate_completed_selection_id\": 0,\n      \"duplicate_row_id\": 0,\n      \"exact_completed_missing_entry_quote_provenance\": 0,\n      \"exact_completed_missing_exit_quote_provenance\": 0,\n      \"exact_completed_missing_policy_exit_condition\": 0,\n      \"fixture_source_not_proof_eligible\": 0,\n      \"lookahead_claimed_as_exact\": 0,\n      \"market_window_not_open\": 0,\n      \"missing_net_pnl_usd\": 0,\n      \"missing_real_source_provenance\": 0,\n      \"missing_required_schema_fields\": 0,\n      \"missing_source_provenance_fields\": 0,\n      \"non_executable_mark_claimed_as_exact\": 0,\n      \"non_frozen_lane\": 0,\n      \"non_preregistered_symbol\": 0,\n      \"pre_freeze_not_acceptance_eligible\": 0,\n      \"scanner_hash_drift\": 0,\n      \"unknown_denominator_status\": 0\n    },\n    \"strict_rows_remaining_to_minimum\": 30,\n    \"strict_usd_pf_lower_bound_5pct\": null,\n    \"total_natural_selections\": 0\n  },\n  \"next_safe_action\": \"continue_paper_shadow_only\",\n  \"state\": \"underpowered_forward_evidence\"\n}\n\nImportant instruction:\nYou are not being asked for generic strategy advice or a casual continue/stop vote. Treat stopping as an exceptional claim. Because strict post-freeze forward proof is currently 0/30, you may recommend stopping only if you can prove that no significant upgrade remains after explicitly considering new lanes, new option structures, historical data-depth repair, and forward collection. Ask up to five operator questions that would materially affect the decision, but do not block on read-only/research-only work; the user has already approved that category. For any live/broker/import/mutation/promotion/proof-bar/holdout action, name the needed approval and select a safe read-only fallback unless no such fallback exists.\n\nReturn a concrete loop decision. If a significant upgrade remains, return verdict=continue, continue_loop=true, and exactly one next Codex task with files/artifacts/commands/tests/acceptance criteria. If a branch needs operator approval, ask the exact operator question and explain why it is required. If no significant upgrade remains under current approvals, return verdict=stop_exception, continue_loop=false, and provide the burden-of-proof check that earned that stop.\n\nDo not say \"collect more data\", \"try more strategies\", \"optimize parameters\", or \"run more backtests\" unless you specify the exact data, lane, option structure, date window, command, and pass/fail threshold.\n\nBefore any stop_exception, explicitly evaluate whether there is a falsifiable path through:\n1. fresh forward paper-shadow collection,\n2. scoped source repair or replay,\n3. a new historical data surface or longer-lookback audit,\n4. a new causal playbook,\n5. new option structures beyond the current directional-spread surface.\n\nNew option edge families to consider before stopping:\n- volatility risk premium,\n- skew mispricing,\n- term-structure dislocation,\n- earnings or macro event volatility,\n- post-event IV crush,\n- post-event drift,\n- trend or momentum continuation,\n- mean reversion,\n- dispersion-like proxy behavior,\n- liquidity or flow effects.\n\nOption structures to consider before stopping:\n- vertical spreads,\n- calendars,\n- diagonals,\n- broken-wing butterflies,\n- ratio spreads,\n- backspreads,\n- straddles,\n- strangles,\n- iron condors,\n- iron butterflies,\n- synthetic covered calls or PMCC-style diagonals,\n- debit/credit hybrids.\n\nFor every proposed lane, provide the frozen rule, eligible universe, inclusion/exclusion rules, leakage controls, required data repairs, minimum sample size, profitability thresholds, and the exact result that would falsify it. A lane should not pass because it has an attractive point backtest; it needs an economic mechanism and a falsifiable audit plan.\n\nAllowed branch families:\n1. fresh_forward_paper_shadow_collection - requires operator approval and a valid market-data window if rows will be appended.\n2. scoped_source_repair_or_replay - requires operator approval before quote import, evidence mutation, or source repair.\n3. new_causal_playbook_generation - read-only preregistration/falsification can continue without live/broker/evidence mutation.\n4. new_historical_data_surface_or_longer_lookback - requires operator approval if it changes the data surface.\n5. dashboard_or_operator_visibility - only significant if tied to a proof blocker or execution decision.\n\nForbidden unless explicitly approved later:\n- broker orders, live validation, auto-track, scanner release, stop/sizing changes, proof-bar relaxation, quote import, evidence DB mutation, protected holdout consumption, promotion.\n\nRequired JSON-like output shape:\n{\n  \"anti_handwave_audit\": {\n    \"exact_next_action_present\": \"boolean\",\n    \"generic_advice_removed\": \"boolean\",\n    \"measurable_threshold_present\": \"boolean\"\n  },\n  \"assumption_challenges\": [\n    {\n      \"assumption\": \"string\",\n      \"risk\": \"string\",\n      \"verification\": \"string\"\n    }\n  ],\n  \"branches_to_stop\": [\n    \"branch ids or candidate ids to avoid repeating\"\n  ],\n  \"burden_of_proof_check\": {\n    \"current_forward_rows\": \"number\",\n    \"reason\": \"string\",\n    \"stop_allowed\": \"boolean\",\n    \"target_profitable_strict_completed_rows\": \"number\"\n  },\n  \"candidate_branches\": [\n    {\n      \"branch\": \"string\",\n      \"expected_value\": \"string\",\n      \"main_uncertainty\": \"string\",\n      \"why_not_selected\": \"string|null\"\n    }\n  ],\n  \"continue_loop\": \"boolean\",\n  \"next_codex_task\": {\n    \"acceptance_criteria\": [\n      \"measurable pass/fail criteria\"\n    ],\n    \"allowed_files_or_artifacts\": [\n      \"paths or artifact families\"\n    ],\n    \"commands_to_run\": [\n      \"exact commands\"\n    ],\n    \"exact_scope\": \"files/modules/artifacts included and excluded\",\n    \"expected_artifacts\": [\n      \"files or readbacks expected after Codex runs\"\n    ],\n    \"failure_criteria\": [\n      \"what result rejects or parks this branch\"\n    ],\n    \"forbidden_actions\": [\n      \"actions that remain forbidden\"\n    ],\n    \"implementation_steps\": [\n      \"ordered steps\"\n    ],\n    \"objective\": \"one concrete implementation or verification task\",\n    \"stop_condition_after_task\": \"what would make this branch exhausted\"\n  },\n  \"operator_questions\": [\n    {\n      \"default_if_unanswered\": \"string\",\n      \"question\": \"string\",\n      \"why_it_matters\": \"string\"\n    }\n  ],\n  \"selected_branch_id\": \"string|null\",\n  \"significant_upgrade_available\": \"boolean\",\n  \"verdict\": \"continue|stop_exception\",\n  \"why_this_is_significant\": \"short explanation tied to profitability proof\"\n}\n\nRelevant NEXT_STEPS excerpt:\n# Next Steps\n\nLast updated: 2026-06-23\n\n## Active Historical Robust-Search Track\n\nCurrent read:\n- Phase 2 forward proof remains the active forward-audit target and is not profitable yet: `0/30` strict post-freeze completed rows, missing real cohort log, `promotion_ready=false`, and live/auto-track/broker flags false. The passive capture runner is now the preferred forward-only command because it wraps staging, validation, and guarded optional append while reading existing `scan_picks.jsonl` only. The latest real run returned `no_phase2_natural_selections_no_append`: `0` staged rows, no candidate JSONL, and no cohort log. During a valid open market window, the next forward-only attempt is:\n\n```powershell\nnpm run options:capture:phase2-forward-paper-shadow -- --market-window-confirmed --market-window-status open --json\nnpm run options:validate:phase2-forward-paper-shadow-candidate -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl\nnpm run options:append:phase2-forward-paper-shadow -- data/forward-tracking/phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl --approval-token APPROVE_PHASE2_FORWARD_COHORT_APPEND --market-window-confirmed\nnpm run options:goal-loop:paper-shadow -- --json\n```\n\nOnly run the validate/append commands if the capture runner wrote candidate rows from real same-day market-window scan picks and validation reports `append_allowed=true`; never append fixture/test/synthetic rows.\n- the forward cohort remains frozen and passive; do not use historical rows as fresh forward promotion proof.\n- the no-wait profitability track is to extend trusted historical ThetaData OPRA/NBBO coverage, then run a split-aware robust-search evaluation before nominating any new lane for forward tracking.\n- trusted `thetadata_opra_nbbo_1m` intraday coverage for the 13-symbol proof/import set (`SPY`, `QQQ`, `IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`, `DIA`) is now `505` shared dates from `2024-05-22` through `2026-06-04`; the 504-date two-year feature-store depth target is met.\n- paid-data readiness is still `not_ready` after batch `2147` because `CVX` executable quote coverage is `88.66%`, below the `90%` floor; do not use the 13-symbol surface for a nomination until this clears or the lane explicitly excludes/fails the affected symbol under a preregistered rule.\n- `docs/regular-options-cvx-executable-coverage.md` diagnoses the CVX issue as observed zero-bid tradability, not missing provider data: `495,306` trusted rows, `505` dates, `56,191` non-executable rows, `100.0%` of non-executable rows are zero-bid/positive-ask, `0` missing bid/ask rows, `0` crossed quotes, and the current multilane source report contains `3` selected CVX historical trades plus `1` suppressed duplicate.\n- `data/contracts/regular-options-source-quality-scope-policy.json` is active and applies the `cvx_zero_bid_tradability_candidate_scope_v1` rule, excluding the `3` matching CVX `bullish_pullback_core` rows from historical nomination metrics without lowering the quote-quality floor.\n- ThetaTerminal v3 is reachable at `http://127.0.0.1:25503`; the old-date dry-run for `2024-05-22` returned `20,958` normalized rows with `0` errors.\n- batches `2130` through `2146` imported `2024-05-22` through `2025-05-14` for the 13-symbol set with `5,805,236` trusted intraday rows, `0` duplicates, and `0` rejects. Batch `2147` then imported the scoped post-repair exact missing rows for the four coverage-repair variants: `17` trusted intraday rows, `0` duplicates, `0` rejects, `0` dry-run/import errors, and `0` lookahead-only rows.\n- `docs/regular-options-feature-store.md` is now the point-in-time feature-store readback: `12,149,436` trusted intraday rows, all `13` symbols available, `505` shared quote dates, and joins require `feature.tradable_after_time <= candidate_entry_time`.\n- `docs/regular-options-robust-search-evaluation.md` is now the split-aware historical robust-search report. Current result is `historical_candidates_blocked`: `231` exact rows accepted after `3` CVX source-quality scope exclusions, `0` / `3` candidates ready, regime robustness passed, feature-store gate passed, combined final holdout `28` trades with bootstrap PF lower bound `0.61`, and blockers include final holdout below `30`, final PF-LB below the selection-adjusted bar, paper-shadow/source-quality blockers, and lane-specific unpriced/zero-bid blockers.\n- `docs/regular-options-historical-simulated-forward-audit.md` is now the explicit calendar split audit exposed as `npm run options:audit:historical-simulated-forward`. It answers the \"two years of data\" challenge by separating quote-history depth from candidate-generation proof: the feature store has `505` shared trusted intraday dates through `2026-06-04`, but the current fail-closed frozen 13-symbol source surface proves `0/24` candidate-generation months and `0` selected rows. The requested `20` train months plus latest `4` simulated-forward audit months is therefore blocked (`selected_trade_months_0_below_required_24`, `train_months_0_below_20`, `audit_months_0_below_4`, `latest_audit_exact_trades_0_below_30`). No latest-four proof-qualified simulated-forward P&L can be claimed from this source chain.\n- `docs/regular-options-historical-depth-selected-trades.md` is the earlier read-only selected-trade calendar-depth readback exposed as `npm run options:build:historical-depth-selected-trades`; it showed why the broad source could not answer the `2024-06` through `2026-05` question. The current proof chain should use the fail-closed frozen source-surface materializer instead of counting broad-source selected rows.\n- `docs/regular-options-point-in-time-selected-trade-depth.md` and `docs/regular-options-point-in-time-candidate-generation.md` are the read-only point-in-time selected-trade depth and candidate-generation proof reports. The current 13-symbol chain consumes the frozen source surface, which proves `0/24` months and no selected rows; zero-selection months outside a proven candidate-generation source cannot be counted as real no-pick months.\n- `docs/regular-options-13-symbol-candidate-generation-no-write.md` is now the read-only no-write/as-of/universe-filter runner-support artifact, exposed as `npm run options:research:13-symbol-no-write-candidate-generation -- --no-write --json`. It proves safe runner controls only; it does not prove candidate-surface coverage or profitability.\n- `docs/regular-options-13-symbol-frozen-candidate-generation-source-surface.md` is now the read-only frozen 13-symbol source-surface materializer, exposed as `npm run options:research:13-symbol-frozen-candidate-generation-source-surface -- --no-write --json`. Current result is `blocked_13_symbol_frozen_candidate_generation_source_surface`: it refuses to post-hoc filter the broad `59`-symbol source into proof, proves `0/24` candidate-generation months and `0` selected rows, and names blockers `missing_frozen_13_symbol_candidate_generation_engine`, `source_artifact_universe_not_13_symbol`, `outside_universe_source_rows_present`, `missing_daily_candidate_generation_diagnostics`, and `candidate_generation_months_0_below_requested_24`.\n- `docs/regular-options-13-symbol-candidate-generation-surface-audit.md` is now the same-session GPT-5.5-selected read-only audit of the narrower 13-symbol research surface, exposed as `npm run options:research:13-symbol-candidate-generation-surface-audit`. Current result is `blocked_13_symbol_candidate_generation_surface_audit`: all `24` requested months have quote-surface availability, and runner support is now `read_only_no_write_runner_available`, but the fail-closed frozen source surface proves `0/24` candidate-generation months and no selected rows. This confirms the remaining blocker is source-surface/candidate-generation proof, not quote depth or missing runner support, and it remains not accepted profitability.\n- `docs/regular-options-point-in-time-dispersion-concentration-\n\nRelevant DECISIONS excerpt:\n# Decisions\n\n## 2026-06-23: Park PMCC Diagonal Readiness On Missing Trend, VIX, And Long-DTE Quote Surface\n\nGPT-5.5 Pro selected a read-only replay-readiness audit for `low_mid_vix_index_pmcc_diagonal_income_v1`. `scripts/build_regular_options_pmcc_diagonal_replay_readiness.py`, exposed as `npm run options:research:pmcc-diagonal-replay-readiness`, now owns that artifact.\n\nLatest status is `blocked_pmcc_diagonal_replay_readiness`. The preregistered PMCC design is valid and remains design-only, undefined/uncapped short-call risk is false, side-aware diagonal entry/roll/exit formulas are registered, short-call roll/assignment/ex-dividend/expiration handling is registered, max-loss/collateral and denominator statuses are registered, the base clean stack identity ledger is ready, and protected-holdout guard is loaded. The real blockers are `missing_point_in_time_trend_or_regime_inputs`, `point_in_time_vix_bucket_blocked`, and `missing_trusted_pmcc_diagonal_quote_surface`; read-only `options_history.db` inspection found `1,992,676` trusted SPY/QQQ call quote rows but `0` long-DTE call rows for the PMCC surface.\n\nDurable decision: do not proceed to PMCC replay and do not repeat this readiness audit unless a point-in-time trend/regime input surface, VIX bucket source/policy, or trusted long-DTE diagonal quote surface changes. This artifact is not replay, not accepted profitability, not forward proof, not quote import, not evidence mutation, not scanner/strategy/proof-bar change, not live validation, not auto-track, not broker permission, not protected-holdout use, and not promotion.\n\n## 2026-06-23: Do Not Treat Empty Trusted Volume/OI Columns Or Research-Grade Flow As Flow Proof\n\nGPT-5.5 Pro selected a read-only volume/open-interest source-row generator for the flow-extreme ratio/backspread branch. `scripts/build_regular_options_flow_extreme_volume_oi_source_rows.py`, exposed as `npm run options:research:flow-extreme-volume-oi-source-rows`, now owns that artifact.\n\nLatest status is `blocked_flow_extreme_volume_oi_source_rows`. The generator opened `data/options-validation/options_history.db` read-only, filtered to trusted `thetadata_opra_nbbo_1m` intraday SPY/QQQ rows, and found `1,635` aggregate rows across `501` dates but `0` usable volume/open-interest aggregates. No point-in-time source rows were written, coverage stayed `0/24` months and `0.0%`, and blockers are `missing_trusted_volume_open_interest_source_rows`, `trusted_rows_have_null_volume_open_interest`, `insufficient_month_coverage`, and `insufficient_date_coverage`.\n\nDurable decision: empty trusted volume/open-interest columns do not clear the flow-input blocker, and research-grade daily rows with volume/OI must not be relabeled as trusted proof without a separate explicit data-trust/source decision. Do not repeat the volume/OI source-row slice unless a new trusted point-in-time volume/OI source, approved data-trust repair, or explicit flow-source strategy changes the blocker. This artifact is not replay, not accepted profitability, not forward proof, not quote import, not evidence mutation, not scanner/strategy/proof-bar change, not live validation, not auto-track, not broker permission, not protected-holdout use, and not promotion.\n\n## 2026-06-23: Do Not Pretend Strict-New Dedupe Is Ready Without Row-Level Base Identities\n\nGPT-5.5 Pro selected a read-only denominator and strict-new dedupe bridge for the flow-extreme ratio/backspread branch. `scripts/build_regular_options_flow_extreme_denominator_dedupe_bridge.py`, exposed as `npm run options:research:flow-extreme-denominator-dedupe-bridge`, now owns that bridge artifact.\n\nLatest status is `flow_extreme_denominator_dedupe_bridge_ready`. The bridge defines the full ratio/backspread denominator status contract and point-in-time opportunity identity hash fields, validates a bounded fixture, consumes the existing multi-leg side-aware pricing capability, and now consumes `data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json`.\n\nThe base ledger is generated by `scripts/build_regular_options_base_clean_stack_identity_ledger.py`, exposed as `npm run options:research:base-clean-stack-identity-ledger`. Current ledger status is `base_clean_stack_identity_ledger_ready`: `157` expected rows, `157` ledger rows, `157` unique identities, `0` duplicate identities, `0` missing identity rows, `0` future/outcome identity dependencies, and `0` protected-holdout overlaps.\n\nDurable decision: strict-new dedupe must fail closed when the base stack lacks row-level identities, but this specific blocker is now cleared for the flow-extreme branch. Fixture identities and base identity hashes are not proof rows, not replay, not forward proof, and not profitability. The flow-extreme branch remains parked only on `missing_point_in_time_flow_extreme_input` and `missing_point_in_time_vix_bucket`; do not repeat the base-ledger or denominator-bridge slice unless those artifacts become missing, malformed, unsafe, stale, or no longer consumed by readiness.\n\n## 2026-06-23: Clear Ratio/Backspread Pricing Capability Without Counting Fixtures As Proof\n\nGPT-5.5 Pro selected a read-only cross-branch blocker-clear for multi-leg side-aware pricing and denominator capability. `scripts/build_regular_options_multi_leg_side_aware_pricing_capability.py`, exposed as `npm run options:research:multi-leg-side-aware-pricing-capability`, now owns that capability artifact.\n\nLatest status is `multi_leg_side_aware_pricing_capability_available`. The artifact opens `data/options-validation/options_history.db` in read-only mode, resolves one bounded QQQ ratio/backspread fixture from trusted `thetadata_opra_nbbo_1m` bid/ask rows, rejects midpoint/source-mark/EOD/display/manual/last/model/synthetic/lookahead evidence, and marks fixture rows as `fixture_source_not_proof_eligible=true`. It clears only the flow-readiness blocker `missing_side_aware_ratio_backspread_pricing`.\n\nDurable decision: capability fixtures are not historical replay, accepted profitability, forward proof, or promotion evidence. The flow-extreme ratio/backspread branch remains blocked by `missing_point_in_time_flow_extreme_input`, `missing_point_in_time_vix_bucket`, `missing_full_denominator_mapping`, and `missing_strict_new_dedupe`. Do not repeat this pricing slice unless the capability artifact becomes missing, malformed, unsafe, or no longer consumed by readiness.\n\n## 2026-06-23: Park Flow-Extreme Input On Missing Trusted Flow Source Rows\n\nGPT-5.5 Pro selected a read-only point-in-time flow-extreme input materializer as the smallest blocker-clearing slice for `index_flow_extreme_mean_reversion_ratio_backspread_v1`. `scripts/build_regular_options_point_in_time_flow_extreme_input.py`, exposed as `npm run options:research:point-in-time-flow-extreme-input`, now owns that input artifact.\n\nLatest status is `blocked_point_in_time_flow_extreme_input`. The materializer found no trusted local flow source rows at `data/profitability-lab/regular-options-point-in-time-flow-extreme-input/source_rows.jsonl`, `0/24` covered months, `0.0%` date coverage, and blockers `missing_point_in_time_flow_extreme_source`, `missing_required_flow_fields`, `insufficient_month_coverage`, and `insufficient_date_coverage`. It inventories `options_history.db` read-only and confirms `volume` / `open_interest` columns exist, while `bid_size`, `ask_size`, and `quote_depth` do not; plain bid/ask quote availability is explicitly not treated as flow.\n\nDurable decision: do not rerun the flow-extreme readiness audit expecting progress until a trusted point-in-time flow/extreme source exists. The input materializer is not replay, profitability, forward proof, quote import, evidence mutation, scanner/strategy change, live validation, auto-track, broker permission, protected-holdout use, proof-bar change, or promotion. It only makes the missing flow source explicit for the next Oracle pivot.\n\n## 2026-06-23: Park Dispersion Input On Missing Point-In-Tim\n\nRelevant PROJECT_CONTEXT excerpt:\n# Project Context\n\nThis repository is a mixed Next.js and FastAPI options research system. The active regular-options product is a supervised lane family for scanning, replay diagnostics, paper ideas, and tracked-position review. The browser UI is organized as a `Trading Desk` for open/closed positions, Alpaca paper-tracked positions, and an all-tracked-stock rollup, with live scan picks available behind the archive toggle, plus a replay-first `Strategy Lab` for validation and policy editing. FastAPI `python-backend/main.py` remains the app composition root, while profile, predictions, and tools routes are extracted into late-bound route modules so LLM agents can read route ownership without losing test-time monkeypatch behavior. Decorator-free application services now include `python-backend/proof_summary_service.py` for `/api/proof-summary`, `python-backend/replay_profit_service.py` for replay/profit readback assembly, and `python-backend/alpaca_paper_trading.py` for opt-in Alpaca paper order submission from proof-gated scanner-origin creates; proof, replay, scanner policy, broker-paper, and profit-cycle semantics stay in the domain modules named by `docs/replay-profit-contract.md` and `docs/DECISIONS.md`. The Trading Desk now treats open tracked positions, Alpaca paper-tracked rows, and open paper ideas as operator review surfaces, while closed/history-heavy rows load on demand through paged read routes. Closed Trades defaults to `Truth-grade`, the strict production-proof filter for live-production accuracy claims. `Realized P&L` remains available as a broader executable historical-learning slice, but historical current-policy guardrail replay is no longer surfaced in the operator dashboard because it can be mistaken for current recommendations or forward-audit performance.\n\nThe proof/evidence contract for those views is versioned at `data/contracts/proof-evidence-contract.json` and explained in `docs/proof-evidence-contract.md`. Backend proof predicates remain authoritative; frontend evidence groups flow from generated `src/lib/generated/proofEvidenceContract.ts` through `src/lib/trading-desk/proofContract.ts` as display/readability wrappers around the same proof classes, quote evidence classes, research/backfill markers, top-level and source-snapshot backfill/migration identity fields, and exit-basis tokens. Compact Trading Desk rows emit read-time `evidence_group` and `quote_evidence_class` diagnostics from the same contract; those labels are not persisted authority and stale frontend labels fail closed by contract version. Read-only audit and research reports use `scripts/quote_evidence_readback.py` for the same quote-class vocabulary, while separately labeling research/backfill row policy and production-proof falsehood. The generated `docs/proof-invariant-table.md`, sourced from `data/contracts/proof-invariant-cases.json`, is the shared backend/frontend regression matrix for raw exact, production proof, Truth-grade, and realized-P&L boundaries.\n\nAI commodity / commodity-infrastructure options is a separate proof-first strategy lane under `data/ai-commodity-infra/` and `scripts/run_ai_commodity_opra_progress.py`. The generated isolation owner is `docs/ai-commodity-isolation.md`, backed by `data/contracts/ai-commodity-isolation.json`. Its preferred final proof path is Alpaca SIP/OPRA bid/ask snapshot replay using `alpaca_opra_daily_snapshot` rows in `data/options-validation/options_history.db`.\n\nThe lane must not claim profitability from underlying bars, option OHLC bars, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, or in-sample-only sweeps. Final promotion requires point-in-time bid/ask or NBBO replay with realistic costs and validation splits.\n\nRegular-options metric readbacks must now use the same proof posture. WFO simulation charges slippage and per-contract fees, expiry settlement uses expiry-day prices, blank/unknown evidence classes quarantine instead of fail-opening to live evidence, profit factor is nullable for no-loss samples, and PF claims use net USD P&L where available. The fresh forward evidence funnel still has `0` exact realized P&L rows and `0` promotion-ready rows; the current named-gate defect report is `docs/fresh-executable-evidence-defect-report-2026-06-09.md`. QQQ `id=537` now has a fresh executable exact HOLD review and SBUX `id=104` is closed from executable exact side-aware exit evidence, so the remaining fresh-evidence gate is legitimate exact realized exit P&L for QQQ `id=537` or another fresh candidate.\n\nThe regular supervised scanner safety contract is now lane-wide and metadata-driven. Regular playbooks default to fresh live validation and `position_tracking_mode=auto_track`; AI Commodity remains separate with scanner/tracked-position tracking disabled. Production scans default to portfolio caps on; caps-off scans are diagnostic unless explicitly allowed. Scanner-origin position and suggested-trade creation requires verified archived forward-scan lineage, a caps-enforced source scan, source `creation_eligible=true`, a current guardrail rerun, and exact-contract proof eligibility. When caps are enforced, existing positions, same-ticker/exact-spread exposure, max concurrent positions, cost-risk, drawdown, daily/weekly loss, sector/regime caps, and correlated-index exposure are hard blockers for auto-track and scanner-origin creation; near-cap notes and sizing reductions may remain cautions. Historical/research rows must use explicit manual modes and remain separated from production proof; control/scout proof labels do not make fresh executable regular rows paper-review-only.\nThe scanner creation safety contract is versioned at `data/contracts/scanner-creation-safety-contract.json` and explained in `docs/scanner-creation-safety-contract.md`. Scheduled auto-track requires explicit market-open state, an available caps-enforced exposure snapshot, auto-track playbook metadata, source `creation_eligible=true`, no creation blockers, proof eligibility, fresh profitability/promotion artifacts, and a passing regular open-risk governor; unknown market, exposure, lane, proof, or open-risk state is not a creation event. Manual Alpaca paper execution uses the same scanner-origin creation gate, submits exactly `1` contract through the Alpaca paper endpoint when explicitly enabled, and records broker-paper metadata separately from OPRA/NBBO production-proof evidence.\nThe candidate lifecycle status contract is generated by `scripts/candidate_lifecycle.py` at `data/contracts/candidate-lifecycle-contract.json`, `docs/candidate-lifecycle-contract.md`, and `src/lib/generated/candidateLifecycleContract.ts`. Queue builders, profitability/promotion gates, pending validation, disposition reporting, and fresh-evidence readbacks use this shared status/outcome vocabulary so paper-only, diagnostic, pending, and validation-attempted rows cannot disappear because a new status was added in only one module. Paper/probation lanes use `pending_paper_exact_evidence` for exact evidence collection; they do not enter `pending_live_validation`.\nThe Phase 2 regular-options forward cohort is preregistered at `data/contracts/forward-cohort-preregistration.json`, with generated doc `docs/forward-cohort-preregistration.md`. Freeze date is `2026-06-14` and eval date is `2026-07-28`. The frozen lanes are `volatility_expansion_observation` and the clean `bullish_pullback_observation` carrier set (`IWM`, `AAPL`, `GOOGL`, `UNH`, `LLY`, `JNJ`, `XOM`, `CVX`, `COP`, `NEM`). `scripts/lane_promotion_state.py`, daily all-lanes/starvation checks, audit completeness guards, scheduled scan logging, and pending validation read this contract so every other regular lane is parked outside the cohort with scans and chores disabled until evaluation or an explicit refreeze. The contract does not lower existing proof bars, consume the protected holdout, submit orders, or convert research/backfill rows into production proof.\nPhase 2 candidat\n",
536 |   "proof_bars_changed": false,
537 |   "protected_holdout_consumed": false,
538 |   "purpose": "Create a reusable same-session GPT-5.5 Pro handoff that keeps the profitability loop moving until GPT-5.5 says no significant upgrades remain.",
539 |   "quotes_imported": false,
540 |   "report_id": "options_oracle_profit_loop_packet",
541 |   "scanner_policy_changed": false,
542 |   "significant_upgrade_definition": [
543 |     "materially increases proof-qualified forward rows, strict-new executable historical rows, quote/execution cleanliness, PF lower-bound confidence, holdout depth, or operator ability to collect exact evidence",
544 |     "retires a false branch with a measurable stop verdict so future loops avoid it",
545 |     "opens a new bounded causal playbook or data-surface branch with clear commands, tests, and acceptance gates",
546 |     "does not count if it only aggregates raw overlapping rows, improves wording, reruns an exhausted variant, lowers proof bars, or depends on live/broker/evidence mutation without approval"
547 |   ],
548 |   "sizing_changed": false,
549 |   "source_artifacts": {
550 |     "base_clean_stack_identity_ledger": {
551 |       "exists": true,
552 |       "generated_at_utc": "2026-06-23T21:04:36Z",
553 |       "path": "data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json",
554 |       "report_id": "regular_options_base_clean_stack_identity_ledger",
555 |       "required": false,
556 |       "status": "loaded"
557 |     },
558 |     "candidate_generation_13_symbol_frozen_source_surface": {
559 |       "exists": true,
560 |       "generated_at_utc": "2026-06-23T19:18:23Z",
561 |       "path": "data/profitability-lab/regular-options-13-symbol-frozen-candidate-generation-source-surface/latest.json",
562 |       "report_id": "regular_options_13_symbol_frozen_candidate_generation_source_surface",
563 |       "required": false,
564 |       "status": "loaded"
565 |     },
566 |     "candidate_generation_13_symbol_surface_audit": {
567 |       "exists": true,
568 |       "generated_at_utc": "2026-06-23T19:18:41Z",
569 |       "path": "data/profitability-lab/regular-options-13-symbol-candidate-generation-surface-audit/latest.json",
570 |       "report_id": "regular_options_13_symbol_candidate_generation_surface_audit",
571 |       "required": false,
572 |       "status": "loaded"
573 |     },
574 |     "causal_falsification": {
575 |       "exists": true,
576 |       "generated_at_utc": "2026-06-22T14:28:59Z",
577 |       "path": "data/profitability-lab/regular-options-causal-falsification-slice/latest.json",
578 |       "report_id": "regular_options_causal_falsification_slice",
579 |       "required": false,
580 |       "status": "loaded"
581 |     },
582 |     "decisions": {
583 |       "excerpt_chars": 8000,
584 |       "exists": true,
585 |       "path": "docs/DECISIONS.md",
586 |       "status": "loaded"
587 |     },
588 |     "dispersion_proxy_hybrid_replay_readiness": {
589 |       "exists": true,
590 |       "generated_at_utc": "2026-06-23T19:41:46Z",
591 |       "path": "data/profitability-lab/regular-options-dispersion-proxy-hybrid-replay-readiness/latest.json",
592 |       "report_id": "regular_options_dispersion_proxy_hybrid_replay_readiness",
593 |       "required": false,
594 |       "status": "loaded"
595 |     },
596 |     "flow_extreme_denominator_dedupe_bridge": {
597 |       "exists": true,
598 |       "generated_at_utc": "2026-06-23T21:04:43Z",
599 |       "path": "data/profitability-lab/regular-options-flow-extreme-denominator-dedupe-bridge/latest.json",
600 |       "report_id": "regular_options_flow_extreme_denominator_dedupe_bridge",
601 |       "required": false,
602 |       "status": "loaded"
603 |     },
604 |     "flow_extreme_ratio_backspread_replay_readiness": {
605 |       "exists": true,
606 |       "generated_at_utc": "2026-06-23T21:28:47Z",
607 |       "path": "data/profitability-lab/regular-options-flow-extreme-ratio-backspread-replay-readiness/latest.json",
608 |       "report_id": "regular_options_flow_extreme_ratio_backspread_replay_readiness",
609 |       "required": false,
610 |       "status": "loaded",
611 |       "unsafe_flags": [],
612 |       "validated_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
613 |       "validation_reason_codes": []
614 |     },
615 |     "flow_extreme_volume_oi_source_rows": {
616 |       "exists": true,
617 |       "generated_at_utc": "2026-06-23T21:28:46Z",
618 |       "path": "data/profitability-lab/regular-options-flow-extreme-volume-oi-source-rows/latest.json",
619 |       "report_id": "regular_options_flow_extreme_volume_oi_source_rows",
620 |       "required": false,
621 |       "status": "loaded"
622 |     },
623 |     "frontier": {
624 |       "exists": true,
625 |       "generated_at_utc": "2026-06-22T04:29:49Z",
626 |       "path": "data/profitability-lab/regular-options-countable-throughput-frontier/latest.json",
627 |       "report_id": "regular_options_countable_throughput_frontier",
628 |       "required": true,
629 |       "status": "loaded"
630 |     },
631 |     "goal_loop": {
632 |       "exists": true,
633 |       "generated_at_utc": "2026-06-23T15:11:45Z",
634 |       "path": "data/forward-tracking/options_goal_loop_latest.json",
635 |       "report_id": "options_goal_loop",
636 |       "required": false,
637 |       "status": "loaded"
638 |     },
639 |     "macro_event_calendar": {
640 |       "exists": true,
641 |       "generated_at_utc": "2026-06-23T17:45:59Z",
642 |       "path": "data/profitability-lab/regular-options-macro-event-calendar/latest.json",
643 |       "report_id": "regular_options_macro_event_calendar",
644 |       "required": false,
645 |       "status": "loaded"
646 |     },
647 |     "macro_event_long_strangle_replay_readiness": {
648 |       "exists": true,
649 |       "generated_at_utc": "2026-06-23T17:46:07Z",
650 |       "path": "data/profitability-lab/regular-options-macro-event-long-strangle-replay-readiness/latest.json",
651 |       "report_id": "regular_options_macro_event_long_strangle_replay_readiness",
652 |       "required": false,
653 |       "status": "loaded"
654 |     },
655 |     "momentum_continuation_bounded_replay": {
656 |       "exists": true,
657 |       "generated_at_utc": "2026-06-23T16:48:19Z",
658 |       "path": "data/profitability-lab/regular-options-momentum-continuation-bounded-replay/latest.json",
659 |       "report_id": "regular_options_momentum_continuation_bounded_replay",
660 |       "required": false,
661 |       "status": "loaded"
662 |     },
663 |     "momentum_continuation_proof_blocker_resolution": {
664 |       "exists": true,
665 |       "generated_at_utc": "2026-06-23T14:10:37Z",
666 |       "path": "data/profitability-lab/regular-options-momentum-continuation-proof-blocker-resolution/latest.json",
667 |       "report_id": "regular_options_momentum_continuation_proof_blocker_resolution",
668 |       "required": false,
669 |       "status": "loaded"
670 |     },
671 |     "momentum_continuation_research_replay": {
672 |       "exists": true,
673 |       "generated_at_utc": "2026-06-23T14:10:13Z",
674 |       "path": "data/profitability-lab/regular-options-momentum-continuation-research-replay/latest.json",
675 |       "report_id": "regular_options_momentum_continuation_research_replay",
676 |       "required": false,
677 |       "status": "loaded"
678 |     },
679 |     "momentum_edge": {
680 |       "exists": true,
681 |       "generated_at_utc": "2026-06-22T14:35:29Z",
682 |       "path": "data/profitability-lab/regular-options-current-regime-momentum-edge/latest.json",
683 |       "report_id": "regular_options_current_regime_momentum_edge",
684 |       "required": false,
685 |       "status": "loaded"
686 |     },
687 |     "multi_leg_side_aware_pricing_capability": {
688 |       "exists": true,
689 |       "generated_at_utc": "2026-06-23T20:27:43Z",
690 |       "path": "data/profitability-lab/regular-options-multi-leg-side-aware-pricing-capability/latest.json",
691 |       "report_id": "regular_options_multi_leg_side_aware_pricing_capability",
692 |       "required": false,
693 |       "status": "loaded"
694 |     },
695 |     "next_steps": {
696 |       "excerpt_chars": 8000,
697 |       "exists": true,
698 |       "path": "docs/NEXT_STEPS.md",
699 |       "status": "loaded"
700 |     },
701 |     "pmcc_diagonal_replay_readiness": {
702 |       "exists": true,
703 |       "generated_at_utc": "2026-06-23T21:50:44Z",
704 |       "path": "data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/latest.json",
705 |       "report_id": "regular_options_pmcc_diagonal_replay_readiness",
706 |       "required": false,
707 |       "status": "loaded",
708 |       "unsafe_flags": [],
709 |       "validated_status": "blocked_pmcc_diagonal_replay_readiness",
710 |       "validation_reason_codes": []
711 |     },
712 |     "point_in_time_dispersion_concentration_proxy": {
713 |       "exists": true,
714 |       "generated_at_utc": "2026-06-23T19:41:38Z",
715 |       "path": "data/profitability-lab/regular-options-point-in-time-dispersion-concentration-proxy/latest.json",
716 |       "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
717 |       "required": false,
718 |       "status": "loaded"
719 |     },
720 |     "point_in_time_flow_extreme_input": {
721 |       "exists": true,
722 |       "generated_at_utc": "2026-06-23T21:28:47Z",
723 |       "path": "data/profitability-lab/regular-options-point-in-time-flow-extreme-input/latest.json",
724 |       "report_id": "regular_options_point_in_time_flow_extreme_input",
725 |       "required": false,
726 |       "status": "loaded"
727 |     },
728 |     "point_in_time_vix_bucket": {
729 |       "exists": true,
730 |       "generated_at_utc": "2026-06-23T17:45:59Z",
731 |       "path": "data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json",
732 |       "report_id": "regular_options_point_in_time_vix_bucket",
733 |       "required": false,
734 |       "status": "loaded"
735 |     },
736 |     "preregistered_dispersion_proxy_hybrid_playbook": {
737 |       "exists": true,
738 |       "generated_at_utc": "2026-06-23T06:06:40Z",
739 |       "path": "data/profitability-lab/regular-options-preregistered-dispersion-proxy-hybrid-playbook/latest.json",
740 |       "report_id": "regular_options_preregistered_dispersion_proxy_hybrid_playbook",
741 |       "required": false,
742 |       "status": "loaded"
743 |     },
744 |     "preregistered_flow_extreme_ratio_backspread_playbook": {
745 |       "exists": true,
746 |       "generated_at_utc": "2026-06-23T05:51:48Z",
747 |       "path": "data/profitability-lab/regular-options-preregistered-flow-extreme-ratio-backspread-playbook/latest.json",
748 |       "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
749 |       "required": false,
750 |       "status": "loaded"
751 |     },
752 |     "preregistered_macro_event_long_strangle_playbook": {
753 |       "exists": true,
754 |       "generated_at_utc": "2026-06-23T05:28:10Z",
755 |       "path": "data/profitability-lab/regular-options-preregistered-macro-event-long-strangle-playbook/latest.json",
756 |       "report_id": "regular_options_preregistered_macro_event_long_strangle_playbook",
757 |       "required": false,
758 |       "status": "loaded"
759 |     },
760 |     "preregistered_playbook": {
761 |       "exists": true,
762 |       "generated_at_utc": "2026-06-22T14:35:35Z",
763 |       "path": "data/profitability-lab/regular-options-preregistered-momentum-continuation-playbook/latest.json",
764 |       "report_id": "regular_options_preregistered_momentum_continuation_playbook",
765 |       "required": false,
766 |       "status": "loaded"
767 |     },
768 |     "preregistered_pmcc_diagonal_playbook": {
769 |       "exists": true,
770 |       "generated_at_utc": "2026-06-23T06:22:04Z",
771 |       "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json",
772 |       "report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
773 |       "required": false,
774 |       "status": "loaded"
775 |     },
776 |     "preregistered_post_event_iv_crush_iron_condor_playbook": {
777 |       "exists": true,
778 |       "generated_at_utc": "2026-06-23T05:35:17Z",
779 |       "path": "data/profitability-lab/regular-options-preregistered-post-event-iv-crush-iron-condor-playbook/latest.json",
780 |       "report_id": "regular_options_preregistered_post_event_iv_crush_iron_condor_playbook",
781 |       "required": false,
782 |       "status": "loaded"
783 |     },
784 |     "preregistered_skew_broken_wing_playbook": {
785 |       "exists": true,
786 |       "generated_at_utc": "2026-06-23T05:14:53Z",
787 |       "path": "data/profitability-lab/regular-options-preregistered-skew-broken-wing-playbook/latest.json",
788 |       "report_id": "regular_options_preregistered_skew_broken_wing_playbook",
789 |       "required": false,
790 |       "status": "loaded"
791 |     },
792 |     "preregistered_term_structure_calendar_playbook": {
793 |       "exists": true,
794 |       "generated_at_utc": "2026-06-23T05:03:26Z",
795 |       "path": "data/profitability-lab/regular-options-preregistered-term-structure-calendar-playbook/latest.json",
796 |       "report_id": "regular_options_preregistered_term_structure_calendar_playbook",
797 |       "required": false,
798 |       "status": "loaded"
799 |     },
800 |     "preregistered_vrp_credit_spread_playbook": {
801 |       "exists": true,
802 |       "generated_at_utc": "2026-06-23T04:39:33Z",
803 |       "path": "data/profitability-lab/regular-options-preregistered-vrp-credit-spread-playbook/latest.json",
804 |       "report_id": "regular_options_preregistered_vrp_credit_spread_playbook",
805 |       "required": false,
806 |       "status": "loaded"
807 |     },
808 |     "project_context": {
809 |       "excerpt_chars": 8000,
810 |       "exists": true,
811 |       "path": "docs/PROJECT_CONTEXT.md",
812 |       "status": "loaded"
813 |     },
814 |     "term_structure_calendar_replay_readiness": {
815 |       "exists": true,
816 |       "generated_at_utc": "2026-06-23T05:03:27Z",
817 |       "path": "data/profitability-lab/regular-options-term-structure-calendar-replay-readiness/latest.json",
818 |       "report_id": "regular_options_term_structure_calendar_replay_readiness",
819 |       "required": false,
820 |       "status": "loaded"
821 |     },
822 |     "vrp_credit_spread_replay_readiness": {
823 |       "exists": true,
824 |       "generated_at_utc": "2026-06-23T04:39:49Z",
825 |       "path": "data/profitability-lab/regular-options-vrp-credit-spread-replay-readiness/latest.json",
826 |       "report_id": "regular_options_vrp_credit_spread_replay_readiness",
827 |       "required": false,
828 |       "status": "loaded"
829 |     }
830 |   },
831 |   "status": "ready_for_same_session_gpt55_guidance",
832 |   "stops_changed": false,
833 |   "strategy_logic_changed": false
834 | }
````

### File: data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/latest.json
Lines: 1-352
```json
  1 | {
  2 |   "accepted_profitability": false,
  3 |   "allowed_next_step": "Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.",
  4 |   "artifacts": {
  5 |     "docs_report": "docs/regular-options-pmcc-diagonal-replay-readiness.md",
  6 |     "json": "data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/20260623T215044Z.json",
  7 |     "latest_json": "data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/latest.json",
  8 |     "latest_markdown": "data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/latest.md",
  9 |     "markdown": "data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/20260623T215044Z.md"
 10 |   },
 11 |   "auto_track_enabled": false,
 12 |   "blockers": [
 13 |     "missing_point_in_time_trend_or_regime_inputs",
 14 |     "point_in_time_vix_bucket_blocked",
 15 |     "missing_trusted_pmcc_diagonal_quote_surface"
 16 |   ],
 17 |   "broker_order_allowed": false,
 18 |   "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
 19 |   "critical_prerequisites": [
 20 |     {
 21 |       "blocker": null,
 22 |       "critical": true,
 23 |       "evidence": [
 24 |         {
 25 |           "matched_terms": [
 26 |             "low_mid_vix_index_pmcc_diagonal_income_v1",
 27 |             "defined_risk_pmcc_style_call_diagonals_only"
 28 |           ],
 29 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
 30 |         }
 31 |       ],
 32 |       "label": "Valid preregistered PMCC playbook",
 33 |       "note": "The design artifact is loaded and validates separately before these checks run.",
 34 |       "prerequisite_id": "valid_preregistered_pmcc_playbook",
 35 |       "status": "ready"
 36 |     },
 37 |     {
 38 |       "blocker": "missing_point_in_time_trend_or_regime_inputs",
 39 |       "critical": true,
 40 |       "evidence": [
 41 |         {
 42 |           "matched_terms": [
 43 |             "trend"
 44 |           ],
 45 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
 46 |         },
 47 |         {
 48 |           "matched_terms": [],
 49 |           "path": "data/profitability-lab/regular-options-feature-store/latest.json"
 50 |         }
 51 |       ],
 52 |       "label": "Point-in-time trend or regime inputs",
 53 |       "note": "The preregistered PMCC design requires point-in-time trend/regime inputs, but the current feature store is quote-surface only.",
 54 |       "prerequisite_id": "point_in_time_trend_or_regime_inputs",
 55 |       "status": "blocked"
 56 |     },
 57 |     {
 58 |       "blocker": "point_in_time_vix_bucket_blocked",
 59 |       "critical": true,
 60 |       "evidence": [
 61 |         {
 62 |           "blockers": [
 63 |             "point_in_time_vix_source_missing",
 64 |             "missing_vix_bucket_threshold_policy",
 65 |             "vix_bucket_date_coverage_incomplete"
 66 |           ],
 67 |           "matched_terms": [
 68 |             "blocked_point_in_time_vix_source_missing"
 69 |           ],
 70 |           "path": "data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json"
 71 |         }
 72 |       ],
 73 |       "label": "Point-in-time VIX low/mid bucket",
 74 |       "note": "Existing VIX bucket artifact is loaded but blocked.",
 75 |       "prerequisite_id": "point_in_time_vix_bucket",
 76 |       "status": "blocked"
 77 |     },
 78 |     {
 79 |       "blocker": "missing_trusted_pmcc_diagonal_quote_surface",
 80 |       "critical": true,
 81 |       "evidence": [
 82 |         {
 83 |           "exists": true,
 84 |           "long_dte_call_row_count": 0,
 85 |           "path": "data/options-validation/options_history.db",
 86 |           "pmcc_diagonal_quote_surface_status": "blocked",
 87 |           "read_only_confirmed": true,
 88 |           "short_dte_call_row_count": 1364438,
 89 |           "status": "loaded",
 90 |           "trusted_call_quote_row_count": 1992676,
 91 |           "underlyings_with_trusted_calls": [
 92 |             "QQQ",
 93 |             "SPY"
 94 |           ]
 95 |         }
 96 |       ],
 97 |       "label": "Trusted OPRA/NBBO long-call and short-call quote surface",
 98 |       "note": "Read-only DB inspection checks trusted SPY/QQQ call rows in both long-DTE and short-DTE buckets.",
 99 |       "prerequisite_id": "trusted_pmcc_diagonal_quote_surface",
100 |       "status": "blocked"
101 |     },
102 |     {
103 |       "blocker": null,
104 |       "critical": true,
105 |       "evidence": [
106 |         {
107 |           "matched_terms": [
108 |             "entry_debit",
109 |             "roll_debit_or_credit",
110 |             "net_pnl_usd"
111 |           ],
112 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
113 |         }
114 |       ],
115 |       "label": "Side-aware diagonal entry, roll, exit, and expiry formulas",
116 |       "note": "This only proves formulas are preregistered; it does not run replay.",
117 |       "prerequisite_id": "side_aware_diagonal_formulas_registered",
118 |       "status": "ready"
119 |     },
120 |     {
121 |       "blocker": null,
122 |       "critical": true,
123 |       "evidence": [
124 |         {
125 |           "matched_terms": [
126 |             "assignment",
127 |             "ex-dividend",
128 |             "expiration",
129 |             "roll"
130 |           ],
131 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
132 |         }
133 |       ],
134 |       "label": "Short-call roll, assignment, ex-dividend, and expiration handling",
135 |       "note": "The current slice records readiness only; future replay still needs implementation.",
136 |       "prerequisite_id": "short_call_roll_assignment_ex_dividend_handling",
137 |       "status": "ready"
138 |     },
139 |     {
140 |       "blocker": null,
141 |       "critical": true,
142 |       "evidence": [
143 |         {
144 |           "matched_terms": [
145 |             "max_loss_usd",
146 |             "required collateral"
147 |           ],
148 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
149 |         }
150 |       ],
151 |       "label": "Max-loss and collateral convention",
152 |       "note": "Undefined or uncapped short-call exposure remains forbidden.",
153 |       "prerequisite_id": "max_loss_collateral_convention",
154 |       "status": "ready"
155 |     },
156 |     {
157 |       "blocker": null,
158 |       "critical": true,
159 |       "evidence": [
160 |         {
161 |           "matched_terms": [
162 |             "denominator_statuses"
163 |           ],
164 |           "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json"
165 |         }
166 |       ],
167 |       "label": "Full denominator status mapping",
168 |       "note": "Denominator registration is not replay or profitability proof.",
169 |       "prerequisite_id": "full_denominator_mapping",
170 |       "status": "ready"
171 |     },
172 |     {
173 |       "blocker": null,
174 |       "critical": true,
175 |       "evidence": [
176 |         {
177 |           "matched_terms": [
178 |             "base_clean_stack_identity_ledger_ready"
179 |           ],
180 |           "path": "data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json"
181 |         }
182 |       ],
183 |       "label": "Strict-new dedupe against the 157-row clean base stack",
184 |       "note": "Future PMCC rows must remain strict-new before count claims.",
185 |       "prerequisite_id": "strict_new_dedupe_against_base_clean_stack",
186 |       "status": "ready"
187 |     },
188 |     {
189 |       "blocker": null,
190 |       "critical": true,
191 |       "evidence": [
192 |         {
193 |           "matched_terms": [
194 |             "loaded"
195 |           ],
196 |           "path": "data/contracts/forward-holdout-contract.json"
197 |         }
198 |       ],
199 |       "label": "Protected-holdout guard",
200 |       "note": "This readiness slice does not consume protected holdout.",
201 |       "prerequisite_id": "protected_holdout_guard",
202 |       "status": "ready"
203 |     },
204 |     {
205 |       "blocker": null,
206 |       "critical": true,
207 |       "evidence": [
208 |         {
209 |           "matched_terms": [
210 |             "readiness is not replay",
211 |             "not profitability",
212 |             "not forward proof",
213 |             "not promotion"
214 |           ],
215 |           "path": "generated_report"
216 |         }
217 |       ],
218 |       "label": "Proof-boundary labeling",
219 |       "note": "The generated artifact carries fail-closed proof-boundary labels.",
220 |       "prerequisite_id": "proof_boundary_labeling",
221 |       "status": "ready"
222 |     }
223 |   ],
224 |   "evidence_stores_mutated": false,
225 |   "forbidden_actions": [
226 |     "do_not_implement_scanner_or_playbook_logic",
227 |     "do_not_run_pmcc_replay",
228 |     "do_not_create_trades",
229 |     "do_not_prepare_or_submit_broker_orders",
230 |     "do_not_enable_live_validation",
231 |     "do_not_enable_auto_track",
232 |     "do_not_import_quotes",
233 |     "do_not_mutate_options_history_db",
234 |     "do_not_mutate_evidence_stores",
235 |     "do_not_consume_protected_holdout",
236 |     "do_not_change_scanner_policy",
237 |     "do_not_change_strategy_logic",
238 |     "do_not_change_stops",
239 |     "do_not_change_sizing",
240 |     "do_not_lower_proof_bars",
241 |     "do_not_promote_any_lane",
242 |     "do_not_allow_naked_or_undefined_risk_short_calls",
243 |     "do_not_invent_point_in_time_trend_vix_or_known_at_inputs"
244 |   ],
245 |   "future_extension_universe": [
246 |     "IWM",
247 |     "DIA"
248 |   ],
249 |   "generated_at_utc": "2026-06-23T21:50:44Z",
250 |   "historical_replay_performed": false,
251 |   "historical_rows_are_forward_proof": false,
252 |   "holdout_contract_loaded": true,
253 |   "initial_research_universe": [
254 |     "SPY",
255 |     "QQQ"
256 |   ],
257 |   "lane_implementation_performed": false,
258 |   "live_validation_enabled": false,
259 |   "preregistration_validation": {
260 |     "reasons": [],
261 |     "required_concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
262 |     "required_report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
263 |     "required_status": "preregistered_design_only",
264 |     "required_structure": "defined_risk_pmcc_style_call_diagonals_only",
265 |     "undefined_or_uncapped_short_call_risk_allowed_required": false,
266 |     "valid": true
267 |   },
268 |   "production_scanner_changed": false,
269 |   "promotion_ready": false,
270 |   "proof_bars_changed": false,
271 |   "protected_holdout_consumed": false,
272 |   "quotes_imported": false,
273 |   "read_only": true,
274 |   "replay_performed": false,
275 |   "report_id": "regular_options_pmcc_diagonal_replay_readiness",
276 |   "research_only": true,
277 |   "scanner_policy_changed": false,
278 |   "scope": "read_only_pmcc_diagonal_replay_readiness_audit",
279 |   "sizing_changed": false,
280 |   "smallest_next_blocker_clearing_slice": "missing_point_in_time_trend_or_regime_inputs",
281 |   "source_artifacts": {
282 |     "base_clean_stack_identity_ledger": {
283 |       "error": null,
284 |       "exists": true,
285 |       "generated_at_utc": "2026-06-23T21:04:36Z",
286 |       "path": "data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json",
287 |       "report_id": "regular_options_base_clean_stack_identity_ledger",
288 |       "required": false,
289 |       "status": "loaded",
290 |       "status_value": "base_clean_stack_identity_ledger_ready"
291 |     },
292 |     "feature_store": {
293 |       "error": null,
294 |       "exists": true,
295 |       "generated_at_utc": "2026-06-18T06:09:35Z",
296 |       "path": "data/profitability-lab/regular-options-feature-store/latest.json",
297 |       "report_id": "regular_options_feature_store",
298 |       "required": true,
299 |       "status": "loaded",
300 |       "status_value": "feature_store_built"
301 |     },
302 |     "forward_holdout_contract": {
303 |       "error": null,
304 |       "exists": true,
305 |       "generated_at_utc": "2026-06-14",
306 |       "path": "data/contracts/forward-holdout-contract.json",
307 |       "report_id": "forward-holdout-contract",
308 |       "required": false,
309 |       "status": "loaded",
310 |       "status_value": "active"
311 |     },
312 |     "options_history_db": {
313 |       "exists": true,
314 |       "long_dte_call_row_count": 0,
315 |       "path": "data/options-validation/options_history.db",
316 |       "pmcc_diagonal_quote_surface_status": "blocked",
317 |       "read_only_confirmed": true,
318 |       "short_dte_call_row_count": 1364438,
319 |       "status": "loaded",
320 |       "trusted_call_quote_row_count": 1992676,
321 |       "underlyings_with_trusted_calls": [
322 |         "QQQ",
323 |         "SPY"
324 |       ]
325 |     },
326 |     "point_in_time_vix_bucket": {
327 |       "error": null,
328 |       "exists": true,
329 |       "generated_at_utc": "2026-06-23T17:45:59Z",
330 |       "path": "data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json",
331 |       "report_id": "regular_options_point_in_time_vix_bucket",
332 |       "required": false,
333 |       "status": "loaded",
334 |       "status_value": "blocked_point_in_time_vix_source_missing"
335 |     },
336 |     "preregistered_pmcc_diagonal_playbook": {
337 |       "error": null,
338 |       "exists": true,
339 |       "generated_at_utc": "2026-06-23T06:22:04Z",
340 |       "path": "data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json",
341 |       "report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
342 |       "required": true,
343 |       "status": "loaded",
344 |       "status_value": "preregistered_design_only"
345 |     }
346 |   },
347 |   "status": "blocked_pmcc_diagonal_replay_readiness",
348 |   "stops_changed": false,
349 |   "strategy_logic_changed": false,
350 |   "structure": "defined_risk_pmcc_style_call_diagonals_only",
351 |   "undefined_or_uncapped_short_call_risk_allowed": false
352 | }
```

### File: data/profitability-lab/regular-options-pmcc-diagonal-replay-readiness/latest.md
Lines: 1-65
```md
 1 | # Regular Options PMCC Diagonal Replay Readiness
 2 | 
 3 | This report is generated from `scripts/build_regular_options_pmcc_diagonal_replay_readiness.py`. It is a read-only readiness audit for a preregistered PMCC-style defined-risk call diagonal concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, prepare or submit broker orders, allow naked or undefined-risk short calls, or promote any lane.
 4 | 
 5 | ## Summary
 6 | 
 7 | - Status: `blocked_pmcc_diagonal_replay_readiness`.
 8 | - Concept: `low_mid_vix_index_pmcc_diagonal_income_v1`.
 9 | - Structure: `defined_risk_pmcc_style_call_diagonals_only`.
10 | - Accepted profitability: `false`.
11 | - Historical replay performed: `false`.
12 | - Replay performed: `false`.
13 | - Smallest next blocker-clearing slice: `missing_point_in_time_trend_or_regime_inputs`.
14 | 
15 | ## Preregistration Validation
16 | 
17 | - Valid: `true`.
18 | - Reasons: `[]`.
19 | 
20 | ## Critical Prerequisites
21 | 
22 | | Prerequisite | Status | Blocker | Evidence |
23 | | --- | --- | --- | --- |
24 | | Valid preregistered PMCC playbook | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
25 | | Point-in-time trend or regime inputs | `blocked` | `missing_point_in_time_trend_or_regime_inputs` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json`, `data/profitability-lab/regular-options-feature-store/latest.json` |
26 | | Point-in-time VIX low/mid bucket | `blocked` | `point_in_time_vix_bucket_blocked` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
27 | | Trusted OPRA/NBBO long-call and short-call quote surface | `blocked` | `missing_trusted_pmcc_diagonal_quote_surface` | `data/options-validation/options_history.db` |
28 | | Side-aware diagonal entry, roll, exit, and expiry formulas | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
29 | | Short-call roll, assignment, ex-dividend, and expiration handling | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
30 | | Max-loss and collateral convention | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
31 | | Full denominator status mapping | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
32 | | Strict-new dedupe against the 157-row clean base stack | `ready` | `None` | `data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json` |
33 | | Protected-holdout guard | `ready` | `None` | `data/contracts/forward-holdout-contract.json` |
34 | | Proof-boundary labeling | `ready` | `None` | `generated_report` |
35 | 
36 | ## Blockers
37 | 
38 | - `missing_point_in_time_trend_or_regime_inputs`
39 | - `point_in_time_vix_bucket_blocked`
40 | - `missing_trusted_pmcc_diagonal_quote_surface`
41 | 
42 | ## Boundary
43 | 
44 | Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.
45 | 
46 | ## Forbidden Actions
47 | 
48 | - `do_not_implement_scanner_or_playbook_logic`
49 | - `do_not_run_pmcc_replay`
50 | - `do_not_create_trades`
51 | - `do_not_prepare_or_submit_broker_orders`
52 | - `do_not_enable_live_validation`
53 | - `do_not_enable_auto_track`
54 | - `do_not_import_quotes`
55 | - `do_not_mutate_options_history_db`
56 | - `do_not_mutate_evidence_stores`
57 | - `do_not_consume_protected_holdout`
58 | - `do_not_change_scanner_policy`
59 | - `do_not_change_strategy_logic`
60 | - `do_not_change_stops`
61 | - `do_not_change_sizing`
62 | - `do_not_lower_proof_bars`
63 | - `do_not_promote_any_lane`
64 | - `do_not_allow_naked_or_undefined_risk_short_calls`
65 | - `do_not_invent_point_in_time_trend_vix_or_known_at_inputs`
```

### File: docs/regular-options-pmcc-diagonal-replay-readiness.md
Lines: 1-65
```md
 1 | # Regular Options PMCC Diagonal Replay Readiness
 2 | 
 3 | This report is generated from `scripts/build_regular_options_pmcc_diagonal_replay_readiness.py`. It is a read-only readiness audit for a preregistered PMCC-style defined-risk call diagonal concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, prepare or submit broker orders, allow naked or undefined-risk short calls, or promote any lane.
 4 | 
 5 | ## Summary
 6 | 
 7 | - Status: `blocked_pmcc_diagonal_replay_readiness`.
 8 | - Concept: `low_mid_vix_index_pmcc_diagonal_income_v1`.
 9 | - Structure: `defined_risk_pmcc_style_call_diagonals_only`.
10 | - Accepted profitability: `false`.
11 | - Historical replay performed: `false`.
12 | - Replay performed: `false`.
13 | - Smallest next blocker-clearing slice: `missing_point_in_time_trend_or_regime_inputs`.
14 | 
15 | ## Preregistration Validation
16 | 
17 | - Valid: `true`.
18 | - Reasons: `[]`.
19 | 
20 | ## Critical Prerequisites
21 | 
22 | | Prerequisite | Status | Blocker | Evidence |
23 | | --- | --- | --- | --- |
24 | | Valid preregistered PMCC playbook | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
25 | | Point-in-time trend or regime inputs | `blocked` | `missing_point_in_time_trend_or_regime_inputs` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json`, `data/profitability-lab/regular-options-feature-store/latest.json` |
26 | | Point-in-time VIX low/mid bucket | `blocked` | `point_in_time_vix_bucket_blocked` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
27 | | Trusted OPRA/NBBO long-call and short-call quote surface | `blocked` | `missing_trusted_pmcc_diagonal_quote_surface` | `data/options-validation/options_history.db` |
28 | | Side-aware diagonal entry, roll, exit, and expiry formulas | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
29 | | Short-call roll, assignment, ex-dividend, and expiration handling | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
30 | | Max-loss and collateral convention | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
31 | | Full denominator status mapping | `ready` | `None` | `data/profitability-lab/regular-options-preregistered-pmcc-diagonal-playbook/latest.json` |
32 | | Strict-new dedupe against the 157-row clean base stack | `ready` | `None` | `data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json` |
33 | | Protected-holdout guard | `ready` | `None` | `data/contracts/forward-holdout-contract.json` |
34 | | Proof-boundary labeling | `ready` | `None` | `generated_report` |
35 | 
36 | ## Blockers
37 | 
38 | - `missing_point_in_time_trend_or_regime_inputs`
39 | - `point_in_time_vix_bucket_blocked`
40 | - `missing_trusted_pmcc_diagonal_quote_surface`
41 | 
42 | ## Boundary
43 | 
44 | Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if blocked, park PMCC on the exact blockers and select the next materially different branch.
45 | 
46 | ## Forbidden Actions
47 | 
48 | - `do_not_implement_scanner_or_playbook_logic`
49 | - `do_not_run_pmcc_replay`
50 | - `do_not_create_trades`
51 | - `do_not_prepare_or_submit_broker_orders`
52 | - `do_not_enable_live_validation`
53 | - `do_not_enable_auto_track`
54 | - `do_not_import_quotes`
55 | - `do_not_mutate_options_history_db`
56 | - `do_not_mutate_evidence_stores`
57 | - `do_not_consume_protected_holdout`
58 | - `do_not_change_scanner_policy`
59 | - `do_not_change_strategy_logic`
60 | - `do_not_change_stops`
61 | - `do_not_change_sizing`
62 | - `do_not_lower_proof_bars`
63 | - `do_not_promote_any_lane`
64 | - `do_not_allow_naked_or_undefined_risk_short_calls`
65 | - `do_not_invent_point_in_time_trend_vix_or_known_at_inputs`
```
