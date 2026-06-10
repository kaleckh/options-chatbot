from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.candidate_lifecycle import (
    STATUS_DIAGNOSTIC_LANE_PROMOTION_STATE,
    STATUS_LIVE_VALIDATION_ATTEMPTED,
    STATUS_LIVE_VALIDATION_SCAN_FAILED,
    STATUS_PAPER_LANE_PROMOTION_STATE,
    STATUS_PENDING_PAPER_EXACT_EVIDENCE,
    STATUS_PENDING_LIVE_VALIDATION,
)
from scripts.lane_profitability_gate import (
    DEFAULT_LANE_GATE_MAX_AGE_HOURS,
    DEFAULT_LANE_GATE_REPORT,
    lane_gate_for_playbook,
    lane_gate_report_health,
    load_lane_gate_report,
)
from supervised_scan import (
    AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID,
    POSITION_TRACKING_AUTO_TRACK,
    SCAN_PLAYBOOKS,
    scan_playbook_fresh_live_validation_enabled,
    scan_playbook_position_tracking_mode,
)


REPORT_ID = "regular_options_lane_promotion_state"
DEFAULT_FILTER_MATRIX = ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json"
DEFAULT_FRESH_EVIDENCE_LOOP = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_OPEN_RISK_REPORT = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_CIRCUIT_BREAKER = ROOT / "data" / "forward-tracking" / "current_policy_circuit_breaker_latest.json"
DEFAULT_LANE_PROMOTION_REPORT = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_LANE_PROMOTION_MARKDOWN = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.md"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "lane-promotion-state.md"
DEFAULT_LANE_PROMOTION_MAX_AGE_HOURS = 36.0
DEFAULT_OPEN_RISK_MAX_AGE_HOURS = 24.0

PROMOTION_STATE_DIAGNOSTIC = "diagnostic"
PROMOTION_STATE_PAPER_PROBATION = "paper_probation"
PROMOTION_STATE_LIVE_VALIDATION = "live_validation"
PROMOTION_STATE_AUTO_TRACK = "auto_track"

LANE_PROMOTION_DIAGNOSTIC_STATUS = STATUS_DIAGNOSTIC_LANE_PROMOTION_STATE
LANE_PROMOTION_PAPER_ONLY_STATUS = STATUS_PAPER_LANE_PROMOTION_STATE
LANE_PROMOTION_PAPER_EVIDENCE_STATUS = STATUS_PENDING_PAPER_EXACT_EVIDENCE

MIN_WALK_FORWARD_LATER_ROWS = 10
MIN_FRESH_EXACT_REALIZED_ROWS = 20
MIN_FRESH_PROMOTION_READY_ROWS = 10

OPEN_RISK_GOVERNOR_PASS = "open_risk_governor_pass"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any, default: int = 0) -> int:
    parsed = _safe_float(value)
    return default if parsed is None else int(parsed)


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return str(candidate)


def _load_json(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_lane_promotion_report(path: Path | str | None = DEFAULT_LANE_PROMOTION_REPORT) -> dict[str, Any] | None:
    return _load_json(path)


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


def lane_promotion_report_health(
    report: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_age_hours: float = DEFAULT_LANE_PROMOTION_MAX_AGE_HOURS,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_missing",
            "generated_at_utc": None,
            "age_hours": None,
            "max_age_hours": max_age_hours,
        }
    generated = _parse_utc_datetime(report.get("generated_at_utc"))
    if generated is None:
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_missing_generated_at_utc",
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
            "reason": "lane_promotion_state_report_generated_in_future",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if age_hours > max_age_hours:
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_stale",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if report.get("report_id") != REPORT_ID:
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_wrong_report_id",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
            "report_id": report.get("report_id"),
        }
    lane_states = report.get("lane_states")
    if not isinstance(lane_states, dict) or not lane_states:
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_missing_lane_states",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if bool(summary.get("live_policy_change")):
        return {
            "usable": False,
            "reason": "lane_promotion_state_report_requires_policy_review",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    return {
        "usable": True,
        "reason": "lane_promotion_state_report_fresh",
        "generated_at_utc": report.get("generated_at_utc"),
        "age_hours": round(age_hours, 4),
        "max_age_hours": max_age_hours,
        "lane_count": len(lane_states),
    }


def open_risk_report_health(
    report: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_age_hours: float = DEFAULT_OPEN_RISK_MAX_AGE_HOURS,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "usable": False,
            "reason": "open_risk_report_missing",
            "generated_at_utc": None,
            "age_hours": None,
            "max_age_hours": max_age_hours,
        }
    generated = _parse_utc_datetime(report.get("generated_at_utc"))
    if generated is None:
        return {
            "usable": False,
            "reason": "open_risk_report_missing_generated_at_utc",
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
            "reason": "open_risk_report_generated_in_future",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if age_hours > max_age_hours:
        return {
            "usable": False,
            "reason": "open_risk_report_stale",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if report.get("scope") != "regular_supervised_open_positions_read_only":
        return {
            "usable": False,
            "reason": "open_risk_report_wrong_scope",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
            "scope": report.get("scope"),
        }
    governor = report.get("open_risk_governor")
    if not isinstance(governor, dict):
        return {
            "usable": False,
            "reason": "open_risk_report_missing_governor",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    return {
        "usable": True,
        "reason": "open_risk_report_fresh",
        "generated_at_utc": report.get("generated_at_utc"),
        "age_hours": round(age_hours, 4),
        "max_age_hours": max_age_hours,
        "governor_status": governor.get("status"),
        "governor_blockers": list(governor.get("blockers") or []),
    }


def lane_promotion_for_playbook(report: dict[str, Any] | None, playbook_id: str | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    playbook = _norm(playbook_id).lower()
    states = report.get("lane_states")
    if isinstance(states, dict):
        state = states.get(playbook)
        if isinstance(state, dict):
            return state
    for row in report.get("lane_state_rows") or []:
        if isinstance(row, dict) and _norm(row.get("playbook_id")).lower() == playbook:
            return row
    return None


def _scenario_by_id(filter_matrix: dict[str, Any] | None, scenario_id: str) -> dict[str, Any] | None:
    if not isinstance(filter_matrix, dict):
        return None
    scenarios = filter_matrix.get("scenarios")
    if isinstance(scenarios, dict):
        scenario = scenarios.get(scenario_id)
        return scenario if isinstance(scenario, dict) else None
    for scenario in scenarios or []:
        if isinstance(scenario, dict) and _norm(scenario.get("scenario_id")) == scenario_id:
            return scenario
    return None


def _fresh_counts_by_lane(fresh_evidence: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "candidate_count": 0,
            "created_or_duplicate_count": 0,
            "fresh_executable_exact_entry_count": 0,
            "exact_realized_pnl_count": 0,
            "promotion_ready_count": 0,
            "proof_ineligible_count": 0,
            "paper_only_count": 0,
            "no_longer_matched_count": 0,
            "legacy_pre_promotion_state_gate_count": 0,
        }
    )
    if not isinstance(fresh_evidence, dict):
        return {}
    for row in fresh_evidence.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        lane = _norm(row.get("playbook_id")).lower()
        if not lane:
            continue
        lane_counts = counts[lane]
        lane_counts["candidate_count"] += 1
        legacy_pre_promotion = _fresh_evidence_row_is_legacy_pre_promotion_gate(row)
        if legacy_pre_promotion:
            lane_counts["legacy_pre_promotion_state_gate_count"] += 1
        outcome = _norm(row.get("validation_outcome"))
        if outcome in {"created", "duplicate"}:
            lane_counts["created_or_duplicate_count"] += 1
        if outcome == "proof_ineligible":
            lane_counts["proof_ineligible_count"] += 1
        if outcome == "paper_only":
            lane_counts["paper_only_count"] += 1
        if outcome == "no_longer_matched":
            lane_counts["no_longer_matched_count"] += 1
        if legacy_pre_promotion:
            continue
        if _norm(row.get("entry_evidence_status")) == "fresh_executable_exact_entry":
            lane_counts["fresh_executable_exact_entry_count"] += 1
        if _norm(row.get("realized_pnl_status")) == "exact_realized_pnl_available":
            lane_counts["exact_realized_pnl_count"] += 1
        if bool(row.get("promotion_discussion_ready")):
            lane_counts["promotion_ready_count"] += 1
    return dict(counts)


def _fresh_evidence_row_is_legacy_pre_promotion_gate(row: dict[str, Any]) -> bool:
    context = _norm(row.get("promotion_gate_context"))
    if context:
        return context == "legacy_pre_promotion_state_gate"
    if isinstance(row.get("lane_promotion_state"), dict):
        return False
    status = _norm(row.get("candidate_status"))
    return status in {
        STATUS_PENDING_LIVE_VALIDATION,
        STATUS_LIVE_VALIDATION_ATTEMPTED,
        STATUS_LIVE_VALIDATION_SCAN_FAILED,
    }


def _circuit_breaker_routes(circuit_breaker: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(circuit_breaker, dict):
        return {}
    routes: dict[str, dict[str, Any]] = {}
    for route in circuit_breaker.get("lane_routes") or []:
        if isinstance(route, dict):
            lane = _norm(route.get("lane_id")).lower()
            if lane:
                routes[lane] = route
    return routes


def _live_exact_open_negative_count(open_risk: dict[str, Any] | None, playbook_id: str) -> int:
    if not isinstance(open_risk, dict):
        return 0
    count = 0
    for row in open_risk.get("top_negative_open_positions") or []:
        if not isinstance(row, dict):
            continue
        if _norm(row.get("record_class")) != "live_exact_tracked":
            continue
        if _norm(row.get("lane")).lower() == playbook_id:
            count += 1
    return count


def _global_live_exact_negative_count(open_risk: dict[str, Any] | None) -> int | None:
    if not isinstance(open_risk, dict):
        return None
    live_exact = (open_risk.get("by_record_class") or {}).get("live_exact_tracked")
    if isinstance(live_exact, dict):
        return _safe_int(live_exact.get("negative"))
    return 0


def _open_risk_governor(open_risk: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(open_risk, dict):
        return {}
    governor = open_risk.get("open_risk_governor")
    return governor if isinstance(governor, dict) else {}


def _gate(gate_id: str, label: str, passed: bool, current: Any, target: Any, blocker: str | None = None) -> dict[str, Any]:
    row = {
        "gate": gate_id,
        "label": label,
        "passed": bool(passed),
        "current": current,
        "target": target,
    }
    if blocker and not passed:
        row["blocker"] = blocker
    return row


def build_lane_promotion_state(
    *,
    lane_gate_report: dict[str, Any] | None = None,
    filter_matrix: dict[str, Any] | None = None,
    fresh_evidence: dict[str, Any] | None = None,
    open_risk: dict[str, Any] | None = None,
    circuit_breaker: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now()
    lane_gate_health = lane_gate_report_health(
        lane_gate_report,
        now_utc=now_utc,
        max_age_hours=DEFAULT_LANE_GATE_MAX_AGE_HOURS,
    )
    filter_scenario = _scenario_by_id(filter_matrix, "current_lane_gate_self_guardrails")
    open_risk_health = open_risk_report_health(open_risk, now_utc=now_utc)
    if filter_scenario is None:
        filter_scenario = _scenario_by_id(filter_matrix, "current_lane_gate_allowlist")
    later_read = filter_scenario.get("later_date_read") if isinstance(filter_scenario, dict) else {}
    if not isinstance(later_read, dict):
        later_read = {}
    fresh_by_lane = _fresh_counts_by_lane(fresh_evidence)
    breaker_routes = _circuit_breaker_routes(circuit_breaker)
    global_live_exact_negative = _global_live_exact_negative_count(open_risk)
    open_risk_governor = _open_risk_governor(open_risk)
    open_risk_governor_status = _norm(open_risk_governor.get("status"))
    open_risk_governor_blockers = [
        str(item) for item in list(open_risk_governor.get("blockers") or []) if str(item).strip()
    ]

    state_rows: list[dict[str, Any]] = []
    for playbook_id in sorted(SCAN_PLAYBOOKS):
        lane = _norm(playbook_id).lower()
        playbook = SCAN_PLAYBOOKS[playbook_id]
        tracking_mode = scan_playbook_position_tracking_mode(lane)
        fresh_validation = scan_playbook_fresh_live_validation_enabled(lane)
        is_regular_auto_track = (
            lane != AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID
            and tracking_mode == POSITION_TRACKING_AUTO_TRACK
            and fresh_validation
        )
        gate = lane_gate_for_playbook(lane_gate_report, lane)
        gate_status = _norm((gate or {}).get("status") or (gate or {}).get("gate_status"))
        gate_metrics = (gate or {}).get("metrics") if isinstance((gate or {}).get("metrics"), dict) else {}
        lane_profitable = bool((gate or {}).get("auto_track_allowed")) if isinstance(gate, dict) else False
        lane_gate_present = isinstance(gate, dict)
        lane_fresh = fresh_by_lane.get(lane, {})
        breaker_route = breaker_routes.get(lane)
        breaker_clear = not (
            isinstance(breaker_route, dict)
            and _norm(breaker_route.get("route_status")) in {"paper_validation_only", "blocked", "diagnostic_only"}
        )
        lane_live_exact_negative = _live_exact_open_negative_count(open_risk, lane)
        risk_report_present = isinstance(open_risk, dict)
        open_risk_governor_clear = (
            bool(open_risk_health.get("usable"))
            and open_risk_governor_status == OPEN_RISK_GOVERNOR_PASS
            and not open_risk_governor_blockers
        )

        walk_later_rows = _safe_int(later_read.get("later_date_rows"))
        walk_survives = bool(later_read.get("survives_later_date_split"))
        entry_time_only = bool((filter_scenario or {}).get("entry_time_only"))
        walk_forward_pass = entry_time_only and walk_survives and walk_later_rows >= MIN_WALK_FORWARD_LATER_ROWS
        fresh_paper_pass = (
            lane_fresh.get("exact_realized_pnl_count", 0) >= MIN_FRESH_EXACT_REALIZED_ROWS
            and lane_fresh.get("promotion_ready_count", 0) >= MIN_FRESH_PROMOTION_READY_ROWS
        )
        unresolved_live_exact_negative = open_risk_governor.get("live_exact_negative_unresolved_count")
        if unresolved_live_exact_negative is None:
            unresolved_live_exact_negative = 0 if open_risk_governor_clear else global_live_exact_negative
        else:
            unresolved_live_exact_negative = _safe_int(unresolved_live_exact_negative)
        risk_pass = risk_report_present and bool(open_risk_health.get("usable")) and open_risk_governor_clear

        gates = [
            _gate(
                "regular_auto_track_scope",
                "Regular auto-track scope",
                is_regular_auto_track,
                {"tracking_mode": tracking_mode, "fresh_live_validation_enabled": fresh_validation},
                "regular auto_track lane with fresh validation enabled",
                "lane_outside_regular_auto_track_scope",
            ),
            _gate(
                "lane_profitability_report_clean",
                "Lane profitability report clean",
                bool(lane_gate_health.get("usable")),
                lane_gate_health.get("reason"),
                "fresh usable report with zero unpriced rows and complete tracked P&L",
                "lane_profitability_gate_report_unusable",
            ),
            _gate(
                "profitable_lane_gate",
                "Profitable lane gate",
                lane_gate_present and lane_profitable,
                {
                    "lane_gate_present": lane_gate_present,
                    "status": gate_status,
                    "priced": gate_metrics.get("priced"),
                    "profit_factor": gate_metrics.get("profit_factor"),
                    "avg_net_pnl_pct": gate_metrics.get("avg_net_pnl_pct"),
                },
                "lane row present, profitable, and auto_track_allowed=true",
                "lane_not_profitable_enough_for_probation",
            ),
            _gate(
                "entry_time_only_rule",
                "Entry-time-only rule",
                entry_time_only,
                (filter_scenario or {}).get("scenario_id"),
                "promotion filter uses entry-time-known inputs only",
                "entry_time_only_rule_missing",
            ),
            _gate(
                "walk_forward_holdout_depth",
                "Walk-forward holdout depth",
                walk_forward_pass,
                {
                    "later_date_rows": walk_later_rows,
                    "survives_later_date_split": walk_survives,
                    "later_date_profit_factor": later_read.get("later_date_profit_factor"),
                },
                {"min_later_date_rows": MIN_WALK_FORWARD_LATER_ROWS, "survives_later_date_split": True},
                "walk_forward_holdout_too_small_or_failed",
            ),
            _gate(
                "fresh_paper_cohort",
                "Fresh paper cohort",
                fresh_paper_pass,
                {
                    "exact_realized_pnl_count": lane_fresh.get("exact_realized_pnl_count", 0),
                    "promotion_ready_count": lane_fresh.get("promotion_ready_count", 0),
                    "fresh_executable_exact_entry_count": lane_fresh.get("fresh_executable_exact_entry_count", 0),
                },
                {
                    "min_exact_realized_pnl_count": MIN_FRESH_EXACT_REALIZED_ROWS,
                    "min_promotion_ready_count": MIN_FRESH_PROMOTION_READY_ROWS,
                },
                "fresh_paper_cohort_insufficient",
            ),
            _gate(
                "current_live_exact_risk_clear",
                "Current live-exact risk clear",
                risk_pass,
                {
                    "open_risk_report_present": risk_report_present,
                    "open_risk_report_health": open_risk_health,
                    "open_risk_governor_status": open_risk_governor_status or None,
                    "open_risk_governor_blockers": open_risk_governor_blockers,
                    "global_live_exact_negative_count": global_live_exact_negative,
                    "lane_live_exact_negative_count": lane_live_exact_negative,
                    "unresolved_live_exact_negative_count": unresolved_live_exact_negative,
                },
                {
                    "open_risk_report": "fresh",
                    "open_risk_governor_status": OPEN_RISK_GOVERNOR_PASS,
                    "open_risk_governor_blockers": [],
                    "unresolved_live_exact_negative_count": 0,
                },
                "current_live_exact_risk_governor_blocked"
                if bool(open_risk_health.get("usable"))
                else "open_risk_report_stale_or_unusable",
            ),
            _gate(
                "recent_cohort_circuit_breaker_clear",
                "Recent cohort circuit breaker clear",
                breaker_clear,
                {
                    "route_status": (breaker_route or {}).get("route_status") if isinstance(breaker_route, dict) else None,
                    "route_reason": (breaker_route or {}).get("route_reason") if isinstance(breaker_route, dict) else None,
                },
                "lane is not routed to paper_validation_only by the recent-cohort breaker",
                "recent_cohort_circuit_breaker_active",
            ),
            _gate(
                "duplicate_spread_suppression_active",
                "Duplicate spread suppression active",
                True,
                "active_in_pending_candidate_queue",
                "exact duplicate spreads are suppressed to one deterministic risk owner",
            ),
            _gate(
                "live_policy_change_false",
                "No live policy change",
                True,
                False,
                False,
            ),
        ]
        failed_gate_ids = [str(item["gate"]) for item in gates if not item.get("passed")]
        failed_blockers = [str(item.get("blocker")) for item in gates if item.get("blocker")]

        if not is_regular_auto_track or not bool(lane_gate_health.get("usable")) or not lane_gate_present or not lane_profitable:
            promotion_state = PROMOTION_STATE_DIAGNOSTIC
            candidate_status = LANE_PROMOTION_DIAGNOSTIC_STATUS
            status_reason = failed_blockers[0] if failed_blockers else "lane_not_promotable"
        elif failed_gate_ids:
            promotion_state = PROMOTION_STATE_PAPER_PROBATION
            candidate_status = LANE_PROMOTION_PAPER_EVIDENCE_STATUS
            status_reason = "promotion_requires_fresh_walk_forward_paper_and_risk_gates"
        else:
            promotion_state = PROMOTION_STATE_LIVE_VALIDATION
            candidate_status = STATUS_PENDING_LIVE_VALIDATION
            status_reason = "lane_promotion_state_allows_live_validation"

        state_rows.append(
            {
                "playbook_id": lane,
                "playbook_label": playbook.get("label"),
                "promotion_state": promotion_state,
                "candidate_status": candidate_status,
                "candidate_status_reason": status_reason,
                "tracking_mode": tracking_mode,
                "fresh_live_validation_enabled": fresh_validation,
                "lane_gate_status": gate_status or None,
                "lane_gate_metrics": {
                    "priced": gate_metrics.get("priced"),
                    "profit_factor": gate_metrics.get("profit_factor"),
                    "avg_net_pnl_pct": gate_metrics.get("avg_net_pnl_pct"),
                    "winner_count": gate_metrics.get("winner_count"),
                    "loser_count": gate_metrics.get("loser_count"),
                },
                "fresh_evidence": dict(lane_fresh),
                "failed_promotion_gates": failed_gate_ids,
                "blockers": failed_blockers,
                "gates": gates,
                "live_policy_change": False,
            }
        )

    state_counts = Counter(row["promotion_state"] for row in state_rows)
    candidate_status_counts = Counter(row["candidate_status"] for row in state_rows)
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at,
        "scope": "regular_options_lane_promotion_state",
        "status": "lane_promotion_state_readback",
        "policy": {
            "states": [
                PROMOTION_STATE_DIAGNOSTIC,
                PROMOTION_STATE_PAPER_PROBATION,
                PROMOTION_STATE_LIVE_VALIDATION,
                PROMOTION_STATE_AUTO_TRACK,
            ],
            "default_for_profitable_historical_lane": PROMOTION_STATE_PAPER_PROBATION,
            "live_validation_requires": [
                "clean lane profitability report",
                "profitable lane gate",
                "entry-time-only rule",
                f"at least {MIN_WALK_FORWARD_LATER_ROWS} later-date walk-forward rows",
                f"at least {MIN_FRESH_EXACT_REALIZED_ROWS} fresh exact realized P&L rows",
                f"at least {MIN_FRESH_PROMOTION_READY_ROWS} promotion-ready fresh rows",
                "zero unresolved live-exact negative open-risk rows",
                "no active lane-specific recent-cohort circuit breaker",
                "duplicate exact-spread suppression active",
            ],
            "auto_track_requires": [
                "live_validation state",
                "separate explicit release review before broker/live tracking semantics change",
            ],
        },
        "inputs": {
            "lane_gate_report_generated_at_utc": (lane_gate_report or {}).get("generated_at_utc")
            if isinstance(lane_gate_report, dict)
            else None,
            "filter_matrix_generated_at_utc": (filter_matrix or {}).get("generated_at_utc")
            if isinstance(filter_matrix, dict)
            else None,
            "fresh_evidence_generated_at_utc": (fresh_evidence or {}).get("generated_at_utc")
            if isinstance(fresh_evidence, dict)
            else None,
            "open_risk_generated_at_utc": (open_risk or {}).get("generated_at_utc")
            if isinstance(open_risk, dict)
            else None,
            "circuit_breaker_generated_at_utc": (circuit_breaker or {}).get("generated_at_utc")
            if isinstance(circuit_breaker, dict)
            else None,
        },
        "input_health": {
            "lane_profitability_gate": lane_gate_health,
            "filter_matrix_loaded": isinstance(filter_matrix, dict),
            "fresh_evidence_loop_loaded": isinstance(fresh_evidence, dict),
            "open_risk_loaded": isinstance(open_risk, dict),
            "open_risk_report": open_risk_health,
            "open_risk_governor": {
                "status": open_risk_governor_status or None,
                "blockers": open_risk_governor_blockers,
                "live_entry_allowed": bool(open_risk_governor.get("live_entry_allowed")),
            },
            "current_policy_circuit_breaker_loaded": isinstance(circuit_breaker, dict),
        },
        "summary": {
            "lane_count": len(state_rows),
            "state_counts": dict(sorted(state_counts.items())),
            "candidate_status_counts": dict(sorted(candidate_status_counts.items())),
            "live_validation_lane_count": state_counts.get(PROMOTION_STATE_LIVE_VALIDATION, 0),
            "auto_track_lane_count": state_counts.get(PROMOTION_STATE_AUTO_TRACK, 0),
            "paper_probation_lane_count": state_counts.get(PROMOTION_STATE_PAPER_PROBATION, 0),
            "diagnostic_lane_count": state_counts.get(PROMOTION_STATE_DIAGNOSTIC, 0),
            "live_policy_change": False,
            "global_live_exact_negative_count": global_live_exact_negative,
            "open_risk_governor_status": open_risk_governor_status or None,
            "open_risk_governor_blockers": open_risk_governor_blockers,
        },
        "lane_states": {row["playbook_id"]: row for row in state_rows},
        "lane_state_rows": state_rows,
    }


def candidate_promotion_decision(
    *,
    playbook_id: str | None,
    report: dict[str, Any] | None,
    require_fresh_report: bool = False,
    now_utc: datetime | None = None,
    max_report_age_hours: float = DEFAULT_LANE_PROMOTION_MAX_AGE_HOURS,
) -> dict[str, Any]:
    if require_fresh_report:
        health = lane_promotion_report_health(
            report,
            now_utc=now_utc,
            max_age_hours=max_report_age_hours,
        )
        if not bool(health.get("usable")):
            return {
                "allowed": False,
                "candidate_status": LANE_PROMOTION_DIAGNOSTIC_STATUS,
                "candidate_status_reason": health.get("reason") or "lane_promotion_state_report_unusable",
                "lane_promotion_state": None,
                "lane_promotion_report_health": health,
            }
    state = lane_promotion_for_playbook(report, playbook_id)
    if state is None:
        return {
            "allowed": False,
            "candidate_status": LANE_PROMOTION_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "missing_lane_promotion_state_row",
            "lane_promotion_state": None,
        }
    promotion_state = _norm(state.get("promotion_state"))
    if promotion_state in {PROMOTION_STATE_LIVE_VALIDATION, PROMOTION_STATE_AUTO_TRACK}:
        return {
            "allowed": True,
            "candidate_status": STATUS_PENDING_LIVE_VALIDATION,
            "candidate_status_reason": state.get("candidate_status_reason") or "lane_promotion_state_allows_live_validation",
            "lane_promotion_state": state,
            "lane_promotion_report_health": lane_promotion_report_health(
                report,
                now_utc=now_utc,
                max_age_hours=max_report_age_hours,
            )
            if require_fresh_report
            else None,
        }
    if promotion_state == PROMOTION_STATE_PAPER_PROBATION:
        return {
            "allowed": False,
            "candidate_status": state.get("candidate_status") or LANE_PROMOTION_PAPER_EVIDENCE_STATUS,
            "candidate_status_reason": state.get("candidate_status_reason")
            or "lane_promotion_state_requires_fresh_forward_validation",
            "lane_promotion_state": state,
            "lane_promotion_report_health": lane_promotion_report_health(
                report,
                now_utc=now_utc,
                max_age_hours=max_report_age_hours,
            )
            if require_fresh_report
            else None,
        }
    return {
        "allowed": False,
        "candidate_status": LANE_PROMOTION_DIAGNOSTIC_STATUS,
        "candidate_status_reason": state.get("candidate_status_reason") or "lane_promotion_state_diagnostic_only",
        "lane_promotion_state": state,
        "lane_promotion_report_health": lane_promotion_report_health(
            report,
            now_utc=now_utc,
            max_age_hours=max_report_age_hours,
        )
        if require_fresh_report
        else None,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Lane Promotion State",
        "",
        "This report is generated from `scripts/lane_promotion_state.py`. It turns the regular-options lane promotion protocol into a rerunnable state artifact. It does not create trades, change scanner policy, submit broker orders, change stops, lower proof bars, or convert research/backfill evidence into production proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Lanes: `{summary['lane_count']}`.",
        f"- State counts: `{json.dumps(summary['state_counts'], sort_keys=True)}`.",
        f"- Candidate status counts: `{json.dumps(summary['candidate_status_counts'], sort_keys=True)}`.",
        f"- Live-validation lanes: `{summary['live_validation_lane_count']}`.",
        f"- Auto-track lanes: `{summary['auto_track_lane_count']}`.",
        f"- Current live-exact negative open rows: `{summary['global_live_exact_negative_count']}`.",
        f"- Live policy change: `{summary['live_policy_change']}`.",
        "",
        "## Promotion Contract",
        "",
        "- `diagnostic`: the lane is outside regular auto-track scope, lacks clean data, lacks a lane row, or is not profitable enough.",
        "- `paper_probation`: the lane is historically profitable enough to study, but still lacks fresh walk-forward/paper/risk clearance.",
        "- `live_validation`: the lane may enter fresh validation; this still is not broker execution by itself.",
        "- `auto_track`: reserved for an explicit future release review after live-validation gates pass.",
        "",
        "## Lane States",
        "",
        "| Lane | State | Candidate status | PF | Avg P&L % | Fresh ready | Exact realized | Main blockers |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["lane_state_rows"]:
        metrics = row.get("lane_gate_metrics") if isinstance(row.get("lane_gate_metrics"), dict) else {}
        fresh = row.get("fresh_evidence") if isinstance(row.get("fresh_evidence"), dict) else {}
        blockers = ", ".join(row.get("blockers") or row.get("failed_promotion_gates") or [])
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("playbook_id")),
                    _fmt(row.get("promotion_state")),
                    _fmt(row.get("candidate_status")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("avg_net_pnl_pct")),
                    _fmt(fresh.get("promotion_ready_count", 0)),
                    _fmt(fresh.get("exact_realized_pnl_count", 0)),
                    _fmt(blockers),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Input Health",
            "",
            f"- Lane profitability gate: `{json.dumps(report['input_health']['lane_profitability_gate'], sort_keys=True)}`.",
            f"- Filter matrix loaded: `{report['input_health']['filter_matrix_loaded']}`.",
            f"- Fresh evidence loop loaded: `{report['input_health']['fresh_evidence_loop_loaded']}`.",
            f"- Open risk loaded: `{report['input_health']['open_risk_loaded']}`.",
            f"- Current-policy circuit breaker loaded: `{report['input_health']['current_policy_circuit_breaker_loaded']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_json: Path = DEFAULT_LANE_PROMOTION_REPORT,
    output_markdown: Path = DEFAULT_LANE_PROMOTION_MARKDOWN,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    markdown = render_markdown(report)
    output_markdown.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")


def build_from_paths(
    *,
    lane_gate_report_path: Path = DEFAULT_LANE_GATE_REPORT,
    filter_matrix_path: Path = DEFAULT_FILTER_MATRIX,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE_LOOP,
    open_risk_path: Path = DEFAULT_OPEN_RISK_REPORT,
    circuit_breaker_path: Path = DEFAULT_CIRCUIT_BREAKER,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    return build_lane_promotion_state(
        lane_gate_report=load_lane_gate_report(lane_gate_report_path),
        filter_matrix=_load_json(filter_matrix_path),
        fresh_evidence=_load_json(fresh_evidence_path),
        open_risk=_load_json(open_risk_path),
        circuit_breaker=_load_json(circuit_breaker_path),
        generated_at_utc=generated_at_utc,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options lane promotion-state readback.")
    parser.add_argument("--lane-gate-report", type=Path, default=DEFAULT_LANE_GATE_REPORT)
    parser.add_argument("--filter-matrix", type=Path, default=DEFAULT_FILTER_MATRIX)
    parser.add_argument("--fresh-evidence-loop", type=Path, default=DEFAULT_FRESH_EVIDENCE_LOOP)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK_REPORT)
    parser.add_argument("--circuit-breaker", type=Path, default=DEFAULT_CIRCUIT_BREAKER)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_LANE_PROMOTION_REPORT)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_LANE_PROMOTION_MARKDOWN)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_from_paths(
        lane_gate_report_path=args.lane_gate_report,
        filter_matrix_path=args.filter_matrix,
        fresh_evidence_path=args.fresh_evidence_loop,
        open_risk_path=args.open_risk,
        circuit_breaker_path=args.circuit_breaker,
    )
    if not args.no_write:
        write_outputs(
            report,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
            docs_report=args.docs_report,
        )
    if args.json:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']} lanes={report['summary']['lane_count']} "
            f"states={json.dumps(report['summary']['state_counts'], sort_keys=True)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
