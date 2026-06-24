from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_causal_falsification_slice as causal
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsCausalFalsificationSliceTests(unittest.TestCase):
    def _frontier_fixture(self, tmp: Path) -> Path:
        path = tmp / "frontier.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_countable_throughput_frontier",
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "status": "current_historical_surface_exhausted_under_current_prohibitions",
                "candidate_count": 4,
                "raw_count_candidate_count": 2,
                "countable_throughput_candidate_found": False,
                "decision_counts": {
                    "blocked_below_strict_new_count": 1,
                    "blocked_execution_quality": 1,
                    "rejected_negative_or_flat_edge": 2,
                },
                "candidate_rankings": [
                    {
                        "candidate_id": "tracked_winner_chain_native_research_all_sleeves",
                        "candidate_family": "tracked_winner_primary",
                        "decision": "blocked_execution_quality",
                        "count_gap_closed": True,
                        "strict_new_rows_after_opportunity_dedupe": 112,
                        "with_candidate_exact_rows": 269,
                        "point_profit_factor": 1.23,
                        "strict_new_profit_factor": 1.23,
                        "stress_profit_factor": 0.9,
                        "quote_coverage_pct": 70.9,
                        "unpriced_rows": 46,
                        "blockers": ["quote_coverage_70.9_below_90", "unpriced_rows_46"],
                    },
                    {
                        "candidate_id": "tracked_winner_chain_native_qqq_time65_all_sleeves",
                        "candidate_family": "tracked_winner_primary",
                        "decision": "rejected_negative_or_flat_edge",
                        "count_gap_closed": True,
                        "strict_new_rows_after_opportunity_dedupe": 148,
                        "with_candidate_exact_rows": 305,
                        "point_profit_factor": 0.68,
                        "strict_new_profit_factor": 0.68,
                        "stress_profit_factor": 0.46,
                        "quote_coverage_pct": 73.3,
                        "unpriced_rows": 54,
                        "blockers": ["point_profitability_not_positive"],
                    },
                    {
                        "candidate_id": "sleeve_next_index_refill_v1",
                        "candidate_family": "etf_index_pullback_control",
                        "decision": "blocked_below_strict_new_count",
                        "count_gap_closed": False,
                        "strict_new_rows_after_opportunity_dedupe": 6,
                        "with_candidate_exact_rows": 163,
                        "point_profit_factor": 1.74,
                        "strict_new_profit_factor": 0.0,
                        "stress_profit_factor": 1.33,
                        "quote_coverage_pct": 100.0,
                        "unpriced_rows": 0,
                        "blockers": ["strict_new_rows_6_below_required_43"],
                    },
                    {
                        "candidate_id": "sleeve_next_high_beta_momentum_fast_v1",
                        "candidate_family": "high_beta_momentum_volatility",
                        "decision": "rejected_negative_or_flat_edge",
                        "count_gap_closed": True,
                        "strict_new_rows_after_opportunity_dedupe": 46,
                        "with_candidate_exact_rows": 203,
                        "point_profit_factor": 0.26,
                        "strict_new_profit_factor": 0.26,
                        "stress_profit_factor": 0.18,
                        "quote_coverage_pct": 79.3,
                        "unpriced_rows": 12,
                        "blockers": ["point_profitability_not_positive"],
                    },
                ],
            },
        )
        return path

    def test_report_falsifies_existing_surface_but_keeps_new_causal_branch_open(self) -> None:
        with WorkspaceTempDir(prefix="causal-falsification") as tmp_dir:
            tmp = Path(tmp_dir)
            frontier = self._frontier_fixture(tmp)
            momentum = tmp / "momentum.json"
            incubator = tmp / "incubator.json"
            walk = tmp / "walk.json"
            _write_json(
                momentum,
                {
                    "report_id": "regular_options_current_regime_momentum_edge",
                    "generated_at_utc": "2026-06-22T00:00:00Z",
                    "status": "raw_count_available_but_not_countable_profitable_edge",
                    "candidate_rankings": [
                        {
                            "candidate_id": "tracked_winner_chain_native_research_all_sleeves",
                            "decision": "raw_count_target_met_but_not_countable_edge",
                            "strict_new_trade_count": 112,
                            "with_candidate_trade_count": 269,
                            "profit_factor": 1.23,
                            "stress_5pct_per_side_profit_factor": 0.9,
                            "quote_coverage_pct": 70.9,
                            "unpriced_rows": 46,
                            "reason_codes": ["stress_pf_0.9_below_1.0"],
                        }
                    ],
                },
            )
            _write_json(incubator, {"status": "current_regime_lane_incubator_ready_for_operator_review"})
            _write_json(walk, {"status": "historical_walkforward_ran_candidates_blocked", "promotion_ready": False})

            report = causal.build_report(
                frontier_path=frontier,
                momentum_edge_path=momentum,
                incubator_path=incubator,
                walk_forward_path=walk,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "existing_surface_falsified_new_causal_branch_still_possible")
        self.assertTrue(report["continue_loop"])
        self.assertTrue(report["significant_upgrade_available"])
        statuses = {row["hypothesis_id"]: row["status"] for row in report["hypotheses"]}
        self.assertEqual(statuses["raw_count_aggregation_is_enough"], "falsified_existing_surface")
        self.assertEqual(statuses["new_preregistered_causal_playbook"], "not_falsified_requires_next_oracle_or_operator_selection")
        self.assertIn("tracked-winner count retuning without new causal evidence", report["branches_to_stop"])

    def test_missing_frontier_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="causal-falsification") as tmp_dir:
            tmp = Path(tmp_dir)
            report = causal.build_report(
                frontier_path=tmp / "missing.json",
                momentum_edge_path=tmp / "missing-momentum.json",
                incubator_path=tmp / "missing-incubator.json",
                walk_forward_path=tmp / "missing-walk.json",
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_required_frontier")
        self.assertFalse(report["continue_loop"])
        self.assertFalse(report["significant_upgrade_available"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="causal-falsification") as tmp_dir:
            tmp = Path(tmp_dir)
            frontier = self._frontier_fixture(tmp)
            report = causal.build_report(
                frontier_path=frontier,
                momentum_edge_path=tmp / "missing-momentum.json",
                incubator_path=tmp / "missing-incubator.json",
                walk_forward_path=tmp / "missing-walk.json",
                generated_at_utc="2026-06-22T01:00:00Z",
            )
            artifacts = causal.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Regular Options Causal Falsification Slice", (tmp / "docs" / "report.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
