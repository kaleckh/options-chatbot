from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_minute_exit_quote_import_plan as plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _readiness_payload() -> dict:
    return {
        "status": "minute_exit_replay_readiness_readback",
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "summary": {
            "overall_status": "blocked_ready_seed_missing_minute_engine",
            "entry_seed_ready_count": 2,
            "position_seed_ready_count": 1,
            "true_minute_exit_pnl_count": 0,
            "minute_exit_replay_engine_status": "missing",
            "minute_quote_coverage_status": "missing",
            "open_risk_status": "open_risk_governor_blocked",
        },
        "candidate_queue": [
            {
                "row_index": 0,
                "ticker": "QQQ",
                "lane": "volatility_expansion_observation",
                "scan_date": "2026-06-05",
                "entry_time_utc": "2026-06-05T14:39:44.945897Z",
                "expiry": "2026-06-18",
                "long_contract_symbol": "QQQ260618C00728000",
                "short_contract_symbol": "QQQ260618C00750000",
                "readiness_status": "position_seed_ready_engine_missing",
                "auto_track_position_id": 537,
                "fill_status": "auto_tracked",
                "fill_outcome": "paper_fill_recorded",
            },
            {
                "row_index": 1,
                "ticker": "SPY",
                "lane": "bullish_pullback_observation",
                "scan_date": "2026-05-21",
                "entry_time_utc": "2026-05-21T14:27:47.890289+00:00",
                "expiry": "2026-06-18",
                "long_contract_symbol": "SPY260618C00740000",
                "short_contract_symbol": "SPY260618C00760000",
                "readiness_status": "entry_seed_only_fill_not_recorded",
                "fill_status": "not_filled_auto_track_skipped",
                "fill_outcome": "no_fill",
            },
        ],
    }


class RegularOptionsMinuteExitQuoteImportPlanTests(unittest.TestCase):
    def test_happy_path_groups_exact_entry_seeds_into_import_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            _write_json(readiness_path, _readiness_payload())

            report = plan.build_report(
                readiness_path=readiness_path,
                generated_at_utc="2026-06-07T00:00:00Z",
            )

        self.assertEqual(report["status"], "minute_exit_quote_import_plan_ready_engine_blocked")
        self.assertFalse(report["live_policy_change"])
        self.assertEqual(report["summary"]["exact_contract_manifest_count"], 4)
        self.assertEqual(report["summary"]["position_linked_quote_demand_count"], 2)
        self.assertEqual(report["summary"]["entry_only_quote_demand_count"], 2)
        self.assertEqual(report["summary"]["command_group_count"], 2)
        groups = {group["group_id"]: group for group in report["command_groups"]}
        first = groups["minute_exit_quote_group_001"]
        self.assertEqual(first["quote_date_et"], "2026-06-05")
        self.assertEqual(first["right"], "call")
        self.assertEqual(first["symbols"], ["QQQ"])
        self.assertEqual(first["start_time_et"], "10:39:44")
        self.assertEqual(first["end_time_et"], "16:00:00")
        self.assertEqual(first["min_dte"], 13)
        self.assertEqual(first["max_dte"], 13)
        self.assertEqual(first["position_linked_seed_count"], 2)
        self.assertEqual(first["entry_only_seed_count"], 0)
        self.assertIn("--symbols QQQ", first["dry_run_command"])
        self.assertIn("--start-time 10:39:44 --end-time 16:00:00", first["dry_run_command"])
        self.assertIn("--min-dte 13 --max-dte 13", first["dry_run_command"])
        self.assertIn("--dry-run --json", first["dry_run_command"])
        self.assertNotIn("--dry-run", first["write_command"])
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertEqual(actions, ["run_minute_exit_quote_import_plan_commands"])
        self.assertEqual(report["summary"]["replay_pnl_status"], "not_available_until_quotes_and_engine_exist")

    def test_missing_readiness_blocks_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = plan.build_report(readiness_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("minute_exit_replay_readiness", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["command_groups"], [])

    def test_live_policy_change_invalidates_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            payload = _readiness_payload()
            payload["live_policy_change"] = True
            _write_json(readiness_path, payload)

            report = plan.build_report(readiness_path=readiness_path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])
        self.assertEqual(report["command_groups"], [])

    def test_unparsed_contracts_are_not_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            payload = _readiness_payload()
            payload["candidate_queue"] = [
                {
                    "row_index": 0,
                    "ticker": "QQQ",
                    "scan_date": "2026-06-05",
                    "entry_time_utc": "2026-06-05T14:39:44.945897Z",
                    "long_contract_symbol": "BAD_SYMBOL",
                    "short_contract_symbol": "QQQ260618C00750000",
                    "readiness_status": "position_seed_ready_engine_missing",
                }
            ]
            _write_json(readiness_path, payload)

            report = plan.build_report(readiness_path=readiness_path)

        self.assertEqual(report["status"], "minute_exit_quote_import_plan_ready_engine_blocked")
        self.assertEqual(report["summary"]["exact_contract_manifest_count"], 1)
        self.assertEqual(report["summary"]["unparsed_quote_demand_count"], 1)
        self.assertEqual(report["summary"]["command_group_count"], 1)

    def test_only_unparsed_contracts_block_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            payload = _readiness_payload()
            payload["candidate_queue"] = [
                {
                    "row_index": 0,
                    "ticker": "QQQ",
                    "scan_date": "2026-06-05",
                    "long_contract_symbol": "BAD_LONG",
                    "short_contract_symbol": "BAD_SHORT",
                    "readiness_status": "position_seed_ready_engine_missing",
                }
            ]
            _write_json(readiness_path, payload)

            report = plan.build_report(readiness_path=readiness_path)

        self.assertEqual(report["status"], "blocked_unparsed_minute_exit_quote_demands")
        self.assertEqual(report["summary"]["unparsed_quote_demand_count"], 2)
        self.assertEqual(report["command_groups"], [])

    def test_no_seeds_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            payload = _readiness_payload()
            payload["candidate_queue"] = []
            _write_json(readiness_path, payload)

            report = plan.build_report(readiness_path=readiness_path)

        self.assertEqual(report["status"], "no_minute_exit_quote_seeds_to_plan")
        self.assertEqual(report["summary"]["command_group_count"], 0)
        self.assertEqual(report["next_evidence_queue"], [])

    def test_full_source_minute_replay_suppresses_more_quote_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            payload = _readiness_payload()
            payload["summary"].update(
                {
                    "overall_status": "minute_exit_replay_coverage_ready",
                    "true_minute_exit_pnl_count": 2,
                    "minute_quote_coverage_status": "full",
                    "minute_exit_replay_engine_status": "read_only_side_aware_engine_partial",
                }
            )
            _write_json(readiness_path, payload)

            report = plan.build_report(readiness_path=readiness_path)

        self.assertEqual(report["status"], "no_minute_exit_quote_seeds_to_plan")
        self.assertEqual(report["summary"]["command_group_count"], 0)
        self.assertEqual(report["summary"]["replay_pnl_status"], "available_in_source_readiness")
        self.assertEqual(report["next_evidence_queue"], [])

    def test_markdown_and_write_outputs_render_commands_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            _write_json(readiness_path, _readiness_payload())
            report = plan.build_report(readiness_path=readiness_path)
            markdown = plan.render_markdown(report)
            artifacts = plan.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-minute-exit-quote-import-plan.md",
            )

            self.assertIn("# Regular Options Minute-Exit Quote Import Plan", markdown)
            self.assertIn("## Command Groups", markdown)
            self.assertIn("Write import", markdown)
            self.assertIn("does not create trades", markdown)
            self.assertIn("synthesize minute-exit P&L", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], plan.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
