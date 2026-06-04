from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, TESTS_DIR, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import proof_contract  # noqa: E402
import replay_profit_service  # noqa: E402
from backend_route_context import BackendRouteContext  # noqa: E402
from options_algorithm_fixtures import load_backend_main  # noqa: E402
from options_profit_flywheel import _candidate_position_metrics  # noqa: E402
from options_profit_gate import _realized_position_metrics  # noqa: E402
from proof_summary_service import build_proof_summary  # noqa: E402


INVARIANT_PATH = ROOT / "data" / "contracts" / "proof-invariant-cases.json"
GOLDEN_PATH = ROOT / "data" / "contracts" / "proof-replay-golden-readbacks.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_closed(row: dict) -> bool:
    return str(row.get("status") or "").strip().lower() == "closed" or bool(row.get("closed_at"))


class _GoldenReadbackRepository:
    is_available = True
    error_message = None

    def __init__(self, rows: list[dict]):
        self.open_rows = [copy.deepcopy(row) for row in rows if not _is_closed(row)]
        self.closed_rows = [copy.deepcopy(row) for row in rows if _is_closed(row)]

    def list_positions(self, status="open", *args, **kwargs):
        if status == "open":
            return copy.deepcopy(self.open_rows)
        if status == "closed":
            return copy.deepcopy(self.closed_rows)
        return []

    def profit_status_snapshot(self):
        return {
            "open_position_count": len(self.open_rows),
            "total_closed_position_count": len(self.closed_rows),
            "closed_positions": copy.deepcopy(self.closed_rows),
        }


def _proof_summary_context(repository: _GoldenReadbackRepository) -> BackendRouteContext:
    return BackendRouteContext(
        {
            "POSITIONS_REPOSITORY": repository,
            "evaluate_measurement_gate": lambda: {"state": "blocked", "blockers": []},
            "evaluate_claim_readiness": lambda: {
                "state": "blocked",
                "claim_ready": False,
                "blocker_count": 0,
                "blockers": [],
                "eligible_event_count": 0,
                "pending_truth_event_count": 0,
                "by_symbol": {},
                "tracked_realized_metrics": {},
            },
            "_cached_forward_evidence_report": lambda: {"ledger_summary": {}},
            "_row_has_raw_exact_contract": proof_contract.row_has_raw_exact_contract,
            "_row_counts_as_proof_grade_exact_closed": (
                proof_contract.row_counts_as_proof_grade_exact_closed
            ),
        }
    )


class GoldenProofReplayReadbacksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.invariant = _load_json(INVARIANT_PATH)
        cls.golden = _load_json(GOLDEN_PATH)
        cls.cases = list(cls.invariant["cases"])
        cls.rows = [copy.deepcopy(case["row"]) for case in cls.cases]
        cls.open_rows = [copy.deepcopy(row) for row in cls.rows if not _is_closed(row)]
        cls.closed_rows = [copy.deepcopy(row) for row in cls.rows if _is_closed(row)]

    def test_golden_contract_is_test_only_and_references_invariant_cases(self):
        self.assertEqual(self.golden["artifact"], "proof_replay_golden_readbacks")
        self.assertEqual(self.golden["version"], 1)
        self.assertIs(self.golden["runtime_use"], False)
        self.assertEqual(
            self.golden["source_manifest"],
            "data/contracts/proof-invariant-cases.json",
        )
        self.assertIn("Does not run WFO replay", " ".join(self.golden["non_goals"]))

        invariant_ids = [case["id"] for case in self.cases]
        self.assertEqual(self.golden["case_ids"], invariant_ids)

    def test_golden_proof_counts_and_summary_readbacks_stay_fixed(self):
        actual_counts = {
            "total_cases": len(self.rows),
            "open_rows": len(self.open_rows),
            "closed_rows": len(self.closed_rows),
            "raw_exact_contract_closed_count": sum(
                1
                for row in self.closed_rows
                if proof_contract.row_has_raw_exact_contract(copy.deepcopy(row))
            ),
            "production_proof_rows": sum(
                1
                for row in self.rows
                if proof_contract.row_counts_as_production_proof(copy.deepcopy(row))
            ),
            "open_production_proof_rows": sum(
                1
                for row in self.open_rows
                if proof_contract.row_counts_as_production_proof(copy.deepcopy(row))
            ),
            "closed_production_proof_rows": sum(
                1
                for row in self.closed_rows
                if proof_contract.row_counts_as_production_proof(copy.deepcopy(row))
            ),
            "proof_grade_exact_contract_closed_count": sum(
                1
                for row in self.closed_rows
                if proof_contract.row_counts_as_proof_grade_exact_closed(copy.deepcopy(row))
            ),
            "non_proof_closed_position_count": sum(
                1
                for row in self.closed_rows
                if not proof_contract.row_counts_as_proof_grade_exact_closed(copy.deepcopy(row))
            ),
        }
        self.assertEqual(actual_counts, self.golden["proof_case_counts"])

        repository = _GoldenReadbackRepository(self.rows)
        summary = build_proof_summary(_proof_summary_context(repository))
        self.assertEqual(
            summary["tracked_positions"],
            self.golden["proof_summary_tracked_positions"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backend = load_backend_main(str(Path(tmpdir) / "chat_history.db"))
            grouped = backend._group_rows_by_status(copy.deepcopy(self.rows))

        self.assertEqual(
            grouped["summary"],
            self.golden["grouped_trading_desk_summary"],
        )

    def test_golden_options_profit_and_status_overlay_counts_only_proof_grade_rows(self):
        realized_metrics = _realized_position_metrics(copy.deepcopy(self.closed_rows))
        self.assertEqual(
            realized_metrics,
            self.golden["options_profit_realized_metrics"],
        )

        candidate = self.golden["candidate_metrics"]
        candidate_metrics = _candidate_position_metrics(
            candidate["symbol"],
            candidate["direction"],
            candidate["candidate_id"],
            copy.deepcopy(self.closed_rows),
        )
        self.assertEqual(candidate_metrics, candidate["expected"])

        repository = _GoldenReadbackRepository(self.rows)
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = load_backend_main(str(Path(tmpdir) / "chat_history.db"))
            with patch.object(backend, "POSITIONS_REPOSITORY", repository):
                health = backend._current_tracked_positions_health_check(
                    {
                        "required_closed_position_count": 1,
                        "required_net_profit_factor": 1.05,
                        "required_avg_net_pnl_pct_gt": 0,
                    }
                )

        expected_overlay = self.golden["options_profit_status_overlay"]
        self.assertEqual(
            {key: health.get(key) for key in expected_overlay},
            expected_overlay,
        )

    def test_golden_replay_service_readbacks_are_deterministic_and_offline(self):
        replay_contract = self.golden["replay_service"]
        truth_lane = replay_contract["truth_lane"]
        min_trades = int(replay_contract["min_trades"])
        bucket_size = int(replay_contract["bucket_size"])

        no_result_ctx = BackendRouteContext(
            {"_cached_preferred_results_by_truth_lane": lambda _truth_lane: None}
        )
        self.assertEqual(
            replay_profit_service.build_metric_truth_report(
                no_result_ctx,
                truth_lane,
                min_trades,
                bucket_size,
            ),
            replay_contract["no_result_metric_truth"],
        )

        calls: list[tuple] = []
        replay_result = {
            "run_at": "2026-06-04T14:00:00Z",
            "total_trades": 12,
            "truth_lane": truth_lane,
        }

        def _cached_readonly_report(key: tuple, builder):
            calls.append(key)
            return builder()

        ctx = BackendRouteContext(
            {
                "_preferred_results_cache_key": lambda lane: ("preferred", str(lane or "default")),
                "_cached_readonly_report": _cached_readonly_report,
                "_cached_preferred_results_by_truth_lane": lambda lane: {
                    **replay_result,
                    "truth_lane": lane,
                },
                "_cached_last_results_by_truth_lane": lambda lane: {
                    "run_at": replay_result["run_at"],
                    "truth_lane": lane,
                },
                "build_prediction_replay_report": lambda *, result, min_trades: {
                    "kind": "report",
                    "truth_lane": result["truth_lane"],
                    "min_trades": min_trades,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_metric_truth_report": lambda *, result, min_trades, bucket_size: {
                    "kind": "metric",
                    "truth_lane": result["truth_lane"],
                    "min_trades": min_trades,
                    "bucket_size": bucket_size,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_options_profitability_forensics": lambda *, result, min_trades: {
                    "kind": "forensics",
                    "truth_lane": result["truth_lane"],
                    "min_trades": min_trades,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_truth_lane_comparison": lambda *, truth_lane: {
                    "kind": "comparison",
                    "truth_lane": truth_lane,
                },
            }
        )

        summary = replay_profit_service.build_backtest_summary(
            ctx,
            truth_lane,
            min_trades,
            bucket_size,
        )

        self.assertEqual(list(summary), replay_contract["summary_keys"])
        self.assertEqual([call[0] for call in calls], replay_contract["cache_key_prefixes"])
        self.assertEqual(summary["last"]["truth_lane"], truth_lane)
        self.assertEqual(summary["report"]["min_trades"], min_trades)
        self.assertEqual(summary["report"]["truth_lane"], truth_lane)
        self.assertEqual(summary["metricTruth"]["min_trades"], min_trades)
        self.assertEqual(summary["metricTruth"]["bucket_size"], bucket_size)
        self.assertEqual(summary["metricTruth"]["truth_lane"], truth_lane)
        self.assertEqual(summary["profitabilityForensics"]["min_trades"], min_trades)
        self.assertEqual(summary["profitabilityForensics"]["truth_lane"], truth_lane)
        self.assertEqual(summary["comparison"]["truth_lane"], truth_lane)


if __name__ == "__main__":
    unittest.main()
