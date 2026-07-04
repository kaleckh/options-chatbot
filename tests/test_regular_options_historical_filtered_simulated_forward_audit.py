from __future__ import annotations

import json
import tempfile
import unittest
import hashlib
from pathlib import Path

from scripts import build_regular_options_historical_filtered_simulated_forward_audit as filtered
from tests.test_regular_options_historical_profitability_filter_iteration import _row, _write_json, _write_jsonl


def _conditions_hash(conditions: list[dict]) -> str:
    payload = json.dumps(conditions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


def _contract() -> dict:
    conditions = [
        {"field": "ticker", "op": "in", "value": ["AAPL"]},
        {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
    ]
    return {
        "report_id": "regular_options_frozen_filtered_policy",
        "policy_id": "historical_filtered_candidate_policy_v1",
        "filter_id": "aapl_prior_10_contract",
        "description": "Frozen fixture filter.",
        "conditions": conditions,
        "conditions_sha256": _conditions_hash(conditions),
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }


class RegularOptionsHistoricalFilteredSimulatedForwardAuditTests(unittest.TestCase):
    def test_blocks_without_accepted_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            iteration = root / "iteration.json"
            _write_jsonl(selected, [_row("2026-01", "AAPL", 5.0), _row("2026-02", "AAPL", 6.0)])
            _write_json(iteration, {"report_id": "regular_options_historical_profitability_filter_iteration", "status": "blocked", "accepted_filters": []})

            report = filtered.build_report(
                selected_candidates_path=selected,
                filter_iteration_path=iteration,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_filtered_simulated_forward_audit")
        self.assertIn("accepted_filter_not_available", report["blockers"])
        self.assertFalse(report["accepted_historical_filtered_audit"])
        self.assertFalse(report["accepted_profitability"])

    def test_passes_for_accepted_train_selected_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            iteration = root / "iteration.json"
            rows = []
            for i in range(100):
                rows.append(_row("2026-01", "AAPL", 10.0, prior=12.0, day=(i % 20) + 1, direction=f"call_win_{i}"))
                rows.append(_row("2026-01", "MSFT", -10.0, prior=-1.0, day=(i % 20) + 1, direction=f"put_loss_{i}"))
            for i in range(20):
                rows.append(_row("2026-01", "AAPL", -1.0, prior=12.0, day=(i % 20) + 1, direction=f"put_small_loss_{i}"))
                rows.append(_row("2026-01", "MSFT", -10.0, prior=-1.0, day=(i % 20) + 1, direction=f"call_loss_{i}"))
            for i in range(35):
                rows.append(_row("2026-02", "AAPL", 12.0, prior=13.0, day=(i % 20) + 1, direction=f"call_win_{i}"))
                rows.append(_row("2026-02", "MSFT", -12.0, prior=-2.0, day=(i % 20) + 1, direction=f"put_loss_{i}"))
            for i in range(5):
                rows.append(_row("2026-02", "AAPL", -1.0, prior=13.0, day=(i % 20) + 1, direction=f"put_small_loss_{i}"))
                rows.append(_row("2026-02", "MSFT", -12.0, prior=-2.0, day=(i % 20) + 1, direction=f"call_loss_{i}"))
            _write_jsonl(selected, rows)
            _write_json(
                iteration,
                {
                    "report_id": "regular_options_historical_profitability_filter_iteration",
                    "status": "historical_profitability_filter_iteration_candidate_found",
                    "accepted_filters": [
                        {
                            "filter_id": "aapl_prior_10",
                            "description": "Fixture accepted filter.",
                            "conditions": [
                                {"field": "ticker", "op": "in", "value": ["AAPL"]},
                                {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
                            ],
                        }
                    ],
                },
            )

            report = filtered.build_report(
                selected_candidates_path=selected,
                filter_iteration_path=iteration,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_filtered_simulated_forward_audit_passed")
        self.assertTrue(report["accepted_historical_filtered_audit"])
        self.assertEqual(report["metrics"]["train"]["exact_trade_count"], 120)
        self.assertEqual(report["metrics"]["simulated_forward_audit"]["exact_trade_count"], 40)
        self.assertEqual(report["filtered_trade_history"]["duplicate_rows_removed"], 0)
        self.assertIn("bootstrap_iid", report["metrics"]["simulated_forward_audit"])
        self.assertIn("bootstrap_cluster", report["metrics"]["simulated_forward_audit"])
        self.assertGreater(report["metrics"]["simulated_forward_audit"]["bootstrap_cluster"]["pf_lb_5pct"], 1.0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["scanner_policy_changed"])
        self.assertIn("do_not_change_scanner_policy_from_filtered_historical_audit", report["prohibited_actions"])

    def test_uses_frozen_contract_when_iteration_selection_not_permitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            iteration = root / "iteration.json"
            contract = root / "contract.json"
            rows = []
            for i in range(100):
                rows.append(_row("2026-01", "AAPL", 10.0, prior=12.0, day=(i % 20) + 1, direction=f"call_win_{i}"))
            for i in range(20):
                rows.append(_row("2026-01", "AAPL", -1.0, prior=12.0, day=(i % 20) + 1, direction=f"put_small_loss_{i}"))
            for i in range(35):
                rows.append(_row("2026-02", "AAPL", 12.0, prior=13.0, day=(i % 20) + 1, direction=f"call_win_{i}"))
            for i in range(5):
                rows.append(_row("2026-02", "AAPL", -1.0, prior=13.0, day=(i % 20) + 1, direction=f"put_small_loss_{i}"))
            _write_jsonl(selected, rows)
            _write_json(
                iteration,
                {
                    "report_id": "regular_options_historical_profitability_filter_iteration",
                    "status": "blocked_audit_window_already_consumed_for_selection",
                    "selection_permitted": False,
                    "accepted_filters": [],
                },
            )
            _write_json(contract, _contract())

            report = filtered.build_report(
                selected_candidates_path=selected,
                filter_iteration_path=iteration,
                policy_contract_path=contract,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["filter_source"]["filter_source_mode"], "frozen_contract")
        self.assertEqual(report["filter_source"]["filter_id"], "aapl_prior_10_contract")
        self.assertEqual(report["metrics"]["train"]["exact_trade_count"], 120)
        self.assertEqual(report["metrics"]["simulated_forward_audit"]["exact_trade_count"], 40)

    def test_frozen_contract_fallback_blocks_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            iteration = root / "iteration.json"
            contract = root / "contract.json"
            rows = []
            for i in range(120):
                rows.append(_row("2026-01", "AAPL", 10.0, prior=12.0, day=(i % 20) + 1, direction=f"call_{i}"))
            for i in range(40):
                rows.append(_row("2026-02", "AAPL", 12.0, prior=13.0, day=(i % 20) + 1, direction=f"call_{i}"))
            bad_contract = _contract()
            bad_contract["conditions_sha256"] = "bad_hash_for_review_check"
            _write_jsonl(selected, rows)
            _write_json(
                iteration,
                {
                    "report_id": "regular_options_historical_profitability_filter_iteration",
                    "status": "blocked_audit_window_already_consumed_for_selection",
                    "selection_permitted": False,
                    "accepted_filters": [],
                },
            )
            _write_json(contract, bad_contract)

            report = filtered.build_report(
                selected_candidates_path=selected,
                filter_iteration_path=iteration,
                policy_contract_path=contract,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["filter_source"]["filter_source_mode"], "frozen_contract")
        self.assertEqual(report["status"], "blocked_historical_filtered_simulated_forward_audit")
        self.assertIn("frozen_contract_filter_hash_mismatch", report["blockers"])

    def test_write_outputs_creates_latest_and_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {
                "report_id": filtered.REPORT_ID,
                "status": "historical_filtered_simulated_forward_audit_passed",
                "accepted_historical_filtered_audit": True,
                "accepted_profitability": False,
                "filter_source": {"filter_id": "fixture", "conditions": []},
                "requested_split": {"bootstrap_draws": 100},
                "metrics": {
                    "train": {"exact_trade_count": 1, "avg_pnl_pct": 1.0, "profit_factor": None, "bootstrap_cluster": {"pf_lb_5pct": None, "statistical_confidence": "negative_or_flat"}},
                    "simulated_forward_audit": {"exact_trade_count": 1, "avg_pnl_pct": 1.0, "profit_factor": None, "bootstrap_cluster": {"pf_lb_5pct": None, "statistical_confidence": "negative_or_flat"}},
                },
                "blockers": [],
            }
            artifacts = filtered.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["latest_json"].replace("\\", "/").endswith("/out/latest.json"))


if __name__ == "__main__":
    unittest.main()
