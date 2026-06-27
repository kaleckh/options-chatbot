from __future__ import annotations

import unittest
from pathlib import Path

from scripts import build_regular_options_direct_vix_source_repair_packet as vix
from workspace_tempdir import WorkspaceTempDir


class RegularOptionsDirectVixSourceRepairPacketTests(unittest.TestCase):
    def test_fixture_parser_normalizes_dates_and_assigns_next_session_known_at_policy(self) -> None:
        rows = vix.parse_vix_csv(vix.DEFAULT_FIXTURE)

        self.assertEqual(rows[0]["source_date"], "2024-05-24")
        self.assertEqual(rows[0]["tradable_after_et"], "2024-05-28T09:30:00 America/New_York")
        self.assertEqual(rows[1]["source_date"], "2024-05-28")
        self.assertEqual(rows[1]["prior_vix_close"], 12.5)
        self.assertEqual(rows[1]["prior_close_bucket"], "low")
        self.assertTrue(rows[1]["prior_close_low_mid"])
        self.assertEqual(rows[3]["prior_close_bucket"], "mid")
        self.assertFalse(rows[4]["prior_close_low_mid"])
        self.assertEqual(rows[1]["rolling_252_percentile_basis"], "strictly_prior_rows_only")

    def test_missing_required_fixture_field_fails(self) -> None:
        with WorkspaceTempDir(prefix="direct-vix") as tmp_dir:
            path = Path(tmp_dir) / "bad.csv"
            path.write_text("Date,Open,High,Close\n2024-05-24,12,13,12.5\n", encoding="utf8")

            with self.assertRaises(ValueError):
                vix.parse_vix_csv(path)

    def test_same_day_vix_close_cannot_be_used_for_same_day_entry(self) -> None:
        rows = vix.parse_vix_csv(vix.DEFAULT_FIXTURE)

        self.assertFalse(vix.row_is_safe_for_candidate(rows[0], candidate_entry_date="2024-05-24"))
        self.assertTrue(vix.row_is_safe_for_candidate(rows[0], candidate_entry_date="2024-05-28"))

    def test_build_report_is_read_only_and_generates_future_commands(self) -> None:
        with WorkspaceTempDir(prefix="direct-vix") as tmp_dir:
            tmp = Path(tmp_dir)
            report = vix.build_report(output_dir=tmp / "out", docs_report=tmp / "doc.md")
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "future_import_manifest_template.json").exists())
            self.assertTrue((tmp / "out" / "parser_fixture_validation.json").exists())
            self.assertTrue((tmp / "doc.md").exists())
            doc_text = (tmp / "doc.md").read_text(encoding="utf8")

        self.assertIn(
            report["status"],
            {
                "direct_vix_source_repair_packet_ready_for_operator_import_decision",
                "blocked_direct_vix_source_repair_packet",
                "direct_vix_source_repair_packet_superseded_by_materialized_vix",
            },
        )
        self.assertEqual(report["source_family"], "direct_vix_daily_close")
        self.assertEqual(report["current_forward_rows"], 0)
        self.assertEqual(report["target_forward_rows"], 30)
        self.assertIn(report["point_in_time_vix_bucket_status"], {"blocked_point_in_time_vix_source_missing", "point_in_time_vix_bucket_ready"})
        self.assertFalse(report["future_import_command_executed"])
        self.assertFalse(report["downstream_vix_bucket_command_executed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["p_l_replay_performed"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertIn("APPROVE_DIRECT_VIX_SOURCE_IMPORT", report["future_import_command"])
        self.assertIn("options:research:point-in-time-vix-bucket", report["downstream_vix_bucket_materialization_command"])
        if report["status"] == "direct_vix_source_repair_packet_superseded_by_materialized_vix":
            self.assertIn("## Superseded Source Boundary", doc_text)
            self.assertNotIn("## Future Approval Question", doc_text)
        if report["status"] != "direct_vix_source_repair_packet_superseded_by_materialized_vix":
            self.assertGreaterEqual(
                sum(
                    1
                    for item in report["vix_blocked_branch_implications"]
                    if item["would_clear_vix_blocker_if_future_source_passes"]
                ),
                2,
            )

    def test_protected_holdout_overlap_blocks_fixture_validation(self) -> None:
        validation = vix._fixture_validation(vix.DEFAULT_FIXTURE, protected_holdout_start="2024-05-29")

        self.assertGreater(validation["protected_holdout_overlap_rows"], 0)

    def test_branch_implications_prefer_replay_gate_blockers(self) -> None:
        implications = vix._blocked_branch_implications(
            {
                "momentum_continuation": {
                    "status": "blocked_momentum_continuation_bounded_replay",
                    "blockers": [
                        "selector_readiness_not_research_only_candidate",
                        "selector_top_candidate_not_momentum_continuation",
                    ],
                    "replay_gate_blockers": ["missing_point_in_time_spy_momentum_confirmation"],
                }
            }
        )

        self.assertEqual(
            implications[0]["remaining_non_vix_blockers"],
            ["missing_point_in_time_spy_momentum_confirmation"],
        )


if __name__ == "__main__":
    unittest.main()
