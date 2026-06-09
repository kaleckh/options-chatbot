from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_lane_quarantine_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _failure_modes() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_decisions": [
            {
                "playbook": "short_term",
                "decision": "diagnostic_only_until_earn_back",
                "blockers": ["profit_factor_below_lane_gate", "average_net_pnl_not_positive"],
            },
            {
                "playbook": "speculative",
                "decision": "diagnostic_only_until_earn_back",
                "blockers": ["insufficient_priced_exact_outcomes"],
            },
            {
                "playbook": "volatility_expansion_observation",
                "decision": "probation_candidate_flow_with_self_guardrails",
                "blockers": [],
            },
        ],
        "failure_modes": {
            "by_playbook": [
                {
                    "key": "short_term",
                    "rows": 54,
                    "priced": 54,
                    "profit_factor": 0.28,
                    "avg_net_pnl_pct": -18.93,
                    "median_net_pnl_pct": -16.91,
                    "win_rate_pct": 33.3,
                    "sum_net_pnl_usd": -3518.15,
                },
                {
                    "key": "speculative",
                    "rows": 8,
                    "priced": 8,
                    "profit_factor": 0.12,
                    "avg_net_pnl_pct": -12.62,
                    "median_net_pnl_pct": -15.53,
                    "win_rate_pct": 25.0,
                    "sum_net_pnl_usd": -413.15,
                },
                {
                    "key": "volatility_expansion_observation",
                    "rows": 24,
                    "priced": 24,
                    "profit_factor": 1.72,
                    "avg_net_pnl_pct": 6.75,
                    "median_net_pnl_pct": 2.15,
                    "win_rate_pct": 50.0,
                    "sum_net_pnl_usd": 972.3,
                },
            ]
        },
    }


def _lane_promotion_state() -> dict:
    base_blockers = [
        "lane_not_profitable_enough_for_probation",
        "fresh_paper_cohort_insufficient",
        "current_live_exact_risk_governor_blocked",
    ]
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_states": {
            "short_term": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "diagnostic",
                "candidate_status": "diagnostic_only_lane_promotion_state",
                "blockers": base_blockers,
            },
            "speculative": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "diagnostic",
                "candidate_status": "diagnostic_only_lane_promotion_state",
                "blockers": ["insufficient_priced_exact_outcomes"],
            },
            "volatility_expansion_observation": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "paper_probation",
                "candidate_status": "pending_paper_exact_evidence",
                "blockers": ["fresh_paper_cohort_insufficient"],
            },
        },
    }


class RegularOptionsLaneQuarantineArchiveTests(unittest.TestCase):
    def test_archives_only_quarantined_negative_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure_path = root / "failure_modes.json"
            lane_path = root / "lane_state.json"
            _write_json(failure_path, _failure_modes())
            _write_json(lane_path, _lane_promotion_state())

            report = archive.build_report(
                failure_modes_path=failure_path,
                lane_promotion_state_path=lane_path,
                generated_at_utc="2026-06-06T03:00:00Z",
            )

        self.assertEqual(report["status"], "lane_quarantine_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "lane_quarantines_archived")
        self.assertEqual(report["summary"]["quarantine_lane_count"], 1)
        archived = {item["lane"]: item for item in report["archived_lanes"]}
        self.assertEqual(set(archived), {"short_term"})
        self.assertEqual(archived["short_term"]["archive_status"], "archived_quarantine_lane")
        self.assertFalse(archived["short_term"]["promotion_ready"])

    def test_missing_inputs_block_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = archive.build_report(
                failure_modes_path=Path(tmp) / "missing_failure.json",
                lane_promotion_state_path=Path(tmp) / "missing_lane.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("missed_picks_failure_modes", report["summary"]["missing_required_inputs"])
        self.assertIn("lane_promotion_state", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure = _failure_modes()
            failure["live_policy_change"] = True
            failure_path = root / "failure_modes.json"
            lane_path = root / "lane_state.json"
            _write_json(failure_path, failure)
            _write_json(lane_path, _lane_promotion_state())

            report = archive.build_report(failure_modes_path=failure_path, lane_promotion_state_path=lane_path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_renders_quarantine_table_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure_path = root / "failure_modes.json"
            lane_path = root / "lane_state.json"
            _write_json(failure_path, _failure_modes())
            _write_json(lane_path, _lane_promotion_state())
            report = archive.build_report(failure_modes_path=failure_path, lane_promotion_state_path=lane_path)

            markdown = archive.render_markdown(report)

        self.assertIn("## Archived Lanes", markdown)
        self.assertIn("short_term", markdown)
        self.assertIn("does not delete or disable lanes", markdown)
        self.assertIn("read-only", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure_path = root / "failure_modes.json"
            lane_path = root / "lane_state.json"
            _write_json(failure_path, _failure_modes())
            _write_json(lane_path, _lane_promotion_state())
            report = archive.build_report(failure_modes_path=failure_path, lane_promotion_state_path=lane_path)

            artifacts = archive.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-lane-quarantine-archive.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], archive.REPORT_ID)
            self.assertEqual(latest["status"], "lane_quarantine_archive_readback")


if __name__ == "__main__":
    unittest.main()
