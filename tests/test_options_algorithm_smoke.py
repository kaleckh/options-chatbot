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
        self.assertGreaterEqual(payload["post_backtest_scan_picks"], 1)
        self.assertGreaterEqual(payload["post_backtest_scan_calibrated_expectancy_count"], 1)
        self.assertIsNotNone(payload["post_backtest_scan_top_calibrated_expectancy_pct"])
        self.assertIn(payload["live_policy_promotion_status"], {"promote", "watch", "block"})
        self.assertEqual(payload["scan_calibrated_expectancy_count"], 0)
        self.assertIn("runtime_context", payload)
        self.assertIn("artifact_health", payload)
        self.assertIn("truth_lane_health", payload)
        self.assertIn("doc_parity", payload)

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["repo_root"], str(smoke.ROOT.resolve()))
        self.assertTrue(runtime["interpreter_path"])
        self.assertTrue(runtime["python_version"])
        self.assertIn("venv_active", runtime)
        self.assertIn("uv_available", runtime)
        self.assertIn("git_changed_files", runtime)

        truth_lane_health = payload["truth_lane_health"]
        self.assertEqual(
            truth_lane_health["default_fallback_order"],
            ["archived_forward_daily", "historical_imported", "historical_imported_daily", "synthetic_research"],
        )
        self.assertIn(
            truth_lane_health["default_selected_truth_source"],
            {"historical_imported_daily", "synthetic_research"},
        )
        self.assertEqual(truth_lane_health["synthetic_research"]["status"], "loadable")
        self.assertIn(
            truth_lane_health["historical_imported"]["status"],
            {"missing_artifact", "missing_recorded_truth_store", "missing_current_store", "loadable"},
        )
        self.assertIn(
            truth_lane_health["historical_imported_daily"]["status"],
            {"missing_artifact", "loadable"},
        )
        self.assertIn(
            truth_lane_health["archived_forward_daily"]["status"],
            {"missing_artifact", "loadable"},
        )

        artifact_health = payload["artifact_health"]
        self.assertTrue(artifact_health["wfo_results"]["present"])
        self.assertIn("archived_forward_daily_latest", artifact_health)
        self.assertIn("forward_truth_db", artifact_health)

        doc_parity = payload["doc_parity"]
        self.assertIn("current_state_doc_present", doc_parity)
        self.assertIn("mismatches", doc_parity)


if __name__ == "__main__":
    unittest.main()
