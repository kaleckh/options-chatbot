from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_volatility_probation_reconciliation as reconciliation


class VolatilityProbationReconciliationTests(unittest.TestCase):
    def test_reconciliation_splits_legacy_live_rows_from_current_paper_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fresh = root / "fresh.json"
            promotion = root / "promotion.json"
            open_risk = root / "open-risk.json"
            queue_rows = [
                {
                    "candidate_key": "legacy",
                    "playbook_id": "volatility_expansion_observation",
                    "candidate_status": "live_validation_attempted",
                    "ticker": "QQQ",
                    "audit_generated_at_utc": "2026-06-05T14:00:00Z",
                },
                {
                    "candidate_key": "paper",
                    "playbook_id": "volatility_expansion_observation",
                    "candidate_status": "pending_paper_exact_evidence",
                    "ticker": "DIA",
                    "audit_generated_at_utc": "2026-06-06T14:00:00Z",
                },
            ]
            queue.write_text("\n".join(json.dumps(row) for row in queue_rows) + "\n", encoding="utf8")
            fresh.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-06T14:30:00Z",
                        "candidates": [
                            {
                                "candidate_key": "legacy",
                                "playbook_id": "volatility_expansion_observation",
                                "candidate_status": "live_validation_attempted",
                                "promotion_gate_context": "legacy_pre_promotion_state_gate",
                                "ticker": "QQQ",
                                "validation_outcome": "created",
                                "entry_evidence_status": "fresh_executable_exact_entry",
                                "realized_pnl_status": "exact_realized_pnl_available",
                                "promotion_discussion_ready": True,
                                "auto_track_position_id": 537,
                            },
                            {
                                "candidate_key": "paper",
                                "playbook_id": "volatility_expansion_observation",
                                "candidate_status": "pending_paper_exact_evidence",
                                "ticker": "DIA",
                                "validation_outcome": "paper_only",
                                "evidence_bridge_status": "paper_probation_exact_entry_required",
                            },
                        ],
                    }
                ),
                encoding="utf8",
            )
            promotion.write_text(
                json.dumps(
                    {
                        "report_id": "regular_options_lane_promotion_state",
                        "generated_at_utc": "2026-06-06T14:40:00Z",
                        "lane_states": {
                            "volatility_expansion_observation": {
                                "promotion_state": "paper_probation",
                                "candidate_status": "pending_paper_exact_evidence",
                                "failed_promotion_gates": ["fresh_paper_cohort"],
                                "blockers": ["fresh_paper_cohort_insufficient"],
                            }
                        },
                    }
                ),
                encoding="utf8",
            )
            open_risk.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-06T14:45:00Z",
                        "open_risk_governor": {
                            "status": "open_risk_governor_blocked",
                            "blockers": ["live_exact_negative_open_risk"],
                            "live_exact_negative_ids": [537],
                        },
                    }
                ),
                encoding="utf8",
            )

            report = reconciliation.build_report(
                queue_file=queue,
                fresh_evidence_path=fresh,
                lane_promotion_path=promotion,
                open_risk_path=open_risk,
                generated_at_utc="2026-06-06T15:00:00Z",
            )

        self.assertEqual(report["status"], "paper_probation_blocked")
        self.assertEqual(report["summary"]["legacy_pre_promotion_state_gate_count"], 1)
        self.assertEqual(report["summary"]["current_paper_probation_exact_evidence_pending_count"], 1)
        self.assertEqual(report["summary"]["promotion_discussion_ready_excluding_legacy_count"], 0)
        contexts = {row["candidate_key"]: row["reconciliation_context"] for row in report["reconciliation_rows"]}
        self.assertEqual(contexts["legacy"], "legacy_pre_promotion_state_gate")
        self.assertEqual(contexts["paper"], "current_paper_probation_exact_evidence_pending")


if __name__ == "__main__":
    unittest.main()
