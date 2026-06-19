from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_robust_edge_discovery as discovery


NOW = "2026-06-17T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _split(total: int = 220, train: int = 150, validation: int = 40, holdout: int = 30, pf: float = 1.5, pf_lb: float = 1.2) -> dict:
    return {
        "combined": {
            "exact_trade_count": total,
            "profit_factor": pf,
            "avg_pnl_pct": 8.0,
            "median_pnl_pct": 3.0,
            "win_rate_pct": 55.0,
            "first_entry_date": "2025-01-01",
            "latest_entry_date": "2026-03-24",
            "risk": {"max_drawdown_pct_points": 25.0, "deep_loss_counts": {"lte_minus_80": 0}},
        },
        "train": {"exact_trade_count": train},
        "validation": {"exact_trade_count": validation, "profit_factor": 1.4},
        "final_holdout": {
            "exact_trade_count": holdout,
            "profit_factor": pf,
            "avg_pnl_pct": 6.0,
            "bootstrap": {"pf_lb_5pct": pf_lb, "statistical_confidence": "confident_positive"},
        },
    }


def _candidate(**overrides) -> dict:
    candidate = {
        "candidate_id": "candidate_good",
        "candidate_type": "combined",
        "historical_nomination_ready": True,
        "split_metrics": _split(),
        "blockers": [],
        "source_quality_gate": {"status": "source_quality_gate_passed", "passed": True, "blockers": []},
        "feature_store_gate": {"status": "feature_store_gate_passed", "passed": True},
        "regime_check": {"status": "regime_robust_passed", "regime_robust": True},
        "execution_evidence_class": "trusted_intraday_opra_nbbo",
        "stress_results": {
            "top_1_removed_profit_factor": 1.2,
            "top_3_removed_profit_factor": 1.1,
            "wider_spread_profit_factor": 1.05,
        },
    }
    candidate.update(overrides)
    return candidate


def _base_payloads(generated_at: str = NOW) -> dict[str, dict]:
    return {
        "robust_search": {
            "generated_at_utc": generated_at,
            "status": "historical_candidates_blocked",
            "summary": {
                "accepted_exact_trade_count": 220,
                "candidate_count": 1,
                "ready_candidate_count": 0,
                "promotion_ready": False,
                "source_quality_gate_status": "source_quality_gate_passed",
                "selection_adjusted_bar": 1.1,
                "variants_searched": 1,
            },
            "split_policy": {},
            "proof_policy": {"historical_use": "nominate only"},
            "candidates": [_candidate(split_metrics=_split(holdout=20), historical_nomination_ready=False)],
        },
        "historical_walk_forward": {
            "generated_at_utc": generated_at,
            "status": "historical_walkforward_ran_candidates_blocked",
            "summary": {
                "promotion_ready": False,
                "ready_candidate_count": 0,
                "latest_candidate_entry_date": "2026-03-24",
                "protected_forward_holdout_start_date": "2026-06-05",
                "protected_forward_holdout_overlap": False,
                "forward_holdout_guard_status": "passed",
            },
            "proof_policy": {"fresh_forward_requirement": "fresh exact realized pnl"},
            "variant_rows": [],
            "repair_queue": [],
        },
        "feature_store": {
            "generated_at_utc": generated_at,
            "status": "feature_store_built",
            "inputs": {"source_label": "thetadata_opra_nbbo_1m", "snapshot_kind": "intraday", "data_trust": "trusted"},
            "summary": {
                "shared_quote_date_count": 505,
                "shared_quote_date_start": "2024-05-22",
                "shared_quote_date_end": "2026-06-04",
                "quote_row_count": 1000,
            },
        },
        "monthly_profitability": {
            "generated_at_utc": generated_at,
            "summary": {"baseline_profit_factor": 0.3, "baseline_avg_net_pnl_pct": -10.0},
            "lane_leaderboard": [
                {
                    "lane": "volatility_expansion_observation",
                    "rows": 24,
                    "priced": 24,
                    "profit_factor": 1.83,
                    "avg_net_pnl_pct": 6.74,
                    "sum_net_pnl_usd": 971.3,
                }
            ],
        },
        "trade_qualification": {
            "generated_at_utc": generated_at,
            "overall_status": "blocked_no_live_release",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "lane_decisions": [
                {
                    "lane_id": "volatility_expansion_observation",
                    "decision": "paper_shadow_collect",
                    "priced_rows": 24,
                    "profit_factor": 1.83,
                    "avg_net_pnl_pct": 6.74,
                    "median_net_pnl_pct": 2.15,
                    "win_rate_pct": 50.0,
                    "reason_codes": ["no_exact_realized_pnl_rows"],
                }
            ],
        },
        "paper_shadow_evidence_plan": {
            "generated_at_utc": generated_at,
            "overall_status": "paper_shadow_evidence_collecting",
        },
        "market_window_evidence_checklist": {
            "generated_at_utc": generated_at,
            "overall_status": "waiting_for_market_window",
        },
        "lane_promotion_state": {
            "generated_at_utc": generated_at,
            "summary": {"promotion_ready_count": 0},
        },
        "missed_filter_matrix": {"generated_at_utc": generated_at, "ranked_scenarios_by_kept_profit_factor": []},
        "missed_outcomes": {"generated_at_utc": generated_at},
        "missed_failures": {"generated_at_utc": generated_at},
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _base_payloads()
    paths = {
        "robust_search_path": root / "robust.json",
        "walk_forward_path": root / "walk.json",
        "feature_store_path": root / "feature.json",
        "monthly_audit_path": root / "monthly.json",
        "trade_qualification_path": root / "triage.json",
        "paper_shadow_plan_path": root / "paper.json",
        "market_window_checklist_path": root / "checklist.json",
        "lane_promotion_path": root / "lane-promotion.json",
        "missed_filter_matrix_path": root / "missed-filter.json",
        "missed_outcomes_path": root / "missed-outcomes.json",
        "missed_failures_path": root / "missed-failures.json",
    }
    key_map = {
        "robust_search_path": "robust_search",
        "walk_forward_path": "historical_walk_forward",
        "feature_store_path": "feature_store",
        "monthly_audit_path": "monthly_profitability",
        "trade_qualification_path": "trade_qualification",
        "paper_shadow_plan_path": "paper_shadow_evidence_plan",
        "market_window_checklist_path": "market_window_evidence_checklist",
        "lane_promotion_path": "lane_promotion_state",
        "missed_filter_matrix_path": "missed_filter_matrix",
        "missed_outcomes_path": "missed_outcomes",
        "missed_failures_path": "missed_failures",
    }
    for arg_name, path in paths.items():
        key = key_map[arg_name]
        if key in payloads:
            _write_json(path, payloads[key])
    return paths


class RegularOptionsRobustEdgeDiscoveryTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **overrides):
        paths = _write_sources(root, payloads)
        paths.update(overrides)
        return discovery.build_report(generated_at_utc=NOW, **paths)

    def test_missing_required_artifacts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads.pop("robust_search")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["robust_search"]["status"], "missing")

    def test_malformed_json_fails_closed_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["robust_search_path"].write_text("{bad", encoding="utf8")
            report = discovery.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["robust_search"]["status"], "malformed")

    def test_positive_pf_below_30_holdout_is_thin_sample_not_robust(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "thin_sample_watch")
        self.assertEqual(report["robust_candidate_count"], 0)

    def test_midpoint_or_stale_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_search"]["candidates"] = [_candidate(execution_evidence_class="midpoint")]
            report = self._build(Path(temp_dir), payloads)

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "execution_fragile_reject")

    def test_ticker_concentrated_profit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_search"]["candidates"] = [
                _candidate(ticker_concentration={"status": "available", "top_ticker_profit_share_pct": 80.0})
            ]
            report = self._build(Path(temp_dir), payloads)

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "ticker_concentrated_reject")

    def test_month_concentrated_profit_is_regime_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_search"]["candidates"] = [
                _candidate(month_concentration={"status": "available", "top_month_profit_share_pct": 75.0})
            ]
            report = self._build(Path(temp_dir), payloads)

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "regime_fragile_reject")

    def test_top_winner_stress_failure_is_overfit_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_search"]["candidates"] = [
                _candidate(stress_results={"top_1_removed_profit_factor": 0.8, "wider_spread_profit_factor": 1.2})
            ]
            report = self._build(Path(temp_dir), payloads)

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "overfit_reject")

    def test_unpriced_rows_require_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["robust_search"]["candidates"] = [_candidate(unpriced_rows=2)]
            report = self._build(Path(temp_dir), payloads)

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "candidate_good")
        self.assertEqual(row["decision"], "repair_needed")

    def test_volatility_paper_probation_remains_paper_shadow_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        row = next(item for item in report["candidate_rankings"] if item["candidate_id"] == "lane:volatility_expansion_observation")
        self.assertEqual(row["decision"], "paper_shadow_candidate")

    def test_existing_promotion_ready_false_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["existing_promotion_ready"])
        self.assertEqual(report["forward_freeze_recommendation"]["status"], "not_recommended")

    def test_no_passing_candidate_returns_paper_shadow_or_no_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertIn(report["overall_status"], {"paper_shadow_only", "no_robust_edge_found"})
        self.assertEqual(report["robust_candidate_count"], 0)

    def test_live_and_broker_flags_are_never_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])
        self.assertFalse(report["broker_order_allowed"])


if __name__ == "__main__":
    unittest.main()
