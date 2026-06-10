from __future__ import annotations

import unittest
from datetime import date, timedelta

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
