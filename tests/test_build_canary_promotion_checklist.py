from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_canary_promotion_checklist import (
    build_canary_promotion_checklist,
    find_duplicate_promotion_checklist,
)
from workspace_tempdir import WorkspaceTempDir


class BuildCanaryPromotionChecklistTests(unittest.TestCase):
    def test_build_checklist_blocks_when_exact_sample_is_thin(self):
        tmp = WorkspaceTempDir(prefix="canary-checklist")
        self.addCleanup(tmp.cleanup)
        run_path = Path(tmp.name) / "run.json"
        run_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "total_trades": 65,
                    "profit_factor": 2.4,
                    "avg_pnl_pct": 19.29,
                    "authoritative_profitability_metrics": {
                        "trade_count": 11,
                        "profit_factor": 0.97,
                        "avg_pnl_pct": -0.47,
                    },
                }
            ),
            encoding="utf8",
        )

        checklist = build_canary_promotion_checklist(run_path, min_exact_trades=40)

        self.assertFalse(checklist["promotion_allowed"])
        self.assertEqual(checklist["requirements"][0]["status"], "needs_more")
        self.assertEqual(checklist["requirements"][0]["current"], 11)
        self.assertIn("proof/control yardstick", checklist["next_actions"][0])
        self.assertTrue(checklist["checklist_fingerprint"])

    def test_find_duplicate_promotion_checklist_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="canary-checklist-dupe")
        self.addCleanup(tmp.cleanup)
        checklist_dir = Path(tmp.name)
        checklist_path = checklist_dir / "promotion_checklist_test.json"
        checklist_path.write_text(json.dumps({"checklist_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_promotion_checklist(checklist_dir, "abc123"), checklist_path)


if __name__ == "__main__":
    unittest.main()
