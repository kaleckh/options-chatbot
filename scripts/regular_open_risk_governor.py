from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPEN_RISK_REPORT = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_OPEN_RISK_MAX_AGE_HOURS = 24.0
EXPECTED_SCOPE = "regular_supervised_open_positions_read_only"
OPEN_RISK_GOVERNOR_PASS = "open_risk_governor_pass"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _parse_utc_datetime(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_regular_open_risk_report(path: Path | str | None = DEFAULT_OPEN_RISK_REPORT) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def regular_open_risk_report_health(
    report: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_age_hours: float = DEFAULT_OPEN_RISK_MAX_AGE_HOURS,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "usable": False,
            "reason": "open_position_risk_report_missing",
            "generated_at_utc": None,
            "age_hours": None,
            "max_age_hours": max_age_hours,
        }
    generated = _parse_utc_datetime(report.get("generated_at_utc"))
    if generated is None:
        return {
            "usable": False,
            "reason": "open_position_risk_report_missing_generated_at_utc",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": None,
            "max_age_hours": max_age_hours,
        }
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    age_hours = (now - generated).total_seconds() / 3600.0
    if age_hours < -0.25:
        return {
            "usable": False,
            "reason": "open_position_risk_report_generated_in_future",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if age_hours > max_age_hours:
        return {
            "usable": False,
            "reason": "open_position_risk_report_stale",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if report.get("scope") != EXPECTED_SCOPE:
        return {
            "usable": False,
            "reason": "open_position_risk_report_wrong_scope",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
            "scope": report.get("scope"),
        }
    governor = report.get("open_risk_governor")
    if not isinstance(governor, dict):
        return {
            "usable": False,
            "reason": "open_position_risk_report_missing_governor",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    return {
        "usable": True,
        "reason": "open_position_risk_report_fresh",
        "generated_at_utc": report.get("generated_at_utc"),
        "age_hours": round(age_hours, 4),
        "max_age_hours": max_age_hours,
        "governor_status": governor.get("status"),
        "governor_blockers": list(governor.get("blockers") or []),
    }


def regular_open_risk_entry_blockers(
    report: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_age_hours: float = DEFAULT_OPEN_RISK_MAX_AGE_HOURS,
) -> list[str]:
    health = regular_open_risk_report_health(report, now_utc=now_utc, max_age_hours=max_age_hours)
    if not bool(health.get("usable")):
        return [f"open_position_risk_report_unusable:{health.get('reason') or 'unknown'}"]
    governor = report.get("open_risk_governor") if isinstance(report, dict) else {}
    governor = governor if isinstance(governor, dict) else {}
    blockers: list[str] = []
    for blocker in list(governor.get("blockers") or []):
        family = _norm(blocker)
        if family:
            blockers.append(f"open_position_risk_{family}")
    if governor.get("status") != OPEN_RISK_GOVERNOR_PASS:
        blockers.append(f"open_position_risk_governor_blocked:{governor.get('status') or 'unknown'}")
    return list(dict.fromkeys(blockers))
