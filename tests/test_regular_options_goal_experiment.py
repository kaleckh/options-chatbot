from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_goal_experiment as goal


class RegularOptionsGoalExperimentTests(unittest.TestCase):
    def test_default_variants_are_lane_a_survivability_experiments(self):
        self.assertGreaterEqual(len(goal.DEFAULT_VARIANTS), 3)
        self.assertTrue(all(item.startswith("lane_a_goal_") for item in goal.DEFAULT_VARIANTS))

    def test_default_variants_include_causal_memory_experiments(self):
        self.assertIn("lane_a_goal_stop200_time75_shortbucket_memory45_backfill", goal.DEFAULT_VARIANTS)
        self.assertIn("lane_a_goal_stop200_time75_symbol_health90_backfill", goal.DEFAULT_VARIANTS)
        by_id = {str(item["id"]): item for item in goal.next_round.VARIANTS}

        short_bucket = by_id["lane_a_goal_stop200_time75_shortbucket_memory45_backfill"]["overrides"]
        self.assertTrue(short_bucket["exit_quote_failure_memory_enabled"])
        self.assertEqual(short_bucket["exit_quote_failure_scope"], "short_expiry_strike_bucket")
        self.assertTrue(short_bucket["execution_backfill_enabled"])

        symbol_health = by_id["lane_a_goal_stop200_time75_symbol_health90_backfill"]["overrides"]
        self.assertTrue(symbol_health["symbol_health_memory_enabled"])
        self.assertEqual(symbol_health["symbol_health_min_observations"], 3)
        self.assertTrue(symbol_health["execution_backfill_enabled"])

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

    def test_experiment_scores_are_experiment_scoped_by_default(self):
        write_calls = []

        def fake_write_outputs(scoreboard, *, output_dir=goal.evaluator.OUTPUT_DIR):
            write_calls.append(Path(output_dir))
            return {"latest_json": str(Path(output_dir) / "latest.json")}

        variant_row = {
            "variant_id": "lane_a_goal_test",
            "result_path": "run.json",
            "description": "test variant",
            "candidate_trade_count": 1,
            "exact_trade_count": 1,
        }
        scoreboard = {
            "score": 0.0,
            "research_score": 1.0,
            "status": "scout_or_blocked",
            "promotion_blockers": [],
            "score_line": "score: 0.00",
            "metrics": {},
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch.object(goal, "_run_lane_variant", return_value=({"variants": [variant_row]}, variant_row)), patch.object(
                goal,
                "_run_robustness",
                return_value=({"ok": True}, output_dir / "robustness.json"),
            ), patch.object(
                goal,
                "_run_side_aware",
                return_value=({"ok": True}, output_dir / "side-aware.json"),
            ), patch.object(
                goal,
                "_score_variant",
                return_value=scoreboard,
            ), patch.object(
                goal.evaluator,
                "append_ledger",
            ), patch.object(
                goal.evaluator,
                "write_outputs",
                side_effect=fake_write_outputs,
            ):
                report = goal.run_goal_experiments(
                    variants=["lane_a_goal_test"],
                    lookback_years=1,
                    output_dir=output_dir,
                )

        self.assertFalse(report["write_global_latest"])
        self.assertEqual(len(write_calls), 1)
        self.assertNotEqual(write_calls[0], goal.evaluator.OUTPUT_DIR)
        self.assertEqual(write_calls[0].name, "autoresearch-scoreboard")


if __name__ == "__main__":
    unittest.main()
