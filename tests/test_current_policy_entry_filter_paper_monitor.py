from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from scripts.monitor_current_policy_entry_filter_paper import gate_status  # noqa: E402


class CurrentPolicyEntryFilterPaperMonitorTests(unittest.TestCase):
    def test_gate_collects_until_fresh_sample_exists(self):
        gate = gate_status(
            baseline={"rows": 3},
            champion={
                "matched": {"rows": 1, "sum_pnl_pct": -80.0, "loss_le_50_count": 1},
                "kept": {"median_pnl_pct": 20.0, "negative_rate_pct": 20.0},
                "winners_lost": 0,
                "losses_avoided": 1,
            },
            min_rows=20,
            min_blocked=5,
        )

        self.assertEqual(gate["status"], "collecting")
        self.assertIn("insufficient_fresh_rows", gate["failures"])

    def test_gate_can_pass_when_champion_clears_fresh_bars(self):
        gate = gate_status(
            baseline={"rows": 24},
            champion={
                "matched": {"rows": 6, "sum_pnl_pct": -180.0, "loss_le_50_count": 2},
                "kept": {"median_pnl_pct": 12.0, "negative_rate_pct": 30.0},
                "winners_lost": 1,
                "losses_avoided": 5,
            },
            min_rows=20,
            min_blocked=5,
        )

        self.assertEqual(gate["status"], "paper_pass_candidate")
        self.assertEqual(gate["failures"], [])


if __name__ == "__main__":
    unittest.main()
