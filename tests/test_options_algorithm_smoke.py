from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.options_algorithm_smoke as smoke


class OptionsAlgorithmSmokeTests(unittest.TestCase):
    def test_fixture_smoke_runs_end_to_end_without_network(self):
        stdout = io.StringIO()
        env = {
            "OPTIONS_SMOKE_PICKS": "2",
            "OPTIONS_SMOKE_LOOKBACK_YEARS": "1",
            "OPTIONS_SMOKE_IV_ADJ": "1.2",
            "OPTIONS_SMOKE_MIN_TRADES": "1",
        }

        with patch.dict(os.environ, env, clear=False), patch.object(
            sys, "argv", ["options_algorithm_smoke.py", "--fixture"]
        ), redirect_stdout(stdout):
            code = smoke.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual(payload["window_mode"], "full")
        self.assertGreater(payload["backtest_total_trades"], 0)
        self.assertGreater(payload["experiment_candidates"], 0)
        self.assertGreaterEqual(payload["scan_candidate_count"], 1)
        self.assertGreaterEqual(payload["scan_returned_count"], 1)
        self.assertGreaterEqual(payload["scan_candidate_count"], payload["scan_returned_count"])
        self.assertEqual(payload["scan_truth_lane"], "historical_imported_daily")
        self.assertFalse(payload["scan_policy_fail_closed"])
        self.assertEqual(payload["backtest_truth_source"], "synthetic_research")
        self.assertIn(payload["live_policy_truth_source"], {"synthetic_research", "historical_imported_daily", "historical_imported"})
        self.assertIsNotNone(payload["scan_top_ticker"])
        self.assertEqual(payload["scan_top_guardrail_decision"], "clear")
        self.assertIsNone(payload["scan_top_calibrated_expectancy_pct"])
        self.assertIn(payload["live_policy_promotion_status"], {"promote", "watch", "block"})
        self.assertEqual(payload["scan_calibrated_expectancy_count"], 0)


if __name__ == "__main__":
    unittest.main()
