from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_exact_candidate_selection_repair as repair


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _lane_outcome_replay() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "status": "lane_outcome_replay_readback",
        "live_policy_change": False,
        "summary": {
            "overall_status": "lane_outcome_replay_built_collecting",
            "missing_outcome_lane_count": 1,
        },
        "lane_outcome_table": [
            {
                "lane": "regular_bearish_put_primary",
                "disposition": "needs_replay_engine",
                "outcome_status": "signal_candidates_without_exact_chain_native_spreads",
                "zero_pick_signal_candidate_count": 4,
                "zero_pick_exact_candidate_count": 0,
                "zero_pick_would_track_pick_count": 0,
            },
            {
                "lane": "short_term",
                "disposition": "quarantine",
                "outcome_status": "monthly_exact_outcome_available",
                "monthly_profit_factor": 0.28,
            },
        ],
    }


def _zero_pick_audit() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lanes": [
            {
                "playbook": "regular_bearish_put_primary",
                "status": "completed",
                "dates": [
                    {
                        "scan_date": "2026-05-22",
                        "signal_candidate_count": 4,
                        "exact_candidate_count": 0,
                        "selected_count": 0,
                        "top_signal_tickers": ["META", "COIN", "SBUX", "DIS"],
                        "exact_reject_reasons": {"no_chain_native_spread_passed_current_filters": 4},
                    },
                    {
                        "scan_date": "2026-05-26",
                        "signal_candidate_count": 0,
                        "exact_candidate_count": 0,
                        "selected_count": 0,
                        "top_signal_tickers": [],
                        "exact_reject_reasons": {},
                    },
                ],
            }
        ],
    }


class RegularOptionsExactCandidateSelectionRepairTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "lane_outcome_replay_path": root / "lane_outcome.json",
            "zero_pick_audit_path": root / "zero_pick.json",
        }
        _write_json(paths["lane_outcome_replay_path"], _lane_outcome_replay())
        _write_json(paths["zero_pick_audit_path"], _zero_pick_audit())
        return paths

    def test_build_report_targets_signal_dates_without_exact_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = repair.build_report(**self._fixture(Path(tmp)), generated_at_utc="2026-06-06T03:00:00Z")

        self.assertEqual(report["status"], "exact_candidate_selection_repair_readback")
        self.assertEqual(report["summary"]["overall_status"], "exact_candidate_selection_repair_targets_ready")
        self.assertEqual(report["summary"]["target_lane_count"], 1)
        self.assertEqual(report["summary"]["target_date_count"], 1)
        self.assertEqual(report["summary"]["target_signal_candidate_count"], 4)
        self.assertEqual(report["summary"]["target_exact_candidate_count"], 0)
        self.assertEqual(report["summary"]["exact_reject_reason_counts"], {"no_chain_native_spread_passed_current_filters": 4})
        target = report["repair_targets"][0]
        self.assertEqual(target["lane"], "regular_bearish_put_primary")
        self.assertEqual(target["scan_date"], "2026-05-22")
        self.assertEqual(target["top_signal_tickers"], ["META", "COIN", "SBUX", "DIS"])
        self.assertEqual(report["next_evidence_queue"][0]["action"], "build_chain_native_filter_relaxation_replay")
        self.assertFalse(report["live_policy_change"])

    def test_no_targets_is_clean_readback_without_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            payload = _lane_outcome_replay()
            payload["lane_outcome_table"][0]["outcome_status"] = "monthly_exact_outcome_available"
            _write_json(paths["lane_outcome_replay_path"], payload)

            report = repair.build_report(**paths)

        self.assertEqual(report["status"], "exact_candidate_selection_repair_readback")
        self.assertEqual(report["summary"]["overall_status"], "exact_candidate_selection_repair_no_targets")
        self.assertEqual(report["summary"]["target_date_count"], 0)
        self.assertEqual(report["next_evidence_queue"], [])

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = repair.build_report(
                lane_outcome_replay_path=root / "missing_lane_outcome.json",
                zero_pick_audit_path=root / "missing_zero_pick.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("lane_outcome_replay", report["summary"]["missing_required_inputs"])
        self.assertIn("all_lanes_zero_pick_audit", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            bad_zero = _zero_pick_audit()
            bad_zero["live_policy_change"] = True
            _write_json(paths["zero_pick_audit_path"], bad_zero)

            report = repair.build_report(**paths)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = repair.build_report(**self._fixture(root))
            markdown = repair.render_markdown(report)
            artifacts = repair.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-exact-candidate-selection-repair.md",
            )

            self.assertIn("Repair Targets", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
