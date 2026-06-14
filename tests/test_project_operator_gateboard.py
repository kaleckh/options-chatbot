from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_project_operator_gateboard as gateboard


class ProjectOperatorGateboardTests(unittest.TestCase):
    def _write_json(self, root: Path, relative_path: str, payload: dict) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_gateboard_separates_clean_data_from_strategy_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = self._write_json(
                root,
                "project-pathway-registry.json",
                {
                    "report_id": "project_pathway_registry",
                    "pathways": [
                        {"id": "data_path", "owner_docs": [], "owner_scripts": []},
                        {"id": "candidate_path", "owner_docs": [], "owner_scripts": []},
                        {"id": "evidence_path", "owner_docs": [], "owner_scripts": []},
                        {"id": "profitability_path", "owner_docs": [], "owner_scripts": []},
                        {"id": "promotion_path", "owner_docs": [], "owner_scripts": []},
                        {"id": "operator_path", "owner_docs": [], "owner_scripts": []},
                    ],
                },
            )
            lifecycle = self._write_json(root, "candidate-lifecycle.json", {"report_id": "candidate_lifecycle_contract"})
            fresh = self._write_json(
                root,
                "fresh.json",
                {
                    "report_id": "regular_options_fresh_evidence_loop",
                    "status": "fresh_evidence_loop_readback",
                    "summary": {
                        "candidate_count": 34,
                        "candidate_status_counts": {"live_validation_attempted": 22},
                        "entry_evidence_status_counts": {"fresh_executable_exact_entry": 6},
                        "linked_position_count": 1,
                        "exact_realized_pnl_count": 0,
                        "promotion_discussion_ready_count": 0,
                        "validation_outcome_counts": {"proof_ineligible": 5},
                    },
                },
            )
            missed = self._write_json(
                root,
                "missed.json",
                {
                    "report_id": "missed_regular_picks_outcome",
                    "summary": {
                        "mark_coverage_count": 210,
                        "raw_row_count": 210,
                        "mark_unpriced_count": 0,
                        "tracked_row_count": 4,
                        "tracked_rows_with_stored_pnl": 4,
                        "untracked_row_count": 206,
                        "lane_gate_allowed_count": 1,
                        "lane_gate_blocked_count": 7,
                    },
                    "metrics": {
                        "untracked_rows_conservative_mark": {
                            "winner_count": 70,
                            "loser_count": 136,
                            "avg_net_pnl_pct": -15.28,
                            "profit_factor": 0.34,
                        }
                    },
                },
            )
            promotion = self._write_json(
                root,
                "promotion.json",
                {
                    "report_id": "regular_options_lane_promotion_state",
                    "status": "lane_promotion_state_readback",
                    "summary": {
                        "lane_count": 14,
                        "diagnostic_lane_count": 13,
                        "paper_probation_lane_count": 1,
                        "live_validation_lane_count": 0,
                        "auto_track_lane_count": 0,
                        "global_live_exact_negative_count": 1,
                        "live_policy_change": False,
                    },
                },
            )
            open_risk = self._write_json(
                root,
                "open-risk.json",
                {
                    "generated_at_utc": "2026-06-05T23:40:00Z",
                    "scope": "regular_supervised_open_positions_read_only",
                    "open_risk_governor": {
                        "status": "open_risk_governor_blocked",
                        "blockers": ["live_exact_negative_open_risk"],
                        "live_exact_negative_ids": [537],
                    },
                },
            )
            suggested_risk = self._write_json(
                root,
                "suggested-risk.json",
                {
                    "generated_at_utc": "2026-06-05T23:41:00Z",
                    "summary": {"rows": 1},
                    "attention_trade_ids": [138],
                },
            )
            shortlist = self._write_json(
                root,
                "shortlist.json",
                {
                    "status": "paper_shortlist_readback",
                    "summary": {
                        "eligible_count": 0,
                        "release_gate_status": "no_paper_shortlist_candidates",
                    },
                },
            )
            scorecard = self._write_json(
                root,
                "scorecard.json",
                {
                    "status": "visible_product_profitability_progress_but_proof_still_blocked",
                    "paper_gate_readiness": {
                        "status": "paper_only_no_live_release",
                        "eligible_paper_review_candidate_count": 0,
                    },
                },
            )
            ai = self._write_json(
                root,
                "ai.json",
                {
                    "verified": False,
                    "current_shared_quote_dates": 3,
                    "required_shared_quote_dates": 100,
                },
            )
            heartbeat = self._write_json(
                root,
                "heartbeat.json",
                {
                    "report_id": "scheduled_scan_heartbeat",
                    "status": "completed",
                    "generated_at_utc": "2026-06-05T18:00:00Z",
                    "run_completed_at_utc": "2026-06-05T18:00:00Z",
                    "host": "KaesDevice",
                    "commit_sha": "abcdef123456",
                },
            )
            data_integrity = {
                "audit": "repository_constraints",
                "status": "pass_or_skipped",
                "stores": [
                    {"store_id": "sqlite_suggested_trades", "status": "pass", "violations": [], "diagnostics": []},
                    {"store_id": "postgres_tracked_positions", "status": "pass", "violations": [], "diagnostics": []},
                ],
            }

            report = gateboard.build_gateboard(
                generated_at_utc="2026-06-05T23:59:00Z",
                data_integrity_audit=data_integrity,
                pathway_registry_path=registry,
                missed_outcome_path=missed,
                lane_promotion_path=promotion,
                fresh_evidence_path=fresh,
                open_risk_path=open_risk,
                suggested_risk_path=suggested_risk,
                paper_shortlist_path=shortlist,
                operating_scorecard_path=scorecard,
                candidate_lifecycle_path=lifecycle,
                ai_commodity_path=ai,
                scan_heartbeat_path=heartbeat,
            )

        states = {row["id"]: row["state"] for row in report["pathway_statuses"]}
        self.assertEqual(states["data_path"], "pass")
        self.assertEqual(states["profitability_path"], "blocked")
        self.assertEqual(states["promotion_path"], "blocked")
        self.assertEqual(report["overall_status"], "safe_blocked_no_live_release")
        self.assertIn("Data is readable", report["primary_message"])
        self.assertEqual(report["no_chase_manifest"]["status"], "no_chase_active")
        self.assertEqual(report["scheduled_scan_health"]["status"], "fresh")
        reasons = {row["reason"] for row in report["no_chase_manifest"]["reasons"]}
        self.assertIn("open_risk_governor_blocked_or_missing", reasons)
        self.assertIn("suggested_trade_review_attention_required", reasons)

    def test_render_markdown_includes_visual_and_counts(self) -> None:
        report = {
            "overall_status": "safe_blocked_no_live_release",
            "generated_at_utc": "2026-06-05T23:59:00Z",
            "primary_message": "Data is readable, but release is intentionally blocked.",
            "pathway_statuses": [
                {"id": "data_path", "label": "Data Path", "state": "pass", "headline": "Clean", "details": ["hard_violation_count=0"]},
                {"id": "candidate_path", "label": "Candidate Path", "state": "pass", "headline": "Visible", "details": ["fresh_candidate_count=34"]},
                {"id": "evidence_path", "label": "Evidence Path", "state": "blocked", "headline": "No promotion-ready rows", "details": ["promotion_discussion_ready_count=0"]},
                {"id": "profitability_path", "label": "Profitability Path", "state": "blocked", "headline": "Negative economics", "details": ["untracked_profit_factor=0.34"]},
                {"id": "promotion_path", "label": "Promotion Path", "state": "blocked", "headline": "No live lanes", "details": ["auto_track_lane_count=0"]},
                {"id": "operator_path", "label": "Operator Path", "state": "blocked", "headline": "No eligible candidates", "details": ["eligible_paper_review_candidates=0"]},
            ],
            "operator_next_actions": ["Keep live validation and auto-track disabled."],
            "no_chase_manifest": {
                "status": "no_chase_active",
                "reason_count": 1,
                "live_policy_change": False,
                "reasons": [
                    {
                        "reason": "no_live_validation_lanes",
                        "severity": "block_live_validation",
                        "evidence": {"auto_track_lane_count": 0},
                    }
                ],
                "prohibited_actions": ["do_not_open_live_or_auto_track_rows_from_blocked_readbacks"],
            },
            "source_artifacts": {
                "missed_regular_picks_outcome": {
                    "path": "data/forward-tracking/missed_regular_picks_outcome_latest.json",
                    "available": True,
                    "status": "readback",
                    "generated_at_utc": "2026-06-05T19:35:21Z",
                }
            },
            "non_goals": ["create trades"],
        }

        markdown = gateboard.render_markdown(report)

        self.assertIn("```mermaid", markdown)
        self.assertIn("## No-Chase Manifest", markdown)
        self.assertIn("untracked_profit_factor=0.34", markdown)
        self.assertIn("Produced by `scripts/build_project_operator_gateboard.py`", markdown)
        self.assertNotIn("\nGenerated by `scripts/build_project_operator_gateboard.py`", markdown)


if __name__ == "__main__":
    unittest.main()
