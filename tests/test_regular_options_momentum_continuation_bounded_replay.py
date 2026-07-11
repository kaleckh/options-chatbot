from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_momentum_continuation_bounded_replay as replay
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf8",
    )


def _selector(tmp: Path, *, valid: bool = True, top_candidate: bool = True) -> Path:
    row = {
        "concept_id": replay.CONCEPT_ID if valid else "wrong",
        "readiness_status": "candidate_for_research_only_implementation_approval"
        if valid
        else "blocked",
    }
    path = tmp / "selector.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_preregistered_playbook_readiness_selector",
            "status": (
                "candidate_selected_for_research_only_implementation_approval"
                if top_candidate
                else "no_research_implementation_candidate_ready_without_blocker"
            ),
            "top_ranked_candidate": row if top_candidate else None,
            "design_inventory": [row],
            "accepted_profitability": False,
        },
    )
    return path


def _playbook(tmp: Path, *, valid: bool = True) -> Path:
    path = tmp / "playbook.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_preregistered_momentum_continuation_playbook",
            "status": "preregistered_design_only" if valid else "implemented",
            "concept_id": replay.CONCEPT_ID if valid else "wrong",
            "structure": replay.EXPECTED_STRUCTURE if valid else "wrong",
            "accepted_profitability": False,
            "concept": {
                "concept_id": replay.CONCEPT_ID if valid else "wrong",
                "structure": replay.EXPECTED_STRUCTURE if valid else "wrong",
                "permitted_research_universe": ["SPY", "QQQ"],
            },
        },
    )
    return path


def _source_replay(tmp: Path, *, valid: bool = True) -> Path:
    path = tmp / "source.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_momentum_continuation_research_replay",
            "status": "implemented_research_replay_no_proof_qualified_rows",
            "concept_id": replay.CONCEPT_ID if valid else "wrong",
            "research_only_replay_harness_implemented": valid,
            "accepted_profitability": False,
            "denominator": {"row_count": 2},
            "diagnostic_only_existing_marks": {
                "metrics": {"net_pnl_usd": -10.0, "profit_factor": 0.8}
            },
        },
    )
    return path


def _resolution(tmp: Path, *, candidate: bool = True) -> Path:
    path = tmp / "resolution.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_momentum_continuation_proof_blocker_resolution",
            "status": "momentum_continuation_proof_candidate_for_review_not_forward_proof"
            if candidate
            else "momentum_continuation_blocked_missing_local_proof_inputs",
            "concept_id": replay.CONCEPT_ID,
            "accepted_profitability": False,
            "historical_rows_are_forward_proof": False,
            "read_only": True,
            "broker_order_allowed": False,
            "proof_qualified_rows_after_resolution": 0 if not candidate else 30,
            "blockers": []
            if candidate
            else [
                "missing_point_in_time_vix_bucket",
                "missing_point_in_time_breadth_confirmation",
            ],
            "resolution_counts": {
                "side_aware_quotes_resolved": 0 if not candidate else 30,
                "point_in_time_inputs_resolved": 0 if not candidate else 30,
                "proof_qualified_candidate_rows": 0 if not candidate else 30,
                "blocker_counts": {}
                if candidate
                else {"missing_point_in_time_vix_bucket": 2},
            },
            "quote_coverage_resolution": {
                "eligible_pre_quote_row_count": 30,
                "eligible_side_aware_row_count": 30 if candidate else 0,
                "eligible_quote_coverage": 1.0 if candidate else 0.0,
            },
            "strict_research_metrics": {
                "net_pnl_usd": None,
                "profit_factor": None,
                "bootstrap_pf_lower_bound_5pct": None,
                "stress_pf": None,
            },
            "side_aware_diagnostic_metrics": {
                "net_pnl_usd": 100.0,
                "profit_factor": 2.0,
            },
        },
    )
    return path


def _holdout(tmp: Path) -> Path:
    path = tmp / "holdout.json"
    _write_json(path, {"protected_range": {"start_date": "2026-06-01"}})
    return path


def _base(tmp: Path, rows: list[dict] | None = None) -> Path:
    path = tmp / "base.json"
    _write_json(path, {"rows": rows or []})
    return path


def _candidate(**overrides: object) -> dict:
    row = {
        "ticker": "QQQ",
        "entry_date": "2026-05-20",
        "expiration": "2026-06-19",
        "long_call_strike": 580,
        "short_call_strike": 600,
        "long_call_ask": 10.10,
        "short_call_bid": 1.80,
        "long_call_bid_exit": 13.00,
        "short_call_ask_exit": 2.10,
        "fees_usd": 2.0,
        "slippage_usd": 0.6,
        "trend_confirmed": True,
        "breadth_confirmed": True,
        "vix_bucket": "low_mid",
    }
    row.update(overrides)
    return row


class MomentumContinuationBoundedReplayTests(unittest.TestCase):
    def _paths(
        self,
        tmp: Path,
        *,
        selector_valid: bool = True,
        selector_top_candidate: bool = True,
        resolution_candidate: bool = True,
    ) -> dict[str, Path]:
        return {
            "selector_path": _selector(
                tmp, valid=selector_valid, top_candidate=selector_top_candidate
            ),
            "preregistered_playbook_path": _playbook(tmp),
            "source_replay_path": _source_replay(tmp),
            "proof_blocker_resolution_path": _resolution(
                tmp, candidate=resolution_candidate
            ),
            "holdout_contract_path": _holdout(tmp),
            "clean_base_stack_path": _base(tmp),
        }

    def test_real_repo_gate_preserves_current_momentum_blockers(self) -> None:
        report = replay.build_report(generated_at_utc="2026-06-23T00:00:00Z")

        self.assertEqual(
            report["status"], "blocked_momentum_continuation_bounded_replay"
        )
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertEqual(
            report["replay_gate_blockers"],
            [
                "missing_policy_exit_date",
                "preregistered_stress_test_not_implemented",
            ],
        )
        self.assertEqual(report["metrics"]["strict_new_exact_completed_rows"], 264)
        self.assertEqual(report["metrics"]["side_aware_quotes_resolved"], 875)
        self.assertEqual(report["metrics"]["quote_coverage"], 0.9747)

    def test_fixture_replay_uses_side_aware_debit_spread_formula_and_statuses(
        self,
    ) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = [
                _candidate(),
                dict(_candidate()),
                _candidate(ticker="SPY", entry_date="2026-05-21", long_call_ask=None),
                _candidate(ticker="IWM", short_call_bid=0.0),
                _candidate(ticker="DIA", entry_date="2026-06-01"),
                _candidate(ticker="QQQ", long_call_strike=610, short_call_strike=600),
                _candidate(
                    ticker="SPY", entry_date="2026-05-22", breadth_confirmed=False
                ),
                _candidate(ticker="SPY", entry_date="2026-05-23", vix_bucket="high"),
            ]
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, rows)
            paths = self._paths(tmp)
            paths["fixture_candidates_path"] = fixture

            report = replay.build_report(**paths)

        counts = report["metrics"]["denominator_counts"]
        self.assertTrue(report["historical_replay_performed"])
        self.assertEqual(counts["exact_exit_captured"], 1)
        self.assertEqual(counts["duplicate_strict_new_identity"], 1)
        self.assertEqual(counts["missing_leg_quote"], 1)
        self.assertEqual(counts["zero_bid_or_untradable"], 1)
        self.assertEqual(counts["protected_holdout_blocked"], 1)
        self.assertEqual(counts["malformed_candidate"], 1)
        self.assertEqual(counts["rejected_no_breadth_confirmation"], 1)
        self.assertEqual(counts["rejected_vix_bucket"], 1)
        self.assertEqual(report["metrics"]["net_pnl_usd"], 257.4)
        self.assertEqual(
            report["status"], "rejected_momentum_continuation_bounded_replay"
        )

    def test_base_stack_overlap_is_rejected_as_duplicate(self) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            row = _candidate()
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, [row])
            paths = self._paths(tmp)
            paths["fixture_candidates_path"] = fixture
            paths["clean_base_stack_path"] = _base(tmp, [row])

            report = replay.build_report(**paths)

        self.assertEqual(
            report["metrics"]["denominator_counts"]["duplicate_strict_new_identity"], 1
        )
        self.assertEqual(report["metrics"]["exact_completed_rows"], 0)

    def test_invalid_selector_fails_closed_before_fixture_replay(self) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, [_candidate()])
            paths = self._paths(tmp, selector_valid=False)
            paths["fixture_candidates_path"] = fixture

            report = replay.build_report(**paths)

        self.assertEqual(
            report["status"], "blocked_momentum_continuation_bounded_replay"
        )
        self.assertFalse(report["historical_replay_performed"])
        self.assertIn(
            "selector_inventory_missing_momentum_continuation",
            report["replay_gate_blockers"],
        )
        self.assertFalse(report["accepted_profitability"])

    def test_selector_without_top_candidate_is_not_a_branch_replay_blocker(
        self,
    ) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                **self._paths(
                    tmp, selector_top_candidate=False, resolution_candidate=False
                )
            )

        self.assertTrue(report["validations"]["selector_valid"])
        self.assertEqual(report["validations"]["selector_reasons"], [])
        self.assertNotIn(
            "selector_top_candidate_not_momentum_continuation",
            report["replay_gate_blockers"],
        )
        self.assertNotIn(
            "selector_readiness_not_research_only_candidate",
            report["replay_gate_blockers"],
        )
        self.assertIn(
            "missing_point_in_time_breadth_confirmation", report["replay_gate_blockers"]
        )

    def test_prior_resolution_blockers_are_carried_forward(self) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(**self._paths(tmp, resolution_candidate=False))

        self.assertEqual(
            report["status"], "blocked_momentum_continuation_bounded_replay"
        )
        self.assertIn(
            "missing_point_in_time_vix_bucket", report["replay_gate_blockers"]
        )
        self.assertIn(
            "missing_point_in_time_breadth_confirmation", report["replay_gate_blockers"]
        )

    def test_forged_or_incoherent_resolution_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            paths = self._paths(tmp)
            payload = json.loads(
                paths["proof_blocker_resolution_path"].read_text(encoding="utf8")
            )
            payload["report_id"] = "forged"
            payload["quote_coverage_resolution"]["eligible_side_aware_row_count"] = 31
            _write_json(paths["proof_blocker_resolution_path"], payload)
            report = replay.build_report(**paths)

        self.assertEqual(
            report["status"], "blocked_momentum_continuation_bounded_replay"
        )
        self.assertIn(
            "missing_or_invalid_momentum_proof_blocker_resolution",
            report["replay_gate_blockers"],
        )

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="momentum-bounded") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(**self._paths(tmp, resolution_candidate=False))
            artifacts = replay.write_outputs(
                report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md"
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)

    def test_runner_does_not_call_scanner_or_trading_paths(self) -> None:
        source = Path(replay.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
        forbidden_calls = {
            "run_daily_ops",
            "log_scan_picks",
            "validate_pending_scan_candidates",
            "submit_order",
            "create_position",
            "auto_track",
            "import_quotes",
        }
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
