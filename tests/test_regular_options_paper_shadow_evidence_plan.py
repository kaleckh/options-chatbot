from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_paper_shadow_evidence_plan as plan


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
            "broker_order_allowed": False,
            "exact_realized_pnl_count": 0,
            "promotion_ready_count": 0,
            "best_current_lane_if_any": {
                "lane_id": "paper_lane",
                "decision": "paper_shadow_collect",
                "profit_factor": 1.7,
                "avg_net_pnl_pct": 6.0,
                "fresh_exact_entry_count": 1,
                "exact_realized_pnl_count": 0,
            },
            "open_risk_status": {"status": "open_risk_governor_pass", "reason_codes": []},
            "lane_decisions": [
                {
                    "lane_id": "paper_lane",
                    "decision": "paper_shadow_collect",
                    "disposition": "paper_shadow",
                    "promotion_state": "paper_probation",
                    "reason_codes": ["fresh_paper_cohort"],
                },
                {
                    "lane_id": "quarantined_lane",
                    "decision": "quarantine_no_chase",
                    "disposition": "quarantine",
                    "promotion_state": None,
                    "reason_codes": ["profit_factor_below_lane_gate"],
                },
            ],
            "required_evidence_before_promotion": ["fresh exact entry", "fresh exact exit"],
            "prohibited_actions": ["do_not_submit_broker_order_from_trade_qualification"],
        },
        "gateboard": {
            "generated_at_utc": generated_at,
            "overall_status": "safe_blocked_no_live_release",
            "no_chase_manifest": {"status": "no_chase_active", "prohibited_actions": ["do_not_chase"]},
        },
        "monthly_profitability": {
            "generated_at_utc": generated_at,
            "prohibited_actions": ["do_not_trade_from_monthly"],
        },
        "lane_promotion_state": {
            "generated_at_utc": generated_at,
            "summary": {"open_risk_governor_status": "open_risk_governor_pass"},
        },
        "candidate_outcome_ledger": {
            "generated_at_utc": generated_at,
            "summary": {
                "exact_realized_pnl_count": 0,
                "promotion_discussion_ready_count": 0,
                "open_risk_status": "open_risk_governor_pass",
            },
            "ledger_rows": [
                {
                    "ledger_key": "fresh:exit",
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "lane_id": "paper_lane",
                    "ticker": "QQQ",
                    "position_id": 537,
                    "candidate_key": "candidate-exit",
                    "scan_date": "2026-06-05",
                    "blocking_reasons": ["missing_realized_pnl"],
                    "action_reason": "linked_position_has_missing_realized_pnl",
                },
                {
                    "ledger_key": "fresh:entry",
                    "next_evidence_action": "capture_paper_only_exact_entry",
                    "lane_id": "paper_lane",
                    "ticker": "SPY",
                    "candidate_key": "candidate-entry",
                    "scan_date": "2026-06-05",
                    "blocking_reasons": ["no_fill_attempt_logged"],
                    "action_reason": "paper_candidate_requires_entry",
                },
            ],
        },
        "fresh_evidence_loop": {
            "generated_at_utc": generated_at,
            "summary": {"exact_realized_pnl_count": 0, "promotion_discussion_ready_count": 0},
            "candidates": [],
        },
        "fill_attempt_evidence_capture_plan": {
            "generated_at_utc": generated_at,
            "plan_rows": [
                {
                    "ledger_key": "fresh:fill",
                    "candidate_key": "candidate-fill",
                    "lane_id": "paper_lane",
                    "ticker": "IWM",
                    "scan_date": "2026-06-05",
                    "blocking_reasons": ["entry_status:fill_attempt_missing"],
                    "market_window_required": True,
                    "operator_next_step": "capture durable fill attempt",
                }
            ],
        },
        "suggested_trade_review_plan": {
            "generated_at_utc": generated_at,
            "plan_rows": [
                {
                    "suggested_trade_id": 138,
                    "lane": "legacy_unlabeled",
                    "ticker": "AAA",
                    "action_bucket": "no_stored_review",
                    "evidence_bucket": "missing_review",
                    "resolution_status": "market_window_required_missing_suggested_trade_review",
                    "market_window_required": True,
                    "operator_next_step": "refresh suggested review",
                }
            ],
        },
        "open_position_risk": {
            "generated_at_utc": generated_at,
            "open_risk_governor": {"status": "open_risk_governor_pass", "live_entry_allowed": True, "blockers": []},
        },
        "suggested_trade_close_risk": {
            "generated_at_utc": generated_at,
            "attention_trade_ids": [138],
            "attention_trades": [{"id": 138}],
        },
        "paper_shortlist": {
            "generated_at_utc": generated_at,
            "summary": {"eligible_count": 0},
        },
        "profit_capture_queue": {
            "generated_at_utc": generated_at,
            "evidence_repair_queue": [
                {
                    "lane_id": "repair_lane",
                    "symbol": "NEM",
                    "reason_codes": ["unresolved_rows_remain"],
                    "repair_actionability": {
                        "status": "needs_status_or_forward_validation_after_repair",
                        "next_action": "repair active target",
                    },
                }
            ],
        },
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _base_payloads()
    paths = {
        "trade_qualification_path": root / "trade-qualification.json",
        "gateboard_path": root / "gateboard.json",
        "monthly_profitability_path": root / "monthly.json",
        "lane_promotion_path": root / "lane-promotion.json",
        "candidate_ledger_path": root / "candidate-ledger.json",
        "fresh_evidence_path": root / "fresh.json",
        "fill_attempt_plan_path": root / "fill-plan.json",
        "suggested_review_plan_path": root / "suggested-plan.json",
        "open_risk_path": root / "open-risk.json",
        "suggested_close_risk_path": root / "suggested-risk.json",
        "paper_shortlist_path": root / "paper-shortlist.json",
        "profit_capture_queue_path": root / "profit-queue.json",
    }
    key_map = {
        "trade_qualification_path": "trade_qualification",
        "gateboard_path": "gateboard",
        "monthly_profitability_path": "monthly_profitability",
        "lane_promotion_path": "lane_promotion_state",
        "candidate_ledger_path": "candidate_outcome_ledger",
        "fresh_evidence_path": "fresh_evidence_loop",
        "fill_attempt_plan_path": "fill_attempt_evidence_capture_plan",
        "suggested_review_plan_path": "suggested_trade_review_plan",
        "open_risk_path": "open_position_risk",
        "suggested_close_risk_path": "suggested_trade_close_risk",
        "paper_shortlist_path": "paper_shortlist",
        "profit_capture_queue_path": "profit_capture_queue",
    }
    for arg_name, path in paths.items():
        key = key_map[arg_name]
        if key in payloads:
            _write_json(path, payloads[key])
    return paths


class RegularOptionsPaperShadowEvidencePlanTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **overrides):
        paths = _write_sources(root, payloads)
        paths.update(overrides)
        return plan.build_report(generated_at_utc=NOW, **paths)

    def test_missing_trade_qualification_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads.pop("trade_qualification")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["trade_qualification"]["status"], "missing")

    def test_malformed_json_fails_closed_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["trade_qualification_path"].write_text("{bad", encoding="utf8")
            report = plan.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["trade_qualification"]["status"], "malformed")

    def test_broker_order_allowed_is_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["broker_order_allowed"])
        self.assertTrue(all(action["is_broker_order"] is False for action in report["operator_actions"]))

    def test_every_action_is_not_trade_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertTrue(report["operator_actions"])
        self.assertTrue(all(action["is_trade_recommendation"] is False for action in report["operator_actions"]))

    def test_open_risk_blocked_blocks_new_scanner_origin_entry_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["open_position_risk"]["open_risk_governor"] = {
                "status": "open_risk_governor_blocked",
                "live_entry_allowed": False,
                "blockers": ["live_exact_negative_open_risk"],
            }
            payloads["trade_qualification"]["open_risk_status"] = {"status": "open_risk_governor_blocked"}
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_open_risk")
        entry_actions = [row for row in report["operator_actions"] if row["action_type"] == "collect_exact_entry_evidence"]
        self.assertTrue(entry_actions)
        self.assertTrue(all(row["status"] == "blocked_by_open_risk" for row in entry_actions))

    def test_linked_exact_row_waits_for_policy_exit_not_forced_close(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        exit_actions = [row for row in report["operator_actions"] if row["action_type"] == "collect_exact_exit_evidence"]
        self.assertEqual(len(exit_actions), 1)
        self.assertEqual(exit_actions[0]["status"], "waiting_for_policy_exit")
        self.assertTrue(exit_actions[0]["requires_policy_exit_condition"])
        self.assertIn("do not force a close", exit_actions[0]["next_operator_step"])

    def test_missing_fill_attempt_row_becomes_capture_fill_attempt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        fill_actions = [row for row in report["operator_actions"] if row["action_type"] == "capture_fill_attempt_evidence"]
        self.assertEqual(len(fill_actions), 1)
        self.assertTrue(fill_actions[0]["requires_fill_attempt_evidence"])

    def test_suggested_trade_attention_becomes_review_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        suggested_actions = [row for row in report["operator_actions"] if row["action_type"] == "refresh_suggested_trade_review"]
        self.assertEqual(len(suggested_actions), 1)
        self.assertEqual(suggested_actions[0]["status"], "review_only")
        self.assertFalse(suggested_actions[0]["is_trade_recommendation"])

    def test_quarantined_lane_becomes_no_chase_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        quarantine_actions = [row for row in report["operator_actions"] if row["action_type"] == "no_chase_quarantine"]
        self.assertEqual(len(quarantine_actions), 1)
        self.assertEqual(quarantine_actions[0]["lane_id"], "quarantined_lane")

    def test_no_actionable_rows_produces_waiting_for_fresh_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["candidate_outcome_ledger"]["ledger_rows"] = []
            payloads["fill_attempt_evidence_capture_plan"]["plan_rows"] = []
            payloads["suggested_trade_review_plan"]["plan_rows"] = []
            payloads["profit_capture_queue"]["evidence_repair_queue"] = []
            payloads["trade_qualification"]["lane_decisions"] = [
                {
                    "lane_id": "paper_lane",
                    "decision": "paper_shadow_collect",
                    "disposition": "paper_shadow",
                    "promotion_state": "paper_probation",
                    "reason_codes": [],
                }
            ]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "waiting_for_fresh_candidates")
        self.assertTrue(any(row["action_type"] == "wait_for_fresh_candidate" for row in report["operator_actions"]))

    def test_stale_source_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads(generated_at="2026-06-10T00:00:00Z")
            report = self._build(Path(temp_dir), payloads, max_source_age_hours=24)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertIn("stale_readback", report["source_artifacts"]["trade_qualification"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
