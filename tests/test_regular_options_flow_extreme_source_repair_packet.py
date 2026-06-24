from __future__ import annotations

import unittest
from pathlib import Path

from scripts import build_regular_options_flow_extreme_source_repair_packet as packet
from workspace_tempdir import WorkspaceTempDir


class RegularOptionsFlowExtremeSourceRepairPacketTests(unittest.TestCase):
    def test_fixture_parser_accepts_good_rows_and_rejects_missing_and_late_rows(self) -> None:
        rows, rejects = packet.parse_flow_csv(packet.DEFAULT_FIXTURE)

        self.assertEqual({row["underlying"] for row in rows}, {"SPY", "QQQ"})
        self.assertGreaterEqual(len(rows), 4)
        self.assertGreaterEqual(len(rejects), 2)
        self.assertTrue(any("missing_or_invalid_total_option_volume" in reject["reasons"] for reject in rejects))
        self.assertTrue(any("known_at_after_tradable_after" in reject["reasons"] for reject in rejects))
        first = rows[0]
        self.assertFalse(packet.row_is_safe_for_input(first, input_date_et=first["source_date"]))
        self.assertTrue(packet.row_is_safe_for_input(first, input_date_et="2024-06-04"))
        gap = next(row for row in rows if row["source_date"] == "2024-07-03")
        self.assertEqual(gap["tradable_after_et"], "2024-07-05T09:30 America/New_York")
        self.assertFalse(first["flow_extreme"])

    def test_missing_required_fixture_header_fails(self) -> None:
        with WorkspaceTempDir(prefix="flow-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "bad.csv"
            path.write_text("source_date,underlying\n2024-06-03,SPY\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_flow_csv(path)

    def test_outside_underlying_fails_closed_as_reject(self) -> None:
        with WorkspaceTempDir(prefix="flow-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "outside.csv"
            text = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").replace("SPY", "IWM", 1)
            path.write_text(text, encoding="utf8")
            _rows, rejects = packet.parse_flow_csv(path)

        self.assertTrue(any("outside_allowed_underlying" in reject["reasons"] for reject in rejects))

    def test_leakage_columns_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="flow-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "leak.csv"
            lines = packet.DEFAULT_FIXTURE.read_text(encoding="utf8").splitlines()
            lines[0] += ",realized_pnl,selected_winner"
            for index in range(1, len(lines)):
                lines[index] += ",1,true"
            path.write_text("\n".join(lines) + "\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_flow_csv(path)

    def test_build_report_is_read_only_and_generates_future_import_decision(self) -> None:
        with WorkspaceTempDir(prefix="flow-source-packet") as tmp_dir:
            tmp = Path(tmp_dir)
            report = packet.build_report(output_dir=tmp / "out", docs_report=tmp / "doc.md")
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "future_import_manifest_template.json").exists())
            self.assertTrue((tmp / "out" / "parser_fixture_validation.json").exists())
            self.assertTrue((tmp / "doc.md").exists())

        self.assertIn(
            report["status"],
            {"flow_extreme_source_repair_packet_ready_for_operator_import_decision", "blocked_flow_extreme_source_repair_packet"},
        )
        self.assertEqual(report["source_family"], "trusted_option_volume_open_interest_daily_v1")
        self.assertEqual(report["current_forward_rows"], 0)
        self.assertEqual(report["target_forward_rows"], 30)
        self.assertEqual(report["point_in_time_flow_extreme_input_status"], "blocked_point_in_time_flow_extreme_input")
        self.assertEqual(report["flow_extreme_volume_oi_source_rows_status"], "blocked_flow_extreme_volume_oi_source_rows")
        self.assertEqual(report["covered_month_count"], 0)
        self.assertEqual(report["date_coverage_pct"], 0.0)
        self.assertEqual(report["flow_extreme_ratio_backspread_replay_readiness_status"], "blocked_flow_extreme_ratio_backspread_replay_readiness")
        self.assertFalse(report["future_import_command_executed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["p_l_replay_performed"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["threshold_policy"]["realized_pnl_used"])
        self.assertFalse(report["threshold_policy"]["plain_bid_ask_used_as_flow"])
        self.assertIn("APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT", report["future_import_command"])
        self.assertTrue(report["fixture_validation"]["known_at_safe"])
        self.assertEqual(report["fixture_validation"]["leakage_reject_count"], 0)
        self.assertEqual(report["fixture_validation"]["protected_holdout_overlap_rows"], 0)
        self.assertEqual(report["fixture_validation"]["underlyings_covered"], ["SPY", "QQQ"])
        self.assertTrue(
            report["downstream_branch_implications"][0]["would_clear_flow_blocker_if_future_source_passes"]
        )

    def test_protected_holdout_overlap_blocks_fixture_validation(self) -> None:
        validation = packet._fixture_validation(packet.DEFAULT_FIXTURE, protected_holdout_start="2024-07-01")

        self.assertGreater(validation["protected_holdout_overlap_rows"], 0)


if __name__ == "__main__":
    unittest.main()
