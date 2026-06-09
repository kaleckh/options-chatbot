from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_overfit_rule_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _filter_matrix() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "scenarios": [
            {
                "scenario_id": "high_pf_tiny_many_lost_winners",
                "status": "active_safety_gate_paper_probation",
                "entry_time_only": True,
                "kept_count": 10,
                "blocked_count": 196,
                "kept_metrics": {"profit_factor": 84.9, "avg_net_pnl_pct": 34.87, "unpriced": 0},
                "lost_winner_count": 61,
                "avoided_deep_loss_count_lte_minus_50": 37,
                "later_date_read": {"later_date_rows": 2, "survives_later_date_split": True},
            },
            {
                "scenario_id": "non_entry_time_rule",
                "status": "research_candidate",
                "entry_time_only": False,
                "kept_count": 40,
                "blocked_count": 20,
                "kept_metrics": {"profit_factor": 2.0, "avg_net_pnl_pct": 12.0, "unpriced": 0},
                "lost_winner_count": 0,
                "avoided_deep_loss_count_lte_minus_50": 4,
                "later_date_read": {"later_date_rows": 20, "survives_later_date_split": True},
            },
            {
                "scenario_id": "clean_entry_time_holdout_candidate",
                "status": "paper_shadow_candidate",
                "entry_time_only": True,
                "kept_count": 20,
                "blocked_count": 50,
                "kept_metrics": {"profit_factor": 1.8, "avg_net_pnl_pct": 8.5, "unpriced": 0},
                "lost_winner_count": 0,
                "avoided_deep_loss_count_lte_minus_50": 5,
                "later_date_read": {"later_date_rows": 12, "survives_later_date_split": True},
            },
        ],
    }


class RegularOptionsOverfitRuleArchiveTests(unittest.TestCase):
    def test_archives_rejected_rules_without_archiving_clean_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matrix_path = Path(tmp) / "matrix.json"
            _write_json(matrix_path, _filter_matrix())

            report = archive.build_report(
                filter_matrix_path=matrix_path,
                generated_at_utc="2026-06-06T02:00:00Z",
            )

        self.assertEqual(report["status"], "overfit_rule_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "overfit_rules_archived")
        self.assertEqual(report["summary"]["reject_overfit_rule_count"], 2)
        self.assertEqual(report["summary"]["archived_reject_overfit_rule_count"], 2)
        self.assertTrue(report["summary"]["archive_complete"])
        archived_ids = {item["scenario_id"] for item in report["archived_rules"]}
        self.assertEqual(archived_ids, {"high_pf_tiny_many_lost_winners", "non_entry_time_rule"})
        self.assertEqual(report["non_archived_rules"][0]["scenario_id"], "clean_entry_time_holdout_candidate")

    def test_missing_filter_matrix_blocks_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = archive.build_report(filter_matrix_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("missed_picks_filter_matrix", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matrix = _filter_matrix()
            matrix["live_policy_change"] = True
            matrix_path = Path(tmp) / "matrix.json"
            _write_json(matrix_path, matrix)

            report = archive.build_report(filter_matrix_path=matrix_path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_renders_archived_table_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matrix_path = Path(tmp) / "matrix.json"
            _write_json(matrix_path, _filter_matrix())
            report = archive.build_report(filter_matrix_path=matrix_path)

            markdown = archive.render_markdown(report)

        self.assertIn("## Archived Rules", markdown)
        self.assertIn("high_pf_tiny_many_lost_winners", markdown)
        self.assertIn("does not delete filter-matrix scenarios", markdown)
        self.assertIn("read-only", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix_path = root / "matrix.json"
            _write_json(matrix_path, _filter_matrix())
            report = archive.build_report(filter_matrix_path=matrix_path)

            artifacts = archive.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-overfit-rule-archive.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], archive.REPORT_ID)
            self.assertEqual(latest["status"], "overfit_rule_archive_readback")


if __name__ == "__main__":
    unittest.main()
