from __future__ import annotations

import json
import re
import types
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import audit_regular_guardrail_starvation as starvation
from scripts import ensure_daily_all_lanes_audit_ran as ensure_audit
from scripts import pending_audit_candidates
from scripts import validate_pending_scan_candidates


@contextmanager
def _raises(expected: type[BaseException], *, match: str):
    try:
        yield
    except expected as exc:
        if not re.search(match, str(exc)):
            raise AssertionError(f"{exc!r} did not match {match!r}") from exc
    else:
        raise AssertionError(f"{expected.__name__} was not raised")


class _MonkeyPatch:
    def __init__(self, test_case: unittest.TestCase) -> None:
        self._test_case = test_case

    def setattr(self, target: object, name: str, value: object) -> None:
        patcher = patch.object(target, name, value)
        patcher.start()
        self._test_case.addCleanup(patcher.stop)


def test_starvation_audit_can_include_every_supervised_playbook() -> None:
    regular_playbooks = starvation._parse_playbooks(None)
    all_playbooks = starvation._parse_playbooks(None, include_commodity=True)

    assert "ai_commodity_infra_observation" not in regular_playbooks
    assert "ai_commodity_infra_observation" in all_playbooks
    assert set(all_playbooks) == set(starvation.SCAN_PLAYBOOKS)


def test_starvation_audit_rejects_commodity_without_explicit_all_lanes_flag() -> None:
    with _raises(ValueError, match="Commodity playbooks"):
        starvation._parse_playbooks("ai_commodity_infra_observation")

    assert starvation._parse_playbooks(
        "ai_commodity_infra_observation",
        include_commodity=True,
    ) == ["ai_commodity_infra_observation"]


def _write_latest(path: Path, **overrides: object) -> None:
    payload = {
        "generated_at_utc": "2026-06-02T17:30:00Z",
        "scope": "all_supervised_guardrail_starvation",
        "errors": [],
        "overall": {
            "playbooks_completed": 2,
            "playbooks_requested": 2,
            "candidate_count_total": 0,
            "returned_count_total": 0,
        },
        "settings": {
            "include_commodity_playbooks": True,
            "audit_all_configured_tickers": True,
            "watchlist_size": 2,
        },
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf8")


def test_daily_all_lanes_artifact_must_be_complete_for_the_market_day(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    latest = tmp_path / "latest.json"
    monkeypatch.setattr(ensure_audit, "SCAN_PLAYBOOKS", {"short_term": {}, "ai_commodity_infra_observation": {}})
    monkeypatch.setattr(ensure_audit, "oc", types.SimpleNamespace(DEFAULT_WATCHLIST=["SPY", "QQQ"]))

    _write_latest(latest)
    assert ensure_audit._audit_is_complete_for_date(date(2026, 6, 2), path=latest) is not None

    _write_latest(latest, scope="regular_supervised_guardrail_starvation")
    assert ensure_audit._audit_is_complete_for_date(date(2026, 6, 2), path=latest) is None

    _write_latest(latest, settings={"include_commodity_playbooks": False, "audit_all_configured_tickers": True, "watchlist_size": 2})
    assert ensure_audit._audit_is_complete_for_date(date(2026, 6, 2), path=latest) is None

    _write_latest(latest, overall={"playbooks_completed": 1, "playbooks_requested": 2})
    assert ensure_audit._audit_is_complete_for_date(date(2026, 6, 2), path=latest) is None


def test_daily_all_lanes_runner_launches_include_commodity_audit(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    script = tmp_path / "audit_regular_guardrail_starvation.py"
    script.write_text("pass", encoding="utf8")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> types.SimpleNamespace:
        calls.append(command)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(ensure_audit, "AUDIT_SCRIPT", script)
    monkeypatch.setattr(ensure_audit, "_default_watchlist_size", lambda: 59)
    monkeypatch.setattr(ensure_audit.subprocess, "run", fake_run)

    assert ensure_audit._run_audit() == 0
    assert calls
    assert "--include-commodity" in calls[0]
    assert calls[0][calls[0].index("--watchlist-size") + 1] == "59"


def test_pending_candidate_queue_records_clear_approved_lane_and_ignores_blocked(
    tmp_path: Path,
) -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": False},
        "playbooks": [
            {
                "playbook_id": "swing",
                "label": "Swing",
                "returned_picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "long_strike": 760.0,
                        "short_strike": 780.0,
                        "net_debit": 7.58,
                        "guardrail_decision": "clear",
                        "candidate_execution_label": "executable_opra_paper_candidate",
                    },
                    {
                        "ticker": "QQQ",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "guardrail_decision": "blocked",
                    },
                ],
            }
        ],
    }

    queue_file = tmp_path / "pending.jsonl"
    summary = pending_audit_candidates.append_pending_candidate_rows(
        report,
        queue_file=queue_file,
        recorded_at_utc="2026-06-02T07:00:00Z",
    )
    rows = [json.loads(line) for line in queue_file.read_text(encoding="utf8").splitlines()]

    assert summary["selected_clear_candidates"] == 1
    assert summary["queued_new_candidates"] == 1
    assert summary["pending_live_validation"] == 1
    assert rows[0]["candidate_status"] == "pending_live_validation"
    assert rows[0]["tracking_approved_lane"] is True
    assert rows[0]["fresh_live_validation_enabled"] is True
    assert rows[0]["position_tracking_mode"] == "auto_track"
    assert rows[0]["ticker"] == "SPY"

    repeat = pending_audit_candidates.append_pending_candidate_rows(
        report,
        queue_file=queue_file,
        recorded_at_utc="2026-06-02T07:01:00Z",
    )
    assert repeat["queued_new_candidates"] == 0
    assert repeat["duplicate_candidates"] == 1


def test_pending_candidate_queue_marks_clear_unapproved_lane_as_diagnostic_only(
    tmp_path: Path,
) -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
        "playbooks": [
            {
                "playbook_id": "ai_commodity_infra_observation",
                "label": "AI Commodity",
                "returned_picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "expiry": "2026-06-08",
                        "guardrail_decision": "clear",
                    }
                ],
            }
        ],
    }

    rows = pending_audit_candidates.build_pending_candidate_rows(report)

    assert len(rows) == 1
    assert rows[0]["candidate_status"] == "diagnostic_only_unapproved_lane"
    assert rows[0]["tracking_approved_lane"] is False


def test_pending_candidate_validation_groups_all_validation_enabled_pending_rows(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "pending.jsonl"
    rows = [
        {
            "audit_generated_at_utc": "2026-06-02T06:39:32Z",
            "candidate_key": "2026-06-02|swing|SPY|call|2026-06-26||||780.0",
            "candidate_status": "pending_live_validation",
            "tracking_approved_lane": True,
            "playbook_id": "swing",
            "ticker": "SPY",
        },
        {
            "audit_generated_at_utc": "2026-06-02T06:39:32Z",
            "candidate_key": "2026-06-02|speculative|QQQ|call|2026-06-08||||750.0",
            "candidate_status": "pending_live_validation",
            "tracking_approved_lane": False,
            "playbook_id": "speculative",
            "ticker": "QQQ",
        },
        {
            "audit_generated_at_utc": "2026-06-01T06:39:32Z",
            "candidate_key": "2026-06-01|short_term|IWM|call|2026-06-20||||220.0",
            "candidate_status": "pending_live_validation",
            "tracking_approved_lane": True,
            "playbook_id": "short_term",
            "ticker": "IWM",
        },
    ]
    queue.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")

    grouped = validate_pending_scan_candidates.pending_playbooks_for_date(
        date(2026, 6, 2),
        queue_file=queue,
    )

    assert set(grouped) == {"swing", "speculative"}
    assert grouped["swing"][0]["ticker"] == "SPY"
    assert grouped["speculative"][0]["ticker"] == "QQQ"


def test_pending_candidate_validation_runs_log_scan_with_caps(
    monkeypatch: object,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(command: list[str], **kwargs: object) -> types.SimpleNamespace:
        calls.append(dict(kwargs["env"]))  # type: ignore[index]
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(validate_pending_scan_candidates.subprocess, "run", fake_run)

    assert validate_pending_scan_candidates._run_playbook_validation("swing") == 0
    assert calls[0]["OPTIONS_SCAN_PLAYBOOK"] == "swing"
    assert calls[0]["OPTIONS_SCAN_AUTO_TRACK"] == "1"
    assert calls[0]["OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS"] == "1"


def test_validation_attempt_resolves_pending_candidate(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "pending.jsonl"
    pending = {
        "audit_generated_at_utc": "2026-06-02T06:39:32Z",
        "candidate_key": "2026-06-02|swing|SPY|call|2026-06-26||||780.0",
        "candidate_status": "pending_live_validation",
        "tracking_approved_lane": True,
        "playbook_id": "swing",
        "ticker": "SPY",
    }
    queue.write_text(json.dumps(pending) + "\n", encoding="utf8")

    appended = pending_audit_candidates.append_validation_attempt_rows(
        [pending],
        queue_file=queue,
        playbook_id="swing",
        exit_code=0,
        recorded_at_utc="2026-06-02T15:00:00Z",
    )
    grouped = validate_pending_scan_candidates.pending_playbooks_for_date(
        date(2026, 6, 2),
        queue_file=queue,
    )

    assert appended == 1
    assert grouped == {}
    latest = pending_audit_candidates.latest_candidate_rows(queue)
    assert latest[0]["candidate_status"] == "live_validation_attempted"


class DailyAllLanesAuditTests(unittest.TestCase):
    def test_starvation_audit_can_include_every_supervised_playbook(self) -> None:
        test_starvation_audit_can_include_every_supervised_playbook()

    def test_starvation_audit_rejects_commodity_without_explicit_all_lanes_flag(self) -> None:
        test_starvation_audit_rejects_commodity_without_explicit_all_lanes_flag()

    def test_daily_all_lanes_artifact_must_be_complete_for_the_market_day(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_daily_all_lanes_artifact_must_be_complete_for_the_market_day(
                Path(temp_dir),
                _MonkeyPatch(self),
            )

    def test_daily_all_lanes_runner_launches_include_commodity_audit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_daily_all_lanes_runner_launches_include_commodity_audit(
                Path(temp_dir),
                _MonkeyPatch(self),
            )

    def test_pending_candidate_queue_records_clear_approved_lane_and_ignores_blocked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_queue_records_clear_approved_lane_and_ignores_blocked(Path(temp_dir))

    def test_pending_candidate_queue_marks_clear_unapproved_lane_as_diagnostic_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_queue_marks_clear_unapproved_lane_as_diagnostic_only(Path(temp_dir))

    def test_pending_candidate_validation_groups_all_validation_enabled_pending_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_validation_groups_all_validation_enabled_pending_rows(Path(temp_dir))

    def test_pending_candidate_validation_runs_log_scan_with_caps(self) -> None:
        test_pending_candidate_validation_runs_log_scan_with_caps(_MonkeyPatch(self))

    def test_validation_attempt_resolves_pending_candidate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_validation_attempt_resolves_pending_candidate(Path(temp_dir))
