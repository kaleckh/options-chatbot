from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_env import load_local_env
from scripts.pending_audit_candidates import (
    DEFAULT_DISPOSITION_FILE,
    DEFAULT_FILL_ATTEMPT_FILE,
    DEFAULT_QUEUE_FILE,
    append_validation_attempt_rows,
    latest_candidate_rows,
    write_validation_disposition_report,
)
from supervised_scan import scan_playbook_fresh_live_validation_enabled
from us_equity_market_calendar import is_us_equity_market_day


LOG_SCAN_SCRIPT = ROOT / "scripts" / "log_scan_picks.py"


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)


def _candidate_scan_date(row: dict[str, Any]) -> str:
    generated = str(row.get("audit_generated_at_utc") or "").strip()
    if generated:
        return generated[:10]
    recorded = str(row.get("queue_recorded_at_utc") or "").strip()
    return recorded[:10]


def pending_playbooks_for_date(scan_date: date, *, queue_file: Path = DEFAULT_QUEUE_FILE) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in latest_candidate_rows(queue_file):
        if str(row.get("candidate_status") or "") != "pending_live_validation":
            continue
        playbook_id = str(row.get("playbook_id") or "").strip()
        if not scan_playbook_fresh_live_validation_enabled(playbook_id):
            continue
        if _candidate_scan_date(row) != scan_date.isoformat():
            continue
        grouped[playbook_id].append(row)
    return dict(grouped)


def _market_is_open_now() -> bool:
    load_local_env(ROOT)
    try:
        import options_chatbot as oc

        return bool(oc._market_is_open())
    except Exception:
        return False


def _run_playbook_validation(playbook_id: str) -> int:
    env = dict(os.environ)
    env["OPTIONS_SCAN_PLAYBOOK"] = playbook_id
    env["OPTIONS_SCAN_AUTO_TRACK"] = "1"
    env["OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS"] = "1"
    env["OPTIONS_SCAN_VALIDATION_SOURCE"] = "pending_candidate_queue"
    completed = subprocess.run(
        [sys.executable, str(LOG_SCAN_SCRIPT)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate pending audit candidates during a fresh market-hours scan."
    )
    parser.add_argument("--date", dest="scan_date", help="YYYY-MM-DD audit date to validate; defaults to today.")
    parser.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE_FILE)
    parser.add_argument("--fill-attempt-file", type=Path, default=DEFAULT_FILL_ATTEMPT_FILE)
    parser.add_argument("--disposition-file", type=Path, default=DEFAULT_DISPOSITION_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    scan_date = _parse_date(args.scan_date)
    stamp = datetime.now().isoformat(timespec="seconds")
    if not is_us_equity_market_day(scan_date):
        print(f"{stamp} skip market-closed pending_validation_date={scan_date.isoformat()}")
        return 0
    grouped = pending_playbooks_for_date(scan_date, queue_file=args.queue_file)
    if not grouped:
        print(f"{stamp} no pending candidates for validation date={scan_date.isoformat()}")
        return 0
    if not _market_is_open_now():
        print(
            f"{stamp} skip market-not-open pending_validation_date={scan_date.isoformat()} "
            f"playbooks={','.join(sorted(grouped))}"
        )
        return 0

    print(
        f"{stamp} validating pending candidates date={scan_date.isoformat()} "
        f"playbooks={','.join(sorted(grouped))} candidates={sum(len(rows) for rows in grouped.values())}"
    )
    if args.dry_run:
        print("dry-run: pending candidate validation scans not started")
        return 0

    failures = 0
    for playbook_id in sorted(grouped):
        exit_code = _run_playbook_validation(playbook_id)
        appended = append_validation_attempt_rows(
            grouped[playbook_id],
            queue_file=args.queue_file,
            playbook_id=playbook_id,
            exit_code=exit_code,
        )
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"playbook={playbook_id} validation_status_rows={appended}"
        )
        if exit_code != 0:
            failures += 1
            print(f"{datetime.now().isoformat(timespec='seconds')} playbook={playbook_id} failed exit={exit_code}")
    disposition = write_validation_disposition_report(
        queue_file=args.queue_file,
        fill_attempt_file=args.fill_attempt_file,
        output_file=args.disposition_file,
        scan_date=scan_date.isoformat(),
    )
    print(
        f"{datetime.now().isoformat(timespec='seconds')} "
        f"validation_disposition_file={args.disposition_file} "
        f"candidates={disposition['summary']['candidate_count']}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
