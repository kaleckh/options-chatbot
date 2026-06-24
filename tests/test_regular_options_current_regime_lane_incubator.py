from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_current_regime_lane_incubator as incubator
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class CurrentRegimeLaneIncubatorTests(unittest.TestCase):
    def _build_fixture(self, tmp: Path) -> dict:
        monthly = tmp / "monthly.json"
        tournament = tmp / "tournament.json"
        robust = tmp / "robust.json"
        goal = tmp / "goal.json"
        _write_json(
            monthly,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "overall_status": "profitability_iteration_ready_blocked_for_promotion",
                "lane_dispositions": {
                    "status_counts": {
                        "paper_shadow": 1,
                        "profitable_candidate": 0,
                        "quarantine": 4,
                        "retest": 3,
                    }
                },
            },
        )
        rankings = [
            {"candidate_id": "lane:volatility_expansion_observation", "lane_id": "volatility_expansion_observation"},
            {"candidate_id": "smh_semiconductor_call_chain_native_timeexit_all_sleeves", "lane_id": "smh_semiconductor"},
            {"candidate_id": "xle_energy_inflation_call_chain_native_timeexit_all_sleeves", "lane_id": "xle_energy_inflation"},
        ]
        _write_json(
            tournament,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "candidate_count": 65,
                "blocked_candidate_count": 28,
                "rejected_candidate_count": 31,
                "best_candidate_if_any": {"candidate_id": "lane:volatility_expansion_observation"},
                "candidate_rankings": rankings,
            },
        )
        _write_json(
            robust,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "candidate_count": 55,
                "robust_candidate_count": 0,
                "paper_shadow_candidate_count": 1,
                "best_candidate_if_any": {"candidate_id": "lane:volatility_expansion_observation"},
                "candidate_rankings": rankings,
            },
        )
        _write_json(
            goal,
            {
                "generated_at_utc": "2026-06-22T00:00:00Z",
                "status": "underpowered_forward_evidence",
                "acceptance_readiness": {
                    "post_freeze_strict_exact_completed_rows": 0,
                    "required_strict_exact_rows": 30,
                    "strict_usd_pf_lower_bound": None,
                    "promotion_ready": False,
                },
            },
        )
        return incubator.build_report(
            monthly_audit_path=monthly,
            hypothesis_tournament_path=tournament,
            robust_edge_path=robust,
            goal_loop_path=goal,
            generated_at_utc="2026-06-22T01:00:00Z",
        )

    def test_report_is_read_only_and_not_accepted_profitable(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        for key, expected in incubator.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertTrue(report["new_lanes_are_research_concepts_only"])
        self.assertTrue(report["operator_approval_required_before_implementation"])
        self.assertTrue(report["historical_rows_are_not_forward_proof"])

    def test_concepts_have_required_proof_and_approval_fields(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        self.assertGreaterEqual(report["concept_count"], 6)
        for concept in report["concepts"]:
            for field in incubator.REQUIRED_CONCEPT_FIELDS:
                self.assertIn(field, concept)
            self.assertTrue(concept["do_not_trade_or_promote"])
            self.assertTrue(concept["approval_required_before_forward_collection"])

    def test_credit_lane_requires_engine_and_approval_before_implementation(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        concept = next(row for row in report["concepts"] if row["concept_id"] == "regime_low_mid_vix_defined_risk_credit_income")
        self.assertEqual(concept["status"], "blocked_by_missing_replay_engine")
        self.assertTrue(concept["approval_required_before_implementation"])
        self.assertIn("credit-spread bid/ask accounting", concept["required_engine_support"])

    def test_event_lane_blocks_when_event_data_missing(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        concept = next(row for row in report["concepts"] if row["concept_id"] == "regime_event_catalyst_defined_risk")
        self.assertEqual(concept["status"], "blocked_by_event_data_missing")
        self.assertIn("event_data_missing", concept["expected_proof_blockers"])

    def test_existing_volatility_lane_is_not_duplicated_or_promoted(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        concept = next(row for row in report["concepts"] if row["concept_id"] == "regime_volatility_expansion_breakout_hedge")
        self.assertEqual(concept["status"], "duplicate_of_existing_candidate")
        self.assertEqual(concept["duplicate_of"], "volatility_expansion_observation")
        self.assertFalse(report["promotion_ready"])

    def test_sector_or_smh_concepts_carry_data_approval_flags(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            report = self._build_fixture(Path(tmp))

        momentum = next(row for row in report["concepts"] if row["concept_id"] == "regime_momentum_continuation_debit_spread")
        weak_sector = next(row for row in report["concepts"] if row["concept_id"] == "regime_weak_sector_relative_weakness")
        self.assertEqual(momentum["status"], "read_only_research_design_ready")
        self.assertTrue(momentum["approval_required_before_implementation"])
        self.assertEqual(weak_sector["status"], "blocked_by_missing_exact_opra_nbbo_coverage")
        self.assertTrue(weak_sector["approval_required_before_quote_import"])

    def test_write_outputs_writes_docs_and_latest_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="current-regime-incubator") as tmp:
            root = Path(tmp)
            report = self._build_fixture(root)
            artifacts = incubator.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "report.md",
            )

            self.assertTrue(Path(artifacts["latest_json"]).exists())
            self.assertTrue(Path(artifacts["latest_markdown"]).exists())
            self.assertTrue(Path(artifacts["docs_report"]).exists())
            markdown = Path(artifacts["docs_report"]).read_text(encoding="utf8")
            self.assertIn("Regular Options Current-Regime Lane Incubator", markdown)


if __name__ == "__main__":
    unittest.main()
