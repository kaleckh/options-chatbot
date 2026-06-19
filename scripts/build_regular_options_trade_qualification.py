from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_trade_qualification"

DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_MONTHLY_PROFITABILITY = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json"
DEFAULT_FRESH_EVIDENCE = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_PAPER_SHORTLIST = ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist" / "latest.json"
DEFAULT_PROFIT_CAPTURE_QUEUE = ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
DEFAULT_REPAIR_BURNDOWN = ROOT / "data" / "profitability-lab" / "regular-options-repair-burndown" / "latest.json"
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_OPEN_RISK_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_open_risk_resolution_plan_latest.json"
DEFAULT_FILL_ATTEMPT_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_fill_attempt_evidence_capture_plan_latest.json"
DEFAULT_SUGGESTED_REVIEW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_suggested_trade_review_plan_latest.json"
DEFAULT_WALK_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_ROBUST_SEARCH = ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-trade-qualification.md"

MAX_SOURCE_AGE_HOURS = 96

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_trade_qualification",
    "do_not_submit_broker_orders_from_trade_qualification",
    "do_not_change_scanner_policy_from_trade_qualification",
    "do_not_change_stops_from_trade_qualification",
    "do_not_change_sizing_from_trade_qualification",
    "do_not_enable_live_validation_from_trade_qualification",
    "do_not_enable_auto_track_from_trade_qualification",
    "do_not_lower_exact_executable_proof_bars_from_trade_qualification",
    "do_not_mutate_evidence_databases_from_trade_qualification",
)

REQUIRED_EVIDENCE_BEFORE_PROMOTION = (
    "fresh executable exact OPRA/NBBO entry evidence for the lane after freeze",
    "fresh executable exact OPRA/NBBO exit evidence and exact realized P&L for the lane",
    "promotion_ready_count greater than zero from fresh forward evidence",
    "sufficient fresh forward sample size under the policy-defined lane gate",
    "positive lane economics under executable pricing, not midpoint, EOD, stale, or display-only marks",
    "open-risk governor passing from fresh executable review or legitimate exit evidence",
    "no active no-chase or quarantine blocker for the lane",
    "paper-shadow/probation evidence bridge complete before any promotion discussion",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _norm(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _load_json_artifact(
    path: Path,
    *,
    name: str,
    required: bool,
    generated_at_utc: str,
    max_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": [],
        "error": None,
    }
    if not path.exists():
        source["reason_codes"] = ["missing_readback"]
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source["status"] = "malformed"
        source["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        source["reason_codes"] = ["malformed_readback"]
        return {}, source
    except OSError as exc:
        source["status"] = "unreadable"
        source["error"] = type(exc).__name__
        source["reason_codes"] = ["unreadable_readback"]
        return {}, source
    if not isinstance(payload, dict):
        source["status"] = "invalid"
        source["reason_codes"] = ["json_root_not_object"]
        return {}, source

    generated = payload.get("generated_at_utc")
    source["generated_at_utc"] = generated
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    generated_dt = _parse_utc(generated)
    if generated_dt is None:
        source["status"] = "stale"
        source["reason_codes"] = ["missing_or_malformed_generated_at_utc", "stale_readback"]
        return payload, source
    age_hours = (as_of - generated_dt).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        source["status"] = "invalid"
        source["reason_codes"] = ["readback_generated_in_future"]
        return payload, source
    if age_hours > max_age_hours:
        source["status"] = "stale"
        source["reason_codes"] = ["stale_readback"]
        return payload, source
    source["status"] = "loaded"
    source["reason_codes"] = []
    source["report_id"] = payload.get("report_id") or name
    return payload, source


def _source_blocked(source_artifacts: dict[str, dict[str, Any]]) -> bool:
    return any(meta.get("required") and meta.get("status") != "loaded" for meta in source_artifacts.values())


def _contains_blocked(value: Any) -> bool:
    text = str(value or "").lower()
    return "blocked" in text or "no_live_release" in text or "no_live" in text


def _no_chase_active(gateboard: dict[str, Any]) -> bool:
    manifest = _as_dict(gateboard.get("no_chase_manifest"))
    return _norm(manifest.get("status")) == "no_chase_active"


def _open_risk_status(
    open_risk: dict[str, Any],
    lane_promotion: dict[str, Any],
    candidate_ledger: dict[str, Any],
    monthly: dict[str, Any],
) -> dict[str, Any]:
    candidates = []
    governor = _as_dict(open_risk.get("open_risk_governor"))
    if governor:
        candidates.append(
            {
                "source": "open_position_risk",
                "status": governor.get("status"),
                "live_entry_allowed": governor.get("live_entry_allowed"),
                "blockers": _as_list(governor.get("blockers")),
            }
        )
    promotion_summary = _as_dict(lane_promotion.get("summary"))
    if promotion_summary:
        candidates.append(
            {
                "source": "lane_promotion_state",
                "status": promotion_summary.get("open_risk_governor_status"),
                "live_entry_allowed": None,
                "blockers": _as_list(promotion_summary.get("open_risk_governor_blockers")),
            }
        )
    ledger_summary = _as_dict(candidate_ledger.get("summary"))
    if ledger_summary:
        candidates.append(
            {
                "source": "candidate_outcome_ledger",
                "status": ledger_summary.get("open_risk_status"),
                "live_entry_allowed": ledger_summary.get("open_risk_live_entry_allowed"),
                "blockers": [],
            }
        )
    risk_portfolio = _as_dict(monthly.get("risk_portfolio"))
    if risk_portfolio:
        candidates.append(
            {
                "source": "monthly_profitability",
                "status": risk_portfolio.get("open_risk_status"),
                "live_entry_allowed": risk_portfolio.get("live_entry_allowed"),
                "blockers": _as_list(risk_portfolio.get("blockers")),
            }
        )

    blocked = any(_contains_blocked(item.get("status")) or item.get("live_entry_allowed") is False for item in candidates)
    contradictory = bool(candidates) and any(
        _norm(item.get("status")) in {"open_risk_governor_pass", "pass"} or item.get("live_entry_allowed") is True
        for item in candidates
    ) and blocked
    status = "open_risk_governor_blocked" if blocked else "open_risk_governor_pass"
    reason_codes = ["open_risk_governor_blocked"] if blocked else []
    if contradictory:
        reason_codes.append("contradictory_open_risk_readbacks_fail_closed")
    return {
        "status": status,
        "new_scanner_origin_entries_allowed": not blocked,
        "reason_codes": reason_codes,
        "sources": candidates,
    }


def _fresh_lane_counts(fresh_evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"fresh_exact_entry_count": 0, "exact_realized_pnl_count": 0, "dates": []})
    for row in _as_list(fresh_evidence.get("candidates")):
        if not isinstance(row, dict):
            continue
        lane = _norm(row.get("playbook_id") or row.get("lane_id"))
        if not lane:
            continue
        if _norm(row.get("entry_evidence_status")) == "fresh_executable_exact_entry":
            counts[lane]["fresh_exact_entry_count"] += 1
        if _norm(row.get("realized_pnl_status")) == "exact_realized_pnl_available" or row.get("promotion_discussion_ready"):
            counts[lane]["exact_realized_pnl_count"] += 1
        scan_date = _norm(row.get("scan_date"))
        if scan_date:
            counts[lane]["dates"].append(scan_date)
    return counts


def _leaderboard_by_lane(monthly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _as_list(monthly.get("lane_leaderboard")):
        if isinstance(row, dict) and _norm(row.get("lane")):
            result[_norm(row.get("lane"))] = row
    return result


def _lane_decision(
    row: dict[str, Any],
    *,
    leaderboard: dict[str, dict[str, Any]],
    lane_counts: dict[str, dict[str, Any]],
    no_chase_active: bool,
    exact_realized_total: int,
    promotion_ready_total: int,
) -> dict[str, Any]:
    lane_id = _norm(row.get("lane") or row.get("lane_id"))
    board = leaderboard.get(lane_id, {})
    disposition = _norm(row.get("disposition") or row.get("source_decision"))
    promotion_state = row.get("promotion_state")
    counts = lane_counts.get(lane_id, {})
    dates = sorted(str(value) for value in counts.get("dates", []) if value)
    priced_rows = _safe_int(row.get("priced") if row.get("priced") is not None else row.get("rows"))
    profit_factor = _safe_float(row.get("profit_factor"))
    avg_net = _safe_float(row.get("avg_net_pnl_pct"))
    median_net = _safe_float(row.get("median_net_pnl_pct"))
    if median_net is None:
        median_net = _safe_float(board.get("median_net_pnl_pct"))
    win_rate = _safe_float(row.get("win_rate_pct"))
    if win_rate is None:
        win_rate = _safe_float(board.get("win_rate_pct"))
    exact_realized = _safe_int(counts.get("exact_realized_pnl_count"))
    fresh_exact = _safe_int(counts.get("fresh_exact_entry_count"))

    reason_codes = _unique(_as_list(row.get("blockers")))
    if no_chase_active:
        reason_codes.append("no_chase_active")
    if exact_realized_total == 0:
        reason_codes.append("no_exact_realized_pnl_rows")
    if promotion_ready_total == 0:
        reason_codes.append("no_promotion_ready_rows")
    if exact_realized == 0 and (profit_factor or 0) > 1 and (avg_net or 0) > 0:
        reason_codes.append("positive_historical_lane_without_fresh_exact_realized_pnl")
    if priced_rows < 30:
        reason_codes.append("insufficient_priced_exact_sample")

    if disposition in {"quarantine", "archive"}:
        decision = "quarantine_no_chase"
        next_action = "Keep lane parked; require earn-back or frozen retest before any fresh collection."
    elif disposition == "needs_replay_engine":
        decision = "needs_replay_engine"
        next_action = "Repair replay/source evidence before treating historical economics as usable."
    elif disposition == "paper_shadow" or _norm(promotion_state) == "paper_probation":
        decision = "paper_shadow_collect"
        next_action = "Collect fresh exact entry and exact realized exit evidence; do not route live."
    elif (profit_factor or 0) > 1 and (avg_net or 0) > 0 and exact_realized == 0:
        decision = "evidence_repair_only"
        next_action = "Bridge historical signal to fresh executable exact evidence before promotion discussion."
    elif priced_rows < 30:
        decision = "insufficient_sample"
        next_action = "Collect or repair exact priced outcomes before lane decisions."
    else:
        decision = "diagnostic_only"
        next_action = "Keep diagnostic; do not chase or promote from this readback."

    if exact_realized_total > 0 and promotion_ready_total > 0 and not reason_codes:
        decision = "live_blocked"
        reason_codes.append("trade_qualification_script_never_grants_live_permission")

    return {
        "lane_id": lane_id,
        "disposition": disposition or None,
        "promotion_state": promotion_state,
        "priced_rows": priced_rows,
        "profit_factor": profit_factor,
        "avg_net_pnl_pct": avg_net,
        "median_net_pnl_pct": median_net,
        "win_rate_pct": win_rate,
        "exact_realized_pnl_count": exact_realized,
        "fresh_exact_entry_count": fresh_exact,
        "sample_window_start": dates[0] if dates else None,
        "sample_window_end": dates[-1] if dates else None,
        "decision": decision,
        "reason_codes": _unique(reason_codes),
        "next_operator_action": next_action,
    }


def _lane_decisions(monthly: dict[str, Any], fresh_evidence: dict[str, Any], no_chase: bool, exact_realized: int, promotion_ready: int) -> list[dict[str, Any]]:
    dispositions = _as_list(_as_dict(monthly.get("lane_dispositions")).get("dispositions"))
    leaderboard = _leaderboard_by_lane(monthly)
    lane_counts = _fresh_lane_counts(fresh_evidence)
    decisions = [
        _lane_decision(
            row,
            leaderboard=leaderboard,
            lane_counts=lane_counts,
            no_chase_active=no_chase,
            exact_realized_total=exact_realized,
            promotion_ready_total=promotion_ready,
        )
        for row in dispositions
        if isinstance(row, dict)
    ]
    return sorted(decisions, key=lambda item: (_norm(item.get("decision")), _norm(item.get("lane_id"))))


def _best_current_lane(lane_decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in lane_decisions
        if row.get("decision") == "paper_shadow_collect"
        and (row.get("profit_factor") or 0) > 1
        and (row.get("avg_net_pnl_pct") or 0) > 0
    ]
    if not candidates:
        return None
    best = sorted(candidates, key=lambda row: ((row.get("profit_factor") or 0), (row.get("avg_net_pnl_pct") or 0)), reverse=True)[0]
    return {
        "lane_id": best.get("lane_id"),
        "decision": best.get("decision"),
        "profit_factor": best.get("profit_factor"),
        "avg_net_pnl_pct": best.get("avg_net_pnl_pct"),
        "fresh_exact_entry_count": best.get("fresh_exact_entry_count"),
        "exact_realized_pnl_count": best.get("exact_realized_pnl_count"),
        "operator_action": "paper-shadow evidence collection only; capture fresh exact entries and policy-defined exact exits.",
    }


def _count_from_action_counts(report: dict[str, Any], action: str) -> int:
    return _safe_int(_as_dict(_as_dict(report.get("summary")).get("action_counts")).get(action))


def _operator_queue(
    *,
    open_risk_status: dict[str, Any],
    candidate_ledger: dict[str, Any],
    fresh_evidence: dict[str, Any],
    fill_attempt_plan: dict[str, Any],
    suggested_review_plan: dict[str, Any],
    repair_burndown: dict[str, Any],
    lane_decisions: list[dict[str, Any]],
    best_lane: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    fresh_summary = _as_dict(fresh_evidence.get("summary"))
    fill_summary = _as_dict(fill_attempt_plan.get("summary"))
    suggested_summary = _as_dict(suggested_review_plan.get("summary"))
    repair_summary = _as_dict(repair_burndown.get("summary"))
    queue = [
        {
            "priority": 1,
            "action": "resolve_open_risk_governor",
            "count": 1 if open_risk_status.get("status") == "open_risk_governor_blocked" else 0,
            "operator_next_step": "Resolve only with fresh executable open-position review or legitimate exit evidence; do not open scanner-origin rows while blocked.",
            "trade_recommendation": False,
        },
        {
            "priority": 2,
            "action": "collect_exact_exit_evidence",
            "count": max(_count_from_action_counts(candidate_ledger, "collect_exact_exit_evidence"), _safe_int(fresh_summary.get("exact_exit_bridge_count"))),
            "operator_next_step": "Collect exact exit evidence for linked/live exact rows only when policy-defined exit conditions fire.",
            "trade_recommendation": False,
        },
        {
            "priority": 3,
            "action": "collect_paper_shadow_exact_evidence",
            "count": 1 if best_lane else 0,
            "lane_id": best_lane.get("lane_id") if best_lane else None,
            "operator_next_step": "Collect fresh exact entry and exact realized exit evidence for the strongest paper-shadow lane.",
            "trade_recommendation": False,
        },
        {
            "priority": 4,
            "action": "capture_missing_fill_attempt_evidence",
            "count": max(
                _count_from_action_counts(candidate_ledger, "capture_missing_fill_attempt_evidence"),
                _safe_int(fill_summary.get("missing_fill_attempt_evidence_count")),
            ),
            "operator_next_step": "Capture missing fill-attempt evidence only for fresh selections during a valid market-data window.",
            "trade_recommendation": False,
        },
        {
            "priority": 5,
            "action": "refresh_suggested_trade_reviews",
            "count": max(
                _count_from_action_counts(candidate_ledger, "refresh_suggested_trade_review"),
                _safe_int(suggested_summary.get("attention_trade_count")),
                _safe_int(suggested_summary.get("suggested_attention_count")),
            ),
            "operator_next_step": "Refresh suggested-trade reviews during valid market-data windows; this is review attention, not a trade recommendation.",
            "trade_recommendation": False,
        },
        {
            "priority": 6,
            "action": "repair_replay_source_evidence",
            "count": _safe_int(repair_summary.get("active_exact_repair_target_count")) + _safe_int(repair_summary.get("source_replay_required_target_count")),
            "operator_next_step": "Repair replay/source evidence only where the repair burn-down target is active and unexhausted.",
            "trade_recommendation": False,
        },
        {
            "priority": 7,
            "action": "keep_broad_quarantined_lanes_parked",
            "count": sum(1 for row in lane_decisions if row.get("decision") == "quarantine_no_chase"),
            "operator_next_step": "Keep broad and quarantined lanes parked; do not chase historical winners.",
            "trade_recommendation": False,
        },
    ]
    return [item for item in queue if _safe_int(item.get("count")) > 0]


def _prohibited_actions(gateboard: dict[str, Any], monthly: dict[str, Any]) -> list[str]:
    manifest = _as_dict(gateboard.get("no_chase_manifest"))
    return _unique(list(PROHIBITED_ACTIONS) + _as_list(manifest.get("prohibited_actions")) + _as_list(monthly.get("prohibited_actions")))


def _overall_status(
    *,
    source_artifacts: dict[str, dict[str, Any]],
    gateboard: dict[str, Any],
    live_entry_allowed: bool,
    best_lane: dict[str, Any] | None,
    operator_queue: list[dict[str, Any]],
) -> str:
    if _source_blocked(source_artifacts):
        return "blocked_missing_readbacks"
    if not live_entry_allowed and (_contains_blocked(gateboard.get("overall_status")) or _no_chase_active(gateboard)):
        return "blocked_no_live_release"
    if best_lane:
        return "paper_shadow_only"
    if any(item.get("action") == "repair_replay_source_evidence" for item in operator_queue):
        return "repair_only"
    return "evidence_collection_only"


def build_report(
    *,
    gateboard_path: Path = DEFAULT_GATEBOARD,
    monthly_profitability_path: Path = DEFAULT_MONTHLY_PROFITABILITY,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    candidate_ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE,
    paper_shortlist_path: Path = DEFAULT_PAPER_SHORTLIST,
    profit_capture_queue_path: Path = DEFAULT_PROFIT_CAPTURE_QUEUE,
    repair_burndown_path: Path = DEFAULT_REPAIR_BURNDOWN,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    suggested_close_risk_path: Path = DEFAULT_SUGGESTED_CLOSE_RISK,
    open_risk_plan_path: Path = DEFAULT_OPEN_RISK_PLAN,
    fill_attempt_plan_path: Path = DEFAULT_FILL_ATTEMPT_PLAN,
    suggested_review_plan_path: Path = DEFAULT_SUGGESTED_REVIEW_PLAN,
    walk_forward_path: Path = DEFAULT_WALK_FORWARD,
    robust_search_path: Path = DEFAULT_ROBUST_SEARCH,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    specs = {
        "gateboard": (gateboard_path, True),
        "monthly_profitability": (monthly_profitability_path, True),
        "lane_promotion_state": (lane_promotion_path, True),
        "candidate_outcome_ledger": (candidate_ledger_path, True),
        "fresh_evidence_loop": (fresh_evidence_path, True),
        "paper_shortlist": (paper_shortlist_path, True),
        "profit_capture_queue": (profit_capture_queue_path, True),
        "repair_burndown": (repair_burndown_path, True),
        "open_position_risk": (open_risk_path, True),
        "suggested_trade_close_risk": (suggested_close_risk_path, True),
        "open_risk_resolution_plan": (open_risk_plan_path, True),
        "fill_attempt_evidence_capture_plan": (fill_attempt_plan_path, True),
        "suggested_trade_review_plan": (suggested_review_plan_path, True),
        "historical_walk_forward": (walk_forward_path, True),
        "robust_search_evaluation": (robust_search_path, True),
    }
    loaded: dict[str, dict[str, Any]] = {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    for name, (path, required) in specs.items():
        payload, source = _load_json_artifact(
            path,
            name=name,
            required=required,
            generated_at_utc=generated_at,
            max_age_hours=max_source_age_hours,
        )
        loaded[name] = payload
        source_artifacts[name] = source

    gateboard = loaded["gateboard"]
    monthly = loaded["monthly_profitability"]
    lane_promotion = loaded["lane_promotion_state"]
    candidate_ledger = loaded["candidate_outcome_ledger"]
    fresh_evidence = loaded["fresh_evidence_loop"]
    no_chase = _no_chase_active(gateboard)
    fresh_summary = _as_dict(fresh_evidence.get("summary"))
    ledger_summary = _as_dict(candidate_ledger.get("summary"))
    exact_realized = max(_safe_int(fresh_summary.get("exact_realized_pnl_count")), _safe_int(ledger_summary.get("exact_realized_pnl_count")))
    fresh_exact_entry = _safe_int(_as_dict(fresh_summary.get("entry_evidence_status_counts")).get("fresh_executable_exact_entry"))
    promotion_ready = max(
        _safe_int(fresh_summary.get("promotion_discussion_ready_count")),
        _safe_int(ledger_summary.get("promotion_discussion_ready_count")),
    )
    paper_review_candidate_count = _safe_int(_as_dict(loaded["paper_shortlist"].get("summary")).get("eligible_count"))

    open_status = _open_risk_status(loaded["open_position_risk"], lane_promotion, candidate_ledger, monthly)
    source_blocked = _source_blocked(source_artifacts)
    gateboard_live_blocked = _contains_blocked(gateboard.get("overall_status"))
    promotion_summary = _as_dict(lane_promotion.get("summary"))
    promotion_live_blocked = _safe_int(promotion_summary.get("live_validation_lane_count")) == 0 or _safe_int(promotion_summary.get("auto_track_lane_count")) == 0
    live_entry_allowed = (
        not source_blocked
        and not gateboard_live_blocked
        and not promotion_live_blocked
        and open_status.get("status") != "open_risk_governor_blocked"
        and exact_realized > 0
        and promotion_ready > 0
    )
    auto_track_allowed = live_entry_allowed and _safe_int(promotion_summary.get("auto_track_lane_count")) > 0

    decisions = _lane_decisions(monthly, fresh_evidence, no_chase, exact_realized, promotion_ready)
    best_lane = _best_current_lane(decisions)
    queue = _operator_queue(
        open_risk_status=open_status,
        candidate_ledger=candidate_ledger,
        fresh_evidence=fresh_evidence,
        fill_attempt_plan=loaded["fill_attempt_evidence_capture_plan"],
        suggested_review_plan=loaded["suggested_trade_review_plan"],
        repair_burndown=loaded["repair_burndown"],
        lane_decisions=decisions,
        best_lane=best_lane,
    )

    prohibited = _prohibited_actions(gateboard, monthly)
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_trade_qualification_profitability_triage",
        "read_only": True,
        "source_artifacts": source_artifacts,
        "overall_status": _overall_status(
            source_artifacts=source_artifacts,
            gateboard=gateboard,
            live_entry_allowed=live_entry_allowed,
            best_lane=best_lane,
            operator_queue=queue,
        ),
        "live_entry_allowed": bool(live_entry_allowed),
        "auto_track_allowed": bool(auto_track_allowed),
        "broker_order_allowed": False,
        "no_chase_active": bool(no_chase),
        "exact_realized_pnl_count": exact_realized,
        "fresh_exact_entry_count": fresh_exact_entry,
        "promotion_ready_count": promotion_ready,
        "paper_review_candidate_count": paper_review_candidate_count,
        "open_risk_status": open_status,
        "best_current_lane_if_any": best_lane,
        "lane_decisions": decisions,
        "operator_queue": queue,
        "prohibited_actions": prohibited,
        "required_evidence_before_promotion": list(REQUIRED_EVIDENCE_BEFORE_PROMOTION),
        "historical_signatures": {
            "walk_forward_status": loaded["historical_walk_forward"].get("status"),
            "robust_search_status": loaded["robust_search_evaluation"].get("status"),
            "actionability": "historical robust-search and walk-forward results can nominate or reject future forward candidates, but are not fresh forward proof by themselves.",
        },
        "non_goals": [
            "create trades",
            "submit broker orders",
            "change stops",
            "change scanner policy",
            "change sizing",
            "lower proof bars",
            "promote lanes",
            "mutate evidence databases",
        ],
    }
    return report


def _status_answer(report: dict[str, Any]) -> str:
    if report.get("overall_status") == "blocked_missing_readbacks":
        return "No live release. Best current action: repair missing or stale local readbacks before evidence collection."
    if report.get("best_current_lane_if_any"):
        return "No live release. Best current action: paper-shadow/evidence collection only."
    return "No live release. Best current action: diagnostic repair and evidence readback hygiene only."


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    best = _as_dict(report.get("best_current_lane_if_any"))
    open_status = _as_dict(report.get("open_risk_status"))
    source_status_counts = Counter(_norm(meta.get("status")) for meta in _as_dict(report.get("source_artifacts")).values())
    lane_decision_counts = Counter(_norm(row.get("decision")) for row in _as_list(report.get("lane_decisions")) if isinstance(row, dict))
    lines = [
        "# Regular Options Trade Qualification",
        "",
        _status_answer(report),
        "",
        "## At a glance",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Live entry allowed: `{str(bool(report.get('live_entry_allowed'))).lower()}`.",
        f"- Auto-track allowed: `{str(bool(report.get('auto_track_allowed'))).lower()}`.",
        f"- Broker order allowed: `{str(bool(report.get('broker_order_allowed'))).lower()}`.",
        f"- No-chase active: `{str(bool(report.get('no_chase_active'))).lower()}`.",
        f"- Fresh exact entry rows: `{report.get('fresh_exact_entry_count')}`.",
        f"- Exact realized P&L rows: `{report.get('exact_realized_pnl_count')}`.",
        f"- Promotion-ready rows: `{report.get('promotion_ready_count')}`.",
        f"- Paper-review candidates: `{report.get('paper_review_candidate_count')}`.",
        f"- Open-risk status: `{open_status.get('status')}`.",
        f"- Lane decisions: `{_json_inline(dict(sorted(lane_decision_counts.items())))}`.",
        "",
        "## Best current lane, if any",
        "",
    ]
    if best:
        lines.extend(
            [
                f"- Lane: `{best.get('lane_id')}`.",
                f"- Decision: `{best.get('decision')}`.",
                f"- Profit factor: `{best.get('profit_factor')}`.",
                f"- Average net P&L pct: `{best.get('avg_net_pnl_pct')}`.",
                f"- Fresh exact entry count: `{best.get('fresh_exact_entry_count')}`.",
                f"- Exact realized P&L count: `{best.get('exact_realized_pnl_count')}`.",
                f"- Operator action: {best.get('operator_action')}",
            ]
        )
    else:
        lines.append("- None. No lane has enough fresh executable proof for promotion, and no lane is live-ready.")
    lines.extend(["", "## Lane table", "", "| Lane | Disposition | Decision | PF | Avg % | Median % | Win % | Priced | Fresh entries | Exact realized | Next action |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
    for row in _as_list(report.get("lane_decisions")):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('lane_id')}`",
                    f"`{row.get('disposition')}`",
                    f"`{row.get('decision')}`",
                    f"`{row.get('profit_factor')}`",
                    f"`{row.get('avg_net_pnl_pct')}`",
                    f"`{row.get('median_net_pnl_pct')}`",
                    f"`{row.get('win_rate_pct')}`",
                    f"`{row.get('priced_rows')}`",
                    f"`{row.get('fresh_exact_entry_count')}`",
                    f"`{row.get('exact_realized_pnl_count')}`",
                    _norm(row.get("next_operator_action")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Why live trading is blocked",
            "",
        ]
    )
    blockers = []
    if not report.get("live_entry_allowed"):
        blockers.append("live_entry_allowed is false")
    if not report.get("auto_track_allowed"):
        blockers.append("auto_track_allowed is false")
    if report.get("broker_order_allowed") is False:
        blockers.append("broker_order_allowed is permanently false for this report")
    if report.get("exact_realized_pnl_count") == 0:
        blockers.append("exact_realized_pnl_count is 0")
    if report.get("promotion_ready_count") == 0:
        blockers.append("promotion_ready_count is 0")
    blockers.extend(open_status.get("reason_codes") or [])
    if report.get("overall_status") == "blocked_missing_readbacks":
        blockers.append("one or more required source readbacks is missing, stale, malformed, or contradictory")
    for blocker in _unique(blockers):
        lines.append(f"- {blocker}.")
    lines.extend(["", "## Next market-window actions", ""])
    for item in _as_list(report.get("operator_queue")):
        if isinstance(item, dict):
            lines.append(f"- `{item.get('priority')}` `{item.get('action')}` count `{item.get('count')}`: {item.get('operator_next_step')}")
    lines.extend(["", "## Evidence repair queue", ""])
    repair_items = [
        item for item in _as_list(report.get("operator_queue")) if isinstance(item, dict) and item.get("action") == "repair_replay_source_evidence"
    ]
    if repair_items:
        for item in repair_items:
            lines.append(f"- Active/unexhausted repair targets: `{item.get('count')}`. {item.get('operator_next_step')}")
    else:
        lines.append("- No active repair item was promoted by the current readbacks.")
    lines.extend(["", "## What not to do", ""])
    for action in _as_list(report.get("prohibited_actions")):
        lines.append(f"- `{action}`")
    lines.extend(["", "## Promotion requirements still missing", ""])
    for requirement in _as_list(report.get("required_evidence_before_promotion")):
        lines.append(f"- {requirement}.")
    lines.extend(["", "## Source artifacts and staleness", "", "| Source | Status | Age hours | Generated at | Reasons |", "| --- | --- | ---: | --- | --- |"])
    for name, meta in sorted(_as_dict(report.get("source_artifacts")).items()):
        if not isinstance(meta, dict):
            continue
        lines.append(
            f"| `{name}` | `{meta.get('status')}` | `{meta.get('age_hours')}` | `{meta.get('generated_at_utc')}` | `{_json_inline(meta.get('reason_codes') or [])}` |"
        )
    lines.extend(
        [
            "",
            f"Source status counts: `{_json_inline(dict(sorted(source_status_counts.items())))}`.",
            "",
            "## Non-goals",
            "",
            "This report does not:",
            "",
            "- create trades",
            "- submit broker orders",
            "- change stops",
            "- change scanner policy",
            "- change sizing",
            "- lower proof bars",
            "- promote lanes",
            "- mutate evidence databases",
            "",
            "It also does not enable live validation or auto-track.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only regular options trade qualification triage.")
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--monthly-profitability", type=Path, default=DEFAULT_MONTHLY_PROFITABILITY)
    parser.add_argument("--lane-promotion", type=Path, default=DEFAULT_LANE_PROMOTION)
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--fresh-evidence", type=Path, default=DEFAULT_FRESH_EVIDENCE)
    parser.add_argument("--paper-shortlist", type=Path, default=DEFAULT_PAPER_SHORTLIST)
    parser.add_argument("--profit-capture-queue", type=Path, default=DEFAULT_PROFIT_CAPTURE_QUEUE)
    parser.add_argument("--repair-burndown", type=Path, default=DEFAULT_REPAIR_BURNDOWN)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--suggested-close-risk", type=Path, default=DEFAULT_SUGGESTED_CLOSE_RISK)
    parser.add_argument("--open-risk-plan", type=Path, default=DEFAULT_OPEN_RISK_PLAN)
    parser.add_argument("--fill-attempt-plan", type=Path, default=DEFAULT_FILL_ATTEMPT_PLAN)
    parser.add_argument("--suggested-review-plan", type=Path, default=DEFAULT_SUGGESTED_REVIEW_PLAN)
    parser.add_argument("--walk-forward", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--robust-search", type=Path, default=DEFAULT_ROBUST_SEARCH)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        gateboard_path=args.gateboard,
        monthly_profitability_path=args.monthly_profitability,
        lane_promotion_path=args.lane_promotion,
        candidate_ledger_path=args.candidate_ledger,
        fresh_evidence_path=args.fresh_evidence,
        paper_shortlist_path=args.paper_shortlist,
        profit_capture_queue_path=args.profit_capture_queue,
        repair_burndown_path=args.repair_burndown,
        open_risk_path=args.open_risk,
        suggested_close_risk_path=args.suggested_close_risk,
        open_risk_plan_path=args.open_risk_plan,
        fill_attempt_plan_path=args.fill_attempt_plan,
        suggested_review_plan_path=args.suggested_review_plan,
        walk_forward_path=args.walk_forward,
        robust_search_path=args.robust_search,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
