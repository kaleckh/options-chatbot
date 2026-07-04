from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_13_symbol_frozen_candidate_generation_engine as engine


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _fixtures(root: Path) -> dict[str, Path]:
    paths = {
        "feature_store_path": root / "feature.json",
        "no_write_runner_path": root / "runner.json",
        "source_surface_path": root / "source.json",
        "denominator_v2_path": root / "denom.json",
        "frozen_entrypoint_path": root / "entrypoint.json",
        "base_ledger_path": root / "base.json",
        "forward_cohort_path": root / "cohort.json",
        "forward_holdout_path": root / "holdout.json",
        "source_quality_policy_path": root / "policy.json",
    }
    _write_json(
        paths["feature_store_path"],
        {
            "report_id": "regular_options_feature_store",
            "status": "feature_store_built",
            "shared_quote_dates": ["2026-02-02", "2026-02-03"],
            "summary": {"shared_quote_date_count": 2},
        },
    )
    _write_json(
        paths["no_write_runner_path"],
        {
            "report_id": "regular_options_13_symbol_candidate_generation_no_write",
            "status": "candidate_generation_no_write_runner_ready_with_blockers",
            "support_manifest": {
                "read_only_no_write_runner_available": True,
                "candidate_commands": ["uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --no-write --json"],
            },
            "source_artifact_inventory": [{"runner_entrypoints": []}],
        },
    )
    _write_json(
        paths["source_surface_path"],
        {
            "report_id": "regular_options_13_symbol_frozen_candidate_generation_source_surface",
            "status": "blocked_13_symbol_frozen_candidate_generation_source_surface",
            "calendar_coverage": {"calendar_months_covered_count": 0},
            "selected_trade_summary": {"selected_rows_in_window": 0},
            "blockers": ["missing_frozen_13_symbol_candidate_generation_engine"],
        },
    )
    _write_json(
        paths["denominator_v2_path"],
        {
            "report_id": "regular_options_13_symbol_frozen_candidate_generation_denominator_v2",
            "status": "blocked_13_symbol_frozen_candidate_generation_denominator_v2",
            "calendar": {"daily_status_row_count": 2},
            "candidate_generation_denominator": {
                "blocked_days": 2,
                "latest_four_month_candidate_rows_after_dedupe": 0,
            },
            "smallest_next_blocker_clearing_slice": "missing_frozen_13_symbol_candidate_generation_engine",
        },
    )
    _write_json(
        paths["frozen_entrypoint_path"],
        {
            "report_id": "regular_options_13_symbol_frozen_candidate_generation_entrypoint",
            "status": "blocked_frozen_13_symbol_candidate_generation_entrypoint",
            "daily_candidate_generation": [],
            "selected_candidates": [],
            "blockers": ["missing_daily_candidate_generation_diagnostics"],
        },
    )
    _write_json(
        paths["base_ledger_path"],
        {
            "report_id": "regular_options_base_clean_stack_identity_ledger",
            "status": "base_clean_stack_identity_ledger_ready",
            "ledger_row_count": 157,
        },
    )
    _write_json(
        paths["forward_cohort_path"],
        {
            "contract_id": "forward-cohort-preregistration",
            "status": "active",
            "cohort": {"freeze_date": "2026-06-14", "eval_date": "2026-07-28", "frozen": True},
            "lanes": [
                {"lane_id": "volatility_expansion_observation", "policy_snapshot_sha256": "vol", "symbols": ["SPY", "QQQ", "IWM", "DIA"]},
                {"lane_id": "bullish_pullback_observation", "policy_snapshot_sha256": "bull", "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"]},
            ],
        },
    )
    _write_json(paths["forward_holdout_path"], {"contract_id": "forward-holdout-contract", "status": "active", "protected_holdout_start": "2026-06-05"})
    _write_json(paths["source_quality_policy_path"], {"status": "active", "rules": []})
    return paths


class RegularOptions13SymbolFrozenCandidateGenerationEngineTests(unittest.TestCase):
    def test_requires_exact_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            with self.assertRaises(ValueError):
                engine.build_report(**paths, universe=["SPY"], no_write=True)

    def test_requires_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            with self.assertRaises(ValueError):
                engine.build_report(**paths, no_write=False)

    def test_blocks_when_no_reusable_entrypoint_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            report = engine.build_report(
                **paths,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_13_symbol_candidate_generation_engine")
        self.assertEqual(report["decision"], "blocked_frozen_candidate_generation_entrypoint_incomplete")
        self.assertIn("missing_daily_candidate_generation_diagnostics", report["blockers"])
        self.assertTrue(report["reusable_entrypoint_discovery"]["available"])
        self.assertEqual(report["daily_candidate_generation_row_count"], 0)
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")

    def test_entrypoint_discovery_can_mark_ready_but_not_execute_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            paths["frozen_entrypoint_path"].unlink()
            runner_payload = json.loads(paths["no_write_runner_path"].read_text(encoding="utf8"))
            runner_payload["support_manifest"]["reusable_frozen_candidate_generation_entrypoint"] = "frozen_candidate_generation_no_write"
            _write_json(paths["no_write_runner_path"], runner_payload)
            report = engine.build_report(
                **paths,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertTrue(report["reusable_entrypoint_discovery"]["available"])
        self.assertNotIn("blocked_missing_reusable_candidate_generation_entrypoint", report["blockers"])
        self.assertIn("blocked_daily_candidate_generation_coverage", report["blockers"])

    def test_consumes_ready_frozen_entrypoint_daily_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            rows = []
            for day in ("2026-02-02", "2026-02-03"):
                for lane in json.loads(paths["forward_cohort_path"].read_text(encoding="utf8"))["lanes"]:
                    for symbol in lane["symbols"]:
                        rows.append({"date": day, "lane": lane["lane_id"], "underlying": symbol, "status": "explicit_no_pick"})
            rows[0]["status"] = "selected_candidate"
            rows[0].update(
                {
                    "exact_priced": True,
                    "proof_grade": "trusted_intraday_opra_nbbo",
                    "fill_basis": "imported_spread_mark",
                }
            )
            _write_json(
                paths["frozen_entrypoint_path"],
                {
                    "report_id": "regular_options_13_symbol_frozen_candidate_generation_entrypoint",
                    "status": "frozen_13_symbol_candidate_generation_entrypoint_ready",
                    "daily_candidate_generation": rows,
                    "selected_candidates": [rows[0]],
                    "blockers": [],
                },
            )
            report = engine.build_report(
                **paths,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 1)
        self.assertEqual(report["daily_candidate_generation_row_count"], 28)
        self.assertEqual(report["selected_candidate_row_count"], 1)
        self.assertNotIn("blocked_daily_candidate_generation_coverage", report["blockers"])
        self.assertEqual(report["coverage"]["latest_audit_exact_trades"], 1)
        self.assertEqual(report["coverage"]["latest_four_strict_new_candidates"], 1)

    def test_partial_selected_row_audit_is_separate_from_strict_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixtures(Path(tmp))
            source_payload = json.loads(paths["source_surface_path"].read_text(encoding="utf8"))
            source_payload["selected_trades"] = [
                {
                    "date": "2026-02-02",
                    "entry_date": "2026-02-02",
                    "ticker": "SPY",
                    "partial_audit_candidate": True,
                    "exact_priced": True,
                    "proof_grade": "trusted_intraday_opra_nbbo",
                    "fill_basis": "imported_spread_mark",
                    "pnl_pct": 10.0,
                }
            ]
            source_payload["calendar_coverage"] = {"status": "calendar_coverage_not_proven"}
            _write_json(paths["source_surface_path"], source_payload)
            report = engine.build_report(
                **paths,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["coverage"]["latest_audit_exact_trades"], 0)
        self.assertEqual(report["coverage"]["latest_audit_exact_trades_scope"], "strict_calendar_coverage_only")
        self.assertIn("strict_latest_audit_exact_trades_0_below_30", report["blockers"])
        self.assertEqual(report["partial_selected_row_audit"]["exact_priced_rows"], 1)
        self.assertEqual(report["partial_selected_row_audit"]["exact_priced_months"], ["2026-02"])
        self.assertFalse(report["partial_selected_row_audit"]["strict_calendar_coverage_proven"])
        self.assertFalse(report["partial_selected_row_audit"]["scanner_parity"])
        self.assertFalse(report["partial_selected_row_audit"]["production_scanner_replay"])

    def test_write_outputs_creates_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixtures(root)
            report = engine.build_report(
                **paths,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            artifacts = engine.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "out" / "daily_candidate_generation.jsonl").exists())
            self.assertTrue((root / "out" / "selected_candidates.jsonl").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["daily_candidate_generation_jsonl"].replace("\\", "/").endswith("/out/daily_candidate_generation.jsonl"))

    def test_ready_boundary_says_downstream_audit_may_consume_generated_rows(self) -> None:
        report = {
            "status": "frozen_13_symbol_candidate_generation_engine_ready",
            "decision": "frozen_13_symbol_candidate_generation_engine_ready",
            "requested_window": {"window_start": "2024-06-01", "window_end": "2026-05-31", "as_of_date": "2026-06-04"},
            "daily_candidate_generation_row_count": 1,
            "coverage": {
                "candidate_generation_months_covered_count": 24,
                "requested_month_count": 24,
                "train_months_covered": 20,
                "audit_months_covered": 4,
                "latest_audit_exact_trades": 345,
                "latest_audit_exact_trades_scope": "strict_calendar_coverage_only",
            },
            "partial_selected_row_audit": {"exact_priced_rows": 2851},
            "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
            "scanner_parity": False,
            "production_scanner_replay": False,
            "baseline_reproduction": {"prior_frozen_source_surface_months_covered": 24, "prior_denominator_v2_all_rows_blocked": True},
            "accepted_profitability": False,
            "daily_status_counts": {"selected_candidate": 1},
            "blockers": [],
        }

        markdown = engine.render_markdown(report)

        self.assertIn("downstream historical simulated-forward audit metrics may consume the generated selected rows", markdown)
        self.assertIn("scanner parity remains false", markdown)
        self.assertNotIn("candidate-generation coverage is not proven", markdown)


if __name__ == "__main__":
    unittest.main()
