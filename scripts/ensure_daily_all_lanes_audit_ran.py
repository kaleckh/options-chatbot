from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "scripts" / "audit_regular_guardrail_starvation.py"
LATEST_AUDIT_JSON = ROOT / "data" / "forward-tracking" / "regular_guardrail_starvation_latest.json"

try:
    import options_chatbot as oc
    from supervised_scan import SCAN_PLAYBOOKS
except Exception:
    oc = None
    SCAN_PLAYBOOKS = {}

try:
    from us_equity_market_calendar import is_us_equity_market_day
except Exception:

    def is_us_equity_market_day(value: date) -> bool:
        return value.weekday() < 5

from scripts.pending_audit_candidates import append_pending_candidate_rows


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)


def _default_watchlist_size() -> int:
    return len(getattr(oc, "DEFAULT_WATCHLIST", []) or [])


def _generated_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().date()
    except ValueError:
        return None


def _audit_is_complete_for_date(scan_date: date, *, path: Path = LATEST_AUDIT_JSON) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    overall = payload.get("overall") if isinstance(payload.get("overall"), dict) else {}
    errors = list(payload.get("errors") or [])
    generated = _generated_date(payload.get("generated_at_utc"))
    expected_playbooks = len(SCAN_PLAYBOOKS)
    completed = int(overall.get("playbooks_completed") or 0)
    requested = int(overall.get("playbooks_requested") or 0)
    watchlist_size = int(settings.get("watchlist_size") or 0)
    expected_watchlist_size = _default_watchlist_size()

    if generated != scan_date:
        return None
    if str(payload.get("scope") or "") != "all_supervised_guardrail_starvation":
        return None
    if not bool(settings.get("include_commodity_playbooks")):
        return None
    if not bool(settings.get("audit_all_configured_tickers")):
        return None
    if expected_playbooks and (requested < expected_playbooks or completed < expected_playbooks):
        return None
    if expected_watchlist_size and watchlist_size < expected_watchlist_size:
        return None
    if errors:
        return None
    return payload


def _run_audit() -> int:
    if not AUDIT_SCRIPT.exists():
        print(f"All-lanes audit script missing: {AUDIT_SCRIPT}")
        return 2
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        "--include-commodity",
        "--watchlist-size",
        str(_default_watchlist_size()),
    ]
    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    return int(completed.returncode)


def _queue_candidates(payload: dict[str, object] | None, *, dry_run: bool = False) -> dict[str, object] | None:
    if not payload:
        return None
    if dry_run:
        from scripts.pending_audit_candidates import build_pending_candidate_rows

        rows = build_pending_candidate_rows(payload)
        return {
            "selected_clear_candidates": len(rows),
            "queued_new_candidates": 0,
            "duplicate_candidates": 0,
            "dry_run": True,
        }
    return append_pending_candidate_rows(payload)


def _print_queue_summary(prefix: str, summary: dict[str, object] | None) -> None:
    if not summary:
        return
    print(
        f"{prefix} selected_clear_candidates={summary.get('selected_clear_candidates')} "
        f"queued_new={summary.get('queued_new_candidates')} "
        f"pending_live_validation={summary.get('pending_live_validation')} "
        f"diagnostic_only={summary.get('diagnostic_only_unapproved_lane')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure today's read-only all-supervised all-ticker scan audit has run."
    )
    parser.add_argument("--date", dest="scan_date", help="YYYY-MM-DD date to check; defaults to today.")
    parser.add_argument("--force", action="store_true", help="Run the audit even if today's artifact exists.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without running the audit.")
    args = parser.parse_args(argv)

    scan_date = _parse_date(args.scan_date)
    stamp = datetime.now().isoformat(timespec="seconds")
    if not is_us_equity_market_day(scan_date):
        print(f"{stamp} skip market-closed all_lanes_audit_date={scan_date.isoformat()}")
        return 0

    existing = _audit_is_complete_for_date(scan_date)
    if existing and not args.force:
        overall = existing.get("overall") if isinstance(existing.get("overall"), dict) else {}
        queue_summary = _queue_candidates(existing, dry_run=args.dry_run)
        print(
            f"{stamp} ok all_lanes_audit_date={scan_date.isoformat()} "
            f"playbooks={overall.get('playbooks_completed')}/{overall.get('playbooks_requested')} "
            f"candidates={overall.get('candidate_count_total')} returned={overall.get('returned_count_total')}"
        )
        _print_queue_summary(f"{stamp} candidate_queue", queue_summary)
        return 0

    reason = "forced" if args.force else "missing or incomplete all-lanes audit"
    print(f"{stamp} {reason}; running all_lanes_audit_date={scan_date.isoformat()}")
    if args.dry_run:
        dry_existing = _audit_is_complete_for_date(scan_date)
        _print_queue_summary(f"{stamp} candidate_queue_dry_run", _queue_candidates(dry_existing, dry_run=True))
        print("dry-run: all-lanes audit not started")
        return 0

    exit_code = _run_audit()
    if exit_code != 0:
        return exit_code

    recorded = _audit_is_complete_for_date(scan_date)
    if recorded:
        overall = recorded.get("overall") if isinstance(recorded.get("overall"), dict) else {}
        queue_summary = _queue_candidates(recorded)
        print(
            f"{datetime.now().isoformat(timespec='seconds')} ok "
            f"all_lanes_audit_date={scan_date.isoformat()} "
            f"playbooks={overall.get('playbooks_completed')}/{overall.get('playbooks_requested')} "
            f"candidates={overall.get('candidate_count_total')} returned={overall.get('returned_count_total')}"
        )
        _print_queue_summary(f"{datetime.now().isoformat(timespec='seconds')} candidate_queue", queue_summary)
        return 0
    print(f"{datetime.now().isoformat(timespec='seconds')} audit completed but no valid all-lanes artifact was recorded")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
