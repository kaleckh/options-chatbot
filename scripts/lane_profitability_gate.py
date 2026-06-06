from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_LANE_GATE_REPORT = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_LANE_GATE_MAX_AGE_HOURS = 36.0

from scripts.candidate_lifecycle import (
    STATUS_DIAGNOSTIC_LANE_PROFITABILITY_GATE,
    STATUS_PAPER_LANE_PROFITABILITY_GATE,
    STATUS_PAPER_LANE_PROFITABILITY_PROBATION,
    STATUS_PENDING_LIVE_VALIDATION,
    is_paper_only_status,
)

LANE_GATE_PENDING_STATUS = STATUS_PENDING_LIVE_VALIDATION
LANE_GATE_DIAGNOSTIC_STATUS = STATUS_DIAGNOSTIC_LANE_PROFITABILITY_GATE
LANE_GATE_PAPER_ONLY_STATUS = STATUS_PAPER_LANE_PROFITABILITY_GATE
LANE_GATE_PROBATION_PAPER_STATUS = STATUS_PAPER_LANE_PROFITABILITY_PROBATION


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def load_lane_gate_report(path: Path | str | None = DEFAULT_LANE_GATE_REPORT) -> dict[str, Any] | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_utc_datetime(value: Any) -> datetime | None:
    text = _norm_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def lane_gate_report_health(
    report: dict[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_age_hours: float = DEFAULT_LANE_GATE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_missing",
            "generated_at_utc": None,
            "age_hours": None,
            "max_age_hours": max_age_hours,
        }

    generated = _parse_utc_datetime(report.get("generated_at_utc"))
    if generated is None:
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_missing_generated_at_utc",
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
            "reason": "lane_profitability_gate_report_generated_in_future",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if age_hours > max_age_hours:
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_stale",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }

    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_missing_summary",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }

    mark_unpriced_count = int(_safe_float(summary.get("mark_unpriced_count")) or 0)
    if mark_unpriced_count > 0:
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_has_unpriced_rows",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
            "mark_unpriced_count": mark_unpriced_count,
        }

    tracked_row_count = int(_safe_float(summary.get("tracked_row_count")) or 0)
    tracked_rows_with_stored_pnl = int(_safe_float(summary.get("tracked_rows_with_stored_pnl")) or 0)
    if tracked_rows_with_stored_pnl < tracked_row_count:
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_tracked_pnl_incomplete",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
            "tracked_row_count": tracked_row_count,
            "tracked_rows_with_stored_pnl": tracked_rows_with_stored_pnl,
        }

    lane_gate_rows = report.get("lane_gate_rows")
    lane_gates = report.get("lane_gates")
    if not isinstance(lane_gates, dict) and not isinstance(lane_gate_rows, list):
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_missing_lane_rows",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    if isinstance(lane_gate_rows, list) and not lane_gate_rows and not isinstance(lane_gates, dict):
        return {
            "usable": False,
            "reason": "lane_profitability_gate_report_empty_lane_rows",
            "generated_at_utc": report.get("generated_at_utc"),
            "age_hours": round(age_hours, 4),
            "max_age_hours": max_age_hours,
        }
    return {
        "usable": True,
        "reason": "lane_profitability_gate_report_fresh",
        "generated_at_utc": report.get("generated_at_utc"),
        "age_hours": round(age_hours, 4),
        "max_age_hours": max_age_hours,
        "mark_unpriced_count": mark_unpriced_count,
        "tracked_row_count": tracked_row_count,
        "tracked_rows_with_stored_pnl": tracked_rows_with_stored_pnl,
        "latest_intraday_quote_date": (report.get("inputs") or {}).get("latest_intraday_quote_date")
        if isinstance(report.get("inputs"), dict)
        else None,
    }


def lane_gate_for_playbook(report: dict[str, Any] | None, playbook_id: str | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    playbook = _norm_text(playbook_id).lower()
    gates = report.get("lane_gates")
    if isinstance(gates, dict):
        gate = gates.get(playbook)
        if isinstance(gate, dict):
            return gate
    for gate in report.get("lane_gate_rows") or []:
        if isinstance(gate, dict) and _norm_text(gate.get("playbook")).lower() == playbook:
            return gate
    return None


def _nested_mapping(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _candidate_metric(candidate: dict[str, Any], *keys: str) -> float | None:
    sources: list[dict[str, Any]] = [candidate]
    source_pick = candidate.get("source_pick_snapshot")
    if isinstance(source_pick, dict):
        sources.append(source_pick)
    for owner in list(sources):
        for nested_key in ("spread_liquidity", "liquidity", "fill_discipline_snapshot"):
            nested = _nested_mapping(owner, nested_key)
            if nested:
                sources.append(nested)
    for owner in sources:
        for key in keys:
            value = _safe_float(owner.get(key))
            if value is not None:
                return value
    return None


def _candidate_debit_pct(candidate: dict[str, Any]) -> float | None:
    explicit = _safe_float(candidate.get("debit_pct_of_width"))
    if explicit is not None:
        return explicit
    debit = _safe_float(candidate.get("net_debit") or candidate.get("entry_execution_price"))
    long_strike = _safe_float(
        candidate.get("long_strike") if candidate.get("long_strike") is not None else candidate.get("strike")
    )
    short_strike = _safe_float(candidate.get("short_strike"))
    if debit is None or long_strike is None or short_strike is None:
        return None
    width = abs(short_strike - long_strike)
    if width <= 0:
        return None
    return debit / width * 100.0


def candidate_gate_decision(
    *,
    playbook_id: str | None,
    candidate: dict[str, Any] | None = None,
    report: dict[str, Any] | None,
    require_fresh_report: bool = False,
    now_utc: datetime | None = None,
    max_report_age_hours: float = DEFAULT_LANE_GATE_MAX_AGE_HOURS,
    probation_paper_only: bool = False,
    require_present_self_guardrail_metrics: bool = False,
) -> dict[str, Any]:
    playbook = _norm_text(playbook_id).lower()
    pick = candidate if isinstance(candidate, dict) else {}
    if require_fresh_report:
        health = lane_gate_report_health(
            report,
            now_utc=now_utc,
            max_age_hours=max_report_age_hours,
        )
        if not bool(health.get("usable")):
            return {
                "allowed": False,
                "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
                "candidate_status_reason": health.get("reason") or "lane_profitability_gate_report_unusable",
                "lane_gate_status": "report_unusable",
                "lane_gate": None,
                "lane_gate_report_health": health,
            }

    gate = lane_gate_for_playbook(report, playbook)
    if gate is None:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "missing_lane_profitability_gate_report_or_lane_row",
            "lane_gate_status": "missing",
            "lane_gate": None,
        }

    lane_status = _norm_text(gate.get("status") or gate.get("gate_status")).lower()
    blockers = list(gate.get("blockers") or [])
    auto_track_allowed = bool(gate.get("auto_track_allowed"))
    if not auto_track_allowed:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_not_profitable_enough_for_live_validation",
            "lane_gate_status": lane_status,
            "lane_gate_blockers": blockers,
            "lane_gate": gate,
        }

    self_guardrails = gate.get("self_guardrails") if isinstance(gate.get("self_guardrails"), dict) else {}
    ticker = _norm_text(pick.get("ticker")).upper()
    blocked_tickers = {
        _norm_text(item.get("ticker") if isinstance(item, dict) else item).upper()
        for item in self_guardrails.get("blocked_tickers") or []
        if _norm_text(item.get("ticker") if isinstance(item, dict) else item)
    }
    if ticker and ticker in blocked_tickers:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_blocked_negative_ticker_cluster",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
        }

    max_debit_pct = _safe_float(self_guardrails.get("max_debit_pct_of_width"))
    candidate_debit_pct = _candidate_debit_pct(pick)
    if max_debit_pct is not None and candidate_debit_pct is None:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_missing_debit_pct",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "max_debit_pct_of_width": max_debit_pct,
        }
    if max_debit_pct is not None and candidate_debit_pct is not None and candidate_debit_pct > max_debit_pct:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_blocked_debit_pct_outside_profitable_bucket",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "candidate_debit_pct_of_width": round(candidate_debit_pct, 4),
            "max_debit_pct_of_width": max_debit_pct,
        }

    max_fill_degradation_pct = _safe_float(self_guardrails.get("max_fill_degradation_vs_mid_pct"))
    candidate_fill_degradation_pct = _candidate_metric(pick, "fill_degradation_vs_mid_pct")
    if (
        max_fill_degradation_pct is not None
        and candidate_fill_degradation_pct is None
        and require_present_self_guardrail_metrics
    ):
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_missing_fill_degradation",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "max_fill_degradation_vs_mid_pct": max_fill_degradation_pct,
        }
    if (
        max_fill_degradation_pct is not None
        and candidate_fill_degradation_pct is not None
        and candidate_fill_degradation_pct > max_fill_degradation_pct
    ):
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_blocked_fill_degradation_outside_profitable_bucket",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "candidate_fill_degradation_vs_mid_pct": round(candidate_fill_degradation_pct, 4),
            "max_fill_degradation_vs_mid_pct": max_fill_degradation_pct,
        }

    max_worst_leg_spread_pct = _safe_float(self_guardrails.get("max_worst_leg_bid_ask_spread_pct"))
    candidate_worst_leg_spread_pct = _candidate_metric(pick, "worst_leg_bid_ask_spread_pct")
    if (
        max_worst_leg_spread_pct is not None
        and candidate_worst_leg_spread_pct is None
        and require_present_self_guardrail_metrics
    ):
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_missing_worst_leg_spread",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "max_worst_leg_bid_ask_spread_pct": max_worst_leg_spread_pct,
        }
    if (
        max_worst_leg_spread_pct is not None
        and candidate_worst_leg_spread_pct is not None
        and candidate_worst_leg_spread_pct > max_worst_leg_spread_pct
    ):
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_DIAGNOSTIC_STATUS,
            "candidate_status_reason": "lane_self_guardrail_blocked_worst_leg_spread_outside_profitable_bucket",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "candidate_worst_leg_bid_ask_spread_pct": round(candidate_worst_leg_spread_pct, 4),
            "max_worst_leg_bid_ask_spread_pct": max_worst_leg_spread_pct,
        }

    report_health = lane_gate_report_health(report, now_utc=now_utc, max_age_hours=max_report_age_hours) if require_fresh_report else None
    if probation_paper_only:
        return {
            "allowed": False,
            "candidate_status": LANE_GATE_PROBATION_PAPER_STATUS,
            "candidate_status_reason": "lane_profitability_gate_probation_requires_paper_validation",
            "lane_gate_status": lane_status,
            "lane_gate": gate,
            "lane_gate_report_health": report_health,
            "probation_allowed": True,
        }

    return {
        "allowed": True,
        "candidate_status": LANE_GATE_PENDING_STATUS,
        "candidate_status_reason": "lane_profitability_gate_passed",
        "lane_gate_status": lane_status,
        "lane_gate": gate,
        "lane_gate_report_health": report_health,
    }


def paper_only_gate_row(
    row: dict[str, Any],
    *,
    decision: dict[str, Any],
    recorded_at_utc: str,
) -> dict[str, Any]:
    next_row = dict(row)
    decision_status = _norm_text(decision.get("candidate_status"))
    paper_status = decision_status if is_paper_only_status(decision_status) else LANE_GATE_PAPER_ONLY_STATUS
    next_row.update(
        {
            "event_type": "pending_candidate_validation",
            "candidate_status": paper_status,
            "candidate_status_reason": decision.get("candidate_status_reason")
            or "lane_profitability_gate_routes_candidate_to_paper_only",
            "validation_exit_code": None,
            "validation_recorded_at_utc": recorded_at_utc,
            "lane_profitability_gate": {
                "allowed": bool(decision.get("allowed")),
                "lane_gate_status": decision.get("lane_gate_status"),
                "lane_gate_blockers": list(decision.get("lane_gate_blockers") or []),
                "lane_gate_report_health": decision.get("lane_gate_report_health"),
                "candidate_debit_pct_of_width": decision.get("candidate_debit_pct_of_width"),
                "max_debit_pct_of_width": decision.get("max_debit_pct_of_width"),
                "candidate_fill_degradation_vs_mid_pct": decision.get("candidate_fill_degradation_vs_mid_pct"),
                "max_fill_degradation_vs_mid_pct": decision.get("max_fill_degradation_vs_mid_pct"),
                "candidate_worst_leg_bid_ask_spread_pct": decision.get("candidate_worst_leg_bid_ask_spread_pct"),
                "max_worst_leg_bid_ask_spread_pct": decision.get("max_worst_leg_bid_ask_spread_pct"),
                "probation_allowed": bool(decision.get("probation_allowed")),
            },
        }
    )
    if decision.get("lane_promotion_state") is not None or decision.get("lane_promotion_report_health") is not None:
        next_row["lane_promotion_state"] = {
            "allowed": bool(decision.get("allowed")),
            "candidate_status": decision.get("candidate_status"),
            "candidate_status_reason": decision.get("candidate_status_reason"),
            "promotion_state": (decision.get("lane_promotion_state") or {}).get("promotion_state")
            if isinstance(decision.get("lane_promotion_state"), dict)
            else None,
            "failed_promotion_gates": list(
                (decision.get("lane_promotion_state") or {}).get("failed_promotion_gates") or []
            )
            if isinstance(decision.get("lane_promotion_state"), dict)
            else [],
            "blockers": list((decision.get("lane_promotion_state") or {}).get("blockers") or [])
            if isinstance(decision.get("lane_promotion_state"), dict)
            else [],
            "lane_promotion_report_health": decision.get("lane_promotion_report_health"),
        }
    return next_row
