from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_post_event_iv_crush_iron_condor_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredPostEventIvCrushIronCondorPlaybookTests(unittest.TestCase):
    def _packet_fixture(self, tmp: Path) -> Path:
        path = tmp / "packet.json"
        _write_json(
            path,
            {
                "report_id": "options_oracle_profit_loop_packet",
                "generated_at_utc": "2026-06-23T00:00:00Z",
                "status": "ready_for_same_session_gpt55_guidance",
                "profitability_target": {
                    "minimum_profitable_strict_completed_rows": 30,
                    "current_forward_rows": 0,
                },
            },
        )
        return path

    def test_report_is_design_only_and_read_only(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=self._packet_fixture(tmp),
                generated_at_utc="2026-06-23T01:00:00Z",
            )

        self.assertEqual(report["status"], "preregistered_design_only")
        for key, expected in playbook.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["lane_implementation_performed"])
        self.assertFalse(report["event_calendar_implemented_in_this_slice"])

    def test_concept_matches_gpt55_selected_design(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_short_iron_condors_or_iron_butterflies_only")
        self.assertEqual(concept["initial_research_universe"], ["SPY", "QQQ"])
        self.assertEqual(concept["future_extension_universe"], ["IWM", "DIA"])
        self.assertFalse(concept["event_calendar_implemented_in_this_slice"])
        self.assertIn("fomc_rate_decision", concept["event_categories"])
        self.assertIn("nonfarm_payrolls", concept["event_categories"])

    def test_side_aware_formulas_and_denominator_statuses_are_registered(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        formulas = report["concept"]["side_aware_pricing_formulas"]
        self.assertIn("short_leg_bid", formulas["entry_credit"])
        self.assertIn("long_leg_ask", formulas["entry_credit"])
        self.assertIn("short_leg_ask", formulas["exit_debit"])
        self.assertIn("intrinsic", formulas["expiry_settlement_value"])
        self.assertIn("fees_and_slippage", formulas["net_pnl_usd"])
        self.assertIn("wing width", formulas["margin_convention"])
        for status in playbook.DENOMINATOR_STATUSES:
            self.assertIn(status, report["concept"]["denominator_statuses"])

    def test_future_requirements_include_short_vol_risks(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        requirements = " ".join(report["concept"]["required_future_replay_engine_support"])
        leakage = " ".join(report["concept"]["leakage_controls"])
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        self.assertIn("point-in-time macro event calendar", requirements)
        self.assertIn("point-in-time IV or event-premium proxy inputs", requirements)
        self.assertIn("four-leg side-aware short-premium bid/ask entry pricing", requirements)
        self.assertIn("max-loss and margin convention", requirements)
        self.assertIn("future IV crush", leakage)
        self.assertIn("30 latest-audit exact rows", falsification)
        self.assertIn("quote coverage is below 90 percent", falsification)
        self.assertIn("assignment, expiration, settlement, margin, or max-loss", falsification)
        self.assertIn("protected-holdout overlap", falsification)

    def test_missing_oracle_packet_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=tmp / "missing.json",
                generated_at_utc="2026-06-23T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_oracle_packet")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Post-Event IV Crush Iron Condor Playbook", markdown)
            self.assertIn("Side-Aware Pricing And Risk", markdown)


if __name__ == "__main__":
    unittest.main()
