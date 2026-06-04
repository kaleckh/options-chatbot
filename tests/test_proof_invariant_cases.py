from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import proof_contract as proof_contract  # noqa: E402
from backend_route_context import BackendRouteContext  # noqa: E402
from options_profit_flywheel import _candidate_position_metrics  # noqa: E402
from options_profit_gate import _realized_position_metrics  # noqa: E402
from proof_summary_service import build_proof_summary  # noqa: E402


MANIFEST_PATH = ROOT / "data" / "contracts" / "proof-invariant-cases.json"


class _ProofSummaryRepository:
    is_available = True
    error_message = None

    def __init__(self, closed_rows: list[dict]):
        self._closed_rows = list(closed_rows)

    def list_positions(self, status="open", *args, **kwargs):
        if status == "closed":
            return list(self._closed_rows)
        return []


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _is_closed_fixture(row: dict) -> bool:
    return str(row.get("status") or "").strip().lower() == "closed" or bool(row.get("closed_at"))


class ProofInvariantCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = _load_manifest()
        cls.cases = list(cls.manifest["cases"])

    def test_manifest_is_test_only_and_has_unique_cases(self):
        self.assertEqual(self.manifest["artifact"], "proof_invariant_cases")
        self.assertEqual(self.manifest["version"], 1)
        self.assertIs(self.manifest["runtime_use"], False)
        self.assertIn("proof_contract.py", self.manifest["scope"])
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)

    def test_backend_proof_invariant_table_matches_predicates(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                row = copy.deepcopy(case["row"])
                expected = case["expected"]["backend"]

                self.assertEqual(
                    proof_contract.row_has_raw_exact_contract(row),
                    expected["raw_exact_contract"],
                )
                self.assertEqual(
                    proof_contract.row_has_research_backfill_marker(row),
                    expected["research_backfill_marker"],
                )
                self.assertEqual(
                    proof_contract.row_has_live_exact_selection_source(row),
                    expected["live_exact_selection_source"],
                )
                self.assertEqual(
                    proof_contract.row_has_verified_live_scan_lineage(row),
                    expected["verified_live_scan_lineage"],
                )
                self.assertEqual(
                    proof_contract.row_has_trusted_opra_source(row),
                    expected["trusted_opra_source"],
                )
                self.assertEqual(
                    proof_contract.row_has_executable_entry(row),
                    expected["executable_entry"],
                )
                self.assertEqual(
                    proof_contract.row_has_trusted_executable_exit(row),
                    expected["trusted_executable_exit"],
                )
                self.assertEqual(
                    proof_contract.row_has_calculable_realized_pnl(row),
                    expected["calculable_realized_pnl"],
                )
                self.assertEqual(
                    proof_contract.row_counts_as_production_proof(row),
                    expected["production_proof"],
                )
                self.assertEqual(
                    proof_contract.row_counts_as_proof_grade_exact_closed(row),
                    expected["proof_grade_exact_closed"],
                )

    def test_proof_summary_and_profit_metrics_use_proof_grade_closed_cases(self):
        closed_rows = [copy.deepcopy(case["row"]) for case in self.cases if _is_closed_fixture(case["row"])]
        expected_raw_exact = sum(
            1
            for case in self.cases
            if _is_closed_fixture(case["row"]) and case["expected"]["backend"]["raw_exact_contract"]
        )
        expected_proof_grade = sum(
            1
            for case in self.cases
            if _is_closed_fixture(case["row"]) and case["expected"]["backend"]["proof_grade_exact_closed"]
        )

        summary = build_proof_summary(
            BackendRouteContext(
                {
                    "POSITIONS_REPOSITORY": _ProofSummaryRepository(closed_rows),
                    "evaluate_measurement_gate": lambda: {"state": "blocked", "blockers": []},
                    "evaluate_claim_readiness": lambda: {
                        "state": "blocked",
                        "claim_ready": False,
                        "blocker_count": 0,
                        "blockers": [],
                        "tracked_realized_metrics": {},
                    },
                    "_cached_forward_evidence_report": lambda: {"ledger_summary": {}},
                    "_row_has_raw_exact_contract": proof_contract.row_has_raw_exact_contract,
                    "_row_counts_as_proof_grade_exact_closed": proof_contract.row_counts_as_proof_grade_exact_closed,
                }
            )
        )
        tracked = summary["tracked_positions"]

        self.assertEqual(tracked["closed_count"], len(closed_rows))
        self.assertEqual(tracked["raw_exact_contract_closed_count"], expected_raw_exact)
        self.assertEqual(tracked["proof_grade_exact_contract_closed_count"], expected_proof_grade)
        self.assertEqual(tracked["exact_contract_closed_count"], expected_proof_grade)

        realized_metrics = _realized_position_metrics(closed_rows)
        self.assertEqual(realized_metrics["closed_position_count"], expected_proof_grade)
        self.assertEqual(realized_metrics["exact_contract_closed_count"], expected_proof_grade)
        self.assertEqual(
            realized_metrics["non_proof_closed_position_count"],
            len(closed_rows) - expected_proof_grade,
        )

        candidate_metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "proof-invariant-case",
            closed_rows,
        )
        self.assertEqual(candidate_metrics["closed_position_count"], expected_proof_grade)
        self.assertEqual(candidate_metrics["exact_outcome_count"], expected_proof_grade)


if __name__ == "__main__":
    unittest.main()
