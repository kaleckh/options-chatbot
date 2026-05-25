from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_canary_forward_evidence import (
    build_canary_forward_evidence,
    cohort_latest_filename,
    find_duplicate_forward_evidence,
)
from workspace_tempdir import WorkspaceTempDir


class BuildCanaryForwardEvidenceTests(unittest.TestCase):
    def test_build_forward_evidence_reports_missing_forward_sample(self):
        report = build_canary_forward_evidence(
            summarize_func=lambda **kwargs: {
                "available": True,
                "db_path": "forward.db",
                "session_count": 0,
                "scan_pick_count": 0,
                "eligible_event_count": 0,
                "pending_truth_event_count": 0,
                "taken_pick_count": 0,
                "closed_review_count": 0,
            }
        )

        self.assertEqual(report["readiness"], "no_forward_evidence_yet")
        self.assertEqual(report["cohort_role"], "proof_control_yardstick")
        self.assertFalse(report["promotion_allowed"])
        self.assertEqual(report["progress"]["closed_forward_needed"], 20)
        self.assertIn("proof/control yardstick", report["next_actions"][0])
        self.assertTrue(report["forward_evidence_fingerprint"])

    def test_build_forward_evidence_marks_collection_in_progress(self):
        report = build_canary_forward_evidence(
            summarize_func=lambda **kwargs: {
                "available": True,
                "db_path": "forward.db",
                "session_count": 3,
                "scan_pick_count": 4,
                "eligible_event_count": 2,
                "pending_truth_event_count": 1,
                "taken_pick_count": 1,
                "closed_review_count": 0,
            }
        )

        self.assertEqual(report["readiness"], "collecting_forward_evidence")
        self.assertEqual(report["progress"]["scan_pick_count"], 4)

    def test_build_forward_evidence_distinguishes_no_pick_scan_attempts(self):
        report = build_canary_forward_evidence(
            summarize_func=lambda **kwargs: {
                "available": True,
                "db_path": "forward.db",
                "session_count": 1,
                "sessions_with_zero_scan_picks": 1,
                "latest_starvation_stage": "guardrails_filtered_all",
                "scan_pick_count": 0,
                "eligible_event_count": 0,
                "pending_truth_event_count": 0,
                "taken_pick_count": 0,
                "closed_review_count": 0,
            }
        )

        self.assertEqual(report["readiness"], "scanning_no_picks_yet")
        self.assertEqual(report["progress"]["session_count"], 1)
        self.assertEqual(report["progress"]["latest_starvation_stage"], "guardrails_filtered_all")

    def test_find_duplicate_forward_evidence_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="forward-evidence-dupe")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        report_path = root / "forward_evidence_test.json"
        report_path.write_text(json.dumps({"forward_evidence_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_forward_evidence(root, "abc123"), report_path)

    def test_cohort_latest_filename_is_stable(self):
        self.assertEqual(
            cohort_latest_filename("tracked_winner_observation"),
            "latest_tracked_winner_observation.json",
        )


if __name__ == "__main__":
    unittest.main()
