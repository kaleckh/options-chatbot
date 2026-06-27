from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_SCAN_SCRIPT = ROOT / "scripts" / "log_scan_picks.py"
DEFAULT_COHORT_PLAYBOOKS = (
    "volatility_expansion_observation",
    "bullish_pullback_observation",
)

from scripts.ensure_scan_picks_ran import _has_scheduled_scan, _ledger_db_path  # noqa: E402
from scripts.forward_cohort_preregistration import (  # noqa: E402
    forward_cohort_lane_ids,
    load_forward_cohort_preregistration,
)

try:
    from us_equity_market_calendar import is_us_equity_market_day
except Exception:
    def is_us_equity_market_day(value: date) -> bool:
        return value.weekday() < 5


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)


def _parse_playbooks(raw: str | None) -> list[str]:
    if not raw:
        return []
    parsed = [item.strip() for item in raw.split(",") if item.strip()]
    return list(dict.fromkeys(parsed))


def _cohort_playbooks() -> list[str]:
    contract = load_forward_cohort_preregistration()
    lanes = forward_cohort_lane_ids(contract)
    return lanes or list(DEFAULT_COHORT_PLAYBOOKS)


def requested_playbooks(raw: str | None = None) -> list[str]:
    return _parse_playbooks(raw) or _cohort_playbooks()


def _run_passive_scan(playbook: str) -> int:
    if not LOG_SCAN_SCRIPT.exists():
        print(f"Scan script missing: {LOG_SCAN_SCRIPT}")
        return 2
    env = os.environ.copy()
    env["OPTIONS_SCAN_PLAYBOOK"] = playbook
    env["OPTIONS_SCAN_AUTO_TRACK"] = "0"
    env["OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS"] = "1"
    env["OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(LOG_SCAN_SCRIPT)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Passively run all frozen forward-cohort scan playbooks for strict forward-audit capture."
    )
    parser.add_argument("--date", dest="scan_date", help="YYYY-MM-DD date to check; defaults to today.")
    parser.add_argument(
        "--playbooks",
        help="Comma-separated override. Defaults to frozen forward-cohort lanes from the preregistration contract.",
    )
    parser.add_argument("--force", action="store_true", help="Run even when today's ledger session exists.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without starting scans.")
    args = parser.parse_args(argv)

    scan_date = _parse_date(args.scan_date)
    playbooks = requested_playbooks(args.playbooks)
    if not playbooks:
        print("No forward-cohort playbooks resolved.")
        return 1
    if not is_us_equity_market_day(scan_date):
        print(f"{datetime.now().isoformat(timespec='seconds')} skip market-closed scan_date={scan_date.isoformat()}")
        return 0

    db_path = _ledger_db_path()
    exit_code = 0
    for playbook in playbooks:
        existing = _has_scheduled_scan(scan_date, playbook, db_path)
        stamp = datetime.now().isoformat(timespec="seconds")
        if existing and not args.force:
            print(
                f"{stamp} ok scan_date={scan_date.isoformat()} playbook={playbook} "
                f"session={existing.get('id')} picks={existing.get('scan_picks_count')} "
                f"recorded_at_utc={existing.get('recorded_at_utc')}"
            )
            continue

        reason = "forced" if args.force else "missing ledger session"
        print(f"{stamp} {reason}; passive forward-cohort scan playbook={playbook}")
        if args.dry_run:
            print(f"dry-run: skipped passive forward-cohort scan playbook={playbook}")
            continue
        result = _run_passive_scan(playbook)
        print(
            f"{datetime.now().isoformat(timespec='seconds')} finished passive forward-cohort scan "
            f"playbook={playbook} exit_code={result}"
        )
        if result != 0 and exit_code == 0:
            exit_code = result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
