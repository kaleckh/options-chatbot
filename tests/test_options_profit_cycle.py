from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import options_chatbot as oc
from options_profit_flywheel import run_options_profit_cycle
from options_profit_state import (
    ensure_options_profit_state,
    live_profile_path,
    load_incumbents_state,
    load_live_profile_state,
    load_profit_status,
    save_live_profile_state,
)


class OptionsProfitCycleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = os.path.join(self._tmp.name, "options_profit")
        self.forward_db_path = os.path.join(self._tmp.name, "forward_tracking.db")
        self.env = patch.dict(
            os.environ,
            {
                "OPTIONS_PROFIT_STATE_DIR": self.state_dir,
                "FORWARD_OPTIONS_LEDGER_DB_PATH": self.forward_db_path,
                "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": self.forward_db_path,
                "OPTIONS_DAILY_TRUTH_AUTO_REFRESH": "0",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_live_profile_overlay_applies_only_to_target_symbol(self):
        ensure_options_profit_state()
        current = load_live_profile_state(refresh=True)
        current["symbols"]["SPY"]["overrides"] = {
            "entry": {"min_tech_score": 91.0},
            "filters": {"min_calibrated_expectancy_pct": 11.0},
        }
        save_live_profile_state(current)

        spy_profile = oc._get_profile("SPY")
        qqq_profile = oc._get_profile("QQQ")

        self.assertEqual(spy_profile["entry"]["min_tech_score"], 91.0)
        self.assertEqual(spy_profile["filters"]["min_calibrated_expectancy_pct"], 11.0)
        self.assertNotEqual(qqq_profile["entry"]["min_tech_score"], 91.0)

    def test_profit_cycle_bootstraps_and_records_read_only_when_gate_is_unhealthy(self):
        result = run_options_profit_cycle()

        self.assertEqual(result["decision"]["action"], "no_op")
        self.assertTrue(str(result["decision"].get("reason") or "").startswith("measurement_gate_"))
        status = load_profit_status()
        self.assertIn(status["measurement_gate"]["state"], {"blocked", "pending_truth", "degraded-watch"})
        self.assertTrue(Path(live_profile_path()).exists())
        incumbents = load_incumbents_state()
        self.assertIn("SPY", incumbents["symbols"])
        self.assertIn("QQQ", incumbents["symbols"])

    def test_profit_cycle_keeps_qqq_challenger_shadow_only(self):
        ensure_options_profit_state()
        shadow_candidate = {
            "candidate_id": "QQQ__shadow_winner",
            "symbol": "QQQ",
            "base_profile": "index",
            "overrides": {"entry": {"min_tech_score": 88.0}},
            "evaluation": {
                "replay_gate": {"passes": True, "promotion_status": "promote", "stability_status": "promote"},
                "forward_exact_contract": {
                    "eligible_trade_count": 30,
                    "avg_pnl_pct": 12.0,
                    "avg_net_pnl_pct": 11.4,
                    "profit_factor": 1.5,
                    "net_profit_factor": 1.45,
                },
                "tracked_realized": {
                    "closed_position_count": 4,
                    "avg_pnl_pct": 8.0,
                    "avg_net_pnl_pct": 7.2,
                    "profit_factor": 1.3,
                    "net_profit_factor": 1.25,
                },
            },
        }

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[shadow_candidate]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=[]):
            result = run_options_profit_cycle()

        self.assertEqual(result["decision"]["action"], "no_op")
        self.assertEqual(result["decision"]["reason"], "no_eligible_live_symbol_challenger")
        ranking = result["status"]["candidate_rankings"][0]
        self.assertEqual(ranking["symbol"], "QQQ")
        self.assertFalse(ranking["eligible"])
        self.assertIn("shadow_only_symbol", ranking["blockers"])


if __name__ == "__main__":
    unittest.main()
