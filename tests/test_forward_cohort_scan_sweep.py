import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.run_forward_cohort_scan_sweep as sweep


class ForwardCohortScanSweepTests(unittest.TestCase):
    def test_requested_playbooks_prefers_forward_cohort_contract_lanes(self):
        contract = {
            "contract_id": "forward-cohort-preregistration",
            "status": "active",
            "cohort": {"frozen": True},
            "lanes": [
                {"lane_id": "volatility_expansion_observation"},
                {"lane_id": "bullish_pullback_observation"},
            ],
        }
        with patch.object(sweep, "load_forward_cohort_preregistration", return_value=contract):
            self.assertEqual(
                sweep.requested_playbooks(),
                ["volatility_expansion_observation", "bullish_pullback_observation"],
            )

    def test_requested_playbooks_accepts_comma_override(self):
        self.assertEqual(
            sweep.requested_playbooks("bullish_pullback_observation,volatility_expansion_observation"),
            ["bullish_pullback_observation", "volatility_expansion_observation"],
        )

    def test_run_passive_scan_disables_auto_track_in_child_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            script = root / "log_scan_picks.py"
            script.write_text("print('scan')\n", encoding="utf-8")

            completed = type("Completed", (), {"returncode": 0})()
            with (
                patch.object(sweep, "ROOT", root),
                patch.object(sweep, "LOG_SCAN_SCRIPT", script),
                patch.object(sweep.subprocess, "run", return_value=completed) as run,
            ):
                result = sweep._run_passive_scan("volatility_expansion_observation")

            self.assertEqual(result, 0)
            self.assertEqual(run.call_args.kwargs["cwd"], str(root))
            child_env = run.call_args.kwargs["env"]
            self.assertEqual(child_env["OPTIONS_SCAN_PLAYBOOK"], "volatility_expansion_observation")
            self.assertEqual(child_env["OPTIONS_SCAN_AUTO_TRACK"], "0")
            self.assertEqual(child_env["OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS"], "1")
            self.assertEqual(child_env["OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE"], "1")

    def test_main_skips_exchange_holiday_before_running_scans(self):
        with patch.object(sweep, "_run_passive_scan") as run_scan:
            result = sweep.main(["--date", "2026-05-25", "--dry-run"])

        self.assertEqual(result, 0)
        run_scan.assert_not_called()

    def test_direct_script_execution_dry_run_resolves_cohort_lanes(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(sweep.__file__)),
                "--date",
                "2026-06-26",
                "--force",
                "--dry-run",
            ],
            cwd=str(Path(sweep.__file__).parent),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("passive forward-cohort scan playbook=volatility_expansion_observation", completed.stdout)
        self.assertIn("passive forward-cohort scan playbook=bullish_pullback_observation", completed.stdout)


if __name__ == "__main__":
    unittest.main()
