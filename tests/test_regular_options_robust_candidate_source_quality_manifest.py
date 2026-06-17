from __future__ import annotations

import unittest

from scripts import build_regular_options_robust_candidate_source_quality_manifest as manifest


def _walk_forward_report() -> dict:
    blockers = [
        "bullish_pullback_core:unpriced_candidates_3",
        "final_holdout_exact_trades_below_30",
        "final_holdout_pf_lb_below_selection_adjusted_bar",
        "lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0",
        "lane_a:conservative_zero_bid_pf_0.85_below_1_3",
        "lane_a:conservative_zero_bid_unpriced_11",
        "lane_a_chain_native_ret20_4_stop200_time75:quote_coverage_53.1_below_97_5",
        "lane_a_chain_native_ret20_4_stop200_time75:rolling_oos_watch",
        "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137",
        "paper_shadow_fill_evidence_pending",
        "source_quality_gate:quality_pending",
    ]
    return {
        "status": "historical_walkforward_ran_candidates_blocked",
        "summary": {
            "protected_forward_holdout_start_date": "2026-06-05",
            "protected_forward_holdout_overlap": False,
        },
        "repair_queue": [
            {
                "priority_rank": 1,
                "priority_band": "high",
                "category": "candidate_source_quality_repair",
                "subject_id": "combined_portfolio",
                "action": "repair_source_quality_and_unpriced_rows_before_any_nomination",
                "execution_permission": "requires_explicit_approval_before_evidence_store_mutation",
                "metrics": {
                    "combined_exact_trade_count": 231,
                    "final_holdout_exact_trade_count": 28,
                    "final_holdout_profit_factor": 1.27,
                    "final_holdout_pf_lb_5pct": 0.61,
                },
                "blockers": blockers,
            },
            {
                "priority_rank": 2,
                "priority_band": "high",
                "category": "candidate_source_quality_repair",
                "subject_id": "lane:bullish_pullback_core",
                "action": "repair_source_quality_and_unpriced_rows_before_any_nomination",
                "execution_permission": "requires_explicit_approval_before_evidence_store_mutation",
                "metrics": {"combined_exact_trade_count": 127, "final_holdout_exact_trade_count": 18},
                "blockers": [
                    "bullish_pullback_core:unpriced_candidates_3",
                    "final_holdout_exact_trades_below_30",
                    "paper_shadow_fill_evidence_pending",
                    "source_quality_gate:quality_pending",
                ],
            },
            {
                "priority_rank": 3,
                "priority_band": "high",
                "category": "candidate_source_quality_repair",
                "subject_id": "lane:lane_a_chain_native_ret20_4_stop200_time75",
                "action": "repair_source_quality_and_unpriced_rows_before_any_nomination",
                "execution_permission": "requires_explicit_approval_before_evidence_store_mutation",
                "metrics": {"combined_exact_trade_count": 104, "final_holdout_exact_trade_count": 14},
                "blockers": [
                    "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates_137",
                    "lane_a:conservative_zero_bid_pf_0.85_below_1_3",
                    "paper_shadow_fill_evidence_pending",
                    "validation_exact_trades_below_30",
                    "source_quality_gate:quality_pending",
                ],
            },
        ],
    }


def _robust_report() -> dict:
    split_metrics = {
        "validation": {"exact_trade_count": 59},
        "final_holdout": {
            "exact_trade_count": 28,
            "profit_factor": 1.27,
            "bootstrap": {"pf_lb_5pct": 0.61},
        },
    }
    quality_gate = {"status": "source_quality_gate_blocked", "blockers": ["source_quality_gate:quality_pending"]}
    return {
        "status": "historical_candidates_blocked",
        "summary": {
            "accepted_exact_trade_count": 231,
            "ready_candidate_count": 0,
            "candidate_count": 3,
            "selection_adjusted_bar": 1.18,
            "source_quality_gate_status": "source_quality_gate_blocked",
            "source_quality_scope_excluded_trade_count": 3,
        },
        "candidates": [
            {
                "candidate_id": "combined_portfolio",
                "status": "historical_candidate_blocked",
                "historical_nomination_ready": False,
                "split_metrics": split_metrics,
                "selection_adjustment": {"selection_adjusted_bar": 1.18},
                "source_quality_gate": quality_gate,
                "source_quality_exclusions": [
                    {
                        "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                        "ticker": "CVX",
                        "lane_id": "bullish_pullback_core",
                    }
                ],
            },
            {
                "candidate_id": "lane:bullish_pullback_core",
                "status": "historical_candidate_blocked",
                "historical_nomination_ready": False,
                "split_metrics": split_metrics,
                "selection_adjustment": {"selection_adjusted_bar": 1.18},
                "source_quality_gate": quality_gate,
                "source_quality_exclusions": [
                    {
                        "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                        "ticker": "CVX",
                        "lane_id": "bullish_pullback_core",
                    }
                ],
            },
            {
                "candidate_id": "lane:lane_a_chain_native_ret20_4_stop200_time75",
                "status": "historical_candidate_blocked",
                "historical_nomination_ready": False,
                "split_metrics": split_metrics,
                "selection_adjustment": {"selection_adjusted_bar": 1.18},
                "source_quality_gate": quality_gate,
                "source_quality_exclusions": [],
            },
        ],
    }


def _run_with_unpriced_rows() -> dict:
    return {
        "candidate_trade_count": 3,
        "exact_contract_match_count": 1,
        "quote_coverage_pct": 33.3,
        "unpriced_trades": [
            {
                "ticker": "WMT",
                "non_promotable_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": "2026-03-25",
                "missing_short_contract_symbol": "WMT260402C00140000",
                "long_contract_symbol": "WMT260402C00128000",
            },
            {
                "ticker": "JNJ",
                "non_promotable_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": "2026-03-23",
                "missing_short_contract_symbol": "JNJ260327C00260000",
                "long_contract_symbol": "JNJ260327C00245000",
            },
            {
                "ticker": "META",
                "non_promotable_reason": "no_chain_native_spread",
                "long_contract_symbol": "META250926C00780000",
            },
        ],
    }


def _zero_bid_report() -> dict:
    return {
        "generated_at_utc": "2026-05-31T02:40:58Z",
        "modes": {
            "conservative": {
                "candidate_count": 127,
                "priced_count": 126,
                "unpriced_count": 1,
                "combined_lane_a_priced_count": 281,
                "combined_lane_a_unpriced_count": 11,
                "combined_lane_a_quote_coverage_pct": 96.2,
                "zero_bid_priced_count": 118,
                "combined_with_existing_lane_a_metrics": {"profit_factor": 0.85, "avg_pnl_pct": -6.51},
                "side_aware_metrics": {"profit_factor": 0.11, "avg_pnl_pct": -66.59, "trade_count": 126},
            }
        },
    }


class RegularOptionsRobustCandidateSourceQualityManifestTests(unittest.TestCase):
    def test_summarize_unpriced_targets_splits_quote_and_selection_gaps(self) -> None:
        summary = manifest.summarize_unpriced_targets(_run_with_unpriced_rows(), source_path="run.json")

        self.assertEqual(summary["unpriced_count"], 3)
        self.assertEqual(summary["missing_quote_count"], 2)
        self.assertEqual(summary["no_chain_native_spread_count"], 1)
        self.assertEqual(summary["missing_leg_counts"]["short"], 2)
        self.assertEqual(summary["ticker_counts"]["WMT"], 1)
        self.assertIn("2026-03-25", summary["missing_quote_dates"])

    def test_build_manifest_classifies_rows_and_permissions(self) -> None:
        report = manifest.build_manifest(
            walk_forward_report=_walk_forward_report(),
            robust_search_report=_robust_report(),
            source_quality_policy={
                "status": "active",
                "rules": [{"rule_id": "cvx_zero_bid_tradability_candidate_scope_v1"}],
            },
            multilane_report={"quality_gate": {"overall_status": "quality_pending"}},
            bullish_pullback_run=_run_with_unpriced_rows(),
            lane_a_run=_run_with_unpriced_rows(),
            lane_a_zero_bid_report=_zero_bid_report(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        self.assertEqual(report["status"], "blocked_non_promotable_observe_only")
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(report["summary"]["high_priority_row_count"], 3)
        self.assertGreaterEqual(report["summary"]["permission_counts"]["read_only_research_ok"], 1)
        self.assertGreaterEqual(
            report["summary"]["permission_counts"]["requires_explicit_approval_before_evidence_store_mutation"],
            1,
        )
        self.assertGreaterEqual(report["summary"]["permission_counts"]["requires_policy_change_approval"], 1)
        self.assertGreaterEqual(report["summary"]["permission_counts"]["not_actionable_without_forward_evidence"], 1)

        classes = {
            classification["class_id"]
            for row in report["rows"]
            for classification in row["classifications"]
        }
        self.assertIn("importable_missing_quote_candidate", classes)
        self.assertIn("observed_zero_bid_tradability_kill_candidate", classes)
        self.assertIn("no_chain_native_spread_selection_gap", classes)
        self.assertIn("paper_shadow_evidence_gap", classes)
        self.assertIn("pure_statistical_sample_blocker", classes)
        self.assertEqual(
            report["target_level_classifications"]["lane_a_zero_bid_tradability"]["zero_bid_exit_rate_pct"],
            41.99,
        )

    def test_render_markdown_carries_blocked_boundary_and_prohibitions(self) -> None:
        report = manifest.build_manifest(
            walk_forward_report=_walk_forward_report(),
            robust_search_report=_robust_report(),
            source_quality_policy={"status": "active", "rules": []},
            multilane_report={},
            bullish_pullback_run=_run_with_unpriced_rows(),
            lane_a_run=_run_with_unpriced_rows(),
            lane_a_zero_bid_report=_zero_bid_report(),
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        markdown = manifest.render_markdown(report)

        self.assertIn("blocked, non-promotable, and observe-only", markdown)
        self.assertIn("do not run --run-all-planned", markdown)
        self.assertIn("requires_policy_change_approval", markdown)


if __name__ == "__main__":
    unittest.main()
