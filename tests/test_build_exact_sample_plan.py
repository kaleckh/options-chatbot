from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_exact_sample_plan import build_exact_sample_plan, find_duplicate_exact_sample_plan
from workspace_tempdir import WorkspaceTempDir


class BuildExactSamplePlanTests(unittest.TestCase):
    def test_build_exact_sample_plan_calculates_historical_and_forward_gaps(self):
        tmp = WorkspaceTempDir(prefix="exact-sample-plan")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        coverage_path = root / "coverage.json"
        coverage_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "earliest_quote_at_utc": "2024-01-02T20:55:00Z",
                    "latest_quote_at_utc": "2025-12-15T20:55:00Z",
                    "overall": {"total": 65, "exact": 11, "nearest": 54, "exact_pct": 16.9},
                }
            ),
            encoding="utf8",
        )
        checklist_path = root / "checklist.json"
        checklist_path.write_text(
            json.dumps(
                {
                    "requirements": [
                        {"id": "exact_historical_trade_count", "current": 11, "target": 40},
                        {"id": "closed_forward_trade_count", "current": 0, "target": 20},
                    ]
                }
            ),
            encoding="utf8",
        )
        forward_path = root / "forward.json"
        forward_path.write_text(
            json.dumps({"progress": {"closed_forward_trade_count": 3}}),
            encoding="utf8",
        )

        plan = build_exact_sample_plan(
            coverage_path=coverage_path,
            checklist_path=checklist_path,
            forward_evidence_path=forward_path,
        )

        self.assertEqual(plan["gaps"]["exact_historical_trades_needed"], 29)
        self.assertEqual(plan["gaps"]["closed_forward_trades_needed"], 17)
        self.assertEqual(plan["gaps"]["candidate_rows_needed_at_current_exact_coverage"], 172)
        self.assertTrue(plan["sample_plan_fingerprint"])

    def test_find_duplicate_exact_sample_plan_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="exact-sample-plan-dupe")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        plan_path = root / "exact_sample_plan_test.json"
        plan_path.write_text(json.dumps({"sample_plan_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_exact_sample_plan(root, "abc123"), plan_path)


if __name__ == "__main__":
    unittest.main()
