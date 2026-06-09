from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_profitability_layer_stack as layer_stack


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _fixture_paths(root: Path) -> dict[str, Path]:
    return {key: root / f"{key}.json" for key in layer_stack.DEFAULT_ARTIFACT_PATHS}


def _write_minimal_artifacts(paths: dict[str, Path]) -> None:
    _write_json(
        paths["candidate_ledger"],
        {
            "summary": {
                "operating_status": "ledger_live_entry_blocked_collect_evidence",
                "ledger_row_count": 8,
                "exact_realized_pnl_count": 0,
                "open_risk_live_entry_allowed": False,
                "action_counts": {
                    "create_or_link_paper_review_row": 2,
                    "collect_exact_exit_evidence": 1,
                },
            },
            "next_evidence_queue": [{"next_evidence_action": "resolve_open_risk_governor"}],
        },
    )
    _write_json(
        paths["fresh_evidence_loop"],
        {
            "summary": {
                "candidate_count": 4,
                "exact_realized_pnl_count": 0,
                "paper_probation_bridge_count": 1,
                "exact_exit_bridge_count": 1,
            }
        },
    )
    _write_json(paths["paper_shortlist"], {"summary": {"eligible_count": 0}})
    _write_json(
        paths["profit_capture_queue"],
        {
            "summary": {
                "queue_rows": 3,
                "tier_a_fresh_match_bridge_count": 0,
                "selection_readiness_counts": {"paper_review_candidate": 1},
            }
        },
    )
    _write_json(
        paths["repair_burndown"],
        {
            "summary": {
                "active_unattempted_exact_target_count": 1,
                "source_replay_required_target_count": 1,
                "diagnostic_lookahead_target_count": 2,
                "exhausted_target_count": 3,
            }
        },
    )
    _write_json(paths["repair_attempts"], {"summary": {"latest_attempt_count": 4}})
    _write_json(
        paths["open_risk"],
        {
            "open_risk_governor": {
                "status": "open_risk_governor_blocked",
                "live_entry_allowed": False,
                "blockers": ["live_exact_negative_open_risk"],
                "live_exact_negative_ids": [537],
            }
        },
    )
    _write_json(paths["suggested_close_risk"], {"attention_trade_ids": [138]})
    _write_json(
        paths["volatility_probation"],
        {
            "summary": {
                "lane_promotion_state": "paper_probation",
                "lane_blockers": ["fresh_paper_cohort_insufficient"],
                "current_paper_probation_exact_evidence_pending_count": 1,
                "promotion_discussion_ready_excluding_legacy_count": 0,
            }
        },
    )
    _write_json(
        paths["lane_promotion_state"],
        {
            "summary": {
                "lane_count": 14,
                "diagnostic_lane_count": 13,
                "paper_probation_lane_count": 1,
                "live_validation_lane_count": 0,
                "open_risk_governor_status": "open_risk_governor_blocked",
            }
        },
    )
    _write_json(
        paths["current_policy_circuit_breaker"],
        {
            "summary": {
                "overall_status": "paper_only_recent_week_break",
                "recovery_gate_failures": ["trusted_exact_realized_pnl_rows"],
            }
        },
    )
    _write_json(paths["missed_picks_outcome"], {"summary": {"raw_row_count": 2}})
    _write_json(paths["missed_picks_failure_modes"], {"data_quality": {"status": "clean_for_failure_analysis"}})
    _write_json(
        paths["missed_picks_filter_matrix"],
        {"summary": {"priced_untracked_rows": 2, "source_mark_unpriced_count": 0}},
    )
    _write_json(
        paths["overfit_rule_archive"],
        {
            "summary": {
                "overall_status": "overfit_rules_archived",
                "archived_reject_overfit_rule_count": 2,
                "unarchived_reject_overfit_rule_count": 0,
            }
        },
    )
    _write_json(paths["entry_filter_walkforward"], {"decision_summary": {"status": "mixed_walkforward_watch_not_promoted"}})
    _write_json(paths["entry_filter_point_in_time"], {"decision_summary": {"status": "paper_only_collecting"}})
    _write_json(paths["entry_filter_paper_monitor"], {"gate": {"status": "collecting"}})
    _write_json(paths["current_policy_stop_grid"], {"baseline": {"rows": 10}})
    _write_json(
        paths["minute_exit_replay_readiness"],
        {
            "status": "minute_exit_replay_readiness_readback",
            "summary": {
                "overall_status": "blocked_ready_seed_missing_minute_engine",
                "entry_seed_ready_count": 2,
                "position_seed_ready_count": 1,
                "true_minute_exit_pnl_count": 0,
                "blockers": [
                    "minute_level_exit_replay_engine_missing",
                    "minute_opra_nbbo_quote_coverage_missing",
                    "daily_stop_grid_is_not_minute_level_proof",
                ],
            },
        },
    )
    _write_json(
        paths["execution_alternative_replay_readiness"],
        {
            "status": "execution_alternative_replay_readiness_readback",
            "summary": {
                "overall_status": "blocked_ready_seed_missing_execution_alternative_replay_engine",
                "candidate_shown_count": 1,
                "top_alternative_logged_row_count": 1,
                "replacement_alternative_logged_row_count": 1,
                "top_spread_replay_seed_count": 1,
                "contract_replacement_seed_count": 1,
                "true_top_spread_replay_pnl_count": 0,
                "true_contract_replacement_pnl_count": 0,
                "liquidity_first_replay_engine_status": "missing",
                "contract_replacement_replay_engine_status": "missing",
                "alternative_exit_quote_coverage_status": "missing",
                "blockers": [
                    "contract_replacement_exit_survivability_replay_engine_missing",
                    "top_spread_liquidity_first_replay_engine_missing",
                    "alternate_contract_exit_quote_coverage_missing",
                    "true_alternative_replay_pnl_rows_missing",
                ],
            },
        },
    )
    _write_json(
        paths["execution_alternative_replay_coverage"],
        {
            "status": "execution_alternative_replay_coverage_readback",
            "summary": {
                "overall_status": "blocked_partial_quote_coverage_no_true_replay_pnl",
                "top_spread_candidate_count": 1,
                "contract_replacement_candidate_count": 1,
                "top_spread_entry_quote_coverage_status": "partial",
                "top_spread_exit_quote_coverage_status": "missing",
                "contract_replacement_entry_quote_coverage_status": "partial",
                "contract_replacement_exit_quote_coverage_status": "missing",
                "alternative_exit_quote_coverage_status": "missing",
                "true_top_spread_replay_pnl_count": 0,
                "true_contract_replacement_pnl_count": 0,
                "liquidity_first_replay_engine_status": "read_only_side_aware_engine_waiting_for_quote_coverage",
                "contract_replacement_replay_engine_status": "read_only_side_aware_engine_waiting_for_quote_coverage",
                "quote_demand_manifest_status": "ready_for_import_or_query",
                "missing_quote_demand_count": 4,
                "missing_entry_quote_demand_count": 2,
                "missing_exit_quote_demand_count": 2,
                "quote_demand_usage_counts": {
                    "top_spread:entry_long": 1,
                    "top_spread:exit_short": 1,
                    "contract_replacement:entry_long": 1,
                    "contract_replacement:exit_short": 1,
                },
                "blockers": [
                    "alternate_contract_exit_quote_coverage_missing",
                    "true_top_spread_replay_pnl_rows_missing",
                    "true_contract_replacement_pnl_rows_missing",
                ],
            },
        },
    )
    _write_json(
        paths["structure_specific_harness"],
        {
            "status": "structure_specific_harness_built_collecting",
            "summary": {
                "overall_status": "structure_specific_harness_built_collecting",
                "candidate_shown_count": 1,
                "structure_bucket_counts": {
                    "vertical_spread": 1,
                    "single_leg": 0,
                    "multi_leg_other": 0,
                    "unknown": 0,
                },
                "strategy_type_counts": {"vertical_spread": 1},
                "proof_live_exact_entry_count": 1,
                "paper_fill_recorded_count": 1,
                "true_structure_specific_pnl_count": 0,
                "harness_row_count": 1,
                "blockers": [
                    "single_leg_or_other_multileg_samples_missing",
                    "true_structure_specific_pnl_rows_missing",
                ],
                "live_policy_change": False,
            },
        },
    )
    _write_json(
        paths["event_data_spine"],
        {
            "status": "event_data_spine_built_collecting",
            "summary": {
                "overall_status": "event_data_spine_built_collecting",
                "candidate_shown_count": 1,
                "event_annotation_count": 0,
                "missing_event_annotation_count": 1,
                "unique_ticker_count": 1,
                "proof_live_exact_entry_count": 1,
                "paper_fill_recorded_count": 1,
                "true_event_replay_pnl_count": 0,
                "post_event_vol_crush_replay_pnl_count": 0,
                "event_annotation_field_counts": {},
                "blockers": [
                    "event_calendar_annotations_missing",
                    "post_event_vol_crush_replay_rows_missing",
                    "true_event_executable_pnl_rows_missing",
                ],
                "live_policy_change": False,
            },
        },
    )
    _write_json(
        paths["risk_budget_sizing_replay"],
        {
            "status": "risk_budget_sizing_replay_readback",
            "summary": {
                "overall_status": "sizing_replay_built_open_risk_blocked",
                "source_row_count": 206,
                "baseline_net_pnl_usd": -16314.0,
                "best_research_scenario_id": "tiered_shadow_full_retest_quarter",
                "best_research_net_pnl_usd": 355.19,
                "best_research_profit_factor": 1.16,
                "positive_research_scenario_count": 2,
                "live_entry_allowed": False,
                "blockers": [
                    "open_risk_governor_blocks_sizing",
                    "fresh_exact_realized_sizing_evidence_required",
                ],
            },
        },
    )
    _write_json(
        paths["multilane_portfolio"],
        {
            "quality_gate": {
                "overall_status": "quality_pending",
                "blockers": ["paper_shadow_fill_evidence_pending"],
            },
            "combined_portfolio": {"exact_trades": 234},
            "lane_status_counts": {"quality_pending": 1},
        },
    )
    _write_json(paths["symbol_sleeves"], {"classification_counts": {"keep": 1}})
    _write_json(paths["guardrail_starvation"], {"overall": {"status": "guardrail_starvation_detected"}})


class RegularOptionsProfitabilityLayerStackTests(unittest.TestCase):
    def test_all_20_layers_are_wired_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _fixture_paths(root)
            _write_minimal_artifacts(paths)
            fills = root / "fills.jsonl"
            fills.write_text(
                json.dumps(
                    {
                        "event_type": "candidate_shown",
                        "strategy_type": "vertical_spread",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_status": "auto_tracked",
                        "fill_outcome": "paper_fill_recorded",
                        "auto_track_position_id": 537,
                        "selected_spread": {"ticker": "QQQ"},
                        "top_alternatives": [{"rank": 1}],
                        "fill_discipline_snapshot": {"fill_degradation_vs_mid_pct": 5.4},
                    }
                )
                + "\n",
                encoding="utf8",
            )

            report = layer_stack.build_report(
                artifact_paths=paths,
                fill_attempt_file=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["summary"]["layer_count"], 20)
        self.assertEqual(report["summary"]["wired_layer_count"], 20)
        self.assertEqual(report["summary"]["overall_status"], "all_20_layers_wired_live_blocked_collect_evidence")
        self.assertFalse(report["summary"]["live_policy_change"])
        by_slug = {layer["slug"]: layer for layer in report["layers"]}
        self.assertEqual(set(by_slug), {str(layer["slug"]) for layer in layer_stack.LAYER_BLUEPRINTS})
        self.assertEqual(by_slug["candidate_outcome_ledger"]["gate_status"], "blocked")
        self.assertEqual(by_slug["paper_only_fill_attempt_logging"]["gate_status"], "ready")
        self.assertEqual(by_slug["top_spread_alternative_replay"]["implementation_status"], "built_replay_coverage_blocked")
        self.assertEqual(by_slug["top_spread_alternative_replay"]["metrics"]["top_spread_replay_seed_count"], 1)
        self.assertEqual(by_slug["top_spread_alternative_replay"]["metrics"]["quote_demand_manifest_status"], "ready_for_import_or_query")
        self.assertEqual(by_slug["top_spread_alternative_replay"]["metrics"]["missing_quote_demand_count"], 4)
        self.assertEqual(by_slug["contract_replacement_exit_survivability"]["implementation_status"], "built_replay_coverage_blocked")
        self.assertEqual(by_slug["contract_replacement_exit_survivability"]["metrics"]["contract_replacement_seed_count"], 1)
        self.assertEqual(by_slug["contract_replacement_exit_survivability"]["metrics"]["missing_exit_quote_demand_count"], 2)
        self.assertEqual(by_slug["minute_level_exit_quote_deterioration"]["implementation_status"], "built_readiness_blocked")
        self.assertIn("true_minute_exit_pnl_rows_missing", by_slug["minute_level_exit_quote_deterioration"]["primary_blockers"])
        self.assertEqual(by_slug["anti_overfit_controls"]["metrics"]["archived_reject_overfit_rule_count"], 2)
        self.assertNotIn("rejected_overfit_rules_unarchived", by_slug["anti_overfit_controls"]["primary_blockers"])
        self.assertEqual(by_slug["portfolio_throttle_replay"]["gate_status"], "blocked")
        self.assertEqual(by_slug["risk_budget_sizing_replay"]["implementation_status"], "built_collecting")
        self.assertEqual(by_slug["risk_budget_sizing_replay"]["gate_status"], "collecting")
        self.assertEqual(by_slug["risk_budget_sizing_replay"]["metrics"]["best_research_scenario_id"], "tiered_shadow_full_retest_quarter")
        self.assertEqual(by_slug["structure_specific_multileg_harness"]["implementation_status"], "built_collecting")
        self.assertEqual(by_slug["structure_specific_multileg_harness"]["gate_status"], "collecting")
        self.assertEqual(
            by_slug["structure_specific_multileg_harness"]["metrics"]["true_structure_specific_pnl_count"],
            0,
        )
        self.assertNotIn(
            "multi_leg_structure_harness_missing",
            by_slug["structure_specific_multileg_harness"]["primary_blockers"],
        )
        self.assertEqual(by_slug["event_data_spine_post_event_vol_crush"]["implementation_status"], "built_collecting")
        self.assertEqual(by_slug["event_data_spine_post_event_vol_crush"]["gate_status"], "collecting")
        self.assertEqual(
            by_slug["event_data_spine_post_event_vol_crush"]["metrics"]["post_event_vol_crush_replay_pnl_count"],
            0,
        )
        self.assertNotIn(
            "event_data_spine_missing",
            by_slug["event_data_spine_post_event_vol_crush"]["primary_blockers"],
        )

    def test_structure_harness_missing_fails_closed_as_replay_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _fixture_paths(root)
            _write_minimal_artifacts(paths)
            paths["structure_specific_harness"].unlink()
            fills = root / "fills.jsonl"
            fills.write_text(
                json.dumps(
                    {
                        "event_type": "candidate_shown",
                        "strategy_type": "vertical_spread",
                        "selected_spread": {"ticker": "QQQ"},
                    }
                )
                + "\n",
                encoding="utf8",
            )

            report = layer_stack.build_report(
                artifact_paths=paths,
                fill_attempt_file=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        by_slug = {layer["slug"]: layer for layer in report["layers"]}
        self.assertEqual(by_slug["structure_specific_multileg_harness"]["implementation_status"], "wired_replay_gap")
        self.assertEqual(by_slug["structure_specific_multileg_harness"]["gate_status"], "blocked")
        self.assertIn(
            "multi_leg_structure_harness_missing",
            by_slug["structure_specific_multileg_harness"]["primary_blockers"],
        )

    def test_event_data_spine_missing_fails_closed_as_data_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _fixture_paths(root)
            _write_minimal_artifacts(paths)
            paths["event_data_spine"].unlink()
            fills = root / "fills.jsonl"
            fills.write_text(
                json.dumps(
                    {
                        "event_type": "candidate_shown",
                        "strategy_type": "vertical_spread",
                        "selected_spread": {"ticker": "QQQ"},
                    }
                )
                + "\n",
                encoding="utf8",
            )

            report = layer_stack.build_report(
                artifact_paths=paths,
                fill_attempt_file=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        by_slug = {layer["slug"]: layer for layer in report["layers"]}
        self.assertEqual(by_slug["event_data_spine_post_event_vol_crush"]["implementation_status"], "wired_data_gap")
        self.assertEqual(by_slug["event_data_spine_post_event_vol_crush"]["gate_status"], "blocked")
        self.assertIn(
            "event_data_spine_missing",
            by_slug["event_data_spine_post_event_vol_crush"]["primary_blockers"],
        )

    def test_missing_candidate_ledger_is_visible_not_silent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _fixture_paths(root)
            _write_minimal_artifacts(paths)
            paths["candidate_ledger"].unlink()
            fills = root / "fills.jsonl"
            fills.write_text("", encoding="utf8")

            report = layer_stack.build_report(
                artifact_paths=paths,
                fill_attempt_file=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        layer_1 = report["layers"][0]
        self.assertEqual(layer_1["slug"], "candidate_outcome_ledger")
        self.assertEqual(layer_1["implementation_status"], "wired_missing_input")
        self.assertEqual(layer_1["gate_status"], "blocked")

    def test_markdown_renders_all_layer_table_and_boundary(self):
        report = {
            "status": "profitability_layer_stack_readback",
            "summary": {
                "overall_status": "all_20_layers_wired_live_blocked_collect_evidence",
                "wired_layer_count": 20,
                "expected_layer_count": 20,
                "blocked_or_collecting_layer_count": 1,
                "gate_status_counts": {"blocked": 1},
                "implementation_status_counts": {"built": 1},
                "candidate_ledger_status": "ledger_live_entry_blocked_collect_evidence",
                "open_risk_status": "open_risk_governor_blocked",
                "live_policy_change": False,
            },
            "layers": [
                {
                    "layer": 20,
                    "title": "Event data spine / post-event vol crush",
                    "implementation_status": "wired_data_gap",
                    "gate_status": "blocked",
                    "primary_blockers": ["event_data_spine_missing"],
                    "next_action": "Build event annotations.",
                }
            ],
        }

        markdown = layer_stack.render_markdown(report)

        self.assertIn("# Regular Options Profitability Layer Stack", markdown)
        self.assertIn("| `20` |", markdown)
        self.assertIn("Event data spine / post-event vol crush", markdown)
        self.assertIn("does not create trades", markdown)


if __name__ == "__main__":
    unittest.main()
