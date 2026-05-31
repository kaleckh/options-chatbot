from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_goal_experiment as goal


class RegularOptionsGoalExperimentTests(unittest.TestCase):
    def test_default_variants_are_lane_a_survivability_experiments(self):
        self.assertGreaterEqual(len(goal.DEFAULT_VARIANTS), 3)
        self.assertTrue(all(item.startswith("lane_a_goal_") for item in goal.DEFAULT_VARIANTS))

    def test_patched_multilane_inputs_replaces_lane_a_artifacts_only(self):
        original_sources = [
            {"lane_id": "core", "artifact": Path("core.json"), "robustness": Path("core_rob.json")},
            {"lane_id": goal.LANE_A_SOURCE_ID, "artifact": Path("old.json"), "robustness": Path("old_rob.json")},
        ]
        with patch.object(goal.multilane, "LANE_SOURCES", original_sources), patch.object(
            goal.multilane,
            "SIDE_AWARE_ZERO_BID_LATEST",
            Path("old_side.json"),
        ):
            with goal._patched_multilane_inputs(
                lane_a_run_path=Path("new.json"),
                lane_a_robustness_path=Path("new_rob.json"),
                side_aware_path=Path("new_side.json"),
            ):
                self.assertEqual(goal.multilane.LANE_SOURCES[0]["artifact"], Path("core.json"))
                self.assertEqual(goal.multilane.LANE_SOURCES[1]["artifact"], Path("new.json"))
                self.assertEqual(goal.multilane.LANE_SOURCES[1]["robustness"], Path("new_rob.json"))
                self.assertEqual(goal.multilane.SIDE_AWARE_ZERO_BID_LATEST, Path("new_side.json"))

            self.assertEqual(goal.multilane.LANE_SOURCES, original_sources)
            self.assertEqual(goal.multilane.SIDE_AWARE_ZERO_BID_LATEST, Path("old_side.json"))


if __name__ == "__main__":
    unittest.main()
