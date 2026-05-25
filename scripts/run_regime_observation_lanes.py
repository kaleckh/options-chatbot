from __future__ import annotations

import os
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_SCRIPT = ROOT / "scripts" / "log_scan_picks.py"
DEFAULT_PLAYBOOKS = (
    "bearish_index_put_observation",
    "range_breakout_observation",
    "volatility_expansion_observation",
    "ai_commodity_infra_observation",
)


def _requested_playbooks() -> list[str]:
    raw = os.getenv("OPTIONS_OBSERVATION_PLAYBOOKS", "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_PLAYBOOKS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run market-regime candidate scan lanes.")
    parser.add_argument("--dry-run", action="store_true", help="Print the playbooks without starting scans.")
    args = parser.parse_args(argv)

    if not SCAN_SCRIPT.exists():
        print(f"Missing scan script: {SCAN_SCRIPT}")
        return 2

    exit_code = 0
    for playbook in _requested_playbooks():
        print(f"{datetime.now().isoformat(timespec='seconds')} starting candidate playbook={playbook}")
        if args.dry_run:
            print(f"dry-run: skipped candidate playbook={playbook}")
            continue
        env = os.environ.copy()
        env["OPTIONS_SCAN_PLAYBOOK"] = playbook
        env["OPTIONS_SCAN_AUTO_TRACK"] = "0"
        completed = subprocess.run(
            [sys.executable, str(SCAN_SCRIPT)],
            cwd=str(ROOT),
            env=env,
            check=False,
        )
        print(
            f"{datetime.now().isoformat(timespec='seconds')} finished candidate "
            f"playbook={playbook} exit_code={completed.returncode}"
        )
        if completed.returncode != 0 and exit_code == 0:
            exit_code = int(completed.returncode)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
