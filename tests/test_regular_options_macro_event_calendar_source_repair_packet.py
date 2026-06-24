from __future__ import annotations

import unittest
from pathlib import Path

from scripts import build_regular_options_macro_event_calendar_source_repair_packet as packet
from workspace_tempdir import WorkspaceTempDir


class RegularOptionsMacroEventCalendarSourceRepairPacketTests(unittest.TestCase):
    def test_fixture_parser_normalizes_categories_and_tradable_after_policy(self) -> None:
        rows = packet.parse_macro_event_csv(packet.DEFAULT_FIXTURE)

        self.assertEqual({row["event_category"] for row in rows}, set(packet.REQUIRED_CATEGORIES))
        before = next(row for row in rows if row["event_id"] == "cpi-2026-02")
        during = next(row for row in rows if row["event_id"] == "fomc-rate-2026-03")
        after = next(row for row in rows if row["event_id"] == "fed-chair-2026-05")
        self.assertEqual(before["event_window_type"], "before_market")
        self.assertEqual(before["tradable_after_et"], "2026-02-12T09:30 America/New_York")
        self.assertEqual(during["event_window_type"], "during_market")
        self.assertEqual(during["tradable_after_et"], "2026-03-18T14:00 America/New_York")
        self.assertEqual(after["event_window_type"], "after_market")
        self.assertEqual(after["tradable_after_et"], "2026-05-26T09:30 America/New_York")
        self.assertTrue(
            packet.row_known_before_candidate(before, candidate_decision_utc=before["scheduled_event_datetime_utc"])
        )
        self.assertTrue(
            packet.row_tradable_by_candidate(after, candidate_entry_et="2026-05-26T09:30 America/New_York")
        )

    def test_missing_required_fixture_field_fails(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "bad.csv"
            path.write_text("event_id,event_category\nx,cpi\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_macro_event_csv(path)

    def test_duplicate_event_id_fails(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "dup.csv"
            source = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").splitlines()
            path.write_text("\n".join(source + [source[1]]) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_macro_event_csv(path)

    def test_leakage_columns_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "leak.csv"
            text = packet.DEFAULT_FIXTURE.read_text(encoding="utf8")
            lines = text.splitlines()
            lines[0] += ",actual,surprise,market_reaction,pnl"
            lines[1] += ",3.1,0.2,up,12"
            for index in range(2, len(lines)):
                lines[index] += ",,,,"
            path.write_text("\n".join(lines) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_macro_event_csv(path)

    def test_known_at_after_event_fails(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "late.csv"
            lines = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").splitlines()
            parts = lines[1].split(",")
            parts[7] = "2026-02-12T20:00:00Z"
            lines[1] = ",".join(parts)
            path.write_text("\n".join(lines) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_macro_event_csv(path)

    def test_build_report_is_read_only_and_generates_future_import_decision(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-source-packet") as tmp_dir:
            tmp = Path(tmp_dir)
            report = packet.build_report(output_dir=tmp / "out", docs_report=tmp / "doc.md")
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "future_import_manifest_template.json").exists())
            self.assertTrue((tmp / "out" / "parser_fixture_validation.json").exists())
            self.assertTrue((tmp / "doc.md").exists())

        self.assertIn(
            report["status"],
            {
                "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision",
                "blocked_macro_event_calendar_source_repair_packet",
            },
        )
        self.assertEqual(report["source_family"], "scheduled_macro_event_calendar_v1")
        self.assertEqual(report["current_forward_rows"], 0)
        self.assertEqual(report["target_forward_rows"], 30)
        self.assertEqual(report["macro_event_calendar_status"], "blocked_macro_event_calendar_source_missing")
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["covered_categories"], [])
        self.assertEqual(set(report["missing_required_categories"]), set(packet.REQUIRED_CATEGORIES))
        self.assertFalse(report["future_import_command_executed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["p_l_replay_performed"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertIn("APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT", report["future_import_command"])
        self.assertTrue(report["fixture_validation"]["known_at_safe"])
        self.assertEqual(report["fixture_validation"]["leakage_reject_count"], 0)
        self.assertEqual(report["fixture_validation"]["protected_holdout_overlap_rows"], 0)
        self.assertTrue(report["fixture_validation"]["all_required_categories_present"])
        self.assertGreaterEqual(
            sum(
                1
                for item in report["downstream_branch_implications"]
                if item["would_clear_event_calendar_blocker_if_future_source_passes"]
            ),
            2,
        )

    def test_protected_holdout_overlap_blocks_fixture_validation(self) -> None:
        validation = packet._fixture_validation(packet.DEFAULT_FIXTURE, protected_holdout_start="2026-05-01")

        self.assertGreater(validation["protected_holdout_overlap_rows"], 0)


if __name__ == "__main__":
    unittest.main()
