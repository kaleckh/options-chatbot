from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_flow_extreme_ratio_backspread_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredFlowExtremeRatioBackspreadPlaybookTests(unittest.TestCase):
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
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
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
        self.assertFalse(report["undefined_risk_allowed"])
        self.assertFalse(report["naked_ratio_spreads_allowed"])

    def test_concept_matches_gpt55_selected_design(self) -> None:
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_ratio_spreads_or_backspreads_only")
        self.assertEqual(concept["initial_research_universe"], ["SPY", "QQQ"])
        self.assertEqual(concept["future_extension_universe"], ["IWM", "DIA"])
        self.assertFalse(concept["undefined_risk_allowed"])
        self.assertFalse(concept["naked_ratio_spreads_allowed"])
        self.assertIn("call_backspread_for_upside_flow_extreme", concept["allowed_design_variants"])
        self.assertIn("put_backspread_for_downside_flow_extreme", concept["allowed_design_variants"])
        self.assertIn("capped_ratio_spread_for_snapback_mean_reversion", concept["allowed_design_variants"])

    def test_side_aware_formulas_and_denominator_statuses_are_registered(self) -> None:
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        formulas = report["concept"]["side_aware_pricing_formulas"]
        self.assertIn("long_leg_ask", formulas["entry_net_premium"])
        self.assertIn("short_leg_bid", formulas["entry_net_premium"])
        self.assertIn("short_leg_ask", formulas["exit_net_value"])
        self.assertIn("long_leg_bid", formulas["exit_net_value"])
        self.assertIn("intrinsic", formulas["expiry_settlement_value"])
        self.assertIn("fees_and_slippage", formulas["net_pnl_usd"])
        self.assertIn("max_loss_usd", formulas["collateral_convention"])
        for status in playbook.DENOMINATOR_STATUSES:
            self.assertIn(status, report["concept"]["denominator_statuses"])
        self.assertIn("rejected_undefined_risk", report["concept"]["denominator_statuses"])

    def test_future_requirements_include_flow_proxy_and_defined_risk_guards(self) -> None:
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        requirements = " ".join(report["concept"]["required_future_replay_engine_support"])
        leakage = " ".join(report["concept"]["leakage_controls"])
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        exclusions = " ".join(report["concept"]["explicit_exclusions"])
        self.assertIn("point-in-time overextension or flow proxy inputs", requirements)
        self.assertIn("multi-leg side-aware ratio-spread and backspread bid/ask entry pricing", requirements)
        self.assertIn("defined-risk cap or extra-wing max-loss convention", requirements)
        self.assertIn("full denominator mapping including rejected undefined-risk rows", requirements)
        self.assertIn("future flow", leakage)
        self.assertIn("30 latest-audit exact rows", falsification)
        self.assertIn("quote coverage is below 90 percent", falsification)
        self.assertIn("undefined-risk exposure", falsification)
        self.assertIn("protected-holdout overlap", falsification)
        self.assertIn("uncapped or undefined-risk naked ratio spreads", exclusions)

    def test_missing_oracle_packet_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=tmp / "missing.json",
                generated_at_utc="2026-06-23T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_oracle_packet")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="flow-extreme-ratio") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Flow-Extreme Ratio/Backspread Playbook", markdown)
            self.assertIn("Side-Aware Pricing And Risk", markdown)


if __name__ == "__main__":
    unittest.main()
