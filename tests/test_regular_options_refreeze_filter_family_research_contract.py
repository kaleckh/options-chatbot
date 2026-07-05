from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_refreeze_filter_family_research_contract as contract


NOW = "2026-07-05T08:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _paths(root: Path) -> dict[str, Path]:
    return {
        "policy": root / "contracts" / "policy.json",
        "bar": root / "contracts" / "bar.json",
        "registry": root / "contracts" / "registry.json",
        "projection": root / "projection" / "latest.json",
        "stationarity": root / "stationarity" / "latest.json",
        "drop": root / "drop" / "latest.json",
        "parity": root / "parity" / "latest.json",
        "tracker": root / "tracker" / "latest.json",
    }


def _write_fixtures(paths: dict[str, Path]) -> None:
    _write_json(
        paths["policy"],
        {
            "report_id": "regular_options_frozen_filtered_policy",
            "policy_id": "historical_filtered_candidate_policy_v1",
            "filter_id": "train_ranked_top_8",
            "conditions_sha256": "abc123",
            "tracking_start_at_utc": "2026-06-30T05:03:45Z",
            "accepted_profitability": False,
            "scanner_policy_changed": False,
        },
    )
    _write_json(
        paths["bar"],
        {
            "report_id": "regular_options_filtered_forward_evidence_bar",
            "bar_id": "regular_options_filtered_forward_evidence_bar_v1",
            "requirements": {"min_completed_forward_paper_shadow_rows": 30},
            "accepted_profitability": False,
            "proof_bars_changed": False,
        },
    )
    _write_json(
        paths["registry"],
        {
            "report_id": "regular_options_audit_window_consumption_registry",
            "entries": [
                {
                    "window_months": ["2026-02", "2026-03", "2026-04", "2026-05"],
                    "consumed_by": "regular_options_historical_profitability_filter_iteration",
                    "selection_permitted": True,
                },
                {
                    "window_months": ["2022-01", "2022-02"],
                    "consumed_by": "regular_options_out_of_sample_frozen_filter_evaluation",
                    "selection_permitted": False,
                    "new_filter_family_permitted": False,
                    "threshold_change_permitted": False,
                    "disposition": "consumed_for_evaluation",
                },
            ],
        },
    )
    _write_json(
        paths["projection"],
        {
            "report_id": "regular_options_forward_evidence_bar_throughput_projection",
            "generated_at_utc": NOW,
            "status": "bar_unreachable_without_state_change",
            "evidence_bar_requirements": {"required_completed_forward_rows": 30},
        },
    )
    _write_json(
        paths["stationarity"],
        {
            "report_id": "regular_options_materializer_match_rate_stationarity",
            "generated_at_utc": NOW,
            "status": "post_freeze_zero_within_historical_variation",
            "operator_escalation": None,
        },
    )
    _write_json(
        paths["drop"],
        {
            "report_id": "regular_options_phase2_drop_decomposition",
            "generated_at_utc": NOW,
            "status": "phase2_drop_decomposition_ready",
            "aggregate_drop_counts": {"momentum": 1710, "option_liquidity": 384, "history_or_liquidity": 304},
            "scheduled_phase2_throughput": {
                "recorded_drop_denominator": 2398,
                "returned_picks": 0,
                "returned_pick_rate_over_recorded_drops": 0.0,
                "session_count": 77,
            },
            "symbol_reason_decomposition": {
                "top_drop_keys": [
                    {"key": "momentum", "count": 1710, "pct": 0.713094},
                    {"key": "option_liquidity", "count": 384, "pct": 0.160133},
                ]
            },
        },
    )
    _write_json(
        paths["parity"],
        {
            "report_id": "regular_options_scanner_materializer_parity_diff",
            "generated_at_utc": NOW,
            "status": "scanner_materializer_parity_diff_ready",
            "materializer_coverage": {
                "row_count_in_window": 182,
                "filter_matched_selected_rows_in_window": 0,
            },
        },
    )
    _write_json(
        paths["tracker"],
        {
            "report_id": "regular_options_filtered_forward_paper_shadow_tracker",
            "generated_at_utc": NOW,
            "status": "filtered_forward_paper_shadow_tracking_active",
            "forward_tracking": {"matched_candidate_count": 0, "completed_candidate_count": 0},
        },
    )


def _build(paths: dict[str, Path]) -> dict:
    return contract.build_contract(
        policy_contract_path=paths["policy"],
        evidence_bar_contract_path=paths["bar"],
        audit_window_registry_path=paths["registry"],
        projection_path=paths["projection"],
        stationarity_path=paths["stationarity"],
        drop_decomposition_path=paths["drop"],
        parity_path=paths["parity"],
        tracker_path=paths["tracker"],
        generated_at_utc=NOW,
    )


class RefreezeFilterFamilyResearchContractTests(unittest.TestCase):
    def test_contract_is_read_only_and_preserves_current_policy_and_bar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _write_fixtures(paths)
            report = _build(paths)

        self.assertEqual(report["status"], "refreeze_filter_family_research_contract_ready")
        self.assertEqual(report["activation_status"], "not_activated_operator_approval_required")
        self.assertFalse(report["fresh_fable_readback_available"])
        self.assertEqual(report["current_policy_preserved"]["filter_id"], "train_ranked_top_8")
        self.assertEqual(report["current_evidence_bar_preserved"]["bar_id"], "regular_options_filtered_forward_evidence_bar_v1")
        self.assertTrue(report["trigger_context"]["operator_may_consider_research_contract_now"])
        self.assertTrue(report["trigger_context"]["current_forward_denominator_empty"])
        drop_evidence = report["allowed_research_questions"][0]["current_evidence"]
        self.assertEqual(drop_evidence["scheduled_phase2_drop_count_total"], 2398)
        self.assertEqual(drop_evidence["top_drop_keys"][0]["key"], "momentum")
        self.assertEqual(drop_evidence["aggregate_drop_counts"]["option_liquidity"], 384)
        for key, expected in contract.FALSE_FLAGS.items():
            self.assertIs(report[key], expected)

    def test_consumed_windows_and_failure_criteria_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _write_fixtures(paths)
            report = _build(paths)

        consumed = report["blocked_or_consumed_selection_windows"]
        self.assertEqual(len(consumed), 2)
        self.assertIn("2026-02", consumed[0]["window_months"])
        self.assertIn("proposal_reuses_consumed_2026_02_through_2026_05_audit_window_for_selection", report["failure_criteria"])
        self.assertIn("proposal_reuses_consumed_2022_01_through_2024_05_oos_window_for_selection_or_threshold_choice", report["failure_criteria"])
        self.assertIn("selection_windows_exclude_consumed_audit_windows_and_protected_holdout", report["research_execution_prerequisites"])

    def test_missing_required_context_blocks_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _write_fixtures(paths)
            paths["projection"].unlink()
            report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_context")
        self.assertIn("forward_evidence_bar_throughput_projection_not_loaded", report["blockers"])
        self.assertFalse(report["scanner_policy_changed"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertEqual(report["activation_status"], "not_activated_operator_approval_required")

    def test_zero_run_trigger_is_recorded_but_not_activated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _write_fixtures(paths)
            stationarity = json.loads(paths["stationarity"].read_text(encoding="utf8"))
            stationarity["status"] = "post_freeze_zero_regime_break_confirmed"
            _write_json(paths["stationarity"], stationarity)
            report = _build(paths)

        self.assertTrue(report["trigger_context"]["zero_run_trigger_active"])
        self.assertEqual(report["activation_status"], "not_activated_operator_approval_required")
        self.assertIn("explicit_operator_approval_for_this_contract_or_a_successor_contract", report["research_execution_prerequisites"])

    def test_write_outputs_creates_contract_and_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            _write_fixtures(paths)
            report = _build(paths)
            artifacts = contract.write_outputs(
                report,
                output_json=root / "contracts" / "contract.json",
                docs_report=root / "docs" / "contract.md",
            )
            doc = (root / "docs" / "contract.md").read_text(encoding="utf8")
            payload = json.loads((root / "contracts" / "contract.json").read_text(encoding="utf8"))

        self.assertIn("docs_report", artifacts)
        self.assertEqual(payload["contract_id"], contract.CONTRACT_ID)
        self.assertIn("Regular Options Refreeze / Filter-Family Research Contract", doc)
        self.assertIn("does not change scanner policy", doc)


if __name__ == "__main__":
    unittest.main()
