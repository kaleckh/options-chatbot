from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_vrp_credit_spread_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredVrpCreditSpreadPlaybookTests(unittest.TestCase):
    def _packet_fixture(self, tmp: Path) -> Path:
        path = tmp / "packet.json"
        _write_json(
            path,
            {
                "report_id": "options_oracle_profit_loop_packet",
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "status": "ready_for_same_session_gpt55_guidance",
                "profitability_target": {
                    "minimum_profitable_strict_completed_rows": 30,
                    "current_forward_rows": 0,
                },
            },
        )
        return path

    def test_report_is_design_only_and_read_only(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=self._packet_fixture(tmp),
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "preregistered_design_only")
        for key, expected in playbook.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["strategy_logic_changed"])
        self.assertFalse(report["lane_implementation_performed"])

    def test_concept_matches_gpt55_selected_design(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_put_credit_spreads_only")
        self.assertEqual(concept["permitted_research_universe"], ["SPY", "QQQ", "IWM", "DIA"])
        self.assertEqual(concept["historical_research_window"]["start_date"], "2024-06-01")
        self.assertEqual(concept["historical_research_window"]["end_date"], "2026-05-31")
        self.assertFalse(concept["historical_research_window"]["protected_holdout_consumed"])
        geometry = concept["candidate_geometry"]
        self.assertEqual(geometry["dte_min"], 21)
        self.assertEqual(geometry["dte_max"], 45)
        self.assertIn("0.20", geometry["short_put_moneyness_or_delta"])
        self.assertIn("5_point_width", geometry["long_put_distance"])
        self.assertEqual(geometry["exit_policy"]["profit_take_pct_of_credit"], 0.50)
        self.assertEqual(geometry["exit_policy"]["time_exit_dte"], 7)

    def test_side_aware_formulas_and_denominator_statuses_are_registered(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        formulas = report["concept"]["side_aware_pricing_formulas"]
        self.assertEqual(formulas["entry_credit"], "short_put_bid - long_put_ask")
        self.assertEqual(formulas["exit_debit"], "short_put_ask - long_put_bid")
        self.assertIn("fees_and_slippage", formulas["net_pnl_usd"])
        for status in playbook.DENOMINATOR_STATUSES:
            self.assertIn(status, report["concept"]["denominator_statuses"])

    def test_future_requirements_include_credit_spread_specific_risks(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        requirements = " ".join(report["concept"]["required_future_replay_engine_support"])
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        exclusions = " ".join(report["concept"]["explicit_exclusions"])
        self.assertIn("credit-spread side-aware bid/ask pricing", requirements)
        self.assertIn("assignment and expiration classification", requirements)
        self.assertIn("margin and max-loss convention", requirements)
        self.assertIn("30 latest-audit exact rows", falsification)
        self.assertIn("quote coverage is below 90 percent", falsification)
        self.assertIn("PF lower bound is less than or equal to 1.0", falsification)
        self.assertIn("source marks", exclusions)

    def test_missing_oracle_packet_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=tmp / "missing.json",
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_oracle_packet")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="vrp-credit-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered VRP Credit Spread Playbook", markdown)
            self.assertIn("Candidate Geometry", markdown)
            self.assertIn("Side-Aware Pricing", markdown)


if __name__ == "__main__":
    unittest.main()
