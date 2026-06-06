from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import candidate_lifecycle as lifecycle
from scripts import pending_audit_candidates as pending
from scripts.lane_profitability_gate import (
    LANE_GATE_DIAGNOSTIC_STATUS,
    LANE_GATE_PAPER_ONLY_STATUS,
    LANE_GATE_PENDING_STATUS,
    LANE_GATE_PROBATION_PAPER_STATUS,
)
from scripts.lane_promotion_state import (
    LANE_PROMOTION_DIAGNOSTIC_STATUS,
    LANE_PROMOTION_PAPER_EVIDENCE_STATUS,
    LANE_PROMOTION_PAPER_ONLY_STATUS,
)


class CandidateLifecycleContractTests(unittest.TestCase):
    def test_runtime_status_aliases_use_candidate_lifecycle_contract(self) -> None:
        self.assertEqual(LANE_GATE_PENDING_STATUS, lifecycle.STATUS_PENDING_LIVE_VALIDATION)
        self.assertEqual(LANE_GATE_DIAGNOSTIC_STATUS, lifecycle.STATUS_DIAGNOSTIC_LANE_PROFITABILITY_GATE)
        self.assertEqual(LANE_GATE_PAPER_ONLY_STATUS, lifecycle.STATUS_PAPER_LANE_PROFITABILITY_GATE)
        self.assertEqual(
            LANE_GATE_PROBATION_PAPER_STATUS,
            lifecycle.STATUS_PAPER_LANE_PROFITABILITY_PROBATION,
        )
        self.assertEqual(LANE_PROMOTION_DIAGNOSTIC_STATUS, lifecycle.STATUS_DIAGNOSTIC_LANE_PROMOTION_STATE)
        self.assertEqual(LANE_PROMOTION_PAPER_ONLY_STATUS, lifecycle.STATUS_PAPER_LANE_PROMOTION_STATE)
        self.assertEqual(LANE_PROMOTION_PAPER_EVIDENCE_STATUS, lifecycle.STATUS_PENDING_PAPER_EXACT_EVIDENCE)
        self.assertEqual(pending.PAPER_VALIDATION_CIRCUIT_STATUS, lifecycle.STATUS_PAPER_CIRCUIT_BREAKER)
        self.assertEqual(
            pending.DUPLICATE_EXACT_SPREAD_PAPER_STATUS,
            lifecycle.STATUS_PAPER_DUPLICATE_EXACT_SPREAD,
        )

    def test_reportable_status_disposition_visibility_with_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fills = root / "fills.jsonl"
            rows = []
            for index, status in enumerate(sorted(lifecycle.VALIDATION_REPORT_STATUSES)):
                rows.append(
                    {
                        "audit_generated_at_utc": "2026-06-05T14:00:00Z",
                        "candidate_key": f"candidate-{index}",
                        "candidate_status": status,
                        "candidate_status_reason": f"reason-{index}",
                        "playbook_id": "swing",
                        "ticker": f"T{index}",
                        "tracking_approved_lane": True,
                        "position_tracking_mode": "auto_track",
                    }
                )
            queue.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")
            fills.write_text("", encoding="utf8")

            report = pending.build_validation_disposition_report(queue_file=queue, fill_attempt_file=fills)

        statuses = {row["candidate_status"] for row in report["candidates"]}
        self.assertEqual(statuses, set(lifecycle.VALIDATION_REPORT_STATUSES))
        outcomes = {row["candidate_status"]: row["outcome"] for row in report["candidates"]}
        self.assertEqual(
            outcomes[lifecycle.STATUS_LIVE_VALIDATION_ATTEMPTED],
            lifecycle.OUTCOME_NO_LONGER_MATCHED,
        )
        self.assertEqual(outcomes[lifecycle.STATUS_LIVE_VALIDATION_SCAN_FAILED], lifecycle.OUTCOME_BLOCKED)
        for status in lifecycle.PAPER_ONLY_STATUSES & lifecycle.VALIDATION_REPORT_STATUSES:
            self.assertEqual(outcomes[status], lifecycle.OUTCOME_PAPER_ONLY)
        self.assertIn(lifecycle.STATUS_PENDING_PAPER_EXACT_EVIDENCE, lifecycle.PAPER_ONLY_STATUSES)
        self.assertNotIn(lifecycle.STATUS_PENDING_PAPER_EXACT_EVIDENCE, lifecycle.VALIDATION_REPORT_STATUSES)

    def test_contract_status_sets_match_status_rows(self) -> None:
        contract = lifecycle.build_contract()
        statuses = {row["status"] for row in contract["statuses"]}

        self.assertEqual(statuses, set(lifecycle.CANDIDATE_LIFECYCLE_STATUSES))
        self.assertEqual(set(contract["status_sets"]["validation_report"]), set(lifecycle.VALIDATION_REPORT_STATUSES))
        self.assertEqual(set(contract["status_sets"]["paper_only"]), set(lifecycle.PAPER_ONLY_STATUSES))
        self.assertEqual(set(contract["status_sets"]["diagnostic_only"]), set(lifecycle.DIAGNOSTIC_ONLY_STATUSES))
        self.assertEqual(set(contract["status_sets"]["pending_validation"]), set(lifecycle.PENDING_VALIDATION_STATUSES))


if __name__ == "__main__":
    unittest.main()
