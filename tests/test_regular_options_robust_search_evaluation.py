from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_regular_options_robust_search_evaluation as robust


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _trade(
    entry_date: str,
    pnl_pct: float,
    *,
    lane_id: str = "alpha",
    lane_family: str = "test_family",
    ticker: str = "SPY",
) -> dict:
    return {
        "entry_date": entry_date,
        "exit_date": entry_date,
        "ticker": ticker,
        "lane_id": lane_id,
        "lane_family": lane_family,
        "direction": "call",
        "pnl_pct": pnl_pct,
        "exact_priced": True,
        "portfolio_eligible": True,
        "proof_grade": "trusted_intraday_opra_nbbo",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "fill_basis": "imported_spread_mark",
        "long_contract_symbol": "SPY260220C00500000",
        "short_contract_symbol": "SPY260220C00510000",
    }


def _passing_source_rows() -> list[dict]:
    rows = []
    start = date(2025, 1, 2)
    for day_index in range(100):
        entry = (start + timedelta(days=day_index)).isoformat()
        for slot in range(2):
            trade_index = day_index * 2 + slot
            pnl = -2.0 if trade_index % 4 == 0 else 20.0
            rows.append(_trade(entry, pnl))
    return rows


class RegularOptionsRobustSearchEvaluationTests(unittest.TestCase):
    def test_chronological_split_keeps_same_entry_date_in_one_split(self) -> None:
        rows = [_trade("2026-01-01", 10.0), _trade("2026-01-01", -2.0), _trade("2026-01-02", 10.0)]

        splits = robust.chronological_split_rows(rows, train_fraction=0.50, validation_fraction=0.25)

        memberships = {}
        for split, split_rows in splits.items():
            for row in split_rows:
                memberships.setdefault(row["entry_date"], set()).add(split)
        self.assertEqual(memberships["2026-01-01"], {"train"})
        self.assertEqual(memberships["2026-01-02"], {"final_holdout"})

    def test_risk_metrics_include_drawdown_and_loss_streak(self) -> None:
        rows = [
            _trade("2026-01-01", -10.0),
            _trade("2026-01-02", -5.0),
            _trade("2026-01-03", 30.0),
            _trade("2026-01-04", -20.0),
        ]

        metrics = robust._metrics_for_rows(rows, branch_id="risk-test", bootstrap_draws=20)

        self.assertEqual(metrics["risk"]["cumulative_pnl_pct_points"], -5.0)
        self.assertEqual(metrics["risk"]["max_drawdown_pct_points"], 20.0)
        self.assertEqual(metrics["risk"]["max_consecutive_loss_count"], 2)
        self.assertEqual(metrics["risk"]["best_trade_pnl_pct"], 30.0)
        self.assertEqual(metrics["risk"]["worst_trade_pnl_pct"], -20.0)

    def test_build_report_can_mark_historical_candidate_ready_for_forward_nomination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            regime = root / "regime.json"
            feature_store = root / "feature_store.json"
            baseline = root / "baseline.json"
            ledger = root / "ledger.jsonl"
            _write_json(
                source,
                {
                    "selected_trades": _passing_source_rows(),
                    "quality_gate": {"overall_status": "passed", "blockers": []},
                },
            )
            _write_json(
                regime,
                {
                    "summary": {
                        "regime_robust": True,
                        "overall_status": "regime_robust",
                        "market_context_status": "available",
                    }
                },
            )
            _write_json(
                feature_store,
                {
                    "status": "feature_store_built",
                    "inputs": {
                        "source_label": "thetadata_opra_nbbo_1m",
                        "snapshot_kind": "intraday",
                        "data_trust": "trusted",
                    },
                    "summary": {"shared_quote_date_count": 504, "missing_required_inputs": []},
                },
            )
            _write_json(baseline, {"baseline_metrics": {"profit_factor": 0.8, "avg_pnl_pct": -1.0}})
            _write_jsonl(ledger, [{"experiment_id": f"variant_{index}"} for index in range(4)])

            report = robust.build_report(
                source_report_path=source,
                regime_report_path=regime,
                feature_store_report_path=feature_store,
                autoresearch_ledger_path=ledger,
                baseline_report_path=baseline,
                bootstrap_draws=200,
                generated_at_utc="2026-01-01T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_candidates_ready_for_forward_nomination")
        self.assertEqual(report["summary"]["accepted_exact_trade_count"], 200)
        combined = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "combined_portfolio")
        self.assertTrue(combined["historical_nomination_ready"])
        self.assertEqual(combined["split_metrics"]["validation"]["exact_trade_count"], 50)
        self.assertEqual(combined["split_metrics"]["final_holdout"]["exact_trade_count"], 30)
        self.assertGreater(combined["split_metrics"]["final_holdout"]["bootstrap"]["pf_lb_5pct"], 1.0)
        self.assertEqual(combined["split_metrics"]["combined"]["risk"]["cumulative_pnl_pct_points"], 2900.0)
        self.assertEqual(combined["split_metrics"]["combined"]["risk"]["max_drawdown_pct_points"], 2.0)
        self.assertEqual(combined["selection_adjustment"]["variants_searched"], 4)
        self.assertEqual(combined["feature_store_gate"]["status"], "feature_store_gate_passed")

    def test_feature_store_gate_blocks_nomination_when_shared_history_is_thin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            regime = root / "regime.json"
            feature_store = root / "feature_store.json"
            baseline = root / "baseline.json"
            ledger = root / "ledger.jsonl"
            _write_json(
                source,
                {
                    "selected_trades": _passing_source_rows(),
                    "quality_gate": {"overall_status": "passed", "blockers": []},
                },
            )
            _write_json(
                regime,
                {
                    "summary": {
                        "regime_robust": True,
                        "overall_status": "regime_robust",
                        "market_context_status": "available",
                    }
                },
            )
            _write_json(
                feature_store,
                {
                    "status": "feature_store_built",
                    "inputs": {
                        "source_label": "thetadata_opra_nbbo_1m",
                        "snapshot_kind": "intraday",
                        "data_trust": "trusted",
                    },
                    "summary": {"shared_quote_date_count": 100, "missing_required_inputs": []},
                },
            )
            _write_json(baseline, {"baseline_metrics": {"profit_factor": 0.8, "avg_pnl_pct": -1.0}})
            _write_jsonl(ledger, [{"experiment_id": f"variant_{index}"} for index in range(4)])

            report = robust.build_report(
                source_report_path=source,
                regime_report_path=regime,
                feature_store_report_path=feature_store,
                autoresearch_ledger_path=ledger,
                baseline_report_path=baseline,
                bootstrap_draws=200,
                generated_at_utc="2026-01-01T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_candidates_blocked")
        combined = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "combined_portfolio")
        self.assertFalse(combined["historical_nomination_ready"])
        self.assertIn("feature_store_shared_quote_dates_100_below_504", combined["blockers"])
        self.assertEqual(combined["feature_store_gate"]["status"], "feature_store_gate_blocked")

    def test_ablation_uses_authoritative_profitability_metrics_first(self) -> None:
        final_metrics = {"profit_factor": 1.4, "avg_pnl_pct": 5.0}
        baseline_report = {
            "profit_factor": 9.9,
            "avg_pnl_pct": 99.0,
            "authoritative_profitability_metrics": {
                "profit_factor": 0.83,
                "avg_pnl_pct": -6.1,
            },
        }

        ablation = robust._ablation_check(final_metrics, baseline_report, {"status": "loaded"})

        self.assertTrue(ablation["positive_ablation"])
        self.assertEqual(ablation["baseline_metrics"]["profit_factor"], 0.83)
        self.assertEqual(ablation["baseline_metrics"]["avg_pnl_pct"], -6.1)

    def test_build_report_fails_closed_when_evidence_chain_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            ledger = root / "ledger.jsonl"
            rows = [_trade((date(2026, 1, 1) + timedelta(days=index)).isoformat(), 5.0) for index in range(40)]
            rows.append({**_trade("2026-03-01", 10.0), "proof_grade": "exact_daily_research"})
            _write_json(
                source,
                {
                    "selected_trades": rows,
                    "quality_gate": {"overall_status": "quality_pending", "blockers": ["paper_shadow_fill_evidence_pending"]},
                },
            )
            _write_jsonl(ledger, [{"experiment_id": "one"}])

            report = robust.build_report(
                source_report_path=source,
                regime_report_path=root / "missing_regime.json",
                feature_store_report_path=root / "missing_feature_store.json",
                autoresearch_ledger_path=ledger,
                baseline_report_path=None,
                bootstrap_draws=50,
                generated_at_utc="2026-01-01T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_candidates_blocked")
        self.assertEqual(report["summary"]["accepted_exact_trade_count"], 40)
        self.assertEqual(report["summary"]["rejected_row_counts"]["not_trusted_intraday_exact_row"], 1)
        combined = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "combined_portfolio")
        self.assertFalse(combined["historical_nomination_ready"])
        self.assertIn("total_exact_trades_below_100", combined["blockers"])
        self.assertIn("regime_report_missing", combined["blockers"])
        self.assertIn("baseline_ablation_report_missing", combined["blockers"])
        self.assertIn("source_quality_gate:quality_pending", combined["blockers"])
        self.assertIn("feature_store_report_missing", combined["blockers"])

    def test_source_quality_scope_policy_excludes_cvx_from_candidate_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            regime = root / "regime.json"
            feature_store = root / "feature_store.json"
            baseline = root / "baseline.json"
            ledger = root / "ledger.jsonl"
            policy = root / "policy.json"
            rows = _passing_source_rows()
            rows.extend(
                [
                    _trade(
                        "2025-05-01",
                        300.0,
                        ticker="CVX",
                        lane_id="bullish_pullback_core",
                        lane_family="bullish_pullback_observation",
                    ),
                    _trade(
                        "2025-05-02",
                        -90.0,
                        ticker="CVX",
                        lane_id="bullish_pullback_core",
                        lane_family="bullish_pullback_observation",
                    ),
                ]
            )
            _write_json(
                source,
                {
                    "selected_trades": rows,
                    "quality_gate": {
                        "overall_status": "quality_pending",
                        "blockers": [
                            "bullish_pullback_core:CVX_low_executable_quote_coverage",
                            "lane_a:unrelated_lane_blocker",
                        ],
                    },
                },
            )
            _write_json(
                regime,
                {
                    "summary": {
                        "regime_robust": True,
                        "overall_status": "regime_robust",
                        "market_context_status": "available",
                    }
                },
            )
            _write_json(
                feature_store,
                {
                    "status": "feature_store_built",
                    "inputs": {
                        "source_label": "thetadata_opra_nbbo_1m",
                        "snapshot_kind": "intraday",
                        "data_trust": "trusted",
                    },
                    "summary": {"shared_quote_date_count": 504, "missing_required_inputs": []},
                },
            )
            _write_json(baseline, {"baseline_metrics": {"profit_factor": 0.8, "avg_pnl_pct": -1.0}})
            _write_jsonl(ledger, [{"experiment_id": f"variant_{index}"} for index in range(4)])
            _write_json(
                policy,
                {
                    "policy_id": "test_source_quality_policy",
                    "status": "active",
                    "rules": [
                        {
                            "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                            "status": "active",
                            "action": "exclude_matching_trades_from_historical_candidate_scope",
                            "symbols": ["CVX"],
                            "lane_ids": ["bullish_pullback_core"],
                            "lane_families": ["bullish_pullback_observation"],
                            "reason": "zero_bid_tradability_floor_failure",
                            "suppressed_quality_blocker_tokens": ["CVX", "low_executable_quote_coverage"],
                        }
                    ],
                },
            )

            report = robust.build_report(
                source_report_path=source,
                regime_report_path=regime,
                feature_store_report_path=feature_store,
                autoresearch_ledger_path=ledger,
                source_quality_policy_path=policy,
                baseline_report_path=baseline,
                bootstrap_draws=200,
                generated_at_utc="2026-01-01T00:00:00Z",
            )

        self.assertEqual(report["summary"]["accepted_exact_trade_count_before_source_quality_scope"], 202)
        self.assertEqual(report["summary"]["accepted_exact_trade_count"], 200)
        self.assertEqual(report["summary"]["source_quality_scope_excluded_trade_count"], 2)
        self.assertEqual({row["ticker"] for row in report["source_quality_exclusions"]}, {"CVX"})
        combined = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "combined_portfolio")
        self.assertEqual(combined["split_metrics"]["combined"]["exact_trade_count"], 200)
        self.assertEqual(combined["source_quality_scope_policy"]["excluded_trade_count"], 2)
        self.assertIn(
            "bullish_pullback_core:CVX_low_executable_quote_coverage",
            combined["source_quality_gate"]["suppressed_blockers"],
        )
        self.assertIn("lane_a:unrelated_lane_blocker", combined["source_quality_gate"]["suppressed_blockers"])
        self.assertEqual(combined["source_quality_gate"]["blockers"], [])
        self.assertEqual(combined["source_quality_gate"]["status"], "source_quality_gate_passed")

    def test_source_quality_gate_applies_lane_alias_blockers(self) -> None:
        gate = robust._quality_gate_check(
            {
                "quality_gate": {
                    "overall_status": "quality_pending",
                    "blockers": ["lane_a:conservative_zero_bid_pf_0.85_below_1_3"],
                }
            },
            candidate_rows=[
                _trade(
                    "2026-01-01",
                    10.0,
                    lane_id="lane_a_chain_native_ret20_4_stop200_time75",
                )
            ],
            scope_exclusions=[],
            source_quality_policy={},
            source_quality_policy_meta={"status": "missing"},
        )

        self.assertFalse(gate["passed"])
        self.assertIn("lane_a:conservative_zero_bid_pf_0.85_below_1_3", gate["blockers"])
        self.assertIn("source_quality_gate:quality_pending", gate["blockers"])


if __name__ == "__main__":
    unittest.main()
