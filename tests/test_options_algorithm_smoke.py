import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.options_algorithm_smoke as smoke


class OptionsAlgorithmSmokeTests(unittest.TestCase):
    def test_fixture_entrypoint_dispatches_without_running_full_fixture_smoke(self):
        stdout = io.StringIO()
        fake_summary = {
            "scan_truth_lane": "historical_imported_daily",
            "live_policy_truth_source": "synthetic_research",
            "live_policy_promotion_status": "watch",
            "forward_truth_runtime_db_path": str(Path.cwd() / "forward_tracking_fixture.db"),
        }

        with patch.dict(os.environ, {}, clear=False), \
             patch.object(sys, "argv", ["options_algorithm_smoke.py", "--fixture"]), \
             patch.object(smoke, "_run_fixture_smoke", return_value=fake_summary) as fixture_runner, \
             patch.object(smoke, "_run_live_smoke") as live_runner, \
             patch.object(smoke, "_runtime_context", return_value={"repo_root": str(smoke.ROOT.resolve())}), \
             patch.object(smoke.wfo, "build_truth_lane_health_summary", return_value={"paths": {}}), \
             patch.object(smoke, "_artifact_health", return_value={"wfo_results": {"present": True}}), \
             patch.object(smoke, "_doc_parity", return_value={"current_state_doc_present": True, "mismatches": []}), \
             redirect_stdout(stdout):
            code = smoke.main()

        self.assertEqual(code, 0)
        fixture_runner.assert_called_once()
        live_runner.assert_not_called()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual(payload["window_mode"], "full")
        self.assertEqual(payload["scan_truth_lane"], "historical_imported_daily")
        self.assertEqual(payload["live_policy_promotion_status"], "watch")
        self.assertEqual(Path(payload["forward_truth_runtime_db_path"]).name, "forward_tracking_fixture.db")

    def test_fixture_smoke_uses_live_scan_truth_lane_and_current_truth_store(self):
        bundle = smoke.build_options_algorithm_fixture_bundle()
        backend = SimpleNamespace(
            app=FastAPI(),
            LIVE_SCAN_TRUTH_LANE="historical_imported_daily",
            POSITIONS_REPOSITORY=None,
        )

        class _FakeClient:
            def __init__(self, app):
                self.app = app

            def close(self):
                return None

        def _capture(client, **kwargs):
            self.assertEqual(kwargs["policy_truth_lane"], "historical_imported_daily")
            self.assertEqual(os.environ["HISTORICAL_OPTIONS_DB_PATH"], "C:/truth/options_history.db")
            return {
                "scan_truth_lane": "historical_imported_daily",
                "live_policy_truth_source": "historical_imported_daily",
                "live_policy_promotion_status": "watch",
            }

        with patch.object(smoke, "_fixture_truth_store_db_path", return_value="C:/truth/options_history.db"), \
             patch.object(smoke, "load_backend_main", return_value=backend), \
             patch.object(smoke, "TestClient", side_effect=_FakeClient), \
             patch.object(smoke, "_run_smoke_sequence", side_effect=_capture), \
             patch.object(smoke, "init_forward_ledger"), \
             patch.object(smoke.oc, "DEFAULT_WATCHLIST", bundle.watchlist), \
             patch.object(smoke.wfo, "DEFAULT_WATCHLIST", bundle.watchlist), \
             patch.object(smoke.oc.yf, "Ticker", side_effect=bundle.make_ticker), \
             patch.object(smoke.wfo.yf, "Ticker", side_effect=bundle.make_ticker), \
             patch.object(smoke.mds.yf, "Ticker", side_effect=bundle.make_ticker), \
             patch.object(smoke.oc, "datetime", smoke.FrozenDateTime), \
             patch.object(smoke.wfo, "datetime", smoke.FrozenDateTime), \
             patch.object(smoke.mds, "datetime", smoke.FrozenDateTime), \
             patch.object(smoke.oc, "_market_is_open", return_value=False), \
             patch.object(smoke.oc, "_load_expectancy_surface_for_live", return_value=None), \
             patch.object(smoke.wfo, "WFO_RESULTS_FILE", str(ROOT / "tmp_wfo_results.json")), \
             patch.dict(os.environ, {}, clear=False):
            summary = smoke._run_fixture_smoke(
                scan_picks=3,
                lookback_years=1,
                iv_adj=1.2,
                min_trades=20,
            )

        self.assertEqual(summary["live_policy_truth_source"], "historical_imported_daily")
        self.assertEqual(summary["fixture_truth_store_db_path"], "C:/truth/options_history.db")


if __name__ == "__main__":
    unittest.main()
