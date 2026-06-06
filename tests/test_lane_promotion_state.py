from __future__ import annotations

import unittest
from datetime import UTC, datetime

from scripts.lane_promotion_state import (
    LANE_PROMOTION_DIAGNOSTIC_STATUS,
    LANE_PROMOTION_PAPER_EVIDENCE_STATUS,
    PROMOTION_STATE_DIAGNOSTIC,
    PROMOTION_STATE_LIVE_VALIDATION,
    PROMOTION_STATE_PAPER_PROBATION,
    build_lane_promotion_state,
    candidate_promotion_decision,
    lane_promotion_report_health,
)


NOW = datetime(2026, 6, 5, 15, 0, tzinfo=UTC)


def _lane_gate_report(*, volatility_allowed: bool = True) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-06-05T14:00:00Z",
        "summary": {
            "mark_unpriced_count": 0,
            "tracked_row_count": 0,
            "tracked_rows_with_stored_pnl": 0,
        },
        "lane_gates": {
            "swing": {
                "status": "diagnostic_only_unprofitable_lane",
                "auto_track_allowed": False,
                "blockers": ["profit_factor_below_lane_gate"],
                "metrics": {"priced": 20, "profit_factor": 0.4, "avg_net_pnl_pct": -12.0},
            },
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": volatility_allowed,
                "blockers": [],
                "metrics": {"priced": 24, "profit_factor": 1.72, "avg_net_pnl_pct": 6.75},
                "self_guardrails": {"max_debit_pct_of_width": 45.0},
            },
        },
    }


def _filter_matrix(*, later_rows: int) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-06-05T14:05:00Z",
        "scenarios": [
            {
                "scenario_id": "current_lane_gate_self_guardrails",
                "status": "active_safety_gate_paper_probation",
                "entry_time_only": True,
                "later_date_read": {
                    "later_date_rows": later_rows,
                    "later_date_profit_factor": 3.48,
                    "survives_later_date_split": True,
                },
            }
        ],
    }


def _fresh_evidence(*, exact_rows: int = 0, ready_rows: int = 0, legacy: bool = False) -> dict[str, object]:
    candidates = []
    for index in range(exact_rows):
        candidates.append(
            {
                "playbook_id": "volatility_expansion_observation",
                "candidate_status": "live_validation_attempted" if legacy else "paper_exact_evidence_attempted",
                "promotion_gate_context": "legacy_pre_promotion_state_gate" if legacy else "current_lane_promotion_state_payload",
                "lane_promotion_state": None if legacy else {"promotion_state": "paper_probation"},
                "validation_outcome": "created",
                "entry_evidence_status": "fresh_executable_exact_entry",
                "realized_pnl_status": "exact_realized_pnl_available",
                "promotion_discussion_ready": index < ready_rows,
            }
        )
    return {
        "generated_at_utc": "2026-06-05T14:10:00Z",
        "candidates": candidates,
    }


def _open_risk(*, blocked: bool = False, missing_governor: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "generated_at_utc": "2026-06-05T14:20:00Z",
        "scope": "regular_supervised_open_positions_read_only",
        "by_record_class": {"live_exact_tracked": {"negative": 1 if blocked else 0}},
        "top_negative_open_positions": [
            {
                "record_class": "live_exact_tracked",
                "lane": "volatility_expansion_observation",
                "pnl_pct": -39.86,
            }
        ]
        if blocked
        else [],
    }
    if not missing_governor:
        payload["open_risk_governor"] = {
            "status": "open_risk_governor_blocked" if blocked else "open_risk_governor_pass",
            "live_entry_allowed": not blocked,
            "blockers": ["live_exact_negative_open_risk"] if blocked else [],
            "live_exact_negative_ids": [537] if blocked else [],
        }
    return payload


class LanePromotionStateTests(unittest.TestCase):
    def test_profitable_lane_stays_paper_probation_without_forward_depth(self) -> None:
        report = build_lane_promotion_state(
            lane_gate_report=_lane_gate_report(),
            filter_matrix=_filter_matrix(later_rows=2),
            fresh_evidence=_fresh_evidence(exact_rows=0, ready_rows=0),
            open_risk=_open_risk(blocked=True),
            circuit_breaker={"generated_at_utc": "2026-06-05T14:25:00Z", "lane_routes": []},
            generated_at_utc="2026-06-05T14:30:00Z",
            now_utc=NOW,
        )

        volatility = report["lane_states"]["volatility_expansion_observation"]
        swing = report["lane_states"]["swing"]
        self.assertEqual(volatility["promotion_state"], PROMOTION_STATE_PAPER_PROBATION)
        self.assertEqual(volatility["candidate_status"], LANE_PROMOTION_PAPER_EVIDENCE_STATUS)
        self.assertIn("fresh_paper_cohort_insufficient", volatility["blockers"])
        self.assertIn("current_live_exact_risk_governor_blocked", volatility["blockers"])
        self.assertEqual(swing["promotion_state"], PROMOTION_STATE_DIAGNOSTIC)
        self.assertEqual(swing["candidate_status"], LANE_PROMOTION_DIAGNOSTIC_STATUS)

        decision = candidate_promotion_decision(
            playbook_id="volatility_expansion_observation",
            report=report,
            require_fresh_report=True,
            now_utc=NOW,
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["candidate_status"], LANE_PROMOTION_PAPER_EVIDENCE_STATUS)

    def test_lane_can_enter_live_validation_only_after_all_promotion_gates_pass(self) -> None:
        report = build_lane_promotion_state(
            lane_gate_report=_lane_gate_report(),
            filter_matrix=_filter_matrix(later_rows=12),
            fresh_evidence=_fresh_evidence(exact_rows=20, ready_rows=10),
            open_risk=_open_risk(blocked=False),
            circuit_breaker={"generated_at_utc": "2026-06-05T14:25:00Z", "lane_routes": []},
            generated_at_utc="2026-06-05T14:30:00Z",
            now_utc=NOW,
        )

        volatility = report["lane_states"]["volatility_expansion_observation"]
        self.assertEqual(volatility["promotion_state"], PROMOTION_STATE_LIVE_VALIDATION)
        self.assertEqual(volatility["failed_promotion_gates"], [])

        decision = candidate_promotion_decision(
            playbook_id="volatility_expansion_observation",
            report=report,
            require_fresh_report=True,
            now_utc=NOW,
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["candidate_status"], "pending_live_validation")

    def test_missing_open_risk_governor_keeps_lane_in_paper_probation(self) -> None:
        report = build_lane_promotion_state(
            lane_gate_report=_lane_gate_report(),
            filter_matrix=_filter_matrix(later_rows=12),
            fresh_evidence=_fresh_evidence(exact_rows=20, ready_rows=10),
            open_risk=_open_risk(missing_governor=True),
            circuit_breaker={"generated_at_utc": "2026-06-05T14:25:00Z", "lane_routes": []},
            generated_at_utc="2026-06-05T14:30:00Z",
            now_utc=NOW,
        )

        volatility = report["lane_states"]["volatility_expansion_observation"]
        self.assertEqual(volatility["promotion_state"], PROMOTION_STATE_PAPER_PROBATION)
        self.assertIn("open_risk_report_stale_or_unusable", volatility["blockers"])
        self.assertEqual(report["input_health"]["open_risk_report"]["reason"], "open_risk_report_missing_governor")

    def test_legacy_pre_promotion_fresh_rows_do_not_satisfy_paper_cohort(self) -> None:
        report = build_lane_promotion_state(
            lane_gate_report=_lane_gate_report(),
            filter_matrix=_filter_matrix(later_rows=12),
            fresh_evidence=_fresh_evidence(exact_rows=20, ready_rows=10, legacy=True),
            open_risk=_open_risk(blocked=False),
            circuit_breaker={"generated_at_utc": "2026-06-05T14:25:00Z", "lane_routes": []},
            generated_at_utc="2026-06-05T14:30:00Z",
            now_utc=NOW,
        )

        volatility = report["lane_states"]["volatility_expansion_observation"]
        self.assertEqual(volatility["promotion_state"], PROMOTION_STATE_PAPER_PROBATION)
        self.assertIn("fresh_paper_cohort_insufficient", volatility["blockers"])
        self.assertEqual(volatility["fresh_evidence"]["legacy_pre_promotion_state_gate_count"], 20)
        self.assertEqual(volatility["fresh_evidence"]["exact_realized_pnl_count"], 0)

    def test_promotion_report_health_fails_closed_when_missing(self) -> None:
        health = lane_promotion_report_health(None, now_utc=NOW)

        self.assertFalse(health["usable"])
        self.assertEqual(health["reason"], "lane_promotion_state_report_missing")


if __name__ == "__main__":
    unittest.main()
