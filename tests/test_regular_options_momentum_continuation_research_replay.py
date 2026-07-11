from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import (
    build_regular_options_momentum_continuation_research_replay as replay,
)
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )


def _trade(**overrides: object) -> dict:
    row = {
        "ticker": "QQQ",
        "date": "2025-08-14",
        "exit_date": "2025-09-11",
        "strategy_type": "vertical_spread",
        "type": "call",
        "contract_symbol": "QQQ250912C00581000",
        "short_contract_symbol": "QQQ250912C00600000",
        "net_debit": 8.44,
        "entry_spread_ask_bid_debit": 8.44,
        "exit_spread_bid_ask_value": 10.50,
        "net_pnl_usd": 203.40,
        "net_pnl_pct": 24.09,
        "truth_source": "historical_imported",
        "execution_realism": "quote_backed_intraday_replay",
        "spy_ret5": 1.2,
        "qqq_ret5": 1.6,
        "vix_bucket": "low_mid",
        "breadth_confirmation": "confirmed",
        "long_entry_quote_basis": "ask_bid",
        "short_entry_quote_basis": "ask_bid",
    }
    row.update(overrides)
    return row


class MomentumContinuationResearchReplayTests(unittest.TestCase):
    def _fixture_paths(
        self, tmp: Path, trades: list[dict]
    ) -> tuple[Path, Path, Path, Path, Path]:
        run_path = tmp / "runs" / "momentum_run.json"
        _write_json(
            run_path,
            {
                "playbook": "fixture_momentum",
                "truth_source": "historical_imported",
                "execution_realism": "quote_backed_intraday_replay",
                "imported_data_scope": "trusted",
                "trades": trades,
                "unpriced_trades": [],
            },
        )
        all_planned = tmp / "all_planned.json"
        _write_json(
            all_planned,
            {
                "variants": [
                    {
                        "variant_id": "fixture_momentum",
                        "run_path": str(run_path),
                        "standalone_metrics": {
                            "exact_trade_count": len(trades),
                            "quote_coverage_pct": 100.0,
                            "profit_factor": 2.0,
                        },
                        "robustness": {"stress_5pct_per_side_profit_factor": 1.2},
                        "novelty_vs_core_plus_clean_reference": {
                            "base_clean_trade_count": 157,
                            "strict_new_trade_count": len(trades),
                            "with_candidate_trade_count": 157 + len(trades),
                        },
                    }
                ]
            },
        )
        prereg = tmp / "prereg.json"
        _write_json(
            prereg,
            {
                "status": "preregistered_design_only",
                "concept_id": replay.CONCEPT_ID,
                "concept": {"concept_id": replay.CONCEPT_ID},
            },
        )
        selector = tmp / "selector.json"
        _write_json(
            selector, {"top_ranked_candidate": {"concept_id": replay.CONCEPT_ID}}
        )
        goal = tmp / "goal.json"
        _write_json(
            goal,
            {
                "current_decision_state": "underpowered_forward_evidence",
                "forward_evidence_accounting": {
                    "post_freeze_strict_exact_completed_rows": 0,
                    "minimum_required": 30,
                    "strict_usd_pf_lower_bound_5pct": None,
                    "live_entry_allowed": False,
                    "auto_track_allowed": False,
                    "broker_order_allowed": False,
                    "promotion_ready": False,
                },
            },
        )
        return prereg, selector, all_planned, goal, run_path

    def test_proof_row_requires_all_point_in_time_and_side_aware_fields(self) -> None:
        with WorkspaceTempDir(prefix="momentum-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            prereg, selector, all_planned, goal, run_path = self._fixture_paths(
                tmp, [_trade()]
            )
            report = replay.build_report(
                preregistered_playbook_path=prereg,
                selector_path=selector,
                all_planned_path=all_planned,
                goal_loop_path=goal,
                run_paths=[run_path],
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(
            report["status"],
            "implemented_research_replay_has_proof_rows_not_forward_proof",
        )
        self.assertTrue(report["research_only_replay_harness_implemented"])
        self.assertTrue(report["historical_replay_performed"])
        self.assertFalse(report["lane_implementation_performed"])
        self.assertFalse(report["accepted_profitability"])
        self.assertEqual(report["proof_qualified"]["row_count"], 1)
        self.assertEqual(report["proof_qualified"]["metrics"]["net_pnl_usd"], 203.4)

    def test_missing_breadth_and_side_aware_exit_blocks_old_diagnostic_marks(
        self,
    ) -> None:
        with WorkspaceTempDir(prefix="momentum-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                exit_spread_bid_ask_value=None,
                breadth_confirmation=None,
                long_entry_quote_basis="mid",
                short_entry_quote_basis="mid",
                spread_diagnostics_proof_role="diagnostic_only",
            )
            prereg, selector, all_planned, goal, run_path = self._fixture_paths(
                tmp, [trade]
            )
            report = replay.build_report(
                preregistered_playbook_path=prereg,
                selector_path=selector,
                all_planned_path=all_planned,
                goal_loop_path=goal,
                run_paths=[run_path],
            )

        self.assertEqual(
            report["status"], "implemented_research_replay_no_proof_qualified_rows"
        )
        self.assertEqual(report["proof_qualified"]["row_count"], 0)
        self.assertEqual(report["diagnostic_only_existing_marks"]["row_count"], 1)
        sample = report["denominator"]["sample_rows"][0]
        self.assertIn(
            "missing_point_in_time_breadth_confirmation", sample["reason_codes"]
        )
        self.assertIn("missing_side_aware_exit_bid_ask", sample["reason_codes"])
        self.assertIn("entry_contains_mid_quote_basis", sample["reason_codes"])

    def test_missing_quote_date_preserves_exact_planned_policy_exit(self) -> None:
        with WorkspaceTempDir(prefix="momentum-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                exit_date=None,
                missing_quote_date="2025-09-05",
                exit_spread_bid_ask_value=None,
                net_pnl_usd=None,
            )
            prereg, selector, all_planned, goal, run_path = self._fixture_paths(
                tmp, [trade]
            )
            report = replay.build_report(
                preregistered_playbook_path=prereg,
                selector_path=selector,
                all_planned_path=all_planned,
                goal_loop_path=goal,
                run_paths=[run_path],
            )

        sample = report["denominator"]["sample_rows"][0]
        self.assertEqual(sample["exit_date"], "2025-09-05")
        self.assertEqual(
            sample["exit_date_source"],
            "planned_policy_exit_missing_quote_date",
        )
        self.assertIn("missing_side_aware_exit_bid_ask", sample["reason_codes"])

    def test_protected_holdout_and_duplicate_rows_are_blocked(self) -> None:
        with WorkspaceTempDir(prefix="momentum-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            duplicate = _trade()
            holdout = _trade(
                date="2026-06-05",
                exit_date="2026-06-19",
                contract_symbol="QQQ260619C00581000",
            )
            prereg, selector, all_planned, goal, run_path = self._fixture_paths(
                tmp, [_trade(), duplicate, holdout]
            )
            report = replay.build_report(
                preregistered_playbook_path=prereg,
                selector_path=selector,
                all_planned_path=all_planned,
                goal_loop_path=goal,
                run_paths=[run_path],
            )

        counts = report["denominator"]["status_counts"]
        self.assertEqual(counts["duplicate_within_research_harness"], 1)
        self.assertEqual(counts["protected_holdout_blocked"], 1)
        self.assertEqual(report["proof_qualified"]["row_count"], 1)

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="momentum-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            prereg, selector, all_planned, goal, run_path = self._fixture_paths(
                tmp, [_trade()]
            )
            report = replay.build_report(
                preregistered_playbook_path=prereg,
                selector_path=selector,
                all_planned_path=all_planned,
                goal_loop_path=goal,
                run_paths=[run_path],
            )
            artifacts = replay.write_outputs(
                report, output_dir=tmp / "out", docs_report=tmp / "docs" / "replay.md"
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "replay.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "replay.md").read_text(encoding="utf8")
            self.assertIn("Momentum Continuation Research Replay", markdown)


if __name__ == "__main__":
    unittest.main()
