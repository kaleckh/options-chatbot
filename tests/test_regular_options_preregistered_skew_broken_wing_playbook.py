from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_skew_broken_wing_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredSkewBrokenWingPlaybookTests(unittest.TestCase):
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
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
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

    def test_concept_matches_gpt55_selected_design(self) -> None:
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_broken_wing_put_butterflies_only")
        self.assertEqual(concept["initial_research_universe"], ["SPY", "QQQ", "IWM", "DIA"])
        self.assertEqual(concept["future_extension_universe"], ["sector_etfs", "single_names"])
        self.assertEqual(concept["historical_research_window"]["start_date"], "2024-06-01")
        self.assertFalse(concept["historical_research_window"]["protected_holdout_consumed"])

    def test_side_aware_formulas_and_denominator_statuses_are_registered(self) -> None:
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        formulas = report["concept"]["side_aware_pricing_formulas"]
        self.assertIn("ask", formulas["entry_value"])
        self.assertIn("bid", formulas["exit_value"])
        self.assertIn("intrinsic", formulas["expiry_settlement_value"])
        self.assertIn("fees_and_slippage", formulas["net_pnl_usd"])
        for status in playbook.DENOMINATOR_STATUSES:
            self.assertIn(status, report["concept"]["denominator_statuses"])

    def test_future_requirements_include_broken_wing_specific_risks(self) -> None:
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        requirements = " ".join(report["concept"]["required_future_replay_engine_support"])
        leakage = " ".join(report["concept"]["leakage_controls"])
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        self.assertIn("multi-leg broken-wing side-aware bid/ask entry pricing", requirements)
        self.assertIn("expiry settlement", requirements)
        self.assertIn("point-in-time VIX and downside-skew inputs", requirements)
        self.assertIn("future skew", leakage)
        self.assertIn("30 latest-audit exact rows", falsification)
        self.assertIn("quote coverage is below 90 percent", falsification)
        self.assertIn("protected-holdout overlap", falsification)

    def test_missing_oracle_packet_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=tmp / "missing.json",
                generated_at_utc="2026-06-23T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_oracle_packet")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="skew-broken-wing") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Skew Broken Wing Playbook", markdown)
            self.assertIn("Side-Aware Pricing", markdown)


if __name__ == "__main__":
    unittest.main()
