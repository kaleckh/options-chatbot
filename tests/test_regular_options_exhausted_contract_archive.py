from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_exhausted_contract_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _attempt(contract: str = "GOOGL260102C00355000", date: str = "2025-12-22") -> dict:
    return {
        "available_quote_dates": [],
        "contract_symbol": contract,
        "current_source_exhausted_for_exact_date": True,
        "exact_date_row_count": 0,
        "exact_missing_date_status": "no_rows_found",
        "first_available_after_missing_date": None,
        "lookahead_row_count": 0,
        "missing_quote_date": date,
        "outcome": "exact_date_no_match",
        "proof_repair_status": "current_source_exhausted",
        "repair_attempt_key": f"source.json|GOOGL|{contract}|{date}",
        "summary_generated_at_utc": "2026-06-02T17:05:32Z",
        "summary_path": "data/options-validation/thetadata-nbbo/summary.json",
        "total_row_count": 0,
    }


def _target(contract: str = "GOOGL260102C00355000", date: str = "2025-12-22") -> dict:
    return {
        "burndown_status": "excluded_current_source_exhausted",
        "capture_tier": "tier_b_profitable_watch_repair",
        "contract_symbol": contract,
        "lane_family": "tracked_winner_primary",
        "lane_id": "tracked_winner_chain_native_qqq_time80_intraday",
        "latest_attempts": [_attempt(contract, date), _attempt(contract, date)],
        "metrics": {"profit_factor": 7.4, "quote_coverage": 80.95, "unresolved_rows": 8},
        "missing_leg_role": "short",
        "missing_quote_date": date,
        "repair_actionability_status": "current_source_exhausted",
        "selection_readiness": "watch_repair_only",
        "source_artifact": "data/options-validation/runs/source.json",
        "symbol": "GOOGL",
        "unpriced_reason": "missing_exit_quote_for_leg",
    }


def _repair_burndown() -> dict:
    return {
        "status": "repair_burndown_ready",
        "generated_at_utc": "2026-06-05T01:14:06Z",
        "summary": {
            "exhausted_current_source_target_count": 2,
            "live_policy_change": False,
        },
        "exhausted_current_source_targets": [
            _target(),
            _target("GOOGL260102C00360000", "2025-12-22"),
        ],
        "live_policy_change": False,
    }


class RegularOptionsExhaustedContractArchiveTests(unittest.TestCase):
    def test_archives_one_repeated_exact_no_match_contract_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repair_burndown.json"
            _write_json(path, _repair_burndown())

            report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=Path(tmp) / "missing_previous_archive.json",
                generated_at_utc="2026-06-08T00:00:00Z",
            )

        self.assertEqual(report["status"], "exhausted_contract_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "exhausted_contract_target_archived")
        self.assertEqual(report["summary"]["archived_exhausted_contract_count"], 1)
        self.assertEqual(report["summary"]["previous_archived_exhausted_contract_count"], 0)
        self.assertEqual(report["summary"]["newly_archived_exhausted_contract_count"], 1)
        self.assertEqual(report["summary"]["remaining_eligible_exhausted_contract_count"], 1)
        item = report["archived_contract_targets"][0]
        self.assertEqual(item["archive_status"], "archived_current_source_exhausted_contract_date")
        self.assertEqual(item["contract_symbol"], "GOOGL260102C00355000")
        self.assertEqual(item["missing_quote_date"], "2025-12-22")
        self.assertEqual(item["exact_no_match_attempt_count"], 2)
        self.assertFalse(item["production_proof"])

    def test_appends_one_new_target_after_previous_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "repair_burndown.json"
            previous_path = root / "previous_archive.json"
            _write_json(path, _repair_burndown())
            first_report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=root / "missing_previous_archive.json",
                generated_at_utc="2026-06-08T00:00:00Z",
            )
            _write_json(previous_path, first_report)

            second_report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=previous_path,
                generated_at_utc="2026-06-08T00:10:00Z",
            )

        self.assertEqual(second_report["summary"]["archived_exhausted_contract_count"], 2)
        self.assertEqual(second_report["summary"]["previous_archived_exhausted_contract_count"], 1)
        self.assertEqual(second_report["summary"]["newly_archived_exhausted_contract_count"], 1)
        self.assertEqual(second_report["summary"]["remaining_eligible_exhausted_contract_count"], 0)
        self.assertEqual(second_report["newly_archived_contract_targets"][0]["contract_symbol"], "GOOGL260102C00360000")

    def test_requires_repeated_exact_date_no_match_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _repair_burndown()
            payload["exhausted_current_source_targets"][0]["latest_attempts"] = [_attempt()]
            payload["exhausted_current_source_targets"][1]["latest_attempts"] = []
            path = Path(tmp) / "repair_burndown.json"
            _write_json(path, payload)

            report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=Path(tmp) / "missing_previous_archive.json",
                min_attempt_count=2,
            )

        self.assertEqual(report["summary"]["overall_status"], "no_exhausted_contract_target_ready_to_archive")
        self.assertEqual(report["summary"]["archived_exhausted_contract_count"], 0)

    def test_missing_repair_burndown_blocks_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = archive.build_report(
                repair_burndown_path=Path(tmp) / "missing.json",
                previous_archive_path=Path(tmp) / "missing_previous_archive.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("repair_burndown", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _repair_burndown()
            payload["live_policy_change"] = True
            path = Path(tmp) / "repair_burndown.json"
            _write_json(path, payload)

            report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=Path(tmp) / "missing_previous_archive.json",
            )

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_renders_archive_table_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repair_burndown.json"
            _write_json(path, _repair_burndown())
            report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=Path(tmp) / "missing_previous_archive.json",
            )

            markdown = archive.render_markdown(report)

        self.assertIn("## Archived Contract Targets", markdown)
        self.assertIn("GOOGL260102C00355000", markdown)
        self.assertIn("read-only", markdown)
        self.assertIn("does not create trades", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "repair_burndown.json"
            _write_json(path, _repair_burndown())
            report = archive.build_report(
                repair_burndown_path=path,
                previous_archive_path=root / "missing_previous_archive.json",
            )

            artifacts = archive.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-exhausted-contract-archive.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], archive.REPORT_ID)
            self.assertEqual(latest["status"], "exhausted_contract_archive_readback")


if __name__ == "__main__":
    unittest.main()
