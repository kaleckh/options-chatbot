from __future__ import annotations

import unittest

import supervised_scan as ss


class _AvailablePositionsRepo:
    is_available = True

    def list_positions(self, status: str | None = "open"):
        return []


def _tracked_winner_pick(**overrides):
    pick = {
        "ticker": "GOOGL",
        "asset_class": "equity",
        "sector": "Technology",
        "direction": "call",
        "type": "call",
        "strategy_type": "vertical_spread",
        "market_regime": "bullish",
        "expiry": "2026-06-19",
        "strike": 320.0,
        "short_strike": 345.0,
        "spread_width": 25.0,
        "net_debit": 7.5,
        "quality_score": 65.0,
        "direction_score": 87.0,
        "tech_score": 78.0,
    }
    pick.update(overrides)
    return pick


def _bullish_pullback_pick(**overrides):
    pick = {
        "ticker": "SPY",
        "asset_class": "index",
        "sector": "Index ETF",
        "direction": "call",
        "type": "call",
        "strategy_type": "vertical_spread",
        "market_regime": "neutral",
        "expiry": "2026-06-26",
        "strike": 650.0,
        "short_strike": 680.0,
        "spread_width": 30.0,
        "net_debit": 12.0,
        "quality_score": 50.0,
        "direction_score": 78.0,
        "tech_score": 42.0,
        "candidate_execution_label": "executable_opra_paper_candidate",
    }
    pick.update(overrides)
    return pick


class TrackedWinnerPrimaryLaneTests(unittest.TestCase):
    def test_default_supervised_options_lane_is_bullish_pullback_primary(self):
        captured: dict[str, object] = {}

        def _scan_func(**kwargs):
            captured.update(kwargs)
            return [_bullish_pullback_pick()]

        result = ss.run_supervised_scan(
            scan_func=_scan_func,
            positions_repository=_AvailablePositionsRepo(),
            n_picks=1,
            watchlist_size=1,
            use_recommended_policy=False,
        )

        self.assertEqual(ss.DEFAULT_SCAN_PLAYBOOK_ID, "bullish_pullback_observation")
        self.assertEqual(ss.get_scan_playbook()["id"], "bullish_pullback_observation")
        self.assertEqual(result["playbook"]["id"], "bullish_pullback_observation")
        self.assertEqual(result["playbook"]["label"], "Bullish Pullback Primary")
        self.assertEqual(result["playbook"]["lane_role"], "primary_profit_candidate")
        self.assertEqual(captured["symbols"], list(ss.BULLISH_PULLBACK_SCAN_TICKERS))
        self.assertEqual(captured["allowed_directions"], ["call"])
        self.assertEqual(captured["signal_variant"], "pullback_uptrend")
        self.assertEqual(result["picks"][0]["cohort_role"], "primary")

    def test_primary_playbook_exposes_managed_tracked_winner_lane(self):
        playbook = ss.get_scan_playbook("tracked_winner_primary")

        self.assertEqual(playbook["id"], "tracked_winner_primary")
        self.assertEqual(playbook["calibration_playbook"], "broad")
        self.assertEqual(playbook["lane_role"], "secondary_shape_guidance")
        self.assertEqual(playbook["forced_cohort_role"], "candidate")
        self.assertFalse(playbook.get("observation_only", False))
        self.assertEqual(playbook["allowed_tickers"], ["SPY", "GOOGL", "XLK", "DIA"])
        self.assertEqual(playbook["allowed_market_regimes"], ["bullish"])
        self.assertEqual(playbook["allowed_directions"], ["call"])
        self.assertEqual(playbook["allowed_strategy_types"], ["vertical_spread"])
        self.assertEqual(playbook["max_debit_pct_of_width"], 40.0)

    def test_regular_bearish_put_primary_scans_full_regular_universe(self):
        playbook = ss.get_scan_playbook("regular_bearish_put_primary")

        self.assertEqual(playbook["id"], "regular_bearish_put_primary")
        self.assertEqual(playbook["calibration_playbook"], "regular_bearish_put_primary")
        self.assertEqual(playbook["allowed_tickers"], list(ss.BULLISH_PULLBACK_SCAN_TICKERS))
        self.assertEqual(playbook["scan_tickers"], list(ss.BULLISH_PULLBACK_SCAN_TICKERS))
        self.assertEqual(playbook["allowed_market_regimes"], ["bearish"])
        self.assertEqual(playbook["allowed_directions"], ["put"])
        self.assertEqual(playbook["scan_allowed_directions"], ["put"])
        self.assertEqual(playbook["allowed_strategy_types"], ["vertical_spread"])
        self.assertFalse(playbook.get("observation_only", False))

    def test_primary_playbook_applies_tracked_winner_shape_constraints(self):
        playbook = ss.get_scan_playbook("tracked_winner_primary")
        clear = _tracked_winner_pick()
        expensive = _tracked_winner_pick(ticker="SPY", net_debit=10.0)
        wrong_ticker = _tracked_winner_pick(ticker="NVDA")
        wrong_direction = _tracked_winner_pick(ticker="XLK", direction="put", type="put")
        wrong_strategy = _tracked_winner_pick(ticker="DIA", strategy_type="single_leg", short_strike=None, net_debit=3.0)

        result = ss.apply_playbook_guardrails(
            [clear, expensive, wrong_ticker, wrong_direction, wrong_strategy],
            playbook=playbook,
            positions_repository=_AvailablePositionsRepo(),
            include_blocked=True,
        )

        by_ticker = {pick["ticker"]: pick for pick in result["ranked_picks"]}
        self.assertEqual(by_ticker["GOOGL"]["guardrail_decision"], "clear")
        self.assertEqual(by_ticker["GOOGL"]["debit_pct_of_width"], 30.0)
        self.assertFalse(by_ticker["GOOGL"].get("observation_only", False))
        self.assertNotEqual(by_ticker["GOOGL"]["suggested_size_tier"], "starter")

        reasons = " ".join(reason for pick in result["ranked_picks"] for reason in pick["guardrail_reasons"])
        self.assertIn("Spread debit", reasons)
        self.assertIn("only runs on tickers", reasons)
        self.assertIn("only allows directions", reasons)
        self.assertIn("only allows strategies", reasons)

    def test_primary_scan_lane_outranks_candidate_lanes_in_playbook_registry(self):
        result = ss.run_supervised_scan(
            scan_func=lambda **_: [_tracked_winner_pick()],
            positions_repository=_AvailablePositionsRepo(),
            n_picks=1,
            watchlist_size=1,
            playbook_id="tracked_winner_primary",
            use_recommended_policy=False,
        )

        self.assertEqual(result["playbook"]["id"], "tracked_winner_primary")
        self.assertFalse(result["picks"][0].get("observation_only", False))

        playbooks = {playbook["id"]: playbook for playbook in result["playbooks"]}
        self.assertEqual(result["playbooks"][0]["id"], "bullish_pullback_observation")
        self.assertFalse(playbooks["tracked_winner_observation"].get("observation_only", False))
        self.assertEqual(playbooks["tracked_winner_observation"].get("forced_cohort_role"), "candidate")
        self.assertGreater(
            playbooks["tracked_winner_observation"].get("lane_priority", 100),
            playbooks["tracked_winner_primary"]["lane_priority"],
        )


if __name__ == "__main__":
    unittest.main()
