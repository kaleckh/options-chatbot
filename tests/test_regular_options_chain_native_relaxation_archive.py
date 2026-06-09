from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_chain_native_relaxation_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _exit_outcome_replay() -> dict:
    return {
        "status": "chain_native_exit_outcome_replay_readback",
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "summary": {
            "overall_status": "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only",
            "missing_exit_quote_demand_count": 0,
            "best_relaxed_scenario": {
                "scenario_id": "widen_dte_window_only",
                "profit_factor": 0.62,
                "avg_net_pnl_pct": -9.26,
                "sum_net_pnl_usd": -1154.0,
            },
        },
        "scenario_metrics": [
            {
                "scenario_id": "current_chain_native_filters",
                "relaxation_kind": "current",
                "rows": 2,
                "priced": 2,
                "unpriced": 0,
                "profit_factor": 0.0,
                "avg_net_pnl_pct": -20.0,
                "sum_net_pnl_usd": -500.0,
            },
            {
                "scenario_id": "widen_dte_window_only",
                "relaxation_kind": "relaxed",
                "rows": 2,
                "priced": 2,
                "unpriced": 0,
                "profit_factor": 0.62,
                "avg_net_pnl_pct": -9.26,
                "median_net_pnl_pct": -8.0,
                "sum_net_pnl_usd": -1154.0,
                "win_rate_pct": 50.0,
                "winner_count": 1,
                "loser_count": 1,
            },
            {
                "scenario_id": "positive_holdout_probe",
                "relaxation_kind": "relaxed",
                "rows": 2,
                "priced": 2,
                "unpriced": 0,
                "profit_factor": 1.4,
                "avg_net_pnl_pct": 5.5,
                "sum_net_pnl_usd": 120.0,
            },
        ],
        "outcome_rows": [
            {
                "scenario_id": "current_chain_native_filters",
                "relaxation_kind": "current",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "ticker": "COIN",
                "exact_exit_pnl_available": True,
            },
            {
                "scenario_id": "current_chain_native_filters",
                "relaxation_kind": "current",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "ticker": "DIS",
                "exact_exit_pnl_available": True,
            },
            {
                "scenario_id": "widen_dte_window_only",
                "relaxation_kind": "relaxed",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "ticker": "COIN",
                "exact_exit_pnl_available": True,
            },
            {
                "scenario_id": "widen_dte_window_only",
                "relaxation_kind": "relaxed",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "ticker": "DIS",
                "exact_exit_pnl_available": True,
            },
            {
                "scenario_id": "positive_holdout_probe",
                "relaxation_kind": "relaxed",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "ticker": "META",
                "exact_exit_pnl_available": True,
            },
        ],
        "next_evidence_queue": [
            {
                "priority": 5,
                "action": "archive_negative_chain_native_relaxation_branch",
                "count": 1,
                "reason": "relaxed_chain_native_exit_outcome_not_profitable_on_exact_replay",
            }
        ],
    }


class RegularOptionsChainNativeRelaxationArchiveTests(unittest.TestCase):
    def test_archives_negative_current_and_relaxed_branches_without_archiving_positive_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exit_outcome.json"
            _write_json(path, _exit_outcome_replay())

            report = archive.build_report(
                chain_native_exit_outcome_replay_path=path,
                generated_at_utc="2026-06-06T01:00:00Z",
            )

        self.assertEqual(report["status"], "chain_native_relaxation_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "negative_chain_native_branches_archived")
        self.assertEqual(report["summary"]["archived_negative_branch_count"], 2)
        self.assertEqual(report["summary"]["archived_negative_current_scenario_count"], 1)
        self.assertEqual(report["summary"]["archived_negative_relaxed_scenario_count"], 1)
        self.assertTrue(report["summary"]["archive_complete"])
        self.assertTrue(report["summary"]["archive_requested_by_exit_outcome_replay"])
        archived = {item["scenario_id"]: item for item in report["archived_branches"]}
        self.assertEqual(
            archived["current_chain_native_filters"]["archive_status"],
            "archived_negative_chain_native_current_branch",
        )
        self.assertEqual(
            archived["widen_dte_window_only"]["archive_status"],
            "archived_negative_chain_native_relaxation_branch",
        )
        self.assertEqual(archived["widen_dte_window_only"]["target_tickers"], ["COIN", "DIS"])
        self.assertEqual(report["non_archived_branches"][0]["scenario_id"], "positive_holdout_probe")

    def test_missing_exit_outcome_blocks_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = archive.build_report(chain_native_exit_outcome_replay_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("chain_native_exit_outcome_replay", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _exit_outcome_replay()
            payload["live_policy_change"] = True
            path = Path(tmp) / "exit_outcome.json"
            _write_json(path, payload)

            report = archive.build_report(chain_native_exit_outcome_replay_path=path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_non_exact_exit_replay_does_not_archive_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _exit_outcome_replay()
            payload["summary"]["overall_status"] = "chain_native_exit_outcome_replay_exit_quote_gap"
            payload["summary"]["missing_exit_quote_demand_count"] = 2
            path = Path(tmp) / "exit_outcome.json"
            _write_json(path, payload)

            report = archive.build_report(chain_native_exit_outcome_replay_path=path)

        self.assertEqual(report["status"], "chain_native_relaxation_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "no_negative_chain_native_branches_to_archive")
        self.assertFalse(report["summary"]["source_ready_for_archive"])
        self.assertFalse(report["archived_branches"])

    def test_markdown_renders_archive_table_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exit_outcome.json"
            _write_json(path, _exit_outcome_replay())
            report = archive.build_report(chain_native_exit_outcome_replay_path=path)

            markdown = archive.render_markdown(report)

        self.assertIn("## Archived Branches", markdown)
        self.assertIn("current_chain_native_filters", markdown)
        self.assertIn("widen_dte_window_only", markdown)
        self.assertIn("read-only", markdown)
        self.assertIn("does not delete chain-native scenarios", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "exit_outcome.json"
            _write_json(path, _exit_outcome_replay())
            report = archive.build_report(chain_native_exit_outcome_replay_path=path)

            artifacts = archive.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-chain-native-relaxation-archive.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], archive.REPORT_ID)
            self.assertEqual(latest["status"], "chain_native_relaxation_archive_readback")


if __name__ == "__main__":
    unittest.main()
