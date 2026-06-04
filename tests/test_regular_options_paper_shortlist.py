from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_paper_shortlist as paper_shortlist
from scripts import build_regular_options_profit_capture_queue as capture_queue


def _fresh_row(**overrides):
    row = {
        "symbol": "SPY",
        "playbook_id": "swing",
        "direction": "call",
        "expiry": "2026-06-26",
        "guardrail_decision": "clear",
        "match_type": "lane_signature",
        "fresh_executable_quote_window": True,
        "candidate_execution_label": "executable_opra_paper_candidate",
        "debit_pct_of_width": 37.9,
        "quality_score": 97.9,
        "matched_sleeves": [
            {
                "symbol": "SPY",
                "lane_id": "swing",
                "capture_tier": capture_queue.TIER_A,
                "exact": 14,
                "profit_factor": 2.0,
            }
        ],
        "fresh_match_bridge": {
            "status": capture_queue.BRIDGE_READY,
            "eligible": True,
            "blockers": [],
            "tier_a_lane_match_count": 1,
            "matched_tier_a_lanes": ["swing"],
            "requires_fresh_executable_quote": True,
            "live_policy_change": False,
        },
        "live_policy_change": False,
    }
    row.update(overrides)
    return row


class RegularOptionsPaperShortlistTests(unittest.TestCase):
    def test_readback_reports_empty_current_release_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "research_paper_capture_queue",
                        "summary": {
                            "queue_rows": 97,
                            "tier_counts": {capture_queue.TIER_A: 15, capture_queue.TIER_B: 82},
                            "selection_readiness_counts": {
                                capture_queue.READINESS_PAPER_REVIEW: 15,
                                capture_queue.READINESS_WATCH_REPAIR: 82,
                            },
                        },
                        "capture_queue": [
                            {
                                "capture_tier": capture_queue.TIER_A,
                                "paper_shortlist_bridge": {
                                    "status": capture_queue.BRIDGE_REQUIRES_FRESH_MATCH,
                                    "eligible": False,
                                },
                            }
                        ],
                        "fresh_scan_matches": [
                            {
                                "symbol": "QQQ",
                                "playbook_id": "swing",
                                "guardrail_decision": "clear",
                                "match_type": "lane_signature",
                                "fresh_executable_quote_window": False,
                                "fresh_match_bridge": {
                                    "status": capture_queue.BRIDGE_NOT_ELIGIBLE,
                                    "eligible": False,
                                    "blockers": ["fresh_executable_quote_missing"],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )

            report = paper_shortlist.build_readback(queue_path)

        self.assertEqual(report["status"], "paper_shortlist_readback")
        self.assertEqual(report["summary"]["eligible_count"], 0)
        self.assertEqual(report["summary"]["release_gate_status"], "no_paper_shortlist_candidates")
        self.assertEqual(report["summary"]["invariant_violation_count"], 0)
        self.assertEqual(
            report["summary"]["capture_bridge_status_counts"],
            {capture_queue.BRIDGE_REQUIRES_FRESH_MATCH: 1},
        )
        self.assertEqual(
            report["summary"]["fresh_bridge_blocker_counts"],
            {"fresh_executable_quote_missing": 1},
        )

    def test_ready_fresh_match_becomes_paper_review_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "research_paper_capture_queue",
                        "summary": {"queue_rows": 1},
                        "fresh_scan_matches": [_fresh_row()],
                    }
                ),
                encoding="utf8",
            )

            report = paper_shortlist.build_readback(queue_path)

        self.assertEqual(report["summary"]["eligible_count"], 1)
        self.assertEqual(report["summary"]["release_gate_status"], "paper_review_candidates_available")
        self.assertEqual(report["summary"]["invariant_violation_count"], 0)
        candidate = report["eligible_paper_review_candidates"][0]
        self.assertEqual(candidate["symbol"], "SPY")
        self.assertEqual(candidate["bridge_status"], capture_queue.BRIDGE_READY)
        self.assertEqual(candidate["matched_tier_a_lanes"], ["swing"])
        self.assertFalse(candidate["live_policy_change"])

    def test_strict_gate_flags_ready_rows_that_violate_invariants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "research_paper_capture_queue",
                        "summary": {"queue_rows": 1},
                        "fresh_scan_matches": [
                            _fresh_row(
                                guardrail_decision="blocked",
                                fresh_executable_quote_window=False,
                                live_policy_change=True,
                            )
                        ],
                    }
                ),
                encoding="utf8",
            )

            report = paper_shortlist.build_readback(queue_path)

        self.assertEqual(report["summary"]["release_gate_status"], "blocked_invariant_violations")
        self.assertEqual(report["summary"]["eligible_count"], 0)
        self.assertEqual(report["eligible_paper_review_candidates"], [])
        self.assertEqual(report["summary"]["invariant_violation_count"], 1)
        violations = set(report["invariant_violations"][0]["violations"])
        self.assertIn("guardrail_not_clear", violations)
        self.assertIn("fresh_executable_quote_missing", violations)
        self.assertIn("live_policy_change_true", violations)

    def test_strict_gate_fails_closed_when_source_queue_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "missing.json"
            self.assertEqual(paper_shortlist.main(["--queue", str(queue_path), "--strict-gate", "--no-write"]), 1)

    def test_strict_gate_fails_when_ready_row_violates_invariants(self):
        report = {
            "status": "paper_shortlist_readback",
            "summary": {
                "release_gate_status": "blocked_invariant_violations",
                "invariant_violation_count": 1,
            }
        }
        with patch.object(paper_shortlist, "build_readback", return_value=report):
            self.assertEqual(paper_shortlist.main(["--strict-gate", "--no-write"]), 1)

    def test_markdown_renders_empty_candidate_table(self):
        report = {
            "status": "paper_shortlist_readback",
            "summary": {
                "release_gate_status": "no_paper_shortlist_candidates",
                "eligible_count": 0,
                "invariant_violation_count": 0,
                "source_queue_rows": 97,
                "capture_bridge_status_counts": {capture_queue.BRIDGE_REQUIRES_FRESH_MATCH: 15},
                "fresh_bridge_status_counts": {capture_queue.BRIDGE_NOT_ELIGIBLE: 15},
                "fresh_bridge_blocker_counts": {"no_tier_a_lane_match": 15},
                "live_policy_change": False,
            },
            "eligible_paper_review_candidates": [],
            "fresh_scan_non_eligible_preview": [],
        }

        markdown = paper_shortlist.render_markdown(report)

        self.assertIn("# Regular Options Paper Shortlist", markdown)
        self.assertIn("Eligible paper-review candidates: `0`", markdown)
        self.assertIn("Tier B, Tier C, blocked, quarantine", markdown)


if __name__ == "__main__":
    unittest.main()
