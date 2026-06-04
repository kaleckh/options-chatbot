from __future__ import annotations

import unittest

from scripts.run_regular_options_multilane_portfolio import (
    _metrics_from_run,
    build_quality_gate,
    classify_lane,
    compact_side_aware_zero_bid_report,
    dedupe_portfolio_trades,
    metrics_for_trades,
    normalize_trade,
    proof_grade_for_run,
)


def _run(**overrides):
    payload = {
        "playbook": "test_lane",
        "truth_source": "historical_imported",
        "execution_realism": "quote_backed_intraday_replay",
    }
    payload.update(overrides)
    return payload


def _lane(**overrides):
    payload = {
        "lane_id": "lane_a",
        "family": "family_a",
        "artifact": "data/options-validation/runs/test.json",
        "priority": 10,
        "include_in_proof_portfolio": True,
    }
    payload.update(overrides)
    return payload


def _trade(**overrides):
    payload = {
        "ticker": "SPY",
        "date": "2026-01-02",
        "exit_date": "2026-01-16",
        "type": "call",
        "allocation_group": "index",
        "priced": True,
        "entry_contract_resolution": "exact_listed_spread_contract",
        "exit_fill_basis": "imported_spread_mark",
        "net_pnl_pct": 25.0,
        "contract_symbol": "SPY260116C00500000",
        "short_contract_symbol": "SPY260116C00510000",
    }
    payload.update(overrides)
    return payload


class RegularOptionsMultilanePortfolioTests(unittest.TestCase):
    def test_proof_grade_separates_intraday_from_daily_research(self):
        self.assertEqual(proof_grade_for_run(_run()), "trusted_intraday_opra_nbbo")
        self.assertEqual(
            proof_grade_for_run(_run(truth_source="historical_imported_daily", execution_realism="coarse_eod_validation")),
            "exact_daily_research",
        )

    def test_normalize_trade_counts_only_exact_intraday_rows_as_portfolio_eligible(self):
        row = normalize_trade(_trade(), _lane(), _run())

        self.assertTrue(row["exact_priced"])
        self.assertTrue(row["portfolio_eligible"])
        self.assertEqual(row["dedupe_key"], "2026-01-02|SPY|call")

    def test_normalize_trade_rejects_daily_row_for_proof_portfolio(self):
        row = normalize_trade(
            _trade(),
            _lane(),
            _run(truth_source="historical_imported_daily", execution_realism="coarse_eod_validation"),
        )

        self.assertFalse(row["exact_priced"])
        self.assertFalse(row["portfolio_eligible"])
        self.assertEqual(row["proof_grade"], "exact_daily_research")

    def test_dedupe_prefers_lower_priority_lane_for_same_ticker_date_direction(self):
        first = normalize_trade(_trade(net_pnl_pct=10.0), _lane(lane_id="core", priority=10), _run())
        duplicate = normalize_trade(
            _trade(net_pnl_pct=200.0, allocation_group="different_sleeve"),
            _lane(lane_id="scout", priority=50),
            _run(),
        )

        result = dedupe_portfolio_trades([duplicate, first])

        self.assertEqual(len(result["selected_trades"]), 1)
        self.assertEqual(result["selected_trades"][0]["lane_id"], "core")
        self.assertEqual(len(result["suppressed_duplicates"]), 1)
        self.assertEqual(result["duplicate_group_count"], 1)

    def test_metrics_for_trades_uses_selected_exact_rows(self):
        rows = [
            normalize_trade(_trade(ticker="SPY", date="2026-01-02", net_pnl_pct=50.0), _lane(), _run()),
            normalize_trade(_trade(ticker="QQQ", date="2026-01-03", net_pnl_pct=-25.0), _lane(), _run()),
            normalize_trade(_trade(ticker="IWM", date="2026-01-04", net_pnl_pct=25.0), _lane(), _run()),
        ]

        metrics = metrics_for_trades(rows)

        self.assertEqual(metrics["exact_trade_count"], 3)
        self.assertEqual(metrics["profit_factor"], 3.0)
        self.assertEqual(metrics["avg_pnl_pct"], 16.67)
        self.assertEqual(metrics["gap_to_200"], 197)

    def test_metrics_from_run_falls_back_for_sparse_authoritative_metrics(self):
        metrics = _metrics_from_run(
            {
                "candidate_trade_count": 10,
                "exact_contract_match_count": 8,
                "win_rate_pct": 62.5,
                "authoritative_profitability_metrics": {
                    "trade_count": 8,
                    "profit_factor": 2.0,
                    "avg_pnl_pct": 15.0,
                },
            }
        )

        self.assertEqual(metrics["profit_factor"], 2.0)
        self.assertEqual(metrics["win_rate_pct"], 62.5)

    def test_classify_lane_blocks_weak_intraday_scout(self):
        status = classify_lane(
            {
                "exact_trade_count": 44,
                "unpriced_trade_count": 12,
                "quote_coverage_pct": 78.6,
                "profit_factor": 0.2,
                "avg_pnl_pct": -35.37,
            },
            {},
            "trusted_intraday_opra_nbbo",
            False,
        )

        self.assertEqual(status["status"], "intraday_scout")
        self.assertIn("pf_below_1_75", status["blockers"])
        self.assertIn("unpriced_candidates_remain", status["blockers"])

    def test_classify_lane_marks_proof_count_candidate_not_clean_portfolio(self):
        status = classify_lane(
            {
                "exact_trade_count": 110,
                "unpriced_trade_count": 9,
                "quote_coverage_pct": 92.4,
                "profit_factor": 2.0,
                "avg_pnl_pct": 10.0,
            },
            {},
            "trusted_intraday_opra_nbbo",
            True,
        )

        self.assertEqual(status["status"], "count_candidate")
        self.assertIn("unpriced_candidates_remain", status["blockers"])

    def test_quality_gate_separates_count_success_from_production_readiness(self):
        gate = build_quality_gate(
            [
                {
                    "lane_id": "core",
                    "include_in_proof_portfolio": True,
                    "status": "count_candidate",
                    "metrics": {"quote_coverage_pct": 97.7, "unpriced_trade_count": 3},
                    "robustness": {
                        "rolling_status": "passed",
                        "stress_5pct_per_side_profit_factor": 1.53,
                    },
                },
                {
                    "lane_id": "lane_a",
                    "include_in_proof_portfolio": True,
                    "status": "count_candidate",
                    "metrics": {"quote_coverage_pct": 53.1, "unpriced_trade_count": 137},
                    "robustness": {
                        "rolling_status": "watch",
                        "stress_5pct_per_side_profit_factor": 2.65,
                    },
                },
            ],
            {"exact_trade_count": 230},
        )

        self.assertEqual(gate["count_status"], "passed")
        self.assertEqual(gate["coverage_status"], "blocked")
        self.assertEqual(gate["robustness_status"], "blocked")
        self.assertEqual(gate["overall_status"], "quality_pending")
        self.assertIn("paper_shadow_fill_evidence_pending", gate["blockers"])

    def test_quality_gate_blocks_bad_lane_a_zero_bid_economics(self):
        gate = build_quality_gate(
            [],
            {"exact_trade_count": 230},
            {
                "modes": {
                    "conservative": {
                        "combined_with_existing_lane_a_metrics": {
                            "profit_factor": 0.85,
                            "avg_pnl_pct": -6.51,
                        },
                        "combined_lane_a_priced_count": 281,
                        "combined_lane_a_unpriced_count": 0,
                        "zero_bid_priced_count": 118,
                        "zero_bid_exit_rate_pct": 41.99,
                    }
                }
            },
        )

        self.assertEqual(gate["zero_bid_status"], "blocked")
        self.assertIn("lane_a:conservative_zero_bid_pf_0.85_below_1_3", gate["blockers"])
        self.assertIn("lane_a:conservative_zero_bid_exit_rate_41.99_above_2.0", gate["blockers"])

    def test_side_aware_zero_bid_summary_keeps_compact_metrics(self):
        summary = compact_side_aware_zero_bid_report(
            {
                "generated_at_utc": "2026-05-31T02:40:58Z",
                "provider_stats": {"theta_request_count": 10},
                "modes": {
                    "conservative": {
                        "candidate_count": 127,
                        "priced_count": 126,
                        "unpriced_count": 1,
                        "zero_bid_priced_count": 118,
                        "side_aware_metrics": {"profit_factor": 0.11, "avg_pnl_pct": -66.59},
                        "combined_with_existing_lane_a_metrics": {"profit_factor": 0.85},
                        "combined_lane_a_priced_count": 281,
                        "combined_lane_a_unpriced_count": 11,
                        "combined_lane_a_quote_coverage_pct": 96.2,
                        "priced_rows": [{"large": "omitted"}],
                    }
                },
            }
        )

        conservative = summary["modes"]["conservative"]
        self.assertEqual(conservative["priced_count"], 126)
        self.assertEqual(conservative["zero_bid_priced_count"], 118)
        self.assertEqual(conservative["combined_lane_a_quote_coverage_pct"], 96.2)
        self.assertEqual(conservative["zero_bid_exit_rate_pct"], 41.99)
        self.assertNotIn("priced_rows", conservative)


if __name__ == "__main__":
    unittest.main()
