from __future__ import annotations

import json
import re
import types
import unittest
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.lane_profitability_gate import (
    LANE_GATE_PROBATION_PAPER_STATUS,
    candidate_gate_decision,
    lane_gate_report_health,
)
from scripts.lane_promotion_state import LANE_PROMOTION_PAPER_EVIDENCE_STATUS, LANE_PROMOTION_PAPER_ONLY_STATUS
from scripts import audit_regular_guardrail_starvation as starvation
from scripts import ensure_daily_all_lanes_audit_ran as ensure_audit
from scripts import pending_audit_candidates
from scripts import validate_pending_scan_candidates
import supervised_scan


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


def test_pending_candidate_queue_records_clear_regular_auto_track_lane_and_ignores_blocked(
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


def test_pending_candidate_queue_marks_clear_separate_nontracking_lane_as_diagnostic_only(
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


def test_pending_candidate_queue_honors_lane_profitability_gate(
    tmp_path: Path,
) -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
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
                    }
                ],
            },
            {
                "playbook_id": "volatility_expansion_observation",
                "label": "Volatility Expansion",
                "returned_picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "long_strike": 760.0,
                        "short_strike": 780.0,
                        "net_debit": 7.58,
                        "guardrail_decision": "clear",
                    },
                    {
                        "ticker": "DIA",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "long_strike": 500.0,
                        "short_strike": 520.0,
                        "net_debit": 6.0,
                        "guardrail_decision": "clear",
                    },
                ],
            },
        ],
    }
    lane_gate_report = {
        "lane_gates": {
            "swing": {
                "status": "diagnostic_only_unprofitable_lane",
                "auto_track_allowed": False,
                "blockers": ["profit_factor_below_lane_gate"],
            },
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": True,
                "blockers": [],
                "self_guardrails": {
                    "blocked_tickers": [{"ticker": "SPY"}],
                    "max_debit_pct_of_width": 55.0,
                },
            },
        }
    }

    rows = pending_audit_candidates.build_pending_candidate_rows(
        report,
        recorded_at_utc="2026-06-02T07:00:00Z",
        lane_gate_report=lane_gate_report,
    )
    statuses = {(row["playbook_id"], row["ticker"]): row["candidate_status"] for row in rows}

    assert statuses[("swing", "SPY")] == "diagnostic_only_lane_profitability_gate"
    assert statuses[("volatility_expansion_observation", "SPY")] == "diagnostic_only_lane_profitability_gate"
    assert statuses[("volatility_expansion_observation", "DIA")] == LANE_GATE_PROBATION_PAPER_STATUS
    assert rows[0]["lane_profitability_gate"]["lane_gate_blockers"] == ["profit_factor_below_lane_gate"]


def test_paper_probation_lane_queues_paper_exact_evidence_not_live_validation(
    tmp_path: Path,
) -> None:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    report = {
        "generated_at_utc": generated_at,
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
        "playbooks": [
            {
                "playbook_id": "volatility_expansion_observation",
                "label": "Volatility Expansion",
                "returned_picks": [
                    {
                        "ticker": "DIA",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "long_strike": 500.0,
                        "short_strike": 520.0,
                        "net_debit": 6.0,
                        "guardrail_decision": "clear",
                    }
                ],
            }
        ],
    }
    lane_gate_report = {
        "generated_at_utc": generated_at,
        "summary": {
            "mark_unpriced_count": 0,
            "tracked_row_count": 0,
            "tracked_rows_with_stored_pnl": 0,
        },
        "lane_gates": {
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": True,
                "blockers": [],
                "self_guardrails": {},
            }
        },
    }
    lane_promotion_report = {
        "report_id": "regular_options_lane_promotion_state",
        "generated_at_utc": generated_at,
        "summary": {"live_policy_change": False},
        "lane_states": {
            "volatility_expansion_observation": {
                "playbook_id": "volatility_expansion_observation",
                "promotion_state": "paper_probation",
                "candidate_status": LANE_PROMOTION_PAPER_EVIDENCE_STATUS,
                "candidate_status_reason": "promotion_requires_fresh_walk_forward_paper_and_risk_gates",
                "failed_promotion_gates": ["fresh_paper_cohort"],
                "blockers": ["fresh_paper_cohort_insufficient"],
            }
        },
    }

    rows = pending_audit_candidates.build_pending_candidate_rows(
        report,
        lane_gate_report=lane_gate_report,
        require_fresh_lane_gate_report=True,
        lane_promotion_report=lane_promotion_report,
        require_fresh_lane_promotion_state=True,
    )

    assert len(rows) == 1
    assert rows[0]["candidate_status"] == LANE_PROMOTION_PAPER_EVIDENCE_STATUS
    assert rows[0]["candidate_status"] != "pending_live_validation"


def test_daily_queue_fails_closed_when_lane_profitability_report_missing() -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
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
                    }
                ],
            }
        ],
    }

    with patch.object(ensure_audit, "load_lane_gate_report", return_value=None):
        summary = ensure_audit._queue_candidates(report, dry_run=True)

    assert summary is not None
    assert summary["selected_clear_candidates"] == 1
    assert summary["pending_live_validation"] == 0
    assert summary["diagnostic_only_lane_profitability_gate"] == 1
    assert summary["lane_profitability_gate_loaded"] is False
    assert summary["lane_profitability_gate_fail_closed"] is True


def test_daily_queue_fails_closed_when_lane_profitability_report_stale() -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
        "playbooks": [
            {
                "playbook_id": "volatility_expansion_observation",
                "label": "Volatility Expansion",
                "returned_picks": [
                    {
                        "ticker": "QQQ",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "long_strike": 760.0,
                        "short_strike": 780.0,
                        "net_debit": 7.58,
                        "guardrail_decision": "clear",
                    }
                ],
            }
        ],
    }
    stale_gate = {
        "generated_at_utc": "2000-01-01T00:00:00Z",
        "lane_gates": {
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": True,
                "blockers": [],
                "self_guardrails": {},
            }
        },
    }

    with patch.object(ensure_audit, "load_lane_gate_report", return_value=stale_gate):
        summary = ensure_audit._queue_candidates(report, dry_run=True)

    assert summary is not None
    assert summary["selected_clear_candidates"] == 1
    assert summary["pending_live_validation"] == 0
    assert summary["diagnostic_only_lane_profitability_gate"] == 1
    assert summary["lane_profitability_gate_loaded"] is True
    assert summary["lane_profitability_gate_usable"] is False
    assert summary["lane_profitability_gate_fail_closed"] is True
    assert summary["lane_profitability_gate_fail_reason"] == "lane_profitability_gate_report_stale"


def test_lane_profitability_gate_blocks_execution_quality_self_guardrail() -> None:
    report = {
        "generated_at_utc": "2026-06-05T14:00:00Z",
        "summary": {
            "mark_unpriced_count": 0,
            "tracked_row_count": 0,
            "tracked_rows_with_stored_pnl": 0,
        },
        "lane_gates": {
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": True,
                "blockers": [],
                "self_guardrails": {
                    "max_fill_degradation_vs_mid_pct": 5.0,
                },
            }
        },
    }

    decision = candidate_gate_decision(
        playbook_id="volatility_expansion_observation",
        candidate={"ticker": "QQQ", "fill_degradation_vs_mid_pct": 6.1},
        report=report,
        require_fresh_report=True,
        now_utc=datetime(2026, 6, 5, 14, 30, tzinfo=UTC),
    )

    assert decision["allowed"] is False
    assert (
        decision["candidate_status_reason"]
        == "lane_self_guardrail_blocked_fill_degradation_outside_profitable_bucket"
    )
    assert decision["candidate_fill_degradation_vs_mid_pct"] == 6.1
    assert decision["max_fill_degradation_vs_mid_pct"] == 5.0


def test_lane_profitability_gate_fails_closed_when_report_has_unpriced_rows() -> None:
    report = {
        "generated_at_utc": "2026-06-05T14:00:00Z",
        "summary": {
            "mark_unpriced_count": 1,
            "tracked_row_count": 0,
            "tracked_rows_with_stored_pnl": 0,
        },
        "lane_gates": {"volatility_expansion_observation": {"auto_track_allowed": True}},
    }

    health = lane_gate_report_health(report, now_utc=datetime(2026, 6, 5, 14, 30, tzinfo=UTC))

    assert health["usable"] is False
    assert health["reason"] == "lane_profitability_gate_report_has_unpriced_rows"


def test_lane_profitability_gate_passed_lane_routes_to_probation_when_requested() -> None:
    report = {
        "generated_at_utc": "2026-06-05T14:00:00Z",
        "summary": {
            "mark_unpriced_count": 0,
            "tracked_row_count": 0,
            "tracked_rows_with_stored_pnl": 0,
        },
        "lane_gates": {
            "volatility_expansion_observation": {
                "status": "candidate_flow_allowed_with_self_guardrails",
                "auto_track_allowed": True,
                "blockers": [],
                "self_guardrails": {"max_debit_pct_of_width": 45.0},
            }
        },
    }

    decision = candidate_gate_decision(
        playbook_id="volatility_expansion_observation",
        candidate={"ticker": "DIA", "long_strike": 500.0, "short_strike": 520.0, "net_debit": 6.0},
        report=report,
        require_fresh_report=True,
        now_utc=datetime(2026, 6, 5, 14, 30, tzinfo=UTC),
        probation_paper_only=True,
    )

    assert decision["allowed"] is False
    assert decision["candidate_status"] == LANE_GATE_PROBATION_PAPER_STATUS
    assert decision["probation_allowed"] is True


def test_pending_candidate_queue_suppresses_duplicate_exact_spreads_to_one_risk_slot() -> None:
    report = {
        "generated_at_utc": "2026-06-02T06:39:32Z",
        "scope": "all_supervised_guardrail_starvation",
        "settings": {"market_open_at_run": True},
        "playbooks": [
            {
                "playbook_id": "swing",
                "label": "Swing",
                "returned_picks": [
                    {
                        "ticker": "DIA",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "contract_symbol": "DIA260626C00500000",
                        "short_contract_symbol": "DIA260626C00520000",
                        "long_strike": 500.0,
                        "short_strike": 520.0,
                        "net_debit": 6.0,
                        "guardrail_decision": "clear",
                    }
                ],
            },
            {
                "playbook_id": "short_term",
                "label": "Short Term",
                "returned_picks": [
                    {
                        "ticker": "DIA",
                        "direction": "call",
                        "expiry": "2026-06-26",
                        "contract_symbol": "DIA260626C00500000",
                        "short_contract_symbol": "DIA260626C00520000",
                        "long_strike": 500.0,
                        "short_strike": 520.0,
                        "net_debit": 6.0,
                        "guardrail_decision": "clear",
                    }
                ],
            },
        ],
    }

    rows = pending_audit_candidates.build_pending_candidate_rows(report)
    statuses = {row["playbook_id"]: row["candidate_status"] for row in rows}

    assert len(rows) == 2
    assert sorted(statuses.values()) == [
        "paper_validation_only_duplicate_exact_spread",
        "pending_live_validation",
    ]
    assert len({row["exact_spread_group_key"] for row in rows}) == 1


def test_volatility_lane_blocks_fill_degradation_above_starter_cap() -> None:
    playbook = dict(supervised_scan.SCAN_PLAYBOOKS["volatility_expansion_observation"])
    pick = {
        "ticker": "QQQ",
        "asset_class": "index",
        "direction": "call",
        "strategy_type": "vertical_spread",
        "quality_score": 80.0,
        "strike": 500.0,
        "short_strike": 520.0,
        "net_debit": 8.0,
        "fill_degradation_vs_mid_pct": 6.1,
        "worst_leg_bid_ask_spread_pct": 1.0,
    }

    annotated = supervised_scan.annotate_pick_with_guardrails(
        pick,
        playbook=playbook,
        exposure={"available": True},
    )

    assert annotated["guardrail_decision"] == "blocked"
    assert any("Fill degradation versus midpoint" in reason for reason in annotated["guardrail_reasons"])


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
    assert calls[0]["OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE"] == "1"


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


def test_validation_disposition_splits_created_duplicate_and_no_longer_matched(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "pending.jsonl"
    fill_attempts = tmp_path / "fills.jsonl"
    base = {
        "audit_generated_at_utc": "2026-06-02T06:39:32Z",
        "candidate_status": "live_validation_attempted",
        "validation_exit_code": 0,
        "validation_recorded_at_utc": "2026-06-02T15:00:00Z",
        "tracking_approved_lane": True,
        "position_tracking_mode": "auto_track",
        "playbook_id": "swing",
        "direction": "call",
        "expiry": "2026-06-26",
        "long_strike": 760.0,
        "short_strike": 780.0,
    }
    rows = [
        {
            **base,
            "candidate_key": "2026-06-02|swing|SPY|call|2026-06-26|||760.0|780.0",
            "ticker": "SPY",
        },
        {
            **base,
            "candidate_key": "2026-06-02|swing|QQQ|call|2026-06-26|||760.0|780.0",
            "ticker": "QQQ",
        },
        {
            **base,
            "candidate_key": "2026-06-02|swing|IWM|call|2026-06-26|||760.0|780.0",
            "ticker": "IWM",
        },
    ]
    queue.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")
    fill_rows = [
        {
            "event_type": "candidate_shown",
            "status": "shown",
            "scan_date": "2026-06-02",
            "playbook_id": "swing",
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-06-26",
            "selected_spread": {"long_strike": 760.0, "short_strike": 780.0},
            "filled": True,
            "fill_status": "auto_tracked",
            "fill_outcome": "paper_fill_recorded",
            "fill_outcome_reason": "auto_track_position_created",
            "auto_track_outcome": "created",
            "auto_track_position_id": 11,
        },
        {
            "event_type": "candidate_shown",
            "status": "shown",
            "scan_date": "2026-06-02",
            "playbook_id": "swing",
            "ticker": "QQQ",
            "direction": "call",
            "expiry": "2026-06-26",
            "selected_spread": {"long_strike": 760.0, "short_strike": 780.0},
            "filled": True,
            "fill_status": "auto_tracked",
            "fill_outcome": "paper_fill_recorded",
            "fill_outcome_reason": "auto_track_position_already_open",
            "auto_track_outcome": "duplicate_open",
            "auto_track_position_id": 12,
        },
    ]
    fill_attempts.write_text("\n".join(json.dumps(row) for row in fill_rows) + "\n", encoding="utf8")

    report = pending_audit_candidates.build_validation_disposition_report(
        queue_file=queue,
        fill_attempt_file=fill_attempts,
        scan_date="2026-06-02",
    )
    outcomes = {row["ticker"]: row["outcome"] for row in report["candidates"]}

    assert outcomes == {"SPY": "created", "QQQ": "duplicate", "IWM": "no_longer_matched"}
    assert report["summary"]["outcome_counts"] == {"created": 1, "duplicate": 1, "no_longer_matched": 1}


def test_validation_disposition_splits_paper_proof_and_blocked(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "pending.jsonl"
    fill_attempts = tmp_path / "fills.jsonl"
    base = {
        "audit_generated_at_utc": "2026-06-02T06:39:32Z",
        "candidate_status": "live_validation_attempted",
        "validation_exit_code": 0,
        "validation_recorded_at_utc": "2026-06-02T15:00:00Z",
        "tracking_approved_lane": True,
        "position_tracking_mode": "auto_track",
        "playbook_id": "swing",
        "direction": "call",
        "expiry": "2026-06-26",
        "long_strike": 760.0,
        "short_strike": 780.0,
    }
    rows = [
        {
            **base,
            "candidate_key": "2026-06-02|swing|SPY|call|2026-06-26|||760.0|780.0",
            "ticker": "SPY",
            "tracking_approved_lane": False,
            "position_tracking_mode": "disabled",
        },
        {
            **base,
            "candidate_key": "2026-06-02|swing|QQQ|call|2026-06-26|||760.0|780.0",
            "ticker": "QQQ",
        },
        {
            **base,
            "candidate_key": "2026-06-02|swing|IWM|call|2026-06-26|||760.0|780.0",
            "ticker": "IWM",
            "candidate_status": "live_validation_scan_failed",
            "validation_exit_code": 1,
        },
    ]
    queue.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")
    fill_rows = [
        {
            "event_type": "candidate_shown",
            "status": "shown",
            "scan_date": "2026-06-02",
            "playbook_id": "swing",
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-06-26",
            "selected_spread": {"long_strike": 760.0, "short_strike": 780.0},
            "filled": False,
            "fill_status": "not_submitted_auto_track_disabled",
            "fill_outcome": "not_submitted",
            "fill_outcome_reason": "auto_track_disabled",
        },
        {
            "event_type": "candidate_shown",
            "status": "shown",
            "scan_date": "2026-06-02",
            "playbook_id": "swing",
            "ticker": "QQQ",
            "direction": "call",
            "expiry": "2026-06-26",
            "selected_spread": {"long_strike": 760.0, "short_strike": 780.0},
            "filled": False,
            "fill_status": "not_filled_auto_track_skipped",
            "fill_outcome": "no_fill",
            "fill_outcome_reason": "auto_track_skipped_or_missing_fill_price",
            "auto_track_skip_reason": "proof_gate_detail_kept_for_operator_audit",
        },
    ]
    fill_attempts.write_text("\n".join(json.dumps(row) for row in fill_rows) + "\n", encoding="utf8")

    report = pending_audit_candidates.build_validation_disposition_report(
        queue_file=queue,
        fill_attempt_file=fill_attempts,
        scan_date="2026-06-02",
    )
    outcomes = {row["ticker"]: row["outcome"] for row in report["candidates"]}

    assert outcomes == {"SPY": "paper_only", "QQQ": "proof_ineligible", "IWM": "blocked"}
    assert report["summary"]["outcome_counts"] == {"blocked": 1, "paper_only": 1, "proof_ineligible": 1}
    assert next(row for row in report["candidates"] if row["ticker"] == "QQQ")[
        "auto_track_skip_reason"
    ] == "proof_gate_detail_kept_for_operator_audit"


def test_validation_disposition_includes_lane_promotion_paper_only_rows(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "pending.jsonl"
    fill_attempts = tmp_path / "fills.jsonl"
    row = {
        "audit_generated_at_utc": "2026-06-05T06:39:32Z",
        "candidate_key": "2026-06-05|volatility_expansion_observation|DIA|call|2026-06-26|||500.0|520.0",
        "candidate_status": LANE_PROMOTION_PAPER_ONLY_STATUS,
        "candidate_status_reason": "promotion_requires_fresh_walk_forward_paper_and_risk_gates",
        "validation_exit_code": None,
        "validation_recorded_at_utc": "2026-06-05T15:00:00Z",
        "tracking_approved_lane": True,
        "position_tracking_mode": "auto_track",
        "playbook_id": "volatility_expansion_observation",
        "ticker": "DIA",
        "direction": "call",
        "expiry": "2026-06-26",
        "long_strike": 500.0,
        "short_strike": 520.0,
        "lane_promotion_state": {
            "promotion_state": "paper_probation",
            "failed_promotion_gates": ["fresh_paper_cohort"],
        },
    }
    queue.write_text(json.dumps(row) + "\n", encoding="utf8")
    fill_attempts.write_text("", encoding="utf8")

    report = pending_audit_candidates.build_validation_disposition_report(
        queue_file=queue,
        fill_attempt_file=fill_attempts,
        scan_date="2026-06-05",
    )

    assert report["summary"]["outcome_counts"] == {"paper_only": 1}
    assert report["candidates"][0]["candidate_status"] == LANE_PROMOTION_PAPER_ONLY_STATUS
    assert report["candidates"][0]["outcome_reason"] == (
        "promotion_requires_fresh_walk_forward_paper_and_risk_gates"
    )


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

    def test_pending_candidate_queue_records_clear_regular_auto_track_lane_and_ignores_blocked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_queue_records_clear_regular_auto_track_lane_and_ignores_blocked(Path(temp_dir))

    def test_pending_candidate_queue_marks_clear_separate_nontracking_lane_as_diagnostic_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_queue_marks_clear_separate_nontracking_lane_as_diagnostic_only(Path(temp_dir))

    def test_pending_candidate_queue_honors_lane_profitability_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_queue_honors_lane_profitability_gate(Path(temp_dir))

    def test_paper_probation_lane_queues_paper_exact_evidence_not_live_validation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_paper_probation_lane_queues_paper_exact_evidence_not_live_validation(Path(temp_dir))

    def test_daily_queue_fails_closed_when_lane_profitability_report_missing(self) -> None:
        test_daily_queue_fails_closed_when_lane_profitability_report_missing()

    def test_daily_queue_fails_closed_when_lane_profitability_report_stale(self) -> None:
        test_daily_queue_fails_closed_when_lane_profitability_report_stale()

    def test_lane_profitability_gate_blocks_execution_quality_self_guardrail(self) -> None:
        test_lane_profitability_gate_blocks_execution_quality_self_guardrail()

    def test_lane_profitability_gate_fails_closed_when_report_has_unpriced_rows(self) -> None:
        test_lane_profitability_gate_fails_closed_when_report_has_unpriced_rows()

    def test_lane_profitability_gate_passed_lane_routes_to_probation_when_requested(self) -> None:
        test_lane_profitability_gate_passed_lane_routes_to_probation_when_requested()

    def test_pending_candidate_queue_suppresses_duplicate_exact_spreads_to_one_risk_slot(self) -> None:
        test_pending_candidate_queue_suppresses_duplicate_exact_spreads_to_one_risk_slot()

    def test_volatility_lane_blocks_fill_degradation_above_starter_cap(self) -> None:
        test_volatility_lane_blocks_fill_degradation_above_starter_cap()

    def test_pending_candidate_validation_groups_all_validation_enabled_pending_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_pending_candidate_validation_groups_all_validation_enabled_pending_rows(Path(temp_dir))

    def test_pending_candidate_validation_runs_log_scan_with_caps(self) -> None:
        test_pending_candidate_validation_runs_log_scan_with_caps(_MonkeyPatch(self))

    def test_validation_attempt_resolves_pending_candidate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_validation_attempt_resolves_pending_candidate(Path(temp_dir))

    def test_validation_disposition_splits_created_duplicate_and_no_longer_matched(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_validation_disposition_splits_created_duplicate_and_no_longer_matched(Path(temp_dir))

    def test_validation_disposition_splits_paper_proof_and_blocked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_validation_disposition_splits_paper_proof_and_blocked(Path(temp_dir))

    def test_validation_disposition_includes_lane_promotion_paper_only_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_validation_disposition_includes_lane_promotion_paper_only_rows(Path(temp_dir))
