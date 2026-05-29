from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
LOG_SCAN_SCRIPT = ROOT / "scripts" / "log_scan_picks.py"
try:
    from supervised_scan import DEFAULT_SCAN_PLAYBOOK_ID
except Exception:
    DEFAULT_SCAN_PLAYBOOK_ID = "bullish_pullback_observation"
try:
    from us_equity_market_calendar import is_us_equity_market_day
except Exception:
    def is_us_equity_market_day(value: date) -> bool:
        return value.weekday() < 5


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)


def _ledger_db_path() -> Path:
    override = os.getenv("FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH")
    if override:
        return Path(override)
    legacy_override = os.getenv("FORWARD_OPTIONS_LEDGER_DB_PATH")
    if legacy_override:
        legacy_path = Path(legacy_override)
        stem = legacy_path.stem or "forward_tracking"
        return legacy_path.with_name(f"{stem}_authoritative{legacy_path.suffix or '.db'}")
    return DEFAULT_LEDGER_DB


def _has_scheduled_scan(scan_date: date, playbook: str, db_path: Path) -> dict[str, object] | None:
    if not db_path.exists():
        return None
    run_prefix = f"scheduled_scan:{scan_date.isoformat()}:%"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT id, recorded_at_utc, playbook, scan_picks_count, eligibility_status
                FROM forward_sessions
                WHERE source_label = 'scheduled_scan'
                  AND run_id LIKE ?
                  AND playbook = ?
                ORDER BY recorded_at_utc DESC, id DESC
                LIMIT 1
                """,
                (run_prefix, playbook),
            ).fetchone()
    except sqlite3.Error as exc:
        print(f"Ledger check failed: {exc}")
        return None
    return dict(row) if row else None


def _run_scan(playbook: str) -> int:
    if not LOG_SCAN_SCRIPT.exists():
        print(f"Scan script missing: {LOG_SCAN_SCRIPT}")
        return 2
    env = os.environ.copy()
    env["OPTIONS_SCAN_PLAYBOOK"] = playbook
    completed = subprocess.run(
        [sys.executable, str(LOG_SCAN_SCRIPT)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the scheduled options scan if today's ledger session is missing."
    )
    parser.add_argument("--date", dest="scan_date", help="YYYY-MM-DD date to check; defaults to today.")
    parser.add_argument("--playbook", default=os.getenv("OPTIONS_SCAN_PLAYBOOK") or DEFAULT_SCAN_PLAYBOOK_ID)
    parser.add_argument("--force", action="store_true", help="Run the scan even if today's ledger session exists.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without running the scan.")
    args = parser.parse_args(argv)

    scan_date = _parse_date(args.scan_date)
    if not is_us_equity_market_day(scan_date):
        print(f"{datetime.now().isoformat(timespec='seconds')} skip market-closed scan_date={scan_date.isoformat()}")
        return 0

    db_path = _ledger_db_path()
    existing = _has_scheduled_scan(scan_date, args.playbook, db_path)
    stamp = datetime.now().isoformat(timespec="seconds")

    if existing and not args.force:
        print(
            f"{stamp} ok scan_date={scan_date.isoformat()} "
            f"session={existing.get('id')} picks={existing.get('scan_picks_count')} "
            f"recorded_at_utc={existing.get('recorded_at_utc')}"
        )
        return 0

    reason = "forced" if args.force else "missing ledger session"
    print(f"{stamp} {reason}; running scan_date={scan_date.isoformat()} playbook={args.playbook}")
    if args.dry_run:
        print("dry-run: scan not started")
        return 0
    exit_code = _run_scan(args.playbook)
    if exit_code != 0:
        return exit_code
    recorded = _has_scheduled_scan(scan_date, args.playbook, db_path)
    if recorded:
        print(
            f"{datetime.now().isoformat(timespec='seconds')} ok scan_date={scan_date.isoformat()} "
            f"session={recorded.get('id')} picks={recorded.get('scan_picks_count')} "
            f"recorded_at_utc={recorded.get('recorded_at_utc')}"
        )
        return 0
    print(f"{datetime.now().isoformat(timespec='seconds')} scan completed but no scheduled ledger session was recorded")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
