from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_current_regime_momentum_edge as edge
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _variant(
    variant_id: str,
    *,
    lane_id: str = "etf_index_pullback_control",
    description: str = "QQQ momentum candidate",
    exact: int,
    pf: float,
    stress: float,
    coverage: float,
    strict_new: int,
    with_count: int,
    worth_status: str,
    unpriced: int = 0,
) -> dict:
    return {
        "variant_id": variant_id,
        "lane_id": lane_id,
        "description": description,
        "worth_status": worth_status,
        "run_path": f"data/options-validation/runs/{variant_id}.json",
        "standalone_metrics": {
            "exact_trade_count": exact,
            "priced_trade_count": exact,
            "unpriced_trade_count": unpriced,
            "profit_factor": pf,
            "avg_pnl_pct": 10.0,
            "win_rate_pct": 55.0,
            "quote_coverage_pct": coverage,
        },
        "robustness": {
            "stress_5pct_per_side_profit_factor": stress,
            "rolling_status": "passed",
        },
        "novelty_vs_core_plus_clean_reference": {
            "base_clean_trade_count": 157,
            "with_candidate_trade_count": with_count,
            "strict_new_trade_count": strict_new,
            "gap_after_candidate": max(200 - with_count, 0),
            "suppressed_duplicate_trade_count": 100,
            "duplicate_group_count": 50,
        },
    }


class CurrentRegimeMomentumEdgeTests(unittest.TestCase):
    def _fixture_paths(self, tmp: Path, variants: list[dict]) -> tuple[Path, Path, Path]:
        all_planned = tmp / "all_planned.json"
        incubator = tmp / "incubator.json"
        robust = tmp / "robust.json"
        _write_json(
            all_planned,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "as_of_date": "2026-06-04",
                "base_clean_stack": {
                    "strict_deduped_trade_count": 157,
                    "gap_to_200": 43,
                },
                "variants": variants,
            },
        )
        _write_json(
            incubator,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "report_id": "regular_options_current_regime_lane_incubator",
                "status": "current_regime_lane_incubator_ready_for_operator_review",
            },
        )
        _write_json(
            robust,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "report_id": "regular_options_robust_edge_discovery",
                "overall_status": "paper_shadow_only",
            },
        )
        return all_planned, incubator, robust

    def test_raw_count_above_target_is_not_accepted_when_economics_fail(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "tracked_winner_chain_native_qqq_time65_all_sleeves",
                        lane_id="tracked_winner_primary",
                        exact=148,
                        pf=0.68,
                        stress=0.46,
                        coverage=73.3,
                        strict_new=148,
                        with_count=305,
                        worth_status="not_worth_current_shape",
                        unpriced=54,
                    ),
                    _variant(
                        "sleeve_next_index_refill_v1",
                        exact=116,
                        pf=1.74,
                        stress=1.33,
                        coverage=100.0,
                        strict_new=6,
                        with_count=163,
                        worth_status="profitable_but_overlaps",
                    ),
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "raw_count_available_but_not_countable_profitable_edge")
        self.assertFalse(report["accepted_profitability"])
        self.assertEqual(report["raw_count_target_met_candidate_count"], 1)
        self.assertEqual(report["countable_momentum_edge_candidate_count"], 0)
        raw = report["raw_count_target_met_candidates"][0]
        self.assertEqual(raw["decision"], "rejected_negative_or_flat_edge")
        self.assertIn("point_profit_factor_not_above_1", raw["reason_codes"])

    def test_positive_overlap_candidate_stays_below_trade_count_target(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "sleeve_next_index_refill_v1",
                        exact=116,
                        pf=1.74,
                        stress=1.33,
                        coverage=100.0,
                        strict_new=6,
                        with_count=163,
                        worth_status="profitable_but_overlaps",
                    )
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_no_countable_high_throughput_momentum_edge")
        candidate = report["candidate_rankings"][0]
        self.assertEqual(candidate["decision"], "blocked_below_trade_count_target")
        self.assertIn("strict_new_rows_6_below_needed_43", candidate["reason_codes"])

    def test_positive_raw_count_target_still_blocks_on_coverage_and_stress(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "tracked_winner_chain_native_research_all_sleeves",
                        lane_id="tracked_winner_primary",
                        exact=112,
                        pf=1.23,
                        stress=0.9,
                        coverage=70.9,
                        strict_new=112,
                        with_count=269,
                        worth_status="weak_positive_or_marginal",
                        unpriced=46,
                    )
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        candidate = report["candidate_rankings"][0]
        self.assertEqual(report["status"], "raw_count_available_but_not_countable_profitable_edge")
        self.assertEqual(candidate["decision"], "raw_count_target_met_but_not_countable_edge")
        self.assertIn("quote_coverage_70.9_below_90.0", candidate["reason_codes"])
        self.assertIn("stress_pf_0.9_below_1.0", candidate["reason_codes"])

    def test_countable_candidate_is_research_only_not_promotion(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "sleeve_next_index_new_momentum_v1",
                        exact=210,
                        pf=1.55,
                        stress=1.12,
                        coverage=98.0,
                        strict_new=53,
                        with_count=210,
                        worth_status="clean_but_too_small",
                    )
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "momentum_edge_target_met_research_only")
        self.assertEqual(report["countable_momentum_edge_candidate_count"], 1)
        self.assertFalse(report["promotion_ready"])
        self.assertFalse(report["broker_order_allowed"])

    def test_non_momentum_and_put_variants_are_excluded(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "xle_energy_inflation_put_chain_native_timeexit_all_sleeves",
                        lane_id="xle_energy_inflation",
                        description="XLE put branch",
                        exact=240,
                        pf=2.0,
                        stress=1.5,
                        coverage=100.0,
                        strict_new=83,
                        with_count=240,
                        worth_status="candidate_to_close_200_gap",
                    ),
                    _variant(
                        "sleeve_next_index_refill_v1",
                        exact=116,
                        pf=1.74,
                        stress=1.33,
                        coverage=100.0,
                        strict_new=6,
                        with_count=163,
                        worth_status="profitable_but_overlaps",
                    ),
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual([row["candidate_id"] for row in report["candidate_rankings"]], ["sleeve_next_index_refill_v1"])

    def test_write_outputs_writes_docs_and_latest_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="momentum-edge") as tmp_dir:
            tmp = Path(tmp_dir)
            all_planned, incubator, robust = self._fixture_paths(
                tmp,
                [
                    _variant(
                        "sleeve_next_index_refill_v1",
                        exact=116,
                        pf=1.74,
                        stress=1.33,
                        coverage=100.0,
                        strict_new=6,
                        with_count=163,
                        worth_status="profitable_but_overlaps",
                    )
                ],
            )
            report = edge.build_report(
                all_planned_path=all_planned,
                incubator_path=incubator,
                robust_edge_path=robust,
                generated_at_utc="2026-06-22T01:00:00Z",
            )
            artifacts = edge.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue(Path(artifacts["latest_json"]).exists())
            self.assertTrue(Path(artifacts["latest_markdown"]).exists())
            self.assertTrue(Path(artifacts["docs_report"]).exists())
            self.assertIn("Current-Regime Momentum Edge Test", Path(artifacts["docs_report"]).read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
