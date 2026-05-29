import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.ensure_scan_picks_ran as ensure_scan_picks_ran


class EnsureScanPicksRanTests(unittest.TestCase):
    def test_direct_script_execution_skips_exchange_holiday(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(ensure_scan_picks_ran.__file__)),
                "--date",
                "2026-05-25",
                "--dry-run",
            ],
            cwd=str(Path(ensure_scan_picks_ran.__file__).parent),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("skip market-closed scan_date=2026-05-25", completed.stdout)

    def test_main_skips_exchange_holiday_before_running_scan(self):
        with patch.object(ensure_scan_picks_ran, "_run_scan") as run_scan:
            result = ensure_scan_picks_ran.main(["--date", "2026-05-25", "--dry-run"])

        self.assertEqual(result, 0)
        run_scan.assert_not_called()

    def test_run_scan_passes_requested_playbook_to_child_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            script = root / "log_scan_picks.py"
            script.write_text("print('scan')\n", encoding="utf-8")

            completed = type("Completed", (), {"returncode": 0})()
            with (
                patch.object(ensure_scan_picks_ran, "ROOT", root),
                patch.object(ensure_scan_picks_ran, "LOG_SCAN_SCRIPT", script),
                patch.object(
                    ensure_scan_picks_ran.subprocess,
                    "run",
                    return_value=completed,
                ) as run,
            ):
                result = ensure_scan_picks_ran._run_scan("short_term")

            self.assertEqual(result, 0)
            self.assertEqual(run.call_args.kwargs["cwd"], str(root))
            self.assertEqual(run.call_args.kwargs["env"]["OPTIONS_SCAN_PLAYBOOK"], "short_term")


if __name__ == "__main__":
    unittest.main()
