from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_momentum_continuation_playbook as playbook
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredMomentumContinuationPlaybookTests(unittest.TestCase):
    def _causal_fixture(self, tmp: Path) -> Path:
        path = tmp / "causal.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_causal_falsification_slice",
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "status": "existing_surface_falsified_new_causal_branch_still_possible",
                "continue_loop": True,
                "significant_upgrade_available": True,
                "branches_to_stop": [
                    "raw overlapping count aggregation",
                    "tracked-winner count retuning without new causal evidence",
                    "clean index/IWM refill as the primary gap closer",
                    "existing current-regime momentum-compatible artifact aggregation",
                ],
            },
        )
        return path

    def test_report_is_design_only_and_read_only(self) -> None:
        with WorkspaceTempDir(prefix="momentum-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                causal_slice_path=self._causal_fixture(tmp),
                momentum_edge_path=tmp / "missing-momentum.json",
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "preregistered_design_only")
        for key, expected in playbook.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["strategy_logic_changed"])
        self.assertFalse(report["lane_implementation_performed"])

    def test_concept_matches_gpt55_selected_design(self) -> None:
        with WorkspaceTempDir(prefix="momentum-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(causal_slice_path=self._causal_fixture(tmp), momentum_edge_path=tmp / "missing.json")

        concept = report["concept"]
        self.assertEqual(concept["concept_id"], playbook.CONCEPT_ID)
        self.assertEqual(concept["status"], "preregistered_design_only")
        self.assertEqual(concept["structure"], "defined_risk_call_debit_spreads_only")
        for symbol in ("SPY", "QQQ", "IWM", "DIA", "AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"):
            self.assertIn(symbol, concept["permitted_research_universe"])
        self.assertIn("tracked-winner retuning", concept["explicit_exclusions"])

    def test_future_proof_path_requires_exact_side_aware_denominator_and_dedupe(self) -> None:
        with WorkspaceTempDir(prefix="momentum-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(causal_slice_path=self._causal_fixture(tmp), momentum_edge_path=tmp / "missing.json")

        proof_path = " ".join(report["concept"]["future_proof_path_required_before_any_profit_claim"])
        self.assertIn("trusted OPRA/NBBO exact-contract entry", proof_path)
        self.assertIn("side-aware debit-spread pricing", proof_path)
        self.assertIn("full denominator rows", proof_path)
        self.assertIn("strict-new opportunity dedupe", proof_path)
        self.assertIn("fresh forward paper-shadow proof", proof_path)

    def test_missing_causal_slice_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="momentum-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(
                causal_slice_path=tmp / "missing.json",
                momentum_edge_path=tmp / "missing-momentum.json",
                generated_at_utc="2026-06-22T01:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_missing_causal_falsification_slice")
        self.assertIsNone(report["concept"])

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="momentum-playbook") as tmp_dir:
            tmp = Path(tmp_dir)
            report = playbook.build_report(causal_slice_path=self._causal_fixture(tmp), momentum_edge_path=tmp / "missing.json")
            artifacts = playbook.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "report.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Momentum Continuation Playbook", markdown)


if __name__ == "__main__":
    unittest.main()
