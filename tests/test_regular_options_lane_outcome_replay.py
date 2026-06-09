from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_lane_outcome_replay as lane_outcome


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _failure_modes() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_decisions": [
            {"playbook": "short_term", "decision": "diagnostic_only_until_earn_back", "blockers": []},
            {"playbook": "volatility_expansion_observation", "decision": "probation_candidate_flow_with_self_guardrails", "blockers": []},
        ],
        "failure_modes": {
            "by_playbook": [
                {
                    "key": "short_term",
                    "rows": 2,
                    "priced": 2,
                    "profit_factor": 0.25,
                    "avg_net_pnl_pct": -20.0,
                    "median_net_pnl_pct": -20.0,
                    "win_rate_pct": 0.0,
                    "sum_net_pnl_usd": -200.0,
                },
                {
                    "key": "volatility_expansion_observation",
                    "rows": 2,
                    "priced": 2,
                    "profit_factor": 2.0,
                    "avg_net_pnl_pct": 12.0,
                    "median_net_pnl_pct": 12.0,
                    "win_rate_pct": 100.0,
                    "sum_net_pnl_usd": 100.0,
                },
            ]
        },
    }


def _missed_outcome() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "rows": [
            {
                "playbook": "short_term",
                "ticker": "SPY",
                "scan_date": "2026-06-01",
                "tracked_match_count": 0,
                "mark": {"priced": True, "net_pnl_usd": -100.0, "net_pnl_pct": -50.0},
            },
            {
                "playbook": "volatility_expansion_observation",
                "ticker": "QQQ",
                "scan_date": "2026-06-01",
                "tracked_match_count": 0,
                "mark": {"priced": True, "net_pnl_usd": 100.0, "net_pnl_pct": 50.0},
            },
        ],
    }


def _lane_promotion_state() -> dict:
    lane_state = {
        "tracking_mode": "auto_track",
        "fresh_live_validation_enabled": True,
        "promotion_state": "diagnostic",
        "candidate_status": "diagnostic_only_lane_promotion_state",
        "blockers": ["lane_not_profitable_enough_for_probation"],
    }
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_states": {
            "short_term": lane_state,
            "volatility_expansion_observation": {
                **lane_state,
                "promotion_state": "paper_probation",
                "candidate_status": "pending_paper_exact_evidence",
            },
            "bearish_defensive": lane_state,
            "regular_bearish_put_primary": lane_state,
        },
    }


def _zero_pick_audit() -> dict:
    def lane(playbook: str, signals: int, exact: int, would: int) -> dict:
        return {
            "playbook": playbook,
            "status": "completed",
            "summary": {
                "date_count": 10,
                "playbook": playbook,
                "signal_candidate_count": signals,
                "exact_candidate_count": exact,
                "would_track_pick_count": would,
                "no_exact_reason_counts": {"no_chain_native_spread_passed_current_filters": signals}
                if signals and not exact
                else {},
                "signal_reject_reason_counts": {"playbook_filter": 3} if not signals else {},
            },
        }

    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "summary": {"requested_lane_count": 4, "completed_lane_count": 4},
        "lanes": [
            lane("short_term", 2, 2, 2),
            lane("volatility_expansion_observation", 2, 2, 2),
            lane("bearish_defensive", 0, 0, 0),
            lane("regular_bearish_put_primary", 4, 0, 0),
        ],
    }


class RegularOptionsLaneOutcomeReplayTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "failure_modes_path": root / "failure_modes.json",
            "missed_outcome_path": root / "missed_outcome.json",
            "lane_promotion_state_path": root / "lane_promotion.json",
            "zero_pick_audit_path": root / "zero_pick.json",
            "lane_quarantine_archive_path": root / "lane_quarantine.json",
        }
        _write_json(paths["failure_modes_path"], _failure_modes())
        _write_json(paths["missed_outcome_path"], _missed_outcome())
        _write_json(paths["lane_promotion_state_path"], _lane_promotion_state())
        _write_json(paths["zero_pick_audit_path"], _zero_pick_audit())
        _write_json(paths["lane_quarantine_archive_path"], {"status": "lane_quarantine_archive_readback"})
        return paths

    def test_build_report_separates_priced_lanes_from_missing_outcome_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = lane_outcome.build_report(**self._fixture(Path(tmp)), generated_at_utc="2026-06-06T03:00:00Z")

        self.assertEqual(report["status"], "lane_outcome_replay_readback")
        self.assertEqual(report["summary"]["overall_status"], "lane_outcome_replay_built_collecting")
        self.assertEqual(report["summary"]["active_lane_count"], 4)
        self.assertEqual(report["summary"]["priced_outcome_lane_count"], 2)
        self.assertEqual(report["summary"]["missing_outcome_lane_count"], 2)
        rows = {row["lane"]: row for row in report["lane_outcome_table"]}
        self.assertEqual(rows["short_term"]["outcome_status"], "monthly_exact_outcome_available")
        self.assertEqual(rows["bearish_defensive"]["outcome_status"], "no_signal_candidates_in_monthly_window")
        self.assertEqual(
            rows["regular_bearish_put_primary"]["outcome_status"],
            "signal_candidates_without_exact_chain_native_spreads",
        )
        self.assertIsNone(rows["bearish_defensive"]["monthly_profit_factor"])
        actions = {item["action"]: item["count"] for item in report["next_evidence_queue"]}
        self.assertEqual(actions["build_or_repair_lane_scan_hypothesis_before_pnl_replay"], 1)
        self.assertEqual(actions["repair_chain_native_exact_candidate_selection"], 1)
        self.assertFalse(report["live_policy_change"])

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = lane_outcome.build_report(
                failure_modes_path=root / "missing_failure.json",
                missed_outcome_path=root / "missing_outcome.json",
                lane_promotion_state_path=root / "missing_lane.json",
                zero_pick_audit_path=root / "missing_zero.json",
                lane_quarantine_archive_path=root / "missing_archive.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("missed_picks_failure_modes", report["summary"]["missing_required_inputs"])
        self.assertIn("all_lanes_zero_pick_audit", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            bad_zero = _zero_pick_audit()
            bad_zero["live_policy_change"] = True
            _write_json(paths["zero_pick_audit_path"], bad_zero)

            report = lane_outcome.build_report(**paths)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = lane_outcome.build_report(**self._fixture(root))
            markdown = lane_outcome.render_markdown(report)
            artifacts = lane_outcome.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-lane-outcome-replay.md",
            )

            self.assertIn("Lane Outcome Table", markdown)
            self.assertIn("does not synthesize P&L", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
