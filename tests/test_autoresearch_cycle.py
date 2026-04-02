import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.autoresearch_cycle as cycle


def _fake_backtest_result(
    *,
    lookback_years: int,
    pricing_lane: str,
    playbook: str,
    profit_factor: float = 1.1,
    avg_pnl_pct: float = 3.0,
    directional_accuracy_pct: float = 55.0,
    max_drawdown_pct: float = 12.0,
    total_trades: int = 24,
    candidate_trade_count: int | None = None,
    priced_trade_count: int | None = None,
    unpriced_trade_count: int = 0,
    trades: list[dict] | None = None,
    selection_source_counts: dict | None = None,
) -> dict:
    return {
        "run_at": "2026-03-30T15:00:00",
        "mode": "backtest",
        "lookback_years": lookback_years,
        "pricing_lane": pricing_lane,
        "truth_source": pricing_lane if pricing_lane.startswith("historical_") else "synthetic_research",
        "playbook": playbook,
        "n_picks": 1,
        "iv_adj": 1.2,
        "total_days": 120,
        "total_trades": total_trades,
        "candidate_trade_count": candidate_trade_count if candidate_trade_count is not None else total_trades + unpriced_trade_count,
        "priced_trade_count": priced_trade_count if priced_trade_count is not None else total_trades,
        "unpriced_trade_count": unpriced_trade_count,
        "avg_picks_per_day": round(total_trades / 120, 2),
        "win_rate_pct": 52.0,
        "full_hit_rate_pct": 40.0,
        "directional_accuracy_pct": directional_accuracy_pct,
        "profit_factor": profit_factor,
        "avg_pnl_pct": avg_pnl_pct,
        "sharpe": 0.8,
        "max_drawdown_pct": max_drawdown_pct,
        "selection_source_counts": selection_source_counts or {"replay_calibrated": total_trades},
        "trades": trades or [],
    }


def _fake_test_report(*, passed: bool = True) -> dict:
    return {
        "generated_at": "2026-03-30T15:00:00",
        "commands": [
            {
                "command": "npm run verify:research",
                "returncode": 0 if passed else 1,
                "passed": passed,
                "stdout": "ok",
                "stderr": "",
            },
        ],
        "all_passed": passed,
    }


class AutoresearchCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proposal = self.root / "docs" / "autoresearch" / "proposal.md"
        self.proposal.parent.mkdir(parents=True, exist_ok=True)
        self.proposal.write_text("# Proposal\n", encoding="utf8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run_dirs(self) -> list[Path]:
        root = self.root / "research_runs"
        return sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []

    def _write_phase_manifest(self) -> Path:
        path = self.root / "docs" / "autoresearch" / "phase.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "phase_id": "truth-first",
                    "mode": "validation",
                    "freeze_search": True,
                    "allowed_truth_lanes": ["synthetic_research", "historical_imported_daily", "historical_imported"],
                    "required_watchlist": ["SPY", "QQQ"],
                    "required_baseline_control": "baseline",
                    "cohorts": [
                        {
                            "id": "baseline",
                            "role": "control",
                            "label": "Baseline",
                            "playbooks": ["broad"],
                            "overrides": {},
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf8",
        )
        return path

    def test_runner_creates_expected_artifacts_and_manifest_fields(self):
        def fake_backtest(**kwargs):
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
            )

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.1}}):
            code = cycle.main(
                [
                    "--slug",
                    "Tech Floor",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--playbook",
                    "broad",
                    "--playbook",
                    "bullish_mean_reversion",
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        run_dir = self._run_dirs()[0]
        expected_files = {
            "manifest.json",
            "proposal.md",
            "tests.txt",
            "matrix.json",
            "primary_report.json",
            "experiments.json",
            "stability.json",
            "policy.json",
            "metric_truth.json",
            "evidence_bundle.json",
            "decision_packet.json",
            "decision.md",
        }
        self.assertTrue(expected_files.issubset({path.name for path in run_dir.iterdir()}))

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["slug"], "tech-floor")
        self.assertEqual(manifest["playbooks"], ["broad", "bullish_mean_reversion"])
        self.assertEqual(manifest["mode"], "search")
        self.assertEqual(manifest["defaults"]["primary_scenario"]["playbook"], "broad")
        self.assertIn("fingerprint_id", manifest["experiment_fingerprint"])

        matrix = json.loads((run_dir / "matrix.json").read_text(encoding="utf8"))
        self.assertEqual(len(matrix["cells"]), 8)
        self.assertEqual(matrix["primary_scenario"]["playbook"], "broad")

        packet = json.loads((run_dir / "decision_packet.json").read_text(encoding="utf8"))
        self.assertIn(packet["recommended_verdict"], {"hold", "reject", "promote"})

    def test_research_gate_collapses_to_a_single_command(self):
        commands = cycle._mandatory_test_commands()

        self.assertEqual(commands, [["npm", "run", "verify:research"]])

    def test_imported_truth_lane_writes_truth_artifacts_and_watchlist_manifest(self):
        watchlist = self.root / "docs" / "autoresearch" / "truth-first-watchlist.json"
        watchlist.write_text(
            json.dumps({"id": "truth-first", "symbols": ["SPY", "QQQ", "AAPL"]}, indent=2),
            encoding="utf8",
        )

        def fake_backtest(**kwargs):
            truth_lane = kwargs["truth_lane"]
            pricing_lane = kwargs["pricing_lane"]
            result = _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=pricing_lane,
                playbook=kwargs["playbook"] or "broad",
                profit_factor=1.15 if truth_lane == "historical_imported" else 1.05,
                avg_pnl_pct=4.0 if truth_lane == "historical_imported" else 2.5,
                total_trades=18 if truth_lane == "historical_imported" else 22,
            )
            result["truth_source"] = truth_lane
            result["pricing_lane"] = pricing_lane
            result["quote_coverage_pct"] = 82.0 if truth_lane == "historical_imported" else 100.0
            result["priced_trade_count"] = result["total_trades"] - 2 if truth_lane == "historical_imported" else result["total_trades"]
            result["unpriced_trade_count"] = 2 if truth_lane == "historical_imported" else 0
            result["trades"] = [
                {"ticker": "SPY", "sector": "Index", "market_regime": "bullish", "pnl_pct": 5.0, "entry_date": "2025-01-10"},
                {"ticker": "QQQ", "sector": "Index", "market_regime": "neutral", "pnl_pct": -2.0, "entry_date": "2025-04-10"},
                {"ticker": "AAPL", "sector": "Technology", "market_regime": "bullish", "pnl_pct": 4.0, "entry_date": "2025-07-10"},
                {"ticker": "SPY", "sector": "Index", "market_regime": "bearish", "pnl_pct": 1.0, "entry_date": "2025-10-10"},
            ]
            return result

        truth_comparison = {
            "synthetic": {"truth_source": "synthetic_research", "total_trades": 22},
            "imported": {"truth_source": "historical_imported", "total_trades": 18},
            "unsupported_by_import_count": 3,
            "deltas": {"profit_factor": 0.10},
        }

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.15}}), \
             patch.object(cycle, "build_truth_lane_comparison", return_value=truth_comparison):
            code = cycle.main(
                [
                    "--slug",
                    "imported-truth",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--truth-lane",
                    "historical_imported",
                    "--watchlist-set",
                    str(watchlist.relative_to(self.root)),
                    "--window-mode",
                    "rolling_6m",
                    "--require-quote-coverage",
                    "75",
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        run_dir = self._run_dirs()[0]
        expected_files = {
            "watchlist_set.json",
            "rolling_windows.json",
            "paired_synthetic_primary_report.json",
            "truth_lane_comparison.json",
            "quote_coverage_sensitivity.json",
            "discovery.json",
            "falsification.json",
            "evidence_bundle.json",
            "decision_packet.json",
        }
        self.assertTrue(expected_files.issubset({path.name for path in run_dir.iterdir()}))

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["truth_lane"], "historical_imported")
        self.assertEqual(manifest["mode"], "search")
        self.assertEqual(manifest["window_mode"], "rolling_6m")
        self.assertEqual(manifest["require_quote_coverage"], 75.0)
        self.assertEqual(manifest["watchlist_manifest"]["symbols"], ["SPY", "QQQ", "AAPL"])

        matrix = json.loads((run_dir / "matrix.json").read_text(encoding="utf8"))
        self.assertEqual(matrix["defaults"]["requested_pricing_lanes"], ["mid", "pessimistic"])
        self.assertEqual(matrix["defaults"]["effective_pricing_lanes"], ["historical_imported"])
        self.assertEqual(matrix["defaults"]["truth_lane"], "historical_imported")

        truth_lane_comparison = json.loads((run_dir / "truth_lane_comparison.json").read_text(encoding="utf8"))
        self.assertEqual(truth_lane_comparison["unsupported_by_import_rate_pct"], 13.6)

        falsification = json.loads((run_dir / "falsification.json").read_text(encoding="utf8"))
        self.assertEqual(
            falsification["acceptance_rule"]["quote_coverage_sensitivity"]["stricter_floor_pct"],
            85.0,
        )

        evidence_bundle = json.loads((run_dir / "evidence_bundle.json").read_text(encoding="utf8"))
        self.assertIn("authoritative_truth_source", evidence_bundle)

    def test_compare_to_writes_comparison_json_with_deltas(self):
        compare_dir = self.root / "research_runs" / "20260330_140000_baseline"
        compare_dir.mkdir(parents=True, exist_ok=True)

        baseline_cells = []
        for years in (1, 2):
            for lane in ("mid", "pessimistic"):
                baseline_cells.append(
                    {
                        "lookback_years": years,
                        "n_picks": 1,
                        "iv_adj": 1.2,
                        "pricing_lane": lane,
                        "playbook": "broad",
                        "matrix_key": cycle._scenario_key(
                            {
                                "lookback_years": years,
                                "n_picks": 1,
                                "iv_adj": 1.2,
                                "pricing_lane": lane,
                                "playbook": "broad",
                            }
                        ),
                        "error": None,
                        "summary": {
                            "total_trades": 20,
                            "profit_factor": 1.0,
                            "avg_pnl_pct": 2.0,
                            "directional_accuracy_pct": 50.0,
                            "max_drawdown_pct": 15.0,
                        },
                    }
                )

        (compare_dir / "matrix.json").write_text(
            json.dumps(
                {
                    "primary_scenario": {
                        "lookback_years": 2,
                        "n_picks": 1,
                        "iv_adj": 1.2,
                        "pricing_lane": "pessimistic",
                        "playbook": "broad",
                    },
                    "cells": baseline_cells,
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (compare_dir / "stability.json").write_text(json.dumps({"overall_status": "watch"}, indent=2), encoding="utf8")
        (compare_dir / "policy.json").write_text(
            json.dumps({"scan_policy": {"promotion_status": "watch"}}, indent=2),
            encoding="utf8",
        )

        def fake_backtest(**kwargs):
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
                profit_factor=1.2,
                avg_pnl_pct=4.5,
                directional_accuracy_pct=57.0,
                max_drawdown_pct=11.0,
                total_trades=28,
            )

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "promote"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "promote"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.2}}):
            code = cycle.main(
                [
                    "--slug",
                    "candidate",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--compare-to",
                    str(compare_dir.relative_to(self.root)),
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        run_dir = [path for path in self._run_dirs() if path != compare_dir][0]
        comparison = json.loads((run_dir / "comparison.json").read_text(encoding="utf8"))
        self.assertEqual(len(comparison["cells"]), 4)
        first_cell = comparison["cells"][0]
        self.assertIn("profit_factor", first_cell["deltas"])
        self.assertEqual(comparison["primary_status"]["stability_overall_status"]["baseline"], "watch")
        self.assertEqual(comparison["primary_status"]["stability_overall_status"]["current"], "promote")

    def test_runner_exits_nonzero_when_proposal_is_missing(self):
        missing = self.root / "docs" / "autoresearch" / "missing.md"

        code = cycle.main(
            [
                "--slug",
                "missing-proposal",
                "--proposal",
                str(missing.relative_to(self.root)),
            ],
            root_dir=self.root,
        )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("Proposal file does not exist" in item for item in manifest["errors"]))

    def test_runner_exits_nonzero_when_regression_suite_fails_and_preserves_partial_artifacts(self):
        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report(passed=False)):
            code = cycle.main(
                [
                    "--slug",
                    "failing-tests",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        self.assertTrue((run_dir / "proposal.md").exists())
        self.assertTrue((run_dir / "tests.txt").exists())
        self.assertFalse((run_dir / "matrix.json").exists())

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("Mandatory regression suite failed" in item for item in manifest["errors"]))

    def test_compare_to_missing_or_incompatible_run_fails_clearly(self):
        def fake_backtest(**kwargs):
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
            )

        missing_compare = self.root / "research_runs" / "does-not-exist"
        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.1}}):
            code = cycle.main(
                [
                    "--slug",
                    "compare-failure",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--compare-to",
                    str(missing_compare.relative_to(self.root)),
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        self.assertTrue((run_dir / "matrix.json").exists())
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("Compare run does not exist" in item for item in manifest["errors"]))

    def test_compare_to_fails_when_window_mode_or_total_days_differ(self):
        compare_dir = self.root / "research_runs" / "20260330_140000_incompatible"
        compare_dir.mkdir(parents=True, exist_ok=True)
        compare_cells = []
        for years in (1, 2):
            for lane in ("mid", "pessimistic"):
                compare_cells.append(
                    {
                        "lookback_years": years,
                        "n_picks": 1,
                        "iv_adj": 1.2,
                        "pricing_lane": lane,
                        "playbook": "broad",
                        "matrix_key": cycle._scenario_key(
                            {
                                "lookback_years": years,
                                "n_picks": 1,
                                "iv_adj": 1.2,
                                "pricing_lane": lane,
                                "playbook": "broad",
                            }
                        ),
                        "error": None,
                        "summary": {
                            "total_days": 119,
                            "total_trades": 20,
                            "profit_factor": 1.0,
                            "avg_pnl_pct": 2.0,
                            "directional_accuracy_pct": 50.0,
                            "max_drawdown_pct": 15.0,
                        },
                    }
                )
        (compare_dir / "matrix.json").write_text(
            json.dumps(
                {
                    "primary_scenario": {
                        "lookback_years": 2,
                        "n_picks": 1,
                        "iv_adj": 1.2,
                        "pricing_lane": "pessimistic",
                        "playbook": "broad",
                        "truth_lane": "synthetic_research",
                    },
                    "cells": compare_cells,
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (compare_dir / "stability.json").write_text(json.dumps({"overall_status": "watch"}, indent=2), encoding="utf8")
        (compare_dir / "policy.json").write_text(
            json.dumps({"scan_policy": {"promotion_status": "watch"}}, indent=2),
            encoding="utf8",
        )
        (compare_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "truth_lane": "synthetic_research",
                    "window_mode": "full",
                    "watchlist_manifest": None,
                },
                indent=2,
            ),
            encoding="utf8",
        )

        def fake_backtest(**kwargs):
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
                total_trades=24,
            )

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.1}}):
            code = cycle.main(
                [
                    "--slug",
                    "compare-window-drift",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--window-mode",
                    "rolling_6m",
                    "--compare-to",
                    str(compare_dir.relative_to(self.root)),
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 1)
        run_dir = [path for path in self._run_dirs() if path != compare_dir][0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("Compare run is incompatible" in item for item in manifest["errors"]))

    def test_validation_mode_rejects_unknown_cohort_when_phase_is_frozen(self):
        phase_manifest = self._write_phase_manifest()

        code = cycle.main(
            [
                "--slug",
                "frozen-validation",
                "--proposal",
                str(self.proposal.relative_to(self.root)),
                "--mode",
                "validation",
                "--phase-manifest",
                str(phase_manifest.relative_to(self.root)),
                "--cohort-id",
                "not-a-cohort",
            ],
            root_dir=self.root,
        )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("not defined" in item for item in manifest["errors"]))

    def test_validation_mode_emits_support_audit_and_uses_phase_watchlist_scope(self):
        phase_manifest = self._write_phase_manifest()

        def fake_backtest(**kwargs):
            truth_lane = kwargs["truth_lane"]
            if truth_lane == "historical_imported_daily":
                trades = [
                    {"pnl_pct": 12.0, "directional_correct": True, "entry_contract_resolution": "exact_target_contract"},
                    {"pnl_pct": 8.0, "directional_correct": True, "entry_contract_resolution": "exact_target_contract"},
                    {"pnl_pct": -4.0, "directional_correct": False, "entry_contract_resolution": "exact_target_contract"},
                    {"pnl_pct": 5.0, "directional_correct": True, "entry_contract_resolution": "exact_target_contract"},
                    {"pnl_pct": -3.0, "directional_correct": False, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": 6.0, "directional_correct": True, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": -2.0, "directional_correct": False, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": 4.0, "directional_correct": True, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": 3.0, "directional_correct": True, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": -1.0, "directional_correct": False, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": 2.0, "directional_correct": True, "entry_contract_resolution": "nearest_listed_contract"},
                    {"pnl_pct": 1.0, "directional_correct": True, "entry_contract_resolution": "nearest_listed_contract"},
                ]
                result = _fake_backtest_result(
                    lookback_years=kwargs["lookback_years"],
                    pricing_lane=kwargs["pricing_lane"],
                    playbook=kwargs["playbook"] or "broad",
                    profit_factor=1.25,
                    avg_pnl_pct=2.6,
                    directional_accuracy_pct=66.7,
                    total_trades=12,
                    candidate_trade_count=16,
                    priced_trade_count=12,
                    unpriced_trade_count=4,
                    trades=trades,
                    selection_source_counts={"bootstrap_heuristic": 6, "replay_calibrated": 6},
                )
                result["truth_source"] = "historical_imported_daily"
                result["quote_coverage_pct"] = 75.0
                result["contract_resolution_counts"] = {
                    "exact_target_contract": 4,
                    "nearest_listed_contract": 8,
                    "unresolved_candidates": 4,
                }
                result["exact_contract_match_count"] = 4
                result["nearest_contract_match_count"] = 8
                result["unresolved_contract_count"] = 4
                return result
            if truth_lane == "historical_imported":
                return {"error": "No imported intraday data"}
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
                profit_factor=0.9,
                avg_pnl_pct=-1.0,
                directional_accuracy_pct=49.0,
                total_trades=18,
                candidate_trade_count=18,
                priced_trade_count=18,
                selection_source_counts={"bootstrap_heuristic": 9, "replay_calibrated": 9},
            )

        def fake_truth_comparison(*, truth_lane=None, **kwargs):
            if truth_lane == "historical_imported_daily":
                return {
                    "synthetic": {"truth_source": "synthetic_research", "total_trades": 18},
                    "imported": {"truth_source": "historical_imported_daily", "total_trades": 12},
                    "matching_priced_trade_count": 6,
                    "unsupported_by_import_count": 2,
                    "unsupported_by_import_rate_pct": 11.1,
                    "matched_support": {
                        "trade_count": 6,
                        "synthetic": {"trade_count": 6, "profit_factor": 0.95, "avg_pnl_pct": 1.1, "directional_accuracy_pct": 50.0},
                        "imported": {"trade_count": 6, "profit_factor": 1.12, "avg_pnl_pct": 2.8, "directional_accuracy_pct": 66.7},
                    },
                }
            return {
                "synthetic": {"truth_source": "synthetic_research", "total_trades": 18},
                "imported": {"truth_source": "historical_imported", "total_trades": 0},
                "matching_priced_trade_count": 0,
                "unsupported_by_import_count": 0,
                "unsupported_by_import_rate_pct": 0.0,
                "matched_support": {
                    "trade_count": 0,
                    "synthetic": {"trade_count": 0, "profit_factor": 0.0, "avg_pnl_pct": 0.0, "directional_accuracy_pct": 0.0},
                    "imported": {"trade_count": 0, "profit_factor": 0.0, "avg_pnl_pct": 0.0, "directional_accuracy_pct": 0.0},
                },
            }

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.25}}), \
             patch.object(cycle, "build_truth_lane_comparison", side_effect=fake_truth_comparison):
            code = cycle.main(
                [
                    "--slug",
                    "validate-baseline",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--mode",
                    "validation",
                    "--phase-manifest",
                    str(phase_manifest.relative_to(self.root)),
                    "--cohort-id",
                    "baseline",
                    "--truth-lane",
                    "synthetic_research",
                    "--window-mode",
                    "rolling_6m",
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["watchlist_manifest"]["symbols"], ["SPY", "QQQ"])
        self.assertTrue(manifest["baseline_compatibility"]["compatible"] in (None, True))

        evidence_bundle = json.loads((run_dir / "evidence_bundle.json").read_text(encoding="utf8"))
        support_audit = evidence_bundle["support_audit"]
        self.assertEqual(
            support_audit["lanes"]["historical_imported_daily"]["candidate_trade_count"],
            16,
        )
        self.assertEqual(
            support_audit["lanes"]["historical_imported_daily"]["matched_support_trade_count"],
            6,
        )
        self.assertEqual(
            support_audit["daily_exactness_sensitivity"]["daily_exact_only"]["trade_count"],
            4,
        )
        self.assertEqual(evidence_bundle["validation_outcome"], "validated")
        self.assertFalse(
            evidence_bundle["lane_caveats"]["historical_imported_daily"]["fill_equivalent_to_synthetic"]
        )
        self.assertIn(
            "not fill-equivalent to synthetic replay",
            evidence_bundle["lane_caveats"]["historical_imported_daily"]["summary"],
        )

        decision_packet = json.loads((run_dir / "decision_packet.json").read_text(encoding="utf8"))
        self.assertEqual(decision_packet["validation_outcome"], "validated")
        self.assertIn("support_audit", decision_packet)
        self.assertFalse(decision_packet["authoritative_lane_caveat"]["fill_equivalent_to_synthetic"])
        self.assertIn(
            "not fill-equivalent to synthetic replay",
            decision_packet["authoritative_lane_caveat"]["summary"],
        )

        decision_md = (run_dir / "decision.md").read_text(encoding="utf8")
        self.assertIn("## Lane Caveat", decision_md)
        self.assertIn("not fill-equivalent to synthetic replay", decision_md)

    def test_search_mode_requires_explicit_override_when_phase_is_frozen(self):
        phase_manifest = self._write_phase_manifest()

        code = cycle.main(
            [
                "--slug",
                "search-while-frozen",
                "--proposal",
                str(self.proposal.relative_to(self.root)),
                "--mode",
                "search",
                "--phase-manifest",
                str(phase_manifest.relative_to(self.root)),
            ],
            root_dir=self.root,
        )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("frozen" in item.lower() for item in manifest["errors"]))

    def test_search_mode_allows_explicit_phase_override(self):
        phase_manifest = self._write_phase_manifest()

        def fake_backtest(**kwargs):
            return _fake_backtest_result(
                lookback_years=kwargs["lookback_years"],
                pricing_lane=kwargs["pricing_lane"],
                playbook=kwargs["playbook"] or "broad",
            )

        with patch.object(cycle, "run_mandatory_regressions", return_value=_fake_test_report()), \
             patch.object(cycle, "run_historical_backtest", side_effect=fake_backtest), \
             patch.object(cycle, "build_options_experiment_matrix", return_value={"generated_at": "now", "experiments": []}), \
             patch.object(cycle, "build_options_stability_report", return_value={"overall_status": "watch"}), \
             patch.object(cycle, "build_live_options_trade_policy", return_value={"scan_policy": {"promotion_status": "watch"}}), \
             patch.object(cycle, "build_metric_truth_report", return_value={"overall": {"profit_factor": 1.1}}):
            code = cycle.main(
                [
                    "--slug",
                    "search-override",
                    "--proposal",
                    str(self.proposal.relative_to(self.root)),
                    "--mode",
                    "search",
                    "--phase-manifest",
                    str(phase_manifest.relative_to(self.root)),
                    "--allow-phase-override",
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "completed")

    def test_search_mode_requires_batch_control_for_challenger(self):
        batch_manifest = self.root / "docs" / "autoresearch" / "batch.json"
        batch_manifest.parent.mkdir(parents=True, exist_ok=True)
        batch_manifest.write_text(
            json.dumps(
                {
                    "batch_id": "batch-1",
                    "control_slug": "control-run",
                    "challenger_slugs": ["candidate-run"],
                    "playbooks": ["broad"],
                    "truth_lanes": ["synthetic_research"],
                    "window_mode": "full",
                    "required_baseline_compatibility": "primary_scenario",
                },
                indent=2,
            ),
            encoding="utf8",
        )

        code = cycle.main(
            [
                "--slug",
                "candidate-run",
                "--proposal",
                str(self.proposal.relative_to(self.root)),
                "--mode",
                "search",
                "--batch-manifest",
                str(batch_manifest.relative_to(self.root)),
            ],
            root_dir=self.root,
        )

        self.assertEqual(code, 1)
        run_dir = self._run_dirs()[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(any("control run" in item.lower() for item in manifest["errors"]))


if __name__ == "__main__":
    unittest.main()
