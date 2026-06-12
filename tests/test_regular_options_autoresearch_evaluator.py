from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_regular_options_autoresearch import (
    append_ledger,
    bootstrap_confidence_for_values,
    build_scoreboard,
    evaluator_config_hash,
    format_score_line,
)


def _lane(
    lane_id: str,
    *,
    candidates: int,
    exact: int,
    unpriced: int,
    stress_pf: float = 1.5,
    rolling_status: str = "passed",
    include: bool = True,
    status: str = "count_candidate",
):
    return {
        "lane_id": lane_id,
        "include_in_proof_portfolio": include,
        "status": status,
        "metrics": {
            "candidate_trade_count": candidates,
            "exact_trade_count": exact,
            "unpriced_trade_count": unpriced,
        },
        "robustness": {
            "stress_5pct_per_side_profit_factor": stress_pf,
            "rolling_status": rolling_status,
        },
    }


def _report(*, with_lane_a: bool = True, side_aware_pf: float = 1.40, side_aware_unpriced: int = 0) -> dict:
    lanes = [
        _lane("core", candidates=100, exact=100, unpriced=0, stress_pf=1.6),
    ]
    if with_lane_a:
        lanes.append(
            _lane(
                "lane_a_chain_native_ret20_4_stop200_time75",
                candidates=110,
                exact=100,
                unpriced=10,
                stress_pf=1.4,
            )
        )
    return {
        "scope": "regular_stock_options_only",
        "combined_portfolio": {
            "duplicate_group_count": 0,
            "suppressed_duplicate_trade_count": 0,
            "metrics": {
                "exact_trade_count": 200,
                "profit_factor": 1.75,
                "avg_pnl_pct": 15.0,
                "win_rate_pct": 58.0,
            },
        },
        "quality_gate": {
            "overall_status": "quality_pending",
            "paper_shadow_status": "pending",
        },
        "lanes": lanes,
        "side_aware_zero_bid_replay": {
            "modes": {
                "conservative": {
                    "combined_lane_a_candidate_count": 110,
                    "combined_lane_a_priced_count": 110 - side_aware_unpriced,
                    "combined_lane_a_unpriced_count": side_aware_unpriced,
                    "priced_count": 20,
                    "zero_bid_priced_count": 0,
                    "combined_with_existing_lane_a_metrics": {
                        "profit_factor": side_aware_pf,
                        "avg_pnl_pct": 4.0,
                    },
                }
            }
        },
    }


def _report_with_selected_trades(values_by_branch: dict[str, list[float]]) -> dict:
    report = _report(with_lane_a=False)
    report["combined_portfolio"]["metrics"]["exact_trade_count"] = sum(len(values) for values in values_by_branch.values())
    report["selected_trades"] = []
    for branch_id, values in values_by_branch.items():
        report["selected_trades"].extend(
            {
                "lane_id": branch_id,
                "exact_priced": True,
                "priced": True,
                "pnl_pct": value,
            }
            for value in values
        )
    report["lanes"] = [
        _lane(
            branch_id,
            candidates=len(values),
            exact=len(values),
            unpriced=0,
            include=True,
        )
        for branch_id, values in values_by_branch.items()
    ]
    return report


class RegularOptionsAutoresearchEvaluatorTests(unittest.TestCase):
    def test_score_is_zero_when_lane_a_zero_bid_replay_fails(self):
        scoreboard = build_scoreboard(
            _report(side_aware_pf=0.85, side_aware_unpriced=11),
            experiment_id="baseline",
            hypothesis="current",
            generated_at_utc="2026-05-31T00:00:00Z",
        )

        self.assertEqual(scoreboard["score"], 0.0)
        self.assertEqual(scoreboard["status"], "scout_or_blocked")
        self.assertIn("lane_a_conservative_pf_below_1_30", scoreboard["promotion_blockers"])
        self.assertIn("effective_unresolved_candidates_remain", scoreboard["promotion_blockers"])
        self.assertIn("score:", format_score_line(scoreboard))
        self.assertIn("progress_score:", format_score_line(scoreboard))

    def test_progress_score_ranks_conservative_pf_below_promotion_bar(self):
        low_pf = _report(side_aware_pf=1.10, side_aware_unpriced=0)
        high_pf = _report(side_aware_pf=1.40, side_aware_unpriced=0)
        low_pf["combined_portfolio"]["metrics"]["profit_factor"] = 1.10
        high_pf["combined_portfolio"]["metrics"]["profit_factor"] = 1.10

        low = build_scoreboard(low_pf, experiment_id="low", hypothesis="low")
        high = build_scoreboard(high_pf, experiment_id="high", hypothesis="high")

        self.assertEqual(low["score"], 0.0)
        self.assertEqual(high["score"], 0.0)
        self.assertGreater(high["progress_score"], low["progress_score"])

    def test_progress_score_does_not_reward_count_or_coverage_only_backfill(self):
        baseline = _report(side_aware_pf=1.10, side_aware_unpriced=10)
        backfilled = _report(side_aware_pf=1.10, side_aware_unpriced=0)
        for report in (baseline, backfilled):
            report["combined_portfolio"]["metrics"]["profit_factor"] = 1.10
            report["combined_portfolio"]["metrics"]["exact_trade_count"] = 250
        backfilled["lanes"][0]["metrics"]["candidate_trade_count"] = 150
        backfilled["lanes"][0]["metrics"]["exact_trade_count"] = 150

        baseline_scoreboard = build_scoreboard(baseline, experiment_id="baseline", hypothesis="same pnl")
        backfilled_scoreboard = build_scoreboard(backfilled, experiment_id="backfilled", hypothesis="same pnl")

        self.assertEqual(baseline_scoreboard["score"], 0.0)
        self.assertEqual(backfilled_scoreboard["score"], 0.0)
        self.assertEqual(backfilled_scoreboard["progress_score"], baseline_scoreboard["progress_score"])

    def test_promotable_clean_can_pass_historical_gates_but_not_paper_shadow(self):
        scoreboard = build_scoreboard(
            _report(side_aware_pf=1.55, side_aware_unpriced=0),
            experiment_id="clean",
            hypothesis="clean lane a",
            generated_at_utc="2026-05-31T00:00:00Z",
        )

        self.assertEqual(scoreboard["status"], "promotable_clean")
        self.assertEqual(scoreboard["metrics"]["promotable_clean_count"], 200)
        self.assertGreater(scoreboard["score"], 0)
        self.assertEqual(scoreboard["production_status"], "not_production_ready")
        self.assertIn("paper_shadow_status_not_passed", scoreboard["production_blockers"])

    def test_side_aware_replay_is_required_when_lane_a_is_counted(self):
        report = _report()
        report.pop("side_aware_zero_bid_replay")

        scoreboard = build_scoreboard(
            report,
            experiment_id="missing-side-aware",
            hypothesis="missing side aware",
            generated_at_utc="2026-05-31T00:00:00Z",
        )

        self.assertIn("side_aware_zero_bid_replay_missing_for_counted_lane_a", scoreboard["promotion_blockers"])

    def test_legacy_portfolio_candidate_status_still_reads_old_artifacts(self):
        report = _report(with_lane_a=False)
        report["lanes"][0]["status"] = "portfolio_candidate"

        scoreboard = build_scoreboard(
            report,
            experiment_id="legacy-status",
            hypothesis="old artifact",
            generated_at_utc="2026-05-31T00:00:00Z",
        )

        self.assertEqual(scoreboard["metrics"]["included_lane_ids"], ["core"])

    def test_ledger_row_is_compact_and_hash_is_stable(self):
        scoreboard = build_scoreboard(
            _report(side_aware_pf=1.55, side_aware_unpriced=0),
            experiment_id="clean",
            hypothesis="clean lane a",
            generated_at_utc="2026-05-31T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            append_ledger(scoreboard, path=path)
            row = json.loads(path.read_text(encoding="utf8").strip())

        self.assertEqual(row["experiment_id"], "clean")
        self.assertEqual(row["evaluator_config_hash"], evaluator_config_hash())
        self.assertIn("score", row)
        self.assertIn("progress_score", row)
        self.assertIn("pf_lb_5pct", row)
        self.assertIn("avg_net_lb_5pct", row)
        self.assertIn("statistical_confidence", row)
        self.assertNotIn("metrics", row)

    def test_bootstrap_all_winners_preserves_no_loss_pf_null_and_positive_avg_lb(self):
        stats = bootstrap_confidence_for_values([5.0, 10.0, 15.0, 20.0], branch_id="all-winners")

        self.assertEqual(stats["n_trades"], 4)
        self.assertIsNone(stats["pf_point"])
        self.assertIsNone(stats["pf_lb_5pct"])
        self.assertIsNone(stats["pf_ub_95pct"])
        self.assertTrue(stats["no_loss_sample"])
        self.assertGreater(stats["avg_net_lb_5pct"], 0.0)
        self.assertEqual(stats["statistical_confidence"], "negative_or_flat")

    def test_bootstrap_mixed_positive_branch_is_confident_and_deterministic(self):
        values = [10.0] * 8 + [-5.0] * 2
        first = bootstrap_confidence_for_values(values, branch_id="mixed-positive")
        second = bootstrap_confidence_for_values(values, branch_id="mixed-positive")

        self.assertEqual(first, second)
        self.assertEqual(first["pf_point"], 8.0)
        self.assertGreater(first["pf_lb_5pct"], 1.0)
        self.assertEqual(first["statistical_confidence"], "confident_positive")

    def test_bootstrap_heavy_tail_loser_marks_point_pf_as_underpowered(self):
        values = [20.0] * 20 + [-250.0]
        stats = bootstrap_confidence_for_values(values, branch_id="heavy-tail")

        self.assertGreaterEqual(stats["pf_point"], 1.2)
        self.assertLess(stats["pf_lb_5pct"], 1.0)
        self.assertLess(stats["avg_net_lb_5pct"], 0.0)
        self.assertEqual(stats["statistical_confidence"], "underpowered")

    def test_scoreboard_reports_combined_and_per_branch_bootstrap_fields(self):
        scoreboard = build_scoreboard(
            _report_with_selected_trades(
                {
                    "branch_a": [10.0] * 8 + [-5.0] * 2,
                    "branch_b": [20.0] * 20 + [-250.0],
                }
            ),
            experiment_id="bootstrap",
            hypothesis="bootstrap diagnostics",
            generated_at_utc="2026-06-12T00:00:00Z",
        )

        metrics = scoreboard["metrics"]
        self.assertEqual(metrics["n_trades"], 31)
        self.assertIn(metrics["statistical_confidence"], {"underpowered", "confident_positive", "negative_or_flat"})
        branches = metrics["bootstrap_confidence"]["branches"]
        self.assertEqual([row["branch_id"] for row in branches], ["branch_a", "branch_b"])
        self.assertEqual(branches[0]["statistical_confidence"], "confident_positive")
        self.assertEqual(branches[1]["statistical_confidence"], "underpowered")
        self.assertIn("pf_lb_5pct:", scoreboard["score_line"])


if __name__ == "__main__":
    unittest.main()
