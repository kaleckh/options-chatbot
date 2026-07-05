from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

import supervised_scan as ss
import wfo_optimizer as wfo


def _make_trade(
    trade_date: date,
    *,
    ticker: str,
    sector: str = "Healthcare",
    market_regime: str = "bearish",
    trade_type: str = "put",
    dte: int = 12,
    pnl_pct: float = 10.0,
    directional_correct: bool = True,
    direction_score: float = 74.0,
    quality_score: float = 68.0,
    ev: float = 16.0,
) -> dict:
    return {
        "ticker": ticker,
        "date": trade_date.isoformat(),
        "type": trade_type,
        "sector": sector,
        "market_regime": market_regime,
        "dte": dte,
        "pnl_pct": pnl_pct,
        "directional_correct": directional_correct,
        "direction_score": direction_score,
        "quality_score": quality_score,
        "ev": ev,
        "prediction_outcome": "hit" if pnl_pct > 0 else "miss",
    }


def _make_result(
    trades: list[dict],
    *,
    lookback_years: int = 2,
    pricing_lane: str = "pessimistic",
    playbook: str = "broad",
) -> dict:
    return {
        "run_at": "2026-03-30T12:00:00",
        "mode": "backtest",
        "lookback_years": lookback_years,
        "pricing_lane": pricing_lane,
        "playbook": playbook,
        "total_days": len(trades) * 5,
        "total_trades": len(trades),
        "trades": trades,
    }


def _find_candidate(report: dict, filters: dict) -> dict:
    return next(item for item in report["candidates"] if item["filters"] == filters)


class PlaybookDiscoveryTests(unittest.TestCase):
    def test_supervised_scan_playbooks_have_validation_tracking_metadata(self):
        for playbook_id in ss.SCAN_PLAYBOOKS:
            with self.subTest(playbook_id=playbook_id):
                playbook = ss.get_scan_playbook(playbook_id)
                self.assertIn("fresh_live_validation_enabled", playbook)
                self.assertIn("position_tracking_mode", playbook)
                self.assertIn("proof_scope", playbook)
                self.assertIn(
                    playbook["position_tracking_mode"],
                    {
                        ss.POSITION_TRACKING_AUTO_TRACK,
                        ss.POSITION_TRACKING_PAPER_REVIEW_ONLY,
                        ss.POSITION_TRACKING_DIAGNOSTIC_ONLY,
                        ss.POSITION_TRACKING_DISABLED,
                    },
                )
                if playbook_id == ss.AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID:
                    self.assertEqual(playbook["position_tracking_mode"], ss.POSITION_TRACKING_DISABLED)
                    self.assertEqual(playbook["proof_scope"], ss.COMMODITY_PROOF_SCOPE)
                else:
                    self.assertEqual(playbook["position_tracking_mode"], ss.POSITION_TRACKING_AUTO_TRACK)
                    expected_proof_scope = (
                        ss.REGULAR_CONTROL_PROOF_SCOPE
                        if playbook_id == ss.QUALITY90_DEBIT55_CANARY_COHORT_ID
                        else ss.REGULAR_PROOF_SCOPE
                    )
                    self.assertEqual(playbook["proof_scope"], expected_proof_scope)

    def test_exit_audit_fallback_tracks_bullish_pullback_playbook(self):
        self.assertEqual(wfo.PLAYBOOK_EXIT_AUDIT_FALLBACK_PLAYBOOK, "bullish_pullback_observation")
        self.assertEqual(wfo._playbook_trade_window(""), {"min_dte": 13, "max_dte": 45})
        self.assertEqual(wfo._playbook_trade_window("bullish_pullback_observation"), {"min_dte": 13, "max_dte": 45})

    def test_speculative_window_targets_shortest_allowed_contracts(self):
        self.assertEqual(wfo._playbook_trade_window("speculative"), {"min_dte": 5, "max_dte": 9})

    def test_active_scan_playbook_windows_include_target_dte(self):
        for playbook_id, playbook in ss.SCAN_PLAYBOOKS.items():
            with self.subTest(playbook_id=playbook_id):
                target_dte = int(playbook["target_dte"])
                window = wfo._playbook_trade_window(playbook_id)
                self.assertLessEqual(window["min_dte"], target_dte)
                self.assertGreaterEqual(window["max_dte"], target_dte)

    def test_stable_slice_gets_promote(self):
        start = date(2024, 1, 5)
        tickers = ["PFE", "MRK", "LLY"]
        pnl_values = [12.0, 10.0, 8.0, 9.0, 11.0, -1.0, 10.0, 9.0, 8.0, -1.0, 6.0, 10.0, 9.0, 7.0, 11.0]
        trades = [
            _make_trade(start + timedelta(days=index * 30), ticker=tickers[index % len(tickers)], pnl_pct=pnl)
            for index, pnl in enumerate(pnl_values)
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(trades),
            min_trades=4,
            rolling_window_days=180,
            rolling_step_days=90,
        )
        candidate = _find_candidate(
            report,
            {"direction": "put", "market_regime": "bearish", "sector": "Healthcare"},
        )

        self.assertEqual(candidate["status"], "promote")
        self.assertTrue(any("cleared the quality bar" in reason.lower() for reason in candidate["reasons"]))

    def test_sparse_slice_stays_watch_or_block(self):
        start = date(2024, 1, 5)
        trades = [
            _make_trade(start, ticker="PFE", pnl_pct=12.0),
            _make_trade(start + timedelta(days=40), ticker="MRK", pnl_pct=-1.0),
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(trades),
            min_trades=4,
            rolling_window_days=180,
            rolling_step_days=90,
        )
        candidate = _find_candidate(
            report,
            {"direction": "put", "market_regime": "bearish", "sector": "Healthcare"},
        )

        self.assertIn(candidate["status"], {"watch", "block"})
        self.assertNotEqual(candidate["status"], "promote")
        self.assertTrue(any("need at least" in blocker.lower() for blocker in candidate["blockers"]))

    def test_non_finite_metrics_do_not_promote_discovery_slice(self):
        trades = [
            {
                "date": None,
                "ticker": "SPY",
                "type": "call",
                "sector": "Index ETF",
                "market_regime": "bullish",
                "directional_correct": True,
                "entry_contract_resolution": "exact_target_contract",
                "pnl_pct": float("inf"),
            },
            {
                "date": None,
                "ticker": "QQQ",
                "type": "call",
                "sector": "Index ETF",
                "market_regime": "bullish",
                "directional_correct": True,
                "entry_contract_resolution": "exact_target_contract",
                "pnl_pct": float("inf"),
            },
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(trades, playbook="short_term"),
            min_trades=1,
        )
        candidate = _find_candidate(
            report,
            {"direction": "call", "market_regime": "bullish", "sector": "Index ETF"},
        )

        self.assertEqual(candidate["status"], "block")
        self.assertFalse(candidate["overall"]["metrics_finite"])
        self.assertIn("profit_factor", candidate["overall"]["non_finite_metrics"])
        self.assertTrue(candidate["overall"]["no_loss_sample"])
        self.assertIn("avg_pnl_pct", candidate["overall"]["non_finite_metrics"])
        self.assertTrue(any("non-finite metrics" in blocker.lower() for blocker in candidate["blockers"]))

    def test_prediction_replay_report_does_not_flag_no_loss_sample_as_sub_unit_pf(self):
        result = _make_result(
            [
                _make_trade(date(2024, 1, 5), ticker="SPY", pnl_pct=12.0),
                _make_trade(date(2024, 1, 6), ticker="QQQ", pnl_pct=8.0),
            ],
            playbook="short_term",
        )

        report = wfo.build_prediction_replay_report(result=result, min_trades=1)

        self.assertIsNone(report["overall"]["profit_factor"])
        self.assertTrue(report["overall"]["no_loss_sample"])
        self.assertFalse(any("Profit factor is below 1.0" in flag for flag in report["risk_flags"]))

    def test_prediction_replay_report_treats_string_directional_flags_strictly(self):
        result = _make_result(
            [
                _make_trade(date(2024, 1, 5), ticker="SPY", pnl_pct=12.0, directional_correct="False"),
                _make_trade(date(2024, 1, 6), ticker="QQQ", pnl_pct=8.0, directional_correct="true"),
            ],
            playbook="short_term",
        )

        report = wfo.build_prediction_replay_report(result=result, min_trades=1)

        self.assertEqual(report["overall"]["directional_accuracy_pct"], 50.0)

    def test_stability_report_does_not_crash_for_mixed_forward_playbook_results(self):
        result = _make_result(
            [
                _make_trade(date(2024, 1, 5), ticker="SPY", dte=7, pnl_pct=12.0),
                _make_trade(date(2024, 2, 5), ticker="QQQ", dte=7, pnl_pct=-4.0, directional_correct=False),
            ],
            playbook="forward_ledger_scan",
        )
        result["truth_source"] = wfo.IMPORTED_DAILY_TRUTH_SOURCE
        result["quote_coverage_pct"] = 100.0

        report = wfo.build_options_stability_report(result=result, min_trades=1, rolling_window_days=30, rolling_step_days=30)

        self.assertNotIn("error", report)
        self.assertIn("overall_status", report)

    def test_playbook_rolling_summary_requires_directional_accuracy_gate(self):
        trades = [
            _make_trade(date(2024, 1, 5), ticker="SPY", pnl_pct=12.0, directional_correct=False),
            _make_trade(date(2024, 1, 20), ticker="QQQ", pnl_pct=8.0, directional_correct=False),
        ]
        source = {
            "label": "1y-pessimistic",
            "dated_trades": trades,
        }

        summary = wfo._playbook_rolling_summary(
            source,
            {"direction": "put", "sector": "Healthcare"},
            min_trades=1,
            min_profit_factor=1.05,
            min_directional_accuracy_pct=50.0,
            rolling_window_days=40,
            rolling_step_days=40,
            catastrophic_pf_floor=0.85,
        )

        self.assertEqual(summary["windows_seen"], 1)
        self.assertEqual(summary["windows_passed"], 0)
        self.assertEqual(summary["status"], "weak")

    def test_live_trade_policy_forwards_directional_threshold_to_stability_report(self):
        result = _make_result(
            [_make_trade(date(2024, 1, 5), ticker="SPY", pnl_pct=12.0)],
            playbook="short_term",
        )

        with (
            patch.object(
                wfo,
                "build_options_experiment_matrix",
                return_value={"overall": {}, "by_category": {}},
            ),
            patch.object(
                wfo,
                "build_options_stability_report",
                return_value={"overall_status": "watch", "slice_statuses": {}},
            ) as stability_report,
        ):
            wfo.build_live_options_trade_policy(
                result=result,
                min_trades=1,
                min_profit_factor=1.0,
                min_directional_accuracy_pct=67.0,
            )

        self.assertEqual(
            stability_report.call_args.kwargs["min_directional_accuracy_pct"],
            67.0,
        )

    def test_stability_report_enforces_directional_accuracy_gate(self):
        result = _make_result(
            [
                _make_trade(date(2024, 1, 5), ticker="SPY", dte=7, pnl_pct=10.0, directional_correct=False),
                _make_trade(date(2024, 1, 6), ticker="QQQ", dte=7, pnl_pct=-1.0, directional_correct=False),
            ],
            playbook="short_term",
        )

        report = wfo.build_options_stability_report(
            result=result,
            min_trades=1,
            min_profit_factor=1.0,
            rolling_window_days=30,
            rolling_step_days=30,
        )

        self.assertNotEqual(report["overall_status"], "promote")
        self.assertFalse(report["scenario_results"]["full_window"]["passes_quality_bar"])
        self.assertTrue(all(item["status"] == "block" for item in report["slice_statuses"]["sector"]))

    def test_pairwise_playbook_comparison_formats_none_profit_factor_safely(self):
        comparison = wfo._pairwise_playbook_comparison(
            "mid vs pessimistic",
            {
                "source_label": "mid",
                "trades": 5,
                "profit_factor": None,
                "avg_pnl_pct": 4.0,
                "directional_accuracy_pct": 80.0,
                "passes_quality_bar": True,
            },
            {
                "source_label": "pessimistic",
                "trades": 5,
                "profit_factor": None,
                "avg_pnl_pct": 3.0,
                "directional_accuracy_pct": 80.0,
                "passes_quality_bar": True,
            },
        )

        self.assertEqual(comparison["status"], "confirmed")
        self.assertIn("PF n/a", comparison["reason"])

    def test_playbook_discovery_slice_preserves_none_profit_factor_for_no_loss_sample(self):
        summary = wfo._summarize_playbook_discovery_slice(
            {"direction": "call", "sector": "Healthcare"},
            [
                _make_trade(date(2024, 1, 5), ticker="SPY", pnl_pct=12.0),
                _make_trade(date(2024, 1, 6), ticker="QQQ", pnl_pct=8.0),
            ],
            2,
            min_trades=1,
            min_profit_factor=1.05,
            min_directional_accuracy_pct=50.0,
        )

        self.assertIsNone(summary["profit_factor"])
        self.assertTrue(summary["no_loss_sample"])

    def test_prediction_group_profit_factor_denominator_matches_net_usd_basis(self):
        summary = wfo._summarize_prediction_group(
            "window",
            "all",
            [
                {"pnl_pct": 1.0, "net_pnl_usd": 200.0, "directional_correct": True},
                {"pnl_pct": -10.0, "net_pnl_usd": -50.0, "directional_correct": False},
            ],
            2,
        )

        self.assertEqual(summary["profit_factor"], 4.0)
        self.assertEqual(summary["gross_win"], 200.0)
        self.assertEqual(summary["gross_loss"], 50.0)

    def test_ticker_only_slice_is_not_promoted_by_default(self):
        start = date(2024, 1, 5)
        trades = [
            _make_trade(start + timedelta(days=index * 28), ticker="PFE", pnl_pct=10.0 + (index % 3))
            for index in range(15)
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(trades),
            min_trades=4,
            rolling_window_days=180,
            rolling_step_days=90,
        )
        candidate = _find_candidate(
            report,
            {"direction": "put", "market_regime": "bearish", "sector": "Healthcare"},
        )

        self.assertIn(candidate["status"], {"watch", "block"})
        self.assertNotEqual(candidate["status"], "promote")
        self.assertTrue(
            any("ticker-chasing" in blocker.lower() or "concentrated" in blocker.lower() for blocker in candidate["blockers"])
        )

    def test_conflicting_windows_downgrade_a_slice(self):
        start = date(2024, 1, 5)
        tickers = ["PFE", "MRK", "LLY"]
        pnl_values = [12.0, 11.0, 9.0, 10.0, 8.0, -15.0, -14.0, -16.0, -13.0, 12.0, 11.0, 10.0, 9.0, 8.0, 12.0]
        trades = [
            _make_trade(
                start + timedelta(days=index * 30),
                ticker=tickers[index % len(tickers)],
                pnl_pct=pnl,
                directional_correct=pnl > 0,
            )
            for index, pnl in enumerate(pnl_values)
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(trades),
            min_trades=4,
            rolling_window_days=180,
            rolling_step_days=90,
        )
        candidate = _find_candidate(
            report,
            {"direction": "put", "market_regime": "bearish", "sector": "Healthcare"},
        )

        self.assertEqual(candidate["status"], "watch")
        self.assertTrue(any("rolling windows conflicted" in blocker.lower() for blocker in candidate["blockers"]))

    def test_cross_scenario_conflicts_downgrade_slice(self):
        start = date(2024, 1, 5)
        tickers = ["PFE", "MRK", "LLY"]
        stable_trades = [
            _make_trade(start + timedelta(days=index * 30), ticker=tickers[index % len(tickers)], pnl_pct=pnl)
            for index, pnl in enumerate([12.0, 10.0, 8.0, 9.0, 11.0, -1.0, 10.0, 9.0, 8.0, -1.0, 6.0, 10.0, 9.0, 7.0, 11.0])
        ]
        weak_1y_trades = [
            _make_trade(
                date(2025, 1, 10) + timedelta(days=index * 35),
                ticker=tickers[index % len(tickers)],
                pnl_pct=-14.0,
                directional_correct=False,
            )
            for index in range(4)
        ]
        weak_pessimistic_trades = [
            _make_trade(
                date(2024, 2, 14) + timedelta(days=index * 40),
                ticker=tickers[index % len(tickers)],
                pnl_pct=-13.0,
                directional_correct=False,
            )
            for index in range(4)
        ]

        report = wfo.build_playbook_discovery_report(
            result=_make_result(stable_trades, lookback_years=2, pricing_lane="mid"),
            comparison_results=[
                _make_result(weak_1y_trades, lookback_years=1, pricing_lane="mid"),
                _make_result(weak_pessimistic_trades, lookback_years=2, pricing_lane="pessimistic"),
            ],
            min_trades=4,
            rolling_window_days=180,
            rolling_step_days=90,
        )
        candidate = _find_candidate(
            report,
            {"direction": "put", "market_regime": "bearish", "sector": "Healthcare"},
        )

        self.assertEqual(candidate["status"], "watch")
        self.assertTrue(any("1y vs 2y comparison conflicted" in reason.lower() for reason in candidate["reasons"]))
        self.assertTrue(any("mid vs pessimistic comparison conflicted" in reason.lower() for reason in candidate["reasons"]))


if __name__ == "__main__":
    unittest.main()
