from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend_route_context import BackendRouteContext  # noqa: E402
from proof_summary_service import build_proof_summary  # noqa: E402


class _ProofSummaryRepository:
    is_available = True

    def __init__(self, *, open_rows=None, closed_rows=None):
        self.open_rows = list(open_rows or [])
        self.closed_rows = list(closed_rows or [])

    def list_positions(self, status="open", *args, **kwargs):
        if status == "open":
            return list(self.open_rows)
        if status == "closed":
            return list(self.closed_rows)
        return []


def _loop_health():
    return {"state": "blocked", "blockers": [{"code": "proof_gap"}]}


def _claim_readiness():
    return {
        "state": "blocked",
        "claim_ready": False,
        "blocker_count": 1,
        "blockers": [{"code": "claim_gap"}],
        "eligible_event_count": 7,
        "pending_truth_event_count": 2,
        "by_symbol": {"SPY": {"eligible": 3}},
        "tracked_realized_metrics": {"avg_net_pnl_pct": 12.5},
    }


class ProofSummaryServiceTests(unittest.TestCase):
    def test_build_proof_summary_counts_positions_and_forward_evidence(self):
        namespace = {
            "POSITIONS_REPOSITORY": _ProofSummaryRepository(
                open_rows=[{"id": 1}],
                closed_rows=[
                    {"id": 2, "raw_exact": True, "proof_grade": True},
                    {"id": 3, "raw_exact": True, "proof_grade": False},
                ],
            ),
            "evaluate_measurement_gate": _loop_health,
            "evaluate_claim_readiness": _claim_readiness,
            "_cached_forward_evidence_report": lambda: {
                "scan_pick_count": "12",
                "eligible_scan_pick_count": "5",
                "ledger_summary": {
                    "position_opened_event_count": "4",
                    "review_event_count": "9",
                },
            },
            "_row_has_raw_exact_contract": lambda row: bool(row.get("raw_exact")),
            "_row_counts_as_proof_grade_exact_closed": lambda row: bool(row.get("proof_grade")),
        }

        summary = build_proof_summary(BackendRouteContext(namespace))

        self.assertEqual(summary["loop_health"]["state"], "blocked")
        self.assertEqual(summary["loop_health"]["blocker_count"], 1)
        self.assertFalse(summary["claim_readiness"]["claim_ready"])
        self.assertEqual(summary["evidence_counts"]["forward_event_count"], 12)
        self.assertEqual(summary["evidence_counts"]["eligible_scan_pick_event_count"], 5)
        self.assertEqual(summary["evidence_counts"]["position_opened_event_count"], 4)
        self.assertEqual(summary["evidence_counts"]["review_event_count"], 9)
        self.assertEqual(summary["evidence_counts"]["eligible_event_count"], 7)
        self.assertEqual(summary["tracked_positions"]["open_count"], 1)
        self.assertEqual(summary["tracked_positions"]["closed_count"], 2)
        self.assertEqual(summary["tracked_positions"]["raw_exact_contract_closed_count"], 2)
        self.assertEqual(summary["tracked_positions"]["proof_grade_exact_contract_closed_count"], 1)
        self.assertEqual(summary["tracked_positions"]["exact_contract_closed_count"], 1)
        self.assertEqual(summary["realized_metrics"]["avg_net_pnl_pct"], 12.5)

    def test_build_proof_summary_uses_late_bound_repository(self):
        namespace = {
            "POSITIONS_REPOSITORY": _ProofSummaryRepository(open_rows=[{"id": 1}], closed_rows=[]),
            "evaluate_measurement_gate": _loop_health,
            "evaluate_claim_readiness": _claim_readiness,
            "_cached_forward_evidence_report": lambda: {"ledger_summary": {}},
            "_row_has_raw_exact_contract": lambda row: False,
            "_row_counts_as_proof_grade_exact_closed": lambda row: False,
        }
        ctx = BackendRouteContext(namespace)

        first = build_proof_summary(ctx)
        namespace["POSITIONS_REPOSITORY"] = _ProofSummaryRepository(
            open_rows=[{"id": 2}, {"id": 3}],
            closed_rows=[{"id": 4}],
        )
        second = build_proof_summary(ctx)

        self.assertEqual(first["tracked_positions"]["open_count"], 1)
        self.assertEqual(first["tracked_positions"]["closed_count"], 0)
        self.assertEqual(second["tracked_positions"]["open_count"], 2)
        self.assertEqual(second["tracked_positions"]["closed_count"], 1)


if __name__ == "__main__":
    unittest.main()
