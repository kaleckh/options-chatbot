from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scripts import build_regular_options_historical_walk_forward as walk_forward


def _feature_report(status: str = "feature_store_built") -> dict:
    return {
        "report_id": "regular_options_feature_store",
        "status": status,
        "summary": {
            "shared_quote_date_count": 505,
            "latest_shared_quote_date_et": "2026-06-04",
        },
    }


def _robust_report(*, status: str = "historical_candidates_blocked", latest_entry_date: str | None = "2026-03-24") -> dict:
    combined_metrics = {
        "exact_trade_count": 231,
        "profit_factor": 2.113,
        "avg_pnl_pct": 25.53,
        "risk": {"max_drawdown_pct_points": 180.0},
    }
    if latest_entry_date is not None:
        combined_metrics["latest_entry_date"] = latest_entry_date
    return {
        "report_id": "regular_options_robust_search_evaluation",
        "status": status,
        "summary": {
            "accepted_exact_trade_count": 231,
            "candidate_count": 1,
            "ready_candidate_count": 0,
            "variants_searched": 12,
            "selection_adjusted_bar": 1.18,
        },
        "candidates": [
            {
                "candidate_id": "combined_portfolio",
                "candidate_type": "combined",
                "status": "historical_candidate_blocked",
                "historical_nomination_ready": False,
                "blockers": ["final_holdout_exact_trades_below_30"],
                "split_metrics": {
                    "combined": combined_metrics,
                    "validation": {"exact_trade_count": 59, "profit_factor": 2.0457},
                    "final_holdout": {
                        "exact_trade_count": 28,
                        "profit_factor": 1.2725,
                        "avg_pnl_pct": 8.94,
                        "bootstrap": {
                            "pf_lb_5pct": 0.61,
                            "statistical_confidence": "underpowered",
                        },
                        "risk": {"max_drawdown_pct_points": 120.0},
                    },
                },
            }
        ],
    }


def _holdout_contract() -> dict:
    return {
        "contract_id": "forward-holdout-contract",
        "status": "active",
        "protected_range": {"date_basis": "candidate_entry_date", "start_date": "2026-06-05"},
    }


def _all_planned_report(
    *,
    as_of_date: str = "2026-06-04",
    run_failed_count: int = 0,
    tested_end_to_end_variant_count: int | None = None,
) -> dict:
    return {
        "generated_at_utc": "2026-06-14T00:00:00Z",
        "as_of_date": as_of_date,
        "implemented_variant_count": 2,
        "selected_variant_count": 2,
        "tested_end_to_end_variant_count": tested_end_to_end_variant_count
        if tested_end_to_end_variant_count is not None
        else 2 - run_failed_count,
        "run_failed_count": run_failed_count,
        "base_clean_stack": {"strict_deduped_trade_count": 157, "gap_to_200": 43},
        "variants": [
            {
                "lane_id": "alpha",
                "variant_id": "alpha_variant",
                "runner": "wfo",
                "worth_status": "repair_coverage_before_counting",
                "standalone_metrics": {
                    "candidate_trade_count": 140,
                    "exact_trade_count": 125,
                    "profit_factor": 1.8,
                    "avg_pnl_pct": 12.5,
                    "quote_coverage_pct": 94.0,
                },
                "robustness": {
                    "rolling_status": "passed",
                    "stress_5pct_per_side_profit_factor": 1.4,
                },
                "novelty_vs_core_plus_clean_reference": {
                    "strict_new_trade_count": 35,
                    "gap_after_candidate": 8,
                    "incremental_metrics": {"profit_factor": 1.5},
                },
                "side_aware_zero_bid_replay": {"status": "not_required"},
                "error": None,
            },
            {
                "lane_id": "beta",
                "variant_id": "beta_variant",
                "runner": "wfo",
                "worth_status": "repair_stress_before_counting",
                "standalone_metrics": {
                    "candidate_trade_count": 140,
                    "exact_trade_count": 140,
                    "unpriced_trade_count": 0,
                    "profit_factor": 1.7,
                    "quote_coverage_pct": 100.0,
                },
                "robustness": {"rolling_status": "watch", "stress_5pct_per_side_profit_factor": 1.1},
                "novelty_vs_core_plus_clean_reference": {"strict_new_trade_count": 8},
                "side_aware_zero_bid_replay": {"status": "not_required"},
                "error": "boom" if run_failed_count else None,
            },
        ],
    }


class RegularOptionsHistoricalWalkForwardTests(unittest.TestCase):
    def test_build_workflow_report_summarizes_blocked_historical_run(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_ran_candidates_blocked")
        self.assertFalse(report["live_policy_change"])
        self.assertFalse(report["summary"]["protected_forward_holdout_overlap"])
        self.assertEqual(report["summary"]["accepted_exact_trade_count"], 231)
        self.assertEqual(report["candidate_rows"][0]["final_holdout_max_drawdown_pct_points"], 120.0)
        self.assertEqual(report["candidate_rows"][0]["combined_max_drawdown_pct_points"], 180.0)
        self.assertEqual(report["summary"]["all_planned_variant_count"], 2)
        self.assertEqual(report["variant_rows"][0]["variant_id"], "alpha_variant")
        self.assertGreaterEqual(report["repair_queue_summary"]["high_priority_count"], 1)
        self.assertIn("repair_queue", report)

    def test_build_workflow_report_adds_ranked_repair_queue(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        actions = {row["action"] for row in report["repair_queue"]}
        self.assertIn("repair_pre_holdout_quote_coverage_then_rerun_walkforward", actions)
        self.assertIn("repair_stress_or_risk_shape_before_counting", actions)
        self.assertIn("fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows", actions)

        coverage_row = next(
            row for row in report["repair_queue"] if row["action"] == "repair_pre_holdout_quote_coverage_then_rerun_walkforward"
        )
        self.assertEqual(coverage_row["subject_id"], "alpha_variant")
        self.assertEqual(
            coverage_row["execution_permission"],
            "requires_explicit_approval_before_evidence_store_mutation",
        )
        self.assertFalse(coverage_row["live_policy_change_allowed"])

        sample_row = next(
            row
            for row in report["repair_queue"]
            if row["action"] == "fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows"
        )
        self.assertEqual(sample_row["metrics"]["final_holdout_rows_needed_for_30_minimum"], 2)
        self.assertEqual(sample_row["holdout_boundary"], "do_not_use_protected_forward_holdout_to_fill_sample_gap")

    def test_variant_rows_rank_new_post_import_statuses_before_weak_shapes(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["variant_rows"][0]["variant_id"], "alpha_variant")
        self.assertEqual(report["variant_rows"][1]["variant_id"], "beta_variant")
        stress_row = next(row for row in report["repair_queue"] if row["category"] == "peer_variant_stress_repair")
        self.assertEqual(stress_row["subject_id"], "beta_variant")
        self.assertEqual(stress_row["execution_permission"], "read_only_research_ok")

    def test_build_workflow_report_summarizes_repair_targets_from_variant_run_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "alpha_run.json"
            run_path.write_text(
                json.dumps(
                    {
                        "unpriced_trades": [
                            {
                                "ticker": "WMT",
                                "date": "2026-02-24",
                                "missing_quote_date": "2026-03-20",
                                "missing_long_contract_symbol": "WMT260327C00110000",
                                "missing_short_contract_symbol": "WMT260327C00120000",
                                "unpriced_reason": "missing_exit_quote_for_leg",
                            }
                        ]
                    }
                ),
                encoding="utf8",
            )
            all_planned = _all_planned_report()
            all_planned["variants"][0]["run_path"] = str(run_path)

            report = walk_forward.build_workflow_report(
                feature_report=_feature_report(),
                robust_report=_robust_report(),
                all_planned_report=all_planned,
                holdout_contract=_holdout_contract(),
                generated_at_utc="2026-06-14T00:00:00Z",
            )

        coverage_row = next(
            row for row in report["repair_queue"] if row["action"] == "repair_pre_holdout_quote_coverage_then_rerun_walkforward"
        )
        summary = coverage_row["repair_target_summary"]
        self.assertEqual(summary["detail_status"], "available")
        self.assertEqual(summary["base_target_count"], 2)
        self.assertEqual(summary["source_occurrence_count"], 2)
        self.assertEqual(summary["ticker_counts"], {"WMT": 2})
        self.assertEqual(summary["source_field_counts"]["missing_long_contract_symbol"], 1)
        self.assertIn("2026-03-20", summary["missing_quote_dates"])

    def test_build_workflow_report_fails_closed_on_protected_holdout_overlap(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(latest_entry_date="2026-06-05"),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_protected_holdout_overlap")
        self.assertTrue(report["forward_holdout_guard"]["overlaps_protected_range"])
        self.assertIn("protected_forward_holdout_overlap", report["blockers"])

    def test_build_workflow_report_fails_closed_on_missing_holdout_start(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract={"contract_id": "forward-holdout-contract", "status": "active"},
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIn("forward_holdout_start_date_missing", report["blockers"])
        self.assertFalse(report["forward_holdout_guard"]["ordinary_workflow_consumes_holdout"])

    def test_build_workflow_report_fails_closed_on_missing_holdout_date_basis(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract={
                "contract_id": "forward-holdout-contract",
                "status": "active",
                "protected_range": {"start_date": "2026-06-05"},
            },
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIsNone(report["forward_holdout_guard"]["date_basis"])
        self.assertIn("forward_holdout_date_basis_not_candidate_entry_date", report["blockers"])

    def test_build_workflow_report_fails_closed_on_wrong_holdout_date_basis(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract={
                "contract_id": "forward-holdout-contract",
                "status": "active",
                "protected_range": {"date_basis": "calendar_date", "start_date": "2026-06-05"},
            },
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertEqual(report["forward_holdout_guard"]["date_basis"], "calendar_date")
        self.assertIn("forward_holdout_date_basis_not_candidate_entry_date", report["blockers"])

    def test_build_workflow_report_fails_closed_on_unreadable_holdout_contract(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract={"status": "unreadable", "path": "bad.json", "error": "JSONDecodeError"},
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIn("forward_holdout_contract_unreadable", report["blockers"])
        self.assertIn("forward_holdout_contract_id_missing", report["blockers"])
        self.assertIn("forward_holdout_start_date_missing", report["blockers"])

    def test_build_workflow_report_fails_closed_on_invalid_holdout_start_date(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract={
                "contract_id": "forward-holdout-contract",
                "status": "active",
                "protected_range": {"date_basis": "candidate_entry_date", "start_date": "not-a-date"},
            },
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIn("forward_holdout_start_date_missing", report["blockers"])

    def test_build_workflow_report_fails_closed_on_missing_latest_candidate_entry_date(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(latest_entry_date=None),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["summary"]["forward_holdout_guard_status"], "blocked")
        self.assertIn("latest_candidate_entry_date_missing", report["blockers"])

    def test_build_workflow_report_fails_closed_on_all_planned_holdout_overlap(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(as_of_date="2026-06-05"),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_all_planned_input")
        self.assertIn("all_planned_sleeves_as_of_date_overlaps_protected_holdout", report["blockers"])

    def test_build_workflow_report_fails_closed_on_incomplete_all_planned_coverage(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(tested_end_to_end_variant_count=1),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_all_planned_input")
        self.assertEqual(report["all_planned_sleeves"]["status"], "all_planned_sleeves_incomplete_variant_coverage")
        self.assertIn("all_planned_sleeves_incomplete_variant_coverage", report["blockers"])
        self.assertIn("all_planned_sleeves_tested_variant_count_below_implemented", report["blockers"])
        self.assertTrue(report["all_planned_sleeves"]["incomplete_variant_coverage"])

    def test_build_workflow_report_fails_closed_on_all_planned_run_failures(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(run_failed_count=1),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "historical_walkforward_blocked_all_planned_input")
        self.assertIn("all_planned_sleeves_run_failed", report["blockers"])

    def test_render_markdown_includes_boundary_and_risk_columns(self) -> None:
        report = walk_forward.build_workflow_report(
            feature_report=_feature_report(),
            robust_report=_robust_report(),
            all_planned_report=_all_planned_report(),
            holdout_contract=_holdout_contract(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        markdown = walk_forward.render_markdown(report)

        self.assertIn("Holdout DD", markdown)
        self.assertIn("Repair Queue", markdown)
        self.assertIn("Targets", markdown)
        self.assertIn("do_not_use_protected_forward_holdout_to_fill_sample_gap", markdown)
        self.assertIn("Forward holdout guard", markdown)
        self.assertIn("## Forward Holdout Guard", markdown)
        self.assertIn("Status: `passed`", markdown)
        self.assertIn("Peer/Variant Sleeve Results", markdown)
        self.assertIn("historical_walkforward_ran_candidates_blocked", markdown)
        self.assertIn("Production proof still requires fresh exact realized OPRA/NBBO P&L", markdown)

    def test_run_workflow_fails_closed_when_holdout_contract_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            all_planned_path = Path(tmp) / "all-planned.json"
            all_planned_path.write_text(json.dumps(_all_planned_report()), encoding="utf8")
            with (
                mock.patch.object(walk_forward.feature_store, "build_report", return_value=_feature_report()),
                mock.patch.object(walk_forward.robust_search, "build_report", return_value=_robust_report()),
            ):
                report = walk_forward.run_workflow(
                    write=False,
                    holdout_contract_path=Path(tmp) / "missing-holdout.json",
                    all_planned_report_path=all_planned_path,
                )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["contract_status"], "missing")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIn("forward_holdout_contract_missing", report["blockers"])
        self.assertIn("forward_holdout_date_basis_not_candidate_entry_date", report["blockers"])

    def test_run_workflow_fails_closed_when_holdout_contract_payload_is_not_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            all_planned_path = Path(tmp) / "all-planned.json"
            all_planned_path.write_text(json.dumps(_all_planned_report()), encoding="utf8")
            holdout_path = Path(tmp) / "holdout.json"
            holdout_path.write_text("[]", encoding="utf8")
            with (
                mock.patch.object(walk_forward.feature_store, "build_report", return_value=_feature_report()),
                mock.patch.object(walk_forward.robust_search, "build_report", return_value=_robust_report()),
            ):
                report = walk_forward.run_workflow(
                    write=False,
                    holdout_contract_path=holdout_path,
                    all_planned_report_path=all_planned_path,
                )

        self.assertEqual(report["status"], "historical_walkforward_blocked_forward_holdout_guard")
        self.assertEqual(report["forward_holdout_guard"]["contract_status"], "invalid")
        self.assertEqual(report["forward_holdout_guard"]["status"], "blocked")
        self.assertIn("forward_holdout_contract_invalid", report["blockers"])
        self.assertIn("forward_holdout_date_basis_not_candidate_entry_date", report["blockers"])

    def test_run_workflow_refuses_run_all_planned_when_holdout_contract_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_contract = Path(tmp) / "bad-holdout.json"
            bad_contract.write_text("{", encoding="utf8")
            with mock.patch.object(walk_forward.all_planned_sleeves, "run_all_planned_sleeves") as run_mock:
                with self.assertRaisesRegex(RuntimeError, "readable active forward holdout metadata"):
                    walk_forward.run_workflow(
                        write=False,
                        holdout_contract_path=bad_contract,
                        all_planned_report_path=Path(tmp) / "missing-all-planned.json",
                        run_all_planned=True,
                        all_planned_as_of_date=date(2026, 6, 4),
                    )
                run_mock.assert_not_called()

    def test_run_workflow_refuses_run_all_planned_with_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            holdout = Path(tmp) / "holdout.json"
            holdout.write_text(
                json.dumps(
                    {
                        "contract_id": "forward-holdout-contract",
                        "status": "active",
                        "protected_range": {
                            "start_date": "2026-06-05",
                            "date_basis": "candidate_entry_date",
                        },
                    }
                ),
                encoding="utf8",
            )
            with mock.patch.object(walk_forward.all_planned_sleeves, "run_all_planned_sleeves") as run_mock:
                with self.assertRaisesRegex(RuntimeError, "cannot be combined with --no-write"):
                    walk_forward.run_workflow(
                        write=False,
                        holdout_contract_path=holdout,
                        all_planned_report_path=Path(tmp) / "missing-all-planned.json",
                        run_all_planned=True,
                        all_planned_as_of_date=date(2026, 6, 4),
                    )
                run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
