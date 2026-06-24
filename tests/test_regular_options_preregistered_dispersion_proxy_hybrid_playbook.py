from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_dispersion_proxy_hybrid_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredDispersionProxyHybridPlaybookTests(unittest.TestCase):
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
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
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
        self.assertFalse(report["undefined_or_uncapped_pair_risk_allowed"])

    def test_concept_matches_gpt55_selected_design_and_universe(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_index_constituent_debit_credit_hybrid_pairs_only")
        self.assertEqual(concept["index_legs"], ["SPY", "QQQ"])
        self.assertIn("AAPL", concept["constituent_legs"])
        self.assertIn("CVX", concept["constituent_legs"])
        self.assertFalse(concept["undefined_or_uncapped_pair_risk_allowed"])
        self.assertIn("long_constituent_debit_spread_short_index_credit_spread_dispersion_v1", concept["allowed_design_variants"])
        self.assertIn("long_index_debit_spread_short_constituent_credit_spread_convergence_v1", concept["allowed_design_variants"])

    def test_cvx_source_quality_blocker_is_explicit(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        cvx_rows = [row for row in report["concept"]["symbol_rows"] if row["symbol"] == "CVX"]
        self.assertEqual(len(cvx_rows), 1)
        self.assertEqual(cvx_rows[0]["source_quality_note"], playbook.CVX_NOTE)
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        self.assertIn("CVX rows are counted without source-quality scope", falsification)

    def test_side_aware_formulas_and_denominator_statuses_are_registered(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        formulas = report["concept"]["side_aware_pricing_formulas"]
        self.assertIn("debit_long_leg_ask", formulas["debit_side_entry"])
        self.assertIn("credit_short_leg_bid", formulas["credit_side_entry"])
        self.assertIn("debit_long_leg_bid", formulas["debit_side_exit_value"])
        self.assertIn("credit_short_leg_ask", formulas["credit_side_exit_debit"])
        self.assertIn("pair_entry_cashflow", formulas["pair_net_pnl_usd"])
        self.assertIn("pair_max_loss_usd", formulas["collateral_convention"])
        for status in playbook.DENOMINATOR_STATUSES:
            self.assertIn(status, report["concept"]["denominator_statuses"])
        self.assertIn("rejected_pair_universe_mismatch", report["concept"]["denominator_statuses"])
        self.assertIn("rejected_undefined_or_uncapped_risk", report["concept"]["denominator_statuses"])

    def test_future_requirements_include_pair_level_guards(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))

        requirements = " ".join(report["concept"]["required_future_replay_engine_support"])
        leakage = " ".join(report["concept"]["leakage_controls"])
        falsification = " ".join(report["concept"]["future_falsification_plan"])
        self.assertIn("point-in-time dispersion or concentration proxy inputs", requirements)
        self.assertIn("multi-underlying pair construction", requirements)
        self.assertIn("pair-level max-loss and collateral convention", requirements)
        self.assertIn("full denominator mapping including rejected pair-universe and undefined-risk rows", requirements)
        self.assertIn("future constituent/index relative returns", leakage)
        self.assertIn("30 latest-audit exact pair rows", falsification)
        self.assertIn("quote coverage is below 90 percent", falsification)
        self.assertIn("uncapped or undefined-risk exposure", falsification)
        self.assertIn("protected-holdout overlap", falsification)

    def test_missing_oracle_packet_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                oracle_packet_path=tmp / "missing.json",
                generated_at_utc="2026-06-23T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_oracle_packet")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(oracle_packet_path=self._packet_fixture(tmp))
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Dispersion-Proxy Hybrid Playbook", markdown)
            self.assertIn("Side-Aware Pricing And Risk", markdown)


if __name__ == "__main__":
    unittest.main()
