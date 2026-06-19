from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_market_window_evidence_checklist as checklist


NOW = "2026-06-17T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _base_payloads(generated_at: str = NOW) -> dict[str, dict]:
    return {
        "trade_qualification": {
            "generated_at_utc": generated_at,
            "overall_status": "blocked_no_live_release",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": True,
            "exact_realized_pnl_count": 0,
            "promotion_ready_count": 0,
            "open_risk_status": {"status": "open_risk_governor_pass"},
            "best_current_lane_if_any": {"lane_id": "paper_lane", "decision": "paper_shadow_collect"},
            "required_evidence_before_promotion": ["fresh exact entry", "fresh exact exit"],
            "prohibited_actions": ["do_not_submit_broker_order_from_trade_qualification"],
        },
        "paper_shadow_evidence_plan": {
            "generated_at_utc": generated_at,
            "overall_status": "paper_shadow_evidence_collecting",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": True,
            "best_evidence_lane": {
                "lane_id": "paper_lane",
                "decision": "paper_shadow_collect",
                "promotion_state": "paper_probation",
            },
            "required_evidence_before_promotion": ["exact realized pnl"],
            "operator_actions": [
                {
                    "action_id": "exit:537",
                    "priority": 2,
                    "action_type": "collect_exact_exit_evidence",
                    "lane_id": "paper_lane",
                    "ticker": "QQQ",
                    "position_id": 537,
                    "candidate_id": "candidate-exit",
                    "status": "waiting_for_policy_exit",
                    "reason_codes": ["linked_position_missing_exact_exit"],
                    "market_window_required": True,
                    "requires_policy_exit_condition": True,
                    "requires_exact_exit_evidence": True,
                    "is_trade_recommendation": True,
                    "is_broker_order": True,
                    "next_operator_step": "collect exit only after policy exit",
                },
                {
                    "action_id": "entry:1",
                    "priority": 3,
                    "action_type": "collect_exact_entry_evidence",
                    "lane_id": "paper_lane",
                    "ticker": "SPY",
                    "candidate_id": "candidate-entry",
                    "status": "ready_for_market_window",
                    "reason_codes": ["paper_probation"],
                    "market_window_required": True,
                    "requires_exact_entry_evidence": True,
                    "is_trade_recommendation": True,
                    "is_broker_order": True,
                },
                {
                    "action_id": "fill:1",
                    "priority": 4,
                    "action_type": "capture_fill_attempt_evidence",
                    "lane_id": "paper_lane",
                    "ticker": "IWM",
                    "candidate_id": "candidate-fill",
                    "status": "blocked_missing_fill_attempt",
                    "reason_codes": ["entry_status:fill_attempt_missing"],
                    "market_window_required": True,
                    "requires_fill_attempt_evidence": True,
                },
                {
                    "action_id": "suggested:138",
                    "priority": 5,
                    "action_type": "refresh_suggested_trade_review",
                    "lane_id": "legacy_unlabeled",
                    "ticker": "AAA",
                    "suggested_trade_id": 138,
                    "status": "review_only",
                    "market_window_required": True,
                    "requires_operator_review": True,
                },
                {
                    "action_id": "quarantine:bad_lane",
                    "priority": 7,
                    "action_type": "no_chase_quarantine",
                    "lane_id": "bad_lane",
                    "status": "no_action",
                    "reason_codes": ["profit_factor_below_lane_gate"],
                },
            ],
            "prohibited_actions": ["do_not_submit_broker_order_from_paper_shadow_plan"],
        },
        "gateboard": {
            "generated_at_utc": generated_at,
            "no_chase_manifest": {"status": "no_chase_active", "prohibited_actions": ["do_not_chase"]},
        },
        "monthly_profitability": {"generated_at_utc": generated_at},
        "fill_attempt_evidence_capture_plan": {"generated_at_utc": generated_at},
        "suggested_trade_review_plan": {"generated_at_utc": generated_at},
        "open_position_risk": {
            "generated_at_utc": generated_at,
            "open_risk_governor": {"status": "open_risk_governor_pass", "live_entry_allowed": True},
        },
        "suggested_trade_close_risk": {"generated_at_utc": generated_at},
        "candidate_outcome_ledger": {"generated_at_utc": generated_at},
        "fresh_evidence_loop": {"generated_at_utc": generated_at},
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _base_payloads()
    paths = {
        "trade_qualification_path": root / "trade-qualification.json",
        "paper_shadow_plan_path": root / "paper-shadow.json",
        "gateboard_path": root / "gateboard.json",
        "monthly_profitability_path": root / "monthly.json",
        "fill_attempt_plan_path": root / "fill.json",
        "suggested_review_plan_path": root / "suggested-review.json",
        "open_risk_path": root / "open-risk.json",
        "suggested_close_risk_path": root / "suggested-close-risk.json",
        "candidate_ledger_path": root / "candidate-ledger.json",
        "fresh_evidence_path": root / "fresh.json",
    }
    key_map = {
        "trade_qualification_path": "trade_qualification",
        "paper_shadow_plan_path": "paper_shadow_evidence_plan",
        "gateboard_path": "gateboard",
        "monthly_profitability_path": "monthly_profitability",
        "fill_attempt_plan_path": "fill_attempt_evidence_capture_plan",
        "suggested_review_plan_path": "suggested_trade_review_plan",
        "open_risk_path": "open_position_risk",
        "suggested_close_risk_path": "suggested_trade_close_risk",
        "candidate_ledger_path": "candidate_outcome_ledger",
        "fresh_evidence_path": "fresh_evidence_loop",
    }
    for arg_name, path in paths.items():
        key = key_map[arg_name]
        if key in payloads:
            _write_json(path, payloads[key])
    return paths


class RegularOptionsMarketWindowEvidenceChecklistTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **overrides):
        paths = _write_sources(root, payloads)
        paths.update(overrides)
        return checklist.build_report(generated_at_utc=NOW, **paths)

    def test_missing_trade_qualification_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads.pop("trade_qualification")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["trade_qualification"]["status"], "missing")

    def test_missing_paper_shadow_evidence_plan_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads.pop("paper_shadow_evidence_plan")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["paper_shadow_evidence_plan"]["status"], "missing")

    def test_malformed_json_fails_closed_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["trade_qualification_path"].write_text("{bad", encoding="utf8")
            report = checklist.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["trade_qualification"]["status"], "malformed")

    def test_broker_order_allowed_is_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["broker_order_allowed"])
        self.assertTrue(all(step["is_broker_order"] is False for step in report["checklist_steps"]))

    def test_is_trade_recommendation_is_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["is_trade_recommendation"])
        self.assertTrue(all(step["is_trade_recommendation"] is False for step in report["checklist_steps"]))

    def test_qqq_537_exit_row_waits_for_policy_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        exit_steps = [step for step in report["checklist_steps"] if step.get("position_id") == 537]
        self.assertEqual(len(exit_steps), 1)
        self.assertEqual(exit_steps[0]["step_type"], "wait_for_policy_exit_condition")
        self.assertEqual(exit_steps[0]["status"], "waiting_for_policy_exit")

    def test_paper_probation_entry_waits_for_market_window_not_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        entry_steps = [step for step in report["checklist_steps"] if step["step_type"] == "collect_exact_entry_evidence"]
        self.assertEqual(len(entry_steps), 1)
        self.assertEqual(entry_steps[0]["status"], "waiting_for_market_window")
        self.assertFalse(entry_steps[0]["is_trade_recommendation"])

    def test_fill_attempt_rows_become_capture_fill_attempt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        fill_steps = [step for step in report["checklist_steps"] if step["step_type"] == "capture_fill_attempt_evidence"]
        self.assertEqual(len(fill_steps), 1)
        self.assertEqual(fill_steps[0]["candidate_id"], "candidate-fill")

    def test_suggested_trade_138_is_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        review_steps = [step for step in report["checklist_steps"] if step.get("suggested_trade_id") == 138]
        self.assertEqual(len(review_steps), 1)
        self.assertEqual(review_steps[0]["step_type"], "refresh_suggested_trade_review")
        self.assertEqual(review_steps[0]["status"], "review_only")
        self.assertFalse(review_steps[0]["is_trade_recommendation"])

    def test_quarantined_lanes_become_no_chase_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        no_chase = [step for step in report["checklist_steps"] if step["step_type"] == "no_chase_quarantine"]
        self.assertEqual(len(no_chase), 1)
        self.assertEqual(no_chase[0]["status"], "blocked_by_no_chase")

    def test_stale_source_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir), _base_payloads(generated_at="2026-06-01T00:00:00Z"))

        self.assertEqual(report["overall_status"], "blocked_stale_readbacks")
        self.assertIn("stale_readback", report["source_artifacts"]["trade_qualification"]["reason_codes"])

    def test_no_actionable_rows_produces_no_evidence_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["paper_shadow_evidence_plan"]["operator_actions"] = []
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_no_evidence_actions")
        wait_steps = [step for step in report["checklist_steps"] if step["step_type"] == "wait_for_fresh_candidate"]
        self.assertTrue(wait_steps)


if __name__ == "__main__":
    unittest.main()
