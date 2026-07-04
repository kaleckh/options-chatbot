from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_earnings_calendar_source_repair_packet as packet
from workspace_tempdir import WorkspaceTempDir


class RegularOptionsEarningsCalendarSourceRepairPacketTests(unittest.TestCase):
    def test_fixture_parser_accepts_required_symbols_and_known_at_policy(self) -> None:
        rows = packet.parse_earnings_calendar_csv(packet.DEFAULT_FIXTURE)

        self.assertEqual({row["symbol"] for row in rows}, set(packet.earnings_calendar.DEFAULT_EQUITY_SYMBOLS))
        first = rows[0]
        self.assertTrue(packet.row_known_before_candidate(first, candidate_decision_utc=first["known_at_utc"]))
        self.assertEqual(first["source_calendar_coverage_start_date_et"], "2024-06-01")
        self.assertEqual(first["source_calendar_coverage_end_date_et"], "2026-07-15")

    def test_missing_required_fixture_header_fails(self) -> None:
        with WorkspaceTempDir(prefix="earnings-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "bad.csv"
            path.write_text("symbol,earnings_date_et\nAAPL,2026-01-29\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_earnings_calendar_csv(path)

    def test_leakage_columns_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="earnings-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "leak.csv"
            lines = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").splitlines()
            lines[0] += ",actual_eps,surprise,pnl"
            for index in range(1, len(lines)):
                lines[index] += ",1.23,0.10,12"
            path.write_text("\n".join(lines) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_earnings_calendar_csv(path)

    def test_known_at_after_earnings_date_fails(self) -> None:
        with WorkspaceTempDir(prefix="earnings-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "late.csv"
            lines = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").splitlines()
            parts = lines[1].split(",")
            parts[6] = "2026-01-30T00:00:00Z"
            lines[1] = ",".join(parts)
            path.write_text("\n".join(lines) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_earnings_calendar_csv(path)

    def test_build_report_is_read_only_and_generates_future_import_decision(self) -> None:
        with WorkspaceTempDir(prefix="earnings-source-packet") as tmp_dir:
            tmp = Path(tmp_dir)
            earnings_readiness = tmp / "earnings-readiness.json"
            historical_audit = tmp / "historical-audit.json"
            earnings_readiness.write_text(
                json.dumps(
                    {
                        "status": "blocked_point_in_time_earnings_calendar",
                        "blockers": ["missing_point_in_time_earnings_calendar_source"],
                        "missing_equity_symbols": sorted(packet.earnings_calendar.DEFAULT_EQUITY_SYMBOLS),
                    }
                ),
                encoding="utf8",
            )
            historical_audit.write_text(
                json.dumps(
                    {
                        "status": "blocked_historical_simulated_forward_audit",
                        "blockers": [
                            "missing_point_in_time_earnings_calendar_source",
                            "missing_daily_candidate_generation_diagnostics",
                        ],
                    }
                ),
                encoding="utf8",
            )
            with (
                patch.object(packet, "DEFAULT_EARNINGS_CALENDAR", earnings_readiness),
                patch.object(packet, "DEFAULT_HISTORICAL_AUDIT", historical_audit),
            ):
                report = packet.build_report(output_dir=tmp / "out", docs_report=tmp / "doc.md")
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "future_import_manifest_template.json").exists())
            self.assertTrue((tmp / "out" / "parser_fixture_validation.json").exists())
            self.assertTrue((tmp / "doc.md").exists())

        self.assertEqual(
            report["status"],
            "earnings_calendar_source_repair_packet_ready_for_operator_import_decision",
        )
        self.assertEqual(report["source_family"], "point_in_time_equity_earnings_calendar_v1")
        self.assertEqual(report["current_earnings_calendar_status"], "blocked_point_in_time_earnings_calendar")
        self.assertEqual(set(report["current_missing_equity_symbols"]), set(packet.earnings_calendar.DEFAULT_EQUITY_SYMBOLS))
        self.assertFalse(report["future_import_command_executed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertIn("APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT", report["future_import_command"])
        self.assertTrue(report["known_at_policy"]["no_live_lookup_substitution"])
        self.assertTrue(report["fixture_validation"]["known_at_safe"])
        self.assertEqual(report["fixture_validation"]["leakage_reject_count"], 0)
        self.assertTrue(report["fixture_validation"]["all_required_symbols_present"])
        self.assertTrue(report["fixture_validation"]["all_symbols_cover_requested_window_plus_max_dte"])
        self.assertIn("missing_daily_candidate_generation_diagnostics", report["remaining_non_earnings_blockers_after_valid_source"])


if __name__ == "__main__":
    unittest.main()
