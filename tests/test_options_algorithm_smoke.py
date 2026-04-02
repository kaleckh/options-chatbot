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


if __name__ == "__main__":
    unittest.main()
