from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_trade_qualification as triage


NOW = "2026-06-17T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _base_payloads(generated_at: str = NOW) -> dict[str, dict]:
    return {
        "gateboard": {
            "report_id": "project_operator_gateboard",
            "generated_at_utc": generated_at,
            "overall_status": "safe_blocked_no_live_release",
            "no_chase_manifest": {
                "status": "no_chase_active",
                "prohibited_actions": ["do_not_chase_no_chase_manifest"],
            },
        },
        "monthly_profitability": {
            "report_id": "monthly_all_lanes_profitability_audit",
            "generated_at_utc": generated_at,
            "status": "monthly_profitability_readback",
            "risk_portfolio": {"open_risk_status": "open_risk_governor_blocked", "live_entry_allowed": False},
            "prohibited_actions": ["do_not_trade_from_monthly_readback"],
            "lane_dispositions": {
                "dispositions": [
                    {
                        "lane": "historical_positive",
                        "disposition": "retest",
                        "promotion_state": None,
                        "priced": 40,
                        "profit_factor": 1.5,
                        "avg_net_pnl_pct": 8.0,
                        "operator_next_step": "collect more evidence",
                        "blockers": [],
                    },
                    {
                        "lane": "quarantined_lane",
                        "disposition": "quarantine",
                        "priced": 50,
                        "profit_factor": 0.2,
                        "avg_net_pnl_pct": -20.0,
                        "blockers": ["profit_factor_below_lane_gate"],
                    },
                    {
                        "lane": "replay_lane",
                        "disposition": "needs_replay_engine",
                        "priced": 12,
                        "profit_factor": 1.2,
                        "avg_net_pnl_pct": 3.0,
                        "blockers": ["source_replay_required"],
                    },
                    {
                        "lane": "paper_lane",
                        "disposition": "paper_shadow",
                        "promotion_state": "paper_probation",
                        "priced": 35,
                        "profit_factor": 1.8,
                        "avg_net_pnl_pct": 6.5,
                        "blockers": ["fresh_paper_cohort"],
                    },
                ]
            },
            "lane_leaderboard": [
                {"lane": "paper_lane", "median_net_pnl_pct": 2.0, "win_rate_pct": 52.0},
                {"lane": "historical_positive", "median_net_pnl_pct": 1.0, "win_rate_pct": 55.0},
            ],
        },
        "lane_promotion_state": {
            "report_id": "regular_options_lane_promotion_state",
            "generated_at_utc": generated_at,
            "status": "lane_promotion_state_readback",
            "summary": {
                "live_validation_lane_count": 0,
                "auto_track_lane_count": 0,
                "open_risk_governor_status": "open_risk_governor_blocked",
                "open_risk_governor_blockers": ["live_exact_negative_open_risk"],
            },
        },
        "candidate_outcome_ledger": {
            "report_id": "regular_options_candidate_outcome_ledger",
            "generated_at_utc": generated_at,
            "summary": {
                "exact_realized_pnl_count": 0,
                "promotion_discussion_ready_count": 0,
                "paper_shortlist_eligible_count": 0,
                "open_risk_status": "open_risk_governor_blocked",
                "open_risk_live_entry_allowed": False,
                "action_counts": {
                    "collect_exact_exit_evidence": 1,
                    "capture_missing_fill_attempt_evidence": 2,
                    "refresh_suggested_trade_review": 1,
                },
            },
        },
        "fresh_evidence_loop": {
            "report_id": "regular_options_fresh_evidence_loop",
            "generated_at_utc": generated_at,
            "summary": {
                "entry_evidence_status_counts": {"fresh_executable_exact_entry": 1},
                "exact_realized_pnl_count": 0,
                "promotion_discussion_ready_count": 0,
                "exact_exit_bridge_count": 1,
            },
            "candidates": [
                {
                    "playbook_id": "paper_lane",
                    "scan_date": "2026-06-16",
                    "entry_evidence_status": "fresh_executable_exact_entry",
                    "realized_pnl_status": "missing_realized_pnl",
                }
            ],
        },
        "paper_shortlist": {
            "generated_at_utc": generated_at,
            "summary": {"eligible_count": 0},
        },
        "profit_capture_queue": {
            "generated_at_utc": generated_at,
            "summary": {"selection_readiness_counts": {"paper_review_candidate": 3}},
        },
        "repair_burndown": {
            "generated_at_utc": generated_at,
            "summary": {"active_exact_repair_target_count": 2, "source_replay_required_target_count": 1},
        },
        "open_position_risk": {
            "generated_at_utc": generated_at,
            "open_risk_governor": {
                "status": "open_risk_governor_blocked",
                "live_entry_allowed": False,
                "blockers": ["live_exact_negative_open_risk"],
            },
        },
        "suggested_trade_close_risk": {
            "generated_at_utc": generated_at,
            "attention_trade_ids": [138],
            "attention_trades": [{"id": 138, "next_safe_action": "refresh_review"}],
        },
        "open_risk_resolution_plan": {
            "generated_at_utc": generated_at,
            "summary": {"open_risk_status": "open_risk_governor_blocked"},
        },
        "fill_attempt_evidence_capture_plan": {
            "generated_at_utc": generated_at,
            "summary": {"missing_fill_attempt_evidence_count": 2},
        },
        "suggested_trade_review_plan": {
            "generated_at_utc": generated_at,
            "summary": {"attention_trade_count": 1},
        },
        "historical_walk_forward": {
            "generated_at_utc": generated_at,
            "status": "historical_walkforward_ran_candidates_blocked",
        },
        "robust_search_evaluation": {
            "generated_at_utc": generated_at,
            "status": "historical_candidates_blocked",
        },
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _base_payloads()
    paths = {
        "gateboard_path": root / "gateboard.json",
        "monthly_profitability_path": root / "monthly.json",
        "lane_promotion_path": root / "lane-promotion.json",
        "candidate_ledger_path": root / "candidate-ledger.json",
        "fresh_evidence_path": root / "fresh.json",
        "paper_shortlist_path": root / "paper-shortlist.json",
        "profit_capture_queue_path": root / "profit-queue.json",
        "repair_burndown_path": root / "repair.json",
        "open_risk_path": root / "open-risk.json",
        "suggested_close_risk_path": root / "suggested-risk.json",
        "open_risk_plan_path": root / "open-risk-plan.json",
        "fill_attempt_plan_path": root / "fill-plan.json",
        "suggested_review_plan_path": root / "suggested-plan.json",
        "walk_forward_path": root / "walk-forward.json",
        "robust_search_path": root / "robust.json",
    }
    payload_key = {
        "gateboard_path": "gateboard",
        "monthly_profitability_path": "monthly_profitability",
        "lane_promotion_path": "lane_promotion_state",
        "candidate_ledger_path": "candidate_outcome_ledger",
        "fresh_evidence_path": "fresh_evidence_loop",
        "paper_shortlist_path": "paper_shortlist",
        "profit_capture_queue_path": "profit_capture_queue",
        "repair_burndown_path": "repair_burndown",
        "open_risk_path": "open_position_risk",
        "suggested_close_risk_path": "suggested_trade_close_risk",
        "open_risk_plan_path": "open_risk_resolution_plan",
        "fill_attempt_plan_path": "fill_attempt_evidence_capture_plan",
        "suggested_review_plan_path": "suggested_trade_review_plan",
        "walk_forward_path": "historical_walk_forward",
        "robust_search_path": "robust_search_evaluation",
    }
    for arg_name, path in paths.items():
        key = payload_key[arg_name]
        if key in payloads:
            _write_json(path, payloads[key])
    return paths


class RegularOptionsTradeQualificationTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **overrides):
        paths = _write_sources(root, payloads)
        paths.update(overrides)
        return triage.build_report(generated_at_utc=NOW, **paths)

    def test_missing_gateboard_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payloads = _base_payloads()
            payloads.pop("gateboard")
            report = self._build(root, payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertFalse(report["live_entry_allowed"])
        self.assertEqual(report["source_artifacts"]["gateboard"]["status"], "missing")

    def test_malformed_json_fails_closed_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["gateboard_path"].write_text("{bad", encoding="utf8")
            report = triage.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["gateboard"]["status"], "malformed")

    def test_live_release_blocked_gateboard_forces_live_and_autotrack_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])
        self.assertFalse(report["broker_order_allowed"])

    def test_open_risk_blocked_forces_no_new_scanner_origin_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertEqual(report["open_risk_status"]["status"], "open_risk_governor_blocked")
        self.assertFalse(report["open_risk_status"]["new_scanner_origin_entries_allowed"])

    def test_zero_exact_realized_pnl_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertEqual(report["exact_realized_pnl_count"], 0)
        self.assertEqual(report["promotion_ready_count"], 0)
        self.assertFalse(report["live_entry_allowed"])

    def test_positive_historical_lane_without_fresh_exact_realized_is_not_live(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        lanes = {row["lane_id"]: row for row in report["lane_decisions"]}
        self.assertIn(lanes["historical_positive"]["decision"], {"paper_shadow_collect", "evidence_repair_only"})
        self.assertNotEqual(lanes["historical_positive"]["decision"], "live_blocked")
        self.assertIn("positive_historical_lane_without_fresh_exact_realized_pnl", lanes["historical_positive"]["reason_codes"])

    def test_quarantined_lane_becomes_quarantine_no_chase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        lanes = {row["lane_id"]: row for row in report["lane_decisions"]}
        self.assertEqual(lanes["quarantined_lane"]["decision"], "quarantine_no_chase")

    def test_needs_replay_engine_lane_becomes_needs_replay_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        lanes = {row["lane_id"]: row for row in report["lane_decisions"]}
        self.assertEqual(lanes["replay_lane"]["decision"], "needs_replay_engine")

    def test_no_chase_active_copies_prohibited_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertTrue(report["no_chase_active"])
        self.assertIn("do_not_chase_no_chase_manifest", report["prohibited_actions"])
        self.assertIn("do_not_trade_from_monthly_readback", report["prohibited_actions"])

    def test_suggested_trade_attention_is_review_action_not_trade_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        actions = {item["action"]: item for item in report["operator_queue"]}
        self.assertIn("refresh_suggested_trade_reviews", actions)
        self.assertFalse(actions["refresh_suggested_trade_reviews"]["trade_recommendation"])
        self.assertIn("not a trade recommendation", actions["refresh_suggested_trade_reviews"]["operator_next_step"])

    def test_stale_source_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payloads = _base_payloads(generated_at="2026-06-10T00:00:00Z")
            report = self._build(root, payloads, max_source_age_hours=24)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertIn("stale_readback", report["source_artifacts"]["gateboard"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
