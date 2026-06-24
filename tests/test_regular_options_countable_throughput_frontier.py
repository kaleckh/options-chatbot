from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_countable_throughput_frontier as frontier
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _candidate(**overrides: object) -> dict:
    base = {
        "candidate_id": "fixture_candidate",
        "candidate_family": "fixture_family",
        "exact_rows": 60,
        "strict_new_rows": 60,
        "strict_new_rows_after_opportunity_dedupe": 60,
        "with_candidate_exact_rows": 217,
        "point_profit_factor": 1.4,
        "strict_new_profit_factor": 1.35,
        "combined_profit_factor": 1.4,
        "profit_factor_lower_bound": 1.08,
        "strict_new_profit_factor_lower_bound": 1.05,
        "average_net_pnl_pct": 5.0,
        "strict_new_average_net_pnl_pct": 4.0,
        "stress_profit_factor": 1.15,
        "strict_new_stress_profit_factor": 1.08,
        "final_holdout_exact_rows": 35,
        "final_holdout_profit_factor_lower_bound": 1.03,
        "quote_coverage_pct": 100.0,
        "unpriced_rows": 0,
        "zero_bid_rows": 0,
        "untradable_rows": 0,
        "lookahead_only_rows": 0,
        "rolling_status": "passed",
        "monthly_profitability_status": "passed",
        "max_single_trade_profit_share": 10.0,
        "top_5_trade_profit_share": 30.0,
        "max_month_profit_share": 20.0,
        "max_underlying_profit_share": 25.0,
        "max_expiration_profit_share": 20.0,
        "run_ledger_status": "loaded",
        "strict_new_row_ledger_available": True,
    }
    base.update(overrides)
    return base


class CountableThroughputFrontierTests(unittest.TestCase):
    def test_strict_new_dedupe_blocks_raw_count_overlap(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                exact_rows=60,
                strict_new_rows=35,
                strict_new_rows_after_opportunity_dedupe=35,
                with_candidate_exact_rows=192,
            )
        )

        self.assertEqual(row["with_candidate_exact_rows"], 192)
        self.assertEqual(row["decision"], "blocked_below_strict_new_count")
        self.assertIn("strict_new_rows_35_below_required_43", row["blockers"])

    def test_count_alone_cannot_pass_stress_failure(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                strict_new_rows=80,
                strict_new_rows_after_opportunity_dedupe=80,
                with_candidate_exact_rows=237,
                point_profit_factor=1.30,
                combined_profit_factor=1.30,
                stress_profit_factor=0.85,
            )
        )

        self.assertEqual(row["decision"], "blocked_stress_fragility")

    def test_point_pf_cannot_override_source_quality(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                strict_new_rows=70,
                strict_new_rows_after_opportunity_dedupe=70,
                point_profit_factor=1.60,
                stress_profit_factor=1.20,
                quote_coverage_pct=75.0,
                unpriced_rows=20,
            )
        )

        self.assertEqual(row["decision"], "blocked_execution_quality")
        self.assertIn("quote_coverage_75.0_below_90", row["blockers"])
        self.assertIn("unpriced_rows_20", row["blockers"])

    def test_base_subsidy_cannot_pass(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                strict_new_rows=53,
                strict_new_rows_after_opportunity_dedupe=53,
                strict_new_profit_factor=0.80,
                combined_profit_factor=1.25,
                with_candidate_exact_rows=210,
            )
        )

        self.assertEqual(row["decision"], "rejected_base_subsidized_only")

    def test_clean_but_too_small_stays_blocked(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                candidate_id="sleeve_next_index_refill_v1",
                exact_rows=116,
                strict_new_rows=6,
                strict_new_rows_after_opportunity_dedupe=6,
                with_candidate_exact_rows=163,
                point_profit_factor=1.74,
                combined_profit_factor=1.74,
                stress_profit_factor=1.33,
                quote_coverage_pct=100.0,
            )
        )

        self.assertEqual(row["decision"], "blocked_below_strict_new_count")

    def test_lookahead_only_rows_stay_diagnostic(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                strict_new_rows=50,
                strict_new_rows_after_opportunity_dedupe=50,
                lookahead_only_rows=50,
                point_profit_factor=2.0,
                strict_new_profit_factor=2.0,
            )
        )

        self.assertEqual(row["decision"], "diagnostic_only_lookahead_or_unpriced")

    def test_true_passing_fixture_can_pass(self) -> None:
        row = frontier._classify_candidate(  # noqa: SLF001
            _candidate(
                strict_new_rows_after_opportunity_dedupe=50,
                with_candidate_exact_rows=207,
                strict_new_profit_factor=1.35,
                combined_profit_factor=1.40,
                strict_new_profit_factor_lower_bound=1.05,
                profit_factor_lower_bound=1.08,
                stress_profit_factor=1.15,
                strict_new_stress_profit_factor=1.08,
                final_holdout_exact_rows=35,
                final_holdout_profit_factor_lower_bound=1.03,
                quote_coverage_pct=100.0,
                unpriced_rows=0,
                zero_bid_rows=0,
                lookahead_only_rows=0,
            )
        )

        self.assertEqual(row["decision"], "countable_throughput_candidate_for_forward_freeze_review")

    def test_write_outputs_writes_requested_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="throughput-frontier") as tmp_dir:
            tmp = Path(tmp_dir)
            report = {
                "report_id": frontier.REPORT_ID,
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "status": "current_historical_surface_exhausted_under_current_prohibitions",
                **frontier.READ_ONLY_FLAGS,
                "countable_throughput_candidate_found": False,
                "current_historical_surface_exhausted_under_current_prohibitions": True,
                "base_clean_stack_exact_rows": 157,
                "target_exact_rows": 200,
                "strict_new_gap_required": 43,
                "candidate_count": 0,
                "raw_count_candidate_count": 0,
                "decision_counts": {},
                "row_level_candidate_ledger_status": "fixture",
                "candidate_rankings": [],
                "strict_new_tranche_profitability": [],
                "blocker_table": [],
                "prohibited_actions": list(frontier.PROHIBITED_ACTIONS),
            }
            artifacts = frontier.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "report.md",
                artifact_json=tmp / "artifacts" / "frontier.json",
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertTrue((tmp / "artifacts" / "frontier.json").exists())
            self.assertIn("artifact_json", artifacts)

    def test_realistic_fixture_reproduces_known_blockers(self) -> None:
        with WorkspaceTempDir(prefix="throughput-frontier") as tmp_dir:
            tmp = Path(tmp_dir)
            run = tmp / "run.json"
            robust = tmp / "robust.json"
            _write_json(run, {"trades": [{"ticker": "SPY", "date": "2025-01-01", "net_pnl_pct": 5.0}], "unpriced_trades": [{}] * 46})
            _write_json(
                robust,
                {
                    "top_winner_removal": [{"remaining_metrics": {"profit_factor": 0.9}}],
                    "slippage_stress": [{"metrics": {"profit_factor": 0.9}}],
                },
            )
            all_planned = tmp / "all-planned.json"
            _write_json(
                all_planned,
                {
                    "variants": [
                        {
                            "variant_id": "tracked_winner_chain_native_research_all_sleeves",
                            "lane_id": "tracked_winner_primary",
                            "description": "Tracked winner",
                            "run_path": str(run),
                            "robustness_path": str(robust),
                            "standalone_metrics": {
                                "candidate_trade_count": 158,
                                "exact_trade_count": 112,
                                "profit_factor": 1.23,
                                "avg_pnl_pct": 6.73,
                                "quote_coverage_pct": 70.9,
                                "unpriced_trade_count": 46,
                            },
                            "novelty_vs_core_plus_clean_reference": {
                                "strict_new_trade_count": 112,
                                "with_candidate_trade_count": 269,
                                "incremental_metrics": {"profit_factor": 1.23, "avg_pnl_pct": 6.73},
                            },
                            "robustness": {"stress_5pct_per_side_profit_factor": 0.9, "rolling_status": "watch"},
                        },
                        {
                            "variant_id": "sleeve_next_index_refill_v1",
                            "lane_id": "etf_index_pullback_control",
                            "run_path": str(run),
                            "robustness_path": str(robust),
                            "standalone_metrics": {
                                "candidate_trade_count": 116,
                                "exact_trade_count": 116,
                                "profit_factor": 1.74,
                                "avg_pnl_pct": 20.49,
                                "quote_coverage_pct": 100.0,
                                "unpriced_trade_count": 0,
                            },
                            "novelty_vs_core_plus_clean_reference": {
                                "strict_new_trade_count": 6,
                                "with_candidate_trade_count": 163,
                                "incremental_metrics": {"profit_factor": 0.0, "avg_pnl_pct": -94.65},
                            },
                            "robustness": {"stress_5pct_per_side_profit_factor": 1.33, "rolling_status": "passed"},
                        },
                    ]
                },
            )
            for name in ("momentum", "optional"):
                _write_json(tmp / f"{name}.json", {"status": "loaded", "overall_status": "loaded"})
            report = frontier.build_report(
                all_planned_path=all_planned,
                momentum_edge_path=tmp / "momentum.json",
                robust_edge_path=tmp / "optional.json",
                hypothesis_tournament_path=tmp / "optional.json",
                walk_forward_path=tmp / "optional.json",
                evidence_burndown_path=tmp / "optional.json",
                source_replay_path=tmp / "optional.json",
                monthly_profitability_path=tmp / "optional.json",
                robust_search_path=tmp / "optional.json",
                generated_at_utc="2026-06-22T00:00:00Z",
            )

        decisions = {row["candidate_id"]: row["decision"] for row in report["candidate_rankings"]}
        self.assertEqual(decisions["tracked_winner_chain_native_research_all_sleeves"], "blocked_execution_quality")
        self.assertEqual(decisions["sleeve_next_index_refill_v1"], "blocked_below_strict_new_count")
        self.assertFalse(report["countable_throughput_candidate_found"])


if __name__ == "__main__":
    unittest.main()
