import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.ensure_scan_picks_ran as ensure_scan_picks_ran


class EnsureScanPicksRanTests(unittest.TestCase):
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
