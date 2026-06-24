from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_13_symbol_frozen_candidate_generation_source_surface as surface


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _source_candidate(
    *,
    universe: list[str] | None = None,
    covered_months: list[str] | None = None,
    zero_months: list[str] | None = None,
    selected_trades: list[dict] | None = None,
) -> dict:
    universe = universe if universe is not None else list(surface.ALLOWED_UNIVERSE)
    covered_months = covered_months if covered_months is not None else ["2026-03"]
    return {
        "report_id": "regular_options_point_in_time_candidate_generation",
        "status": "point_in_time_candidate_generation_ready_for_audit",
        "allowed_universe": universe,
        "calendar_coverage": {
            "covered_months": covered_months,
            "zero_selection_months": zero_months or [],
            "zero_selection_months_explicit": bool(zero_months),
        },
        "selected_trades": selected_trades or [],
        "source_artifact_inventory": [
            {
                "playbook": "frozen_fixture",
                "replay_calendar": {"underlyings": universe},
                "daily_selection_diagnostic_day_count": 1,
            }
        ],
    }


class RegularOptions13SymbolFrozenCandidateGenerationSourceSurfaceTests(unittest.TestCase):
    def test_requires_exact_requested_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            _write_json(source_path, _source_candidate())

            with self.assertRaises(ValueError):
                surface.build_report(
                    source_candidate_generation_path=source_path,
                    window_start="2026-03-01",
                    window_end="2026-03-31",
                    universe=["SPY", "QQQ"],
                    no_write=True,
                )

    def test_requires_no_write_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            _write_json(source_path, _source_candidate())

            with self.assertRaises(ValueError):
                surface.build_report(
                    source_candidate_generation_path=source_path,
                    window_start="2026-03-01",
                    window_end="2026-03-31",
                    no_write=False,
                )

    def test_exact_source_surface_can_prove_selected_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            _write_json(
                source_path,
                _source_candidate(selected_trades=[{"entry_date": "2026-03-10", "ticker": "SPY", "lane_id": "fixture"}]),
            )
            report = surface.build_report(
                source_candidate_generation_path=source_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "ready_13_symbol_frozen_candidate_generation_source_surface")
        self.assertEqual(report["calendar_coverage"]["calendar_months_covered_count"], 1)
        self.assertEqual(report["selected_trade_summary"]["selected_rows_in_window"], 1)
        self.assertEqual(report["selected_trades"][0]["ticker"], "SPY")

    def test_exact_source_surface_can_prove_zero_pick_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            _write_json(source_path, _source_candidate(zero_months=["2026-03"]))
            report = surface.build_report(
                source_candidate_generation_path=source_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "ready_13_symbol_frozen_candidate_generation_source_surface")
        self.assertTrue(report["month_diagnostics"][0]["explicit_no_pick_proof"])
        self.assertEqual(report["calendar_coverage"]["zero_selection_months"], ["2026-03"])

    def test_broad_source_surface_fails_closed_without_posthoc_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            broad_universe = list(surface.ALLOWED_UNIVERSE) + ["NFLX"]
            _write_json(
                source_path,
                _source_candidate(
                    universe=broad_universe,
                    selected_trades=[
                        {"entry_date": "2026-03-10", "ticker": "SPY", "lane_id": "fixture"},
                        {"entry_date": "2026-03-11", "ticker": "NFLX", "lane_id": "fixture"},
                    ],
                ),
            )
            report = surface.build_report(
                source_candidate_generation_path=source_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_13_symbol_frozen_candidate_generation_source_surface")
        self.assertIn("source_artifact_universe_not_13_symbol", report["blockers"])
        self.assertIn("missing_frozen_13_symbol_candidate_generation_engine", report["blockers"])
        self.assertIn("outside_universe_source_rows_present", report["blockers"])
        self.assertEqual(report["selected_trade_summary"]["selected_rows_in_window"], 0)
        self.assertFalse(report["source_surface"]["posthoc_filtering_allowed_as_proof"])

    def test_write_outputs_creates_latest_and_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "source.json"
            _write_json(source_path, _source_candidate(zero_months=["2026-03"]))
            report = surface.build_report(
                source_candidate_generation_path=source_path,
                window_start="2026-03-01",
                window_end="2026-03-31",
                generated_at_utc="2026-06-23T00:00:00Z",
            )
            artifacts = surface.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["latest_json"].replace("\\", "/").endswith("/out/latest.json"))


if __name__ == "__main__":
    unittest.main()
