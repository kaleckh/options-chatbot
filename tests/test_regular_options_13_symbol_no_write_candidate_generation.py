from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_regular_options_13_symbol_no_write_candidate_generation as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _candidate_generation(*, covered_months: list[str] | None = None, selected_trades: list[dict] | None = None) -> dict:
    covered_months = covered_months or ["2026-03"]
    return {
        "report_id": "regular_options_point_in_time_candidate_generation",
        "status": "point_in_time_candidate_generation_ready_for_audit",
        "allowed_universe": list(runner.ALLOWED_UNIVERSE),
        "calendar_coverage": {
            "covered_months": covered_months,
            "zero_selection_months": [],
            "zero_selection_months_explicit": False,
        },
        "selected_trades": selected_trades or [{"entry_date": f"{covered_months[0]}-10", "ticker": "SPY"}],
        "source_artifact_inventory": [
            {
                "playbook": "bounded_13_symbol_fixture",
                "replay_calendar": {"underlyings": list(runner.ALLOWED_UNIVERSE)},
                "runner_entrypoints": [],
            }
        ],
    }


class RegularOptions13SymbolNoWriteCandidateGenerationTests(unittest.TestCase):
    def test_requires_exact_frozen_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidate.json"
            _write_json(candidate_path, _candidate_generation())

            with self.assertRaises(ValueError):
                runner.build_report(
                    candidate_generation_path=candidate_path,
                    window_start="2026-03-01",
                    window_end="2026-03-31",
                    universe=["SPY", "QQQ"],
                    no_write=True,
                )

    def test_requires_no_write_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidate.json"
            _write_json(candidate_path, _candidate_generation())

            with self.assertRaises(ValueError):
                runner.build_report(
                    candidate_generation_path=candidate_path,
                    window_start="2026-03-01",
                    window_end="2026-03-31",
                    no_write=False,
                )

    def test_emits_safe_support_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidate.json"
            _write_json(candidate_path, _candidate_generation())
            report = runner.build_report(
                candidate_generation_path=candidate_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        manifest = report["support_manifest"]
        self.assertTrue(manifest["read_only_no_write_runner_available"])
        self.assertTrue(manifest["no_write"])
        self.assertTrue(manifest["as_of_gated"])
        self.assertTrue(manifest["universe_filter"])
        self.assertFalse(manifest["mutating"])
        for key, expected in runner.READ_ONLY_FALSE_FLAGS.items():
            self.assertEqual(report[key], expected)

    def test_broad_source_surface_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidate.json"
            payload = _candidate_generation(selected_trades=[{"entry_date": "2026-03-10", "ticker": "NFLX"}])
            payload["allowed_universe"] = list(runner.ALLOWED_UNIVERSE) + ["NFLX"]
            payload["source_artifact_inventory"][0]["replay_calendar"]["underlyings"] = payload["allowed_universe"]
            _write_json(candidate_path, payload)

            report = runner.build_report(
                candidate_generation_path=candidate_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "candidate_generation_no_write_runner_ready_with_blockers")
        self.assertIn("source_artifact_universe_not_13_symbol", report["blockers"])
        self.assertIn("outside_universe_source_rows_present", report["blockers"])
        self.assertEqual(report["coverage"]["audit_coverable_month_count"], 0)

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_path = root / "candidate.json"
            _write_json(candidate_path, _candidate_generation())
            report = runner.build_report(
                candidate_generation_path=candidate_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )
            artifacts = runner.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["latest_json"].replace("\\", "/").endswith("/out/latest.json"))


if __name__ == "__main__":
    unittest.main()
