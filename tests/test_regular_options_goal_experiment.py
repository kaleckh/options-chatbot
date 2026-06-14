from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_goal_experiment as goal


class RegularOptionsGoalExperimentTests(unittest.TestCase):
    def test_default_variants_retire_lane_a_survivability_batch(self):
        self.assertEqual(goal.DEFAULT_VARIANTS, [])
        self.assertNotIn("Lane A", goal.DEFAULT_GOAL)

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
            "progress_score": 1.0,
            "research_score": 1.0,
            "status": "scout_or_blocked",
            "promotion_blockers": [],
            "score_line": "score: 0.00 progress_score: 1.00",
            "metrics": {
                "pf_point": 1.3,
                "pf_lb_5pct": 0.8,
                "pf_ub_95pct": 2.4,
                "avg_net_lb_5pct": -3.2,
                "n_trades": 44,
                "statistical_confidence": "underpowered",
                "strategy_family": "lane_a",
                "variants_searched": 7,
                "selection_adjusted_bar": 1.14,
                "selection_adjusted_confidence": "below_selection_adjusted_bar",
                "selection_adjustment_formula": "1.0 + 0.05 * log2(max(variants_searched, 1))",
            },
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
        self.assertEqual(report["variants"][0]["pf_lb_5pct"], 0.8)
        self.assertEqual(report["variants"][0]["statistical_confidence"], "underpowered")
        self.assertEqual(report["variants"][0]["variants_searched"], 7)
        self.assertEqual(report["variants"][0]["selection_adjusted_bar"], 1.14)
        self.assertEqual(len(write_calls), 1)
        self.assertNotEqual(write_calls[0], goal.evaluator.OUTPUT_DIR)
        self.assertEqual(write_calls[0].name, "autoresearch-scoreboard")

    def test_experiment_batch_ranks_by_score_then_progress_score(self):
        rows = {
            "count_proxy": {
                "variant_id": "count_proxy",
                "result_path": "count_proxy.json",
                "description": "count only",
                "candidate_trade_count": 300,
                "exact_trade_count": 250,
                "quote_coverage_pct": 99.0,
            },
            "pnl_progress": {
                "variant_id": "pnl_progress",
                "result_path": "pnl_progress.json",
                "description": "pnl progress",
                "candidate_trade_count": 180,
                "exact_trade_count": 160,
                "quote_coverage_pct": 90.0,
            },
        }

        def fake_run_lane_variant(variant_id: str, *, lookback_years: int):
            row = rows[variant_id]
            return {"variants": [row]}, row

        def fake_score_variant(*, variant_id, run_path, robustness_path, side_aware_path, hypothesis):
            progress = 40.0 if variant_id == "pnl_progress" else 10.0
            research = 10.0 if variant_id == "pnl_progress" else 100.0
            return {
                "score": 0.0,
                "progress_score": progress,
                "research_score": research,
                "status": "scout_or_blocked",
                "promotion_blockers": [],
                "score_line": f"score: 0.00 progress_score: {progress:.2f}",
                "metrics": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch.object(goal, "_run_lane_variant", side_effect=fake_run_lane_variant), patch.object(
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
                side_effect=fake_score_variant,
            ), patch.object(
                goal.evaluator,
                "write_outputs",
                return_value={"latest_json": "latest.json"},
            ):
                report = goal.run_goal_experiments(
                    variants=["count_proxy", "pnl_progress"],
                    lookback_years=1,
                    output_dir=output_dir,
                    append_ledger=False,
                )

        self.assertEqual(report["best"]["variant_id"], "pnl_progress")
        self.assertEqual(report["ranked"][0]["progress_score"], 40.0)
        self.assertEqual(report["ranked"][1]["research_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
