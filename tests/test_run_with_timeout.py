from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_with_timeout.py"


class RunWithTimeoutTests(unittest.TestCase):
    def test_returns_child_exit_code_when_command_finishes(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--timeout-seconds",
                "10",
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ],
            cwd=ROOT,
            check=False,
        )

        self.assertEqual(completed.returncode, 7)

    def test_plain_python_uses_wrapper_interpreter(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--timeout-seconds",
                "10",
                "--",
                "python",
                "-c",
                "import sys; print(sys.executable)",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(Path(completed.stdout.strip()).resolve(), Path(sys.executable).resolve())

    def test_returns_timeout_code_when_command_exceeds_limit(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--timeout-seconds",
                "0.5",
                "--",
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )

        self.assertEqual(completed.returncode, 124)
        self.assertIn("Command timed out", completed.stderr)

    def test_timeout_can_be_overridden_for_ci_probes(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--timeout-seconds",
                "10",
                "--",
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
            env={**os.environ, "RUN_WITH_TIMEOUT_SECONDS": "0.5"},
        )

        self.assertEqual(completed.returncode, 124)


if __name__ == "__main__":
    unittest.main()
