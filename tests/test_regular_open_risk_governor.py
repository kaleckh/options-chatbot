from __future__ import annotations

from datetime import UTC, datetime

from scripts.regular_open_risk_governor import (
    regular_open_risk_entry_blockers,
    regular_open_risk_report_health,
)


NOW = datetime(2026, 6, 6, 15, 0, tzinfo=UTC)


def _report(*, status: str = "open_risk_governor_pass", blockers: list[str] | None = None) -> dict:
    return {
        "generated_at_utc": "2026-06-06T14:00:00Z",
        "scope": "regular_supervised_open_positions_read_only",
        "open_risk_governor": {
            "status": status,
            "blockers": blockers or [],
            "live_entry_allowed": status == "open_risk_governor_pass",
        },
    }


def test_open_risk_report_health_requires_governor():
    health = regular_open_risk_report_health(
        {
            "generated_at_utc": "2026-06-06T14:00:00Z",
            "scope": "regular_supervised_open_positions_read_only",
        },
        now_utc=NOW,
    )

    assert health["usable"] is False
    assert health["reason"] == "open_position_risk_report_missing_governor"


def test_open_risk_entry_blockers_prefix_governor_reasons():
    blockers = regular_open_risk_entry_blockers(
        _report(status="open_risk_governor_blocked", blockers=["live_exact_negative_open_risk"]),
        now_utc=NOW,
    )

    assert blockers == [
        "open_position_risk_live_exact_negative_open_risk",
        "open_position_risk_governor_blocked:open_risk_governor_blocked",
    ]


def test_open_risk_entry_blockers_pass_when_governor_passes():
    assert regular_open_risk_entry_blockers(_report(), now_utc=NOW) == []
