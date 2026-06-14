from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_monthly_all_lanes_profitability_audit as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _failure_modes() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "data_quality": {"data_status": "clean_for_failure_analysis"},
        "overall_read": {"status": "data_clean_strategy_unprofitable"},
        "lane_decisions": [
            {
                "playbook": "short_term",
                "decision": "diagnostic_only_until_earn_back",
                "blockers": ["profit_factor_below_lane_gate"],
            },
            {
                "playbook": "volatility_expansion_observation",
                "decision": "probation_candidate_flow_with_self_guardrails",
                "blockers": [],
            },
        ],
        "failure_modes": {
            "by_playbook": [
                {
                    "key": "short_term",
                    "rows": 54,
                    "priced": 54,
                    "profit_factor": 0.28,
                    "avg_net_pnl_pct": -18.93,
                    "median_net_pnl_pct": -16.91,
                    "win_rate_pct": 33.3,
                    "sum_net_pnl_usd": -3518.15,
                    "winner_count": 18,
                    "loser_count": 36,
                },
                {
                    "key": "volatility_expansion_observation",
                    "rows": 24,
                    "priced": 24,
                    "profit_factor": 1.72,
                    "avg_net_pnl_pct": 6.75,
                    "median_net_pnl_pct": 2.15,
                    "win_rate_pct": 50.0,
                    "sum_net_pnl_usd": 972.3,
                    "winner_count": 12,
                    "loser_count": 12,
                },
            ],
            "worst_ticker_clusters": [
                {
                    "key": "XLK",
                    "rows": 31,
                    "profit_factor": 0.02,
                    "avg_net_pnl_pct": -37.43,
                    "sum_net_pnl_usd": -6099.6,
                }
            ],
            "debit_pct_bucket_metrics": [{"key": "gte45", "rows": 37, "profit_factor": 0.01}],
            "entry_debit_bucket_metrics": [{"key": "2_4", "rows": 56, "profit_factor": 0.13}],
            "dte_bucket_metrics": [
                {
                    "key": "gte36",
                    "rows": 19,
                    "profit_factor": 0.2,
                    "avg_net_pnl_pct": -13.88,
                    "sum_net_pnl_usd": -420.0,
                }
            ],
            "duplicate_exact_spread_groups": [],
        },
    }


def _filter_matrix() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "baseline_metrics": {"rows": 206, "profit_factor": 0.34, "avg_net_pnl_pct": -15.28},
        "summary": {"source_mark_unpriced_count": 0},
        "scenarios": [
            {
                "scenario_id": "high_pf_tiny_many_lost_winners",
                "status": "active_safety_gate_paper_probation",
                "entry_time_only": True,
                "kept_count": 10,
                "blocked_count": 196,
                "kept_metrics": {"profit_factor": 84.9, "avg_net_pnl_pct": 34.87, "unpriced": 0},
                "lost_winner_count": 61,
                "avoided_deep_loss_count_lte_minus_50": 37,
                "later_date_read": {"later_date_rows": 2, "survives_later_date_split": True},
            },
            {
                "scenario_id": "clean_entry_time_holdout_candidate",
                "status": "paper_shadow_candidate",
                "entry_time_only": True,
                "kept_count": 20,
                "blocked_count": 50,
                "kept_metrics": {"profit_factor": 1.8, "avg_net_pnl_pct": 8.5, "unpriced": 0},
                "lost_winner_count": 0,
                "avoided_deep_loss_count_lte_minus_50": 5,
                "later_date_read": {"later_date_rows": 12, "survives_later_date_split": True},
            },
            {
                "scenario_id": "non_entry_time_rule",
                "status": "research_candidate",
                "entry_time_only": False,
                "kept_count": 40,
                "blocked_count": 20,
                "kept_metrics": {"profit_factor": 2.0, "avg_net_pnl_pct": 12.0, "unpriced": 0},
                "lost_winner_count": 0,
                "avoided_deep_loss_count_lte_minus_50": 4,
                "later_date_read": {"later_date_rows": 20, "survives_later_date_split": True},
            },
        ],
    }


def _cohort_health() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "summary": {
            "overall_status": "paper_only_recent_week_break",
            "showcase_month": "2026-04",
            "showcase_month_summary": {"health_status": "healthy"},
            "recent_month": "2026-05",
            "recent_month_summary": {
                "health_status": "paper_only_recent_break",
                "priced": 42,
                "avg_pnl_pct": 7.49,
                "median_pnl_pct": -4.6,
                "negative_rate_priced_pct": 54.8,
            },
            "recent_week": "2026-W21",
            "recent_week_summary": {"health_status": "paper_only_recent_break"},
        },
        "monthly": {
            "2026-04": {
                "priced": 70,
                "avg_pnl_pct": 81.17,
                "median_pnl_pct": 71.82,
                "negative_rate_priced_pct": 8.6,
                "health_status": "healthy",
            },
            "2026-05": {
                "priced": 42,
                "avg_pnl_pct": 7.49,
                "median_pnl_pct": -4.6,
                "negative_rate_priced_pct": 54.8,
                "health_status": "paper_only_recent_break",
            },
        },
        "lane_monthly": {
            "2026-05:short_term": {
                "priced": 17,
                "avg_pnl_pct": -12.3,
                "median_pnl_pct": -55.41,
                "negative_rate_priced_pct": 70.6,
                "health_status": "paper_only_recent_break",
            }
        },
        "ticker_monthly": {
            "2026-05:DIS": {
                "priced": 1,
                "avg_pnl_pct": -99.54,
                "median_pnl_pct": -99.54,
                "negative_rate_priced_pct": 100.0,
                "health_status": "paper_only_thin_severe",
            }
        },
        "recommended_actions": [{"action": "keep_recent_lanes_paper_only"}],
    }


def _layer_stack() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "summary": {
            "overall_status": "all_20_layers_wired_live_blocked_collect_evidence",
            "blocked_or_collecting_layer_count": 6,
            "live_policy_change": False,
        },
        "layers": [
            {
                "slug": "top_spread_alternative_replay",
                "gate_status": "blocked",
                "implementation_status": "wired_replay_gap",
                "primary_blockers": ["liquidity_first_v2_replay_not_promoted"],
                "next_action": "Build top-spread replay.",
            },
            {
                "slug": "contract_replacement_exit_survivability",
                "gate_status": "blocked",
                "implementation_status": "wired_replay_gap",
                "primary_blockers": ["contract_replacement_exit_survivability_replay_missing"],
                "next_action": "Build contract replacement replay.",
            },
            {
                "slug": "minute_level_exit_quote_deterioration",
                "gate_status": "blocked",
                "implementation_status": "built_readiness_blocked",
                "primary_blockers": ["minute_level_exit_replay_engine_missing"],
                "metrics": {
                    "minute_readiness_overall_status": "blocked_ready_seed_missing_minute_engine",
                    "entry_seed_ready_count": 2,
                    "position_seed_ready_count": 1,
                    "true_minute_exit_pnl_count": 0,
                },
                "next_action": "Build minute-level exit replay.",
            },
            {
                "slug": "structure_specific_multileg_harness",
                "gate_status": "blocked",
                "implementation_status": "wired_replay_gap",
                "primary_blockers": ["multi_leg_structure_harness_missing"],
                "next_action": "Build structure harness.",
            },
            {
                "slug": "portfolio_throttle_replay",
                "gate_status": "blocked",
                "implementation_status": "built_blocked",
                "primary_blockers": ["portfolio_throttle_replay_blocked"],
                "next_action": "Keep portfolio throttle blocked.",
            },
            {
                "slug": "risk_budget_sizing_replay",
                "gate_status": "blocked",
                "implementation_status": "wired_replay_gap",
                "primary_blockers": ["risk_budget_sizing_replay_missing"],
                "next_action": "Build sizing replay.",
            },
            {
                "slug": "event_data_spine_post_event_vol_crush",
                "gate_status": "blocked",
                "implementation_status": "wired_data_gap",
                "primary_blockers": ["event_data_spine_missing"],
                "next_action": "Build event data spine.",
            },
        ],
    }


def _payload_for_key(key: str) -> dict:
    common = {"generated_at_utc": "2026-06-06T00:00:00Z", "live_policy_change": False}
    if key == "missed_picks_failure_modes":
        return _failure_modes()
    if key == "missed_picks_filter_matrix":
        return _filter_matrix()
    if key == "current_policy_cohort_health":
        return _cohort_health()
    if key == "current_policy_circuit_breaker":
        return {
            **common,
            "summary": {
                "breaker_active": True,
                "overall_status": "paper_only_recent_week_break",
                "recovery_gate_failures": ["point_in_time_replay_pass", "paper_monitor_pass"],
            },
        }
    if key == "entry_filter_walkforward":
        return {**common, "decision_summary": {"status": "mixed_walkforward_watch_not_promoted"}}
    if key == "entry_filter_point_in_time":
        return {**common, "decision_summary": {"status": "paper_only_collecting"}}
    if key == "entry_filter_paper_monitor":
        return {**common, "summary": {"status": "collecting", "live_policy_change": False}}
    if key == "candidate_ledger":
        return {
            **common,
            "summary": {
                "exact_realized_pnl_count": 0,
                "paper_probation_bridge_count": 8,
                "open_risk_live_entry_allowed": False,
            },
            "next_evidence_queue": [
                {
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "action_priority": 2,
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                }
            ],
        }
    if key == "profitability_layer_stack":
        return _layer_stack()
    if key == "open_risk":
        return {
            **common,
            "open_risk_governor": {
                "status": "open_risk_governor_blocked",
                "live_entry_allowed": False,
                "live_exact_negative_ids": [537],
                "blockers": ["live_exact_negative_open_risk"],
            },
        }
    if key == "multilane_portfolio":
        return {
            **common,
            "quality_gate": {
                "overall_status": "quality_pending",
                "blockers": [
                    "lane_a:conservative_zero_bid_pf_0.85_below_1_3",
                    "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5",
                ],
            },
        }
    if key == "lane_promotion_state":
        return {
            **common,
            "summary": {
                "live_validation_lane_count": 0,
                "paper_probation_lane_count": 1,
                "diagnostic_lane_count": 13,
                "open_risk_governor_status": "open_risk_governor_blocked",
            },
        }
    return common


class MonthlyAllLanesProfitabilityAuditTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[dict[str, Path], Path]:
        paths: dict[str, Path] = {}
        for key in audit.DEFAULT_ARTIFACT_PATHS:
            path = root / f"{key}.json"
            _write_json(path, _payload_for_key(key))
            paths[key] = path
        fill_attempts = root / "fill_attempts.jsonl"
        _write_jsonl(
            fill_attempts,
            [
                {
                    "event_type": "candidate_shown",
                    "pricing_evidence_class": "proof_live_opra_exact_contract",
                    "fill_status": "not_filled_auto_track_skipped",
                    "fill_outcome": "no_fill",
                },
                {
                    "event_type": "candidate_shown",
                    "pricing_evidence_class": "proof_live_opra_exact_contract",
                    "fill_status": "not_submitted_auto_track_disabled",
                    "fill_outcome": "not_submitted",
                },
                {
                    "event_type": "candidate_shown",
                    "pricing_evidence_class": "proof_live_opra_exact_contract",
                    "fill_status": "auto_tracked",
                    "fill_outcome": "paper_fill_recorded",
                    "fill_discipline_snapshot": {"limit": 1.25},
                    "top_alternatives": [{"symbol": "ALT"}],
                },
                {"event_type": "candidate_shown", "pricing_evidence_class": "diagnostic_midpoint"},
            ],
        )
        return paths, fill_attempts

    def test_happy_path_builds_command_center_sections_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            report = audit.build_report(
                artifact_paths=paths,
                fill_attempts_path=fill_attempts,
                generated_at_utc="2026-06-06T01:00:00Z",
            )

        self.assertEqual(report["status"], "monthly_profitability_readback")
        self.assertEqual(report["summary"]["overall_status"], "profitability_iteration_ready_blocked_for_promotion")
        self.assertEqual(len(report["lane_leaderboard"]), 2)
        self.assertEqual(report["monthly_drift"]["recent_month"], "2026-05")
        self.assertEqual(report["execution_realism"]["proof_live_exact_count"], 3)
        self.assertEqual(report["execution_realism"]["no_fill_count"], 1)
        self.assertEqual(report["execution_realism"]["not_submitted_count"], 1)
        self.assertEqual(report["execution_realism"]["paper_fill_recorded_count"], 1)
        self.assertEqual(report["execution_realism"]["fill_discipline_snapshot_count"], 1)
        self.assertEqual(report["execution_realism"]["minute_exit_readiness"]["entry_seed_ready_count"], 2)
        self.assertEqual(report["risk_portfolio"]["risk_portfolio_status"], "blocked")
        self.assertFalse(report["promotion_gate"]["promotion_ready"])
        dispositions = {item["lane"]: item for item in report["lane_dispositions"]["dispositions"]}
        self.assertEqual(report["lane_dispositions"]["lane_disposition_status"], "all_active_regular_lanes_classified_read_only")
        self.assertEqual(dispositions["short_term"]["disposition"], "quarantine")
        self.assertEqual(dispositions["volatility_expansion_observation"]["disposition"], "paper_shadow")
        self.assertEqual(report["summary"]["lane_disposition_counts"]["quarantine"], 1)
        self.assertEqual(report["summary"]["lane_disposition_counts"]["paper_shadow"], 1)
        self.assertEqual(report["summary"]["unarchived_quarantine_lane_count"], 1)
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertIn("resolve_open_risk", actions)
        self.assertIn("build_minute_exit_replay", actions)
        self.assertIn("archive_overfit_rule", actions)
        self.assertIn("record_lane_quarantine_disposition", actions)
        self.assertIn("collect_paper_shadow_exact_evidence", actions)
        self.assertEqual(report["summary"]["archived_reject_overfit_rule_count"], 0)
        self.assertEqual(report["summary"]["unarchived_reject_overfit_rule_count"], 2)

    def test_missing_required_profitability_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            paths["missed_picks_failure_modes"].unlink()
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("missed_picks_failure_modes", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["inputs"]["missed_picks_failure_modes"]["status"], "missing")

    def test_candidate_rule_scoring_rejects_overfit_and_keeps_only_clean_paper_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        rules = {rule["scenario_id"]: rule for rule in report["candidate_rules"]}
        self.assertEqual(rules["high_pf_tiny_many_lost_winners"]["classification"], "reject_overfit")
        self.assertIn("winner_damage_exceeds_deep_losses_avoided", rules["high_pf_tiny_many_lost_winners"]["classification_blockers"])
        self.assertEqual(rules["clean_entry_time_holdout_candidate"]["classification"], "paper_candidate_only")
        self.assertFalse(rules["clean_entry_time_holdout_candidate"]["promotion_ready"])
        self.assertEqual(rules["non_entry_time_rule"]["classification"], "reject_overfit")

    def test_active_regular_lane_without_monthly_economics_needs_replay_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            lane_state = _payload_for_key("lane_promotion_state")
            lane_state["lane_states"] = {
                "missing_active_lane": {
                    "tracking_mode": "auto_track",
                    "fresh_live_validation_enabled": True,
                    "promotion_state": "diagnostic",
                    "candidate_status": "diagnostic_only_lane_promotion_state",
                    "blockers": ["lane_not_profitable_enough_for_probation"],
                    "lane_gate_metrics": {},
                }
            }
            _write_json(paths["lane_promotion_state"], lane_state)
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        dispositions = {item["lane"]: item for item in report["lane_dispositions"]["dispositions"]}
        self.assertEqual(dispositions["missing_active_lane"]["disposition"], "needs_replay_engine")
        self.assertIn("missing_monthly_lane_economics", dispositions["missing_active_lane"]["blockers"])
        self.assertEqual(report["lane_dispositions"]["status_counts"]["needs_replay_engine"], 1)

    def test_archived_quarantine_lanes_leave_disposition_table_but_not_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            archive_path = root / "lane_quarantine_archive.json"
            _write_json(
                archive_path,
                {
                    "status": "lane_quarantine_archive_readback",
                    "summary": {"live_policy_change": False, "archive_complete": True},
                    "archived_lanes": [
                        {
                            "lane": "short_term",
                            "archive_status": "archived_quarantine_lane",
                        }
                    ],
                },
            )
            paths["lane_quarantine_archive"] = archive_path
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        dispositions = {item["lane"]: item for item in report["lane_dispositions"]["dispositions"]}
        self.assertEqual(dispositions["short_term"]["archive_status"], "archived_quarantine_lane")
        self.assertEqual(report["summary"]["archived_quarantine_lane_count"], 1)
        self.assertEqual(report["summary"]["unarchived_quarantine_lane_count"], 0)
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("record_lane_quarantine_disposition", actions)

    def test_built_sizing_replay_surfaces_metrics_without_build_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            layer_stack = _layer_stack()
            for layer in layer_stack["layers"]:
                if layer["slug"] == "risk_budget_sizing_replay":
                    layer["implementation_status"] = "built_collecting"
                    layer["gate_status"] = "collecting"
                    layer["primary_blockers"] = [
                        "open_risk_governor_blocks_sizing",
                        "fresh_exact_realized_sizing_evidence_required",
                    ]
                    layer["metrics"] = {
                        "sizing_replay_status": "sizing_replay_built_open_risk_blocked",
                        "best_research_scenario_id": "tiered_shadow_full_retest_quarter",
                        "best_research_net_pnl_usd": 355.19,
                        "best_research_profit_factor": 1.16,
                    }
            _write_json(paths["profitability_layer_stack"], layer_stack)

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["risk_portfolio"]["risk_budget_sizing_status"], "collecting")
        self.assertEqual(
            report["risk_portfolio"]["risk_budget_sizing_metrics"]["best_research_scenario_id"],
            "tiered_shadow_full_retest_quarter",
        )
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("build_risk_budget_sizing_replay", actions)

    def test_built_lane_outcome_replay_replaces_generic_build_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            lane_state = _payload_for_key("lane_promotion_state")
            lane_state["lane_states"] = {
                "missing_active_lane": {
                    "tracking_mode": "auto_track",
                    "fresh_live_validation_enabled": True,
                    "promotion_state": "diagnostic",
                    "candidate_status": "diagnostic_only_lane_promotion_state",
                    "blockers": ["lane_not_profitable_enough_for_probation"],
                    "lane_gate_metrics": {},
                }
            }
            _write_json(paths["lane_promotion_state"], lane_state)
            lane_outcome_path = root / "lane_outcome.json"
            _write_json(
                lane_outcome_path,
                {
                    "status": "lane_outcome_replay_readback",
                    "summary": {
                        "overall_status": "lane_outcome_replay_built_collecting",
                        "active_lane_count": 1,
                        "priced_outcome_lane_count": 0,
                        "missing_outcome_lane_count": 1,
                        "outcome_status_counts": {"no_signal_candidates_in_monthly_window": 1},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "build_or_repair_lane_scan_hypothesis_before_pnl_replay",
                            "count": 1,
                            "reason": "no_signal_candidates_in_monthly_window",
                        }
                    ],
                },
            )
            paths["lane_outcome_replay"] = lane_outcome_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["lane_outcome_replay"]["status"], "lane_outcome_replay_built_collecting")
        self.assertEqual(report["summary"]["lane_outcome_replay_implementation_status"], "built_collecting")
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("build_lane_outcome_replay", actions)
        self.assertIn("build_or_repair_lane_scan_hypothesis_before_pnl_replay", actions)

    def test_lane_scan_hypothesis_repair_replaces_generic_no_signal_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            lane_state = _payload_for_key("lane_promotion_state")
            lane_state["lane_states"] = {
                "missing_active_lane": {
                    "tracking_mode": "auto_track",
                    "fresh_live_validation_enabled": True,
                    "promotion_state": "diagnostic",
                    "candidate_status": "diagnostic_only_lane_promotion_state",
                    "blockers": ["lane_not_profitable_enough_for_probation"],
                    "lane_gate_metrics": {},
                }
            }
            _write_json(paths["lane_promotion_state"], lane_state)
            lane_outcome_path = root / "lane_outcome.json"
            _write_json(
                lane_outcome_path,
                {
                    "status": "lane_outcome_replay_readback",
                    "summary": {
                        "overall_status": "lane_outcome_replay_built_collecting",
                        "active_lane_count": 1,
                        "priced_outcome_lane_count": 0,
                        "missing_outcome_lane_count": 1,
                        "outcome_status_counts": {"no_signal_candidates_in_monthly_window": 1},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "build_or_repair_lane_scan_hypothesis_before_pnl_replay",
                            "count": 1,
                            "reason": "no_signal_candidates_in_monthly_window",
                        }
                    ],
                },
            )
            lane_scan_repair_path = root / "lane_scan_repair.json"
            _write_json(
                lane_scan_repair_path,
                {
                    "status": "lane_scan_hypothesis_repair_readback",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "overall_status": "lane_scan_hypothesis_repair_built_collecting",
                        "target_no_signal_lane_count": 1,
                        "predeclared_replacement_candidate_count": 1,
                        "predeclared_candidate_lane_count": 1,
                        "missing_replacement_candidate_lane_count": 0,
                        "proof_ready_replacement_candidate_count": 0,
                        "fresh_exact_scan_retest_row_count": 0,
                        "true_lane_outcome_pnl_row_count": 0,
                        "repair_status_counts": {"predeclared_proof_only_candidate_found": 1},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "collect_proof_only_lane_scan_retest_rows",
                            "count": 1,
                            "reason": "no_signal_lanes_have_predeclared_proof_only_replacement_candidates",
                        }
                    ],
                },
            )
            paths["lane_outcome_replay"] = lane_outcome_path
            paths["lane_scan_hypothesis_repair"] = lane_scan_repair_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["lane_scan_hypothesis_repair"]["status"],
            "lane_scan_hypothesis_repair_built_collecting",
        )
        self.assertEqual(
            report["summary"]["lane_scan_hypothesis_repair_implementation_status"],
            "built_collecting",
        )
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("build_or_repair_lane_scan_hypothesis_before_pnl_replay", actions)
        self.assertNotIn("collect_proof_only_lane_scan_retest_rows", actions)

    def test_exact_candidate_repair_replaces_generic_chain_native_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            lane_state = _payload_for_key("lane_promotion_state")
            lane_state["lane_states"] = {
                "regular_bearish_put_primary": {
                    "tracking_mode": "auto_track",
                    "fresh_live_validation_enabled": True,
                    "promotion_state": "diagnostic",
                    "candidate_status": "diagnostic_only_lane_promotion_state",
                    "blockers": ["lane_monthly_outcome_missing"],
                }
            }
            _write_json(paths["lane_promotion_state"], lane_state)
            lane_outcome_path = root / "lane_outcome.json"
            _write_json(
                lane_outcome_path,
                {
                    "status": "lane_outcome_replay_readback",
                    "summary": {
                        "overall_status": "lane_outcome_replay_built_collecting",
                        "active_lane_count": 1,
                        "priced_outcome_lane_count": 0,
                        "missing_outcome_lane_count": 1,
                        "outcome_status_counts": {"signal_candidates_without_exact_chain_native_spreads": 1},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "repair_chain_native_exact_candidate_selection",
                            "count": 1,
                            "reason": "signals_exist_but_no_exact_chain_native_spreads",
                        }
                    ],
                },
            )
            exact_repair_path = root / "exact_repair.json"
            _write_json(
                exact_repair_path,
                {
                    "status": "exact_candidate_selection_repair_readback",
                    "summary": {
                        "overall_status": "exact_candidate_selection_repair_targets_ready",
                        "target_lane_count": 1,
                        "target_date_count": 1,
                        "target_signal_candidate_count": 4,
                        "target_exact_candidate_count": 0,
                        "exact_reject_reason_counts": {"no_chain_native_spread_passed_current_filters": 4},
                        "top_signal_tickers": ["COIN", "DIS", "META", "SBUX"],
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "build_chain_native_filter_relaxation_replay",
                            "count": 1,
                            "reason": "no_chain_native_spread_passed_current_filters:1",
                        }
                    ],
                },
            )
            paths["lane_outcome_replay"] = lane_outcome_path
            paths["exact_candidate_selection_repair"] = exact_repair_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["exact_candidate_selection_repair"]["status"], "exact_candidate_selection_repair_targets_ready")
        self.assertEqual(report["summary"]["exact_candidate_selection_repair_implementation_status"], "built_collecting")
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("repair_chain_native_exact_candidate_selection", actions)
        self.assertIn("build_chain_native_filter_relaxation_replay", actions)

    def test_chain_native_filter_relaxation_replay_replaces_build_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            lane_state = json.loads(paths["lane_promotion_state"].read_text(encoding="utf8"))
            lane_state["lane_states"] = {
                "regular_bearish_put_primary": {
                    "tracking_mode": "auto_track",
                    "fresh_live_validation_enabled": True,
                    "promotion_state": "diagnostic",
                    "candidate_status": "diagnostic_only_lane_promotion_state",
                    "blockers": ["lane_monthly_outcome_missing"],
                }
            }
            _write_json(paths["lane_promotion_state"], lane_state)
            lane_outcome_path = root / "lane_outcome.json"
            _write_json(
                lane_outcome_path,
                {
                    "status": "lane_outcome_replay_readback",
                    "summary": {
                        "overall_status": "lane_outcome_replay_built_collecting",
                        "active_lane_count": 1,
                        "priced_outcome_lane_count": 0,
                        "missing_outcome_lane_count": 1,
                        "outcome_status_counts": {"signal_candidates_without_exact_chain_native_spreads": 1},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "repair_chain_native_exact_candidate_selection",
                            "count": 1,
                            "reason": "signals_exist_but_no_exact_chain_native_spreads",
                        }
                    ],
                },
            )
            exact_repair_path = root / "exact_repair.json"
            _write_json(
                exact_repair_path,
                {
                    "status": "exact_candidate_selection_repair_readback",
                    "summary": {
                        "overall_status": "exact_candidate_selection_repair_targets_ready",
                        "target_lane_count": 1,
                        "target_date_count": 1,
                        "target_signal_candidate_count": 4,
                        "target_exact_candidate_count": 0,
                        "exact_reject_reason_counts": {"no_chain_native_spread_passed_current_filters": 4},
                        "top_signal_tickers": ["COIN", "DIS", "META", "SBUX"],
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "build_chain_native_filter_relaxation_replay",
                            "count": 1,
                            "reason": "no_chain_native_spread_passed_current_filters:1",
                        }
                    ],
                },
            )
            chain_relaxation_path = root / "chain_relaxation.json"
            _write_json(
                chain_relaxation_path,
                {
                    "status": "chain_native_filter_relaxation_replay_readback",
                    "summary": {
                        "overall_status": "chain_native_filter_relaxation_replay_entry_quote_gap",
                        "target_lane_count": 1,
                        "target_date_count": 1,
                        "target_signal_candidate_count": 4,
                        "replay_signal_candidate_count": 4,
                        "scenario_count": 7,
                        "scenario_row_count": 28,
                        "current_selected_chain_native_entry_spread_count": 0,
                        "relaxed_selected_chain_native_entry_spread_count": 0,
                        "entry_quote_demand_count": 4,
                        "entry_quote_demand_tickers": ["COIN", "DIS", "META", "SBUX"],
                        "scenario_status_counts": {"no_entry_contract_quotes": 28},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "import_or_query_chain_native_entry_contract_quotes",
                            "count": 4,
                            "reason": "trusted_entry_contract_quote_coverage_missing_for_target_underlyings",
                        }
                    ],
                },
            )
            paths["lane_outcome_replay"] = lane_outcome_path
            paths["exact_candidate_selection_repair"] = exact_repair_path
            paths["chain_native_filter_relaxation_replay"] = chain_relaxation_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["chain_native_filter_relaxation_replay"]["status"],
            "chain_native_filter_relaxation_replay_entry_quote_gap",
        )
        self.assertEqual(report["summary"]["chain_native_filter_relaxation_replay_implementation_status"], "built_collecting")
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("repair_chain_native_exact_candidate_selection", actions)
        self.assertNotIn("build_chain_native_filter_relaxation_replay", actions)
        self.assertIn("import_or_query_chain_native_entry_contract_quotes", actions)

    def test_chain_native_exit_outcome_replay_replaces_exit_build_queue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            chain_relaxation_path = root / "chain_relaxation.json"
            _write_json(
                chain_relaxation_path,
                {
                    "status": "chain_native_filter_relaxation_replay_readback",
                    "summary": {
                        "overall_status": "chain_native_filter_relaxation_replay_candidates_found_diagnostic_only",
                        "target_lane_count": 1,
                        "target_date_count": 1,
                        "target_signal_candidate_count": 4,
                        "replay_signal_candidate_count": 4,
                        "scenario_count": 7,
                        "scenario_row_count": 28,
                        "current_selected_chain_native_entry_spread_count": 4,
                        "relaxed_selected_chain_native_entry_spread_count": 24,
                        "entry_quote_demand_count": 0,
                        "entry_quote_demand_tickers": [],
                        "scenario_status_counts": {"selected_chain_native_entry_spread": 28},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates",
                            "count": 24,
                            "reason": "relaxed_entry_candidates_have_no_exact_exit_pnl",
                        },
                        {
                            "priority": 5,
                            "action": "validate_chain_native_relaxation_on_later_holdout",
                            "count": 1,
                            "reason": "single_date_target_overfit_risk",
                        },
                    ],
                },
            )
            exit_outcome_path = root / "exit_outcome.json"
            _write_json(
                exit_outcome_path,
                {
                    "status": "chain_native_exit_outcome_replay_readback",
                    "summary": {
                        "overall_status": "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only",
                        "selected_scenario_row_count": 28,
                        "current_selected_scenario_row_count": 4,
                        "relaxed_selected_scenario_row_count": 24,
                        "priced_scenario_row_count": 28,
                        "priced_current_scenario_row_count": 4,
                        "priced_relaxed_scenario_row_count": 24,
                        "missing_exit_quote_demand_count": 0,
                        "best_relaxed_scenario": {
                            "scenario_id": "combined_broad_entry_relaxation",
                            "avg_net_pnl_pct": 12.5,
                            "profit_factor": 1.8,
                        },
                        "latest_intraday_quote_date": "2026-06-04",
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 5,
                            "action": "validate_chain_native_relaxation_on_later_holdout",
                            "count": 1,
                            "reason": "single_date_positive_diagnostic_exit_outcome_requires_holdout",
                        }
                    ],
                },
            )
            paths["chain_native_filter_relaxation_replay"] = chain_relaxation_path
            paths["chain_native_exit_outcome_replay"] = exit_outcome_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["chain_native_exit_outcome_replay"]["status"],
            "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only",
        )
        self.assertEqual(report["summary"]["chain_native_exit_outcome_replay_implementation_status"], "built_collecting")
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertNotIn("build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates", actions)
        self.assertIn("validate_chain_native_relaxation_on_later_holdout", actions)

    def test_chain_native_relaxation_archive_suppresses_negative_branch_archive_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            chain_relaxation_path = root / "chain_relaxation.json"
            _write_json(
                chain_relaxation_path,
                {
                    "status": "chain_native_filter_relaxation_replay_readback",
                    "summary": {
                        "overall_status": "chain_native_filter_relaxation_replay_candidates_found_diagnostic_only",
                        "target_lane_count": 1,
                        "target_date_count": 1,
                        "target_signal_candidate_count": 4,
                        "replay_signal_candidate_count": 4,
                        "scenario_count": 7,
                        "scenario_row_count": 28,
                        "current_selected_chain_native_entry_spread_count": 4,
                        "relaxed_selected_chain_native_entry_spread_count": 24,
                        "entry_quote_demand_count": 0,
                        "entry_quote_demand_tickers": [],
                        "scenario_status_counts": {"selected_chain_native_entry_spread": 28},
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 4,
                            "action": "build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates",
                            "count": 24,
                            "reason": "relaxed_entry_candidates_have_no_exact_exit_pnl",
                        },
                        {
                            "priority": 5,
                            "action": "validate_chain_native_relaxation_on_later_holdout",
                            "count": 1,
                            "reason": "single_date_target_overfit_risk",
                        },
                    ],
                },
            )
            exit_outcome_path = root / "exit_outcome.json"
            _write_json(
                exit_outcome_path,
                {
                    "status": "chain_native_exit_outcome_replay_readback",
                    "summary": {
                        "overall_status": "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only",
                        "selected_scenario_row_count": 28,
                        "current_selected_scenario_row_count": 4,
                        "relaxed_selected_scenario_row_count": 24,
                        "priced_scenario_row_count": 28,
                        "priced_current_scenario_row_count": 4,
                        "priced_relaxed_scenario_row_count": 24,
                        "missing_exit_quote_demand_count": 0,
                        "best_relaxed_scenario": {
                            "scenario_id": "widen_dte_window_only",
                            "avg_net_pnl_pct": -9.26,
                            "profit_factor": 0.62,
                        },
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 5,
                            "action": "archive_negative_chain_native_relaxation_branch",
                            "count": 1,
                            "reason": "relaxed_chain_native_exit_outcome_not_profitable_on_exact_replay",
                        }
                    ],
                },
            )
            archive_path = root / "chain_archive.json"
            _write_json(
                archive_path,
                {
                    "status": "chain_native_relaxation_archive_readback",
                    "summary": {
                        "overall_status": "negative_chain_native_branches_archived",
                        "live_policy_change": False,
                        "archive_complete": True,
                        "source_ready_for_archive": True,
                        "branch_scenario_count": 7,
                        "negative_branch_count": 7,
                        "archived_negative_branch_count": 7,
                        "unarchived_negative_branch_count": 0,
                        "current_scenario_count": 1,
                        "negative_current_scenario_count": 1,
                        "archived_negative_current_scenario_count": 1,
                        "unarchived_negative_current_scenario_count": 0,
                        "relaxed_scenario_count": 6,
                        "negative_relaxed_scenario_count": 6,
                        "archived_negative_relaxed_scenario_count": 6,
                        "unarchived_negative_relaxed_scenario_count": 0,
                        "archive_requested_by_exit_outcome_replay": True,
                    },
                    "archived_branches": [
                        {
                            "branch_id": "current_chain_native_filters|regular_bearish_put_primary|2026-05-22",
                            "archive_status": "archived_negative_chain_native_current_branch",
                        },
                        {
                            "branch_id": "widen_dte_window_only|regular_bearish_put_primary|2026-05-22",
                            "archive_status": "archived_negative_chain_native_relaxation_branch",
                        }
                    ],
                },
            )
            paths["chain_native_filter_relaxation_replay"] = chain_relaxation_path
            paths["chain_native_exit_outcome_replay"] = exit_outcome_path
            paths["chain_native_relaxation_archive"] = archive_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["chain_native_relaxation_archive"]["status"],
            "negative_chain_native_branches_archived",
        )
        self.assertEqual(report["summary"]["chain_native_relaxation_archive_implementation_status"], "built")
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertNotIn("build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates", actions)
        self.assertNotIn("archive_negative_chain_native_relaxation_branch", actions)
        self.assertNotIn("validate_chain_native_relaxation_on_later_holdout", actions)

    def test_exhausted_contract_archive_surfaces_archived_contract_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            archive_path = root / "exhausted_contract_archive.json"
            _write_json(
                archive_path,
                {
                    "status": "exhausted_contract_archive_readback",
                    "summary": {
                        "overall_status": "exhausted_contract_target_archived",
                        "source_ready_for_archive": True,
                        "source_repair_burndown_status": "repair_burndown_ready",
                        "source_exhausted_current_source_target_count": 97,
                        "archived_exhausted_contract_count": 1,
                        "previous_archived_exhausted_contract_count": 0,
                        "newly_archived_exhausted_contract_count": 1,
                        "remaining_eligible_exhausted_contract_count": 96,
                        "archive_limit": 1,
                        "new_target_limit": 1,
                        "min_attempt_count_required": 2,
                        "archive_complete_for_selected_limit": True,
                        "live_policy_change": False,
                    },
                },
            )
            paths["exhausted_contract_archive"] = archive_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["exhausted_contract_archive"]["status"], "exhausted_contract_target_archived")
        self.assertEqual(report["summary"]["exhausted_contract_archive_implementation_status"], "built")
        self.assertEqual(
            report["summary"]["exhausted_contract_archive_metrics"]["archived_exhausted_contract_count"],
            1,
        )
        self.assertEqual(
            report["summary"]["exhausted_contract_archive_metrics"]["newly_archived_exhausted_contract_count"],
            1,
        )

    def test_execution_alternative_quote_import_plan_replaces_generic_replay_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            plan_path = root / "execution_alternative_quote_import_plan.json"
            _write_json(
                plan_path,
                {
                    "status": "execution_alternative_quote_import_plan_ready",
                    "generated_at_utc": "2026-06-06T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "source_coverage_status": "execution_alternative_replay_coverage_readback",
                        "source_quote_demand_manifest_status": "ready_for_import_or_query",
                        "exact_contract_manifest_count": 58,
                        "unparsed_quote_demand_count": 0,
                        "command_group_count": 6,
                        "entry_quote_demand_count": 33,
                        "exit_quote_demand_count": 25,
                        "quote_dates": ["2026-05-21", "2026-05-22", "2026-06-04"],
                        "underlyings": ["QQQ", "SPY"],
                        "operator_command_status": "ready_for_dry_run_then_operator_import",
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "run_execution_alternative_quote_import_commands",
                            "count": 6,
                            "reason": "execution_alternative_quote_demands_ready_for_import_or_query",
                            "operator_next_step": "Run the dry-run commands first.",
                        }
                    ],
                },
            )
            paths["execution_alternative_quote_import_plan"] = plan_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["execution_alternative_quote_import_plan"]["status"],
            "execution_alternative_quote_import_plan_ready",
        )
        self.assertEqual(
            report["summary"]["execution_alternative_quote_import_plan_implementation_status"],
            "built_collecting",
        )
        self.assertEqual(
            report["summary"]["execution_alternative_quote_import_plan_metrics"]["command_group_count"],
            6,
        )
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("run_execution_alternative_quote_import_commands", actions)
        self.assertNotIn("build_top_spread_alternative_replay", actions)
        self.assertNotIn("build_contract_replacement_replay", actions)
        self.assertIn("build_minute_exit_replay", actions)
        queue_item = next(
            item
            for item in report["next_evidence_queue"]
            if item["action"] == "run_execution_alternative_quote_import_commands"
        )
        self.assertEqual(queue_item["source"], "execution_alternative_quote_import_plan")
        self.assertEqual(queue_item["count"], 6)

    def test_minute_exit_quote_import_plan_replaces_generic_minute_replay_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            plan_path = root / "minute_exit_quote_import_plan.json"
            _write_json(
                plan_path,
                {
                    "status": "minute_exit_quote_import_plan_ready_engine_blocked",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "source_readiness_status": "minute_exit_replay_readiness_readback",
                        "source_overall_status": "blocked_ready_seed_missing_minute_engine",
                        "source_entry_seed_ready_count": 12,
                        "source_position_seed_ready_count": 1,
                        "source_true_minute_exit_pnl_count": 0,
                        "source_minute_exit_replay_engine_status": "missing",
                        "source_minute_quote_coverage_status": "missing",
                        "exact_contract_manifest_count": 24,
                        "unparsed_quote_demand_count": 0,
                        "command_group_count": 4,
                        "position_linked_quote_demand_count": 2,
                        "entry_only_quote_demand_count": 22,
                        "quote_dates": ["2026-05-21", "2026-06-05"],
                        "underlyings": ["QQQ", "SPY"],
                        "operator_command_status": "ready_for_dry_run_then_operator_import",
                        "replay_pnl_status": "not_available_until_quotes_and_engine_exist",
                    },
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "run_minute_exit_quote_import_plan_commands",
                            "count": 4,
                            "reason": "minute_exit_quote_demands_ready_for_import_or_query",
                            "operator_next_step": "Run dry-run imports first.",
                        }
                    ],
                },
            )
            paths["minute_exit_quote_import_plan"] = plan_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["minute_exit_quote_import_plan"]["status"],
            "minute_exit_quote_import_plan_ready_engine_blocked",
        )
        self.assertEqual(
            report["summary"]["minute_exit_quote_import_plan_implementation_status"],
            "built_collecting",
        )
        self.assertEqual(
            report["summary"]["minute_exit_quote_import_plan_metrics"]["command_group_count"],
            4,
        )
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("run_minute_exit_quote_import_plan_commands", actions)
        self.assertNotIn("build_minute_exit_replay", actions)
        queue_item = next(
            item
            for item in report["next_evidence_queue"]
            if item["action"] == "run_minute_exit_quote_import_plan_commands"
        )
        self.assertEqual(queue_item["source"], "minute_exit_quote_import_plan")
        self.assertEqual(queue_item["count"], 4)

    def test_open_risk_resolution_plan_replaces_duplicate_open_risk_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            candidate_ledger = _payload_for_key("candidate_ledger")
            candidate_ledger["next_evidence_queue"] = [
                {
                    "next_evidence_action": "resolve_open_risk_governor",
                    "action_priority": 0,
                    "count": 1,
                    "operator_next_step": "Resolve the governor.",
                },
                {
                    "next_evidence_action": "refresh_open_position_executable_review",
                    "action_priority": 1,
                    "count": 1,
                    "operator_next_step": "Refresh the open position review.",
                },
                {
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "action_priority": 2,
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                },
            ]
            _write_json(paths["candidate_ledger"], candidate_ledger)
            plan_path = root / "open_risk_resolution_plan.json"
            _write_json(
                plan_path,
                {
                    "status": "open_risk_resolution_plan_ready_blocked_for_market_window",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "source_open_risk_status": "open_risk_governor_blocked",
                        "live_entry_allowed": False,
                        "live_exact_negative_count": 1,
                        "live_exact_negative_ids": [537],
                        "open_position_row_count": 12,
                        "open_position_negative_count": 10,
                        "open_position_avg_pnl_pct": -44.14,
                        "open_position_median_pnl_pct": -47.58,
                        "plan_row_count": 2,
                        "market_window_required_count": 2,
                        "live_exact_plan_row_count": 1,
                        "display_only_sell_count": 1,
                        "operator_plan_status": "ready_for_fresh_executable_review_window",
                    },
                    "plan_rows": [
                        {
                            "priority": 0,
                            "row_id": 537,
                            "ticker": "QQQ",
                            "lane": "volatility_expansion_observation",
                            "record_class": "live_exact_tracked",
                            "action": "refresh_live_exact_negative_open_position_review",
                            "resolution_status": "fresh_quote_monitor_or_close_decision_required",
                        },
                        {
                            "priority": 1,
                            "row_id": 104,
                            "ticker": "SBUX",
                            "lane": "bullish_pullback_observation",
                            "record_class": "main_zero_pick_research_backfill",
                            "action": "refresh_display_only_sell_executable_review",
                            "resolution_status": "market_window_required_display_only_sell_review",
                        },
                    ],
                    "next_evidence_queue": [
                        {
                            "priority": 0,
                            "action": "execute_open_risk_resolution_review_plan",
                            "count": 2,
                            "reason": "open_risk_rows_need_fresh_executable_review_or_monitor_decision",
                        }
                    ],
                },
            )
            paths["open_risk_resolution_plan"] = plan_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["open_risk_resolution_plan"]["status"],
            "open_risk_resolution_plan_ready_blocked_for_market_window",
        )
        self.assertEqual(
            report["summary"]["open_risk_resolution_plan_implementation_status"],
            "built_collecting",
        )
        self.assertEqual(
            report["summary"]["open_risk_resolution_plan_metrics"]["plan_row_count"],
            2,
        )
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("execute_open_risk_resolution_review_plan", actions)
        self.assertIn("collect_exact_exit_evidence", actions)
        self.assertNotIn("resolve_open_risk", actions)
        self.assertNotIn("resolve_open_risk_governor", actions)
        self.assertNotIn("refresh_open_position_executable_review", actions)
        queue_item = next(
            item
            for item in report["next_evidence_queue"]
            if item["action"] == "execute_open_risk_resolution_review_plan"
        )
        self.assertEqual(queue_item["source"], "open_risk_resolution_plan")
        self.assertEqual(queue_item["count"], 2)

    def test_fill_attempt_capture_plan_replaces_generic_missing_fill_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            candidate_ledger = _payload_for_key("candidate_ledger")
            candidate_ledger["next_evidence_queue"] = [
                {
                    "next_evidence_action": "capture_missing_fill_attempt_evidence",
                    "action_priority": 7,
                    "count": 4,
                    "operator_next_step": "Capture missing fill evidence.",
                },
                {
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "action_priority": 2,
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                },
            ]
            _write_json(paths["candidate_ledger"], candidate_ledger)
            plan_path = root / "fill_attempt_plan.json"
            _write_json(
                plan_path,
                {
                    "status": "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "source_candidate_ledger_operating_status": "ledger_live_entry_blocked_collect_evidence",
                        "source_fill_attempt_rows": 500,
                        "source_missing_fill_attempt_action_count": 4,
                        "plan_row_count": 4,
                        "missing_fill_attempt_evidence_count": 4,
                        "ledger_stale_fill_attempt_logged_count": 0,
                        "market_window_required_count": 4,
                        "scan_dates": ["2026-06-05"],
                        "lane_counts": {"swing": 2, "short_term": 1, "volatility_expansion_observation": 1},
                        "ticker_counts": {"QQQ": 2, "SPY": 2},
                        "operator_plan_status": "ready_for_fresh_selection_capture",
                    },
                    "plan_rows": [
                        {
                            "priority": 7,
                            "scan_date": "2026-06-05",
                            "ticker": "QQQ",
                            "lane_id": "swing",
                            "action": "capture_durable_fill_attempt_on_fresh_selection",
                            "capture_status": "missing",
                        }
                    ],
                    "next_evidence_queue": [
                        {
                            "priority": 7,
                            "action": "execute_fill_attempt_evidence_capture_plan",
                            "count": 4,
                            "reason": "fresh_candidates_need_durable_fill_attempt_evidence",
                        }
                    ],
                },
            )
            paths["fill_attempt_evidence_capture_plan"] = plan_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["fill_attempt_evidence_capture_plan"]["status"],
            "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection",
        )
        self.assertEqual(
            report["summary"]["fill_attempt_evidence_capture_plan_implementation_status"],
            "built_collecting",
        )
        self.assertEqual(
            report["summary"]["fill_attempt_evidence_capture_plan_metrics"]["missing_fill_attempt_evidence_count"],
            4,
        )
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("execute_fill_attempt_evidence_capture_plan", actions)
        self.assertIn("collect_exact_exit_evidence", actions)
        self.assertNotIn("capture_missing_fill_attempt_evidence", actions)
        queue_item = next(
            item
            for item in report["next_evidence_queue"]
            if item["action"] == "execute_fill_attempt_evidence_capture_plan"
        )
        self.assertEqual(queue_item["source"], "fill_attempt_evidence_capture_plan")
        self.assertEqual(queue_item["count"], 4)

    def test_suggested_trade_review_plan_replaces_generic_suggested_review_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            candidate_ledger = _payload_for_key("candidate_ledger")
            candidate_ledger["next_evidence_queue"] = [
                {
                    "next_evidence_action": "refresh_suggested_trade_review",
                    "action_priority": 1,
                    "count": 1,
                    "operator_next_step": "Refresh suggested-trade review.",
                },
                {
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "action_priority": 2,
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                },
            ]
            _write_json(paths["candidate_ledger"], candidate_ledger)
            plan_path = root / "suggested_trade_review_plan.json"
            _write_json(
                plan_path,
                {
                    "status": "suggested_trade_review_plan_ready_blocked_for_market_window",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "open_suggested_trade_rows": 1,
                        "attention_trade_count": 1,
                        "close_risk_trade_count": 0,
                        "stale_or_missing_review_trade_count": 1,
                        "missing_review_count": 1,
                        "stale_review_count": 0,
                        "executable_close_ready_count": 0,
                        "non_executable_close_risk_count": 0,
                        "plan_row_count": 1,
                        "market_window_required_count": 1,
                        "source_action_counts": {"no_stored_review": 1},
                        "source_evidence_counts": {"missing_review": 1},
                        "operator_plan_status": "ready_for_fresh_suggested_trade_review_window",
                    },
                    "plan_rows": [
                        {
                            "priority": 1,
                            "suggested_trade_id": 138,
                            "ticker": "AAA",
                            "lane": "legacy_unlabeled",
                            "record_class": "suggested_trade",
                            "action": "refresh_missing_suggested_trade_review",
                            "resolution_status": "market_window_required_missing_suggested_trade_review",
                        }
                    ],
                    "next_evidence_queue": [
                        {
                            "priority": 1,
                            "action": "execute_suggested_trade_review_plan",
                            "count": 1,
                            "reason": "suggested_trade_attention_rows_need_fresh_explicit_review",
                        }
                    ],
                },
            )
            paths["suggested_trade_review_plan"] = plan_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(
            report["suggested_trade_review_plan"]["status"],
            "suggested_trade_review_plan_ready_blocked_for_market_window",
        )
        self.assertEqual(
            report["summary"]["suggested_trade_review_plan_implementation_status"],
            "built_collecting",
        )
        self.assertEqual(
            report["summary"]["suggested_trade_review_plan_metrics"]["missing_review_count"],
            1,
        )
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("execute_suggested_trade_review_plan", actions)
        self.assertIn("collect_exact_exit_evidence", actions)
        self.assertNotIn("refresh_suggested_trade_review", actions)
        queue_item = next(
            item
            for item in report["next_evidence_queue"]
            if item["action"] == "execute_suggested_trade_review_plan"
        )
        self.assertEqual(queue_item["source"], "suggested_trade_review_plan")
        self.assertEqual(queue_item["count"], 1)

    def test_stale_candidate_archive_replaces_generic_wait_archive_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            candidate_ledger = _payload_for_key("candidate_ledger")
            candidate_ledger["next_evidence_queue"] = [
                {
                    "next_evidence_action": "wait_for_fresh_match_or_archive_candidate",
                    "action_priority": 8,
                    "count": 2,
                    "operator_next_step": "Archive stale no-longer-matched candidates.",
                },
                {
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "action_priority": 2,
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                },
            ]
            _write_json(paths["candidate_ledger"], candidate_ledger)
            stale_archive_path = root / "stale_candidate_archive.json"
            _write_json(
                stale_archive_path,
                {
                    "status": "stale_candidate_archive_readback",
                    "generated_at_utc": "2026-06-07T00:00:00Z",
                    "live_policy_change": False,
                    "summary": {
                        "overall_status": "stale_candidates_archived",
                        "source_wait_or_archive_count": 2,
                        "archived_no_longer_matched_candidate_count": 2,
                        "archive_exception_count": 0,
                        "archive_complete": True,
                        "lane_counts": {"quality90_debit55_canary": 2},
                        "ticker_counts": {"QQQ": 1, "SPY": 1},
                        "production_proof_ready_count": 0,
                    },
                    "next_evidence_queue": [],
                },
            )
            paths["stale_candidate_archive"] = stale_archive_path

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["stale_candidate_archive"]["status"], "stale_candidates_archived")
        self.assertEqual(report["summary"]["stale_candidate_archive_implementation_status"], "built")
        self.assertEqual(report["summary"]["stale_candidate_archive_metrics"]["source_wait_or_archive_count"], 2)
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertIn("collect_exact_exit_evidence", actions)
        self.assertNotIn("wait_for_fresh_match_or_archive_candidate", actions)

    def test_structure_specific_harness_collecting_removes_generic_build_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            layer_stack = _payload_for_key("profitability_layer_stack")
            for layer in layer_stack["layers"]:
                if layer["slug"] == "structure_specific_multileg_harness":
                    layer["gate_status"] = "collecting"
                    layer["implementation_status"] = "built_collecting"
                    layer["primary_blockers"] = [
                        "single_leg_or_other_multileg_samples_missing",
                        "true_structure_specific_pnl_rows_missing",
                    ]
                    layer["metrics"] = {
                        "candidate_shown_count": 4,
                        "structure_bucket_counts": {
                            "vertical_spread": 4,
                            "single_leg": 0,
                            "multi_leg_other": 0,
                            "unknown": 0,
                        },
                        "true_structure_specific_pnl_count": 0,
                    }
                    layer["next_action"] = "Collect true structure-specific exact P&L."
            _write_json(paths["profitability_layer_stack"], layer_stack)

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("build_structure_specific_harness", actions)
        self.assertNotIn(
            "structure_specific_multileg_harness",
            report["execution_realism"]["execution_realism_blockers"],
        )
        self.assertEqual(
            report["execution_realism"]["replay_gap_flags"]["structure_specific_multileg_harness"][
                "implementation_status"
            ],
            "built_collecting",
        )

    def test_event_data_spine_collecting_removes_generic_build_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            layer_stack = _payload_for_key("profitability_layer_stack")
            for layer in layer_stack["layers"]:
                if layer["slug"] == "event_data_spine_post_event_vol_crush":
                    layer["gate_status"] = "collecting"
                    layer["implementation_status"] = "built_collecting"
                    layer["primary_blockers"] = [
                        "event_calendar_annotations_missing",
                        "post_event_vol_crush_replay_rows_missing",
                        "true_event_executable_pnl_rows_missing",
                    ]
                    layer["metrics"] = {
                        "candidate_shown_count": 4,
                        "event_annotation_count": 0,
                        "missing_event_annotation_count": 4,
                        "post_event_vol_crush_replay_pnl_count": 0,
                    }
                    layer["next_action"] = "Collect event annotations and true post-event exact P&L."
            _write_json(paths["profitability_layer_stack"], layer_stack)

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("build_event_data_spine", actions)

    def test_archived_rejected_rules_leave_candidate_table_but_not_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            archive_path = root / "overfit_rule_archive.json"
            _write_json(
                archive_path,
                {
                    "status": "overfit_rule_archive_readback",
                    "summary": {"live_policy_change": False, "archive_complete": True},
                    "archived_rules": [
                        {
                            "scenario_id": "high_pf_tiny_many_lost_winners",
                            "archive_status": "archived_rejected_rule",
                        },
                        {
                            "scenario_id": "non_entry_time_rule",
                            "archive_status": "archived_rejected_rule",
                        },
                    ],
                },
            )
            paths["overfit_rule_archive"] = archive_path
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        rules = {rule["scenario_id"]: rule for rule in report["candidate_rules"]}
        self.assertEqual(rules["high_pf_tiny_many_lost_winners"]["archive_status"], "archived_rejected_rule")
        self.assertEqual(rules["non_entry_time_rule"]["archive_status"], "archived_rejected_rule")
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("archive_overfit_rule", actions)
        self.assertEqual(report["summary"]["archived_reject_overfit_rule_count"], 2)
        self.assertEqual(report["summary"]["unarchived_reject_overfit_rule_count"], 0)

    def test_open_risk_governor_and_paper_monitor_block_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        blockers = set(report["promotion_gate"]["blockers"])
        self.assertIn("open_risk_governor_blocked", blockers)
        self.assertIn("paper_monitor_not_passed", blockers)
        self.assertIn("profitability_layer_stack_blocked_or_collecting", blockers)
        self.assertFalse(report["summary"]["promotion_ready"])

    def test_oracle_ceiling_remains_non_promotable_without_trusted_mfe_mae(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["oracle_ceiling"]["oracle_ceiling_status"], "not_available_replay_gap")
        self.assertIsNone(report["oracle_ceiling"]["trusted_mfe_mae_artifact"])
        self.assertFalse(report["oracle_ceiling"]["promotion_allowed"])

    def test_live_policy_change_flag_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            payload = _payload_for_key("candidate_ledger")
            payload["summary"]["live_policy_change"] = True
            _write_json(paths["candidate_ledger"], payload)
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_scheduled_scan_heartbeat_reports_stale_market_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            paths["scheduled_scan_heartbeat"] = root / "scheduled_scan_heartbeat.json"
            _write_json(
                paths["scheduled_scan_heartbeat"],
                {
                    "status": "completed",
                    "run_completed_at_utc": "2026-06-05T18:00:00Z",
                    "host": "KaesDevice",
                    "commit_sha": "abc123",
                },
            )
            report = audit.build_report(
                artifact_paths=paths,
                fill_attempts_path=fill_attempts,
                generated_at_utc="2026-06-10T18:00:00Z",
            )

        self.assertEqual(report["scheduled_scan_health"]["state"], "fail")
        self.assertEqual(report["scheduled_scan_health"]["days_since_last_scheduled_scan"], 3)
        self.assertEqual(report["summary"]["scheduled_scan_heartbeat_state"], "fail")

    def test_autoresearch_search_effort_is_visible_when_scoreboard_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root)
            paths["regular_options_autoresearch_scoreboard"] = root / "autoresearch_latest.json"
            _write_json(
                paths["regular_options_autoresearch_scoreboard"],
                {
                    "evaluator_version": "regular-options-autoresearch-v2",
                    "search_effort": {
                        "strategy_family": "lane_a",
                        "variant_id": "lane_a_goal_51",
                        "variants_searched": 51,
                        "selection_adjusted_bar": 1.28,
                        "selection_adjustment_formula": "1.0 + 0.05 * log2(max(variants_searched, 1))",
                        "selection_adjustment_metric": "pf_lb_5pct",
                    },
                    "metrics": {
                        "pf_lb_5pct": 1.12,
                        "statistical_confidence": "underpowered",
                        "selection_adjusted_confidence": "below_selection_adjusted_bar",
                    },
                },
            )

            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)
            markdown = audit.render_markdown(report)

        metrics = report["autoresearch_search_effort"]["metrics"]
        self.assertEqual(metrics["variants_searched"], 51)
        self.assertEqual(metrics["selection_adjusted_bar"], 1.28)
        self.assertEqual(report["summary"]["autoresearch_search_effort_status"], "available")
        self.assertIn("## Autoresearch Search Effort", markdown)
        self.assertIn("1.0 + 0.05 * log2", markdown)

    def test_markdown_renders_core_tables_and_read_only_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, fill_attempts = self._fixture(Path(tmp))
            report = audit.build_report(artifact_paths=paths, fill_attempts_path=fill_attempts)
            markdown = audit.render_markdown(report)

        self.assertIn("## Lane Leaderboard", markdown)
        self.assertIn("## Lane Dispositions", markdown)
        self.assertIn("paper_shadow", markdown)
        self.assertIn("## Worst Buckets", markdown)
        self.assertIn("## Candidate Rules", markdown)
        self.assertIn("## Execution Realism", markdown)
        self.assertIn("Minute-exit readiness", markdown)
        self.assertIn("does not create trades", markdown)
        self.assertIn("read-only", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, fill_attempts = self._fixture(root / "inputs")
            report = audit.build_report(
                artifact_paths=paths,
                fill_attempts_path=fill_attempts,
                generated_at_utc="2026-06-06T01:00:00Z",
            )
            artifacts = audit.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "monthly-all-lanes-profitability-audit.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], audit.REPORT_ID)
            self.assertEqual(latest["status"], "monthly_profitability_readback")


if __name__ == "__main__":
    unittest.main()
