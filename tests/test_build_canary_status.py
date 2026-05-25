from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_canary_status import build_canary_status, find_duplicate_canary_status
from workspace_tempdir import WorkspaceTempDir


class BuildCanaryStatusTests(unittest.TestCase):
    def test_build_canary_status_separates_research_from_proof(self):
        tmp = WorkspaceTempDir(prefix="canary-status")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        run_path = root / "run.json"
        run_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "lookback_years": 5,
                    "total_trades": 65,
                    "profit_factor": 2.4,
                    "avg_pnl_pct": 19.29,
                    "win_rate_pct": 75.4,
                    "authoritative_profitability_metrics": {
                        "trade_count": 11,
                        "profit_factor": 0.97,
                        "avg_pnl_pct": -0.47,
                    },
                    "truth_store": {
                        "earliest_quote_at_utc": "2024-01-02T20:55:00Z",
                        "latest_quote_at_utc": "2025-12-15T20:55:00Z",
                    },
                }
            ),
            encoding="utf8",
        )
        coverage_path = root / "coverage.json"
        coverage_path.write_text(
            json.dumps({"overall": {"total": 65, "exact": 11, "nearest": 54, "exact_pct": 16.9}}),
            encoding="utf8",
        )
        checklist_path = root / "checklist.json"
        checklist_path.write_text(
            json.dumps(
                {
                    "requirements": [
                        {"id": "exact_historical_trade_count", "status": "needs_more", "current": 11, "target": 40},
                        {"id": "closed_forward_trade_count", "status": "needs_forward_collection", "current": 0, "target": 20},
                    ]
                }
            ),
            encoding="utf8",
        )
        forward_path = root / "forward.json"
        forward_path.write_text(
            json.dumps({"progress": {"closed_forward_trade_count": 2, "closed_forward_needed": 18}}),
            encoding="utf8",
        )
        sample_plan_path = root / "sample_plan.json"
        sample_plan_path.write_text(
            json.dumps({"gaps": {"exact_historical_trades_needed": 29, "closed_forward_trades_needed": 18}}),
            encoding="utf8",
        )

        status = build_canary_status(
            run_path,
            exact_coverage_path=coverage_path,
            promotion_checklist_path=checklist_path,
            forward_evidence_path=forward_path,
            sample_plan_path=sample_plan_path,
        )

        self.assertEqual(status["readiness"], "research_positive_needs_exact_proof")
        self.assertEqual(status["cohort_role"], "proof_control_yardstick")
        self.assertFalse(status["promotion_allowed"])
        self.assertEqual(status["research_signal"]["profit_factor"], 2.4)
        self.assertEqual(status["proof_signal"]["trade_count"], 11)
        self.assertEqual(status["exact_coverage"]["exact_pct"], 16.9)
        self.assertEqual(status["forward_progress"]["closed_forward_trade_count"], 2)
        self.assertEqual(status["sample_gaps"]["exact_historical_trades_needed"], 29)
        self.assertIn("proof/control yardstick", status["next_actions"][0])
        self.assertTrue(status["status_fingerprint"])

    def test_find_duplicate_canary_status_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="canary-status-dupe")
        self.addCleanup(tmp.cleanup)
        status_dir = Path(tmp.name)
        status_path = status_dir / "canary_status_test.json"
        status_path.write_text(json.dumps({"status_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_canary_status(status_dir, "abc123"), status_path)


if __name__ == "__main__":
    unittest.main()
