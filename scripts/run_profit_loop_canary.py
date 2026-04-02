from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profit_loop_automation import run_profit_loop_canary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the three profit-loop automation steps in sequence.")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--temp-state-dir", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.state_dir and args.temp_state_dir:
        raise SystemExit("--state-dir and --temp-state-dir are mutually exclusive")

    state_dir = args.state_dir
    if args.temp_state_dir:
        state_dir = tempfile.mkdtemp(prefix="profit-loop-canary-")

    result = run_profit_loop_canary(state_dir=state_dir, dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2))
    return int(result.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
