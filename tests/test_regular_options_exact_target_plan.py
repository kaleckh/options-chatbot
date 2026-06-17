from __future__ import annotations

import unittest
from datetime import date

from scripts import build_regular_options_exact_target_plan as plan


def _manifest() -> dict:
    return {
        "status": "blocked_non_promotable_observe_only",
        "summary": {
            "protected_forward_holdout_start_date": "2026-06-05",
            "high_priority_row_count": 3,
        },
        "target_level_classifications": {
            "bullish_pullback_unpriced_targets": {"missing_quote_count": 1},
            "lane_a_unpriced_targets": {
                "missing_quote_count": 3,
                "no_chain_native_spread_count": 1,
            },
        },
    }


def _run_with_mixed_unpriced() -> dict:
    return {
        "unpriced_trades": [
            {
                "ticker": "WMT",
                "date": "2026-02-25",
                "unpriced_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": "2026-03-25",
                "missing_short_contract_symbol": "WMT260402C00140000",
                "long_contract_symbol": "WMT260402C00128000",
                "short_contract_symbol": "WMT260402C00140000",
                "sleeve_id": "fixture",
            },
            {
                "ticker": "WMT",
                "date": "2026-02-26",
                "unpriced_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": "2026-03-25",
                "missing_short_contract_symbol": "WMT260402C00140000",
                "long_contract_symbol": "WMT260402C00127000",
                "short_contract_symbol": "WMT260402C00140000",
                "sleeve_id": "fixture",
            },
            {
                "ticker": "JNJ",
                "date": "2026-06-06",
                "unpriced_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": "2026-06-08",
                "missing_short_contract_symbol": "JNJ260327C00260000",
                "long_contract_symbol": "JNJ260327C00245000",
                "short_contract_symbol": "JNJ260327C00260000",
                "sleeve_id": "fixture",
            },
            {
                "ticker": "PLD",
                "date": "2025-10-28",
                "unpriced_reason": "no_chain_native_spread",
                "sleeve_id": "fixture",
            },
        ]
    }


class RegularOptionsExactTargetPlanTests(unittest.TestCase):
    def test_missing_quote_group_dedupes_and_flags_holdout_overlap(self) -> None:
        group = plan.build_missing_quote_group(
            group_id="fixture_missing",
            label="Fixture",
            source_path="fixture.json",
            run_report=_run_with_mixed_unpriced(),
            holdout_start=date.fromisoformat("2026-06-05"),
        )

        self.assertEqual(group["row_count"], 3)
        self.assertEqual(group["unique_target_count"], 2)
        self.assertEqual(group["duplicate_extra_row_count"], 1)
        self.assertEqual(group["protected_holdout_overlap_unique_target_count"], 1)
        duplicate = group["duplicate_targets"][0]
        self.assertEqual(duplicate["contract_symbol"], "WMT260402C00140000")
        self.assertEqual(duplicate["source_occurrence_count"], 2)

    def test_build_report_separates_no_chain_bucket_and_fails_closed_on_overlap(self) -> None:
        report = plan.build_report(
            manifest=_manifest(),
            bullish_pullback_run=_run_with_mixed_unpriced(),
            lane_a_run=_run_with_mixed_unpriced(),
            generated_at_utc="2026-06-14T00:00:00Z",
            manifest_path="manifest.json",
            bullish_pullback_run_path="bull.json",
            lane_a_run_path="lane.json",
        )

        self.assertEqual(report["status"], "blocked_protected_holdout_overlap")
        self.assertEqual(report["summary"]["protected_holdout_overlap_importable_targets"], 2)
        self.assertEqual(
            report["selection_gap_buckets"]["lane_a_no_chain_native_spread"]["classification"],
            "non_importable_selection_gap",
        )
        self.assertEqual(report["selection_gap_buckets"]["lane_a_no_chain_native_spread"]["row_count"], 1)
        self.assertFalse(report["proof_gate_status"]["quote_import_approved"])
        permissions = {item["permission"] for item in report["permission_table"]}
        self.assertEqual(
            permissions,
            {
                "read_only_ok",
                "evidence_mutation_requires_approval",
                "policy_change_requires_approval",
                "not_actionable_without_forward_evidence",
            },
        )

    def test_render_markdown_carries_plan_only_boundary(self) -> None:
        report = plan.build_report(
            manifest=_manifest(),
            bullish_pullback_run={"unpriced_trades": []},
            lane_a_run={"unpriced_trades": []},
            generated_at_utc="2026-06-14T00:00:00Z",
        )

        markdown = plan.render_markdown(report)

        self.assertIn("No write/import command is approved by this report.", markdown)
        self.assertIn("read_only_ok", markdown)
        self.assertIn("not_proof", markdown)
        self.assertIn("does not request quotes", markdown.lower())


if __name__ == "__main__":
    unittest.main()
