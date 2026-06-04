from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import build_current_policy_circuit_breaker as breaker
from scripts import pending_audit_candidates as pending
from scripts import validate_pending_scan_candidates as validate_pending


def _cohort(overall_status: str = "paper_only_recent_week_break") -> dict:
    lane_status = "healthy" if overall_status == "healthy" else "paper_only_recent_break"
    return {
        "generated_at_utc": "2026-06-04T20:00:00Z",
        "summary": {
            "overall_status": overall_status,
            "recent_month": "2026-05",
            "recent_week": "2026-W21",
        },
        "lane_monthly": {
            "2026-05:short_term": {
                "priced": 17,
                "avg_pnl_pct": -12.3,
                "median_pnl_pct": -55.41,
                "negative_rate_priced_pct": 70.6,
                "health_status": lane_status,
            },
            "2026-05:bullish_pullback_observation": {
                "priced": 2,
                "avg_pnl_pct": -73.37,
                "median_pnl_pct": -73.37,
                "negative_rate_priced_pct": 100.0,
                "health_status": "healthy" if overall_status == "healthy" else "paper_only_thin_severe",
            },
        },
    }


def _point_in_time(
    *,
    status: str = "paper_only_collecting",
    exact_rows: int = 0,
    matched_exact_rows: int = 0,
    blockers: list[str] | None = None,
) -> dict:
    return {
        "generated_at_utc": "2026-06-04T20:01:00Z",
        "filter": {"filter_id": "short_term_fill_degradation_ge_15", "live_policy_change": False},
        "baseline": {"rows": exact_rows, "exact_priced_rows": exact_rows},
        "matched": {"rows": matched_exact_rows, "exact_priced_rows": matched_exact_rows},
        "effects": {"lost_winners": 0, "avoided_losses": 2},
        "decision_summary": {
            "status": status,
            "promotion_blockers": blockers if blockers is not None else ["insufficient_exact_priced_candidate_rows"],
        },
    }


def _monitor(*, status: str = "collecting", rows: int = 0, matched_rows: int = 0, failures: list[str] | None = None) -> dict:
    return {
        "generated_at_utc": "2026-06-04T20:02:00Z",
        "baseline": {"rows": rows},
        "champion": {
            "filter_id": "short_term_fill_degradation_ge_15",
            "matched": {"rows": matched_rows},
            "kept": {"median_pnl_pct": 18.0, "negative_rate_pct": 20.0},
            "winners_lost": 0,
            "losses_avoided": 2,
        },
        "gate": {
            "status": status,
            "failures": failures if failures is not None else ["insufficient_fresh_rows"],
            "live_policy_change": False,
            "minimum_fresh_rows": 20,
            "minimum_candidate_blocked_rows": 5,
        },
    }


class CurrentPolicyCircuitBreakerTests(unittest.TestCase):
    def test_recent_week_break_routes_affected_lanes_to_paper_validation_only(self) -> None:
        report = breaker.build_report(
            cohort_health=_cohort(),
            point_in_time=_point_in_time(),
            paper_monitor=_monitor(),
        )

        self.assertTrue(report["summary"]["breaker_active"])
        self.assertEqual(report["summary"]["route_status"], "paper_validation_only")
        self.assertEqual(
            breaker.paper_validation_only_playbooks(report),
            {"short_term", "bullish_pullback_observation"},
        )
        self.assertIn("recent_cohort_recovered", report["summary"]["recovery_gate_failures"])
        self.assertIn("fresh_current_policy_rows", report["summary"]["recovery_gate_failures"])
        self.assertFalse(report["summary"]["live_policy_change"])
        self.assertFalse(report["summary"]["lane_deletion"])
        self.assertTrue(all(not route["lane_deleted"] for route in report["lane_routes"]))

    def test_recovery_requires_cohort_recovery_and_all_forward_gates(self) -> None:
        report = breaker.build_report(
            cohort_health=_cohort(overall_status="healthy"),
            point_in_time=_point_in_time(
                status="point_in_time_replay_pass_candidate_not_promoted",
                exact_rows=22,
                matched_exact_rows=5,
                blockers=[],
            ),
            paper_monitor=_monitor(status="paper_pass_candidate", rows=22, matched_rows=5, failures=[]),
        )

        self.assertFalse(report["summary"]["breaker_active"])
        self.assertEqual(report["summary"]["recovery_gate_failures"], [])
        self.assertEqual(report["summary"]["route_status"], "recovery_review_required")
        self.assertEqual(breaker.paper_validation_only_playbooks(report), set())
        self.assertEqual(
            breaker.validation_hold_playbooks(report),
            {"short_term", "bullish_pullback_observation"},
        )

    def test_recovered_label_without_forward_evidence_stays_paper_only(self) -> None:
        report = breaker.build_report(
            cohort_health=_cohort(overall_status="healthy"),
            point_in_time=_point_in_time(),
            paper_monitor=_monitor(),
        )

        self.assertFalse(report["summary"]["breaker_active"])
        self.assertIn("fresh_current_policy_rows", report["summary"]["recovery_gate_failures"])
        self.assertEqual(report["summary"]["route_status"], "paper_validation_only")
        self.assertEqual(
            breaker.validation_hold_playbooks(report),
            {"short_term", "bullish_pullback_observation"},
        )

    def test_circuit_breaker_validation_rows_resolve_as_paper_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            queue = Path(temp_dir) / "pending.jsonl"
            fill_attempts = Path(temp_dir) / "fills.jsonl"
            candidate = {
                "audit_generated_at_utc": "2026-06-04T16:00:00Z",
                "candidate_key": "2026-06-04|short_term|SPY|call|2026-06-26|||760.0|780.0",
                "candidate_status": "pending_live_validation",
                "tracking_approved_lane": True,
                "position_tracking_mode": "auto_track",
                "playbook_id": "short_term",
                "ticker": "SPY",
                "direction": "call",
                "expiry": "2026-06-26",
                "long_strike": 760.0,
                "short_strike": 780.0,
            }
            queue.write_text(json.dumps(candidate) + "\n", encoding="utf8")
            circuit = breaker.build_report(
                cohort_health=_cohort(),
                point_in_time=_point_in_time(),
                paper_monitor=_monitor(),
            )

            appended = pending.append_circuit_breaker_validation_rows(
                [candidate],
                queue_file=queue,
                playbook_id="short_term",
                circuit_breaker=circuit,
                recorded_at_utc="2026-06-04T16:05:00Z",
            )
            disposition = pending.build_validation_disposition_report(
                queue_file=queue,
                fill_attempt_file=fill_attempts,
                scan_date="2026-06-04",
            )

            self.assertEqual(appended, 1)
            self.assertEqual(disposition["summary"]["outcome_counts"], {"paper_only": 1})
            self.assertEqual(disposition["candidates"][0]["outcome"], "paper_only")
            self.assertEqual(
                disposition["candidates"][0]["outcome_reason"],
                "recent_cohort_circuit_breaker_routes_lane_to_paper_validation_only",
            )
            self.assertEqual(
                disposition["candidates"][0]["recent_cohort_circuit_breaker"]["route_status"],
                "paper_validation_only",
            )

    def test_missing_circuit_breaker_fails_closed_before_auto_track_validation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            queue = Path(temp_dir) / "pending.jsonl"
            fill_attempts = Path(temp_dir) / "fills.jsonl"
            disposition = Path(temp_dir) / "disposition.json"
            missing_breaker = Path(temp_dir) / "missing-breaker.json"
            candidate = {
                "audit_generated_at_utc": "2026-06-04T16:00:00Z",
                "candidate_key": "2026-06-04|short_term|SPY|call|2026-06-26|||760.0|780.0",
                "candidate_status": "pending_live_validation",
                "tracking_approved_lane": True,
                "position_tracking_mode": "auto_track",
                "playbook_id": "short_term",
                "ticker": "SPY",
                "direction": "call",
                "expiry": "2026-06-26",
                "long_strike": 760.0,
                "short_strike": 780.0,
            }
            queue.write_text(json.dumps(candidate) + "\n", encoding="utf8")

            with patch.object(validate_pending, "_market_is_open_now", return_value=True), patch.object(
                validate_pending,
                "_run_playbook_validation",
                side_effect=AssertionError("affected lane should not enter auto-track validation"),
            ):
                exit_code = validate_pending.main(
                    [
                        "--date",
                        "2026-06-04",
                        "--queue-file",
                        str(queue),
                        "--fill-attempt-file",
                        str(fill_attempts),
                        "--disposition-file",
                        str(disposition),
                        "--circuit-breaker",
                        str(missing_breaker),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = json.loads(disposition.read_text(encoding="utf8"))
            self.assertEqual(report["summary"]["outcome_counts"], {"paper_only": 1})
            self.assertEqual(
                report["candidates"][0]["outcome_reason"],
                "circuit_breaker_missing_or_unavailable_routes_lane_to_paper_validation_only",
            )

    def test_empty_lane_routes_fail_closed(self) -> None:
        malformed = {"lane_routes": []}

        self.assertEqual(
            breaker.paper_validation_only_playbooks(malformed),
            {"short_term", "bullish_pullback_observation"},
        )
        self.assertEqual(
            breaker.validation_hold_playbooks(malformed),
            {"short_term", "bullish_pullback_observation"},
        )


if __name__ == "__main__":
    unittest.main()
