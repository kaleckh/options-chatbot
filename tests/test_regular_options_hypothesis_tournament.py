from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_hypothesis_tournament as tournament


NOW = "2026-06-18T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _candidate(**overrides) -> dict:
    row = {
        "candidate_id": "candidate_good",
        "lane_id": "candidate_good",
        "strategy_family": "unit_test",
        "rule_summary": "simple exact executable candidate",
        "source_decision": "robust_candidate_for_forward_freeze",
        "total_exact_rows": 220,
        "priced_rows": 220,
        "unpriced_rows": 0,
        "train_rows": 150,
        "validation_rows": 40,
        "holdout_rows": 30,
        "profit_factor": 1.5,
        "profit_factor_lower_bound": 1.2,
        "avg_net_pnl_pct": 8.0,
        "median_net_pnl_pct": 3.0,
        "win_rate_pct": 55.0,
        "execution_evidence_class": "trusted_intraday_opra_nbbo",
        "source_quality_status": "source_quality_gate_passed",
        "stress_results": {
            "top_1_removed_profit_factor": 1.2,
            "top_3_removed_profit_factor": 1.1,
            "wider_spread_profit_factor": 1.05,
        },
        "ticker_concentration": {"status": "available", "top_ticker_profit_share_pct": 20.0},
        "month_concentration": {"status": "available", "top_month_profit_share_pct": 25.0, "month_count": 5},
        "reason_codes": [],
    }
    row.update(overrides)
    return row


def _paper_candidate(**overrides) -> dict:
    row = {
        "candidate_id": "lane:volatility_expansion_observation",
        "lane_id": "volatility_expansion_observation",
        "strategy_family": "monthly_lane_gate",
        "rule_summary": "current paper-shadow lane",
        "source_decision": "paper_shadow_candidate",
        "total_exact_rows": 24,
        "priced_rows": 24,
        "unpriced_rows": 0,
        "holdout_rows": 0,
        "profit_factor": 1.83,
        "avg_net_pnl_pct": 6.74,
        "execution_evidence_class": "trusted_intraday_opra_nbbo",
        "reason_codes": ["paper_shadow_or_probation_only"],
    }
    row.update(overrides)
    return row


def _base_payloads(generated_at: str = NOW) -> dict[str, dict]:
    return {
        "robust_edge": {
            "generated_at_utc": generated_at,
            "overall_status": "paper_shadow_only",
            "existing_promotion_ready": False,
            "candidate_rankings": [_paper_candidate()],
            "prohibited_actions": ["do_not_create_trades_from_robust_edge_discovery"],
            "data_coverage_summary": {"source_quality_gate_status": "source_quality_gate_passed"},
        },
        "robust_search": {
            "generated_at_utc": generated_at,
            "status": "historical_candidates_blocked",
            "summary": {
                "accepted_exact_trade_count": 220,
                "ready_candidate_count": 0,
                "selection_adjusted_bar": 1.1,
                "source_quality_gate_status": "source_quality_gate_passed",
            },
            "split_policy": {"split_unit": "unique_entry_date"},
            "prohibited_actions": [],
        },
        "historical_walk_forward": {
            "generated_at_utc": generated_at,
            "status": "historical_walkforward_ran_candidates_blocked",
            "summary": {
                "promotion_ready": False,
                "latest_candidate_entry_date": "2026-03-24",
                "protected_forward_holdout_start_date": "2026-06-05",
                "protected_forward_holdout_overlap": False,
                "forward_holdout_guard_status": "passed",
            },
            "prohibited_actions": [],
        },
        "feature_store": {
            "generated_at_utc": generated_at,
            "status": "feature_store_built",
            "inputs": {"source_label": "thetadata_opra_nbbo_1m", "snapshot_kind": "intraday", "data_trust": "trusted"},
            "summary": {
                "shared_quote_date_count": 505,
                "first_shared_quote_date_et": "2024-05-22",
                "latest_shared_quote_date_et": "2026-06-04",
            },
        },
        "monthly_profitability": {
            "generated_at_utc": generated_at,
            "summary": {"baseline_profit_factor": 0.32, "baseline_avg_net_pnl_pct": -16.54},
            "prohibited_actions": [],
        },
        "missed_filter_matrix": {
            "generated_at_utc": generated_at,
            "ranked_scenarios_by_kept_profit_factor": [],
        },
        "missed_failures": {
            "generated_at_utc": generated_at,
            "guardrail_candidates": {},
        },
        "lane_promotion_state": {
            "generated_at_utc": generated_at,
            "summary": {"live_validation_lane_count": 0},
        },
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _base_payloads()
    paths = {
        "robust_edge_path": root / "robust-edge.json",
        "robust_search_path": root / "robust-search.json",
        "walk_forward_path": root / "walk.json",
        "feature_store_path": root / "feature.json",
        "monthly_audit_path": root / "monthly.json",
        "missed_filter_matrix_path": root / "filter.json",
        "missed_failures_path": root / "failures.json",
        "lane_promotion_path": root / "lane-promotion.json",
    }
    key_map = {
        "robust_edge_path": "robust_edge",
        "robust_search_path": "robust_search",
        "walk_forward_path": "historical_walk_forward",
        "feature_store_path": "feature_store",
        "monthly_audit_path": "monthly_profitability",
        "missed_filter_matrix_path": "missed_filter_matrix",
        "missed_failures_path": "missed_failures",
        "lane_promotion_path": "lane_promotion_state",
    }
    for arg_name, path in paths.items():
        key = key_map[arg_name]
        if key in payloads:
            _write_json(path, payloads[key])
    return paths


class RegularOptionsHypothesisTournamentTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **overrides):
        paths = _write_sources(root, payloads)
        paths.update(overrides)
        return tournament.build_report(generated_at_utc=NOW, **paths)

    def test_missing_required_artifacts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads.pop("robust_edge")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["robust_edge_discovery"]["status"], "missing")

    def test_malformed_json_fails_closed_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["robust_edge_path"].write_text("{bad", encoding="utf8")
            report = tournament.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["robust_edge_discovery"]["status"], "malformed")

    def test_positive_pf_but_fewer_than_30_holdout_rows_is_not_forward_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [_candidate(holdout_rows=20)]
            report = self._build(Path(temp_dir), payloads)

        row = report["candidate_rankings"][0]
        self.assertEqual(row["decision"], "insufficient_holdout_reject")
        self.assertEqual(report["forward_freeze_candidate_count"], 0)

    def test_unpriced_proof_rows_are_repair_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [_candidate(unpriced_rows=2)]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["candidate_rankings"][0]["decision"], "repair_needed")

    def test_midpoint_or_stale_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [_candidate(execution_evidence_class="midpoint")]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["candidate_rankings"][0]["decision"], "execution_fragile_reject")

    def test_ticker_concentrated_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [
                _candidate(ticker_concentration={"status": "available", "top_ticker_profit_share_pct": 80.0})
            ]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["candidate_rankings"][0]["decision"], "ticker_concentrated_reject")

    def test_month_concentrated_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [
                _candidate(month_concentration={"status": "available", "top_month_profit_share_pct": 70.0, "month_count": 5})
            ]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["candidate_rankings"][0]["decision"], "month_concentrated_reject")

    def test_top_winner_stress_failure_is_overfit_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [
                _candidate(stress_results={"top_1_removed_profit_factor": 0.8})
            ]
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["candidate_rankings"][0]["decision"], "overfit_reject")

    def test_volatility_expansion_remains_paper_shadow_unless_all_gates_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        row = report["candidate_rankings"][0]
        self.assertEqual(row["candidate_id"], "lane:volatility_expansion_observation")
        self.assertEqual(row["decision"], "paper_shadow_candidate")

    def test_existing_promotion_ready_false_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["existing_promotion_ready"])
        self.assertFalse(report["live_entry_allowed"])

    def test_no_candidate_passing_gates_returns_paper_shadow_or_no_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertIn(report["overall_status"], {"paper_shadow_only", "no_candidate_survived"})
        self.assertEqual(report["forward_freeze_candidate_count"], 0)

    def test_search_budget_is_recorded_and_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [
                _candidate(candidate_id=f"candidate_{i}", lane_id=f"candidate_{i}") for i in range(5)
            ]
            report = self._build(Path(temp_dir), payloads, max_variants=2)

        self.assertEqual(report["search_budget"]["max_variants"], 2)
        self.assertTrue(report["search_budget"]["budget_enforced"])
        self.assertEqual(report["variants_tested"], 2)

    def test_never_outputs_trading_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_edge"]["candidate_rankings"] = [_candidate()]
            report = self._build(Path(temp_dir), payloads)

        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])


if __name__ == "__main__":
    unittest.main()
