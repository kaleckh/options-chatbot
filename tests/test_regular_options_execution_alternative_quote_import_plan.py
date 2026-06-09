from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_execution_alternative_quote_import_plan as plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _coverage_payload() -> dict:
    return {
        "status": "execution_alternative_replay_coverage_readback",
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "summary": {
            "overall_status": "blocked_partial_quote_coverage_no_true_replay_pnl",
            "quote_demand_manifest_status": "ready_for_import_or_query",
            "missing_quote_demand_count": 4,
            "missing_entry_quote_demand_count": 3,
            "missing_exit_quote_demand_count": 1,
        },
        "quote_demands": [
            {
                "priority": 0,
                "contract_symbol": "QQQ260618C00710000",
                "quote_date_et": "2026-05-21",
                "quote_minute_et": 627,
                "window_minutes": 0,
                "quote_phase": "entry",
                "source_labels": ["thetadata_opra_nbbo_1m"],
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "usage_labels": ["top_spread:entry_long"],
                "missing_reasons": ["missing_entry_long_quote"],
                "source_row_count": 1,
                "source_rows": [{"ticker": "QQQ", "lane": "bullish_pullback_observation"}],
            },
            {
                "priority": 0,
                "contract_symbol": "SPY260618C00740000",
                "quote_date_et": "2026-05-21",
                "quote_minute_et": 627,
                "window_minutes": 0,
                "quote_phase": "entry",
                "source_labels": ["thetadata_opra_nbbo_1m"],
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "usage_labels": ["contract_replacement:entry_long"],
                "missing_reasons": ["missing_entry_long_quote"],
                "source_row_count": 1,
                "source_rows": [{"ticker": "SPY", "lane": "bullish_pullback_observation"}],
            },
            {
                "priority": 1,
                "contract_symbol": "QQQ260618C00745000",
                "quote_date_et": "2026-05-21",
                "quote_minute_et": 955,
                "window_minutes": 0,
                "quote_phase": "exit",
                "source_labels": ["thetadata_opra_nbbo_1m"],
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "usage_labels": ["top_spread:exit_short"],
                "missing_reasons": ["missing_exit_short_quote"],
                "source_row_count": 1,
                "source_rows": [{"ticker": "QQQ", "lane": "bullish_pullback_observation"}],
            },
            {
                "priority": 0,
                "contract_symbol": "COIN260619P00200000",
                "quote_date_et": "2026-05-22",
                "quote_minute_et": 630,
                "window_minutes": 0,
                "quote_phase": "entry",
                "source_labels": ["thetadata_opra_nbbo_1m"],
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "usage_labels": ["contract_replacement:entry_long"],
                "missing_reasons": ["missing_entry_long_quote"],
                "source_row_count": 1,
                "source_rows": [{"ticker": "COIN", "lane": "regular_bearish_put_primary"}],
            },
        ],
    }


class RegularOptionsExecutionAlternativeQuoteImportPlanTests(unittest.TestCase):
    def test_happy_path_groups_quote_demands_into_import_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            _write_json(coverage_path, _coverage_payload())

            report = plan.build_report(
                coverage_path=coverage_path,
                generated_at_utc="2026-06-06T01:00:00Z",
            )

        self.assertEqual(report["status"], "execution_alternative_quote_import_plan_ready")
        self.assertFalse(report["live_policy_change"])
        self.assertEqual(report["summary"]["exact_contract_manifest_count"], 4)
        self.assertEqual(report["summary"]["entry_quote_demand_count"], 3)
        self.assertEqual(report["summary"]["exit_quote_demand_count"], 1)
        self.assertEqual(report["summary"]["command_group_count"], 3)
        groups = {group["group_id"]: group for group in report["command_groups"]}
        first = groups["execution_alternative_quote_group_001"]
        self.assertEqual(first["quote_date_et"], "2026-05-21")
        self.assertEqual(first["quote_phase"], "entry")
        self.assertEqual(first["right"], "call")
        self.assertEqual(first["symbols"], ["QQQ", "SPY"])
        self.assertEqual(first["start_time_et"], "10:27:00")
        self.assertEqual(first["end_time_et"], "10:27:00")
        self.assertEqual(first["min_dte"], 28)
        self.assertEqual(first["max_dte"], 28)
        self.assertIn("--symbols QQQ,SPY", first["dry_run_command"])
        self.assertIn("--date-from 2026-05-21 --date-to 2026-05-21", first["dry_run_command"])
        self.assertIn("--right call", first["dry_run_command"])
        self.assertIn("--dry-run --json", first["dry_run_command"])
        self.assertNotIn("--dry-run", first["write_command"])
        actions = [item["action"] for item in report["next_evidence_queue"]]
        self.assertEqual(actions, ["run_execution_alternative_quote_import_commands"])

    def test_missing_coverage_blocks_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = plan.build_report(coverage_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("execution_alternative_replay_coverage", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["command_groups"], [])

    def test_live_policy_change_invalidates_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            payload = _coverage_payload()
            payload["live_policy_change"] = True
            _write_json(coverage_path, payload)

            report = plan.build_report(coverage_path=coverage_path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])
        self.assertEqual(report["command_groups"], [])

    def test_unparsed_demands_are_not_grouped_into_import_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            payload = _coverage_payload()
            payload["quote_demands"] = [
                {
                    "priority": 0,
                    "contract_symbol": "BAD_SYMBOL",
                    "quote_date_et": "2026-05-21",
                    "quote_minute_et": 627,
                    "quote_phase": "entry",
                    "source_rows": [{"ticker": "QQQ"}],
                }
            ]
            _write_json(coverage_path, payload)

            report = plan.build_report(coverage_path=coverage_path)

        self.assertEqual(report["status"], "blocked_unparsed_quote_demands")
        self.assertEqual(report["summary"]["unparsed_quote_demand_count"], 1)
        self.assertEqual(report["command_groups"], [])

    def test_no_quote_demands_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            payload = _coverage_payload()
            payload["summary"]["quote_demand_manifest_status"] = "no_missing_quote_demands"
            payload["quote_demands"] = []
            _write_json(coverage_path, payload)

            report = plan.build_report(coverage_path=coverage_path)

        self.assertEqual(report["status"], "no_quote_demands_to_plan")
        self.assertEqual(report["summary"]["command_group_count"], 0)
        self.assertEqual(report["next_evidence_queue"], [])

    def test_markdown_and_write_outputs_render_commands_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            _write_json(coverage_path, _coverage_payload())
            report = plan.build_report(coverage_path=coverage_path)
            markdown = plan.render_markdown(report)
            artifacts = plan.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-execution-alternative-quote-import-plan.md",
            )

            self.assertIn("# Regular Options Execution Alternative Quote Import Plan", markdown)
            self.assertIn("## Command Groups", markdown)
            self.assertIn("Write import", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], plan.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
