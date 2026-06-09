from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_lane_scan_hypothesis_repair as repair


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _lane_outcome_replay() -> dict:
    return {
        "status": "lane_outcome_replay_readback",
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "live_policy_change": False,
        "summary": {"overall_status": "lane_outcome_replay_built_collecting"},
        "lane_outcome_table": [
            {
                "lane": "no_signal_candidate_lane",
                "outcome_status": "no_signal_candidates_in_monthly_window",
                "zero_pick_date_count": 10,
                "zero_pick_signal_candidate_count": 0,
                "zero_pick_exact_candidate_count": 0,
                "zero_pick_would_track_pick_count": 0,
                "zero_pick_signal_reject_reason_counts": {"playbook_filter": 4, "signal": 2},
            },
            {
                "lane": "missing_candidate_lane",
                "outcome_status": "no_signal_candidates_in_monthly_window",
                "zero_pick_date_count": 9,
                "zero_pick_signal_candidate_count": 0,
                "zero_pick_exact_candidate_count": 0,
                "zero_pick_would_track_pick_count": 0,
                "zero_pick_signal_reject_reason_counts": {"direction_score": 3},
            },
            {
                "lane": "signal_without_exact_lane",
                "outcome_status": "signal_candidates_without_exact_chain_native_spreads",
                "zero_pick_signal_candidate_count": 4,
                "zero_pick_exact_candidate_count": 0,
            },
        ],
        "next_evidence_queue": [
            {
                "priority": 7,
                "action": "build_or_repair_lane_scan_hypothesis_before_pnl_replay",
                "count": 2,
                "reason": "no_signal_candidates_in_monthly_window",
            }
        ],
    }


def _zero_pick_audit() -> dict:
    def lane(playbook: str, reasons: dict[str, int]) -> dict:
        return {
            "playbook": playbook,
            "status": "completed",
            "summary": {
                "date_count": 10,
                "signal_candidate_count": 0,
                "exact_candidate_count": 0,
                "would_track_pick_count": 0,
                "signal_reject_reason_counts": reasons,
            },
        }

    return {
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "live_policy_change": False,
        "lanes": [
            lane("no_signal_candidate_lane", {"playbook_filter": 5, "signal": 2}),
            lane("missing_candidate_lane", {"direction_score": 3}),
        ],
    }


def _lane_promotion_state() -> dict:
    lane_state = {
        "tracking_mode": "auto_track",
        "promotion_state": "diagnostic",
        "candidate_status": "diagnostic_only_lane_promotion_state",
        "blockers": ["lane_not_profitable_enough_for_probation"],
    }
    return {
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "live_policy_change": False,
        "lane_states": {
            "no_signal_candidate_lane": lane_state,
            "missing_candidate_lane": lane_state,
        },
    }


def _symbol_sleeves() -> dict:
    return {
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "live_policy_change": False,
        "lane_symbol_rows": [
            {
                "sleeve_id": "no_signal_candidate_lane_chain_native_timeexit:QQQ",
                "lane_family": "no_signal_candidate_lane",
                "lane_id": "no_signal_candidate_lane_chain_native_timeexit",
                "strategy_logic_id": "no_signal_candidate_lane_chain_native_timeexit",
                "symbol": "QQQ",
                "status": "needs-paper",
                "evidence_class": "trusted_intraday_unresolved",
                "sample_status": "none",
                "metrics": {
                    "candidates": 12,
                    "exact_trusted_priced_trades": 0,
                    "unresolved_rows": 12,
                    "quote_coverage": 0.0,
                    "profit_factor": 0.0,
                    "avg_pnl": 0.0,
                },
                "executable_exit_pnl": None,
                "reason_codes": ["evidence_class:trusted_intraday_unresolved"],
                "blockers": ["unresolved_rows_remain"],
            },
            {
                "sleeve_id": "no_signal_candidate_lane_daily:SPY",
                "lane_family": "no_signal_candidate_lane",
                "lane_id": "no_signal_candidate_lane_daily",
                "strategy_logic_id": "no_signal_candidate_lane_daily",
                "symbol": "SPY",
                "status": "needs-paper",
                "evidence_class": "daily_eod_research_only",
                "metrics": {"candidates": 8},
            },
            {
                "sleeve_id": "no_signal_candidate_lane_rejected:SPY",
                "lane_family": "no_signal_candidate_lane",
                "lane_id": "no_signal_candidate_lane_rejected",
                "strategy_logic_id": "no_signal_candidate_lane_rejected",
                "symbol": "SPY",
                "status": "rejected",
                "evidence_class": "trusted_intraday_opra_nbbo_exact",
                "metrics": {"candidates": 7, "exact_trusted_priced_trades": 7},
            },
        ],
    }


class RegularOptionsLaneScanHypothesisRepairTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "lane_outcome_replay_path": root / "lane_outcome.json",
            "zero_pick_audit_path": root / "zero_pick.json",
            "lane_promotion_state_path": root / "lane_promotion.json",
            "symbol_sleeves_path": root / "symbol_sleeves.json",
        }
        _write_json(paths["lane_outcome_replay_path"], _lane_outcome_replay())
        _write_json(paths["zero_pick_audit_path"], _zero_pick_audit())
        _write_json(paths["lane_promotion_state_path"], _lane_promotion_state())
        _write_json(paths["symbol_sleeves_path"], _symbol_sleeves())
        return paths

    def test_build_report_finds_predeclared_proof_only_candidate_without_promoting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = repair.build_report(**self._fixture(Path(tmp)), generated_at_utc="2026-06-07T02:00:00Z")

        self.assertEqual(report["status"], "lane_scan_hypothesis_repair_readback")
        self.assertEqual(report["summary"]["overall_status"], "lane_scan_hypothesis_repair_built_collecting")
        self.assertEqual(report["summary"]["target_no_signal_lane_count"], 2)
        self.assertEqual(report["summary"]["predeclared_replacement_candidate_count"], 1)
        self.assertEqual(report["summary"]["predeclared_candidate_lane_count"], 1)
        self.assertEqual(report["summary"]["missing_replacement_candidate_lane_count"], 1)
        self.assertEqual(report["summary"]["proof_ready_replacement_candidate_count"], 0)
        self.assertEqual(report["summary"]["fresh_exact_scan_retest_row_count"], 0)
        self.assertEqual(report["summary"]["true_lane_outcome_pnl_row_count"], 0)
        self.assertFalse(report["summary"]["promotion_ready"])
        rows = {row["lane"]: row for row in report["repair_rows"]}
        self.assertEqual(rows["no_signal_candidate_lane"]["repair_status"], "predeclared_proof_only_candidate_found")
        self.assertEqual(rows["missing_candidate_lane"]["repair_status"], "causal_replacement_hypothesis_missing")
        candidate = rows["no_signal_candidate_lane"]["predeclared_replacement_candidates"][0]
        self.assertEqual(candidate["proof_status"], "proof_only_collecting_not_production_proof")
        self.assertFalse(candidate["production_proof_ready"])
        actions = {item["action"]: item["count"] for item in report["next_evidence_queue"]}
        self.assertEqual(actions["collect_proof_only_lane_scan_retest_rows"], 1)
        self.assertEqual(actions["draft_causal_hypothesis_for_no_signal_lane_without_tuning"], 1)
        self.assertIn("do_not_tune_threshold_symbol_expiry_or_window_from_zero_signal_sample", report["prohibited_actions"])

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = repair.build_report(
                lane_outcome_replay_path=root / "missing_lane_outcome.json",
                zero_pick_audit_path=root / "missing_zero_pick.json",
                lane_promotion_state_path=root / "missing_lane_promotion.json",
                symbol_sleeves_path=root / "missing_symbol_sleeves.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("lane_outcome_replay", report["summary"]["missing_required_inputs"])
        self.assertIn("regular_options_symbol_sleeves", report["summary"]["missing_required_inputs"])

    def test_write_outputs_creates_latest_and_docs_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = repair.build_report(**self._fixture(root))
            markdown = repair.render_markdown(report)
            artifacts = repair.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-lane-scan-hypothesis-repair.md",
            )

            self.assertIn("Lane Scan Hypothesis Repair", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
