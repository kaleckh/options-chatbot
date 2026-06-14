from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_host_policy import evidence_host_status  # noqa: E402
from scripts.operational_provenance import build_operational_provenance, utc_now_iso  # noqa: E402

try:
    from us_equity_market_calendar import is_us_equity_market_day
except Exception:  # pragma: no cover - fallback for isolated tests
    is_us_equity_market_day = None  # type: ignore[assignment]


REPORT_ID = "scheduled_scan_heartbeat"
DEFAULT_HEARTBEAT_PATH = ROOT / "data" / "forward-tracking" / "scheduled_scan_heartbeat_latest.json"
DEFAULT_STALE_MARKET_DAY_LIMIT = 2


def _is_market_day(value: date) -> bool:
    if is_us_equity_market_day is None:
        return value.weekday() < 5
    try:
        return bool(is_us_equity_market_day(value))
    except Exception:
        return value.weekday() < 5


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def market_days_since(last_run_at_utc: str | None, *, as_of_utc: str | None = None) -> int | None:
    parsed = _parse_datetime(last_run_at_utc)
    if parsed is None:
        return None
    as_of = _parse_datetime(as_of_utc) or datetime.now(UTC)
    current = parsed.date() + timedelta(days=1)
    end = as_of.date()
    count = 0
    while current <= end:
        if _is_market_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def build_scan_heartbeat(
    *,
    status: str,
    scan_date: str | None = None,
    run_started_at_utc: str | None = None,
    run_completed_at_utc: str | None = None,
    details: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed = run_completed_at_utc or utc_now_iso()
    run_provenance = provenance or build_operational_provenance(run_id_prefix="scheduled_scan")
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": completed,
        "scan_date": scan_date,
        "run_started_at_utc": run_started_at_utc,
        "run_completed_at_utc": completed,
        "host": run_provenance.get("host"),
        "commit_sha": run_provenance.get("commit_sha"),
        "short_commit_sha": run_provenance.get("short_commit_sha"),
        "branch": run_provenance.get("branch"),
        "run_id": run_provenance.get("run_id"),
        "evidence_host": evidence_host_status(current_host=str(run_provenance.get("host") or "")),
        "details": dict(details or {}),
    }


def write_scan_heartbeat(
    *,
    status: str,
    heartbeat_path: Path = DEFAULT_HEARTBEAT_PATH,
    scan_date: str | None = None,
    run_started_at_utc: str | None = None,
    run_completed_at_utc: str | None = None,
    details: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_scan_heartbeat(
        status=status,
        scan_date=scan_date,
        run_started_at_utc=run_started_at_utc,
        run_completed_at_utc=run_completed_at_utc,
        details=details,
        provenance=provenance,
    )
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_scan_heartbeat(path: Path = DEFAULT_HEARTBEAT_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path), "error": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "path": str(path), "error": f"unreadable:{type(exc).__name__}"}
    if not isinstance(payload, dict):
        return {"available": False, "path": str(path), "error": "json_root_not_object"}
    payload.setdefault("available", True)
    payload.setdefault("path", str(path))
    return payload


def build_scan_heartbeat_health(
    *,
    heartbeat_path: Path = DEFAULT_HEARTBEAT_PATH,
    as_of_utc: str | None = None,
    stale_market_day_limit: int = DEFAULT_STALE_MARKET_DAY_LIMIT,
) -> dict[str, Any]:
    heartbeat = load_scan_heartbeat(heartbeat_path)
    generated = heartbeat.get("run_completed_at_utc") or heartbeat.get("generated_at_utc")
    days = market_days_since(str(generated or ""), as_of_utc=as_of_utc)
    if not heartbeat.get("available"):
        status = "missing"
        state = "fail"
    elif days is None:
        status = "unusable_timestamp"
        state = "fail"
    elif days > int(stale_market_day_limit):
        status = "stale"
        state = "fail"
    else:
        status = "fresh"
        state = "pass"
    return {
        "report_id": "scheduled_scan_heartbeat_health",
        "status": status,
        "state": state,
        "heartbeat_path": str(heartbeat_path),
        "heartbeat_available": bool(heartbeat.get("available")),
        "last_run_at_utc": generated,
        "last_status": heartbeat.get("status"),
        "last_host": heartbeat.get("host"),
        "last_commit_sha": heartbeat.get("commit_sha"),
        "days_since_last_scheduled_scan": days,
        "stale_market_day_limit": int(stale_market_day_limit),
        "as_of_utc": as_of_utc or utc_now_iso(),
        "blocker": (
            None
            if status == "fresh"
            else "scheduled_scan_heartbeat_missing_or_stale"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or inspect the scheduled scan heartbeat.")
    parser.add_argument("--status", default="manual_probe")
    parser.add_argument("--scan-date", default=None)
    parser.add_argument("--heartbeat-path", type=Path, default=DEFAULT_HEARTBEAT_PATH)
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.health:
        payload = build_scan_heartbeat_health(heartbeat_path=args.heartbeat_path)
    elif args.no_write:
        payload = build_scan_heartbeat(status=args.status, scan_date=args.scan_date)
    else:
        payload = write_scan_heartbeat(
            status=args.status,
            scan_date=args.scan_date,
            heartbeat_path=args.heartbeat_path,
        )

    if args.json or args.health:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {payload.get('status')} {payload.get('generated_at_utc')}")
    return 0 if payload.get("state") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
