from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_lane_month_post_expiry_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _monthly_lane_pnl() -> dict:
    return {
        "report_id": "regular_options_monthly_lane_exact_pnl",
        "status": "lane_month_exact_pnl_partial",
        "generated_at_utc": "2026-06-08T14:50:14Z",
        "read_only": True,
        "live_policy_change": False,
        "summary": {
            "target_month": "2026-03",
            "target_lane": "bullish_pullback_observation",
            "true_executable_lane_month_pnl_rows": 11,
            "missing_proof_count": 2,
        },
        "lane_month_rows": [
            {
                "ticker": "AA",
                "entry_date": "2026-03-19",
                "exit_date": "2026-04-27",
                "long_contract_symbol": "AA260424C00062000",
                "short_contract_symbol": "AA260424C00067000",
                "true_executable_pnl_available": False,
                "blockers": ["missing_exit_long_quote", "missing_exit_short_quote"],
            },
            {
                "ticker": "COIN",
                "entry_date": "2026-03-24",
                "exit_date": "2026-04-27",
                "long_contract_symbol": "COIN260424C00210000",
                "short_contract_symbol": "COIN260424C00225000",
                "true_executable_pnl_available": False,
                "blockers": ["missing_exit_long_quote", "missing_exit_short_quote"],
            },
            {
                "ticker": "JNJ",
                "entry_date": "2026-03-19",
                "exit_date": "2026-04-06",
                "long_contract_symbol": "JNJ260410C00255000",
                "short_contract_symbol": "JNJ260410C00260000",
                "true_executable_pnl_available": True,
            },
        ],
    }


class RegularOptionsLaneMonthPostExpiryArchiveTests(unittest.TestCase):
    def test_archives_post_expiry_missing_rows_after_readiness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "monthly.json"
            _write_json(source, _monthly_lane_pnl())

            report = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=root / "missing_previous.json",
                feed_readiness_status="healthy",
                feed_readiness_evidence=["dry_run_generated_rows=824_errors=0"],
                generated_at_utc="2026-06-08T15:00:00Z",
            )

        self.assertEqual(report["status"], "lane_month_post_expiry_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "post_expiry_lane_month_branches_archived")
        self.assertEqual(report["summary"]["newly_archived_post_expiry_row_count"], 2)
        self.assertEqual(report["summary"]["newly_archived_contract_leg_count"], 4)
        self.assertEqual(report["summary"]["source_true_executable_lane_month_pnl_rows"], 11)
        item = report["newly_archived_lane_month_rows"][0]
        self.assertEqual(item["archive_status"], "archived_lane_month_post_expiry_non_executable_exit")
        self.assertEqual(item["exit_timestamp_utc"], "2026-04-27T19:55:00Z")
        self.assertEqual(item["long_contract_expiration"], "2026-04-24")
        self.assertFalse(item["production_proof"])
        self.assertFalse(item["true_executable_pnl_row"])

    def test_requires_feed_readiness_or_durable_no_match_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "monthly.json"
            _write_json(source, _monthly_lane_pnl())

            report = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=root / "missing_previous.json",
                generated_at_utc="2026-06-08T15:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn(
            "thetadata_readiness_or_durable_no_match_evidence",
            report["summary"]["missing_required_inputs"],
        )
        self.assertEqual(report["summary"]["newly_archived_post_expiry_row_count"], 0)

    def test_appends_only_new_archives_after_previous_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "monthly.json"
            previous = root / "previous.json"
            _write_json(source, _monthly_lane_pnl())
            first = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=root / "missing_previous.json",
                feed_readiness_status="healthy",
                feed_readiness_evidence=["first_run"],
            )
            first["archived_lane_month_rows"] = first["archived_lane_month_rows"][:1]
            _write_json(previous, first)

            second = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=previous,
                feed_readiness_status="healthy",
                feed_readiness_evidence=["second_run"],
            )

        self.assertEqual(second["summary"]["previous_archived_post_expiry_row_count"], 1)
        self.assertEqual(second["summary"]["newly_archived_post_expiry_row_count"], 1)
        self.assertEqual(second["summary"]["archived_post_expiry_row_count"], 2)
        self.assertEqual(second["newly_archived_lane_month_rows"][0]["ticker"], "COIN")

    def test_markdown_renders_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "monthly.json"
            _write_json(source, _monthly_lane_pnl())
            report = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=root / "missing_previous.json",
                feed_readiness_status="healthy",
                feed_readiness_evidence=["dry_run_generated_rows=824_errors=0"],
            )

            markdown = archive.render_markdown(report)

        self.assertIn("## Archived Branches", markdown)
        self.assertIn("AA260424C00062000", markdown)
        self.assertIn("read-only", markdown)
        self.assertIn("does not create trades", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "monthly.json"
            _write_json(source, _monthly_lane_pnl())
            report = archive.build_report(
                monthly_lane_pnl_path=source,
                previous_archive_path=root / "missing_previous.json",
                feed_readiness_status="healthy",
                feed_readiness_evidence=["dry_run_generated_rows=824_errors=0"],
            )

            artifacts = archive.write_outputs(report, output_dir=root / "out")

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], archive.REPORT_ID)
            self.assertEqual(latest["status"], "lane_month_post_expiry_archive_readback")


if __name__ == "__main__":
    unittest.main()
