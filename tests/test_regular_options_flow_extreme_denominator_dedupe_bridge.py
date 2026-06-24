from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_flow_extreme_denominator_dedupe_bridge as bridge
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsFlowExtremeDenominatorDedupeBridgeTests(unittest.TestCase):
    def _pricing_capability(self, tmp: Path, *, ready: bool = True) -> Path:
        path = tmp / "pricing.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_multi_leg_side_aware_pricing_capability",
                "status": "multi_leg_side_aware_pricing_capability_available" if ready else "blocked_multi_leg_side_aware_pricing_capability",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "options_history_db_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "pricing_capability_blockers": [] if ready else ["missing_leg_quote"],
                "structure_support": {
                    "ratio_backspread_bounded": {
                        "status": "available" if ready else "blocked",
                        "denominator_mapping_status": "ready" if ready else "blocked",
                    }
                },
            },
        )
        return path

    def _candidate(self, **patch: object) -> dict:
        candidate = {
            "case_id": "clean",
            "concept_id": bridge.CONCEPT_ID,
            "structure": bridge.STRUCTURE,
            "underlying": "QQQ",
            "signal_date": "2026-05-29",
            "planned_entry_timestamp": "2026-05-29T14:25:00Z",
            "entry_policy": "flow_extreme_entry_v1",
            "exit_policy": "policy_exit_or_expiry_v1",
            "candidate_source_id": "fixture_source",
            "bounded_risk": True,
            "undefined_risk_allowed": False,
            "protected_holdout_overlap": False,
            "fixture_source_not_proof_eligible": True,
            "denominator_status_mapping": {status: status for status in bridge.DENOMINATOR_STATUSES},
            "legs": [
                {"side": "short", "ratio": 1, "option_right": "call", "expiration": "2026-06-03", "strike": 720},
                {"side": "long", "ratio": 1, "option_right": "call", "expiration": "2026-06-03", "strike": 725},
                {"side": "long", "ratio": 1, "option_right": "call", "expiration": "2026-06-03", "strike": 735},
            ],
        }
        candidate.update(patch)
        return candidate

    def _manifest(self, tmp: Path, candidates: list[dict], *, statuses: list[str] | None = None) -> Path:
        path = tmp / "manifest.json"
        _write_json(path, {"denominator_status_contract": statuses or list(bridge.DENOMINATOR_STATUSES), "candidates": candidates})
        return path

    def _base_ledger(self, tmp: Path, hashes: list[str] | None = None, *, status: str = "ready") -> Path:
        path = tmp / "base-ledger.json"
        _write_json(path, {"report_id": "regular_options_base_stack_identity_ledger", "status": status, "identity_hashes": hashes or ["seed"]})
        return path

    def _base_clean_stack_ledger(
        self,
        tmp: Path,
        hashes: list[str] | None = None,
        *,
        status: str = "base_clean_stack_identity_ledger_ready",
    ) -> Path:
        clean_hashes = hashes or [f"seed-{index:03d}" for index in range(157)]
        path = tmp / "base-clean-stack-ledger.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_base_clean_stack_identity_ledger",
                "status": status,
                "read_only": True,
                "research_only": True,
                "accepted_profitability": False,
                "proof_row_count": 0,
                "historical_replay_performed": False,
                "replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "expected_base_clean_stack_exact_rows": 157,
                "ledger_row_count": len(clean_hashes),
                "unique_identity_count": len(set(clean_hashes)),
                "duplicate_identity_count": len(clean_hashes) - len(set(clean_hashes)),
                "missing_identity_field_row_count": 0,
                "future_or_outcome_field_dependency_count": 0,
                "protected_holdout_overlap_count": 0,
                "identity_hashes": clean_hashes,
                "blockers": [] if status == "base_clean_stack_identity_ledger_ready" else ["base_clean_stack_row_source_missing"],
            },
        )
        return path

    def test_realistic_missing_base_identity_ledger_blocks_only_strict_new(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            frontier = tmp / "frontier.json"
            _write_json(
                frontier,
                {
                    "report_id": "regular_options_countable_throughput_frontier",
                    "base_clean_stack_exact_rows": 157,
                    "candidate_rankings": [{"strict_new_row_ledger_available": False}],
                    "blockers": ["strict_new_row_level_identity_ledger_missing"],
                },
            )
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=frontier,
                manifest_path=self._manifest(tmp, [self._candidate()]),
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_flow_extreme_denominator_dedupe_bridge")
        self.assertEqual(report["full_denominator_mapping_status"], "ready")
        self.assertEqual(report["strict_new_dedupe_status"], "blocked")
        self.assertIn("base_stack_identity_ledger_missing", report["bridge_blockers"])
        self.assertIn("strict_new_row_level_identity_ledger_missing", report["bridge_blockers"])
        self.assertEqual(report["proof_row_count"], 0)
        self.assertFalse(report["accepted_profitability"])

    def test_ready_when_base_ledger_exists_and_fixture_is_new(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [self._candidate()]),
            )

        self.assertEqual(report["status"], "flow_extreme_denominator_dedupe_bridge_ready")
        self.assertEqual(report["full_denominator_mapping_status"], "ready")
        self.assertEqual(report["strict_new_dedupe_status"], "ready")
        self.assertEqual(report["bridge_blockers"], [])
        self.assertEqual(report["candidate_results"][0]["status"], "readiness_candidate_priced_not_replayed")

    def test_duplicate_against_base_stack_blocks_strict_new(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            candidate = self._candidate()
            hashes = [bridge.identity_hash(candidate)] + [f"seed-{index:03d}" for index in range(156)]
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp, hashes),
                manifest_path=self._manifest(tmp, [candidate]),
            )

        self.assertEqual(report["strict_new_dedupe_status"], "blocked")
        self.assertIn("candidate_duplicate_existing_base_stack", report["bridge_blockers"])

    def test_duplicate_within_research_harness_blocks(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [self._candidate(case_id="a"), self._candidate(case_id="b")]),
            )

        self.assertIn("candidate_duplicate_within_research_harness", report["bridge_blockers"])

    def test_missing_identity_field_blocks(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            candidate = self._candidate(candidate_source_id="")
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [candidate]),
            )

        self.assertIn("missing_identity_field", report["bridge_blockers"])
        self.assertIn("candidate_source_id", report["candidate_results"][0]["missing_identity_fields"])

    def test_protected_holdout_and_unbounded_ratio_block(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(
                    tmp,
                    [
                        self._candidate(case_id="holdout", signal_date="2026-06-05"),
                        self._candidate(case_id="unbounded", bounded_risk=False, undefined_risk_allowed=True),
                    ],
                ),
            )

        self.assertIn("candidate_protected_holdout_overlap", report["bridge_blockers"])
        self.assertIn("candidate_rejected_unbounded_or_undefined_risk", report["bridge_blockers"])

    def test_missing_denominator_status_and_fixture_proof_flag_block(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            statuses = [status for status in bridge.DENOMINATOR_STATUSES if status != "blocked_source_missing"]
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [self._candidate(fixture_source_not_proof_eligible=False)], statuses=statuses),
            )

        self.assertIn("missing_denominator_status", report["bridge_blockers"])
        self.assertIn("blocked_source_missing", report["missing_denominator_statuses"])
        self.assertIn("fixture_source_not_proof_eligible_not_true", report["bridge_blockers"])

    def test_leaky_identity_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [self._candidate(identity_fields=["concept_id", "net_pnl_usd"])]),
            )

        self.assertIn("leaky_identity_or_future_field_present", report["bridge_blockers"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="flow-bridge") as tmp_dir:
            tmp = Path(tmp_dir)
            report = bridge.build_report(
                pricing_capability_path=self._pricing_capability(tmp),
                base_identity_ledger_path=self._base_clean_stack_ledger(tmp),
                manifest_path=self._manifest(tmp, [self._candidate()]),
            )
            artifacts = bridge.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "bridge.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "bridge.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Flow-Extreme Denominator/Dedupe Bridge", (tmp / "docs" / "bridge.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
