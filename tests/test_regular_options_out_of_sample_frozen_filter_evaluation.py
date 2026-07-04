from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_out_of_sample_frozen_filter_evaluation as evaluation


def _conditions_hash(conditions: list[dict]) -> str:
    return hashlib.sha256(json.dumps(conditions, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


class OutOfSampleFrozenFilterEvaluationTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
        return path

    def _write_jsonl(self, path: Path, rows: list[dict]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf8")
        return path

    def _contract(self, *, tamper_hash: bool = False) -> dict:
        conditions = [
            {"field": "ticker", "op": "in", "value": ["SPY", "QQQ"]},
            {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
        ]
        return {
            "contract_id": "regular_options_out_of_sample_extension_v1",
            "target_window": {
                "requested_start_month": "2022-01",
                "requested_end_month": "2022-02",
                "requested_start_date": "2022-01-01",
                "requested_end_date": "2022-02-28",
            },
            "frozen_policy": {
                "policy_id": "historical_filtered_candidate_policy_v1",
                "filter_id": "frozen_test_filter",
                "conditions": conditions,
                "conditions_sha256": "bad" if tamper_hash else _conditions_hash(conditions),
            },
            "gates": {
                "bootstrap_draws": 10,
                "percent_cluster_pf_lb_5pct_must_be_gt": 1.0,
                "usd_cluster_pf_lb_5pct_must_be_gt": 1.0,
                "total_net_pnl_usd_must_be_gt": 0.0,
            },
            "interpretation": {
                "failure_verdict": "park_filter_hypothesis_tracker_may_continue",
                "passing_verdict": "historically_consistent_still_awaiting_forward_bar",
            },
        }

    def _row(self, entry_date: str, ticker: str, prior_return: float, pnl: float = 10.0, usd: float = 100.0) -> dict:
        return {
            "entry_date": entry_date,
            "ticker": ticker,
            "direction": "bullish_call_vertical",
            "exact_priced": True,
            "proof_grade": "trusted_intraday_opra_nbbo",
            "fill_basis": "imported_spread_mark",
            "pnl_pct": pnl,
            "net_pnl_usd": usd,
            "signal_evidence": {"prior_20_trading_day_return_pct": prior_return},
        }

    def test_hash_gate_blocks_mismatched_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write_json(root / "contract.json", self._contract(tamper_hash=True))
            materializer = self._write_json(root / "materializer.json", {"calendar_coverage": {"covered_months": ["2022-01"]}})
            selected = self._write_jsonl(root / "selected.jsonl", [self._row("2022-01-10", "SPY", 12.0)])
            registry = self._write_json(root / "registry.json", {"entries": []})

            report = evaluation.build_report(
                selected_candidates_path=selected,
                materializer_report_path=materializer,
                contract_path=contract,
                consumption_registry_path=registry,
                record_consumption=False,
            )

        self.assertIn("frozen_policy_conditions_sha256_mismatch", report["blockers"])
        self.assertFalse(report["frozen_policy"]["hash_verified"])

    def test_month_scoping_uses_only_contract_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write_json(root / "contract.json", self._contract())
            materializer = self._write_json(root / "materializer.json", {"calendar_coverage": {"covered_months": ["2022-01", "2022-02", "2022-03"]}})
            selected = self._write_jsonl(
                root / "selected.jsonl",
                [
                    self._row("2022-01-10", "SPY", 12.0),
                    self._row("2022-02-10", "QQQ", 14.0),
                    self._row("2022-03-10", "SPY", 99.0),
                ],
            )
            registry = self._write_json(root / "registry.json", {"entries": []})

            report = evaluation.build_report(
                selected_candidates_path=selected,
                materializer_report_path=materializer,
                contract_path=contract,
                consumption_registry_path=registry,
                record_consumption=False,
            )

        self.assertEqual(report["row_counts"]["in_requested_window_rows"], 2)
        self.assertEqual(report["row_counts"]["rows_for_frozen_policy_evaluation"], 2)
        self.assertEqual(report["row_counts"]["frozen_filter_exact_rows"], 2)
        self.assertNotIn("2022-03", report["coverage_summaries"]["rows_for_evaluation"]["by_month"])

    def test_registry_append_consumed_for_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write_json(root / "contract.json", self._contract())
            materializer = self._write_json(root / "materializer.json", {"calendar_coverage": {"covered_months": ["2022-01", "2022-02"]}})
            selected = self._write_jsonl(root / "selected.jsonl", [self._row("2022-01-10", "SPY", 12.0)])
            registry = self._write_json(root / "registry.json", {"entries": []})

            report = evaluation.build_report(
                selected_candidates_path=selected,
                materializer_report_path=materializer,
                contract_path=contract,
                consumption_registry_path=registry,
                record_consumption=True,
            )
            payload = json.loads(registry.read_text(encoding="utf8"))

        self.assertTrue(report["registry_appended"])
        self.assertEqual(payload["entries"][0]["disposition"], "consumed_for_evaluation")
        self.assertFalse(payload["entries"][0]["selection_permitted"])
        self.assertEqual(payload["entries"][0]["window_months"], ["2022-01", "2022-02"])

    def test_partial_months_are_excluded_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write_json(root / "contract.json", self._contract())
            materializer = self._write_json(root / "materializer.json", {"calendar_coverage": {"covered_months": ["2022-02"]}})
            selected = self._write_jsonl(
                root / "selected.jsonl",
                [
                    self._row("2022-01-10", "SPY", 12.0),
                    self._row("2022-02-10", "QQQ", 14.0),
                ],
            )
            registry = self._write_json(root / "registry.json", {"entries": []})

            report = evaluation.build_report(
                selected_candidates_path=selected,
                materializer_report_path=materializer,
                contract_path=contract,
                consumption_registry_path=registry,
                record_consumption=False,
            )

        self.assertEqual(report["evaluation_window"]["evaluated_full_months"], ["2022-02"])
        self.assertEqual(report["evaluation_window"]["excluded_or_missing_months"], ["2022-01"])
        self.assertEqual(report["row_counts"]["excluded_rows_from_missing_or_partial_months"], 1)
        self.assertEqual(report["row_counts"]["rows_for_frozen_policy_evaluation"], 1)


if __name__ == "__main__":
    unittest.main()
